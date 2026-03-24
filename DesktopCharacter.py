import sys
import os
import requests
import json
import re
from PyQt6.QtWidgets import (QApplication, QMainWindow, QLabel, QMenu,
                             QLineEdit, QWidget, QVBoxLayout, QGraphicsDropShadowEffect,
                             QScrollArea, QFrame, QSizePolicy, QToolTip, QDialog, QButtonGroup, QRadioButton,
                             QHBoxLayout, QPushButton, QMessageBox, QComboBox, QTextEdit, QFormLayout)
from PyQt6.QtCore import Qt, QPoint, QThread, pyqtSignal, QTimer, QRect, QEvent
from PyQt6.QtGui import QPixmap, QColor, QAction, QPainter, QBrush, QPen, QCursor
# 引入本地 API
from CharacterChat import PetChatCore
from ListenEvent import DesktopMonitor
from AIConfig import prompt_config, DEFAULT_PROMPTS, config

user_name, password = prompt_config.get_user_name_password()
# --- 配置区域 ---
USERNAME = user_name
PASSWORD = password
IMAGE_PATH = "CharacterImage/Qchat.png"

PET_HEIGHT = 300
BUBBLE_OFFSET_X = 20  # 向身体内部的水平缩进
BUBBLE_OFFSET_Y = 20  # 默认垂直位置
BUBBLE_MAX_HEIGHT = 150
SHOW_THINK_BUBBLE = False  # 是否显示思考的气泡
STICKERS_DURATION = 8000  # 表情包显示时间


# ----------------

class AIWorker(QThread):
    """直接调用本地 PetChatCore 生成流的后台线程"""
    token_received = pyqtSignal(str)
    finished = pyqtSignal()
    error = pyqtSignal(str)

    def __init__(self, core_api, user_id, session_id, message):
        super().__init__()
        self.core_api = core_api
        self.user_id = user_id
        self.session_id = session_id
        self.message = message
        self.running = True

    def run(self):
        try:
            # 直接迭代 generator 获取增量文本
            for token in self.core_api.chat_stream(self.user_id, self.session_id, self.message):
                if not self.running: break
                if token:
                    self.token_received.emit(token)
        except Exception as e:
            self.error.emit(str(e))
        finally:
            self.finished.emit()

    def stop(self):
        self.running = False


class CustomDesktopMonitor(DesktopMonitor):
    """继承监听器，将拦截到的结果和实时熵值抛给 PyQt 线程"""

    def __init__(self, trigger_callback, entropy_callback, user_role="用户"):
        super().__init__(role=user_role)
        self.trigger_callback = trigger_callback
        self.entropy_callback = entropy_callback

    def _process_finalized_event(self, event):
        # 先让基类处理事件，这会更新底层 VisualAttentionManager 的状态
        result = super()._process_finalized_event(event)

        # --- 精准提取 VisualAttention.py 中的分数和阈值 ---
        va = getattr(self, 'visual_attention', None)
        if va and hasattr(va, 'entropy_pools'):
            display_data = {}
            current_tag = va.current_tag

            # 顶部显示当前所处环境
            display_data["[当前焦点]"] = f"🎯 {current_tag}"

            # 使用读写锁安全读取数据
            with va.config_lock:
                for tag, score in va.entropy_pools.items():
                    # 排除掉被禁用或为 0 的噪音池
                    if score <= 0:
                        continue

                    # 获取该场景对应的阈值
                    policy = va._get_policy(tag)
                    threshold = policy.get('threshold', 100.0)

                    # 格式化显示：例如 "65.5 / 100.0"
                    if tag == current_tag:
                        display_data[f"▶ {tag}"] = f"{score:.1f} / {threshold}"
                    else:
                        display_data[f"  {tag}"] = f"{score:.1f} / {threshold}"

            self.entropy_callback(display_data)
        else:
            self.entropy_callback({"系统提示": "等待获取 VisualAttentionManager 状态..."})

        # --- 触发多模态对话回调 ---
        if result:
            self.trigger_callback(result)

        return result


class MonitorWorker(QThread):
    def __init__(self, user_role="用户", busy_callback=None):
        super().__init__()
        self.user_role = user_role
        self.busy_callback = busy_callback

    """后台独立监听线程"""
    trigger_signal = pyqtSignal(dict)
    entropy_signal = pyqtSignal(dict)  # 用于传递熵值的信号

    # 用于通知主线程隐藏/显示宠物的信号
    hide_pet_signal = pyqtSignal()
    show_pet_signal = pyqtSignal()

    def run(self):
        self.monitor = CustomDesktopMonitor(
            trigger_callback=self.on_trigger,
            entropy_callback=self.on_entropy,
            user_role=self.user_role
        )

        # 将回调函数绑定到触发器
        self.monitor.before_capture_callback = self.on_before_capture
        self.monitor.after_capture_callback = self.on_after_capture
        self.monitor.busy_check_callback = self.busy_callback  # 绑定给底层的 monitor

        self.monitor.run()

    def on_trigger(self, result):
        self.trigger_signal.emit(result)

    def on_entropy(self, entropy_data):
        self.entropy_signal.emit(entropy_data)  # 通过信号安全地发送给主线程UI

    #  触发隐身信号的方法
    def on_before_capture(self):
        self.hide_pet_signal.emit()

    #  触发显形信号的方法
    def on_after_capture(self):
        self.show_pet_signal.emit()

    def stop(self):
        if hasattr(self, 'monitor'):
            self.monitor.is_running = False
        self.quit()
        self.wait()


class ActiveAIWorker(QThread):
    """专门处理主动触发事件的后台 AI 线程"""
    token_received = pyqtSignal(str)
    finished = pyqtSignal()
    error = pyqtSignal(str)

    def __init__(self, core_api, user_id, session_id, context_text, image_path, user_role="用户"):
        super().__init__()
        self.core_api = core_api
        self.user_id = user_id
        self.session_id = session_id
        self.context_text = context_text
        self.image_path = image_path
        self.running = True
        self.user_role = user_role

    def run(self):
        try:
            for token in self.core_api.active_trigger_stream(self.user_id, self.session_id, self.context_text,
                                                             self.image_path):
                if not self.running: break
                if token:
                    self.token_received.emit(token)
        except Exception as e:
            self.error.emit(str(e))
        finally:
            self.finished.emit()

    def stop(self):
        self.running = False


