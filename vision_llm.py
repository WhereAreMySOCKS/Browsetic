import json
import os
from openai import OpenAI
from prompt.agent_prompt import get_prompt
from action import Action


class VisionLLM:
    def __init__(self, model_name='qwen2.5-vl-72b-instruct', api_key=None):
        self.client = OpenAI(
            api_key=api_key or os.getenv("DASHSCOPE_API_KEY"),
            base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        )
        self.model = model_name
        self.sys_role = '你是一个浏览器自动化执行助手，根据用户上传的浏览器截图和用户指令规划当前步骤的动作。'

    def parse_llm_output(self, output):
        """
        将 LLM 输出的 JSON 字符串解析为字典，并将 Action 字段转为真正的 Action 类实例。

        参数:
            output (str): LLM 返回的 JSON 格式字符串。

        返回:
            dict: 解析后的字典，'Action' 字段为真正的 Action 类实例。
        """
        try:
            # 去除 JSON 块的标记，确保只保留纯 JSON 部分
            cleaned_output = output.strip('```json').strip('```').strip()
            cleaned_string = " ".join(cleaned_output.split())

            # 将字符串解析为字典
            parsed = json.loads(cleaned_string)

            # 验证必需字段
            if 'Action' not in parsed or 'Thought' not in parsed:
                raise ValueError("缺少必要字段 'Action' 或 'Thought'")

            # 构造 Action 实例（如果有参数，就解包传参）
            action_type = parsed['Action']
            action_params = parsed.get('Parameters', {})
            parsed['Action'] = Action(action_type, action_params)
            return parsed

        except json.JSONDecodeError as e:
            print(f"JSON 解析失败: {e}")
        except TypeError as e:
            print(f"Action 实例化失败: {e}")
        except Exception as e:
            print(f"发生未知错误: {e}")

        return None

    def think(self, *args, **kwargs):
        _page_info = kwargs.get('page_info', None)
        user_instruction = kwargs.get('user_instruction', None)
        history = kwargs.get('history', [])
        visible_elements = kwargs.get('visible_elements', None)

        # 可选参数，带默认值
        model = kwargs.get('model', self.model)
        temperature = kwargs.get('temperature', 1.3)

        messages = [
            {"role": "system", "content": self.sys_role},
            {"role": "user", "content": [
                {"type": "text", "text": get_prompt(user_instruction=user_instruction, history=history,
                                                    visible_elements=visible_elements)},
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{_page_info.get('img_base64')}"}}
            ]}
        ]

        completion = self.client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature
        )
        resp = self.parse_llm_output(completion.choices[0].message.content)
        return resp['Thought'], resp['Action']
