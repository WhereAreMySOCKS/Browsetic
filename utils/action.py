from dataclasses import dataclass
from typing import Optional, Tuple, TypeAlias

# 定义类型别名，便于理解
Coordinate: TypeAlias = Tuple[float, float, float, float]
Point: TypeAlias = Tuple[float, float]

@dataclass(frozen=True)
class Action:
    """
    表示用户操作指令的数据类。

    Attributes:
        type: 操作类型，例如 'click', 'drag', 'scroll', 'type', 'hotkey' 等。
        content: 当操作类型为 'type' 时，待输入的文本内容。
        start_box: 用于 'click'、'drag'、'scroll' 操作的区域坐标，格式为 (x1, y1, x2, y2)。
        end_box: 用于 'drag' 操作的结束区域坐标，格式为 (x1, y1, x2, y2)。
        deltas: 用于 'scroll' 操作的滚动偏移量，格式为 (delta_x, delta_y)。
        key: 用于 'hotkey' 操作的按键标识。
    """
    type: str
    content: Optional[str] = None
    start_box: Optional[Coordinate] = None
    end_box: Optional[Coordinate] = None
    deltas: Optional[Tuple[float, float]] = None
    key: Optional[str] = None

    # 定义各操作类型必需的字段
    REQUIRED_FIELDS = {
        'click': ['start_box'],
        'drag': ['start_box', 'end_box'],
        'scroll': ['start_box', 'deltas'],
        'type': ['content'],
        'hotkey': ['key']
    }

    def validate(self) -> None:
        """
        验证当前 Action 实例是否满足其操作类型所需的必填字段。
        若缺少必需字段，则抛出 ValueError 异常。
        """
        if self.type in self.REQUIRED_FIELDS:
            for field in self.REQUIRED_FIELDS[self.type]:
                if getattr(self, field) is None:
                    raise ValueError(f"Action type '{self.type}' requires field '{field}'")

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
        return ((box[0] + box[2]) / 2, (box[1] + box[3]) / 2)