class SettingsDialog(QDialog):
    """设置面板对话框"""

    def __init__(self, current_use_ollama, parent=None):
        super().__init__(parent)
        self.setWindowTitle("系统设置")
        self.setFixedSize(260, 160)
        # 保持设置面板始终在顶层，不被其他窗口遮挡
        self.setWindowFlags(self.windowFlags() | Qt.WindowType.WindowStaysOnTopHint)

        layout = QVBoxLayout(self)

        self.label = QLabel("选择核心驱动模型:")
        self.label.setStyleSheet("font-family: 'Microsoft YaHei'; font-weight: bold;")
        layout.addWidget(self.label)

        self.btn_group = QButtonGroup(self)

        self.radio_ollama = QRadioButton("本地大模型 (Ollama)")
        self.radio_openai = QRadioButton("云端大模型 (OpenAI/自定义)")
        self.radio_ollama.setStyleSheet("font-family: 'Microsoft YaHei';")
        self.radio_openai.setStyleSheet("font-family: 'Microsoft YaHei';")

        self.btn_group.addButton(self.radio_ollama)
        self.btn_group.addButton(self.radio_openai)

        if current_use_ollama:
            self.radio_ollama.setChecked(True)
        else:
            self.radio_openai.setChecked(True)

        layout.addWidget(self.radio_ollama)
        layout.addWidget(self.radio_openai)

        layout.addSpacing(10)

        btn_layout = QHBoxLayout()
        self.btn_save = QPushButton("保存配置")
        self.btn_cancel = QPushButton("取消")

        btn_style = """
            QPushButton {
                background-color: #f0f0f0; border: 1px solid #ccc;
                border-radius: 4px; padding: 5px; font-family: 'Microsoft YaHei';
            }
            QPushButton:hover { background-color: #e0e0e0; }
        """
        self.btn_save.setStyleSheet(btn_style)
        self.btn_cancel.setStyleSheet(btn_style)

        btn_layout.addWidget(self.btn_save)
        btn_layout.addWidget(self.btn_cancel)
        layout.addLayout(btn_layout)

        self.btn_save.clicked.connect(self.accept)
        self.btn_cancel.clicked.connect(self.reject)

    def is_ollama_selected(self):
        return self.radio_ollama.isChecked()


class EntropyPanelDialog(QDialog):
    """主动触发熵值监控面板"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("主动触发监控 (视觉注意力状态)")
        self.setFixedSize(280, 300)
        # 保持在顶层，不被其他窗口遮挡
        self.setWindowFlags(self.windowFlags() | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool)

        layout = QVBoxLayout(self)

        title_label = QLabel("🧠 实时熵值/关注度状态")
        title_label.setStyleSheet("font-family: 'Microsoft YaHei'; font-weight: bold; font-size: 14px; color: #333;")
        layout.addWidget(title_label)

        # 使用滚动区域展示实时数据
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setStyleSheet(
            "QScrollArea { border: 1px solid #ccc; border-radius: 5px; background: #fafafa; }")

        self.text_display = QLabel("等待底层数据接入...\n(请确保随便进行一些点击或打字)")
        self.text_display.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self.text_display.setStyleSheet(
            "font-family: 'Consolas', 'Microsoft YaHei'; font-size: 12px; color: #555; padding: 5px;")

        self.scroll_area.setWidget(self.text_display)
        layout.addWidget(self.scroll_area)

    def update_data(self, entropy_data: dict):
        """接收后台信号并更新 UI"""
        if not entropy_data:
            return

        lines = []
        for key, value in entropy_data.items():
            # 格式化输出，如果 value 是浮点数则保留两位小数
            if isinstance(value, float):
                lines.append(f"🔸 {key:<12}: {value:.2f}")
            else:
                lines.append(f"🔸 {key:<12}: {value}")

        self.text_display.setText("\n".join(lines))


class PromptSettingsDialog(QDialog):
    """提示词与角色设置对话框"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Prompt 与角色设置")
        self.setFixedSize(400, 500)
        self.setWindowFlags(self.windowFlags() | Qt.WindowType.WindowStaysOnTopHint)

        layout = QVBoxLayout(self)

        # 1. 用户称呼设置
        form_layout = QFormLayout()
        self.role_input = QLineEdit()
        self.role_input.setPlaceholderText("例如：哥哥、姐姐、主人")
        self.role_input.setText(prompt_config.get_user_role())
        form_layout.addRow("AI 对你的称呼:", self.role_input)
        layout.addLayout(form_layout)

        # 2. 模板选择
        layout.addWidget(QLabel("选择预设模板:"))
        self.template_combo = QComboBox()
        self.template_combo.addItems(list(DEFAULT_PROMPTS.keys()))
        current_name = prompt_config.data.get("selected_prompt_name", "温柔妹妹")
        if current_name in DEFAULT_PROMPTS:
            self.template_combo.setCurrentText(current_name)
        layout.addWidget(self.template_combo)

        # 3. 自定义提示词
        layout.addWidget(QLabel("自定义提示词 (留空则使用预设):"))
        self.custom_prompt_edit = QTextEdit()
        self.custom_prompt_edit.setPlaceholderText("在此输入自定义 System Prompt，可使用 {user_role} 占位符")
        self.custom_prompt_edit.setText(prompt_config.data.get("custom_prompt", ""))
        self.custom_prompt_edit.setMaximumHeight(200)
        layout.addWidget(self.custom_prompt_edit)

        # 4. 按钮
        btn_layout = QHBoxLayout()
        self.btn_save = QPushButton("保存并生效")
        self.btn_cancel = QPushButton("取消")
        btn_style = """
            QPushButton {
                background-color: #f0f0f0; border: 1px solid #ccc;
                border-radius: 4px; padding: 5px; font-family: 'Microsoft YaHei';
            }
             QPushButton:hover { background-color: #e0e0e0; }
         """
        self.btn_save.setStyleSheet(btn_style)
        self.btn_cancel.setStyleSheet(btn_style)

        btn_layout.addWidget(self.btn_save)
        btn_layout.addWidget(self.btn_cancel)
        layout.addLayout(btn_layout)

        self.btn_save.clicked.connect(self.accept)
        self.btn_cancel.clicked.connect(self.reject)

    def get_config(self):
        return {
            "role": self.role_input.text().strip() or "哥哥",
            "template_name": self.template_combo.currentText(),
            "custom_prompt": self.custom_prompt_edit.toPlainText().strip()
        }


