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
    def __init__(self, website_url: str = None):
        """
        初始化 Agent 实例。

        Args:
            website_url (str): 目标网站的 URL。
        """
        self.website_url = website_url
        self.brain = VisionLLM()  # VisionLLM 实例
        self.hands = BrowserController(self.website_url)  # BrowserController 实例
        self.screenshot_cache = []  # 初始化截图缓存列表
        self.logger = logging.getLogger(f'Agent[{website_url}]')  # 使用更具描述性的 logger 名称

    async def work(self, user_instruction):
        """
        执行 Agent 的主要工作流程。

        Args:
            user_instruction (str): 用户指令。
        """
        assert self.website_url,"未指定任务网站，请设置！"
        history = []
        action = Action("start")
        step = 0
        # 创建任务专属日志文件夹，包含时间戳和网站名称
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.task_log_dir = os.path.join(LOG_BASE_DIR, f'task_{timestamp}_{os.path.basename(self.website_url)}')
        os.makedirs(self.task_log_dir, exist_ok=True)
        log_file = os.path.join(self.task_log_dir, f'agent_{timestamp}.log')

        # 配置任务专属的日志文件处理器
        file_handler = logging.FileHandler(log_file, encoding='utf-8')
        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(name)s - %(message)s')  # 包含 logger 名称
        file_handler.setFormatter(formatter)
        self.logger.addHandler(file_handler)  # Agent Logger 添加文件Handler

        self.logger.info(f"任务开始：'{user_instruction}'，目标网站：'{self.website_url}'")

        await self.hands.initialize()
        try:  # 使用 try...finally 确保即使发生异常也关闭浏览器
            while action.action_type not in ['finished', 'call_user']:
                step += 1
                self.logger.info(f"--- 开始步骤{step} ---")
                info = await self.hands.save_page_info()
                screenshot = info.get('screenshot', None)
                # visible_elements = await self.hands.capture_visible_elements()
                if screenshot:
                    self.screenshot_cache.append(screenshot)  # 缓存截图
                self.logger.info(f"历史动作：{history}")
                self.logger.info(f"VisionLLM 思考中......")
                thought, action = self.brain.think(page_info=info,
                                                   user_instruction=user_instruction, history=history)
                self.logger.info(f"VisionLLM 思考结果 - Thought: '{thought}', Action: '{action}'")
                history.append(f'thought:{thought},action:{action}')
                await self.hands.execute(action)
                self.logger.info(f"--- 步骤结束 ---\n\n\n")

            if action.action_type == 'finished':
                self.logger.info(f"任务完成！")
            elif action.action_type == 'call_user':
                self.logger.warning(f"请求用户协助：{action.parameters.get('message', '')}")

        finally:
            await self.hands.shutdown()
            self.logger.info(f"浏览器已关闭。")
            self._save_cached_screenshots()  # 任务结束后保存所有缓存的截图
            self.logger.info(f"截图已保存，任务结束。")

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

    def set_websit(self,website_url):
        self.website_url = website_url
        self.hands.set_website_url(self.website_url)



async def main():
    """
    主函数，用于创建 Agent 并执行任务。
    """
    website_key = 'google'  # 可以修改为 '微博' 或 '小红书'
    agent = Agent()
    agent.set_websit("https://www.google.com.hk/")
    await agent.work("在输入框输入‘今日黄金价格’,回车搜索，查看最相关页面，收集网页结果返回")
    # 可以创建多个 Agent 并发执行任务 (示例代码已注释)
    # agents = [Agent(WEBSITE_DICT['百度']) for _ in range(2)] # 创建多个 Agent 实例
    # tasks = [asyncio.create_task(agent.work("查询今日黄金价格")) for agent in agents] # 创建任务列表
    # await asyncio.gather(*tasks) # 并发执行任务


if __name__ == '__main__':
    asyncio.run(main())
