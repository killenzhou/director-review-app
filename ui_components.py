# -*- coding: utf-8 -*-
import os
import time
import numpy as np
from PySide6.QtWidgets import (
    QLabel, QWidget, QHBoxLayout, QPushButton, QMessageBox, QRubberBand,
    QDialog, QVBoxLayout, QTextBrowser, QDialogButtonBox, QInputDialog,
    QSpinBox, QScrollArea, QFrame, QToolButton, QTabWidget, QTextEdit,
    QProgressBar, QSplitter, QTableWidget, QTableWidgetItem, QHeaderView,
    QComboBox, QSlider
)
from PySide6.QtGui import (
    QPixmap, QPainter, QColor, QPen, QMouseEvent, QKeyEvent, QGuiApplication,
    QBrush, QCursor, QIcon, QShortcut, QKeySequence
)
from PySide6.QtCore import Qt, Signal, QPoint, QRect, QSize, QUrl, QTimer

try:
    from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput
    from PySide6.QtMultimediaWidgets import QVideoWidget
except Exception:
    QMediaPlayer = None
    QAudioOutput = None
    QVideoWidget = None

# --- 导入帮助文本模块 ---
from help_content import HELP_TEXT_HTML

class RecordingIndicator(QLabel):
    def __init__(self):
        super().__init__()
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setStyleSheet("QLabel { color: white; background-color: rgba(224, 108, 117, 0.85); border-radius: 5px; padding: 8px 12px; font-size: 10pt; font-weight: bold; }")
        self.setText("正在录音...")
        self.adjustSize(); self.hide()
    def set_text(self, text):
        self.setText(text); self.adjustSize()
    def show_at_corner(self):
        screen_geometry = QGuiApplication.primaryScreen().availableGeometry()
        self.move(screen_geometry.right() - self.width() - 15, screen_geometry.bottom() - self.height() - 15)
        self.show()

class CropWindow(QWidget):
    ocr_retry_signal = Signal(int, QRect, int)
    def __init__(self, image_path, row, column):
        super().__init__()
        self.image_path = image_path; self.row = row; self.column = column
        self.pixmap = QPixmap(image_path)
        self.setWindowTitle("双击关闭 | 拖拽鼠标框选需识别的区域"); self.setGeometry(100, 100, self.pixmap.width(), self.pixmap.height()); self.setCursor(Qt.CrossCursor)
        self.rubber_band = QRubberBand(QRubberBand.Rectangle, self); self.origin = QPoint(); self.show()
    def paintEvent(self, event):
        painter = QPainter(self); painter.drawPixmap(self.rect(), self.pixmap)
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton: self.origin = event.position().toPoint(); self.rubber_band.setGeometry(QRect(self.origin, QSize())); self.rubber_band.show()
    def mouseMoveEvent(self, event):
        if not self.origin.isNull(): self.rubber_band.setGeometry(QRect(self.origin, event.position().toPoint()).normalized())
    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton: self.rubber_band.hide(); crop_rect = self.rubber_band.geometry(); self.ocr_retry_signal.emit(self.row, crop_rect, self.column); self.close()
    def mouseDoubleClickEvent(self, event): self.close()

class DoodleEditor(QWidget):
    doodle_saved = Signal(int, str)
    def __init__(self, image_path, row):
        super().__init__(); self.image_path = image_path; self.row = row; self.pixmap = QPixmap(image_path)
        self.setWindowTitle("涂鸦编辑器 - 双击图片保存并关闭 | Esc 取消"); self.setGeometry(100, 100, self.pixmap.width(), self.pixmap.height()); self.setCursor(Qt.CrossCursor)
        self.drawing = False; self.last_point = QPoint(); self.current_tool = 'pen'; self.current_color = QColor("#ff5555"); self.shapes = []
        self.setup_mini_toolbar(); self.show()
    def setup_mini_toolbar(self):
        self.toolbar = QWidget(self); self.toolbar.setStyleSheet("QWidget { background-color: rgba(40, 44, 52, 0.9); border-radius: 5px; } QPushButton { color: white; border: 1px solid #555; padding: 5px; font-size: 9pt;} QPushButton:checked { background-color: #528bff; }"); layout = QHBoxLayout(self.toolbar)
        pen_btn = QPushButton("画笔"); pen_btn.setCheckable(True); pen_btn.setChecked(True); rect_btn = QPushButton("方框"); rect_btn.setCheckable(True); arrow_btn = QPushButton("箭头"); arrow_btn.setCheckable(True)
        self.tool_buttons = [pen_btn, rect_btn, arrow_btn]; pen_btn.clicked.connect(lambda: self.set_tool('pen', pen_btn)); rect_btn.clicked.connect(lambda: self.set_tool('rect', rect_btn)); arrow_btn.clicked.connect(lambda: self.set_tool('arrow', arrow_btn))
        red_btn = QPushButton(); red_btn.setStyleSheet("background-color: #ff5555;"); red_btn.setFixedSize(20, 20); yellow_btn = QPushButton(); yellow_btn.setStyleSheet("background-color: #e5c07b;"); yellow_btn.setFixedSize(20, 20); blue_btn = QPushButton(); blue_btn.setStyleSheet("background-color: #528bff;"); blue_btn.setFixedSize(20, 20)
        red_btn.clicked.connect(lambda: self.set_color("#ff5555")); yellow_btn.clicked.connect(lambda: self.set_color("#e5c07b")); blue_btn.clicked.connect(lambda: self.set_color("#528bff"))
        save_btn = QPushButton("保存"); save_btn.clicked.connect(self.save_doodle); cancel_btn = QPushButton("取消 (Esc)"); cancel_btn.clicked.connect(self.close)
        layout.addWidget(pen_btn); layout.addWidget(rect_btn); layout.addWidget(arrow_btn); layout.addSpacing(20); layout.addWidget(red_btn); layout.addWidget(yellow_btn); layout.addWidget(blue_btn); layout.addStretch(); layout.addWidget(save_btn); layout.addWidget(cancel_btn)
        self.toolbar.move(20, 20); self.toolbar.adjustSize()
    def set_tool(self, tool_name, clicked_button): self.current_tool = tool_name; [btn.setChecked(False) for btn in self.tool_buttons if btn != clicked_button]
    def set_color(self, color_hex): self.current_color = QColor(color_hex)
    def paintEvent(self, event):
        painter = QPainter(self); painter.drawPixmap(self.rect(), self.pixmap)
        for shape in self.shapes:
            pen = QPen(shape['color'], 3, Qt.SolidLine); painter.setPen(pen)
            if shape['tool'] == 'pen': painter.drawPolyline(shape['points'])
            elif shape['tool'] == 'rect': painter.drawRect(QRect(shape['start'], shape['end']))
            elif shape['tool'] == 'arrow': self.draw_arrow(painter, shape['start'], shape['end'])
    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.LeftButton:
            self.drawing = True; self.last_point = event.position().toPoint()
            if self.current_tool == 'pen': self.shapes.append({'tool': 'pen', 'color': self.current_color, 'points': [self.last_point]})
            else: self.shapes.append({'tool': self.current_tool, 'color': self.current_color, 'start': self.last_point, 'end': self.last_point})
            self.update()
    def mouseMoveEvent(self, event: QMouseEvent):
        if self.drawing:
            if self.current_tool == 'pen': self.shapes[-1]['points'].append(event.position().toPoint())
            else: self.shapes[-1]['end'] = event.position().toPoint()
            self.update()
    def mouseReleaseEvent(self, event: QMouseEvent):
        if event.button() == Qt.LeftButton: self.drawing = False
    def keyPressEvent(self, event: QKeyEvent):
        if event.key() == Qt.Key_Escape: self.close()
    def mouseDoubleClickEvent(self, event: QMouseEvent): self.save_doodle()
    def draw_arrow(self, painter, start_point, end_point):
        if start_point == end_point: return
        painter.drawLine(start_point, end_point)
        angle = np.arctan2(end_point.y() - start_point.y(), end_point.x() - start_point.x())
        arrow_head_size = 15.0
        p1 = end_point - QPoint(int(np.cos(angle + np.pi/6) * arrow_head_size), int(np.sin(angle + np.pi/6) * arrow_head_size))
        p2 = end_point - QPoint(int(np.cos(angle - np.pi/6) * arrow_head_size), int(np.sin(angle - np.pi/6) * arrow_head_size))
        painter.drawLine(end_point, p1); painter.drawLine(end_point, p2)
    def save_doodle(self):
        import os
        final_pixmap = self.pixmap.copy(); painter = QPainter(final_pixmap)
        for shape in self.shapes:
            pen = QPen(shape['color'], 3, Qt.SolidLine); painter.setPen(pen)
            if shape['tool'] == 'pen': painter.drawPolyline(shape['points'])
            elif shape['tool'] == 'rect': painter.drawRect(QRect(shape['start'], shape['end']))
            elif shape['tool'] == 'arrow': self.draw_arrow(painter, shape['start'], shape['end'])
        painter.end()
        dir_name = os.path.dirname(self.image_path); base_name, ext = os.path.splitext(os.path.basename(self.image_path)); base_name = base_name.replace("_annotated", "")
        new_name = f"{base_name}_annotated{ext}"; save_path = os.path.join(dir_name, new_name)
        final_pixmap.save(save_path); self.doodle_saved.emit(self.row, save_path); self.close()