class BubbleWindow(QWidget):
    """气泡窗口 - 支持路径点击复制和自动换行"""

    def __init__(self, parent=None, bg_color=QColor(255, 255, 255, 240), text_color="#333", border_style="solid"):
        super().__init__(parent)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Tool | Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(15, 15, 15, 15)

        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll_area.viewport().setStyleSheet("background: transparent;")
        self.scroll_area.setStyleSheet("""
            QScrollArea { background: transparent; border: none; }
            QScrollBar:vertical { width: 4px; background: transparent; }
            QScrollBar::handle:vertical { background: rgba(0,0,0,0.2); border-radius: 2px; }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0px; }
        """)

        self.label = QLabel(" ")
        self.label.setWordWrap(True)
        self.label.setTextFormat(Qt.TextFormat.MarkdownText)
        self.label.setStyleSheet(f"""
            QLabel {{
                color: {text_color};
                font-family: 'Microsoft YaHei';
                font-size: 14px;
                background: transparent;
                word-wrap: break-word; 
                white-space: pre-wrap;
            }}
        """)
        self.scroll_area.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.label.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self.label.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)

        # 处理超链接点击
        self.label.setOpenExternalLinks(False)  # 阻止自动打开链接
        self.label.linkActivated.connect(self.on_link_activated)
        # =================================

        self.scroll_area.setWidget(self.label)
        self.main_layout.addWidget(self.scroll_area)

        self.bg_color = bg_color
        self.border_style = border_style

        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(10)
        shadow.setColor(QColor(0, 0, 0, 60))
        shadow.setOffset(2, 2)
        self.setGraphicsEffect(shadow)
        self.hide()

    # 链接点击回调函数
    def on_link_activated(self, link):
        if link.startswith("copy:"):
            # 提取路径，并将可能存在的双斜杠还原为单斜杠
            path = link[5:].replace("\\\\", "\\")
            # 写入剪贴板
            QApplication.clipboard().setText(path)
            # 弹出小提示
            QToolTip.showText(QCursor.pos(), f"✅ 路径已复制到剪贴板:\n{path}")
        else:
            # 遇到常规 http 网页链接，使用系统默认浏览器打开
            import webbrowser
            webbrowser.open(link)

    def update_text(self, text):
        if not text or not text.strip():
            self.label.setText(" ")
            self.hide()
            return

        # ====== 通过正则拦截路径，替换为高亮 HTML 链接 ======
        # 匹配 Windows 盘符路径，支持被反引号包裹，过滤掉多余的标点符号
        # 兼容 E:\xxx 和 E:\\xxx 的写法
        pattern = r'`?([a-zA-Z]:(?:\\\\|\\)[^`\*\n"\'\<\>\|\?]+)`?'

        def repl(match):
            raw_path = match.group(1).strip()
            # 移除末尾可能会匹配进去的标点
            while raw_path and raw_path[-1] in ['.', ',', '!', '。', '，', ';']:
                raw_path = raw_path[:-1]

            # 【关键修改】：为显示的路径在每个斜杠后插入零宽空格（&#8203;），强制 Qt 允许换行
            # 注意：这只改变显示的文本，不改变 href 里实际要复制的 raw_path
            display_path = raw_path.replace("\\", "\\&#8203;").replace("/", "/&#8203;")

            # 用 a 标签包裹：href 保持纯净的 raw_path，中间显示的文本使用 display_path
            return f'<a href="copy:{raw_path}" style="color: #0078D7; text-decoration: underline; font-weight: bold;">{display_path}</a>'

        processed_text = re.sub(pattern, repl, text)
        # ========================================================

        # 启用 Markdown 渲染并将处理后的文本塞入
        self.label.setTextFormat(Qt.TextFormat.MarkdownText)
        self.label.setText(processed_text)

        # 先让 label 根据内容计算理想大小
        self.label.adjustSize()

        # 获取内容尺寸
        content_width = self.label.sizeHint().width()
        content_height = self.label.sizeHint().height()

        max_bubble_width = 400
        min_bubble_width = 100

        bubble_width = min(max(content_width + 40, min_bubble_width), max_bubble_width)
        self.setFixedWidth(bubble_width)

        self.label.setMaximumWidth(bubble_width - 35)
        self.label.adjustSize()

        content_height = self.label.height() + 30
        self.setFixedHeight(min(content_height, BUBBLE_MAX_HEIGHT))

        self.show()

        vbar = self.scroll_area.verticalScrollBar()
        if vbar:
            # 使用 QTimer.singleShot 确保在 Qt 完成布局计算后，再执行一次滚动到底部
            QTimer.singleShot(10, lambda: vbar.setValue(vbar.maximum()))

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setBrush(QBrush(self.bg_color))

        pen = QPen(QColor("#888"))
        pen.setWidth(2)
        if self.border_style == "dashed":
            pen.setStyle(Qt.PenStyle.DashLine)
            pen.setColor(QColor("#aaa"))
        else:
            pen.setStyle(Qt.PenStyle.SolidLine)

        painter.setPen(pen)
        rect = self.rect().adjusted(2, 2, -2, -2)
        painter.drawRoundedRect(rect, 15, 15)


class InputWindow(QWidget):
    send_signal = pyqtSignal(str)
    visibility_changed = pyqtSignal(bool)  # 可见性变化信号

    def __init__(self):
        super().__init__()
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Tool | Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        # 新增：发送状态标志
        self.is_sending = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)

        self.text_field = QLineEdit()
        self.text_field.setPlaceholderText("想和我说什么？(回车发送)")
        self.text_field.setStyleSheet("""
            QLineEdit {
                background-color: transparent; border: none; color: #333;
                font-family: "Microsoft YaHei"; font-size: 14px;
            }
        """)
        self.text_field.returnPressed.connect(self.on_submit)
        layout.addWidget(self.text_field)
        self.setFixedSize(220, 50)

        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(10)
        shadow.setColor(QColor(0, 0, 0, 80))
        shadow.setOffset(2, 2)
        self.setGraphicsEffect(shadow)

    def changeEvent(self, event):
        # 全局监听窗口激活状态
        # 检测窗口激活状态的变化
        if event.type() == QEvent.Type.ActivationChange:
            # 如果当前窗口不再是激活窗口 (说明用户点击了别的软件、桌面、或宠物本体)
            if not self.isActiveWindow() and self.isVisible():
                # 为了防止发送中途被隐藏，加个状态判断
                if not self.is_sending:
                    self.hide()
                    self.reset_sending_state()
        super().changeEvent(event)

    def on_submit(self):
        text = self.text_field.text().strip()
        if text and not self.is_sending:
            # 不清空、不隐藏，只设置发送状态
            self.is_sending = True
            self.text_field.clear()
            self.send_signal.emit(text)

    # 新增：重置发送状态的方法
    def reset_sending_state(self):
        self.is_sending = False

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setBrush(QBrush(QColor(255, 255, 255, 240)))
        painter.setPen(QPen(QColor("#aaa"), 1))
        rect = self.rect().adjusted(5, 5, -5, 5)
        painter.drawRoundedRect(rect, 20, 20)

    # 重写显示和隐藏事件，向外同步状态
    def showEvent(self, event):
        super().showEvent(event)
        self.visibility_changed.emit(True)

    def hideEvent(self, event):
        super().hideEvent(event)
        self.visibility_changed.emit(False)


