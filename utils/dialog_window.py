from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QWidget,
                             QLabel, QLineEdit, QTextEdit, QPushButton,
                             QGraphicsDropShadowEffect, QStyle, QMessageBox)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QIcon,  QPixmap, QColor, QPainter

# 系统字体和精确颜色
SYSTEM_FONT = ".AppleSystemUIFont"  # 系统字体
BACKGROUND_COLOR = "#F5F5F7"
BUTTON_BLUE = "#007AFF"
ACCENT_GRAY = "#E5E5EA"

# 风格样式表
DIALOG_STYLE = """
QDialog {
    background-color: """ + BACKGROUND_COLOR + """;
    border-radius: 10px;
}

QLabel {
    color: #000000;
    font-family: """ + SYSTEM_FONT + """;
    font-size: 13px;
}

QLabel[heading=true] {
    font-weight: 500;
    font-size: 13px;
}

QLineEdit, QTextEdit {
    background-color: white;
    border: 1px solid #d0d0d0;
    border-radius: 6px;
    padding: 5px 8px;
    font-family: """ + SYSTEM_FONT + """;
    font-size: 13px;
    selection-background-color: #b2d7ff;
}

QLineEdit:focus, QTextEdit:focus {
    border: 1px solid """ + BUTTON_BLUE + """;
}

QPushButton {
    background-color: #fbfbfb;
    border: 0.5px solid #c0c0c0;
    border-radius: 6px;
    padding: 1px 10px;
    min-width: 67px;
    min-height: 21px;
    font-family: """ + SYSTEM_FONT + """;
    font-size: 14px;
}

QPushButton:hover {
    background-color: #f7f7f7;
}

QPushButton:pressed {
    background-color: #e5e5e5;
}

QPushButton[primary=true] {
    background-color: """ + BUTTON_BLUE + """;
    color: white;
    border: none;
}

QPushButton[primary=true]:hover {
    background-color: #0071e3;
}

QPushButton[primary=true]:pressed {
    background-color: #0068d0;
}
"""


class BaseDialog(QDialog):
    """基础对话框"""

    def __init__(self, title, width=400, height=200):
        super().__init__()
        self.setWindowTitle(title)
        self.resize(width, height)
        self.setStyleSheet(DIALOG_STYLE)

        # 对话框窗口特性
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.WindowStaysOnTopHint)
        self.setWindowModality(Qt.WindowModality.ApplicationModal)

        # 添加窗口阴影效果
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(20)
        shadow.setColor(QColor(0, 0, 0, 50))
        shadow.setOffset(0, 4)
        self.setGraphicsEffect(shadow)

    def paintEvent(self, event):
        """绘制窗口背景和边框"""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # 填充背景
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(BACKGROUND_COLOR))
        painter.drawRoundedRect(self.rect(), 10, 10)

        super().paintEvent(event)


class InputDialog(BaseDialog):

    def __init__(self, title, message, default_text="", multiline=False):
        height = 210 if multiline else 150  # 精确高度
        super().__init__(title, width=420, height=height)

        # 创建布局
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(12)

        # 添加消息标签
        message_label = QLabel(message)
        message_label.setWordWrap(True)
        message_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        message_label.setProperty("heading", True)
        layout.addWidget(message_label)

        # 创建输入框（单行或多行）
        if multiline:
            self.text_input = QTextEdit()
            self.text_input.setText(default_text)
            self.text_input.setMinimumHeight(95)
        else:
            self.text_input = QLineEdit(default_text)
            self.text_input.setMinimumHeight(24)

        self.text_input.setFocus()
        layout.addWidget(self.text_input)

        # 添加按钮区域 - 精确匹配间距
        button_layout = QHBoxLayout()
        button_layout.setContentsMargins(0, 12, 0, 0)
        button_layout.setSpacing(12)

        # 创建取消和确认按钮
        cancel_button = QPushButton("取消")
        cancel_button.setAutoDefault(False)

        ok_button = QPushButton("确定")
        ok_button.setProperty("primary", True)
        ok_button.setDefault(True)

        # 按钮右对齐
        button_layout.addStretch()
        button_layout.addWidget(cancel_button)
        button_layout.addWidget(ok_button)

        layout.addLayout(button_layout)

        # 连接信号
        cancel_button.clicked.connect(self.reject)
        ok_button.clicked.connect(self.accept)

    def get_text(self):
        """获取用户输入的文本"""
        if self.exec() == QDialog.DialogCode.Accepted:
            if isinstance(self.text_input, QTextEdit):
                return self.text_input.toPlainText()
            else:
                return self.text_input.text()
        return None