# --- FIX: Re-implement HelpDialog as a proper QDialog with a scrollable area ---
class HelpDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("帮助 - 协同审阅平台")
        self.resize(700, 550)  # Set a default size for the dialog

        # Main layout
        layout = QVBoxLayout(self)

        # Text browser for scrollable rich text content
        text_browser = QTextBrowser()
        text_browser.setHtml(HELP_TEXT_HTML)
        text_browser.setOpenExternalLinks(True) # Make links clickable

        # Standard button box (e.g., OK button)
        button_box = QDialogButtonBox(QDialogButtonBox.Ok)
        button_box.accepted.connect(self.accept)

        # Add widgets to the layout
        layout.addWidget(text_browser)
        layout.addWidget(button_box)


class DraggableToolbar(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._dragging = False
        self._drag_offset = QPoint()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            child = self.childAt(event.position().toPoint())
            if child is None or child.property("dragHandle"):
                self._dragging = True
                self._drag_offset = event.position().toPoint()
                self.setCursor(Qt.ClosedHandCursor)
                event.accept()
                return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._dragging:
            new_pos = self.mapToParent(event.position().toPoint() - self._drag_offset)
            parent_rect = self.parentWidget().rect() if self.parentWidget() else None
            if parent_rect:
                new_x = max(0, min(new_pos.x(), parent_rect.width() - self.width()))
                new_y = max(0, min(new_pos.y(), parent_rect.height() - self.height()))
                self.move(new_x, new_y)
            else:
                self.move(new_pos)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton and self._dragging:
            self._dragging = False
            self.setCursor(Qt.ArrowCursor)
            event.accept()
            return
        super().mouseReleaseEvent(event)


class AnnotationOverlay(QWidget):
    annotation_saved = Signal(str)

    def __init__(self, image_path, save_dir, parent=None, show_immediately=True):
        super().__init__(parent)
        self.image_path = image_path
        self.save_dir = save_dir
        self.pixmap = QPixmap(image_path)
        self.current_tool = "pen"
        self.current_color = QColor("#ff3b30")
        self.pen_width = 5
        self.shapes = []
        self.redo_stack = []
        self.drawing = False
        self.active_shape = None
        self._saved_path = None

        self.setWindowTitle("录制截图批注 - 有标注时退出自动保存 | Esc 退出")
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.setCursor(Qt.CrossCursor)
        self._setup_toolbar()

        screen = QGuiApplication.screenAt(QCursor.pos()) or QGuiApplication.primaryScreen()
        self.setGeometry(screen.geometry())
        if show_immediately:
            self.showFullScreen()

    def _setup_toolbar(self):
        self.toolbar = DraggableToolbar(self)
        self.toolbar.setStyleSheet("""
            QWidget { background-color: rgba(22, 24, 29, 0.92); border-radius: 6px; }
            QPushButton, QToolButton { color: white; background-color: #3e4451; border: 1px solid #5c6370; padding: 6px 9px; border-radius: 3px; }
            QPushButton:checked { background-color: #0a84ff; border: 2px solid #ffffff; font-weight: bold; }
            QPushButton:hover, QToolButton:hover { background-color: #4f5663; }
        """)
        layout = QHBoxLayout(self.toolbar)
        layout.setContentsMargins(8, 6, 8, 6)

        handle = QLabel("拖动空白处移动工具栏")
        handle.setProperty("dragHandle", True)
        handle.setCursor(Qt.OpenHandCursor)
        handle.setStyleSheet("color: #cbd5e1; padding: 0 8px;")
        layout.addWidget(handle)

        self.tool_buttons = []
        for text, tool in [("笔刷", "pen"), ("方框", "rect"), ("箭头", "arrow"), ("文字", "text")]:
            btn = QPushButton(text)
            btn.setCheckable(True)
            btn.clicked.connect(lambda checked=False, t=tool, b=btn: self.set_tool(t, b))
            self.tool_buttons.append(btn)
            layout.addWidget(btn)
        self.tool_buttons[0].setChecked(True)

        for color in ["#ff3b30", "#ffd60a", "#32d74b", "#0a84ff", "#ffffff"]:
            btn = QPushButton()
            btn.setFixedSize(24, 24)
            btn.setStyleSheet(f"background-color: {color}; border: 1px solid #888;")
            btn.clicked.connect(lambda checked=False, c=color: self.set_color(c))
            layout.addWidget(btn)

        self.width_spin = QSpinBox()
        self.width_spin.setRange(1, 24)
        self.width_spin.setValue(self.pen_width)
        self.width_spin.setSuffix(" px")
        self.width_spin.valueChanged.connect(self.set_width)
        layout.addWidget(self.width_spin)

        for text, callback in [
            ("撤销", self.undo),
            ("重做", self.redo),
            ("清空", self.clear_annotations),
            ("退出", self.close),
        ]:
            btn = QPushButton(text)
            btn.clicked.connect(callback)
            layout.addWidget(btn)

        self.toolbar.move(18, 18)
        self.toolbar.adjustSize()

    def set_tool(self, tool_name, clicked_button):
        self.current_tool = tool_name
        for btn in self.tool_buttons:
            btn.setChecked(btn is clicked_button)

    def set_color(self, color_hex):
        self.current_color = QColor(color_hex)

    def set_width(self, value):
        self.pen_width = value

    def _to_image_point(self, point):
        if self.width() == 0 or self.height() == 0:
            return QPoint(point)
        x = int(point.x() * self.pixmap.width() / self.width())
        y = int(point.y() * self.pixmap.height() / self.height())
        return QPoint(x, y)

    def _to_screen_point(self, point):
        if self.pixmap.width() == 0 or self.pixmap.height() == 0:
            return QPoint(point)
        x = int(point.x() * self.width() / self.pixmap.width())
        y = int(point.y() * self.height() / self.pixmap.height())
        return QPoint(x, y)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.drawPixmap(self.rect(), self.pixmap)
        painter.setRenderHint(QPainter.Antialiasing)
        for shape in self.shapes:
            self._draw_shape(painter, shape, to_screen=True)

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() != Qt.LeftButton or self.childAt(event.position().toPoint()) is not None:
            return
        image_point = self._to_image_point(event.position().toPoint())
        if self.current_tool == "text":
            text, ok = QInputDialog.getText(self, "添加文字", "批注文字:")
            if ok and text:
                self.shapes.append({
                    "tool": "text", "text": text, "point": image_point,
                    "color": QColor(self.current_color), "width": self.pen_width
                })
                self.redo_stack.clear()
                self.update()
            return

        self.drawing = True
        if self.current_tool == "pen":
            self.active_shape = {
                "tool": "pen", "points": [image_point],
                "color": QColor(self.current_color), "width": self.pen_width
            }
        else:
            self.active_shape = {
                "tool": self.current_tool, "start": image_point, "end": image_point,
                "color": QColor(self.current_color), "width": self.pen_width
            }
        self.shapes.append(self.active_shape)
        self.redo_stack.clear()
        self.update()

    def mouseMoveEvent(self, event: QMouseEvent):
        if not self.drawing or not self.active_shape:
            return
        image_point = self._to_image_point(event.position().toPoint())
        if self.active_shape["tool"] == "pen":
            self.active_shape["points"].append(image_point)
        else:
            self.active_shape["end"] = image_point
        self.update()

    def mouseReleaseEvent(self, event: QMouseEvent):
        if event.button() == Qt.LeftButton:
            self.drawing = False
            self.active_shape = None

    def keyPressEvent(self, event: QKeyEvent):
        if event.key() == Qt.Key_Escape:
            self.close()
            return
        if event.key() in (Qt.Key_Return, Qt.Key_Enter) and event.modifiers() & Qt.ControlModifier:
            self.close()
            return
        if event.key() == Qt.Key_Z and event.modifiers() & Qt.ControlModifier:
            self.undo()
            return
        if event.key() == Qt.Key_Y and event.modifiers() & Qt.ControlModifier:
            self.redo()
            return
        super().keyPressEvent(event)

    def undo(self):
        if self.shapes:
            self.redo_stack.append(self.shapes.pop())
            self.update()

    def redo(self):
        if self.redo_stack:
            self.shapes.append(self.redo_stack.pop())
            self.update()

    def clear_annotations(self):
        if self.shapes:
            self.redo_stack.extend(reversed(self.shapes))
            self.shapes.clear()
            self.update()

    def _draw_shape(self, painter, shape, to_screen=False):
        pen = QPen(shape["color"], shape.get("width", 3), Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)

        def pt(value):
            return self._to_screen_point(value) if to_screen else value

        if shape["tool"] == "pen":
            points = [pt(p) for p in shape.get("points", [])]
            if len(points) > 1:
                painter.drawPolyline(points)
        elif shape["tool"] == "rect":
            painter.drawRect(QRect(pt(shape["start"]), pt(shape["end"])).normalized())
        elif shape["tool"] == "arrow":
            start = pt(shape["start"])
            end = pt(shape["end"])
            self._draw_arrow(painter, start, end)
        elif shape["tool"] == "text":
            painter.setBrush(QBrush(shape["color"]))
            font = painter.font()
            font.setPointSize(max(12, shape.get("width", 5) * 3))
            font.setBold(True)
            painter.setFont(font)
            painter.drawText(pt(shape["point"]), shape.get("text", ""))

    def _draw_arrow(self, painter, start_point, end_point):
        if start_point == end_point:
            return
        painter.drawLine(start_point, end_point)
        angle = np.arctan2(end_point.y() - start_point.y(), end_point.x() - start_point.x())
        arrow_head_size = max(14.0, self.pen_width * 4.0)
        p1 = end_point - QPoint(int(np.cos(angle + np.pi / 6) * arrow_head_size), int(np.sin(angle + np.pi / 6) * arrow_head_size))
        p2 = end_point - QPoint(int(np.cos(angle - np.pi / 6) * arrow_head_size), int(np.sin(angle - np.pi / 6) * arrow_head_size))
        painter.drawLine(end_point, p1)
        painter.drawLine(end_point, p2)

    def save_annotation(self):
        if self._save_annotation_if_needed():
            self.close()

    def closeEvent(self, event):
        self._save_annotation_if_needed()
        super().closeEvent(event)

    def _save_annotation_if_needed(self):
        if self._saved_path:
            return True
        if not self.shapes:
            return False
        os.makedirs(self.save_dir, exist_ok=True)
        final_pixmap = self.pixmap.copy()
        painter = QPainter(final_pixmap)
        painter.setRenderHint(QPainter.Antialiasing)
        for shape in self.shapes:
            self._draw_shape(painter, shape, to_screen=False)
        painter.end()
        save_path = os.path.join(self.save_dir, f"annotation_{int(time.time())}.png")
        if final_pixmap.save(save_path):
            self._saved_path = save_path
            self.annotation_saved.emit(save_path)
            return True
        else:
            QMessageBox.critical(self, "保存失败", f"无法保存批注截图:\n{save_path}")
            return False


class ReviewDetailPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.resolve_path = None
        self.open_file = None
        self.current_media_path = None
        self.player = None
        self.audio_output = None
        self.video_widget = None
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        self.title_label = QLabel("详情预览")
        self.title_label.setStyleSheet("font-weight: bold; font-size: 12pt;")
        layout.addWidget(self.title_label)

        self.preview_image = QLabel("选择一条审阅记录")
        self.preview_image.setAlignment(Qt.AlignCenter)
        self.preview_image.setMinimumHeight(180)
        self.preview_image.setFrameShape(QFrame.StyledPanel)
        layout.addWidget(self.preview_image)

        self.meta_label = QLabel("")
        self.meta_label.setWordWrap(True)
        layout.addWidget(self.meta_label)

        self.refs_area = QScrollArea()
        self.refs_area.setWidgetResizable(True)
        self.refs_widget = QWidget()
        self.refs_layout = QVBoxLayout(self.refs_widget)
        self.refs_area.setWidget(self.refs_widget)
        self.refs_area.setMinimumHeight(110)
        layout.addWidget(QLabel("参考文件"))
        layout.addWidget(self.refs_area)

        layout.addWidget(QLabel("音频/视频预览"))
        if QMediaPlayer and QAudioOutput and QVideoWidget:
            self.video_widget = QVideoWidget()
            self.video_widget.setMinimumHeight(160)
            layout.addWidget(self.video_widget)
            self.audio_output = QAudioOutput(self)
            self.player = QMediaPlayer(self)
            self.player.setAudioOutput(self.audio_output)
            self.player.setVideoOutput(self.video_widget)
            controls = QHBoxLayout()
            for text, callback in [("播放", self.play), ("暂停", self.pause), ("停止", self.stop), ("打开文件", self.open_current_media)]:
                btn = QPushButton(text)
                btn.clicked.connect(callback)
                controls.addWidget(btn)
            layout.addLayout(controls)
        else:
            layout.addWidget(QLabel("QtMultimedia 不可用，无法内置预览。"))

        layout.addStretch()

    def set_callbacks(self, resolve_path, open_file):
        self.resolve_path = resolve_path
        self.open_file = open_file

    def set_entry(self, entry):
        if not entry:
            self.title_label.setText("详情预览")
            self.preview_image.setText("选择一条审阅记录")
            self.preview_image.setPixmap(QPixmap())
            self.meta_label.setText("")
            self._clear_layout(self.refs_layout)
            self.stop()
            self.current_media_path = None
            return

        self.title_label.setText(entry.get("shot_number") or "未命名镜头")
        self.meta_label.setText(
            f"时间戳: {entry.get('timestamp', '')}\n"
            f"部门: {entry.get('department', '')}\n"
            f"状态: {entry.get('status', '') or '自动'}\n"
            f"简化意见: {entry.get('simplified_review', '')}"
        )
        self._set_preview_image(self._resolve(entry.get("screenshot_path")))
        self._populate_references(entry.get("reference_files", []))
        self._load_first_media(entry)

    def _resolve(self, rel_or_abs):
        if not rel_or_abs:
            return None
        if os.path.isabs(rel_or_abs):
            return rel_or_abs
        return self.resolve_path(rel_or_abs) if self.resolve_path else rel_or_abs

    def _set_preview_image(self, path):
        if path and os.path.exists(path):
            pixmap = QPixmap(path)
            self.preview_image.setPixmap(pixmap.scaled(320, 180, Qt.KeepAspectRatio, Qt.SmoothTransformation))
            self.preview_image.setText("")
        else:
            self.preview_image.setPixmap(QPixmap())
            self.preview_image.setText("图片丢失")

    def _populate_references(self, refs):
        self._clear_layout(self.refs_layout)
        valid_refs = [ref for ref in refs or [] if ref]
        if not valid_refs:
            self.refs_layout.addWidget(QLabel("无参考文件"))
            return
        for rel_path in valid_refs:
            abs_path = self._resolve(rel_path)
            row = QWidget()
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(0, 0, 0, 0)
            label = QLabel(os.path.basename(rel_path))
            label.setToolTip(abs_path or "")
            preview_btn = QPushButton("预览")
            preview_btn.clicked.connect(lambda checked=False, p=abs_path: self._set_preview_image(p))
            open_btn = QPushButton("打开")
            open_btn.clicked.connect(lambda checked=False, p=abs_path: self.open_file(p) if self.open_file else None)
            row_layout.addWidget(label)
            row_layout.addWidget(preview_btn)
            row_layout.addWidget(open_btn)
            self.refs_layout.addWidget(row)
        self.refs_layout.addStretch()

    def _load_first_media(self, entry):
        media_files = [m for m in entry.get("media_files", []) or [] if m]
        if not media_files and entry.get("audio_path"):
            media_files = [entry.get("audio_path")]
        media_path = self._resolve(media_files[0]) if media_files else None
        self.load_media(media_path)

    def load_media(self, path):
        self.current_media_path = path if path and os.path.exists(path) else None
        if self.player:
            self.player.stop()
            if self.current_media_path:
                self.player.setSource(QUrl.fromLocalFile(self.current_media_path))
            else:
                self.player.setSource(QUrl())

    def play(self):
        if self.player and self.current_media_path:
            self.player.play()

    def pause(self):
        if self.player:
            self.player.pause()

    def stop(self):
        if self.player:
            self.player.stop()

    def open_current_media(self):
        if self.open_file and self.current_media_path:
            self.open_file(self.current_media_path)

    def _clear_layout(self, layout):
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

        self.setLayout(layout)
# --- End FIX ---


class ReviewModePanel(QWidget):
    entry_selected = Signal(int)

    def __init__(self, resolve_path=None, open_file=None, parent=None):
        super().__init__(parent)
        self.resolve_path = resolve_path
        self.open_file = open_file
        self.entries = []
        self.visible_rows = []
        self.current_row = -1
        self.timeline_buttons = {}
        self.current_media_path = None
        self.player = None
        self.audio_output = None
        self.video_widget = None
        self._seeking = False
        self._playback_rate = 1.0
        self._reverse_rate = 0.0
        self._reverse_timer = QTimer(self)
        self._reverse_timer.setInterval(40)
        self._reverse_timer.timeout.connect(self._reverse_tick)
        self._playback_shortcuts = []
        self.setFocusPolicy(Qt.StrongFocus)
        self._build_ui()

    def _build_ui(self):
        root = QHBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(8)

        main = QWidget()
        main_layout = QVBoxLayout(main)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(8)

        self.viewer_frame = QFrame()
        self.viewer_frame.setFrameShape(QFrame.StyledPanel)
        viewer_layout = QVBoxLayout(self.viewer_frame)
        viewer_layout.setContentsMargins(8, 8, 8, 8)
        viewer_layout.setSpacing(6)

        self.player_title = QLabel("审阅播放器")
        self.player_title.setStyleSheet("font-size: 13pt; font-weight: 700;")
        viewer_layout.addWidget(self.player_title)

        if QMediaPlayer and QAudioOutput and QVideoWidget:
            self.video_widget = QVideoWidget()
            self.video_widget.setMinimumHeight(330)
            viewer_layout.addWidget(self.video_widget, 1)
            self.audio_output = QAudioOutput(self)
            self.player = QMediaPlayer(self)
            self.player.setAudioOutput(self.audio_output)
            self.player.setVideoOutput(self.video_widget)
            self.player.mediaStatusChanged.connect(self._on_media_status_changed)
            self.player.positionChanged.connect(self._on_player_position_changed)
            self.player.durationChanged.connect(self._on_player_duration_changed)
        else:
            missing = QLabel("QtMultimedia 不可用，无法内置播放。")
            missing.setAlignment(Qt.AlignCenter)
            missing.setMinimumHeight(330)
            viewer_layout.addWidget(missing, 1)

        progress_layout = QHBoxLayout()
        self.current_time_label = QLabel("00:00")
        self.total_time_label = QLabel("00:00")
        self.seek_slider = QSlider(Qt.Horizontal)
        self.seek_slider.setRange(0, 0)
        self.seek_slider.sliderPressed.connect(self._begin_seek)
        self.seek_slider.sliderMoved.connect(self._preview_seek)
        self.seek_slider.sliderReleased.connect(self._finish_seek)
        progress_layout.addWidget(self.current_time_label)
        progress_layout.addWidget(self.seek_slider, 1)
        progress_layout.addWidget(self.total_time_label)
        viewer_layout.addLayout(progress_layout)

        controls = QHBoxLayout()
        for text, callback in [
            ("上一镜", self.play_previous),
            ("播放", self.play),
            ("暂停", self.pause),
            ("停止", self.stop),
            ("下一镜", self.play_next),
            ("打开媒体", self.open_current_media),
        ]:
            btn = QPushButton(text)
            btn.clicked.connect(callback)
            controls.addWidget(btn)
        self.rate_label = QLabel("1x")
        self.rate_label.setMinimumWidth(48)
        self.rate_label.setAlignment(Qt.AlignCenter)
        controls.addWidget(self.rate_label)
        controls.addStretch()
        controls.addWidget(QLabel("时间线缩放"))
        self.zoom_slider = QSlider(Qt.Horizontal)
        self.zoom_slider.setRange(80, 180)
        self.zoom_slider.setValue(110)
        self.zoom_slider.setFixedWidth(130)
        self.zoom_slider.valueChanged.connect(self._apply_timeline_zoom)
        controls.addWidget(self.zoom_slider)
        viewer_layout.addLayout(controls)
        self._setup_playback_shortcuts()
        main_layout.addWidget(self.viewer_frame, 1)

        timeline_frame = QFrame()
        timeline_frame.setFrameShape(QFrame.StyledPanel)
        timeline_layout = QVBoxLayout(timeline_frame)
        timeline_layout.setContentsMargins(8, 8, 8, 8)
        timeline_layout.setSpacing(6)
        timeline_layout.addWidget(QLabel("镜头时间线"))
        self.timeline_scroll = QScrollArea()
        self.timeline_scroll.setWidgetResizable(True)
        self.timeline_content = QWidget()
        self.timeline_layout = QHBoxLayout(self.timeline_content)
        self.timeline_layout.setContentsMargins(2, 2, 2, 2)
        self.timeline_layout.setSpacing(6)
        self.timeline_scroll.setWidget(self.timeline_content)
        self.timeline_scroll.setMinimumHeight(120)
        timeline_layout.addWidget(self.timeline_scroll)
        main_layout.addWidget(timeline_frame)

        detail = QFrame()
        detail.setFrameShape(QFrame.StyledPanel)
        detail.setMinimumWidth(320)
        detail.setMaximumWidth(430)
        detail_layout = QVBoxLayout(detail)
        detail_layout.setContentsMargins(10, 10, 10, 10)
        detail_layout.setSpacing(8)

        self.detail_title = QLabel("选择一个镜头")
        self.detail_title.setStyleSheet("font-size: 13pt; font-weight: 700;")
        detail_layout.addWidget(self.detail_title)
        self.detail_meta = QLabel("")
        self.detail_meta.setWordWrap(True)
        detail_layout.addWidget(self.detail_meta)
        detail_layout.addWidget(QLabel("历史版本"))
        self.version_select = QComboBox()
        self.version_select.currentIndexChanged.connect(self._on_version_selected)
        detail_layout.addWidget(self.version_select)

        detail_layout.addWidget(QLabel("修改意见"))
        self.full_review_text = QTextEdit()
        self.full_review_text.setReadOnly(True)
        self.full_review_text.setMinimumHeight(150)
        detail_layout.addWidget(self.full_review_text)

        detail_layout.addWidget(QLabel("整理结果"))
        self.summary_label = QLabel("")
        self.summary_label.setWordWrap(True)
        self.summary_label.setFrameShape(QFrame.StyledPanel)
        self.summary_label.setMinimumHeight(70)
        detail_layout.addWidget(self.summary_label)

        detail_layout.addWidget(QLabel("参考"))
        self.reference_preview = QLabel("无参考")
        self.reference_preview.setAlignment(Qt.AlignCenter)
        self.reference_preview.setMinimumHeight(150)
        self.reference_preview.setFrameShape(QFrame.StyledPanel)
        detail_layout.addWidget(self.reference_preview)
        self.refs_area = QScrollArea()
        self.refs_area.setWidgetResizable(True)
        self.refs_widget = QWidget()
        self.refs_layout = QVBoxLayout(self.refs_widget)
        self.refs_layout.setContentsMargins(0, 0, 0, 0)
        self.refs_layout.setSpacing(4)
        self.refs_area.setWidget(self.refs_widget)
        self.refs_area.setMinimumHeight(120)
        detail_layout.addWidget(self.refs_area)

        root.addWidget(main, 1)
        root.addWidget(detail)

    def set_callbacks(self, resolve_path, open_file):
        self.resolve_path = resolve_path
        self.open_file = open_file

    def update_entries(self, entries, visible_rows=None):
        self.entries = list(entries or [])
        if visible_rows is None:
            self.visible_rows = [idx for idx, entry in enumerate(self.entries) if entry.get("entry_type") != "long_video_full"]
        else:
            self.visible_rows = [
                row for row in visible_rows
                if 0 <= row < len(self.entries) and self.entries[row].get("entry_type") != "long_video_full"
            ]
        self._rebuild_timeline()
        if 0 <= self.current_row < len(self.entries) and self.current_row in self.visible_rows:
            self.set_current_row(self.current_row, emit=False)
        else:
            self.set_current_row(self._first_review_row(), emit=False)

    def set_current_row(self, row, emit=False):
        if not (0 <= row < len(self.entries)):
            self.current_row = -1
            self._set_empty_detail()
            self._highlight_current_button()
            return
        self.current_row = row
        entry = self.entries[row]
        self._update_detail(row, entry)
        self._load_entry_media(entry)
        self._highlight_current_button()
        if emit:
            self.entry_selected.emit(row)

    def play(self):
        if self.player and self.current_media_path:
            self._stop_reverse()
            self._set_playback_rate(1.0)
            self.player.play()

    def pause(self):
        self._stop_reverse()
        if self.player:
            self.player.pause()

    def stop(self):
        self._stop_reverse()
        if self.player:
            self.player.stop()
            self._set_playback_rate(1.0)

    def toggle_play_pause(self):
        if not self.player or not self.current_media_path:
            return
        if self._reverse_timer.isActive():
            self._stop_reverse()
            return
        if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.player.pause()
        else:
            self._set_playback_rate(1.0)
            self.player.play()

    def play_forward_shortcut(self):
        if not self.player or not self.current_media_path:
            return
        if self._reverse_timer.isActive():
            self._stop_reverse()
            self._set_playback_rate(1.0)
        elif self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState and self._playback_rate < 2.0:
            self._set_playback_rate(2.0)
        else:
            self._set_playback_rate(1.0)
        self.player.play()

    def play_reverse_shortcut(self):
        if not self.player or not self.current_media_path:
            return
        next_rate = 2.0 if self._reverse_timer.isActive() and self._reverse_rate < 2.0 else 1.0
        self._start_reverse(next_rate)

    def _setup_playback_shortcuts(self):
        for key, callback in [("K", self.toggle_play_pause), ("L", self.play_forward_shortcut), ("J", self.play_reverse_shortcut)]:
            shortcut = QShortcut(QKeySequence(key), self)
            shortcut.setContext(Qt.WidgetWithChildrenShortcut)
            shortcut.activated.connect(callback)
            self._playback_shortcuts.append(shortcut)

    def _set_playback_rate(self, rate):
        self._playback_rate = float(rate)
        if self.player:
            self.player.setPlaybackRate(self._playback_rate)
        self._update_rate_label()

    def _start_reverse(self, rate):
        if not self.player:
            return
        self.player.pause()
        self._reverse_rate = float(rate)
        self._reverse_timer.start()
        self._update_rate_label()

    def _stop_reverse(self):
        if self._reverse_timer.isActive():
            self._reverse_timer.stop()
        self._reverse_rate = 0.0
        self._update_rate_label()

    def _reverse_tick(self):
        if not self.player:
            return
        step_ms = int(self._reverse_timer.interval() * max(self._reverse_rate, 1.0))
        next_position = max(0, self.player.position() - step_ms)
        self.player.setPosition(next_position)
        if next_position <= 0:
            self._stop_reverse()

    def _update_rate_label(self):
        if not hasattr(self, "rate_label"):
            return
        if self._reverse_rate:
            self.rate_label.setText(f"-{self._reverse_rate:g}x")
        else:
            self.rate_label.setText(f"{self._playback_rate:g}x")

    def _begin_seek(self):
        self._seeking = True

    def _preview_seek(self, value):
        self.current_time_label.setText(self._format_ms(value))

    def _finish_seek(self):
        if self.player:
            self.player.setPosition(self.seek_slider.value())
        self._seeking = False

    def _on_player_position_changed(self, position):
        if not self._seeking:
            self.seek_slider.setValue(position)
        self.current_time_label.setText(self._format_ms(position))

    def _on_player_duration_changed(self, duration):
        self.seek_slider.setRange(0, max(0, duration))
        self.total_time_label.setText(self._format_ms(duration))

    def _format_ms(self, value):
        total_seconds = max(0, int(value // 1000))
        hours, remainder = divmod(total_seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        if hours:
            return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
        return f"{minutes:02d}:{seconds:02d}"

    def play_next(self):
        row = self._next_media_row(self.current_row + 1)
        if row is not None:
            self.set_current_row(row, emit=True)
            self.play()

    def play_previous(self):
        row = self._previous_media_row(self.current_row - 1)
        if row is not None:
            self.set_current_row(row, emit=True)
            self.play()

    def open_current_media(self):
        if self.open_file and self.current_media_path:
            self.open_file(self.current_media_path)

    def _on_media_status_changed(self, status):
        if QMediaPlayer and status == QMediaPlayer.MediaStatus.EndOfMedia:
            self._stop_reverse()
            self._set_playback_rate(1.0)
            self.play_next()

    def _rebuild_timeline(self):
        self._clear_layout(self.timeline_layout)
        self.timeline_buttons = {}
        rows = list(self.visible_rows)
        if not rows:
            self.timeline_layout.addWidget(QLabel("暂无可审阅镜头"))
            self.timeline_layout.addStretch()
            return
        for row in rows:
            entry = self.entries[row]
            button = QToolButton()
            button.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
            button.setCheckable(True)
            button.setText(self._timeline_text(row, entry))
            button.setToolTip(entry.get("full_review") or entry.get("simplified_review") or "")
            image_path = self._resolve(entry.get("screenshot_path"))
            if image_path and os.path.exists(image_path):
                pixmap = QPixmap(image_path).scaled(96, 54, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                button.setIcon(QIcon(pixmap))
                button.setIconSize(QSize(96, 54))
            button.clicked.connect(lambda checked=False, r=row: self.set_current_row(r, emit=True))
            self.timeline_layout.addWidget(button)
            self.timeline_buttons[row] = button
        self.timeline_layout.addStretch()
        self._apply_timeline_zoom()
        self._highlight_current_button()

    def _timeline_text(self, row, entry):
        shot = entry.get("shot_number") or f"第 {row + 1} 行"
        dept = entry.get("department") or "未分类"
        mark = "参考" if entry.get("reference_files") else ""
        return f"{shot}\n{dept} {mark}".strip()

    def _apply_timeline_zoom(self):
        width = int(self.zoom_slider.value()) if hasattr(self, "zoom_slider") else 110
        height = int(width * 0.82)
        for button in self.timeline_buttons.values():
            button.setFixedSize(width, max(92, height))

    def _highlight_current_button(self):
        for row, button in self.timeline_buttons.items():
            checked = row == self.current_row
            button.setChecked(checked)
            if checked:
                button.setStyleSheet("QToolButton { border: 2px solid #18a999; background: rgba(24, 169, 153, 0.22); padding: 4px; }")
            elif row < len(self.entries) and not self.entries[row].get("full_review"):
                button.setStyleSheet("QToolButton { border: 1px solid #b58900; background: rgba(181, 137, 0, 0.12); padding: 4px; }")
            else:
                button.setStyleSheet("QToolButton { border: 1px solid #4b5563; padding: 4px; }")

    def _update_detail(self, row, entry):
        shot = entry.get("shot_number") or f"第 {row + 1} 行"
        self.detail_title.setText(shot)
        self.player_title.setText(f"审阅播放器 - {shot}")
        self.detail_meta.setText(
            f"时间码: {entry.get('timestamp', '')}\n"
            f"部门: {entry.get('department', '')}\n"
            f"状态: {entry.get('status', '') or '自动'}\n"
            f"来源: {entry.get('source_project') or entry.get('source_revpack') or '-'}"
        )
        self._update_version_options(row, entry)
        self.full_review_text.setPlainText(entry.get("full_review", ""))
        summary_parts = []
        if entry.get("simplified_review"):
            summary_parts.append(entry.get("simplified_review"))
        if entry.get("keywords"):
            summary_parts.append("关键词: " + ", ".join(entry.get("keywords") or []))
        self.summary_label.setText("\n".join(summary_parts) or "暂无整理结果")
        self._populate_references(entry)

    def _set_empty_detail(self):
        self.detail_title.setText("选择一个镜头")
        self.player_title.setText("审阅播放器")
        self.detail_meta.setText("")
        if hasattr(self, "version_select"):
            self.version_select.blockSignals(True)
            self.version_select.clear()
            self.version_select.blockSignals(False)
        self.full_review_text.setPlainText("")
        self.summary_label.setText("")
        self.reference_preview.setPixmap(QPixmap())
        self.reference_preview.setText("无参考")
        self._clear_layout(self.refs_layout)
        self.current_media_path = None
        if self.player:
            self._stop_reverse()
            self._set_playback_rate(1.0)
            self.player.setSource(QUrl())
        if hasattr(self, "seek_slider"):
            self.seek_slider.setRange(0, 0)
            self.current_time_label.setText("00:00")
            self.total_time_label.setText("00:00")

    def _populate_references(self, entry):
        self._clear_layout(self.refs_layout)
        preview_path = self._resolve(entry.get("screenshot_path"))
        refs = [ref for ref in entry.get("reference_files", []) or [] if ref]
        if refs:
            first_ref = self._resolve(refs[0])
            if first_ref:
                preview_path = first_ref
        self._set_reference_preview(preview_path)
        if not refs:
            self.refs_layout.addWidget(QLabel("暂无参考文件"))
            self.refs_layout.addStretch()
            return
        for rel_path in refs:
            abs_path = self._resolve(rel_path)
            row_widget = QWidget()
            row_layout = QHBoxLayout(row_widget)
            row_layout.setContentsMargins(0, 0, 0, 0)
            label = QLabel(os.path.basename(rel_path))
            label.setToolTip(abs_path or "")
            preview_btn = QPushButton("预览")
            preview_btn.clicked.connect(lambda checked=False, p=abs_path: self._set_reference_preview(p))
            open_btn = QPushButton("打开")
            open_btn.clicked.connect(lambda checked=False, p=abs_path: self.open_file(p) if self.open_file else None)
            row_layout.addWidget(label, 1)
            row_layout.addWidget(preview_btn)
            row_layout.addWidget(open_btn)
            self.refs_layout.addWidget(row_widget)
        self.refs_layout.addStretch()

    def _set_reference_preview(self, path):
        if path and os.path.exists(path) and str(path).lower().endswith((".png", ".jpg", ".jpeg", ".bmp", ".webp")):
            pixmap = QPixmap(path)
            self.reference_preview.setPixmap(pixmap.scaled(300, 160, Qt.KeepAspectRatio, Qt.SmoothTransformation))
            self.reference_preview.setText("")
        else:
            self.reference_preview.setPixmap(QPixmap())
            self.reference_preview.setText("无可预览图片")

    def _load_entry_media(self, entry):
        media_path = self._first_media_path(entry)
        self.current_media_path = media_path
        if self.player:
            self._stop_reverse()
            self._set_playback_rate(1.0)
            self.player.stop()
            self.player.setSource(QUrl.fromLocalFile(media_path) if media_path else QUrl())
        if hasattr(self, "seek_slider"):
            self.seek_slider.setValue(0)
            self.seek_slider.setRange(0, 0)
            self.current_time_label.setText("00:00")
            self.total_time_label.setText("00:00")

    def _first_media_path(self, entry):
        candidates = [item for item in entry.get("media_files", []) or [] if item]
        if entry.get("audio_path"):
            candidates.append(entry.get("audio_path"))
        for rel_path in candidates:
            abs_path = self._resolve(rel_path)
            if abs_path and os.path.exists(abs_path):
                return abs_path
        return None

    def _next_media_row(self, start):
        for row in range(max(0, start), len(self.entries)):
            if self.entries[row].get("entry_type") == "long_video_full":
                continue
            if self._first_media_path(self.entries[row]):
                return row
        return None

    def _previous_media_row(self, start):
        for row in range(min(start, len(self.entries) - 1), -1, -1):
            if self.entries[row].get("entry_type") == "long_video_full":
                continue
            if self._first_media_path(self.entries[row]):
                return row
        return None

    def _first_review_row(self):
        for row in self.visible_rows:
            entry = self.entries[row]
            if entry.get("entry_type") != "long_video_full":
                return row
        return -1

    def _episode_scene_for_entry(self, entry):
        return (
            entry.get("episode") or entry.get("__episode") or "未分集",
            entry.get("scene") or entry.get("__scene") or "未分场",
        )

    def _history_key(self, entry):
        episode, scene = self._episode_scene_for_entry(entry)
        return (episode, scene, str(entry.get("shot_number") or "").strip())

    def _history_rows_for_entry(self, entry):
        key = self._history_key(entry)
        if not key[2]:
            return []
        rows = []
        for row, other in enumerate(self.entries):
            if other.get("entry_type") == "long_video_full":
                continue
            if self._history_key(other) == key:
                rows.append(row)
        return rows

    def _update_version_options(self, row, entry):
        if not hasattr(self, "version_select"):
            return
        rows = self._history_rows_for_entry(entry) or [row]
        self.version_select.blockSignals(True)
        self.version_select.clear()
        for version_row in rows:
            version_entry = self.entries[version_row]
            label = (
                f"{version_entry.get('source_project') or version_entry.get('source_revpack') or '当前工程'}"
                f" · {version_entry.get('timestamp') or '-'}"
            )
            self.version_select.addItem(label, version_row)
        idx = self.version_select.findData(row)
        self.version_select.setCurrentIndex(idx if idx >= 0 else 0)
        self.version_select.setEnabled(len(rows) > 1)
        self.version_select.blockSignals(False)

    def _on_version_selected(self, index):
        if index < 0 or not hasattr(self, "version_select"):
            return
        row = self.version_select.itemData(index)
        if isinstance(row, int) and row != self.current_row:
            self.set_current_row(row, emit=True)

    def _resolve(self, rel_or_abs):
        if not rel_or_abs:
            return None
        if os.path.isabs(rel_or_abs):
            return rel_or_abs
        return self.resolve_path(rel_or_abs) if self.resolve_path else rel_or_abs

    def _clear_layout(self, layout):
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()


class LongVideoTranscriptionDialog(QDialog):
    summary_requested = Signal()
    table_requested = Signal()
    issues_requested = Signal()
    issues_commit_requested = Signal(list)
    manual_issue_requested = Signal(dict)
    transcript_save_requested = Signal(str)

    def __init__(self, video_path, parent=None):
        super().__init__(parent)
        self.video_path = video_path
        self.issues = []
        self.mark_start_seconds = None
        self.player = None
        self.audio_output = None
        self.video_widget = None
        self.setWindowTitle("长视频转文字")
        self.resize(1400, 820)
        self._build_ui()
        self.set_video(video_path)

    def _build_ui(self):
        root = QVBoxLayout(self)
        header = QHBoxLayout()
        self.title_label = QLabel(os.path.basename(self.video_path) if self.video_path else "长视频")
        self.title_label.setStyleSheet("font-size: 14pt; font-weight: 700;")
        self.status_label = QLabel("准备转写")
        self.status_label.setStyleSheet("color: #8ab4f8;")
        summary_btn = QPushButton("生成纲要")
        summary_btn.clicked.connect(self.summary_requested.emit)
        issues_btn = QPushButton("整理问题")
        issues_btn.clicked.connect(self.issues_requested.emit)
        table_btn = QPushButton("确认入表")
        table_btn.clicked.connect(lambda: self.issues_commit_requested.emit(self.collect_issues()))
        save_btn = QPushButton("保存逐字稿")
        save_btn.clicked.connect(lambda: self.transcript_save_requested.emit(self.transcript_text.toPlainText()))
        header.addWidget(self.title_label, 1)
        header.addWidget(self.status_label)
        header.addWidget(summary_btn)
        header.addWidget(issues_btn)
        header.addWidget(table_btn)
        header.addWidget(save_btn)
        root.addLayout(header)

        splitter = QSplitter(Qt.Horizontal)
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        self.tabs = QTabWidget()
        self.summary_text = QTextEdit()
        self.summary_text.setReadOnly(True)
        self.issue_table = QTableWidget()
        self._setup_issue_table()
        self.timeline_text = QTextEdit()
        self.timeline_text.setReadOnly(True)
        self.transcript_text = QTextEdit()
        self.transcript_text.setReadOnly(False)
        self.tabs.addTab(self.summary_text, "纲要")
        self.tabs.addTab(self.issue_table, "问题清单")
        self.tabs.addTab(self.timeline_text, "时间轴")
        self.tabs.addTab(self.transcript_text, "逐字稿")
        left_layout.addWidget(self.tabs)
        splitter.addWidget(left)

        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(8, 0, 0, 0)
        if QMediaPlayer and QAudioOutput and QVideoWidget:
            self.video_widget = QVideoWidget()
            self.video_widget.setMinimumHeight(360)
            right_layout.addWidget(self.video_widget, 1)
            self.audio_output = QAudioOutput(self)
            self.player = QMediaPlayer(self)
            self.player.setAudioOutput(self.audio_output)
            self.player.setVideoOutput(self.video_widget)
            controls = QHBoxLayout()
            for text, callback in [("播放", self.play), ("暂停", self.pause), ("停止", self.stop), ("标记开始", self.mark_start), ("标记结束", self.mark_end)]:
                btn = QPushButton(text)
                btn.clicked.connect(callback)
                controls.addWidget(btn)
            selected_btn = QPushButton("选中文本建问题")
            selected_btn.clicked.connect(self.create_issue_from_selection)
            controls.addWidget(selected_btn)
            controls.addStretch()
            right_layout.addLayout(controls)
        else:
            right_layout.addWidget(QLabel("QtMultimedia 不可用，无法内置预览。"))
        splitter.addWidget(right)
        splitter.setSizes([520, 880])
        root.addWidget(splitter, 1)

        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setValue(0)
        root.addWidget(self.progress)

    def set_video(self, path):
        if self.player and path and os.path.exists(path):
            self.player.setSource(QUrl.fromLocalFile(path))

    def set_status(self, text, busy=True):
        self.status_label.setText(text)
        self.progress.setRange(0, 0 if busy else 100)
        if not busy:
            self.progress.setValue(100)

    def set_transcript(self, text, segments):
        segments = segments or []
        self.transcript_text.setPlainText(text or "")
        self.timeline_text.setPlainText("\n".join(
            f"{self._fmt_time(item.get('start', 0))} - {self._fmt_time(item.get('end', 0))}  {item.get('text', '')}"
            for item in segments
        ))
        duration = self._fmt_time(segments[-1].get("end", 0)) if segments else "未知"
        self.summary_text.setPlainText(
            f"完整转写已完成\n\n"
            f"转写片段数：{len(segments)}\n"
            f"覆盖时长：{duration}\n\n"
            f"可以点击“生成纲要”汇总本次讨论要点，也可以点击“整理到表格”把有明确问题的片段拆成审阅行。"
        )
        self.set_status("完整转写完成", busy=False)

    def set_summary(self, text):
        self.summary_text.setPlainText(text or "未生成纲要。")
        self.tabs.setCurrentWidget(self.summary_text)
        self.set_status("纲要已生成", busy=False)

    def _setup_issue_table(self):
        headers = ["开始", "结束", "原始讨论", "专业整理", "简化意见", "关键词", "部门", "状态"]
        self.issue_table.setColumnCount(len(headers))
        self.issue_table.setHorizontalHeaderLabels(headers)
        self.issue_table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.issue_table.horizontalHeader().setStretchLastSection(True)
        self.issue_table.setWordWrap(True)
        self.issue_table.setAlternatingRowColors(True)
        for col, width in enumerate([70, 70, 260, 260, 220, 140, 80, 80]):
            self.issue_table.setColumnWidth(col, width)

    def set_issues(self, issues):
        self.issues = list(issues or [])
        self.issue_table.setRowCount(len(self.issues))
        for row, issue in enumerate(self.issues):
            values = [
                self._fmt_time(issue.get("start", 0)),
                self._fmt_time(issue.get("end", 0)),
                issue.get("raw_discussion") or issue.get("discussion") or "",
                issue.get("meeting_note") or issue.get("full_review") or "",
                issue.get("simplified_review") or "",
                ", ".join(issue.get("keywords", []) or []),
                issue.get("department") or "未分类",
                issue.get("status") or "AI生成",
            ]
            for col, value in enumerate(values):
                self.issue_table.setItem(row, col, QTableWidgetItem(str(value)))
        self.tabs.setCurrentWidget(self.issue_table)
        self.set_status(f"已整理 {len(self.issues)} 条问题，请确认或手动补充", busy=False)

    def collect_issues(self):
        issues = []
        for row in range(self.issue_table.rowCount()):
            def cell(col):
                item = self.issue_table.item(row, col)
                return item.text().strip() if item else ""
            issue = {
                "start": self._parse_time(cell(0)),
                "end": self._parse_time(cell(1)),
                "raw_discussion": cell(2),
                "meeting_note": cell(3),
                "simplified_review": cell(4),
                "keywords": [part.strip() for part in cell(5).replace("，", ",").split(",") if part.strip()],
                "department": cell(6) or "未分类",
                "status": cell(7) or "用户确认",
            }
            if issue["end"] > issue["start"] and (issue["raw_discussion"] or issue["meeting_note"] or issue["simplified_review"]):
                issues.append(issue)
        return issues

    def add_manual_issue(self, issue):
        issues = self.collect_issues()
        issues.append(issue)
        self.set_issues(issues)

    def mark_start(self):
        self.mark_start_seconds = self.current_position_seconds()
        self.set_status(f"已标记开始：{self._fmt_time(self.mark_start_seconds)}", busy=False)

    def mark_end(self):
        end = self.current_position_seconds()
        start = self.mark_start_seconds if self.mark_start_seconds is not None else max(0, end - 10)
        if end <= start:
            end = start + 10
        text = self._text_for_range(start, end)
        issue = {
            "start": start,
            "end": end,
            "raw_discussion": text,
            "meeting_note": text,
            "simplified_review": "",
            "keywords": [],
            "department": "未分类",
            "status": "用户标记",
        }
        self.add_manual_issue(issue)
        self.manual_issue_requested.emit(issue)
        self.mark_start_seconds = None

    def create_issue_from_selection(self):
        selected = self.transcript_text.textCursor().selectedText().strip()
        if not selected:
            selected = self.timeline_text.textCursor().selectedText().strip()
        if not selected:
            QMessageBox.information(self, "提示", "请先在逐字稿或时间轴里选中一段文字。")
            return
        now = self.current_position_seconds()
        issue = {
            "start": max(0, now - 10),
            "end": now + 10,
            "raw_discussion": selected,
            "meeting_note": selected,
            "simplified_review": "",
            "keywords": [],
            "department": "未分类",
            "status": "用户标记",
        }
        self.add_manual_issue(issue)
        self.manual_issue_requested.emit(issue)

    def current_position_seconds(self):
        if self.player:
            return self.player.position() / 1000.0
        return 0.0

    def _text_for_range(self, start, end):
        lines = []
        for line in self.timeline_text.toPlainText().splitlines():
            if " - " not in line:
                continue
            try:
                start_text, rest = line.split(" - ", 1)
                end_text, text = rest.split("  ", 1)
                line_start = self._parse_time(start_text)
                line_end = self._parse_time(end_text)
                if line_end >= start and line_start <= end:
                    lines.append(text)
            except ValueError:
                continue
        return "\n".join(lines).strip()

    def play(self):
        if self.player:
            self.player.play()

    def pause(self):
        if self.player:
            self.player.pause()

    def stop(self):
        if self.player:
            self.player.stop()

    @staticmethod
    def _fmt_time(seconds):
        try:
            seconds = int(float(seconds))
        except (TypeError, ValueError):
            seconds = 0
        h = seconds // 3600
        m = (seconds % 3600) // 60
        s = seconds % 60
        return f"{h:02d}:{m:02d}:{s:02d}"

    @staticmethod
    def _parse_time(value):
        value = str(value).strip()
        try:
            if ":" not in value:
                return float(value)
            parts = [int(part) for part in value.split(":")]
            while len(parts) < 3:
                parts.insert(0, 0)
            return float(parts[-3] * 3600 + parts[-2] * 60 + parts[-1])
        except Exception:
            return 0.0
