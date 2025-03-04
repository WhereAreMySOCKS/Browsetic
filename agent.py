import requests
import logging
from functools import wraps, partial
from playwright.async_api import async_playwright
from typing import Callable, Coroutine, Any
import asyncio
import aiohttp

from utils.action import Action
from utils.data import Data
from utils.error import BrowserOperationError, AgentError


class Agent:
    class DOMLoaded:
        """DOM加载等待装饰器 (可配置超时时间)"""

        def __init__(self, timeout: int = 30000):
            self.timeout = timeout

        def __call__(self, func: Callable[..., Coroutine]) -> Callable:
            @wraps(func)
            async def wrapper(instance: 'Agent', *args, **kwargs) -> Any:
                result = await func(instance, *args, **kwargs)
                await instance.wait_for_dom(timeout=self.timeout)
                return result

            return wrapper

    DEFAULT_TIMEOUT = 30000  # 统一管理超时常量

    def __init__(self, server_host: str):
        if not server_host:
            raise ValueError("Server host must be provided")
        self.server_host = server_host
        self._state = {'finished': False, 'user_requested': False}
        self._browser = None
        self._page = None
        self._playwright = None
        self.logger = logging.getLogger(self.__class__.__name__)

    @property
    def is_finished(self) -> bool:
        """任务是否完成的状态属性"""
        return self._state['finished']

    @property
    def needs_user(self) -> bool:
        """是否需要用户协助的状态属性"""
        return self._state['user_requested']

    async def initialize(self) -> None:
        """初始化浏览器环境"""
        health_url = f"{self.server_host}/health"
        try:
            response = requests.get(health_url, timeout=5)
            response.raise_for_status()
            self.logger.info("Server health check passed")

            self._playwright = await async_playwright().start()
            self._browser = await self._playwright.chromium.launch(
                headless=False,
                args=["--disable-blink-features=AutomationControlled"]
            )
            self._page = await self._browser.new_page()
            await self._page.goto(
                'https://weibo.com/newlogin?tabtype=mine&gid=&openLoginLayer=0&url=https%3A%2F%2Fwww.weibo.com%2F',
                wait_until='networkidle')
            self.logger.info("Browser initialized successfully")
        except Exception as e:
            self.logger.error(f"Browser initialization failed: {str(e)}")
            raise BrowserOperationError("Failed to initialize browser") from e
        except requests.RequestException as e:
            self.logger.error(f"Server health check failed: {str(e)}")

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
        3. 根据 action.type 路由到具体的处理函数，并执行操作。
        4. 最后截图，方便后续调试或日志记录。
        """
        # 利用 Action 类内置的验证逻辑
        action.validate()

        if not self._page:
            await self.initialize()

        try:
            await self._process_action(action)
            await self._capture_screenshot()
        except Exception as e:
            self.logger.error(f"Action {action.type} failed: {str(e)}")
            raise BrowserOperationError(f"Action failed: {action.type}") from e

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
            'wait': self._handle_wait,
            'finished': partial(self._set_state, flag='finished'),
            'call_user': partial(self._set_state, flag='user_requested')
        }

        handler = handlers.get(action.type)
        if not handler:
            raise ValueError(f"Invalid action type: {action.type}. Valid types: {', '.join(handlers.keys())}")
        await handler(action)

    def _set_state(self, flag: str, _: Any = None) -> None:
        """状态设置通用方法"""
        self._state[flag] = True

    @DOMLoaded(timeout=DEFAULT_TIMEOUT)
    async def _handle_click(self, action: Action) -> None:
        """处理点击操作"""
        center = Action.calculate_center(action.start_box)
        await self._page.mouse.click(*center)

    @DOMLoaded()
    async def _handle_double_click(self, action: Action) -> None:
        """处理双击操作"""
        center = Action.calculate_center(action.start_box)
        await self._page.mouse.click(*center, clickCount=2)

    @DOMLoaded()
    async def _handle_right_click(self, action: Action) -> None:
        """处理右键操作"""
        center = Action.calculate_center(action.start_box)
        await self._page.mouse.click(*center, button='right')

    @DOMLoaded()
    async def _handle_drag(self, action: Action) -> None:
        """处理拖拽操作"""
        start = Action.calculate_center(action.start_box)
        end = Action.calculate_center(action.end_box)
        await self._page.mouse.move(*start)
        await self._page.mouse.down()
        await self._page.mouse.move(*end)
        await self._page.mouse.up()

    @DOMLoaded()
    async def _handle_hotkey(self, action: Action) -> None:
        """处理快捷键操作"""
        await self._page.keyboard.press(action.key)

    @DOMLoaded()
    async def _handle_type(self, action: Action) -> None:
        """处理输入操作"""
        content, submit = action.parse_content()
        await self._page.keyboard.type(content)
        if submit:
            await self._page.keyboard.press('Enter')

    @DOMLoaded()
    async def _handle_scroll(self, action: Action) -> None:
        """处理滚动操作"""
        center = Action.calculate_center(action.start_box)
        await self._page.mouse.move(*center)
        await self._page.mouse.wheel(*action.deltas)

    async def _handle_wait(self, _: Action) -> None:
        """等待页面稳定"""
        await self.wait_for_dom(timeout=5000)

    async def wait_for_dom(self, timeout: int = DEFAULT_TIMEOUT) -> None:
        """等待DOM稳定状态"""
        try:
            await self._page.wait_for_load_state('domcontentloaded', timeout=timeout)
        except Exception as e:
            self.logger.warning(f"DOM wait timeout: {str(e)}")
            raise

    async def _capture_screenshot(self, is_full_page=False) -> None:
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
                    self.server_host + '/',
                    data=form_data
            ) as response:
                # 读取响应内容（根据实际情况调整）
                response_text = await response.text()
                return {
                    "status": response.status,
                    "content": response_text
                }


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)


    async def main():
        agent = Agent(server_host="http://10.0.87.17:50002/")
        try:
            await agent.initialize()
            # 捕获页面文本
            resp = await agent._upload_data()
            print(resp)
        except AgentError as e:
            logging.error(f"Operation failed: {str(e)}")
        finally:
            await agent.shutdown()


    asyncio.run(main())
