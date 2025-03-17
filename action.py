from dataclasses import dataclass
from typing import Optional, Tuple, TypeAlias, Dict, List, ClassVar

# 定义类型别名，便于理解
Coordinate: TypeAlias = Tuple[float, float, float, float]
Point: TypeAlias = Tuple[float, float]

# 支持的操作类型
ACTION_TYPE = [
    'start', 'click', 'left_double', 'right_single', 'drag', 'hotkey', 'type', 'scroll', 'wait', 'finished', 'call_user'
]


@dataclass
class Action:
    action_type: str
    content: Optional[str] = None
    start_box: Optional[Coordinate] = None
    end_box: Optional[Coordinate] = None
    deltas: Optional[Tuple[float, float]] = None
    key: Optional[str] = None

    # 定义各操作类型必需的字段
    REQUIRED_FIELDS: ClassVar[Dict[str, List[str]]] = {
        'click': ['start_box'],
        'left_double': ['start_box'],
        'right_single': ['start_box'],
        'drag': ['start_box', 'end_box'],
        'scroll': ['start_box', 'deltas'],
        'type': ['content'],
        'hotkey': ['key'],
        'wait': [],  # wait 操作不需要额外字段
        'finished': [],  # finished 操作不需要额外字段
        'call_user': ['message']
    }

    def __init__(self, action_type, params=None):
        """根据传入的字典初始化 Action 对象"""
        # 初始化字段
        if params is None:
            params = {}
        self.action_type = action_type
        self.content = params.get('content', None)
        self.start_box = params.get('start_box', None)
        self.end_box = params.get('end_box', None)
        self.deltas = params.get('deltas', None)
        self.key = params.get('key', None)
        self.message = None

        # 验证字段
        if not self.action_type:
            raise ValueError("action_type is required")
        assert self.action_type in ACTION_TYPE, f"不支持的操作类型: {self.action_type}"
        self.validate()

    def validate(self) -> bool:
        """检查当前 Action 对象是否符合其 type 所要求的字段"""
        required_fields = self.REQUIRED_FIELDS.get(self.action_type, [])
        for field in required_fields:
            if getattr(self, field) is None:
                raise ValueError(f"Action type '{self.action_type}' requires field '{field}' which is not provided.")
        return True

    def parse_content(self) -> Tuple[str, bool]:
        """
        解析 'type' 操作中的文本内容。

        如果内容以换行符结尾，则返回 (content_without_newline, True)；
        否则返回 (content, False)。
        """
        if self.content and self.content.endswith('\\n'):
            # 去除结尾的换行符
            return self.content.rstrip('\\n'), True
        return self.content or '', False

    @staticmethod
    def calculate_center(box: Coordinate) -> Point:
        return (box[0] + box[2]) // 2, (box[1] + box[3]) // 2

    def __repr__(self):
        fields = []
        for field_name in self.REQUIRED_FIELDS.get(self.action_type, []):
            fields.append(f"{field_name}={getattr(self, field_name)}")
        return f"Action(action_type='{self.action_type}', {', '.join(fields)})"