class CommandInputDialog(BaseDialog):
    """指令输入对话框"""

    def __init__(self, title="添加指令", name_default="", content_default="", icon_path=None):
        # 准确的窗口尺寸
        super().__init__(title, width=440, height=340)

        # 创建布局 - 精确匹配间距
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(16)

        # 指令名称区域
        name_label = QLabel("指令名称")
        name_label.setProperty("heading", True)
        layout.addWidget(name_label)

        self.name_input = QLineEdit(name_default)
        self.name_input.setPlaceholderText("输入一个简短名称")
        self.name_input.setMinimumHeight(28)
        layout.addWidget(self.name_input)

        # 指令内容区域 - 稍微增加间距
        content_label = QLabel("指令内容")
        content_label.setProperty("heading", True)
        layout.addWidget(content_label, 0, Qt.AlignmentFlag.AlignBottom)

        self.content_input = QTextEdit()
        self.content_input.setText(content_default)
        self.content_input.setMinimumHeight(140)

        # 设置占位符文本
        self.content_input.setPlaceholderText(
            "在这里输入指令内容...\n\n例如：\n- 分析最新的三篇文章\n- 总结主要观点\n- 提取关键信息")

        layout.addWidget(self.content_input)

        # 按钮区域 - 精确匹配间距
        button_layout = QHBoxLayout()
        button_layout.setContentsMargins(0, 4, 0, 0)
        button_layout.setSpacing(12)

        cancel_button = QPushButton("取消")
        cancel_button.setAutoDefault(False)

        ok_button = QPushButton("确定")
        ok_button.setProperty("primary", True)
        ok_button.setDefault(True)

        # 按钮右对齐
        button_layout.addStretch()
        button_layout.addWidget(cancel_button)
        button_layout.addWidget(ok_button)

        layout.addLayout(button_layout)

        # 连接信号
        cancel_button.clicked.connect(self.reject)
        ok_button.clicked.connect(self.accept)

        # 默认焦点在名称输入框
        self.name_input.setFocus()

        # 设置窗口图标（如果提供）
        if icon_path:
            self.setWindowIcon(QIcon(icon_path))

    def get_inputs(self):
        """获取用户输入的指令名称和内容"""
        if self.exec() == QDialog.DialogCode.Accepted:
            name = self.name_input.text().strip()
            content = self.content_input.toPlainText().strip()
            return name, content
        return None, None


class ConfirmDialog(BaseDialog):
    """确认对话框"""

    def __init__(self, title, message, icon_path=None):
        super().__init__(title, width=420, height=140)

        # 创建布局
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(12)

        # 创建消息区域
        content_layout = QHBoxLayout()
        content_layout.setSpacing(15)

        # 添加图标（如果提供）
        if icon_path:
            icon_label = QLabel()
            pixmap = QPixmap(icon_path)
            # 确保图标大小合适
            if not pixmap.isNull():
                pixmap = pixmap.scaled(32, 32, Qt.AspectRatioMode.KeepAspectRatio,
                                       Qt.TransformationMode.SmoothTransformation)
                icon_label.setPixmap(pixmap)
                icon_label.setFixedSize(32, 32)
                content_layout.addWidget(icon_label, 0, Qt.AlignmentFlag.AlignTop)
        else:
            # 使用默认警告图标
            icon_label = QLabel()
            style_icon = self.style().standardIcon(QStyle.StandardPixmap.SP_MessageBoxWarning)
            pixmap = style_icon.pixmap(32, 32)
            icon_label.setPixmap(pixmap)
            icon_label.setFixedSize(32, 32)
            content_layout.addWidget(icon_label, 0, Qt.AlignmentFlag.AlignTop)

        # 添加消息文本
        message_label = QLabel(message)
        message_label.setWordWrap(True)
        message_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        content_layout.addWidget(message_label, 1)

        layout.addLayout(content_layout)
        layout.addStretch()

        # 添加按钮区域
        button_layout = QHBoxLayout()
        button_layout.setSpacing(12)

        cancel_button = QPushButton("取消")
        cancel_button.setAutoDefault(False)

        confirm_button = QPushButton("确定")
        confirm_button.setProperty("primary", True)
        confirm_button.setDefault(True)

        # 按钮右对齐
        button_layout.addStretch()
        button_layout.addWidget(cancel_button)
        button_layout.addWidget(confirm_button)

        layout.addLayout(button_layout)

        # 连接信号
        self.is_confirmed = False
        cancel_button.clicked.connect(self.reject)
        confirm_button.clicked.connect(self.accept_confirm)

    def accept_confirm(self):
        """确认按钮点击回调"""
        self.is_confirmed = True
        self.accept()

    def keyPressEvent(self, event):
        """处理键盘事件，支持Enter确定和Escape取消"""
        if event.key() == Qt.Key.Key_Return or event.key() == Qt.Key.Key_Enter:
            self.accept_confirm()
        elif event.key() == Qt.Key.Key_Escape:
            self.reject()
        else:
            super().keyPressEvent(event)


def confirm_dialog(title, message, icon_path=None):
    """显示确认对话框，使用与其他对话框一致的风格"""
    dialog = ConfirmDialog(title, message, icon_path)
    dialog.exec()
    return dialog.is_confirmed