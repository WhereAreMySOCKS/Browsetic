import base64
import time
import logging
import asyncio
from typing import Optional, Tuple, Dict, Any

from playwright.async_api import async_playwright, Page, Browser, Playwright
from action import Action
from utils.error import BrowserOperationError
from utils.get_absolute_path import get_absolute_path


class BrowserController:
    def __init__(self, website_url: str = None):
        # Config: Use local browser and existing user profiles to skip login
        self.WAIT_TIME = 2  # Unified timeout constant
        self.is_online = True
        self._state = {'finished': False, 'user_requested': False}
        self._browser: Optional[Browser] = None
        self._page: Optional[Page] = None
        self._playwright: Optional[Playwright] = None
        self.logger = logging.getLogger(self.__class__.__name__)
        self.website_url = None

    def set_website_url(self, website_url):
        self.website_url = website_url

    async def initialize(self) -> None:
        """Initialize browser environment"""
        try:  # Start browser and navigate to the website
            self._playwright = await async_playwright().start()
            self._browser = await self._playwright.chromium.launch(
                headless=False,
                args=[
                    "--disable-blink-features=AutomationControlled",
                ]
            )
            self._page = await self._browser.new_page()
            await self._page.set_viewport_size({"width": 1280, "height": 720})
            await self._page.goto(
                self.website_url,
                wait_until='networkidle')

            self.logger.info("Browser initialized successfully")
        except Exception as e:
            self.logger.error(f"Browser initialization failed: {str(e)}")
            raise BrowserOperationError("Failed to initialize browser") from e

    async def _wait(self, t=None):
        if t is None:
            t = self.WAIT_TIME
        await asyncio.sleep(t)  # Using asyncio.sleep instead of time.sleep

    async def shutdown(self) -> None:
        """Safely close browser resources"""
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
        Entry method for executing operation commands

        1. Call action.validate() to validate required fields.
        2. If the page is not initialized, call initialize().
        3. Route to the specific handler function based on action.action_type and execute the operation.
        """
        # Use built-in validation logic in Action class
        action.validate()
        if action.action_type in ['call_user', 'finished', 'start']:
            return

        if not self._page:
            await self.initialize()
        try:
            await self._process_action(action)
        except Exception as e:
            self.logger.error(f"Action {action.action_type} failed: {str(e)}")
            raise BrowserOperationError(f"Action failed: {action.action_type}") from e

    async def save_page_info(self) -> Dict[str, Any]:
        """Capture and return various page information"""
        screenshot = await self._capture_screenshot()
        html = await self._capture_html()
        js = await self._capture_js()
        text = await self._capture_text()
        img_base64 = base64.b64encode(screenshot).decode("utf-8")
        return {'html': html, 'js': js, 'text': text, 'img_base64': img_base64, 'screenshot': screenshot}

    async def _process_action(self, action: Action) -> None:
        """Route operation commands to specific handlers"""
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
        """Handle click operation"""
        center = Action.calculate_center(action.start_box)
        await self._show_mouse_move(*center)
        await self._page.mouse.click(*center)
        await self._wait()

    async def _handle_double_click(self, action: Action) -> None:
        """Handle double click operation"""
        center = Action.calculate_center(action.start_box)
        await self._show_mouse_move(*center)
        await self._page.mouse.click(*center, clickCount=2)
        await self._wait()

    async def _handle_right_click(self, action: Action) -> None:
        """Handle right click operation"""
        center = Action.calculate_center(action.start_box)
        await self._show_mouse_move(*center)
        await self._page.mouse.click(*center, button='right')
        await self._wait()

    async def _handle_drag(self, action: Action) -> None:
        """Handle drag operation"""
        start = Action.calculate_center(action.start_box)
        end = Action.calculate_center(action.end_box)
        await self._page.mouse.move(*start)
        await self._page.mouse.down()
        await self._page.mouse.move(*end)
        await self._page.mouse.up()
        await self._wait()

    async def _handle_hotkey(self, action: Action) -> None:
        """Handle hotkey operation"""
        await self._page.keyboard.press(action.key)
        await self._wait()

    async def _handle_type(self, action: Action) -> None:
        """Handle input operation"""
        content, submit = action.parse_content()
        await self._page.keyboard.type(content)
        if submit:
            await self._page.keyboard.press('Enter')
        await self._wait()

    async def _handle_scroll(self, action: Action) -> None:
        """Handle scroll operation"""
        center = Action.calculate_center(action.start_box)
        await self._page.mouse.move(*center)
        await self._page.mouse.wheel(*action.deltas)
        await self._wait()

    async def _capture_screenshot(self, is_full_page=False) -> bytes:
        """Capture page screenshot"""
        try:
            if not self._page:
                raise BrowserOperationError("Page is not initialized")
            screenshot = await self._page.screenshot(full_page=is_full_page)
            self.logger.debug("Screenshot captured successfully")
            return screenshot
        except Exception as e:
            self.logger.error(f"Screenshot failed: {str(e)}")
            raise

    async def _capture_html(self) -> str:
        """Capture complete HTML content of the page"""
        try:
            if not self._page:
                raise BrowserOperationError("Page is not initialized")
            html = await self._page.content()
            self.logger.debug("HTML captured successfully")
            return html
        except Exception as e:
            self.logger.error(f"HTML capture failed: {str(e)}")
            raise

    async def _capture_js(self) -> str:
        """Capture JavaScript code from all script tags on the page"""
        try:
            if not self._page:
                raise BrowserOperationError("Page is not initialized")
            js = await self._page.evaluate(
                "() => { return Array.from(document.scripts).map(script => script.textContent).join('\\n'); }"
            )
            self.logger.debug("JS captured successfully")
            return js
        except Exception as e:
            self.logger.error(f"JS capture failed: {str(e)}")
            raise

    async def _capture_text(self) -> str:
        """Capture all visible text content on the page"""
        try:
            if not self._page:
                raise BrowserOperationError("Page is not initialized")
            text = await self._page.inner_text("body")
            self.logger.debug("Text captured successfully")
            return text
        except Exception as e:
            self.logger.error(f"Text capture failed: {str(e)}")
            raise

    async def _show_mouse_move(self, x: int, y: int) -> None:
        """
        Animate mouse movement from screen edge to target position
        :param x: Target element center x-coordinate
        :param y: Target element center y-coordinate
        :return: None
        """
        if not self._page:
            return

        try:
            # Get current viewport size
            viewport_size = await self._page.evaluate("({ width: window.innerWidth, height: window.innerHeight })")
            screen_width = viewport_size['width']
            screen_height = viewport_size['height']

            # Calculate initial movement direction (based on relative position to viewport center)
            dx = -200 if x < screen_width / 2 else 200  # horizontal offset
            dy = -200 if y < screen_height / 2 else 200  # vertical offset
            rotate = 30 if dx > 0 else -30  # set rotation angle based on direction

            # Read SVG file
            try:
                with open(get_absolute_path("/icon/mouse.svg"), "rb") as f:
                    svg_data = f.read()
                svg_base64 = base64.b64encode(svg_data).decode("utf-8")
                svg_url = f"data:image/svg+xml;base64,{svg_base64}"
            except Exception as e:
                self.logger.error(f"Failed to load mouse SVG: {str(e)}")
                # Use fallback image URL
                svg_url = "data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHZpZXdCb3g9IjAgMCAzMCAzMCI+PHBhdGggZD0iTTEyIDI0LjQyMkwyLjUgMTQuOTIyVjMuNUgyNS41VjI1LjVIMTJWMjQuNDIyWiIgc3Ryb2tlPSJibGFjayIgc3Ryb2tlLXdpZHRoPSIyIiBmaWxsPSJ3aGl0ZSIvPjwvc3ZnPg=="

            # JavaScript code needs to use single quotes, and inject Python variables correctly using f-string
            js_code = f"""
                () => {{
                    // Remove any existing mouse animation elements
                    const existingMouse = document.getElementById('animated-mouse');
                    if (existingMouse) existingMouse.remove();

                    // Create new mouse element
                    const moveImg = document.createElement('img');
                    moveImg.id = 'animated-mouse';
                    moveImg.src = '{svg_url}';

                    // Set element base styles
                    moveImg.style.position = 'fixed'; // Use fixed instead of absolute to avoid scrolling issues
                    moveImg.style.width = '30px';
                    moveImg.style.height = '30px';
                    moveImg.style.zIndex = '9999';
                    moveImg.style.pointerEvents = 'none';

                    // Set initial position (calculated based on target position and offsets)
                    const startX = {x} + {dx};
                    const startY = {y} + {dy};
                    moveImg.style.left = startX - 15 + 'px';
                    moveImg.style.top = startY - 15 + 'px';
                    moveImg.style.transform = 'rotate({rotate}deg) scale(0.3)';

                    document.body.appendChild(moveImg);

                    // Ensure DOM updates before starting animation
                    setTimeout(() => {{
                        moveImg.style.transition = 'all 0.6s cubic-bezier(0.34, 1.56, 0.64, 1)';
                        moveImg.style.left = '{x - 15}px';
                        moveImg.style.top = '{y - 15}px';
                        moveImg.style.transform = 'rotate(0deg) scale(1)';
                    }}, 10);

                    // Remove element after animation completes
                    setTimeout(() => {{
                        moveImg.remove();
                    }}, 1200);
                }}
            """

            # Execute JavaScript code
            await self._page.evaluate(js_code)

            # Wait for animation to complete (0.6s animation time + 0.2s buffer)
            await self._wait(0.8)

        except Exception as e:
            self.logger.error(f"Failed to show mouse move animation to ({x}, {y}): {str(e)}")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)


    async def main():
        agent = BrowserController('https://www.baidu.com/')
        await agent.initialize()

        screenshot_count = 1  # Initialize screenshot counter

        while True:
            action_type = input(
                "Please enter operation type (click, left_double, right_single, drag, hotkey, type, scroll, screenshot, exit): ")
            if action_type == 'exit':
                break
            if action_type == 'screenshot':
                screenshot_path = f"screenshot_{screenshot_count}.png"  # Auto-generate screenshot filename
                try:
                    screenshot = await agent._capture_screenshot()
                    with open(screenshot_path, "wb") as f:
                        f.write(screenshot)
                    print(f"Screenshot saved to {screenshot_path}")
                    screenshot_count += 1  # Increment counter
                except Exception as e:
                    print(f"Screenshot failed: {e}")
                continue

            # Create Action object based on operation type
            if action_type in ['click', 'left_double', 'right_single', 'scroll']:
                start_box_str = input("Please enter start_box (e.g., 100,200,300,400): ")
                start_box = tuple(map(int, start_box_str.split(',')))
                if action_type == 'scroll':
                    deltas_str = input("Please enter deltas (e.g., 0,100): ")
                    deltas = tuple(map(int, deltas_str.split(',')))
                    action = Action(action_type, params={'start_box': start_box, 'deltas': deltas})
                else:
                    action = Action(action_type, params={'start_box': start_box})
            elif action_type == 'drag':
                start_box_str = input("Please enter start_box (e.g., 100,200,300,400): ")
                start_box = tuple(map(int, start_box_str.split(',')))
                end_box_str = input("Please enter end_box (e.g., 500,600,700,800): ")
                end_box = tuple(map(int, end_box_str.split(',')))
                action = Action(action_type, params={'start_box': start_box, 'end_box': end_box})
            elif action_type == 'hotkey':
                key = input("Please enter key name (e.g., Enter, Escape, a): ")
                action = Action(action_type, params={'key': key})
            elif action_type == 'type':
                content = input("Please enter content to type: ")
                submit_str = input("Submit? (yes/no): ")
                submit = submit_str.lower() == 'yes'
                if submit:
                    content += '\n'
                action = Action(action_type, params={'content': content})
            else:
                print("Invalid operation type!")
                continue

            try:
                await agent.execute(action)
                print("Operation executed successfully!")
                # Save screenshot immediately after each operation, auto-numbered
                screenshot_path = f"screenshot_{screenshot_count}.png"
                try:
                    screenshot = await agent._capture_screenshot()
                    with open(screenshot_path, "wb") as f:
                        f.write(screenshot)
                    print(f"Screenshot saved to {screenshot_path}")
                    screenshot_count += 1
                except Exception as e:
                    print(f"Screenshot failed: {e}")
            except BrowserOperationError as e:
                print(f"Operation execution failed: {e}")
            except Exception as e:
                print(f"An unknown error occurred: {e}")

        await agent.shutdown()


    asyncio.run(main())
