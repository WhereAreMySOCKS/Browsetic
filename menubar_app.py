import rumps
import os
import json
import subprocess
import threading
import asyncio
import sys

from PyQt6.QtWidgets import QApplication

from agent import Agent
from utils.dialog_window import *

# 配置文件路径
CONFIG_FILE = os.path.expanduser("~/newsfilter_config.json")


# ToDo 增加配置大模型功能
class NewsFilterMenuBar(rumps.App):
    def __init__(self):
        idle_icon_path = 'icon/idle_icon.png'
        working_icon_path = 'icon/working_icon.png'
        super(NewsFilterMenuBar, self).__init__(
            name="NewsFilter",
            title="",
            icon=idle_icon_path,  # 默认图标 - 空闲状态
            quit_button="退出"
        )
        # 初始化图标路径
        # 存储图标对象而不只是路径
        self.icons = {
            'idle': idle_icon_path,
            'working': working_icon_path
        }

        # 初始化PyQt应用
        self.qt_app = QApplication.instance()
        if not self.qt_app:
            self.qt_app = QApplication(sys.argv)

        # 状态变量
        self.websites = []
        self.commands = {}  # 改为字典：{名称: 内容}
        self.saved_configs = []  # 保存的配置组合 [(网站, 指令名称), ...]
        self.current_website = ""
        self.current_website_name = ""
        self.current_command_name = ""  # 当前选择的指令名称
        self.task_running = False
        self.api_key = ""  # 存储API Key
        self.agent = None  # 初始化时不创建Agent实例

        # 加载已保存的配置
        self.load_config()

        # 设置初始菜单
        self.setup_menu()

        # 检查并设置API Key
        if not self.api_key:
            self.configure_api_key(None)

        self.agent = Agent(api_key=self.api_key)  # 传入API Key

    def setup_menu(self):
        """设置菜单结构"""
        print("\n重建菜单结构")

        # 如果菜单中已存在退出按钮，保存它以便重新添加
        quit_item = None
        if "退出" in self.menu:
            quit_item = self.menu["退出"]

        # 直接清空所有菜单项
        self.menu.clear()

        # 1. 我的配置（已保存的网站+指令组合）
        if self.saved_configs:
            my_configs_menu = rumps.MenuItem("我的配置")
            for site, cmd_name in self.saved_configs:
                # 格式为 "网站: 指令名称"
                config_name = f"{site}: {cmd_name}"
                item = rumps.MenuItem(config_name, callback=self.select_saved_config)
                if site == self.current_website and cmd_name == self.current_command_name:
                    item.state = 1
                my_configs_menu.add(item)
            self.menu.add(my_configs_menu)
            print("已添加 '我的配置' 菜单")

        # 2. 网站菜单
        website_menu = rumps.MenuItem("我的网站")
        if self.websites:
            for site in self.websites:
                item = rumps.MenuItem(site, callback=self.select_website)
                if site == self.current_website:
                    item.state = 1
                website_menu.add(item)
            website_menu.add(rumps.separator)  # 添加分隔线
        website_menu.add(rumps.MenuItem("添加", callback=self.add_website))
        self.menu.add(website_menu)
        print("已添加 '网站' 菜单")

        # 3. 指令菜单
        command_menu = rumps.MenuItem("我的指令")
        if self.commands:
            for cmd_name in self.commands.keys():
                item = rumps.MenuItem(cmd_name, callback=self.select_command)
                if cmd_name == self.current_command_name:
                    item.state = 1
                command_menu.add(item)
            command_menu.add(rumps.separator)  # 添加分隔线
        command_menu.add(rumps.MenuItem("添加", callback=self.add_command))
        self.menu.add(command_menu)
        print("已添加 '指令' 菜单")

        # 4. 任务操作
        self.menu.add(rumps.separator)
        self.menu.add(rumps.MenuItem("开始任务", callback=self.start_task))
        self.menu.add(rumps.MenuItem("保存当前配置", callback=self.save_current_config))
        print("已添加任务操作菜单项")

        # 5. 新增的删除菜单
        self.menu.add(rumps.separator)
        delete_menu = rumps.MenuItem("删除")

        # 删除指令子菜单
        if self.commands:
            delete_commands_menu = rumps.MenuItem("删除指令")
            for cmd_name in self.commands.keys():
                item = rumps.MenuItem(cmd_name, callback=self.delete_command)
                delete_commands_menu.add(item)
            delete_menu.add(delete_commands_menu)

        # 删除网站子菜单
        if self.websites:
            delete_websites_menu = rumps.MenuItem("删除网站")
            for site in self.websites:
                item = rumps.MenuItem(site, callback=self.delete_website)
                delete_websites_menu.add(item)
            delete_menu.add(delete_websites_menu)

        # 一键清空选项
        delete_menu.add(rumps.MenuItem("一键清空", callback=self.clear_config))

        self.menu.add(delete_menu)
        print("已添加 '删除' 菜单")

        # 6. 高级设置
        self.menu.add(rumps.separator)
        advanced_menu = rumps.MenuItem("设置")
        advanced_menu.add(rumps.MenuItem("配置API Key", callback=self.configure_api_key))
        advanced_menu.add(rumps.MenuItem("编辑配置文件", callback=self.edit_config_file))
        advanced_menu.add(rumps.MenuItem("查看日志", callback=self.open_logs))
        self.menu.add(advanced_menu)
        print("已添加 '高级设置' 菜单")

        # 7. 显示当前状态
        if self.current_website_name or self.current_command_name:
            status = "当前: "
            if self.current_website:
                status += self.current_website_name
            if self.current_website and self.current_command_name:
                status += " | "
            if self.current_command_name:
                status += self.current_command_name
            self.menu.add(rumps.separator)
            self.menu.add(rumps.MenuItem(status, callback=None))
            print(f"已添加状态显示: {status}")

        # 如果之前存在退出按钮，则重新添加
        if quit_item is not None:
            self.menu.add(quit_item)

        # 更新标题显示当前选择
        self.update_title()
        print("菜单重建完成")

    def update_title(self):
        """更新菜单栏标题显示当前选择"""
        if self.current_website:
            # 提取域名中间部分，去除www和com等
            domain_parts = self.current_website.split('.')

            # 如果长度至少为3，可能包含www前缀
            if len(domain_parts) >= 3 and domain_parts[0].lower() in ['www', 'https://www']:
                # 去除www和最后一个部分(com/org等)，只保留中间部分
                self.current_website_name = domain_parts[1]
            # 如果只有两部分(如example.com)
            elif len(domain_parts) >= 2:
                # 只保留第一个部分
                self.current_website_name = domain_parts[0]
            else:
                # 如果格式不符合预期，保留原样
                self.current_website_name = self.current_website

            self.title = f"{self.current_website_name}"
        else:
            self.title = "️"
        print(f"菜单标题更新为: {self.title}")

    def set_icon_state(self, is_working=False):
        """更新应用图标状态"""
        icon_key = 'working' if is_working else 'idle'

        # 如果当前图标已经是目标状态，则不进行操作
        if hasattr(self, "_current_icon_state") and self._current_icon_state == icon_key:
            return

        print(f"set_icon_state 被调用, 目标图标: {icon_key}")
        self._current_icon_state = icon_key  # 记录当前图标状态

        # 取消之前的定时器（如果存在）
        if hasattr(self, "_icon_timer") and self._icon_timer is not None:
            self._icon_timer.stop()
            self._icon_timer = None

        def delayed_set(_):
            self.icon = self.icons[icon_key]

            # 只在调试模式下打印或使用日志记录而非直接打印
            if hasattr(self, "debug_mode") and self.debug_mode:
                print(f"已切换到{icon_key}图标")

            # 轻微改变菜单以触发刷新 - 使用更简洁的方式
            original_title = self.title
            self.title = original_title + " "
            self.title = original_title

            # 完成后清除定时器引用
            self._icon_timer = None

        self._icon_timer = rumps.Timer(delayed_set, 0.2)
        self._icon_timer.start()


    def show_notification(self, title, subtitle, message):
        """显示通知并在控制台打印"""
        print(f"\n通知: [{title}] {subtitle}\n{message}")
        try:
            rumps.notification(title, subtitle, message)
        except Exception as e:
            print(f"rumps通知失败: {e}")

    def qt_input_dialog(self, title, message, default_text="", multiline=False):
        """使用PyQt显示输入对话框"""
        print(f"\n对话框: [{title}] {message}")
        try:
            # 确保在主线程中执行
            dialog = InputDialog(title, message, default_text, multiline)
            result = dialog.get_text()
            print(f"用户输入: {result}")
            return result
        except Exception as e:
            print(f"对话框显示失败: {e}")
        return None

    def qt_confirm_dialog(self, title, message):
        """使用PyQt显示确认对话框"""
        print(f"\n确认对话框: [{title}] {message}")
        try:
            confirmed = confirm_dialog(title, message)
            print(f"用户选择: {'确定' if confirmed else '取消'}")
            return confirmed
        except Exception as e:
            print(f"确认对话框失败: {e}")
        return False

    def select_saved_config(self, sender):
        """选择已保存的配置组合"""
        try:
            title = sender.title
            print(f"\n选择配置: {title}")
            site, cmd_name = title.split(": ", 1)
            self.current_website = site
            self.current_command_name = cmd_name
            # 更新网站名称
            self.update_title()
            print(f"已设置当前网站: {site}")
            print(f"已设置当前指令: {cmd_name}")
            self.setup_menu()
            self.show_notification("NewsFilter", "配置已选择",
                                   f"当前网站: {self.current_website_name}\n当前指令: {cmd_name}")
        except ValueError as e:
            print(f"选择配置失败: {e}")
            self.show_notification("NewsFilter", "错误", "配置格式不正确")

    def save_current_config(self, _):
        """保存当前的网站和指令组合"""
        print("\n保存当前配置")
        if not self.current_website or not self.current_command_name:
            print("错误: 未选择网站或指令")
            self.show_notification("NewsFilter", "错误", "请先选择网站和指令")
            return

        config_pair = (self.current_website, self.current_command_name)
        if config_pair in self.saved_configs:
            print(f"配置已存在: {config_pair}")
            self.show_notification("NewsFilter", "提示", "此配置组合已保存")
            return

        self.saved_configs.append(config_pair)
        print(f"已添加配置: {config_pair}")
        self.save_config()
        self.setup_menu()
        # 使用更简洁的网站名称显示
        self.show_notification("NewsFilter", "配置已保存",
                               f"已保存配置: {self.current_website_name} - {self.current_command_name}")

    def add_website(self, _):
        """添加新网站"""
        print("\n添加新网站")
        website = self.qt_input_dialog("添加网站", "请输入网站名称或URL:")
        if website and website.strip():
            website = website.strip()
            if website not in self.websites:
                self.websites.append(website)
                self.current_website = website
                # 立即更新网站名称显示
                self.update_title()
                print(f"已添加新网站: {website}")
                self.save_config()
                self.setup_menu()
                self.show_notification("NewsFilter", "网站已添加", f"当前网站: {self.current_website_name}")
            else:
                print(f"网站已存在: {website}")
                self.current_website = website
                # 立即更新网站名称显示
                self.update_title()
                self.setup_menu()
                self.show_notification("NewsFilter", "提示", f"此网站已在列表中，已选择: {self.current_website_name}")
        else:
            print("用户取消或输入为空")

    def add_command(self, _):
        """添加新指令 - 使用组合输入对话框"""
        print("\n添加新指令")
        try:
            # 使用组合输入对话框
            dialog = CommandInputDialog("添加指令")
            command_name, command = dialog.get_inputs()

            if not command_name or not command:
                print("用户取消或输入为空")
                return

            if command_name not in self.commands:
                self.commands[command_name] = command  # 存储到字典中
                self.current_command_name = command_name
                print(f"已添加新指令: {command_name}")
                self.save_config()
                self.setup_menu()
                self.show_notification("NewsFilter", "指令已添加", f"当前指令: {command_name}")
            else:
                print(f"指令名称已存在: {command_name}")
                self.show_notification("NewsFilter", "提示", "此指令名称已在列表中")
                self.current_command_name = command_name
                self.setup_menu()
        except Exception as e:
            print(f"添加指令失败: {e}")
            self.show_notification("NewsFilter", "错误", f"添加指令失败: {str(e)}")

    def select_website(self, sender):
        """选择网站回调"""
        website = sender.title
        print(f"\n选择网站: {website}")
        self.current_website = website
        self.update_title()
        self.setup_menu()  # 重建菜单以更新状态
        self.show_notification("NewsFilter", "网站已选择", f"当前网站: {self.current_website_name}")

    def select_command(self, sender):
        """选择指令回调"""
        command_name = sender.title
        print(f"\n选择指令: {command_name}")
        self.current_command_name = command_name
        self.setup_menu()  # 重建菜单以更新状态
        self.show_notification("NewsFilter", "指令已选择", f"当前指令: {self.current_command_name}")

    def edit_config_file(self, _):
        """在文本编辑器中编辑配置文件"""
        print("\n编辑配置文件")
        self.save_config()
        subprocess.call(["open", CONFIG_FILE])
        print(f"已打开配置文件: {CONFIG_FILE}")
        self.show_notification("NewsFilter", "配置文件", "已打开配置文件，保存后重启应用生效")

    def clear_config(self, _):
        """清除所有配置"""
        print("\n清除所有配置")
        confirm = self.qt_confirm_dialog("确认", "确定要清除所有配置吗?")
        if confirm:
            print("用户确认清除配置")
            self.websites = []
            self.commands = {}  # 清空字典
            self.saved_configs = []
            self.current_website = ""
            self.current_command_name = ""
            print("已清空所有配置数据")
            self.save_config()
            self.setup_menu()
            self.show_notification("NewsFilter", "配置已清除", "所有配置已被清除")
        else:
            print("用户取消清除操作")

    def start_task(self, _):
        """开始任务 - 非异步版本，启动一个线程来执行异步操作"""
        print("\n开始任务")
        if self.task_running:
            print("错误: 任务已在进行中")
            self.show_notification("NewsFilter", "任务进行中", "请等待当前任务完成")
            return

        if not self.current_website:
            print("错误: 未选择网站")
            self.show_notification("NewsFilter", "错误", "请先选择或添加一个网站")
            return

        if not self.current_command_name:
            print("错误: 未选择指令")
            self.show_notification("NewsFilter", "错误", "请先选择或添加一个指令")
            return

        # 获取指令内容
        command_content = self.commands.get(self.current_command_name)
        if not command_content:
            print(f"错误: 找不到指令内容: {self.current_command_name}")
            self.show_notification("NewsFilter", "错误", "指令内容不存在")
            return

        # 检查API Key
        if not self.api_key:
            print("错误: 未配置API Key")
            self.show_notification("NewsFilter", "错误", "请先配置API Key")
            self.configure_api_key(None)
            if not self.api_key:  # 如果用户取消了配置
                return

        # 确保Agent实例存在
        if not self.agent:
            self.agent = Agent(api_key=self.api_key)

        print(f"开始执行任务: 网站={self.current_website}, 指令={self.current_command_name}")
        self.show_notification("NewsFilter", "任务开始",
                               f"网站: {self.current_website_name}\n指令: {self.current_command_name}")

        # 设置任务状态并更新图标
        self.task_running = True
        self.set_icon_state(is_working=True)  # 切换到工作图标

        # 启动一个线程来运行异步任务
        threading.Thread(target=self._run_async_task, args=(command_content,), daemon=True).start()

    def _run_async_task(self, command_content):
        """在单独的线程中运行异步任务"""
        try:
            # 设置网站
            self.agent.set_website(self.current_website)

            # 为这个线程创建一个新的事件循环
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

            # 运行异步任务
            loop.run_until_complete(self._execute_task(command_content))
            loop.close()
        except Exception as e:
            print(f"任务执行出错: {e}")

            # 在主线程上安排通知
            def show_error_notification(_):
                self.show_notification("NewsFilter", "任务失败", str(e))
                # 任务失败时切换回空闲图标
                self.set_icon_state(is_working=False)

            timer = rumps.Timer(show_error_notification, 0.1)
            timer.start()
        finally:
            # 标记任务完成，并在主线程上切换回空闲图标
            self.task_running = False

            def restore_idle_state(_):
                self.set_icon_state(is_working=False)

            timer = rumps.Timer(restore_idle_state, 0.1)
            timer.start()

    async def _execute_task(self, command_content):
        """实际的异步任务执行"""
        try:
            # 使用指令内容执行任务
            await self.agent.work(command_content)

            # 任务完成后在主线程上安排通知
            def show_completion_notification(_):
                self.show_notification(
                    "NewsFilter",
                    "任务完成",
                    f"网站: {self.current_website_name}\n指令: {self.current_command_name}"
                )
                # 切换回空闲图标
                self.set_icon_state(is_working=False)

            timer = rumps.Timer(show_completion_notification, 0.1)
            timer.start()
        except Exception as e:
            print(f"执行任务时出错: {e}")
            raise  # 重新抛出异常，让_run_async_task捕获

    def open_logs(self, _):
        """打开日志文件夹"""
        print("\n查看日志")

        # 定义日志文件夹路径
        log_dir = "./logs"

        # 确保日志文件夹存在
        try:
            if not os.path.exists(log_dir):
                os.makedirs(log_dir)
                print(f"创建日志文件夹: {os.path.abspath(log_dir)}")

            # 在 macOS 上使用 open 命令打开文件夹
            abs_path = os.path.abspath(log_dir)
            subprocess.call(["open", abs_path])
            print(f"已打开日志文件夹: {abs_path}")

            self.show_notification("NewsFilter", "日志", f"已打开日志文件夹")
        except Exception as e:
            error_msg = f"打开日志文件夹失败: {str(e)}"
            print(error_msg)
            self.show_notification("NewsFilter", "错误", error_msg)

    def configure_api_key(self, _):
        """配置API Key"""
        print("\n配置API Key")
        api_key = self.qt_input_dialog("配置API Key", "请输入您的API Key:", self.api_key)
        if api_key and api_key.strip():
            self.api_key = api_key.strip()
            print("API Key已更新")
            self.save_config()
            self.show_notification("NewsFilter", "API Key已更新", "API Key配置已保存")
            # 重新初始化Agent
            self.agent = Agent(api_key=self.api_key)
        else:
            print("API Key配置已取消")

    def save_config(self):
        """保存配置到文件"""
        print(f"\n保存配置到: {CONFIG_FILE}")
        config = {
            "websites": self.websites,
            "commands": self.commands,  # 保存为字典 {名称: 内容}
            "saved_configs": self.saved_configs,
            "last_website": self.current_website,
            "last_command": self.current_command_name,
            "api_key": self.api_key  # 保存API Key
        }
        try:
            with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
                json.dump(config, f, ensure_ascii=False, indent=2)
            print("配置保存成功")
        except Exception as e:
            print(f"保存配置失败: {e}")
            self.show_notification("NewsFilter", "错误", "保存配置失败")

    def load_config(self):
        """从文件加载配置"""
        print(f"\n加载配置: {CONFIG_FILE}")
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                    self.websites = config.get("websites", [])

                    # 处理commands，兼容旧格式(列表)和新格式(字典)
                    commands_data = config.get("commands", {})
                    if isinstance(commands_data, list):
                        # 旧格式：将列表转换为字典
                        print("检测到旧格式的指令配置，正在转换...")
                        self.commands = {}
                        for i, cmd in enumerate(commands_data):
                            # 如果是元组(已经是新格式的一部分过渡)
                            if isinstance(cmd, list) and len(cmd) == 2:
                                self.commands[cmd[0]] = cmd[1]
                            else:
                                # 完全旧格式，使用序号作为名称
                                cmd_name = f"指令 {i + 1}"
                                self.commands[cmd_name] = cmd
                        print(f"转换完成，共 {len(self.commands)} 个指令")
                    else:
                        # 新格式：直接使用字典
                        self.commands = commands_data

                    self.saved_configs = config.get("saved_configs", [])
                    self.current_website = config.get("last_website", "")

                    # 处理当前指令名称，兼容旧版本
                    last_command = config.get("last_command", "")
                    # 如果last_command是字符串，可能是旧格式的指令内容或新格式的指令名称
                    if last_command:
                        if last_command in self.commands:
                            # 新格式：名称存在于字典中
                            self.current_command_name = last_command
                        else:
                            # 旧格式：需要找出对应的名称
                            for name, content in self.commands.items():
                                if content == last_command:
                                    self.current_command_name = name
                                    break
                            else:
                                self.current_command_name = ""

                    self.api_key = config.get("api_key", "")
                print("配置加载成功")
                print(f"已加载 {len(self.websites)} 个网站")
                print(f"已加载 {len(self.commands)} 个指令")
                print(f"已加载 {len(self.saved_configs)} 个保存的配置")
                if self.api_key:
                    print("已加载API Key配置")
            except Exception as e:
                print(f"加载配置失败: {e}")

    def delete_website(self, sender):
        """删除单个网站"""
        website = sender.title
        print(f"\n删除网站: {website}")

        # 从网站列表中移除
        if website in self.websites:
            self.websites.remove(website)
            print(f"已删除网站: {website}")

            # 如果删除的是当前选择的网站，则清除当前选择
            if self.current_website == website:
                self.current_website = ""
                self.current_website_name = ""

            # 移除相关的已保存配置
            self.saved_configs = [(site, cmd) for site, cmd in self.saved_configs
                                  if site != website]

            # 保存配置并更新菜单
            self.save_config()
            self.setup_menu()
            self.update_title()
            self.show_notification("NewsFilter", "删除成功", f"已删除网站: {website}")
        else:
            print(f"错误: 网站不存在: {website}")

    def delete_command(self, sender):
        """删除单个指令"""
        cmd_name = sender.title
        print(f"\n删除指令: {cmd_name}")

        # 从指令字典中移除
        if cmd_name in self.commands:
            del self.commands[cmd_name]
            print(f"已删除指令: {cmd_name}")

            # 如果删除的是当前选择的指令，则清除当前选择
            if self.current_command_name == cmd_name:
                self.current_command_name = ""

            # 移除相关的已保存配置
            self.saved_configs = [(site, cmd) for site, cmd in self.saved_configs
                                  if cmd != cmd_name]

            # 保存配置并更新菜单
            self.save_config()
            self.setup_menu()
            self.show_notification("NewsFilter", "删除成功", f"已删除指令: {cmd_name}")
        else:
            print(f"错误: 指令不存在: {cmd_name}")


if __name__ == "__main__":
    print("启动 NewsFilter 应用")
    app = NewsFilterMenuBar()
    app.run()
