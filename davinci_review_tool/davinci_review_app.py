# -*- coding: utf-8 -*-
import os
import sys
import threading

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from app_constants import DEFAULT_DEPARTMENTS
from davinci_review_tool.cgtw_client import CgtwClient, load_app_settings
from davinci_review_tool.resolve_adapter import ResolveAdapter
from davinci_review_tool.review_capture import ReviewCaptureSession, copy_references_to_entry


class DropReferenceList(QListWidget):
    files_dropped = Signal(list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setMinimumHeight(110)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        paths = [url.toLocalFile() for url in event.mimeData().urls() if url.toLocalFile()]
        if paths:
            self.files_dropped.emit(paths)
            event.acceptProposedAction()


class ReviewConfirmDialog(QDialog):
    def __init__(self, entry, parent=None):
        super().__init__(parent)
        self.entry = dict(entry or {})
        self.setWindowTitle("确认返修信息")
        self.resize(860, 620)

        layout = QVBoxLayout(self)
        header = QLabel(f"镜头: {self.entry.get('shot_number', '')}")
        header.setObjectName("DialogTitle")
        layout.addWidget(header)

        body = QSplitter(Qt.Horizontal)
        preview_panel = QWidget()
        preview_layout = QVBoxLayout(preview_panel)
        self.preview = QLabel("无截图")
        self.preview.setAlignment(Qt.AlignCenter)
        self.preview.setMinimumSize(300, 220)
        screenshot = self.entry.get("screenshot_path")
        if screenshot and os.path.exists(screenshot):
            pixmap = QPixmap(screenshot)
            self.preview.setPixmap(pixmap.scaled(420, 260, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        preview_layout.addWidget(self.preview)

        self.reference_list = DropReferenceList()
        self.reference_list.files_dropped.connect(self.add_reference_paths)
        preview_layout.addWidget(QLabel("参考文件 / 批注 / 录屏"))
        preview_layout.addWidget(self.reference_list)
        add_ref_button = QPushButton("添加参考文件")
        add_ref_button.clicked.connect(self.browse_references)
        preview_layout.addWidget(add_ref_button)
        body.addWidget(preview_panel)

        form_panel = QWidget()
        form = QVBoxLayout(form_panel)
        form.addWidget(QLabel("完整意见"))
        self.full_review_edit = QTextEdit()
        self.full_review_edit.setPlainText(self.entry.get("full_review", ""))
        form.addWidget(self.full_review_edit, 2)
        form.addWidget(QLabel("简化意见"))
        self.simplified_edit = QTextEdit()
        self.simplified_edit.setPlainText(self.entry.get("simplified_review", ""))
        self.simplified_edit.setMaximumHeight(110)
        form.addWidget(self.simplified_edit)
        row = QHBoxLayout()
        row.addWidget(QLabel("部门"))
        self.department_combo = QComboBox()
        self.department_combo.setEditable(True)
        self.department_combo.addItems(["未分类"] + DEFAULT_DEPARTMENTS)
        self.department_combo.setCurrentText(self.entry.get("department") or "未分类")
        row.addWidget(self.department_combo, 1)
        row.addWidget(QLabel("关键词"))
        self.keywords_edit = QTextEdit()
        self.keywords_edit.setMaximumHeight(54)
        keywords = self.entry.get("keywords") or []
        self.keywords_edit.setPlainText(", ".join(str(item) for item in keywords))
        row.addWidget(self.keywords_edit, 2)
        form.addLayout(row)
        body.addWidget(form_panel)
        body.setStretchFactor(0, 1)
        body.setStretchFactor(1, 2)
        layout.addWidget(body)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText("完成并同步 CGT")
        buttons.button(QDialogButtonBox.Cancel).setText("取消")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self._refresh_reference_list()

    def browse_references(self):
        paths, _ = QFileDialog.getOpenFileNames(self, "选择参考文件", "", "All Files (*.*)")
        self.add_reference_paths(paths)

    def add_reference_paths(self, paths):
        self.entry = copy_references_to_entry(paths, self.entry)
        self._refresh_reference_list()

    def _refresh_reference_list(self):
        self.reference_list.clear()
        paths = []
        paths.extend(self.entry.get("reference_files") or [])
        paths.extend(self.entry.get("media_files") or [])
        if self.entry.get("audio_path"):
            paths.append(self.entry["audio_path"])
        for path in paths:
            item = QListWidgetItem(os.path.basename(path))
            item.setToolTip(path)
            self.reference_list.addItem(item)

    def result_entry(self):
        entry = dict(self.entry)
        entry["full_review"] = self.full_review_edit.toPlainText().strip()
        entry["simplified_review"] = self.simplified_edit.toPlainText().strip()
        entry["department"] = self.department_combo.currentText().strip() or "未分类"
        entry["keywords"] = [
            part.strip()
            for part in self.keywords_edit.toPlainText().replace("，", ",").split(",")
            if part.strip()
        ]
        return entry


class StatusDialog(QDialog):
    def __init__(self, shot_number, tasks, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"{shot_number} - CGT 状态")
        self.resize(820, 420)
        layout = QVBoxLayout(self)
        title = QLabel(f"镜头全部 CGT 状态: {shot_number}")
        title.setObjectName("DialogTitle")
        layout.addWidget(title)
        table = QTableWidget()
        table.setColumnCount(6)
        table.setHorizontalHeaderLabels(["镜头", "Pipeline", "视效状态", "任务状态", "负责人", "更新时间"])
        table.setRowCount(len(tasks))
        for row, task in enumerate(tasks):
            values = [
                task.get("shot_number", ""),
                task.get("pipeline", ""),
                task.get("supervise_status", ""),
                task.get("task_status", ""),
                task.get("artist", ""),
                task.get("updated_at", ""),
            ]
            for col, value in enumerate(values):
                table.setItem(row, col, QTableWidgetItem(str(value or "")))
        table.resizeColumnsToContents()
        layout.addWidget(table)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok)
        buttons.accepted.connect(self.accept)
        layout.addWidget(buttons)


class DavinciReviewWindow(QMainWindow):
    tasks_loaded = Signal(list)
    cgt_status_loaded = Signal(list)
    worker_error = Signal(str)
    worker_message = Signal(str)
    approve_done = Signal(dict)
    retake_done = Signal(dict)

    def __init__(self):
        super().__init__()
        self.setWindowTitle("DaVinci CGT 审核标记")
        self.resize(1120, 680)
        self.settings = load_app_settings(ROOT_DIR)
        self.resolve = ResolveAdapter()
        self.cgtw = CgtwClient(self.settings)
        self.capture = ReviewCaptureSession(self.settings, self)
        self.current_clip_info = {}
        self.tasks = []
        self._build_ui()
        self._wire_signals()
        self.refresh_current_clip()
        self.refresh_cgt_status()

    def _build_ui(self):
        root = QWidget()
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)

        top = QFrame()
        top.setObjectName("TopBar")
        grid = QGridLayout(top)
        self.shot_label = QLabel("当前镜头: -")
        self.episode_label = QLabel("本集: -")
        self.cgt_status_label = QLabel("CGT: 未检测")
        self.refresh_current_button = QPushButton("刷新当前镜头")
        self.refresh_current_button.clicked.connect(self.refresh_current_clip)
        self.refresh_tasks_button = QPushButton("获取待 Check 列表")
        self.refresh_tasks_button.clicked.connect(self.refresh_check_tasks)
        grid.addWidget(self.shot_label, 0, 0)
        grid.addWidget(self.episode_label, 0, 1)
        grid.addWidget(self.cgt_status_label, 0, 2)
        grid.addWidget(self.refresh_current_button, 0, 3)
        grid.addWidget(self.refresh_tasks_button, 0, 4)
        layout.addWidget(top)

        splitter = QSplitter(Qt.Horizontal)
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.addWidget(QLabel("待 Check 任务"))
        self.task_table = QTableWidget()
        self.task_table.setColumnCount(6)
        self.task_table.setHorizontalHeaderLabels(["镜头", "Pipeline", "视效状态", "任务状态", "负责人", "更新时间"])
        self.task_table.cellClicked.connect(self.on_task_clicked)
        self.task_table.doubleClicked.connect(lambda _: self.jump_selected_task())
        left_layout.addWidget(self.task_table)
        splitter.addWidget(left)

        right = QWidget()
        right_layout = QVBoxLayout(right)
        self.approve_button = QPushButton("通过")
        self.approve_button.setObjectName("ApproveButton")
        self.approve_button.clicked.connect(self.approve_current_shot)
        self.retake_button = QPushButton("开始返修录制")
        self.retake_button.setObjectName("RetakeButton")
        self.retake_button.clicked.connect(self.toggle_retake_recording)
        self.annotate_button = QPushButton("截图批注")
        self.annotate_button.clicked.connect(self.capture.open_annotation_overlay)
        self.status_button = QPushButton("查询当前镜头全部状态")
        self.status_button.clicked.connect(self.query_current_shot_status)
        for button in [self.approve_button, self.retake_button, self.annotate_button, self.status_button]:
            right_layout.addWidget(button)
        right_layout.addWidget(QLabel("日志"))
        self.log = QTextEdit()
        self.log.setReadOnly(True)
        right_layout.addWidget(self.log, 1)
        splitter.addWidget(right)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 1)
        layout.addWidget(splitter, 1)
        self.setStyleSheet(APP_STYLE)

    def _wire_signals(self):
        self.tasks_loaded.connect(self.on_tasks_loaded)
        self.cgt_status_loaded.connect(self.on_status_loaded)
        self.worker_error.connect(self.show_error)
        self.worker_message.connect(self.append_log)
        self.approve_done.connect(self.on_approve_done)
        self.retake_done.connect(self.on_retake_done)
        self.capture.recording_started.connect(self.on_recording_started)
        self.capture.recording_stopped.connect(lambda: self.append_log("录制结束，正在转写和 AI 整理..."))
        self.capture.review_ready.connect(self.on_review_ready)
        self.capture.error_occurred.connect(self.show_error)

    def append_log(self, text):
        self.log.append(str(text))

    def show_error(self, text):
        self.append_log(f"错误: {text}")
        QMessageBox.warning(self, "提示", str(text))

    def refresh_cgt_status(self):
        status = self.cgtw.public_status()
        if status.get("ok"):
            self.cgt_status_label.setText(f"CGT: {status.get('db')} / {status.get('module')}")
        else:
            self.cgt_status_label.setText("CGT: 配置不完整")
            self.append_log("\n".join(status.get("errors") or []))

    def refresh_current_clip(self):
        try:
            self.current_clip_info = self.resolve.get_current_clip_info()
            self.shot_label.setText(f"当前镜头: {self.current_clip_info.get('shot_number')}")
            self.episode_label.setText(f"本集: {self.current_clip_info.get('episode')}")
            self.append_log(f"当前片段: {self.current_clip_info.get('clip_name')}")
        except Exception as exc:
            self.current_clip_info = {}
            self.shot_label.setText("当前镜头: -")
            self.episode_label.setText("本集: -")
            self.append_log(str(exc))

    def current_shot(self):
        if not self.current_clip_info:
            self.refresh_current_clip()
        shot = self.current_clip_info.get("shot_number")
        if not shot:
            raise RuntimeError("未识别到当前播放头镜头。")
        return shot

    def refresh_check_tasks(self):
        try:
            self.refresh_current_clip()
            episode = self.current_clip_info.get("episode")
            if not episode:
                raise RuntimeError("无法从当前播放头文件名解析本集。")
            self.append_log(f"正在查询 {episode} 待 Check 任务...")
            threading.Thread(target=self._load_tasks_worker, args=(episode,), daemon=True).start()
        except Exception as exc:
            self.show_error(str(exc))

    def _load_tasks_worker(self, episode):
        try:
            self.tasks_loaded.emit(self.cgtw.list_check_tasks(episode))
        except Exception as exc:
            self.worker_error.emit(str(exc))

    def on_tasks_loaded(self, tasks):
        self.tasks = tasks or []
        self.task_table.setRowCount(len(self.tasks))
        for row, task in enumerate(self.tasks):
            values = [
                task.get("shot_number", ""),
                task.get("pipeline", ""),
                task.get("supervise_status", ""),
                task.get("task_status", ""),
                task.get("artist", ""),
                task.get("updated_at", ""),
            ]
            for col, value in enumerate(values):
                item = QTableWidgetItem(str(value or ""))
                item.setData(Qt.UserRole, task)
                self.task_table.setItem(row, col, item)
        self.task_table.resizeColumnsToContents()
        self.append_log(f"待 Check 任务: {len(self.tasks)} 条")

    def on_task_clicked(self, row, _col):
        task = self._task_for_row(row)
        if task:
            self.jump_to_task(task)

    def jump_selected_task(self):
        row = self.task_table.currentRow()
        task = self._task_for_row(row)
        if task:
            self.jump_to_task(task)

    def _task_for_row(self, row):
        if 0 <= row < len(self.tasks):
            return self.tasks[row]
        return None

    def jump_to_task(self, task):
        shot = task.get("shot_number") or ""
        if self.resolve.jump_to_shot(shot):
            self.append_log(f"已跳转: {shot}")
            self.refresh_current_clip()
        else:
            self.show_error(f"时间线上未找到镜头: {shot}")

    def approve_current_shot(self):
        try:
            shot = self.current_shot()
            self.append_log(f"正在标记审核通过: {shot}")
            threading.Thread(target=self._approve_worker, args=(shot,), daemon=True).start()
        except Exception as exc:
            self.show_error(str(exc))

    def _approve_worker(self, shot):
        result = self.cgtw.approve_shot_from_resolve(shot)
        self.approve_done.emit({"shot_number": shot, "result": result})

    def on_approve_done(self, payload):
        result = payload.get("result") or {}
        shot = payload.get("shot_number")
        if result.get("success"):
            self.append_log(f"已审核通过: {shot}")
            self._remove_task_rows(shot)
        else:
            self.show_error(result.get("message") or str(result))

    def toggle_retake_recording(self):
        try:
            if self.capture.is_recording():
                self.capture.stop()
                self.retake_button.setText("开始返修录制")
                return
            shot = self.current_shot()
            self.capture.start(shot, record_video=True)
        except Exception as exc:
            self.show_error(str(exc))

    def on_recording_started(self, status):
        self.retake_button.setText("停止返修录制")
        self.append_log(status)

    def on_review_ready(self, entry):
        dialog = ReviewConfirmDialog(entry, self)
        if dialog.exec() != QDialog.Accepted:
            self.append_log("返修已取消，本地素材保留在临时目录。")
            return
        final_entry = dialog.result_entry()
        self.append_log(f"正在同步返修: {final_entry.get('shot_number')}")
        threading.Thread(target=self._retake_worker, args=(final_entry,), daemon=True).start()

    def _retake_worker(self, entry):
        result = self.cgtw.submit_retake_from_resolve(entry)
        self.retake_done.emit({"entry": entry, "result": result})

    def on_retake_done(self, payload):
        entry = payload.get("entry") or {}
        result = payload.get("result") or {}
        shot = entry.get("shot_number")
        if result.get("success"):
            self.append_log(f"返修已同步: {shot}")
            self._remove_task_rows(shot)
        else:
            self.show_error(result.get("message") or str(result))

    def query_current_shot_status(self):
        try:
            shot = self.current_shot()
            self.append_log(f"正在查询镜头全部状态: {shot}")
            threading.Thread(target=self._status_worker, args=(shot,), daemon=True).start()
        except Exception as exc:
            self.show_error(str(exc))

    def _status_worker(self, shot):
        try:
            self.cgt_status_loaded.emit(self.cgtw.get_shot_status(shot))
        except Exception as exc:
            self.worker_error.emit(str(exc))

    def on_status_loaded(self, tasks):
        shot = self.current_clip_info.get("shot_number", "")
        StatusDialog(shot, tasks or [], self).exec()

    def _remove_task_rows(self, shot):
        target = str(shot or "").lower()
        self.tasks = [task for task in self.tasks if str(task.get("shot_number", "")).lower() != target]
        self.on_tasks_loaded(self.tasks)


APP_STYLE = """
QMainWindow, QWidget { background: #181b20; color: #e8edf4; font-size: 10pt; }
#TopBar { background: #222832; border: 1px solid #3a4352; border-radius: 6px; }
#DialogTitle { font-size: 14pt; font-weight: 700; padding: 4px 0; }
QPushButton { background: #303846; border: 1px solid #516070; border-radius: 5px; padding: 9px 12px; }
QPushButton:hover { background: #3b4657; }
#ApproveButton { background: #1f6f43; border-color: #39a96b; font-weight: 700; }
#RetakeButton { background: #7b2d2d; border-color: #d75d5d; font-weight: 700; }
QTableWidget, QTextEdit, QListWidget, QComboBox { background: #111419; color: #e8edf4; border: 1px solid #3a4352; border-radius: 4px; }
QHeaderView::section { background: #2a313d; color: #e8edf4; padding: 5px; border: none; }
"""


def main():
    app = QApplication.instance() or QApplication(sys.argv)
    window = DavinciReviewWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())

