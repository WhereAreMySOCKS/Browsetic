import base64
import time
import logging
import subprocess
import platform
import os
from pyexpat.errors import messages
from typing import Optional, Dict, Any

from playwright.async_api import async_playwright, Browser, BrowserContext, Page
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

    def set_website_url(self, website_url: str):
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
                    self._page = await self._context.new_page()
                else:
                    self._context = await self._browser.new_context()
                    self._page = await self._context.new_page()

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

            # Common setup
            await self._page.set_viewport_size({"width": 1280, "height": 720})

            # Set default navigation timeout to avoid getting stuck
            self._page.set_default_navigation_timeout(30000)

            # Navigate to the website
            await self.navigate(self.website_url)
            self.logger.info(f"Navigated to {self.website_url}")

        except Exception as e:
            self.logger.error(f"Failed to initialize browser: {e}")
            await self.cleanup()
            raise BrowserOperationError(f"Browser initialization failed: {str(e)}")

    async def _wait(self, t=None):
        """Wait for a specified time"""
        if t is None:
            t = self.WAIT_TIME
        await asyncio.sleep(t)

    async def navigate(self, url: str) -> None:
        """Navigate to a URL"""
        try:
            response = await self._page.goto(url, wait_until="networkidle")
            if not response:
                self.logger.warning(f"Navigation to {url} did not return a response.")
            elif response.status >= 400:
                self.logger.warning(f"Navigation to {url} returned status {response.status}")
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
        await self._page.mouse.click(*center)
        await self._wait()

    async def _handle_double_click(self, action: Action) -> None:
        """处理双击操作"""
        center = Action.calculate_center(action.start_box)
        await self._show_mouse_move(*center)
        await self._page.mouse.click(*center, click_count=2)
        await self._wait()

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

    async def _handle_type(self, action: Action) -> None:
        """处理输入操作"""
        content, submit = action.parse_content()
        await self._page.keyboard.type(content)
        if submit:
            await self._page.keyboard.press('Enter')
        await self._wait()

    async def _handle_scroll(self, action: Action) -> None:
        """处理滚动操作"""
        center = Action.calculate_center(action.start_box)
        await self._page.mouse.move(*center)
        await self._page.mouse.wheel(*action.deltas)
        await self._wait()

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
        return {'html': html, 'js': js, 'text': text, 'img_base64': img_base64, 'screenshot': screenshot}

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
            if self._page:
                await self._page.close()
                self._page = None

            if self._context:
                await self._context.close()
                self._context = None

            if self._browser:
                await self._browser.close()
                self._browser = None

            if self._playwright:
                await self._playwright.stop()
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
                "请输入操作类型（click, left_double, right_single, drag, hotkey, type, scroll, screenshot, exit）：")
            if action_type == 'exit':
                break
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
