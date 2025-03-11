import base64
import time
import logging
from playwright.async_api import async_playwright
import asyncio
import aiohttp
from utils.action import Action
from utils.data import Data
from utils.error import BrowserOperationError, AgentError
from utils.get_absolute_path import get_absolute_path


class BrowserController:
    def __init__(self):
        self.WAIT_TIME = 3  # 统一管理超时常量
        self.is_online = True
        self._state = {'finished': False, 'user_requested': False}
        self._browser = None
        self._page = None
        self._playwright = None
        self.logger = logging.getLogger(self.__class__.__name__)

    async def initialize(self) -> None:
        """初始化浏览器环境"""
        # if not self.is_online:  # 检查服务器连接是否正常
        #     health_url = f"{self.server_host}/health"
        #     try:
        #         response = requests.get(health_url, timeout=5)
        #         response.raise_for_status()
        #         self.logger.info("Server health check passed")
        #     except requests.RequestException as e:
        #         self.logger.error(f"Server health check failed: {str(e)}")

        try:  # 启动浏览器，打开微博
            self._playwright = await async_playwright().start()
            self._browser = await self._playwright.chromium.launch(
                headless=False,
                args=[
                    "--disable-blink-features=AutomationControlled",
                ]
            )
            self._page = await self._browser.new_page()
            await self._page.set_viewport_size({"width": 1920, "height": 1080})
            await self._page.goto(
                'https://www.baidu.com/',
                wait_until='networkidle')

            self.logger.info("Browser initialized successfully")
        except Exception as e:
            self.logger.error(f"Browser initialization failed: {str(e)}")
            raise BrowserOperationError("Failed to initialize browser") from e

    async def _wait(self, t=None):
        if t is None:
            t = self.WAIT_TIME
        time.sleep(t)

    async def shutdown(self) -> None:
        """安全关闭浏览器资源"""
        try:
            if self._browser:
                await self._browser.close()
            if self._playwright:
                await self._playwright.stop()
            self.logger.info("Browser resources cleaned up")
        except Exception as e:
            self.logger.error(f"Error during shutdown: {str(e)}")
            raise BrowserOperationError("Shutdown failed") from e
        finally:
            self._page = None

    async def execute(self, action: Action) -> None:
        """
        执行操作指令的入口方法

        1. 调用 action.validate() 完成对必填字段的校验。
        2. 如尚未初始化页面，则调用 initialize()。
        3. 根据 action.action_type 路由到具体的处理函数，并执行操作。
        """
        # 利用 Action 类内置的验证逻辑
        action.validate()

        if not self._page:
            await self.initialize()
        try:
            await self._process_action(action)
        except Exception as e:
            self.logger.error(f"Action {action.action_type} failed: {str(e)}")
            raise BrowserOperationError(f"Action failed: {action.action_type}") from e

    async def save_page_info(self):
        screenshot = await self._capture_screenshot()
        html = await self._capture_html()
        js = await self._capture_js()
        text = await self._capture_text()
        img_base64 = base64.b64encode(screenshot).decode("utf-8")
        return {'html': html, 'js': js, 'text': text, 'img_base64': img_base64}

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
        await self._show_click_complete(*center)
        await self._wait()

    async def _handle_double_click(self, action: Action) -> None:
        """处理双击操作"""
        center = Action.calculate_center(action.start_box)
        await self._show_mouse_move(*center)
        await self._page.mouse.click(*center, clickCount=2)
        await self._show_click_complete(*center)
        await self._wait()

    async def _handle_right_click(self, action: Action) -> None:
        """处理右键操作"""
        center = Action.calculate_center(action.start_box)
        await self._show_mouse_move(*center)
        await self._page.mouse.click(*center, button='right')
        await self._show_click_complete(*center)
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

    async def _upload_data(self):
        """ 已废弃 """

        text = await self._capture_text()
        html = await self._capture_html()
        js = await self._capture_js()
        screenshot = await self._capture_screenshot()
        data = Data(text, html, js, screenshot)

        async with aiohttp.ClientSession() as session:
            # 构造 multipart 表单数据
            form_data = aiohttp.FormData()

            # 添加元数据文件
            metadata = data.to_files()['metadata']
            form_data.add_field(
                name='metadata',
                value=metadata[1],
                filename=metadata[0],
                content_type=metadata[2]
            )

            # 添加截图文件（如果存在）
            if data.screenshot:
                screenshot_info = data.to_files()['screenshot']
                form_data.add_field(
                    name='screenshot',
                    value=screenshot_info[1],
                    filename=screenshot_info[0],
                    content_type=screenshot_info[2]
                )

            # 发送异步请求
            async with session.post(
                    self.server_host + '/upload',
                    data=form_data
            ) as response:
                # 读取响应内容（根据实际情况调整）
                response_text = await response.text()
                return {
                    "status": response.status,
                    "content": response_text
                }

    async def _show_mouse_move(self, x: int, y: int) -> None:
        """
        在点击前显示鼠标移动动画，使用 /icon/mouse.svg 作为图标。
        此处创建一个 <img> 元素，初始位置设置在页面左上角，
        然后利用 CSS transition 平滑移动到目标位置。
        """
        with open(get_absolute_path("/icon/mouse.svg"), "rb") as f:
            svg_data = f.read()
        svg_base64 = base64.b64encode(svg_data).decode("utf-8")
        svg_url = f"data:image/svg+xml;base64,{svg_base64}"
        try:
            await self._page.evaluate(f"""
                // 创建鼠标移动动画图标（SVG 图片）
                const moveImg = document.createElement('img');
                moveImg.src = '{svg_url}';  // 使用SVG图标
                moveImg.style.position = 'absolute';
                moveImg.style.left = '0px';
                moveImg.style.top = '0px';
                moveImg.style.width = '20px';
                moveImg.style.height = '20px';
                moveImg.style.zIndex = 9999;
                // 添加平滑移动动画
                moveImg.style.transition = 'left 0.5s linear, top 0.5s linear';
                document.body.appendChild(moveImg);

                // 利用 requestAnimationFrame 保证动画启动
                requestAnimationFrame(() => {{
                    // 调整位置使图标中心对齐目标坐标（20px 宽高的一半为10px）
                    moveImg.style.left = '{x - 10}px';
                    moveImg.style.top = '{y - 10}px';
                }});

                // 动画结束后删除图标（稍长时间以确保动画完成）
                setTimeout(() => moveImg.remove(), 900);
            """)
            await self._wait(1)
        except Exception as e:
            self.logger.error(f"Failed to show mouse move animation to ({x}, {y}): {str(e)}")

    async def _show_click_complete(self, x: int, y: int) -> None:
        """
        在点击后显示点击完成动画，使用 /icon/mouse.svg 作为图标。
        这里创建一个较大的图标，通过 CSS keyframes 实现淡出放大效果，
        以视觉上提示点击事件的完成。
        """
        with open(get_absolute_path("/icon/mouse.svg"), "rb") as f:
            svg_data = f.read()
        svg_base64 = base64.b64encode(svg_data).decode("utf-8")
        svg_url = f"data:image/svg+xml;base64,{svg_base64}"
        try:
            await self._page.evaluate(f"""
                // 创建点击完成动画图标（SVG 图片）
                const clickImg = document.createElement('img');
                clickImg.src = '{svg_url}';
                clickImg.style.position = 'absolute';
                // 调整位置使图标中心对齐目标位置（120px 宽高的一半为60px）
                clickImg.style.left = '{x - 60}px';
                clickImg.style.top = '{y - 60}px';
                clickImg.style.width = '120px';
                clickImg.style.height = '120px';
                clickImg.style.zIndex = 9999;
                clickImg.style.pointerEvents = 'none';
                // 应用淡出放大动画
                clickImg.style.animation = 'fadeOut 1s forwards';

                // 动态注入动画关键帧（避免重复注入时可优化判断）
                const style = document.createElement('style');
                style.textContent = `
                    @keyframes fadeOut {{
                        0% {{ opacity: 1; transform: scale(1); }}
                        100% {{ opacity: 0; transform: scale(2); }}
                    }}
                `;
                document.head.appendChild(style);
                document.body.appendChild(clickImg);

                // 动画结束后自动删除图标
                setTimeout(() => clickImg.remove(), 2000);
            """)
        except Exception as e:
            self.logger.error(f"Failed to show click complete animation at ({x}, {y}): {str(e)}")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)


    async def main():
        agent = BrowserController()
        action1 = Action("type", content="Hello, World!")
        action2 = Action("click", start_box=(0, 0, 1920, 1080))

        try:
            await agent.initialize()
            # 捕获页面
            x = await agent.save_page_info()
            await agent.execute(action1)
            await agent.execute(action2)

        except AgentError as e:
            logging.error(f"Operation failed: {str(e)}")
        finally:
            await agent.shutdown()


    asyncio.run(main())
