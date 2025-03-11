import os
from openai import OpenAI
from prompt.agent_prompt import get_prompt
from utils.get_absolute_path import get_absolute_path
from utils.img2base64 import image_to_base64

def main():
    image_path = get_absolute_path("/img.png")
    user_prompt = "打开百度搜索，搜索“当日黄金价格”，查看最相关页面，确认今日黄金金价，并保存截图。"
    result = []
    while True:
        response = next_step(image_path, user_prompt)
        result.append(response)
def next_step(image_path, user_prompt):
    """
    调用视觉大模型分析浏览器截图
    """
    # 将图片转换为 Base64 编码
    base64_image = image_to_base64(image_path)
    # 初始化 OpenAI 客户端
    client = OpenAI(
        api_key=os.getenv("DASHSCOPE_API_KEY"),
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
    )
    messages = [
        {"role": "system", "content": "你是一个浏览器自动化执行助手，根据用户上传的浏览器截图和用户指令规划当前步骤的动作。"},
        {"role": "user", "content": [
            {"type": "text", "text": get_prompt(user_prompt)},
            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}}
        ]}
    ]

    completion = client.chat.completions.create(
        model="qwen-vl-plus",
        messages=messages
    )

    # 返回模型的回复
    return completion.choices[0].message.content


# 示例用法
if __name__ == "__main__":
    main()