class ImageBubbleWindow(QWidget):
    """表情包专属气泡窗口"""

    def __init__(self, parent=None, bg_color=QColor(255, 255, 255, 240)):
        super().__init__(parent)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Tool | Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(10, 10, 10, 10)

        self.image_label = QLabel(self)
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.main_layout.addWidget(self.image_label)

        self.bg_color = bg_color

        # 阴影效果
        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(10)
        shadow.setColor(QColor(0, 0, 0, 60))
        shadow.setOffset(2, 2)
        self.setGraphicsEffect(shadow)

        # 5秒自动隐藏定时器
        self.hide_timer = QTimer(self)
        self.hide_timer.setSingleShot(True)
        self.hide_timer.timeout.connect(self.hide)

        self.hide()

    def show_image(self, image_path, duration=5000):
        # 【1. 停止定时器】
        self.hide_timer.stop()

        # 【2. 加载新图】
        pixmap = QPixmap()
        success = pixmap.load(image_path)

        if not success or pixmap.isNull():
            print(f"[UI 拦截] ❌ 表情包加载失败或损坏，放弃渲染：{image_path}")
            self.hide()
            return

        print(f"[UI 拦截] ✅ 成功渲染表情包：{image_path}")

        max_width = 160
        if pixmap.width() > max_width:
            pixmap = pixmap.scaledToWidth(max_width, Qt.TransformationMode.SmoothTransformation)

        # 【3. 核心修复：先清空再设置，强制刷新】
        # 关键：先 clear() 确保旧图被清除
        self.image_label.clear()
        # QApplication.processEvents()  # 处理 pending 事件，确保 clear 生效
        self.repaint()

        # 设置新图
        self.image_label.setPixmap(pixmap)
        self.image_label.adjustSize()

        # 【4. 强制刷新窗口 - 关键步骤】
        # 无论窗口是否可见，都先隐藏再显示，强制 Qt 重绘整个窗口内容
        was_visible = self.isVisible()
        self.hide()
        # QApplication.processEvents()  # 确保隐藏事件处理完成
        self.repaint()

        # 设置新尺寸（即使相同也要重新设置）
        self.setFixedSize(pixmap.width() + 20, pixmap.height() + 20)

        # 显示并置顶
        self.show()
        self.raise_()
        self.activateWindow()
        # QApplication.processEvents()  # 确保显示事件处理完成
        self.repaint()

        # 强制重绘
        self.image_label.repaint()
        self.repaint()

        # 【5. 重新开始计时】
        self.hide_timer.setSingleShot(True)
        self.hide_timer.start(duration)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setBrush(QBrush(self.bg_color))
        painter.setPen(QPen(QColor("#888"), 2))
        rect = self.rect().adjusted(2, 2, -2, -2)
        painter.drawRoundedRect(rect, 15, 15)


