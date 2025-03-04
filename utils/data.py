import json
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class Data:
    """用户操作指令的数据类"""
    text: str
    html: Optional[str] = None
    js: Optional[str] = None
    screenshot: Optional[bytes] = None

    def to_json(self) -> str:
        """将结构化数据转为 JSON 字符串，不包括二进制截图"""
        return json.dumps({
            'text': self.text,
            'html': self.html,
            'js': self.js
        })

    def to_files(self) -> dict:
        """生成用于 requests 的文件字典，适配 multipart/form-data"""
        files = {'metadata': ('metadata.json', self.to_json(), 'application/json')}
        if self.screenshot:
            files['screenshot'] = ('screenshot.png', self.screenshot, 'image/png')
        return files