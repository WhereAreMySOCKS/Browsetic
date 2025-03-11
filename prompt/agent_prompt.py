from utils.get_absolute_path import get_absolute_path


def get_prompt(_user_command):
    path = get_absolute_path("/prompt/prompt_template.txt")
    with open(path, 'r') as f:
        content = f.read()
    content = content.format(user_command=_user_command)
    return content


if __name__ == '__main__':
    user_command = "搜索框输入“当日黄金价格”，点击搜索按钮，查看最相关页面，确认今日黄金金价，并保存截图。"
    print(get_prompt(user_command))