class DesktopPet(QMainWindow):
    def __init__(self, user_role=None):
        super().__init__()
        # 如果未指定角色，从配置加载
        if user_role is None:
            user_role = prompt_config.get_user_role()

        # 初始化底层 Core
        self.core_api = PetChatCore(user_role=user_role)
        self.user_id = None
        self.chat_session_id = None
        self.buffer_text = ""
        self.is_thinking = False
        self.worker = None
        self.debug_mode = False
        self.current_use_ollama = config.use_ollama
        self.is_active_triggering = False
        self.show_think_bubble = SHOW_THINK_BUBBLE  # 读取思考气泡显示配置

        # --- 动态隐藏时间配置 ---
        self.hide_time_base = 8000  # 基础停留时间 (毫秒)
        self.hide_time_per_char = 200  # 每个字符增加的时间 (毫秒)
        self.hide_time_max = 120000  # 最大停留时间 (毫秒)

        # 新增：流式处理相关属性
        self.raw_buffer = ""  # 原始字符缓冲区
        self.paused = False  # 是否暂停输出
        self.pause_timer = QTimer()  # 暂停定时器
        self.pause_timer.setSingleShot(True)
        self.pause_timer.timeout.connect(self.resume_processing)
        self.pause_duration = 800  # 表情包展示暂停时间（毫秒）

        self.is_user_interacting = False  # 记录输入框是否激活

        self.init_ui()
        # 初始化监听线程
        self.monitor_thread = MonitorWorker(user_role=user_role, busy_callback=self.check_pet_busy)
        self.monitor_thread.trigger_signal.connect(self.handle_active_trigger)

        # 连接截图隐藏/显示信号
        self.monitor_thread.hide_pet_signal.connect(self.on_capture_hide)
        self.monitor_thread.show_pet_signal.connect(self.on_capture_show)

        # Timer setup
        self.online_hide_timer = QTimer()
        self.online_hide_timer.setSingleShot(True)
        self.online_hide_timer.timeout.connect(self.hide_reply_bubble)

        self.reply_hide_timer = QTimer()
        self.reply_hide_timer.setSingleShot(True)
        self.reply_hide_timer.timeout.connect(self.hide_reply_bubble)

        QTimer.singleShot(100, self.login_and_init_chat)

    def set_interaction_state(self, state):
        self.is_user_interacting = state

    def check_pet_busy(self):
        """提供给后台线程：检测宠物是否处于交互或忙碌状态"""
        is_worker_running = self.worker is not None and self.worker.isRunning()
        # 如果输入框显示着，或者 AI 正在思考/生成内容，都视为正在交互
        return self.is_user_interacting or self.is_thinking or is_worker_running

    def on_capture_hide(self):
        """截图前将所有组件设置为完全透明，防止失去焦点或被截取"""
        self.setWindowOpacity(0.0)
        self.reply_bubble.setWindowOpacity(0.0)
        self.think_bubble.setWindowOpacity(0.0)
        self.image_bubble.setWindowOpacity(0.0)
        self.input_window.setWindowOpacity(0.0)
        self.entropy_panel.setWindowOpacity(0.0)
        # 强制 Qt 立即重绘，确保在 time.sleep 的 0.15 秒内应用透明度
        # QApplication.processEvents()
        self.repaint()

    def on_capture_show(self):
        """截图后恢复所有组件的透明度"""
        self.setWindowOpacity(1.0)
        self.reply_bubble.setWindowOpacity(1.0)
        self.think_bubble.setWindowOpacity(1.0)
        self.image_bubble.setWindowOpacity(1.0)
        self.input_window.setWindowOpacity(1.0)
        self.entropy_panel.setWindowOpacity(1.0)
        # QApplication.processEvents()
        self.repaint()

    def hide_reply_bubble(self):
        """统一隐藏回复气泡的函数"""
        self.reply_bubble.update_text("")

    # 清空记忆功能
    def clear_memory(self):
        """清空当前会话记忆，创建新会话"""
        if not self.user_id or not self.chat_session_id:
            QMessageBox.warning(self, "系统提示", "尚未登录或会话未初始化，无法清空记忆。")
            return

        # 确认对话框
        reply = QMessageBox.question(
            self,
            "确认清空记忆",
            "确定要清空当前对话记忆吗？\n这将删除当前会话并创建新会话。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )

        if reply != QMessageBox.StandardButton.Yes:
            return

        try:
            # 1. 记录旧会话 ID
            old_session_id = self.chat_session_id

            # 2. 创建新会话获取新 ID
            new_session_id = self.core_api.memory_manager.create_session(self.user_id,
                                                                         self.core_api.ll_model,
                                                                         chat_type="pet_chat")

            if new_session_id:
                # 3. 删除旧会话
                self.core_api.memory_manager.delete_session(self.user_id, old_session_id, "hard", "pet_chat")

                # 4. 更新当前会话 ID
                self.chat_session_id = new_session_id

                # 5. 提示用户
                self.reply_bubble.update_text("✨ 记忆已清空，我们重新开始吧！")
                self.online_hide_timer.start(3000)
                self.update_bubble_positions()

                print(f"[Memory] Cleared old session: {old_session_id}, New session: {new_session_id}")
            else:
                QMessageBox.critical(self, "错误", "创建新会话失败，请稍后重试。")

        except Exception as e:
            QMessageBox.critical(self, "错误", f"清空记忆失败：{e}")
            print(f"[Error] Clear memory failed: {e}")

    # 计算动态隐藏时间的方法
    def get_dynamic_hide_time(self, text):
        if not text:
            return self.hide_time_base
        length = len(text.strip())
        # 公式：基础时间 + (字符数 * 单字耗时)
        calculated_time = self.hide_time_base + (length * self.hide_time_per_char)
        # 限制最大时间
        return min(calculated_time, self.hide_time_max)

    def init_ui(self):
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        self.layout = QVBoxLayout(self.central_widget)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(0)

        self.image_label = QLabel(self)
        original_pixmap = QPixmap(IMAGE_PATH)
        if original_pixmap.isNull():
            scaled_pixmap = QPixmap(100, 100)
            scaled_pixmap.fill(QColor("red"))
        else:
            scaled_pixmap = original_pixmap.scaledToHeight(PET_HEIGHT, Qt.TransformationMode.SmoothTransformation)
        self.image_label.setPixmap(scaled_pixmap)
        self.layout.addWidget(self.image_label)
        self.setFixedSize(scaled_pixmap.width(), scaled_pixmap.height())

        self.reply_bubble = BubbleWindow(None, bg_color=QColor(255, 255, 255, 240), text_color="#000")
        self.reply_bubble.setMaximumWidth(1200)  # 设置一个合理的最大宽度

        self.think_bubble = BubbleWindow(None, bg_color=QColor(240, 240, 240, 230), text_color="#666",
                                         border_style="dashed")
        self.think_bubble.setMaximumWidth(800)

        # 初始化表情气泡
        self.image_bubble = ImageBubbleWindow(None)

        self.input_window = InputWindow()
        self.input_window.send_signal.connect(self.handle_input_text)
        # 监听输入框的显示和隐藏
        self.input_window.visibility_changed.connect(self.set_interaction_state)
        # --- 初始化熵值监控面板 ---
        self.entropy_panel = EntropyPanelDialog(self)
        self.entropy_panel.hide()  # 默认隐藏

        screen = QApplication.primaryScreen().geometry()
        # 初始位置改为左下角 (100, screen.height() - 300)
        self.move(100, screen.height() - 300)

    def update_bubble_positions(self):
        pet_geo = self.geometry()
        screen_rect = QApplication.primaryScreen().availableGeometry()

        right_space = screen_rect.right() - pet_geo.right()
        left_space = pet_geo.left() - screen_rect.left()

        reply_w = self.reply_bubble.width()
        think_w = self.think_bubble.width()
        image_w = self.image_bubble.width() if self.image_bubble.isVisible() else 0

        MODE_SPLIT = 0
        MODE_ALL_LEFT = 1
        MODE_ALL_RIGHT = 2

        layout_mode = MODE_SPLIT
        if right_space < max(reply_w, image_w):
            layout_mode = MODE_ALL_LEFT
        elif left_space < think_w:
            layout_mode = MODE_ALL_RIGHT

        # --- 1. Think Bubble (思考气泡位置保持原样) ---
        tx, ty = 0, 0
        if self.think_bubble.isVisible():
            t_h = self.think_bubble.height()
            if layout_mode == MODE_ALL_RIGHT:
                tx = pet_geo.right() - BUBBLE_OFFSET_X
            else:
                tx = pet_geo.left() - think_w + BUBBLE_OFFSET_X
            ty = pet_geo.top() - t_h + 50
            if ty < screen_rect.top(): ty = screen_rect.top() + 5
            self.think_bubble.move(int(tx), int(ty))

        # --- 2. 新增：Image Bubble (表情气泡布局) ---
        ix, iy = 0, 0
        if self.image_bubble.isVisible():
            i_h = self.image_bubble.height()
            i_w = self.image_bubble.width()

            # X 坐标：跟回复气泡保持同一侧
            if layout_mode == MODE_ALL_LEFT:
                ix = pet_geo.left() - i_w + BUBBLE_OFFSET_X
            else:
                ix = pet_geo.right() - BUBBLE_OFFSET_X

            # Y 坐标：如果在同一侧且有思考气泡，排在思考气泡下面；否则在宠物上方对齐
            if (layout_mode != MODE_SPLIT) and self.think_bubble.isVisible():
                iy = self.think_bubble.geometry().bottom() + 10
            else:
                iy = pet_geo.top() - i_h + BUBBLE_OFFSET_Y

            if iy < screen_rect.top(): iy = screen_rect.top() + 5
            self.image_bubble.move(int(ix), int(iy))

        # --- 3. Reply Bubble (回复气泡布局修改) ---
        rx, ry = 0, 0
        if self.reply_bubble.isVisible():
            r_h = self.reply_bubble.height()

            if layout_mode == MODE_ALL_LEFT:
                rx = pet_geo.left() - reply_w + BUBBLE_OFFSET_X
            else:
                rx = pet_geo.right() - BUBBLE_OFFSET_X

            # Y 坐标：优先排在表情气泡下方，其次是思考气泡下方
            if self.image_bubble.isVisible():
                ry = self.image_bubble.geometry().bottom() + 10
            elif (layout_mode != MODE_SPLIT) and self.think_bubble.isVisible():
                ry = self.think_bubble.geometry().bottom() + 10
            else:
                ry = pet_geo.top() - r_h + BUBBLE_OFFSET_Y

            if ry < screen_rect.top(): ry = screen_rect.top() + 5
            if ry + r_h > screen_rect.bottom(): ry = screen_rect.bottom() - r_h - 5

            self.reply_bubble.move(int(rx), int(ry))

        if self.input_window.isVisible():
            self.update_input_position()

    def update_input_position(self):
        pet_geo = self.geometry()
        in_geo = self.input_window.geometry()
        screen_rect = QApplication.primaryScreen().availableGeometry()

        x = pet_geo.center().x() - (in_geo.width() // 2)
        y = pet_geo.bottom() + 10

        if x < screen_rect.left(): x = screen_rect.left()
        if x + in_geo.width() > screen_rect.right(): x = screen_rect.right() - in_geo.width()
        if y + in_geo.height() > screen_rect.bottom():
            y = pet_geo.top() - in_geo.height() - 10
        self.input_window.move(int(x), int(y))

    def handle_input_text(self, text):
        if not text or not self.chat_session_id:
            return

        if self.online_hide_timer.isActive():
            self.online_hide_timer.stop()
        if self.reply_hide_timer.isActive():
            self.reply_hide_timer.stop()

        self.think_bubble.update_text("")
        self.think_bubble.hide()
        self.image_bubble.hide()  # 新对话时隐藏表情包
        self.image_bubble.image_label.clear()

        self.buffer_text = ""
        self.current_reply_text = ""
        self.current_think_text = ""
        self.is_thinking = False

        # --- 用户主动聊天时，保持原有"..."即时反馈 ---
        self.is_active_triggering = False  # 确保重置

        self.raw_buffer = ""
        if self.pause_timer.isActive():
            self.pause_timer.stop()
        self.paused = False

        self.reply_bubble.update_text("嗯...")
        self.update_bubble_positions()

        # 启动处理线程
        self.worker = AIWorker(
            self.core_api,
            self.user_id,
            self.chat_session_id,
            text
        )
        self.worker.token_received.connect(self.on_ai_token)
        self.worker.finished.connect(self.on_ai_finished)
        self.worker.start()

        # AI 处理完成后重置输入框发送状态
        self.worker.finished.connect(self.input_window.reset_sending_state)

    def handle_active_trigger(self, packet):
        """处理来自 ListenEvent 线程的主动触发信号"""
        if not self.chat_session_id:
            return

        # 为了不打断用户主动和宠物的聊天，如果它正在思考，则忽略此次环境触发
        if self.is_thinking or (self.worker and self.worker.isRunning()):
            return

        text_context = packet.get("text", "")
        image_path = packet.get("image", None)

        if self.online_hide_timer.isActive():
            self.online_hide_timer.stop()
        if self.reply_hide_timer.isActive():
            self.reply_hide_timer.stop()

        self.think_bubble.update_text("")
        self.think_bubble.hide()
        self.image_bubble.hide()  # 新对话时隐藏表情包
        self.image_bubble.image_label.clear()

        self.buffer_text = ""
        self.current_reply_text = ""
        self.current_think_text = ""
        self.is_thinking = False

        # --- 隐藏气泡，等待正式回复 ---
        self.reply_bubble.hide()

        # --- 标记为主动触发状态 ---
        self.is_active_triggering = True
        self.raw_buffer = ""
        if self.pause_timer.isActive():
            self.pause_timer.stop()
        self.paused = False

        # 启动主动处理的 AI 线程
        self.worker = ActiveAIWorker(
            self.core_api,
            self.user_id,
            self.chat_session_id,
            text_context,
            image_path
        )
        self.worker.token_received.connect(self.on_ai_token)
        self.worker.finished.connect(self.on_ai_finished)
        self.worker.start()

    def login_and_init_chat(self):
        try:
            # 接收返回的 用户 ID 和持久化记录的模型模式
            self.user_id, model_mode = self.core_api.login(USERNAME, PASSWORD)

            if self.user_id:
                # 0 为 Ollama, 1 为 OpenAI
                self.current_use_ollama = (model_mode == 0)

                self.chat_session_id = self.core_api.init_session(self.user_id)
                self.reply_bubble.update_text("你回来了，我好想你！")
                self.online_hide_timer.start(2000)
                # 登录成功且建立会话后，启动监听器
                if not self.monitor_thread.isRunning():
                    # 连接触发信号
                    self.monitor_thread.trigger_signal.connect(self.handle_active_trigger)
                    # 连接熵值刷新信号
                    self.monitor_thread.entropy_signal.connect(self.entropy_panel.update_data)
                    self.monitor_thread.start()
            else:
                self.reply_bubble.update_text("登录失败，请检查账号密码。")
                self.online_hide_timer.start(3000)

        except Exception as e:
            print(f"Init Error: {e}")
            self.reply_bubble.update_text(f"初始化错误：{e}")
            self.online_hide_timer.start(3000)

        self.update_bubble_positions()

    def on_ai_token(self, token):
        """接收 AI 流式输出的一个片段"""
        if self.paused:
            # 暂停期间只追加到缓冲区，不处理
            self.raw_buffer += token
            return

        # 正常状态下，将新 token 加入缓冲区并尝试处理
        self.raw_buffer += token
        self.process_raw_buffer()

    def process_raw_buffer(self):
        """从 raw_buffer 中提取完整标签和安全文本，更新 UI"""
        if self.paused:
            return  # 暂停中不处理

        # 定义标签正则（增强容错性）
        think_start_pattern = r'<think>'
        think_end_pattern = r'</think>'

        # 表情包正则：支持 <$...$>、<$...>、<...$>、<...图片后缀>
        # \$? 表示 $ 可选，([^>$]*?) 捕获中间内容，\$? 表示结尾 $ 可选
        emoji_pattern = r'<\$?([^>$]*?)\$?>'
        # 图片后缀正则（不区分大小写）
        image_suffix_pattern = r'<[^>]*\.(png|jpg|jpeg|gif|bmp|webp)>'

        import re

        # 循环处理，直到 buffer 中没有完整标签或触发暂停
        while True:
            # 寻找第一个 '>' 作为标签结束符
            end_pos = self.raw_buffer.find('>')
            if end_pos == -1:
                # 没有 '>'，检查是否有 '<' 作为潜在标签前缀
                last_lt = self.raw_buffer.rfind('<')
                if last_lt != -1:
                    # '<' 之前的是安全文本
                    safe_part = self.raw_buffer[:last_lt]
                    if safe_part:
                        if self.is_thinking:
                            self.current_think_text += safe_part
                        else:
                            self.current_reply_text += safe_part
                        self._update_bubbles()
                    # 保留从 '<' 开始的部分等待完整标签
                    self.raw_buffer = self.raw_buffer[last_lt:]
                else:
                    # 没有 '<'，整个 buffer 都是安全文本
                    if self.raw_buffer:
                        if self.is_thinking:
                            self.current_think_text += self.raw_buffer
                        else:
                            self.current_reply_text += self.raw_buffer
                        self._update_bubbles()
                        self.raw_buffer = ""
                break  # 退出循环

            # 找到 '>' 后，寻找它前面最近的 '<'
            start_pos = self.raw_buffer.rfind('<', 0, end_pos + 1)

            if start_pos == -1:
                # 有 '>' 但没有 '<'，说明 '>' 之前都是安全文本
                safe_text = self.raw_buffer[:end_pos + 1]
                if self.is_thinking:
                    self.current_think_text += safe_text
                else:
                    self.current_reply_text += safe_text
                self._update_bubbles()
                self.raw_buffer = self.raw_buffer[end_pos + 1:]
                continue

            # 提取候选标签内容 <...>
            candidate_tag = self.raw_buffer[start_pos:end_pos + 1]
            safe_before_tag = self.raw_buffer[:start_pos]

            # 输出标签前的安全文本
            if safe_before_tag:
                if self.is_thinking:
                    self.current_think_text += safe_before_tag
                else:
                    self.current_reply_text += safe_before_tag
                self._update_bubbles()

            # 判断候选标签是否匹配已知标签类型
            matched = False

            # 检查 think 开始标签
            if re.fullmatch(think_start_pattern, candidate_tag, flags=re.IGNORECASE):
                self.is_thinking = True
                matched = True
            # 检查 think 结束标签
            elif re.fullmatch(think_end_pattern, candidate_tag, flags=re.IGNORECASE):
                self.is_thinking = False
                matched = True
            # 检查表情包标签（增强容错：支持 $ 缺失或单侧）
            elif re.fullmatch(emoji_pattern, candidate_tag, flags=re.IGNORECASE):
                m = re.fullmatch(emoji_pattern, candidate_tag, flags=re.IGNORECASE)
                if m:
                    emoji_content = m.group(1).strip()
                    # 额外检查：如果是图片路径格式，也接受
                    if not emoji_content and re.fullmatch(image_suffix_pattern, candidate_tag, flags=re.IGNORECASE):
                        # 从 <...图片后缀> 中提取路径
                        emoji_content = candidate_tag[1:-1].strip()  # 去掉 < 和 >

                    if emoji_content:
                        self.show_sticker(emoji_content)
                        self.paused = True
                        self.pause_timer.start(self.pause_duration)
                        matched = True
                        # 移除已处理的标签部分
                        self.raw_buffer = self.raw_buffer[end_pos + 1:]
                        return  # 暂停后返回，等待 resume_processing

            if matched:
                # 已知标签，从 buffer 中移除
                self.raw_buffer = self.raw_buffer[end_pos + 1:]
            else:
                # 未知标签（如 <br>、<$...> 但不符合表情包规则等），当作普通文本输出
                if self.is_thinking:
                    self.current_think_text += candidate_tag
                else:
                    self.current_reply_text += candidate_tag
                self._update_bubbles()
                self.raw_buffer = self.raw_buffer[end_pos + 1:]

    def _update_bubbles(self):
        """更新气泡显示（从 current_reply_text 和 current_think_text 刷新 UI）"""
        # 清理回复文本中的残留表情包标签（保险）
        clean_reply = self.current_reply_text.strip()
        if clean_reply:
            self.reply_bubble.update_text(clean_reply)
        else:
            self.reply_bubble.hide()

        # 思考气泡
        if self.show_think_bubble and self.current_think_text.strip():
            self.think_bubble.update_text(self.current_think_text)
        else:
            self.think_bubble.hide()

        # 更新所有气泡位置
        self.update_bubble_positions()

    def resume_processing(self):
        """暂停结束后恢复处理缓冲区"""
        self.paused = False
        self.process_raw_buffer()

    def toggle_input(self):
        if self.input_window.isVisible():
            self.input_window.hide()
        else:
            self.input_window.show()
            self.update_input_position()
            self.input_window.text_field.setFocus()

    def open_settings(self):
        """打开设置菜单进行模型配置"""
        if not self.user_id:
            QMessageBox.warning(self, "系统提示", "网络较慢，请等待身份加载完毕。")
            return

        dialog = SettingsDialog(self.current_use_ollama, self)

        # 居中显示
        pet_geo = self.geometry()
        dialog.move(pet_geo.center().x() - dialog.width() // 2, pet_geo.center().y() - dialog.height() // 2)

        if dialog.exec() == QDialog.DialogCode.Accepted:
            new_use_ollama = dialog.is_ollama_selected()
            if new_use_ollama != self.current_use_ollama:
                try:
                    # 调用数据层执行更新，并重新实例化 LLModel 核心
                    self.core_api.update_user_model_mode(self.user_id, new_use_ollama)
                    self.current_use_ollama = new_use_ollama

                    model_str = "本地大模型 (Ollama)" if self.current_use_ollama else "云端大模型 (OpenAI)"
                    self.reply_bubble.update_text(f"已切换为 {model_str} 驱动！")
                    self.online_hide_timer.start(3000)
                    self.update_bubble_positions()
                except Exception as e:
                    QMessageBox.critical(self, "错误", f"保存设置失败：{e}")

    def open_prompt_settings(self):
        """打开提示词与角色设置菜单"""
        dialog = PromptSettingsDialog(self)
        pet_geo = self.geometry()
        dialog.move(pet_geo.center().x() - dialog.width() // 2, pet_geo.center().y() - dialog.height() // 2)

        if dialog.exec() == QDialog.DialogCode.Accepted:
            config_data = dialog.get_config()
            try:
                # 保存配置到 JSON
                prompt_config.update_config(
                    config_data["template_name"],
                    config_data["custom_prompt"],
                    config_data["role"]
                )
                # 更新 Core 中的运行时配置
                self.core_api.update_role_and_prompt(
                    config_data["role"],
                    config_data["custom_prompt"] if config_data["custom_prompt"] else None
                )
                # 更新监听器中的角色 (用于主动触发)
                # 注意：MonitorWorker 已在 init 时传入，若要实时生效需重启或动态更新，此处简化处理
                self.reply_bubble.update_text(f"设置已生效！现在称呼您为：{config_data['role']}")
                self.online_hide_timer.start(3000)
            except Exception as e:
                QMessageBox.critical(self, "错误", f"保存 Prompt 配置失败：{e}")

    def moveEvent(self, event):
        super().moveEvent(event)
        self.update_bubble_positions()

    def paintEvent(self, event):
        if self.debug_mode:
            painter = QPainter(self)
            painter.setPen(QPen(Qt.GlobalColor.red, 2, Qt.PenStyle.DashLine))
            painter.drawRect(self.rect().adjusted(1, 1, -1, -1))
        super().paintEvent(event)

    def contextMenuEvent(self, event):
        menu = QMenu(self)
        menu.addAction("聊天", self.toggle_input)
        # --- 添加设置按钮 ---
        menu.addAction("模型设置", self.open_settings)
        menu.addAction("Prompt 设置", self.open_prompt_settings)  # 新增
        menu.addAction("数据监控", self.toggle_entropy_panel)

        # 新增：清空记忆菜单项
        menu.addSeparator()
        menu.addAction("清空记忆", self.clear_memory)

        menu.addSeparator()  # 分割线

        action_debug = QAction("调试模式", self)
        action_debug.setCheckable(True)
        action_debug.setChecked(self.debug_mode)
        action_debug.triggered.connect(self.toggle_debug)
        menu.addAction(action_debug)
        menu.addAction("退出", self.quit_app)
        menu.exec(event.globalPos())

    def toggle_debug(self, checked):
        self.debug_mode = checked
        self.update()

    def toggle_entropy_panel(self):
        """显示或隐藏熵值面板"""
        if self.entropy_panel.isVisible():
            self.entropy_panel.hide()
        else:
            # 显示在宠物旁边
            pet_geo = self.geometry()
            self.entropy_panel.move(pet_geo.right() + 10, pet_geo.top())
            self.entropy_panel.show()

    def on_ai_finished(self):
        # 确保所有 buffer 都被处理（可能有不完整标签，强制输出）
        if self.raw_buffer and not self.paused:
            # 将剩余 buffer 视为普通文本输出（避免显示残缺标签）
            if self.is_thinking:
                self.current_think_text += self.raw_buffer
            else:
                self.current_reply_text += self.raw_buffer
            self._update_bubbles()
            self.raw_buffer = ""

        # 重置输入框发送状态
        self.input_window.reset_sending_state()

        # --- 如果主动触发但没有收到任何回复，确保重置标志 ---
        self.is_active_triggering = False
        # -----------------------------------------------
        # --- 根据文本长度动态计算隐藏时间 ---
        # 只有当配置允许显示思考气泡时才计算隐藏时间
        if self.show_think_bubble:
            think_time = self.get_dynamic_hide_time(self.current_think_text)
            QTimer.singleShot(think_time, self.think_bubble.hide)

        # 计算回复气泡隐藏时间
        reply_time = self.get_dynamic_hide_time(self.current_reply_text)
        self.reply_hide_timer.start(reply_time)

    def show_sticker(self, relative_path):
        """拼接绝对路径并触发表情包显示"""
        clean_path = relative_path.strip()
        full_path = os.path.join(config.stickers_dir, clean_path)
        full_path = os.path.normpath(full_path)

        print(f"[逻辑拦截] 捕获到表情请求: '{clean_path}' -> 拼装路径: '{full_path}'")

        if os.path.exists(full_path):
            self.image_bubble.show_image(full_path, STICKERS_DURATION)
            self.update_bubble_positions()
        else:
            print(f"[逻辑拦截] ❌ 文件不存在，放弃显示: {full_path}")
            self.image_bubble.hide()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self.drag_pos)
            event.accept()

    def quit_app(self):
        if self.worker and self.worker.isRunning():
            self.worker.stop()
            self.worker.wait(1000)  # 等待最多1秒让其自然结束
        # 安全关闭监听线程
        if hasattr(self, 'monitor_thread'):
            self.monitor_thread.stop()
        self.think_bubble.close()
        self.reply_bubble.close()
        self.image_bubble.close()
        self.input_window.close()
        self.close()
        QApplication.instance().quit()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    pet = DesktopPet()
    pet.show()
    sys.exit(app.exec())
