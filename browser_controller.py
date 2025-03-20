import base64
import time
import logging
import subprocess
import platform
import os
from pyexpat.errors import messages
from typing import Optional, Dict, Any, List

from playwright.async_api import async_playwright, Browser, BrowserContext, Page, TimeoutError
import asyncio
from action import Action, Coordinate
from utils.error import BrowserOperationError
from utils.get_absolute_path import get_absolute_path


class BrowserController:
    def __init__(self, website_url: str = None, use_local_chrome: bool = True):
        self.use_local_chrome = use_local_chrome
        # Set Chrome path based on operating system
        if platform.system() == "Darwin":  # macOS
            self.chrome_path = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
        # ToDo: Add support for other platforms
        else:
            self.chrome_path = None  # Will use Playwright's bundled browser

        self.WAIT_TIME = 2  # 统一管理超时常量
        self.is_online = True
        self._state = {'finished': False, 'user_requested': False}
        self._browser = None
        self._page = None
        self._context = None
        self._playwright = None
        self.debug_port = 9222
        self.chrome_process = None
        self.logger = logging.getLogger(self.__class__.__name__)
        self.website_url = website_url
        self._pages = []  # 存储所有打开的页面
        self._page_listeners = []  # 存储页面事件监听器

    def set_website_url(self, website_url: str):
        if website_url and 'http' not in website_url:
            website_url = 'https://' + website_url
        self.website_url = website_url
        assert self.website_url, "News website cannot be None!"

    async def initialize(self) -> None:
        """初始化浏览器环境"""
        try:
            self._playwright = await async_playwright().start()

            if self.use_local_chrome and self.chrome_path and os.path.exists(self.chrome_path):
                self.logger.info("Using local Chrome browser")

                # Check if Chrome is already running with remote debugging
                import socket
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                chrome_running = s.connect_ex(('localhost', self.debug_port)) == 0
                s.close()

                if not chrome_running:
                    # Launch Chrome with remote debugging enabled
                    user_data_dir = os.path.expanduser("~/Library/Application Support/Google/Chrome")
                    self.chrome_process = subprocess.Popen([
                        self.chrome_path,
                        f'--remote-debugging-port={self.debug_port}',
                        '--no-first-run',
                        '--no-default-browser-check',
                        f'--user-data-dir={user_data_dir}'
                    ])
                    # Wait for Chrome to start
                    await asyncio.sleep(1.5)

                # Connect to the running Chrome instance
                self._browser = await self._playwright.chromium.connect_over_cdp(f'http://localhost:{self.debug_port}')

                # Get existing context or create a new one
                if len(self._browser.contexts) > 0:
                    self._context = self._browser.contexts[0]
                    # 获取所有已存在的页面
                    self._pages = self._context.pages
                    if len(self._pages) > 0:
                        self._page = self._pages[0]  # 使用第一个页面作为当前页面
                    else:
                        self._page = await self._context.new_page()
                        self._pages.append(self._page)
                else:
                    self._context = await self._browser.new_context()
                    self._page = await self._context.new_page()
                    self._pages = [self._page]

            else:
                # Use Playwright's bundled browser
                self._browser = await self._playwright.chromium.launch(
                    headless=False,
                    args=[
                        "--disable-blink-features=AutomationControlled",
                    ]
                )
                self._context = await self._browser.new_context()
                self._page = await self._context.new_page()
                self._pages = [self._page]

            # Common setup
            await self._page.set_viewport_size({"width": 1280, "height": 720})

            # Set default navigation timeout to avoid getting stuck
            self._page.set_default_navigation_timeout(30000)

            # 设置页面事件监听
            await self._setup_page_listeners()

            # Navigate to the website
            if self.website_url:
                await self.navigate(self.website_url)
                self.logger.info(f"Navigated to {self.website_url}")

        except Exception as e:
            self.logger.error(f"Failed to initialize browser: {e}")
            await self.cleanup()
            raise BrowserOperationError(f"Browser initialization failed: {str(e)}")

    async def _setup_page_listeners(self):
        """设置页面事件监听器"""
        if not self._context:
            return

        # 监听新页面打开事件
        self._context.on("page", self._on_new_page)
        
        # 为当前页面添加加载事件监听
        for page in self._pages:
            self._add_page_listeners(page)

    def _add_page_listeners(self, page):
        """为页面添加事件监听器"""
        # 监听页面导航事件
        page.on("load", lambda: asyncio.create_task(self._on_page_load(page)))
        
        # 可以添加更多事件监听器，如对话框、控制台消息等
        page.on("dialog", lambda dialog: asyncio.create_task(self._on_dialog(dialog)))

    async def _on_page_load(self, page):
        """页面加载完成时的回调"""
        try:
            # 如果加载的页面不在我们的列表中，添加它
            if page not in self._pages:
                self._pages.append(page)
                self._add_page_listeners(page)

            # 更新视口大小
            if page.is_closed():
                return

            await page.set_viewport_size({"width": 1280, "height": 720})
            self.logger.info(f"Page loaded: {await page.title() if not page.is_closed() else 'unknown'}")
        except Exception as e:
            self.logger.error(f"Error in page load handler: {e}")

    async def _on_dialog(self, dialog):
        """处理对话框的回调"""
        try:
            # 默认处理方式：接受对话框
            self.logger.info(f"Dialog appeared: {dialog.message}")
            await dialog.accept()
        except Exception as e:
            self.logger.error(f"Error handling dialog: {e}")

    async def _on_new_page(self, page):
        """新页面打开时的回调"""
        try:
            self.logger.info("New page opened")
            
            # 添加到页面列表
            if page not in self._pages:
                self._pages.append(page)
                
            # 为新页面添加事件监听器
            self._add_page_listeners(page)
            
            # 切换到新页面
            self._page = page
            
            # 等待页面加载完成
            try:
                await page.wait_for_load_state("domcontentloaded", timeout=5000)
                self.logger.info("New page DOM loaded")
            except TimeoutError:
                self.logger.warning("Timeout waiting for new page to load")
                
            # 设置视口大小
            if not page.is_closed():
                await page.set_viewport_size({"width": 1280, "height": 720})
                title = await page.title() if not page.is_closed() else "unknown"
                self.logger.info(f"Switched to new page: {title}")
        except Exception as e:
            self.logger.error(f"Error handling new page: {e}")

    async def get_all_pages(self) -> List[Page]:
        """获取所有打开的页面"""
        if self._context:
            # 刷新页面列表，删除已关闭的页面
            self._pages = [page for page in self._context.pages if not page.is_closed()]
        return self._pages

    async def switch_to_page(self, page_index: int) -> None:
        """切换到指定索引的页面"""
        pages = await self.get_all_pages()
        if 0 <= page_index < len(pages):
            self._page = pages[page_index]
            title = await self._page.title() if not self._page.is_closed() else "unknown"
            self.logger.info(f"Switched to page {page_index}: {title}")
        else:
            raise BrowserOperationError(f"Invalid page index: {page_index}. Total pages: {len(pages)}")

    async def switch_to_new_page(self) -> None:
        """切换到最新打开的页面"""
        pages = await self.get_all_pages()
        if len(pages) > 0:
            self._page = pages[-1]  # 最后一个页面通常是最新打开的
            title = await self._page.title() if not self._page.is_closed() else "unknown"
            self.logger.info(f"Switched to latest page: {title}")
        else:
            raise BrowserOperationError("No pages available")

    async def close_current_page(self) -> None:
        """关闭当前页面并切换到前一个页面"""
        if not self._page or self._page.is_closed():
            return
            
        pages = await self.get_all_pages()
        current_index = pages.index(self._page) if self._page in pages else -1
        
        if current_index == -1:
            return
        
        # 关闭当前页面
        await self._page.close()
        
        # 更新页面列表
        pages = await self.get_all_pages()
        
        # 如果还有页面，切换到前一个页面
        if pages:
            new_index = min(current_index, len(pages) - 1)
            self._page = pages[new_index]
            title = await self._page.title() if not self._page.is_closed() else "unknown"
            self.logger.info(f"Switched to page {new_index} after closing previous page: {title}")
        else:
            # 如果没有页面了，创建一个新页面
            self._page = await self._context.new_page()
            self._pages = [self._page]
            self.logger.info("Created new page after closing last page")
            
    async def _wait(self, t=None):
        """Wait for a specified time"""
        if t is None:
            t = self.WAIT_TIME
        await asyncio.sleep(t)

    async def navigate(self, url: str) -> None:
        """Navigate to a URL"""
        if not url:
            self.logger.warning("Empty URL provided to navigate")
            return
            
        try:
            self.logger.info(f"Navigating to: {url}")
            response = await self._page.goto(url, wait_until="domcontentloaded")
            
            # 尝试等待网络请求完成，但不让它阻塞太久
            try:
                await self._page.wait_for_load_state("networkidle", timeout=10000)
            except TimeoutError:
                self.logger.warning("Timeout waiting for network idle, continuing anyway")
                
            if not response:
                self.logger.warning(f"Navigation to {url} did not return a response.")
            elif response.status >= 400:
                self.logger.warning(f"Navigation to {url} returned status {response.status}")
            else:
                self.logger.info(f"Successfully navigated to {url}")
        except Exception as e:
            self.logger.error(f"Failed to navigate to {url}: {e}")
            raise BrowserOperationError(f"Navigation failed: {str(e)}")

    async def shutdown(self) -> None:
        """Alias for cleanup for compatibility"""
        await self.cleanup()

    async def execute(self, action: Action) -> None:
        """Execute action - compatibility with your original code"""
        # If page is not initialized, initialize it
        if not self._page:
            await self.initialize()

        # Validate the action
        action.validate()

        if action.action_type in ['call_user', 'finished', 'start']:
            return

        try:
            await self._process_action(action)
        except Exception as e:
            self.logger.error(f"Action {action.action_type} failed: {str(e)}")
            raise BrowserOperationError(f"Action failed: {action.action_type}") from e

    async def _process_action(self, action: Action) -> None:
        """操作指令路由"""
        handlers = {
            'click': self._handle_click,
            'left_double': self._handle_double_click,
            'right_single': self._handle_right_click,
            'drag': self._handle_drag,
            'hotkey': self._handle_hotkey,
            'type': self._handle_type,
            'scroll': self._handle_scroll,
            'switch_tab': self._handle_switch_tab,
        }
        try:
            handler = handlers[action.action_type]
        except KeyError:
            raise ValueError(f"Invalid action type: {action.action_type}. Valid types: {', '.join(handlers.keys())}")
        await handler(action)

    async def _handle_click(self, action: Action) -> None:
        """处理点击操作"""
        center = Action.calculate_center(action.start_box)
        await self._show_mouse_move(*center)
        
        # 保存点击前的页面数量
        before_pages = len(await self.get_all_pages())
        
        # 执行点击
        await self._page.mouse.click(*center)
        await self._wait(0.5)
        
        # 检查是否有新页面打开
        after_pages = len(await self.get_all_pages())
        if after_pages > before_pages:
            self.logger.info("New page detected after click, waiting for it to load")
            # 等待新页面加载
            await self._wait(1.0)
        
        # 等待页面加载状态
        try:
            await self._page.wait_for_load_state("domcontentloaded", timeout=5000)
        except TimeoutError:
            self.logger.warning("Timeout waiting for page to load after click, continuing anyway")

    async def _handle_double_click(self, action: Action) -> None:
        """处理双击操作"""
        center = Action.calculate_center(action.start_box)
        await self._show_mouse_move(*center)
        await self._page.mouse.click(*center, click_count=2)
        await self._wait()
        
        # 等待页面加载状态
        try:
            await self._page.wait_for_load_state("domcontentloaded", timeout=5000)
        except TimeoutError:
            pass

    async def _handle_right_click(self, action: Action) -> None:
        """处理右键操作"""
        center = Action.calculate_center(action.start_box)
        await self._show_mouse_move(*center)
        await self._page.mouse.click(*center, button='right')
        await self._wait()

    async def _handle_drag(self, action: Action) -> None:
        """处理拖拽操作"""
        start = Action.calculate_center(action.start_box)
        end = Action.calculate_center(action.end_box)
        await self._page.mouse.move(*start)
        await self._page.mouse.down()
        await self._page.mouse.move(*end)
        await self._page.mouse.up()
        await self._wait()

    async def _handle_hotkey(self, action: Action) -> None:
        """处理快捷键操作"""
        await self._page.keyboard.press(action.key)
        await self._wait()
        
        # 部分快捷键可能触发导航，等待页面加载
        try:
            await self._page.wait_for_load_state("domcontentloaded", timeout=5000)
        except TimeoutError:
            pass

    async def _handle_type(self, action: Action) -> None:
        """处理输入操作"""
        content, submit = action.parse_content()
        await self._page.keyboard.type(content)
        if submit:
            await self._page.keyboard.press('Enter')
            # 提交表单可能触发导航，等待页面加载
            try:
                await self._page.wait_for_load_state("domcontentloaded", timeout=5000)
            except TimeoutError:
                pass
        await self._wait()

    async def _handle_scroll(self, action: Action) -> None:
        """处理滚动操作"""
        center = Action.calculate_center(action.start_box)
        await self._page.mouse.move(*center)
        await self._page.mouse.wheel(*action.deltas)
        await self._wait()
        
    async def _handle_switch_tab(self, action: Action) -> None:
        """处理标签页切换"""
        if hasattr(action, 'tab_index') and action.tab_index is not None:
            tab_index = action.tab_index
            await self.switch_to_page(tab_index)
        else:
            # 默认切换到最新标签页
            await self.switch_to_new_page()
        await self._wait(0.5)

    async def _show_mouse_move(self, x: int, y: int) -> None:
        """
        美化鼠标移动动画，鼠标从视口边缘移入目标位置
        :param x: 元素中心点横坐标
        :param y: 元素中心点纵坐标
        :return: None
        """
        try:
            # 获取当前视口尺寸
            viewport_size = await self._page.evaluate("({ width: window.innerWidth, height: window.innerHeight })")
            screen_width = viewport_size['width']
            screen_height = viewport_size['height']

            # 计算初始移动方向（基于目标点与视口中心的相对位置）
            dx = -200 if x < screen_width / 2 else 200  # 横向偏移量
            dy = -200 if y < screen_height / 2 else 200  # 纵向偏移量
            rotate = 30 if dx > 0 else -30  # 根据方向设置旋转角度

            # 读取SVG文件
            try:
                with open(get_absolute_path("/icon/mouse.svg"), "rb") as f:
                    svg_data = f.read()
                svg_base64 = base64.b64encode(svg_data).decode("utf-8")
                svg_url = f"data:image/svg+xml;base64,{svg_base64}"
            except Exception as e:
                self.logger.error(f"Failed to load mouse SVG: {str(e)}")
                # 使用备用图像URL作为fallback
                svg_url = "data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHZpZXdCb3g9IjAgMCAzMCAzMCI+PHBhdGggZD0iTTEyIDI0LjQyMkwyLjUgMTQuOTIyVjMuNUgyNS41VjI1LjVIMTJWMjQuNDIyWiIgc3Ryb2tlPSJibGFjayIgc3Ryb2tlLXdpZHRoPSIyIiBmaWxsPSJ3aGl0ZSIvPjwvc3ZnPg=="

            # JavaScript代码中的字符串需要使用单引号，并使用f-string将Python变量正确注入
            js_code = f"""
                () => {{
                    // 移除任何已存在的鼠标动画元素
                    const existingMouse = document.getElementById('animated-mouse');
                    if (existingMouse) existingMouse.remove();

                    // 创建新的鼠标元素
                    const moveImg = document.createElement('img');
                    moveImg.id = 'animated-mouse';
                    moveImg.src = '{svg_url}';

                    // 设置元素基础样式
                    moveImg.style.position = 'fixed'; // 使用fixed而不是absolute，以避免滚动问题
                    moveImg.style.width = '30px';
                    moveImg.style.height = '30px';
                    moveImg.style.zIndex = '9999';
                    moveImg.style.pointerEvents = 'none';

                    // 设置初始位置（基于目标位置和偏移量计算）
                    const startX = {x} + {dx};
                    const startY = {y} + {dy};
                    moveImg.style.left = startX - 15 + 'px';
                    moveImg.style.top = startY - 15 + 'px';
                    moveImg.style.transform = 'rotate({rotate}deg) scale(0.3)';

                    document.body.appendChild(moveImg);

                    // 确保DOM更新后再开始动画
                    setTimeout(() => {{
                        moveImg.style.transition = 'all 0.6s cubic-bezier(0.34, 1.56, 0.64, 1)';
                        moveImg.style.left = '{x - 15}px';
                        moveImg.style.top = '{y - 15}px';
                        moveImg.style.transform = 'rotate(0deg) scale(1)';
                    }}, 10);

                    // 动画结束后移除元素
                    setTimeout(() => {{
                        moveImg.remove();
                    }}, 1200);
                }}
            """

            # 执行JavaScript代码
            await self._page.evaluate(js_code)

            # 等待动画完成（0.6秒动画时间 + 0.2秒缓冲）
            await self._wait(0.8)

        except Exception as e:
            self.logger.error(f"Failed to show mouse move animation to ({x}, {y}): {str(e)}")

    async def click(self, coordinates: Coordinate) -> None:
        """Click at specific coordinates"""
        try:
            await self._page.mouse.click(coordinates.x, coordinates.y)
            await asyncio.sleep(0.5)
        except Exception as e:
            self.logger.error(f"Failed to click at coordinates {coordinates}: {e}")
            raise BrowserOperationError(f"Click operation failed: {str(e)}")

    async def click_element(self, selector: str) -> None:
        """Click an element by selector"""
        try:
            await self._page.click(selector)
            await asyncio.sleep(0.5)
        except Exception as e:
            self.logger.error(f"Failed to click element with selector {selector}: {e}")
            raise BrowserOperationError(f"Click element operation failed: {str(e)}")

    async def type_text(self, text: str) -> None:
        """Type text at current focus"""
        try:
            await self._page.keyboard.type(text)
        except Exception as e:
            self.logger.error(f"Failed to type text: {e}")
            raise BrowserOperationError(f"Type operation failed: {str(e)}")

    async def press_key(self, key: str) -> None:
        """Press a specific key"""
        try:
            await self._page.keyboard.press(key)
        except Exception as e:
            self.logger.error(f"Failed to press key {key}: {e}")
            raise BrowserOperationError(f"Key press operation failed: {str(e)}")

    async def get_current_page_info(self) -> Dict[str, Any]:
        """获取当前页面的信息"""
        if not self._page or self._page.is_closed():
            return {"error": "No active page"}
            
        try:
            pages = await self.get_all_pages()
            return {
                "url": self._page.url,
                "title": await self._page.title(),
                "page_index": pages.index(self._page) if self._page in pages else -1,
                "total_pages": len(pages)
            }
        except Exception as e:
            self.logger.error(f"Failed to get page info: {e}")
            return {"error": str(e)}

    async def _capture_screenshot(self, is_full_page=False) -> bytes:
        """页面截图捕获"""
        try:
            screenshot = await self._page.screenshot(full_page=is_full_page)
            self.logger.debug("Screenshot captured successfully")
            return screenshot
        except Exception as e:
            self.logger.error(f"Screenshot failed: {str(e)}")
            raise

    async def _capture_html(self) -> str:
        """
        捕获页面的完整 HTML 内容
        """
        try:
            html = await self._page.content()
            self.logger.debug("HTML captured successfully")
            return html
        except Exception as e:
            self.logger.error(f"HTML capture failed: {str(e)}")
            raise

    async def _capture_js(self) -> str:
        """
        捕获页面中所有 script 标签内的 JavaScript 代码
        """
        try:
            js = await self._page.evaluate(
                "() => { return Array.from(document.scripts).map(script => script.textContent).join('\\n'); }"
            )
            self.logger.debug("JS captured successfully")
            return js
        except Exception as e:
            self.logger.error(f"JS capture failed: {str(e)}")
            raise

    async def _capture_text(self) -> str:
        """
        捕获页面上所有可见的文本内容
        """
        try:
            text = await self._page.inner_text("body")
            self.logger.debug("Text captured successfully")
            return text
        except Exception as e:
            self.logger.error(f"Text capture failed: {str(e)}")
            raise

    async def save_page_info(self) -> dict:
        screenshot = await self._capture_screenshot()
        html = await self._capture_html()
        js = await self._capture_js()
        text = await self._capture_text()
        img_base64 = base64.b64encode(screenshot).decode("utf-8")
        
        # 获取页面元信息
        page_info = await self.get_current_page_info()
        
        return {
            'html': html, 
            'js': js, 
            'text': text, 
            'img_base64': img_base64, 
            'screenshot': screenshot,
            'page_info': page_info
        }

    async def execute_javascript(self, script: str):
        """Execute JavaScript in the browser context"""
        try:
            result = await self._page.evaluate(script)
            return result
        except Exception as e:
            self.logger.error(f"Failed to evaluate JavaScript: {e}")
            raise BrowserOperationError(f"JavaScript evaluation failed: {str(e)}")

    async def cleanup(self) -> None:
        """Clean up resources"""
        try:
            # 清理页面列表
            self._pages = []
            
            if self._page:
                try:
                    if not self._page.is_closed():
                        await self._page.close()
                except:
                    pass
                self._page = None

            if self._context:
                try:
                    await self._context.close()
                except:
                    pass
                self._context = None

            if self._browser:
                try:
                    await self._browser.close()
                except:
                    pass
                self._browser = None

            if self._playwright:
                try:
                    await self._playwright.stop()
                except:
                    pass
                self._playwright = None

            # Only terminate the process if we started it
            if self.chrome_process and self.use_local_chrome:
                try:
                    self.chrome_process.terminate()
                    self.chrome_process = None
                except Exception as e:
                    self.logger.warning(f"Failed to terminate Chrome process: {e}")

            self.logger.info("Browser controller cleaned up")
        except Exception as e:
            self.logger.error(f"Error during cleanup: {e}")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)


    async def main():
        agent = BrowserController('https://www.baidu.com/', use_local_chrome=True)
        await agent.initialize()

        screenshot_count = 1  # 初始化截图计数器

        while True:
            action_type = input(
                "请输入操作类型（click, left_double, right_single, drag, hotkey, type, scroll, screenshot, tabs, exit）：")
            
            if action_type == 'exit':
                break
                
            if action_type == 'tabs':
                # 显示和管理标签页
                pages = await agent.get_all_pages()
                print(f"当前共有 {len(pages)} 个标签页:")
                for i, page in enumerate(pages):
                    title = await page.title() if not page.is_closed() else "unknown"
                    url = page.url
                    current = "* " if page == agent._page else "  "
                    print(f"{current}[{i}] {title} - {url}")
                
                tab_cmd = input("请输入标签页操作 (switch <index>/new/close/refresh): ")
                if tab_cmd.startswith("switch "):
                    try:
                        idx = int(tab_cmd.split(" ")[1])
                        await agent.switch_to_page(idx)
                        print(f"已切换到标签页 {idx}")
                    except Exception as e:
                        print(f"切换标签页失败: {e}")
                elif tab_cmd == "new":
                    try:
                        new_page = await agent._context.new_page()
                        agent._pages.append(new_page)
                        agent._page = new_page
                        await new_page.goto("https://www.baidu.com")
                        print("已创建新标签页")
                    except Exception as e:
                        print(f"创建新标签页失败: {e}")
                elif tab_cmd == "close":
                    try:
                        await agent.close_current_page()
                        print("已关闭当前标签页")
                    except Exception as e:
                        print(f"关闭标签页失败: {e}")
                elif tab_cmd == "refresh":
                    try:
                        await agent._page.reload()
                        print("已刷新当前页面")
                    except Exception as e:
                        print(f"刷新页面失败: {e}")
                continue
                
            if action_type == 'screenshot':
                screenshot_path = f"screenshot_{screenshot_count}.png"  # 自动生成截图文件名
                try:
                    screenshot = await agent._capture_screenshot()
                    with open(screenshot_path, "wb") as f:
                        f.write(screenshot)
                    print(f"截图已保存到 {screenshot_path}")
                    screenshot_count += 1  # 计数器加一
                except Exception as e:
                    print(f"截图失败：{e}")
                continue

            # 使用 Action 类创建操作对象
            if action_type in ['click', 'left_double', 'right_single', 'scroll']:
                start_box_str = input("请输入 start_box (例如：100,200,300,400)：")
                start_box = tuple(map(int, start_box_str.split(',')))
                if action_type == 'scroll':
                    deltas_str = input("请输入 deltas (例如：0,100)：")
                    deltas = tuple(map(int, deltas_str.split(',')))
                    action = Action(action_type, params={'start_box': start_box, 'deltas': deltas})
                else:
                    action = Action(action_type, params={'start_box': start_box})
            elif action_type == 'drag':
                start_box_str = input("请输入 start_box (例如：100,200,300,400)：")
                start_box = tuple(map(int, start_box_str.split(',')))
                end_box_str = input("请输入 end_box (例如：500,600,700,800)：")
                end_box = tuple(map(int, end_box_str.split(',')))
                action = Action(action_type, params={'start_box': start_box, 'end_box': end_box})
            elif action_type == 'hotkey':
                key = input("请输入按键名称 (例如：Enter, Escape, a)：")
                action = Action(action_type, params={'key': key})
            elif action_type == 'type':
                content = input("请输入要输入的内容：")
                submit_str = input("是否提交？(yes/no)：")
                submit = submit_str.lower() == 'yes'
                if submit:
                    content += '\n'
                action = Action(action_type, params={'content': content})
            elif action_type == 'switch_tab':
                tab_idx_str = input("请输入要切换的标签页索引 (默认切换到最新标签页): ")
                if tab_idx_str:
                    try:
                        tab_idx = int(tab_idx_str)
                        action = Action(action_type, params={'tab_index': tab_idx})
                    except ValueError:
                        action = Action(action_type)
                else:
                    action = Action(action_type)
            else:
                print("无效的操作类型！")
                continue

            try:
                await agent.execute(action)
                print("操作执行成功！")
                # 每次操作后立即保存截图，自动编号
                screenshot_path = f"screenshot_{screenshot_count}.png"
                try:
                    screenshot = await agent._capture_screenshot()
                    with open(screenshot_path, "wb") as f:
                        f.write(screenshot)
                    print(f"截图已保存到 {screenshot_path}")
                    screenshot_count += 1
                except Exception as e:
                    print(f"截图失败：{e}")
            except BrowserOperationError as e:
                print(f"操作执行失败：{e}")
            except Exception as e:
                print(f"发生未知错误：{e}")

        await agent.shutdown()


    asyncio.run(main())
