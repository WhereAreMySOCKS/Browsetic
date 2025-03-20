import asyncio
import logging
import os
from datetime import datetime

from browser_controller import BrowserController  # 假设 browser_controller.py 文件已存在
from action import Action  # 假设 utils/action.py 文件已存在
from vision_llm import VisionLLM  # 假设 vision_llm.py 文件已存在

# 网站字典，用于存储不同网站的 URL
WEBSITE_DICT = {
    '百度': 'https://www.baidu.com/',
    '微博': 'https://weibo.com/newlogin?tabtype=mine&gid=&openLoginLayer=0&url=https%3A%2F%2Fwww.weibo.com%2F',
    '小红书': 'https://www.xiaohongshu.com/explore',
    'bing': 'https://www.bing.com/',
    'google': 'https://www.google.com/'
}

# 日志根目录
LOG_BASE_DIR = 'logs'
if not os.path.exists(LOG_BASE_DIR):
    os.makedirs(LOG_BASE_DIR)

# 配置全局日志记录器，输出到控制台和全局日志文件
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(name)s - %(message)s',  # 包含 logger 名称
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(os.path.join(LOG_BASE_DIR, 'global.log'), encoding='utf-8')  # 全局日志文件
    ]
)


class Agent:
    def __init__(self, api_key=None):
        """
        初始化 Agent 实例。

        Args:
            api_key (str): 用于 VisionLLM 的 API Key。
        """
        self.brain = VisionLLM(api_key=api_key)  # 传递API Key到VisionLLM
        self.hands = BrowserController()  # BrowserController 实例
        self.screenshot_cache = []  # 初始化截图缓存列表
        self.logger = logging.getLogger(f'Agent')  # 使用更具描述性的 logger 名称
        self._is_stop_work = False

    async def work(self, user_instruction):
        """
        执行 Agent 的主要工作流程。

        Args:
            user_instruction (str): 用户指令。
        """
        assert self.hands.website_url, "未指定任务网站，请设置！"
        history = []
        action = Action("start")
        step = 0
        # 创建任务专属日志文件夹，包含时间戳和网站名称
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.task_log_dir = os.path.join(LOG_BASE_DIR, f'task_{timestamp}_{os.path.basename(self.hands.website_url)}')
        os.makedirs(self.task_log_dir, exist_ok=True)
        log_file = os.path.join(self.task_log_dir, f'agent_{timestamp}.log')

        # 配置任务专属的日志文件处理器
        file_handler = logging.FileHandler(log_file, encoding='utf-8')
        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(name)s - %(message)s')  # 包含 logger 名称
        file_handler.setFormatter(formatter)
        self.logger.addHandler(file_handler)  # Agent Logger 添加文件Handler

        self.logger.info(f"任务开始：'{user_instruction}'，目标网站：'{self.hands.website_url}'")

        await self.hands.initialize()
        try:  # 使用 try...finally 确保即使发生异常也关闭浏览器
            while action.action_type not in ['finished', 'call_user'] and not self._is_stop_work:
                step += 1
                self.logger.info(f"--- 开始步骤{step} ---")
                
                # 捕获当前页面信息
                try:
                    info = await self.hands.save_page_info()
                    screenshot = info.get('screenshot', None)
                    if screenshot:
                        self.screenshot_cache.append(screenshot)  # 缓存截图
                except Exception as e:
                    self.logger.error(f"捕获页面信息失败: {e}")
                    if step > 1:  # 如果不是第一步，尝试继续
                        continue
                    else:  # 如果是第一步就失败，则中断任务
                        raise
                
                self.logger.info(f"历史动作：{history}")
                self.logger.info(f"VisionLLM 思考中......")
                
                # AI思考并决定动作
                thought, action = self.brain.think(page_info=info,
                                                   user_instruction=user_instruction, history=history)
                self.logger.info(f"VisionLLM 思考结果 - Thought: '{thought}', Action: '{action}'")
                history.append(f'thought:{thought},action:{action}')
                
                # 执行动作
                try:
                    await self.hands.execute(action)
                    self.logger.info(f"动作执行成功: {action}")
                except Exception as e:
                    self.logger.error(f"动作执行失败: {e}")
                    if action.action_type == 'switch_tab':
                        self.logger.info("尝试刷新页面列表并重试...")
                        await self.hands.get_all_pages()  # 刷新页面列表
                        try:
                            await self.hands.execute(action)
                            self.logger.info(f"重试后动作执行成功: {action}")
                        except Exception as retry_error:
                            self.logger.error(f"重试仍然失败: {retry_error}")
                
                # 每个步骤后稍微等待
                await asyncio.sleep(0.5)
                
                self.logger.info(f"--- 步骤结束 ---\n\n\n")

            if action.action_type == 'finished':
                self.logger.info(f"任务完成！")
            elif action.action_type == 'call_user':
                self.logger.warning(f"请求用户协助：{action.question if hasattr(action, 'question') else '未提供问题'}")

        finally:
            # 清理资源
            await self.hands.shutdown()
            self.logger.info(f"浏览器已关闭。")
            self._save_cached_screenshots()  # 任务结束后保存所有缓存的截图
            self.logger.info(f"截图已保存，任务结束。")
            
            # 移除文件处理器以避免资源泄漏
            self.logger.removeHandler(file_handler)
            file_handler.close()

    def _save_cached_screenshots(self):
        """
        保存缓存的截图到任务专属日志文件夹。
        """
        if not self.screenshot_cache:
            self.logger.info("截图缓存为空，无需保存。")
            return

        self.logger.info(f"开始保存缓存的 {len(self.screenshot_cache)} 张截图...")
        for i, screenshot in enumerate(self.screenshot_cache):
            screenshot_filename = os.path.join(self.task_log_dir,
                                               f'screenshot_{datetime.now().strftime("%Y%m%d_%H%M%S_%f")}_{i + 1}.png')
            try:
                with open(screenshot_filename, 'wb') as f:
                    f.write(screenshot)
                self.logger.info(f"截图 {i + 1} 已保存: {screenshot_filename}")
            except Exception as e:
                self.logger.error(f"保存截图 {i + 1} 失败: {e}")
        self.screenshot_cache = []  # 清空缓存列表
        self.logger.info("所有缓存截图保存完毕，缓存已清空。")

    def set_website(self, website_url):
        self.hands.set_website_url(website_url)

    def stop_task(self):
        self._is_stop_work = True

