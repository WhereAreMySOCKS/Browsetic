from dataclasses import dataclass
from typing import Optional, Tuple, TypeAlias, Dict, List, ClassVar

# 定义类型别名，便于理解
Coordinate: TypeAlias = Tuple[float, float, float, float]
Point: TypeAlias = Tuple[float, float]

# 支持的操作类型
ACTION_TYPE = [
    'click', 'left_double', 'right_single', 'drag', 'hotkey', 'type', 'scroll', 'wait', 'finished', 'call_user'
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
        'call_user': []  # call_user 操作不需要额外字段
    }

    def __post_init__(self):
        """初始化 Action 对象，并验证字段是否符合要求"""
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
        if self.content and self.content.endswith('\n'):
            # 去除结尾的换行符
            return self.content.rstrip('\n'), True
        return self.content or '', False

    @staticmethod
    def calculate_center(box: Coordinate) -> Point:
        """
        根据给定的区域坐标 (x1, y1, x2, y2) 计算中心点坐标。
        """
        return (box[0] + box[2]) / 2, (box[1] + box[3]) / 2

    def __repr__(self):
        """返回 Action 对象的字符串表示，便于调试"""
        fields = []
        for field_name in self.REQUIRED_FIELDS.get(self.action_type, []):
            fields.append(f"{field_name}={getattr(self, field_name)}")
        return f"Action(action_type='{self.action_type}', {', '.join(fields)})"


if __name__ == '__main__':
    # 测试用例
    try:
        # 创建一个点击操作
        click_action = Action("click", start_box=(1, 2, 3, 4))
        print(click_action)  # 输出: Action(action_type='click', start_box=(1, 2, 3, 4))

        # 创建一个拖动操作
        drag_action = Action("drag", start_box=(1, 2, 3, 4), end_box=(5, 6, 7, 8))
        print(drag_action)  # 输出: Action(action_type='drag', start_box=(1, 2, 3, 4), end_box=(5, 6, 7, 8))

        # 创建一个输入文本操作
        type_action = Action("type", content="Hello, World!\n")
        print(type_action)  # 输出: Action(action_type='type', content='Hello, World!\n')

        # 测试字段验证
        invalid_action = Action("click")  # 缺少 start_box 字段

        # 测试 parse_content 方法
        content, has_newline = type_action.parse_content()
        print(f"Parsed content: '{content}', has_newline: {has_newline}")  # 输出: Parsed content: 'Hello, World!', has_newline: True

        # 测试 calculate_center 方法
        center = Action.calculate_center((10, 20, 30, 40))
        print(f"Center: {center}")  # 输出: Center: (20.0, 30.0)

    except Exception as e:
        print(f"Error: {e}")
