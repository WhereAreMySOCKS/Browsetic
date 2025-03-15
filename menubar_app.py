import rumps
import os
import json
import subprocess
import threading
import asyncio

from agent import Agent

# 配置文件路径
CONFIG_FILE = os.path.expanduser("~/newsfilter_config.json")


class NewsFilterMenuBar(rumps.App):
    def __init__(self):
        super(NewsFilterMenuBar, self).__init__(
            name="NewsFilter",
            title="🌧️",
            icon=None,
            quit_button="退出"
        )
        # ToDo： 增加动画，提示用户程序正在执行

        # 状态变量
        self.websites = []
        self.commands = []
        self.saved_configs = []  # 保存的配置组合 [(网站, 指令), ...]
        self.current_website = ""
        self.current_command = ""
        self.task_running = False

        # 加载已保存的配置
        self.load_config()

        # 设置初始菜单
        self.setup_menu()

        self.agent = Agent()

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
            for site, cmd in self.saved_configs:
                # 格式为 "网站: 指令"
                config_name = f"{site}: {cmd}"
                item = rumps.MenuItem(config_name, callback=self.select_saved_config)
                if site == self.current_website and cmd == self.current_command:
                    item.state = 1
                my_configs_menu.add(item)
            self.menu.add(my_configs_menu)
            print("已添加 '我的配置' 菜单")

        # 2. 网站菜单
        website_menu = rumps.MenuItem("网站")
        if self.websites:
            for site in self.websites:
                item = rumps.MenuItem(site, callback=self.select_website)
                if site == self.current_website:
                    item.state = 1
                website_menu.add(item)
            website_menu.add(rumps.separator)  # 添加分隔线
        website_menu.add(rumps.MenuItem("添加网站", callback=self.add_website))
        self.menu.add(website_menu)
        print("已添加 '网站' 菜单")

        # 3. 指令菜单
        command_menu = rumps.MenuItem("指令")
        if self.commands:
            for cmd in self.commands:
                item = rumps.MenuItem(cmd, callback=self.select_command)
                if cmd == self.current_command:
                    item.state = 1
                command_menu.add(item)
            command_menu.add(rumps.separator)  # 添加分隔线
        command_menu.add(rumps.MenuItem("添加指令", callback=self.add_command))
        self.menu.add(command_menu)
        print("已添加 '指令' 菜单")

        # 4. 任务操作
        self.menu.add(rumps.separator)
        self.menu.add(rumps.MenuItem("开始任务", callback=self.start_task))
        self.menu.add(rumps.MenuItem("保存当前配置", callback=self.save_current_config))
        print("已添加任务操作菜单项")

        # 5. 高级设置
        self.menu.add(rumps.separator)
        advanced_menu = rumps.MenuItem("高级设置")
        advanced_menu.add(rumps.MenuItem("编辑配置文件", callback=self.edit_config_file))
        advanced_menu.add(rumps.MenuItem("清除所有配置", callback=self.clear_config))
        advanced_menu.add(rumps.MenuItem("查看日志", callback=self.open_logs))
        advanced_menu.add(rumps.MenuItem("显示通知测试", callback=self.test_notification))
        self.menu.add(advanced_menu)
        print("已添加 '高级设置' 菜单")

        # 6. 显示当前状态
        if self.current_website or self.current_command:
            status = "当前: "
            if self.current_website:
                status += self.current_website
            if self.current_website and self.current_command:
                status += " | "
            if self.current_command:
                status += self.current_command
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
            # ToDO 优化名称，可以让用户起一个
            short_name = ''.join([c for c in self.current_website if c.isupper() or c.isdigit()])
            if not short_name:
                short_name = self.current_website[:2]
            self.title = f"🌧️ {short_name}"
        else:
            self.title = "🌧️"
        print(f"菜单标题更新为: {self.title}")

    def test_notification(self, _):
        """测试不同通知方法"""
        print("\n===== 通知测试开始 =====")

        try:
            rumps.notification("测试通知 1", "使用 rumps.notification", "如果您看到此消息，rumps通知正常工作")
            print("rumps.notification 已调用")
        except Exception as e:
            print(f"rumps.notification 失败: {e}")

        try:
            cmd = ['osascript', '-e',
                   'display notification "如果您看到此消息，简单AppleScript通知正常工作" with title "测试通知 2"']
            result = subprocess.run(cmd, capture_output=True, text=True)
            print(f"osascript 简单版返回状态: {result.returncode}")
            if result.stderr:
                print(f"错误输出: {result.stderr}")
        except Exception as e:
            print(f"osascript 简单版失败: {e}")

        print("\n方法3: 使用终端通知")
        print("*********************************")
        print("* 测试通知 3: 终端通知          *")
        print("* 如果你看到这个，终端输出正常  *")
        print("*********************************")

        print("===== 通知测试结束 =====\n")

    def show_notification(self, title, subtitle, message):
        """显示通知并在控制台打印"""
        print(f"\n通知: [{title}] {subtitle}\n{message}")
        try:
            rumps.notification(title, subtitle, message)
        except Exception as e:
            print(f"rumps通知失败: {e}")

        try:
            script = f'display notification "{message}" with title "{title}"'
            if subtitle:
                script += f' subtitle "{subtitle}"'
            subprocess.run(['osascript', '-e', script], capture_output=True)
        except Exception as e:
            print(f"AppleScript通知失败: {e}")

    def applescript_input_dialog(self, title, message, default_text=""):
        """使用AppleScript显示输入对话框"""
        # ToDO 太丑了
        print(f"\n对话框: [{title}] {message}")
        try:
            script = f'''
            tell application "System Events"
                display dialog "{message}" default answer "{default_text}" with title "{title}"
                set dialogResult to result
                set buttonPressed to button returned of dialogResult
                set textReturned to text returned of dialogResult
                return textReturned
            end tell
            '''
            result = subprocess.run(['osascript', '-e', script], capture_output=True, text=True)
            if result.returncode == 0:
                response = result.stdout.strip()
                print(f"用户输入: {response}")
                return response
            else:
                print(f"对话框取消或失败: {result.stderr}")
        except Exception as e:
            print(f"对话框显示失败: {e}")
        return None

    def applescript_confirm_dialog(self, title, message):
        """使用AppleScript显示确认对话框"""
        # ToDO 太丑了
        print(f"\n确认对话框: [{title}] {message}")
        try:
            script = f'''
            tell application "System Events"
                display dialog "{message}" buttons {{"取消", "确定"}} default button "确定" with title "{title}"
                set dialogResult to result
                set buttonPressed to button returned of dialogResult
                return buttonPressed
            end tell
            '''
            result = subprocess.run(['osascript', '-e', script], capture_output=True, text=True)
            confirmed = result.returncode == 0 and "确定" in result.stdout
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
            site, cmd = title.split(": ", 1)
            self.current_website = site
            self.current_command = cmd
            print(f"已设置当前网站: {site}")
            print(f"已设置当前指令: {cmd}")
            self.setup_menu()
            self.show_notification("NewsFilter", "配置已选择",
                                   f"当前网站: {site}\n当前指令: {cmd}")
        except ValueError as e:
            print(f"选择配置失败: {e}")
            self.show_notification("NewsFilter", "错误", "配置格式不正确")

    def save_current_config(self, _):
        """保存当前的网站和指令组合"""
        print("\n保存当前配置")
        if not self.current_website or not self.current_command:
            print("错误: 未选择网站或指令")
            self.show_notification("NewsFilter", "错误", "请先选择网站和指令")
            return

        config_pair = (self.current_website, self.current_command)
        if config_pair in self.saved_configs:
            print(f"配置已存在: {config_pair}")
            self.show_notification("NewsFilter", "提示", "此配置组合已保存")
            return

        self.saved_configs.append(config_pair)
        print(f"已添加配置: {config_pair}")
        self.save_config()
        self.setup_menu()
        self.show_notification("NewsFilter", "配置已保存",
                               f"已保存配置: {self.current_website} - {self.current_command}")

    def add_website(self, _):
        """添加新网站"""
        print("\n添加新网站")
        website = self.applescript_input_dialog("添加网站", "请输入网站名称或URL:")
        if website and website.strip():
            website = website.strip()
            if website not in self.websites:
                self.websites.append(website)
                self.current_website = website
                print(f"已添加新网站: {website}")
                self.save_config()
                self.setup_menu()
                self.show_notification("NewsFilter", "网站已添加", f"当前网站: {website}")
            else:
                print(f"网站已存在: {website}")
                self.show_notification("NewsFilter", "提示", "此网站已在列表中")
                self.current_website = website
                self.setup_menu()
        else:
            print("用户取消或输入为空")

    def add_command(self, _):
        """添加新指令"""
        print("\n添加新指令")
        command = self.applescript_input_dialog("添加指令", "请输入指令:")
        if command and command.strip():
            command = command.strip()
            if command not in self.commands:
                self.commands.append(command)
                self.current_command = command
                print(f"已添加新指令: {command}")
                self.save_config()
                self.setup_menu()
                self.show_notification("NewsFilter", "指令已添加", f"当前指令: {command}")
            else:
                print(f"指令已存在: {command}")
                self.show_notification("NewsFilter", "提示", "此指令已在列表中")
                self.current_command = command
                self.setup_menu()
        else:
            print("用户取消或输入为空")

    def select_website(self, sender):
        """选择网站回调"""
        website = sender.title
        print(f"\n选择网站: {website}")
        self.current_website = website
        self.update_title()
        self.setup_menu()  # 重建菜单以更新状态
        self.show_notification("NewsFilter", "网站已选择", f"当前网站: {self.current_website}")

    def select_command(self, sender):
        """选择指令回调"""
        command = sender.title
        print(f"\n选择指令: {command}")
        self.current_command = command
        self.setup_menu()  # 重建菜单以更新状态
        self.show_notification("NewsFilter", "指令已选择", f"当前指令: {self.current_command}")

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
        confirm = self.applescript_confirm_dialog("确认", "确定要清除所有配置吗?")
        if confirm:
            print("用户确认清除配置")
            self.websites = []
            self.commands = []
            self.saved_configs = []
            self.current_website = ""
            self.current_command = ""
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

        if not self.current_command:
            print("错误: 未选择指令")
            self.show_notification("NewsFilter", "错误", "请先选择或添加一个指令")
            return

        print(f"开始执行任务: 网站={self.current_website}, 指令={self.current_command}")
        self.show_notification("NewsFilter", "任务开始", f"网站: {self.current_website}\n指令: {self.current_command}")
        self.task_running = True

        # 启动一个线程来运行异步任务
        threading.Thread(target=self._run_async_task, daemon=True).start()

    def _run_async_task(self):
        """在单独的线程中运行异步任务"""
        try:
            # 设置网站
            self.agent.set_websit(self.current_website)

            # 为这个线程创建一个新的事件循环
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

            # 运行异步任务
            loop.run_until_complete(self._execute_task())
            loop.close()
        except Exception as e:
            print(f"任务执行出错: {e}")
            # 在主线程上安排通知
            rumps.Timer(0, lambda _: self.show_notification("NewsFilter", "任务失败", str(e))).start()
        finally:
            # 标记任务完成
            self.task_running = False

    async def _execute_task(self):
        """实际的异步任务执行"""
        try:
            # 注意: 这里修复了字符串引用的问题，使用实际值而不是字符串字面量
            await self.agent.work(self.current_command)

            # 任务完成后在主线程上安排通知
            rumps.Timer(0, lambda _: self.show_notification(
                "NewsFilter",
                "任务完成",
                f"网站: {self.current_website}\n指令: {self.current_command}"
            )).start()
        except Exception as e:
            print(f"执行任务时出错: {e}")
            raise  # 重新抛出异常，让_run_async_task捕获

    def open_logs(self, _):
        """打开日志"""
        print("\n查看日志")
        self.show_notification("NewsFilter", "日志", "日志功能尚未实现")

    def save_config(self):
        """保存配置到文件"""
        print(f"\n保存配置到: {CONFIG_FILE}")
        config = {
            "websites": self.websites,
            "commands": self.commands,
            "saved_configs": self.saved_configs,
            "last_website": self.current_website,
            "last_command": self.current_command
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
                    self.commands = config.get("commands", [])
                    self.saved_configs = config.get("saved_configs", [])
                    self.current_website = config.get("last_website", "")
                    self.current_command = config.get("last_command", "")
                print("配置加载成功")
                print(f"已加载 {len(self.websites)} 个网站")
                print(f"已加载 {len(self.commands)} 个指令")
                print(f"已加载 {len(self.saved_configs)} 个保存的配置")
            except Exception as e:
                print(f"加载配置失败: {e}")


if __name__ == "__main__":
    print("启动 NewsFilter 应用")
    app = NewsFilterMenuBar()
    app.run()