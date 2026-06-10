# -*- coding: utf-8 -*-
# --- START OF FILE main_app.py ---

import sys
import os
import time
import threading
import json
import re
import shutil
import subprocess
import urllib.error
import urllib.request
import ctypes
import wave
import logging
import contextlib
import io
import html
from ctypes import wintypes
from PIL import Image
from concurrent.futures import ThreadPoolExecutor

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QTableWidget, QTableWidgetItem, QToolBar, QHeaderView, QPushButton, QLabel,
    QComboBox, QMessageBox, QSystemTrayIcon, QMenu, QGridLayout, QCheckBox, QStyle,
    QProgressBar, QProgressDialog, QFileDialog, QToolButton, QLineEdit, QStackedWidget, QButtonGroup,
    QSplitter, QTreeWidget, QTreeWidgetItem, QTextEdit
)
from PySide6.QtGui import QAction, QIcon, QKeySequence, QPixmap
from PySide6.QtCore import Qt, QEvent, Signal, QTimer, QMimeData, QUrl
import shiboken6

from settings_dialog import SettingsDialog
from ai_processor import AIProcessor, LOCAL_AI_PROVIDERS
from ui_components import HelpDialog, DoodleEditor, CropWindow, RecordingIndicator, AnnotationOverlay, LongVideoTranscriptionDialog, ReviewModePanel
from recording_manager import RecordingManager, check_ffmpeg_availability
from project_manager import ProjectManager
from export_manager import export_to_excel
from video_export_manager import export_merged_video
from cgtw_sync import (
    default_cgtw_settings,
    get_cgtw_settings,
    prepare_cgtw_payload,
    run_cgtw_sync,
    summarize_payload,
    validate_cgtw_settings,
)
from cgtw_bridge_server import CgtwBridgeServer
import ocr_utils

import socket
import websocket_receiver

# --- 事件定义 ---
ADD_REVIEW_EVENT_TYPE = QEvent.Type(QEvent.User + 1)
AI_UPDATE_EVENT_TYPE = QEvent.Type(QEvent.User + 2)
TRANSCRIPTION_DONE_EVENT_TYPE = QEvent.Type(QEvent.User + 3)
EXPORT_STATUS_EVENT_TYPE = QEvent.Type(QEvent.User + 4)
RETRY_OCR_DONE_EVENT_TYPE = QEvent.Type(QEvent.User + 5)
PROJECT_STATUS_EVENT_TYPE = QEvent.Type(QEvent.User + 6)
MOBILE_START_RECORDING_EVENT_TYPE = QEvent.Type(QEvent.User + 7)
MOBILE_STOP_RECORDING_EVENT_TYPE = QEvent.Type(QEvent.User + 8)
VIDEO_EXPORT_STATUS_EVENT_TYPE = QEvent.Type(QEvent.User + 9)
LONG_VIDEO_IMPORT_EVENT_TYPE = QEvent.Type(QEvent.User + 10)
LONG_VIDEO_SEGMENTS_EVENT_TYPE = QEvent.Type(QEvent.User + 11)
LONG_VIDEO_SUMMARY_EVENT_TYPE = QEvent.Type(QEvent.User + 12)
LONG_VIDEO_ISSUES_EVENT_TYPE = QEvent.Type(QEvent.User + 13)
MODEL_LOAD_STATUS_EVENT_TYPE = QEvent.Type(QEvent.User + 14)
CGTW_SYNC_STATUS_EVENT_TYPE = QEvent.Type(QEvent.User + 15)
CGTW_SYNC_PROGRESS_EVENT_TYPE = QEvent.Type(QEvent.User + 16)

def resource_path(relative_path):
    portable_path = os.path.join(app_base_path(), relative_path)
    if os.path.exists(portable_path):
        return portable_path
    if hasattr(sys, '_MEIPASS'):
        bundled_path = os.path.join(sys._MEIPASS, relative_path)
        if os.path.exists(bundled_path):
            return bundled_path
    return os.path.join(os.path.abspath("."), relative_path)

def app_base_path():
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))

def funasr_source_path():
    portable_path = os.path.join(app_base_path(), "FunASR-main")
    if os.path.isdir(portable_path):
        return portable_path
    return os.path.abspath(os.path.join(app_base_path(), "..", "FunASR-main"))

def funasr_cached_model_path(model_folder_name, fallback_name):
    model_path = os.path.join(app_base_path(), "FunASR_models", "models", "iic", model_folder_name)
    if os.path.isdir(model_path):
        return model_path
    return fallback_name

DEFAULT_LOCAL_AI_BASE_URL = "http://127.0.0.1:8080/v1"
DEFAULT_QWEN_MODEL = "Qwen3VL-8B-Instruct-Q4_K_M.gguf"
QWEN_MODEL_DIR = "Qwen3-VL-8B"
LLAMA_CPP_DIR = "llama-cpp"
PREFERRED_LOCAL_MODEL_ROOTS = [r"G:\模型"]
WM_HOTKEY = 0x0312
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_ALT = 0x0001
HOTKEY_REVIEW_ID = 1001
HOTKEY_ANNOTATION_ID = 1002
VK_A = 0x41
VK_R = 0x52

COL_SCREENSHOT = 0
COL_EPISODE = 1
COL_SCENE = 2
COL_TIMESTAMP = 3
COL_SHOT = 4
COL_SOURCE = 5
COL_FULL_REVIEW = 6
COL_SIMPLIFIED = 7
COL_KEYWORDS = 8
COL_DEPARTMENT = 9
COL_STATUS = 10
COL_REFERENCE = 11
COL_MEDIA = 12

INPUT_TABLE_COLUMNS = [
    COL_SCREENSHOT,
    COL_TIMESTAMP,
    COL_SHOT,
    COL_FULL_REVIEW,
    COL_SIMPLIFIED,
    COL_KEYWORDS,
    COL_DEPARTMENT,
    COL_REFERENCE,
    COL_MEDIA,
]

def apply_app_stylesheet(app, theme="light"):
    stylesheet_name = "style_dark.qss" if theme == "dark" else "style.qss"
    try:
        with open(resource_path(stylesheet_name), "r", encoding="utf-8") as f:
            app.setStyleSheet(f.read())
    except FileNotFoundError:
        print(f"Style file not found: {stylesheet_name}")
        app.setStyleSheet("")

class CustomEvent(QEvent):
    def __init__(self, data, event_type):
        super().__init__(event_type)
        self.data = data

class MainWindow(QMainWindow):
    hotkey_pressed_signal = Signal()
    annotation_hotkey_signal = Signal()

    def __init__(self):
        super().__init__()
        self.setWindowTitle("协同审阅平台 v3.0")
        self.setGeometry(100, 100, 1200, 450)
        self.is_transcribing_batch = False
        self.is_ai_processing = False
        self.is_packing = False
        self.is_video_exporting = False
        self.is_cgtw_syncing = False
        self.cgtw_bridge_server = None
        self.local_ai_process = None
        self._local_ai_launching = False
        self._registered_hotkeys = []
        self.long_video_dialogs = {}
        self.settings = self.load_settings()
        self.current_view_mode = "input"
        self._transcription_loading = False
        self._transcription_loading_name = None
        self._transcription_model_status = "未加载"
        self._restoring_table_layout = False
        self._table_layout_save_timer = QTimer(self)
        self._table_layout_save_timer.setSingleShot(True)
        self._table_layout_save_timer.timeout.connect(self.save_settings)
        apply_app_stylesheet(QApplication.instance(), self.settings.get("theme", "light"))

        ffmpeg_executable_path = check_ffmpeg_availability(self.settings)
        if ffmpeg_executable_path:
            ffmpeg_dir = os.path.dirname(ffmpeg_executable_path)
            os.environ["PATH"] = ffmpeg_dir + os.pathsep + os.environ.get("PATH", "")
            print(f"INFO: 已将 FFmpeg 目录添加到 PATH: {ffmpeg_dir}")
        else:
            print("WARNING: FFmpeg not found. Video features may fail.")

        self.recording_manager = RecordingManager(self.settings, self)
        self.project_manager = ProjectManager(self)
        self.whisper_model = None
        self._transcription_model_name = None
        self._whisper_loading_lock = threading.Lock()
        self._whisper_load_error = None
        self.setup_ui()
        self.setup_connections()
        self.start_cgtw_bridge_server()
        QTimer.singleShot(3000, self.start_background_services_on_app_start)
        QTimer.singleShot(0, self.setup_hotkey_listener)
        self.mobile_text_override = None
        self.websocket_server = None
        self.mobile_connection_active = False
        self._is_updating_table = False
        self._current_cell_value = None
        self.annotation_overlay = None
        self._annotation_capture_busy = False
        self._quiet_capture_state = None
        
    def setup_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        self.setup_toolbar()
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("搜索镜头号、意见、关键词...")
        self.episode_filter = QComboBox()
        self.episode_filter.addItem("全部集号")
        self.scene_filter = QComboBox()
        self.scene_filter.addItem("全部场号")
        self.department_filter = QComboBox()
        self.department_filter.addItem("全部部门")
        self.department_filter.addItems(self.settings.get("departments", []))
        self.status_filter = QComboBox()
        self.status_filter.addItems(["全部状态", "待转写", "待AI", "待处理", "已完成", "已通过"])
        filter_layout = QHBoxLayout()
        filter_layout.addWidget(QLabel("搜索:"))
        filter_layout.addWidget(self.search_input, 1)
        filter_layout.addWidget(QLabel("集号:"))
        filter_layout.addWidget(self.episode_filter)
        filter_layout.addWidget(QLabel("场号:"))
        filter_layout.addWidget(self.scene_filter)
        filter_layout.addWidget(QLabel("部门:"))
        filter_layout.addWidget(self.department_filter)
        filter_layout.addWidget(QLabel("状态:"))
        filter_layout.addWidget(self.status_filter)
        main_layout.addLayout(filter_layout)

        self.content_stack = QStackedWidget()
        self.input_page = QWidget()
        input_layout = QVBoxLayout(self.input_page)
        input_layout.setContentsMargins(0, 0, 0, 0)
        input_layout.addWidget(QLabel("当前录入"))
        self.latest_table = QTableWidget()
        self.setup_latest_table()
        input_layout.addWidget(self.latest_table)
        self.content_stack.addWidget(self.input_page)

        self.review_mode_panel = ReviewModePanel(self._resolve_temp_path, self.open_file, self)
        self.content_stack.addWidget(self.review_mode_panel)

        self.table_page = QWidget()
        table_layout = QVBoxLayout(self.table_page)
        table_layout.setContentsMargins(0, 0, 0, 0)
        self.review_table = QTableWidget()
        self.setup_review_table()
        table_layout.addWidget(self.review_table)
        self.content_stack.addWidget(self.table_page)

        self.history_page = self.create_history_page()
        self.content_stack.addWidget(self.history_page)
        main_layout.addWidget(self.content_stack)
        self.volume_bar = QProgressBar()
        self.volume_bar.setRange(0, 100)
        self.volume_bar.setValue(0)
        self.volume_bar.setTextVisible(False)
        self.volume_bar.setFixedSize(120, 16)
        self.statusBar().addPermanentWidget(self.volume_bar)
        self.volume_bar.hide()
        self.statusBar().hide()
        self.setup_tray_icon()
        self.recording_indicator = RecordingIndicator()

    def setup_toolbar(self):
        self.toolbar = QToolBar("Main Toolbar")
        self.addToolBar(self.toolbar)
        self.record_toggle_action = QAction("开始录制", self)
        self.record_toggle_action.setToolTip("开始/停止审阅录制")
        self.toolbar.addAction(self.record_toggle_action)
        self.record_video_checkbox = QCheckBox("录制视频")
        self.record_video_checkbox.setChecked(True)
        self.toolbar.addWidget(self.record_video_checkbox)
        self.recording_status_label = QLabel("未录制")
        self.recording_status_label.setStyleSheet("QLabel { color: #7a7f87; font-weight: 700; padding: 2px 8px; }")
        self.toolbar.addWidget(self.recording_status_label)
        self.update_toolbar_state()
        self.toolbar.addSeparator()
        self.view_mode_group = QButtonGroup(self)
        self.view_mode_group.setExclusive(True)
        self.input_mode_button = QToolButton()
        self.input_mode_button.setText("录入")
        self.input_mode_button.setCheckable(True)
        self.input_mode_button.setChecked(True)
        self.review_mode_button = QToolButton()
        self.review_mode_button.setText("审阅")
        self.review_mode_button.setCheckable(True)
        self.table_mode_button = QToolButton()
        self.table_mode_button.setText("表格")
        self.table_mode_button.setCheckable(True)
        self.history_mode_button = QToolButton()
        self.history_mode_button.setText("历史")
        self.history_mode_button.setCheckable(True)
        self.view_mode_group.addButton(self.input_mode_button)
        self.view_mode_group.addButton(self.review_mode_button)
        self.view_mode_group.addButton(self.table_mode_button)
        self.view_mode_group.addButton(self.history_mode_button)
        self.toolbar.addWidget(self.input_mode_button)
        self.toolbar.addWidget(self.review_mode_button)
        self.toolbar.addWidget(self.table_mode_button)
        self.toolbar.addWidget(self.history_mode_button)
        self.cgtw_sync_action = QAction("同步到 CGTeamWork", self)
        self.toolbar.addAction(self.cgtw_sync_action)
        self.toolbar.addSeparator()
        self.new_action = QAction("新建", self, shortcut=QKeySequence.StandardKey.New)
        self.save_action = QAction("保存", self, shortcut=QKeySequence.StandardKey.Save)
        self.open_action = QAction("打开", self, shortcut=QKeySequence.StandardKey.Open)
        self.open_project_folder_action = QAction("打开工程文件夹", self)
        self.pack_action = QAction("打包项目", self)
        self.web_viewer_action = QAction("网页预览器", self)
        self.append_revpack_action = QAction("追加导入 revpack", self)
        self.merge_action = QAction("合并相同镜头", self)
        self.annotation_action = QAction("截图批注", self)
        self.import_long_video_action = QAction("导入长视频", self)
        self.transcribe_all_action = QAction("全部转录", self)
        self.ai_process_action = QAction("AI处理", self)
        self.ai_rewrite_selected_action = QAction("AI优化选中", self)
        self.export_action = QAction("导出Excel", self)
        self.export_video_action = QAction("合并导出视频", self)
        self.settings_action = QAction("设置", self)
        self.undo_action = QAction("撤销", self, shortcut=QKeySequence("Ctrl+Z"), enabled=False)
        self.redo_action = QAction("重做", self, shortcut=QKeySequence("Ctrl+Y"), enabled=False)
        self.help_action = QAction("帮助", self)
        self.mobile_connection_action = QAction("手机连接", self)
        self.mobile_connection_action.setCheckable(True)
        self.recent_project_actions = []
        for index in range(5):
            action = QAction(self)
            action.setVisible(False)
            action.triggered.connect(lambda checked=False, i=index: self.open_recent_project(i))
            self.recent_project_actions.append(action)
        self._add_toolbar_menu("项目", [
            self.new_action,
            self.open_action,
            *self.recent_project_actions,
            None,
            self.append_revpack_action,
            self.save_action,
            self.open_project_folder_action,
            self.pack_action,
            self.web_viewer_action,
        ])
        self._add_toolbar_menu("审阅", [
            self.merge_action,
            self.annotation_action,
            self.import_long_video_action,
            self.transcribe_all_action,
        ])
        self._add_toolbar_menu("AI", [
            self.ai_process_action,
            self.ai_rewrite_selected_action,
        ])
        self._add_toolbar_menu("导出", [
            self.export_action,
            self.export_video_action,
        ])
        self._add_toolbar_menu("工具", [
            self.settings_action,
            self.undo_action,
            self.redo_action,
            self.mobile_connection_action,
            self.help_action,
        ])
        self.toolbar.addSeparator()
        self.toolbar.addWidget(QLabel("语音模型:"))
        self.whisper_model_selector = QComboBox()
        self.whisper_model_selector.addItems(["funasr-paraformer-zh"])
        self.whisper_model_selector.setCurrentText(self.settings.get("selected_model", "funasr-paraformer-zh"))
        self.toolbar.addWidget(self.whisper_model_selector)
        self.model_status_label = QLabel("模型: 未加载")
        self.model_status_label.setStyleSheet("QLabel { color: #7a7f87; padding: 2px 8px; }")
        self.toolbar.addWidget(self.model_status_label)
        integration_menu = QMenu(self)
        integration_menu.addAction(self.cgtw_sync_action)
        integration_menu.addSeparator()
        premiere_action = QAction("Premiere", self, enabled=False)
        resolve_action = QAction("DaVinci Resolve", self, enabled=False)
        db_action = QAction("数据库", self, enabled=False)
        integration_menu.addAction(premiere_action)
        integration_menu.addAction(resolve_action)
        integration_menu.addAction(db_action)
        self._add_toolbar_menu("对接流程", integration_menu.actions())
        self.toolbar.addSeparator()
        self.update_recent_project_actions()

    def _add_toolbar_menu(self, title, actions):
        button = QToolButton(self)
        button.setText(title)
        button.setPopupMode(QToolButton.InstantPopup)
        menu = QMenu(button)
        for action in actions:
            if action is None:
                menu.addSeparator()
            else:
                menu.addAction(action)
        button.setMenu(menu)
        self.toolbar.addWidget(button)
        return button

    def update_recent_project_actions(self):
        if not hasattr(self, "recent_project_actions"):
            return
        recent = [path for path in self.settings.get("recent_projects", []) if path and os.path.exists(path)]
        self.settings["recent_projects"] = recent[:5]
        for index, action in enumerate(self.recent_project_actions):
            if index < len(recent):
                path = recent[index]
                action.setText(f"最近 {index + 1}: {os.path.basename(path)}")
                action.setToolTip(path)
                action.setData(path)
                action.setVisible(True)
                action.setEnabled(True)
            else:
                action.setText(f"最近 {index + 1}: 空")
                action.setToolTip("")
                action.setData("")
                action.setVisible(False)

    def add_recent_project(self, path):
        if not path:
            return
        abs_path = os.path.abspath(path)
        recent = [item for item in self.settings.get("recent_projects", []) if os.path.abspath(item) != abs_path]
        recent.insert(0, abs_path)
        self.settings["recent_projects"] = recent[:5]
        self.update_recent_project_actions()
        self.save_settings()

    def open_recent_project(self, index):
        if not (0 <= index < len(getattr(self, "recent_project_actions", []))):
            return
        path = self.recent_project_actions[index].data()
        if not path:
            return
        if not os.path.exists(path):
            QMessageBox.warning(self, "工程不存在", f"最近工程已不存在:\n{path}")
            self.settings["recent_projects"] = [item for item in self.settings.get("recent_projects", []) if item != path]
            self.update_recent_project_actions()
            self.save_settings()
            return
        self.project_manager.load_projects([path])
        self.add_recent_project(path)

    def update_toolbar_state(self):
        if hasattr(self, "cgtw_sync_action"):
            self.cgtw_sync_action.setEnabled(bool(get_cgtw_settings(self.settings).get("enabled", True)) and not self.is_cgtw_syncing)
        if not self.recording_manager.is_mss_available():
            self.record_video_checkbox.setToolTip("错误: mss 库未安装")
            self.record_video_checkbox.setEnabled(False)
        elif not self.recording_manager.is_ffmpeg_available:
            self.record_video_checkbox.setToolTip("未找到 FFmpeg，请在设置中配置路径。")
            self.record_video_checkbox.setEnabled(False)
        else:
            self.record_video_checkbox.setToolTip("勾选时录制视频和音频。")
            self.record_video_checkbox.setEnabled(True)
    
    def setup_connections(self):
        self.hotkey_pressed_signal.connect(self.toggle_review_capture)
        self.record_toggle_action.triggered.connect(self.toggle_review_capture)
        self.input_mode_button.clicked.connect(lambda: self.set_view_mode("input"))
        self.review_mode_button.clicked.connect(lambda: self.set_view_mode("review"))
        self.table_mode_button.clicked.connect(lambda: self.set_view_mode("table"))
        self.history_mode_button.clicked.connect(lambda: self.set_view_mode("history"))
        self.review_mode_panel.entry_selected.connect(self.select_review_row_from_review_mode)
        self.annotation_hotkey_signal.connect(self.open_recording_annotation_overlay)
        self.new_action.triggered.connect(self.project_manager.new_project)
        self.save_action.triggered.connect(self.handle_save_project)
        self.open_action.triggered.connect(self.handle_open_project)
        self.open_project_folder_action.triggered.connect(self.open_project_folder)
        self.append_revpack_action.triggered.connect(self.handle_append_revpack)
        self.pack_action.triggered.connect(self.handle_pack_project)
        self.web_viewer_action.triggered.connect(self.open_web_viewer)
        self.merge_action.triggered.connect(self.project_manager.merge_duplicate_shots)
        self.annotation_action.triggered.connect(self.open_recording_annotation_overlay)
        self.import_long_video_action.triggered.connect(self.import_long_video_review)
        self.transcribe_all_action.triggered.connect(self.transcribe_all_pending)
        self.ai_process_action.triggered.connect(self.process_all_reviews_with_ai)
        self.ai_rewrite_selected_action.triggered.connect(self.process_selected_review_with_ai)
        self.export_action.triggered.connect(self.handle_export)
        self.export_video_action.triggered.connect(self.handle_export_merged_video)
        self.cgtw_sync_action.triggered.connect(self.handle_cgtw_sync)
        self.settings_action.triggered.connect(self.open_settings)
        self.undo_action.triggered.connect(self.project_manager.undo)
        self.redo_action.triggered.connect(self.project_manager.redo)
        self.whisper_model_selector.currentTextChanged.connect(self.on_model_changed)
        self.help_action.triggered.connect(lambda: HelpDialog(self).exec())
        self.mobile_connection_action.triggered.connect(self.toggle_mobile_connection)
        self.review_table.doubleClicked.connect(self.handle_table_double_click)
        self.review_table.customContextMenuRequested.connect(self.show_table_context_menu)
        self.review_table.currentCellChanged.connect(self.on_table_current_cell_changed)
        self.latest_table.doubleClicked.connect(self.handle_input_table_double_click)
        self.latest_table.customContextMenuRequested.connect(self.show_input_table_context_menu)
        self.recording_manager.recording_finished.connect(self.on_recording_finished)
        self.recording_manager.volume_updated.connect(self.update_volume_bar)
        self.recording_manager.error_occurred.connect(self.handle_recording_error)
        self.review_table.cellPressed.connect(self.store_cell_value_on_press)
        self.review_table.itemChanged.connect(self.handle_item_changed)
        self.latest_table.cellPressed.connect(self.store_input_cell_value_on_press)
        self.latest_table.itemChanged.connect(self.handle_input_item_changed)
        self.search_input.textChanged.connect(self.apply_filters)
        self.episode_filter.currentTextChanged.connect(self.on_episode_filter_changed)
        self.scene_filter.currentTextChanged.connect(self.apply_filters)
        self.department_filter.currentTextChanged.connect(self.apply_filters)
        self.status_filter.currentTextChanged.connect(self.apply_filters)
    
    def setup_review_table(self):
        self.review_table.setColumnCount(len(self.review_table_headers()))
        self.review_table.setHorizontalHeaderLabels(self.review_table_headers())
        header = self.review_table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.Interactive)
        header.setStretchLastSection(False)
        default_widths = self._default_table_column_widths()
        for col, width in enumerate(default_widths):
            self.review_table.setColumnWidth(col, width)
        self.review_table.setWordWrap(True)
        self.review_table.verticalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.review_table.verticalHeader().setDefaultSectionSize(self.settings.get("table_default_row_height", 110))
        self.review_table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.review_table.setAlternatingRowColors(True)
        self.review_table.setEditTriggers(
            QTableWidget.EditTrigger.DoubleClicked
            | QTableWidget.EditTrigger.EditKeyPressed
            | QTableWidget.EditTrigger.SelectedClicked
        )
        header.sectionResized.connect(self.on_table_column_resized)
        self.review_table.verticalHeader().sectionResized.connect(self.on_table_row_resized)
        QTimer.singleShot(0, self.apply_saved_table_layout)

    def setup_latest_table(self):
        self.latest_table.setColumnCount(len(INPUT_TABLE_COLUMNS))
        self.latest_table.setHorizontalHeaderLabels([
            self.review_table_headers()[col] for col in INPUT_TABLE_COLUMNS
        ])
        self.latest_table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.latest_table.setWordWrap(True)
        self.latest_table.verticalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.latest_table.setEditTriggers(
            QTableWidget.EditTrigger.DoubleClicked
            | QTableWidget.EditTrigger.EditKeyPressed
            | QTableWidget.EditTrigger.SelectedClicked
        )
        self.latest_table.setAlternatingRowColors(True)
        self.latest_table.setContextMenuPolicy(Qt.CustomContextMenu)
        widths = [self._default_table_column_widths()[col] for col in INPUT_TABLE_COLUMNS]
        for col, width in enumerate(widths):
            self.latest_table.setColumnWidth(col, min(width, 260))

    def review_table_headers(self):
        return ["截图", "集号", "场号", "时间码", "镜头号", "revpack地址", "完整意见", "简化意见", "关键词", "部门", "状态", "参考", "媒体"]

    def create_history_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        splitter = QSplitter(Qt.Horizontal)
        self.history_tree = QTreeWidget()
        self.history_tree.setHeaderLabels(["镜头归宗", "版本"])
        self.history_tree.itemSelectionChanged.connect(self.on_history_selection_changed)
        self.history_tree.itemDoubleClicked.connect(lambda item, col: self.open_history_selected_version())
        splitter.addWidget(self.history_tree)

        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(6, 0, 0, 0)
        header_layout = QHBoxLayout()
        self.history_title = QLabel("未选择镜头")
        self.history_title.setStyleSheet("font-weight: 700;")
        self.history_review_button = QPushButton("审阅当前版本")
        self.history_review_button.clicked.connect(self.open_history_selected_version)
        header_layout.addWidget(self.history_title, 1)
        header_layout.addWidget(self.history_review_button)
        right_layout.addLayout(header_layout)

        self.history_versions_table = QTableWidget()
        self.history_versions_table.setColumnCount(7)
        self.history_versions_table.setHorizontalHeaderLabels(["版本", "来源", "时间码", "部门", "状态", "完整意见", "整理结果"])
        self.history_versions_table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.history_versions_table.horizontalHeader().setStretchLastSection(True)
        self.history_versions_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.history_versions_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.history_versions_table.doubleClicked.connect(lambda index: self.open_history_selected_version())
        right_layout.addWidget(self.history_versions_table, 1)

        self.history_detail = QTextEdit()
        self.history_detail.setReadOnly(True)
        self.history_detail.setMinimumHeight(120)
        right_layout.addWidget(self.history_detail)
        splitter.addWidget(right_panel)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 3)
        layout.addWidget(splitter)
        return page

    def _default_table_column_widths(self):
        return [132, 92, 92, 116, 150, 190, 320, 240, 150, 110, 92, 130, 130]

    def _default_table_column_ratios(self):
        widths = self._default_table_column_widths()
        total = sum(widths)
        return [width / total for width in widths]

    def _normalized_table_column_ratios(self):
        ratios = self.settings.get("table_column_ratios")
        if isinstance(ratios, list) and len(ratios) == self.review_table.columnCount():
            try:
                ratios = [max(float(value), 0.01) for value in ratios]
                total = sum(ratios)
                if total > 0:
                    return [value / total for value in ratios]
            except (TypeError, ValueError):
                pass
        widths = self.settings.get("table_column_widths")
        if isinstance(widths, list) and len(widths) == self.review_table.columnCount():
            try:
                widths = [max(int(value), 20) for value in widths]
                total = sum(widths)
                if total > 0:
                    return [value / total for value in widths]
            except (TypeError, ValueError):
                pass
        return self._default_table_column_ratios()

    def _available_table_width(self):
        width = self.review_table.viewport().width()
        if width <= 0:
            width = self.review_table.width()
        return max(width - 4, 600)

    def apply_saved_table_layout(self):
        if not hasattr(self, "review_table"):
            return
        self._restoring_table_layout = True
        try:
            ratios = self._normalized_table_column_ratios()
            available_width = self._available_table_width()
            min_widths = [80, 70, 70, 90, 110, 120, 180, 160, 100, 90, 80, 100, 100]
            widths = [max(min_widths[i], int(available_width * ratios[i])) for i in range(self.review_table.columnCount())]
            overflow = sum(widths) - available_width
            if overflow > 0:
                for col in sorted(range(len(widths)), key=lambda i: widths[i] - min_widths[i], reverse=True):
                    reducible = widths[col] - min_widths[col]
                    reduction = min(reducible, overflow)
                    widths[col] -= reduction
                    overflow -= reduction
                    if overflow <= 0:
                        break
            for col, width in enumerate(widths):
                self.review_table.setColumnWidth(col, width)
            self.apply_saved_table_row_heights()
        finally:
            self._restoring_table_layout = False

    def apply_saved_table_row_heights(self):
        row_heights = self.settings.get("table_row_heights", {})
        if not isinstance(row_heights, dict):
            return
        self._restoring_table_layout = True
        try:
            for row in range(self.project_manager.get_entry_count()):
                key = self._table_row_key(row)
                height = row_heights.get(key)
                if isinstance(height, int) and height > 0:
                    self.review_table.setRowHeight(row, height)
        finally:
            self._restoring_table_layout = False

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "review_table"):
            self.apply_saved_table_layout()

    def showEvent(self, event):
        super().showEvent(event)
        if hasattr(self, "review_table"):
            QTimer.singleShot(0, self.apply_saved_table_layout)

    def _table_row_key(self, row):
        if 0 <= row < self.project_manager.get_entry_count():
            entry = self.project_manager.review_entries[row]
            for field in ("screenshot_path", "audio_path", "timestamp", "shot_number"):
                value = entry.get(field)
                if value:
                    return f"{field}:{value}"
        return f"row:{row}"

    def on_table_column_resized(self, logical_index, old_size, new_size):
        if self._restoring_table_layout or not hasattr(self, "review_table"):
            return
        widths = [self.review_table.columnWidth(col) for col in range(self.review_table.columnCount())]
        total = sum(widths)
        if total <= 0:
            return
        self.settings["table_column_widths"] = widths
        self.settings["table_column_ratios"] = [width / total for width in widths]
        self._queue_table_layout_save()

    def on_table_row_resized(self, logical_index, old_size, new_size):
        if self._restoring_table_layout or logical_index < 0:
            return
        self.settings["table_default_row_height"] = self.review_table.verticalHeader().defaultSectionSize()
        row_heights = self.settings.setdefault("table_row_heights", {})
        if isinstance(row_heights, dict):
            row_heights[self._table_row_key(logical_index)] = int(new_size)
        self._queue_table_layout_save()

    def _queue_table_layout_save(self):
        self._table_layout_save_timer.start(500)
        
    def setup_tray_icon(self):
        self.tray_icon = QSystemTrayIcon(self)
        icon_path = resource_path("icon.png")
        if os.path.exists(icon_path):
            self.tray_icon.setIcon(QIcon(icon_path))
        else:
            self.tray_icon.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_MessageBoxInformation))
        tray_menu = QMenu()
        show_action = tray_menu.addAction("显示/隐藏窗口")
        show_action.triggered.connect(self.toggle_window_visibility)
        tray_menu.addSeparator()
        quit_action = tray_menu.addAction("退出")
        quit_action.triggered.connect(self.close)
        self.tray_icon.setContextMenu(tray_menu)
        self.tray_icon.show()
        self.tray_icon.setToolTip("协同审阅平台\nCtrl+R: 审阅")

    def _create_highlighted_label(self, text, keywords):
        label = QLabel()
        if not text:
            label.setText("")
            return label
        highlighted_text = text
        for keyword in keywords:
            highlighted_text = highlighted_text.replace(keyword, f'<font color="#e06c75">{keyword}</font>')
        label.setText(highlighted_text)
        label.setTextFormat(Qt.RichText)
        label.setWordWrap(True)
        label.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        label.setContentsMargins(4, 4, 4, 4)
        return label

    def entry_source_label(self, entry):
        return entry.get("source_revpack") or entry.get("source_project") or os.path.basename(self.project_manager.current_project_file or "") or "-"

    def entry_keywords_text(self, entry):
        keywords = entry.get("keywords", [])
        if isinstance(keywords, str):
            return keywords
        return ", ".join(keywords or [])

    def entry_keyword_list(self, entry):
        keywords = entry.get("keywords", [])
        if isinstance(keywords, str):
            return [part.strip() for part in re.split(r"[,，、\s]+", keywords) if part.strip()]
        return [str(part).strip() for part in (keywords or []) if str(part).strip()]

    def _highlighted_entry_html(self, text, entry):
        raw = str(text or "")
        if not raw:
            return ""

        terms = []
        for term in ("发现通过", "已通过", "通过"):
            terms.append((term, "approved"))
        for keyword in self.entry_keyword_list(entry):
            terms.append((keyword, "keyword"))

        matches = []
        for term, kind in terms:
            if not term:
                continue
            for match in re.finditer(re.escape(term), raw, re.IGNORECASE):
                matches.append((match.start(), match.end(), kind))
        if not matches:
            return html.escape(raw).replace("\n", "<br>")

        pieces = []
        cursor = 0
        for start, end, kind in sorted(matches, key=lambda item: (item[0], -(item[1] - item[0]))):
            if start < cursor:
                continue
            pieces.append(html.escape(raw[cursor:start]))
            color = "#2e9d57" if kind == "approved" else "#d93025"
            pieces.append(f'<span style="color: {color}; font-weight: 700;">{html.escape(raw[start:end])}</span>')
            cursor = end
        pieces.append(html.escape(raw[cursor:]))
        return "".join(pieces).replace("\n", "<br>")

    def _make_input_text_label(self, text, entry=None, rich=False):
        label = QLabel()
        label.setWordWrap(True)
        label.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        label.setContentsMargins(4, 4, 4, 4)
        if rich and entry is not None:
            label.setText(self._highlighted_entry_html(text, entry))
            label.setTextFormat(Qt.RichText)
        else:
            label.setText(str(text or ""))
        return label

    def populate_row(self, row, data):
        self._is_updating_table = True
        data["status"] = self.infer_entry_status(data)
        self._annotate_entry_production_info(data)
        self.update_screenshot_cell(row, self._resolve_temp_path(data.get("screenshot_path")))
        self.review_table.setItem(row, COL_EPISODE, QTableWidgetItem(data.get("__episode", "未分集")))
        self.review_table.setItem(row, COL_SCENE, QTableWidgetItem(data.get("__scene", "未分场")))
        self.update_ocr_cell(row, data.get("timestamp", ""), COL_TIMESTAMP)
        self.update_ocr_cell(row, data.get("shot_number", ""), COL_SHOT)
        source_item = QTableWidgetItem(self.entry_source_label(data))
        source_item.setFlags(source_item.flags() & ~Qt.ItemIsEditable)
        self.review_table.setItem(row, COL_SOURCE, source_item)
        self.review_table.removeCellWidget(row, COL_FULL_REVIEW)
        full_review = data.get("full_review", "")
        full_review_item = QTableWidgetItem(full_review)
        if not full_review:
            full_review_item.setToolTip("待转写。可双击手动填写，或右键重新识别录音。")
        self.review_table.setItem(row, COL_FULL_REVIEW, full_review_item)
        simplified_review = data.get("simplified_review", "")
        department = data.get("department", "")
        self.review_table.removeCellWidget(row, COL_SIMPLIFIED)
        self.review_table.setItem(row, COL_SIMPLIFIED, QTableWidgetItem(simplified_review))
        self.review_table.removeCellWidget(row, COL_KEYWORDS)
        self.review_table.setItem(row, COL_KEYWORDS, QTableWidgetItem(self.entry_keywords_text(data)))
        self._set_department_combo(self.review_table, row, COL_DEPARTMENT, department, row)
        status_item = QTableWidgetItem(data.get("status", ""))
        status_item.setFlags(status_item.flags() & ~Qt.ItemIsEditable)
        self.review_table.setItem(row, COL_STATUS, status_item)
        self.update_reference_cell(row)
        self.update_media_cell(row, data)
        self._is_updating_table = False

    def input_review_rows(self):
        return [
            row for row in self.visible_review_rows()
            if 0 <= row < len(self.project_manager.review_entries)
            and self.project_manager.review_entries[row].get("entry_type") != "long_video_full"
        ]

    def populate_latest_table(self):
        if not hasattr(self, "latest_table"):
            return
        rows = self.input_review_rows()
        self.latest_table.blockSignals(True)
        self.latest_table.setRowCount(0)
        if not rows:
            self.latest_table.blockSignals(False)
            return
        self.latest_table.setRowCount(len(rows))
        for table_row, source_row in enumerate(rows):
            entry = self.project_manager.review_entries[source_row]
            self._annotate_entry_production_info(entry)
            self.latest_table.setVerticalHeaderItem(table_row, QTableWidgetItem(str(source_row + 1)))
            self.latest_table.setCellWidget(
                table_row,
                INPUT_TABLE_COLUMNS.index(COL_SCREENSHOT),
                self._build_screenshot_widget(self._resolve_temp_path(entry.get("screenshot_path")), 120, 68),
            )
            values = {
                COL_TIMESTAMP: entry.get("timestamp", ""),
                COL_SHOT: entry.get("shot_number", ""),
                COL_FULL_REVIEW: entry.get("full_review", ""),
                COL_SIMPLIFIED: entry.get("simplified_review", ""),
                COL_KEYWORDS: self.entry_keywords_text(entry),
                COL_DEPARTMENT: entry.get("department", ""),
            }
            for original_col, value in values.items():
                table_col = INPUT_TABLE_COLUMNS.index(original_col)
                if original_col == COL_DEPARTMENT:
                    self._set_department_combo(self.latest_table, table_row, table_col, str(value or ""), source_row)
                else:
                    item = QTableWidgetItem(str(value or ""))
                    item.setData(Qt.UserRole, source_row)
                    item.setData(Qt.UserRole + 1, original_col)
                    if original_col == COL_KEYWORDS and value:
                        item.setForeground(Qt.red)
                    if any(term in str(value or "") for term in ("发现通过", "已通过", "通过")):
                        item.setForeground(Qt.darkGreen)
                    self.latest_table.setItem(table_row, table_col, item)
            self.latest_table.setCellWidget(
                table_row,
                INPUT_TABLE_COLUMNS.index(COL_REFERENCE),
                self._build_reference_cell_widget(source_row),
            )
            self.latest_table.setCellWidget(
                table_row,
                INPUT_TABLE_COLUMNS.index(COL_MEDIA),
                self._build_media_cell_widget(source_row, entry),
            )
        self.latest_table.resizeRowsToContents()
        self.latest_table.blockSignals(False)

    def _build_media_cell_widget(self, row, data):
        media_files_rel = data.get("media_files", [])
        media_widget = QWidget()
        media_layout = QVBoxLayout(media_widget)
        media_layout.setContentsMargins(4, 4, 4, 4)
        media_layout.setSpacing(4)
        if not media_files_rel:
            media_layout.addWidget(QLabel("无媒体"))
        else:
            for rel_path in media_files_rel:
                if not rel_path:
                    continue
                abs_path = self._resolve_temp_path(rel_path)
                row_widget = QWidget()
                row_layout = QHBoxLayout(row_widget)
                row_layout.setContentsMargins(0, 0, 0, 0)
                row_layout.setSpacing(4)
                is_video = str(rel_path).lower().endswith((".mp4", ".mov", ".mkv", ".avi", ".webm"))
                label = QLabel(("视频 " if is_video else "音频 ") + os.path.basename(rel_path))
                label.setToolTip(abs_path)
                label.setStyleSheet("color: #d8dee9;")
                open_button = self._make_cell_tool_button("播放" if is_video else "打开", QStyle.StandardPixmap.SP_MediaPlay)
                open_button.clicked.connect(lambda _, p=abs_path: self.open_file(p))
                folder_button = self._make_cell_tool_button("目录", QStyle.StandardPixmap.SP_DirOpenIcon)
                folder_button.clicked.connect(lambda _, p=abs_path: self.open_file(os.path.dirname(p)) if p else None)
                row_layout.addWidget(label, 1)
                row_layout.addWidget(open_button)
                row_layout.addWidget(folder_button)
                if data.get("entry_type") == "long_video_full" and is_video:
                    workspace_button = self._make_cell_tool_button("转文字", QStyle.StandardPixmap.SP_FileDialogDetailedView)
                    workspace_button.clicked.connect(lambda _, r=row: self.open_long_video_workspace(r))
                    row_layout.addWidget(workspace_button)
                media_layout.addWidget(row_widget)
        return media_widget

    def update_media_cell(self, row, data):
        media_widget = self._build_media_cell_widget(row, data)
        self.review_table.setCellWidget(row, COL_MEDIA, media_widget)

    def _make_cell_tool_button(self, text, standard_icon=None):
        button = QToolButton()
        button.setText(text)
        if standard_icon is not None:
            button.setIcon(self.style().standardIcon(standard_icon))
        button.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        button.setAutoRaise(True)
        button.setCursor(Qt.PointingHandCursor)
        button.setStyleSheet(
            "QToolButton { padding: 3px 6px; border: 1px solid #5c6370; border-radius: 4px; }"
            "QToolButton:hover { background: rgba(90, 120, 170, 0.25); }"
        )
        return button

    def infer_entry_status(self, entry):
        if entry.get("approved") or entry.get("review_outcome") == "approved" or entry.get("review_status") == "approved":
            return "已通过"
        if entry.get("entry_type") == "long_video_full":
            return "已完成" if entry.get("full_review") else "待转写"
        if not entry.get("full_review"):
            return "待转写"
        if entry.get("full_review") and not entry.get("simplified_review"):
            return "待AI"
        if not entry.get("department") or entry.get("department") in ["未分类", "错误"]:
            return "待处理"
        return "已完成"

    def _entry_matches_filters(self, entry):
        query = self.search_input.text().strip().lower() if hasattr(self, "search_input") else ""
        episode = self.episode_filter.currentText() if hasattr(self, "episode_filter") else "全部集号"
        scene = self.scene_filter.currentText() if hasattr(self, "scene_filter") else "全部场号"
        department = self.department_filter.currentText() if hasattr(self, "department_filter") else "全部部门"
        status = self.status_filter.currentText() if hasattr(self, "status_filter") else "全部状态"
        entry_status = self.infer_entry_status(entry)
        if episode != "全部集号" and self._entry_episode(entry) != episode:
            return False
        if scene != "全部场号" and self._entry_scene(entry) != scene:
            return False
        if department != "全部部门" and entry.get("department") != department:
            return False
        if status != "全部状态" and entry_status != status:
            return False
        if query:
            if self._compact_query_matches_entry(query, entry):
                return True
            haystack = " ".join([
                str(entry.get("__episode", "")),
                str(entry.get("__scene", "")),
                str(entry.get("shot_number", "")),
                str(entry.get("timestamp", "")),
                str(entry.get("full_review", "")),
                str(entry.get("simplified_review", "")),
                self.entry_keywords_text(entry),
                str(entry.get("department", "")),
                self.entry_source_label(entry),
            ]).lower()
            if query not in haystack:
                return False
        return True

    def _compact_query_matches_entry(self, query, entry):
        parts = re.findall(r"\d+", query or "")
        if len(parts) < 3:
            return False
        # 简化搜索格式：5 2 23 => EP005 / SC02 / 镜头号 023。
        target_episode = self._normalize_episode(parts[0])
        target_scene = self._normalize_scene(parts[1])
        target_shot = parts[2]
        if not self._normalized_code_matches(self._entry_episode(entry), target_episode):
            return False
        if not self._normalized_code_matches(self._entry_scene(entry), target_scene):
            return False
        return self._shot_matches_compact_token(entry.get("shot_number", ""), target_shot)

    def _normalized_code_matches(self, value, target):
        if value == target:
            return True
        value_number = re.search(r"\d+", str(value or ""))
        target_number = re.search(r"\d+", str(target or ""))
        if not value_number or not target_number:
            return False
        return int(value_number.group(0)) == int(target_number.group(0))

    def _shot_matches_compact_token(self, shot_number, token):
        raw = str(shot_number or "").lower()
        raw_token = str(token or "").lstrip("0") or "0"
        if str(token or "").lower() in raw:
            return True
        for number in re.findall(r"\d+", raw):
            if (number.lstrip("0") or "0") == raw_token:
                return True
        return False

    def _normalize_episode(self, value):
        raw = str(value or "").strip()
        if not raw:
            return ""
        match = re.search(r"\d+", raw)
        return f"EP{int(match.group(0)):03d}" if match else raw

    def _normalize_scene(self, value):
        raw = str(value or "").strip()
        if not raw:
            return ""
        match = re.search(r"[A-Za-z]*\d+[A-Za-z]*", raw)
        if not match:
            return raw
        digits = re.search(r"\d+", match.group(0))
        return f"SC{int(digits.group(0)):02d}" if digits else match.group(0)

    def _parse_episode_scene_from_text(self, text):
        raw = str(text or "")
        if not raw:
            return "", ""
        patterns = [
            r"(?:^|[^a-z0-9])e(?:p)?[\s_-]*0*(\d{1,3}).*?(?:sc|scene|s)[\s_-]*0*([a-z0-9]{1,6})",
            r"(?:^|[^a-z0-9])0*(\d{1,3})\s*集.*?0*([a-z0-9]{1,6})\s*场",
        ]
        for pattern in patterns:
            match = re.search(pattern, raw, re.IGNORECASE)
            if match:
                return self._normalize_episode(match.group(1)), self._normalize_scene(match.group(2))
        return "", ""

    def _entry_episode_scene(self, entry):
        explicit_episode = entry.get("episode") or entry.get("episode_number") or entry.get("episode_id") or entry.get("集号") or entry.get("集数")
        explicit_scene = entry.get("scene") or entry.get("scene_number") or entry.get("scene_id") or entry.get("场号") or entry.get("场次")
        if explicit_episode or explicit_scene:
            return self._normalize_episode(explicit_episode), self._normalize_scene(explicit_scene)
        for field in ("shot_number", "screenshot_path", "original_screenshot_path", "source_project", "source_revpack", "__sourceFile", "__projectName"):
            episode, scene = self._parse_episode_scene_from_text(entry.get(field))
            if episode or scene:
                return episode or "未分集", scene or "未分场"
        return "未分集", "未分场"

    def _annotate_entry_production_info(self, entry):
        episode, scene = self._entry_episode_scene(entry)
        entry["__episode"] = episode
        entry["__scene"] = scene
        return episode, scene

    def _entry_episode(self, entry):
        episode, _ = self._entry_episode_scene(entry)
        return episode

    def _entry_scene(self, entry):
        _, scene = self._entry_episode_scene(entry)
        return scene

    def visible_review_rows(self):
        return [
            row for row, entry in enumerate(self.project_manager.review_entries)
            if self._entry_matches_filters(entry)
        ]

    def apply_filters(self):
        if not hasattr(self, "review_table"):
            return
        for row, entry in enumerate(self.project_manager.review_entries):
            self.review_table.setRowHidden(row, not self._entry_matches_filters(entry))
        self.populate_latest_table()
        self.refresh_review_mode()
        if self.current_view_mode == "history":
            self.update_history_panel()

    def on_episode_filter_changed(self, apply=True):
        if hasattr(self, "scene_filter"):
            current = self.scene_filter.currentText()
            selected_episode = self.episode_filter.currentText()
            scenes = sorted({
                self._entry_scene(entry)
                for entry in self.project_manager.review_entries
                if selected_episode == "全部集号" or self._entry_episode(entry) == selected_episode
            })
            self.scene_filter.blockSignals(True)
            self.scene_filter.clear()
            self.scene_filter.addItem("全部场号")
            self.scene_filter.addItems([scene for scene in scenes if scene])
            idx = self.scene_filter.findText(current)
            self.scene_filter.setCurrentIndex(idx if idx >= 0 else 0)
            self.scene_filter.blockSignals(False)
        if apply:
            self.apply_filters()

    def refresh_views(self):
        for entry in self.project_manager.review_entries:
            self._annotate_entry_production_info(entry)
        if hasattr(self, "episode_filter"):
            current_episode = self.episode_filter.currentText()
            episodes = sorted({self._entry_episode(entry) for entry in self.project_manager.review_entries})
            self.episode_filter.blockSignals(True)
            self.episode_filter.clear()
            self.episode_filter.addItem("全部集号")
            self.episode_filter.addItems([episode for episode in episodes if episode])
            idx = self.episode_filter.findText(current_episode)
            self.episode_filter.setCurrentIndex(idx if idx >= 0 else 0)
            self.episode_filter.blockSignals(False)
            self.on_episode_filter_changed(False)
        if hasattr(self, "department_filter"):
            current = self.department_filter.currentText()
            self.department_filter.blockSignals(True)
            self.department_filter.clear()
            self.department_filter.addItem("全部部门")
            self.department_filter.addItems(self.settings.get("departments", []))
            idx = self.department_filter.findText(current)
            self.department_filter.setCurrentIndex(idx if idx >= 0 else 0)
            self.department_filter.blockSignals(False)
        self.apply_filters()

    def set_view_mode(self, mode):
        self.current_view_mode = mode if mode in ("input", "review", "table", "history") else "input"
        if hasattr(self, "content_stack"):
            pages = {
                "input": self.input_page,
                "review": self.review_mode_panel,
                "table": self.table_page,
                "history": self.history_page,
            }
            self.content_stack.setCurrentWidget(pages[self.current_view_mode])
        if hasattr(self, "input_mode_button"):
            self.input_mode_button.setChecked(self.current_view_mode == "input")
            self.review_mode_button.setChecked(self.current_view_mode == "review")
            self.table_mode_button.setChecked(self.current_view_mode == "table")
            self.history_mode_button.setChecked(self.current_view_mode == "history")
        if self.current_view_mode == "review":
            self.refresh_review_mode()
        elif self.current_view_mode == "history":
            self.update_history_panel()
        elif self.current_view_mode == "input":
            self.populate_latest_table()

    def refresh_review_mode(self):
        if not hasattr(self, "review_mode_panel"):
            return
        for entry in self.project_manager.review_entries:
            self._annotate_entry_production_info(entry)
        visible_rows = self.visible_review_rows() if hasattr(self, "review_table") else None
        self.review_mode_panel.update_entries(self.project_manager.review_entries, visible_rows=visible_rows)
        row = self.review_table.currentRow() if hasattr(self, "review_table") else -1
        if row >= 0 and (visible_rows is None or row in visible_rows):
            self.review_mode_panel.set_current_row(row, emit=False)

    def history_groups(self):
        groups = {}
        for row in self.visible_review_rows():
            if not (0 <= row < len(self.project_manager.review_entries)):
                continue
            entry = self.project_manager.review_entries[row]
            if entry.get("entry_type") == "long_video_full":
                continue
            self._annotate_entry_production_info(entry)
            shot = str(entry.get("shot_number") or f"第 {row + 1} 行").strip()
            key = (entry.get("__episode", "未分集"), entry.get("__scene", "未分场"), shot)
            groups.setdefault(key, []).append(row)
        for rows in groups.values():
            rows.sort(key=lambda r: (
                str(self.project_manager.review_entries[r].get("source_project") or ""),
                str(self.project_manager.review_entries[r].get("source_revpack") or ""),
                self.project_manager.review_entries[r].get("source_entry_index", r),
            ))
        return dict(sorted(groups.items(), key=lambda item: item[0]))

    def update_history_panel(self):
        if not hasattr(self, "history_tree"):
            return
        current_key = None
        current = self.history_tree.currentItem()
        if current:
            data = current.data(0, Qt.UserRole)
            current_key = data.get("key") if isinstance(data, dict) else None

        self.history_tree.blockSignals(True)
        self.history_tree.clear()
        groups = self.history_groups()
        episode_items = {}
        scene_items = {}
        first_shot_item = None
        for key, rows in groups.items():
            episode, scene, shot = key
            episode_item = episode_items.get(episode)
            if episode_item is None:
                episode_item = QTreeWidgetItem([episode, ""])
                episode_item.setData(0, Qt.UserRole, {"type": "episode"})
                self.history_tree.addTopLevelItem(episode_item)
                episode_items[episode] = episode_item
            scene_key = (episode, scene)
            scene_item = scene_items.get(scene_key)
            if scene_item is None:
                scene_item = QTreeWidgetItem([scene, ""])
                scene_item.setData(0, Qt.UserRole, {"type": "scene"})
                episode_item.addChild(scene_item)
                scene_items[scene_key] = scene_item
            shot_item = QTreeWidgetItem([shot, f"{len(rows)} 个版本"])
            shot_item.setData(0, Qt.UserRole, {"type": "shot", "key": key, "rows": rows})
            scene_item.addChild(shot_item)
            if first_shot_item is None or key == current_key:
                first_shot_item = shot_item
        self.history_tree.expandAll()
        if first_shot_item:
            self.history_tree.setCurrentItem(first_shot_item)
        self.history_tree.blockSignals(False)
        self.on_history_selection_changed()

    def on_history_selection_changed(self):
        if not hasattr(self, "history_versions_table"):
            return
        item = self.history_tree.currentItem()
        data = item.data(0, Qt.UserRole) if item else None
        rows = data.get("rows", []) if isinstance(data, dict) and data.get("type") == "shot" else []
        title = item.text(0) if item and rows else "未选择镜头"
        self.history_title.setText(title)
        self.history_versions_table.setRowCount(0)
        self.history_detail.clear()
        if not rows:
            return
        self.history_versions_table.setRowCount(len(rows))
        for table_row, source_row in enumerate(rows):
            entry = self.project_manager.review_entries[source_row]
            values = [
                f"版本 {table_row + 1}",
                self.entry_source_label(entry),
                entry.get("timestamp", ""),
                entry.get("department", ""),
                self.infer_entry_status(entry),
                entry.get("full_review", ""),
                entry.get("simplified_review", ""),
            ]
            for col, value in enumerate(values):
                item = QTableWidgetItem(str(value or ""))
                item.setData(Qt.UserRole, source_row)
                self.history_versions_table.setItem(table_row, col, item)
        self.history_versions_table.resizeRowsToContents()
        self.history_versions_table.selectRow(len(rows) - 1)
        latest = self.project_manager.review_entries[rows[-1]]
        self.history_detail.setPlainText(
            f"来源: {self.entry_source_label(latest)}\n"
            f"集场: {latest.get('__episode', '未分集')} / {latest.get('__scene', '未分场')}\n"
            f"关键词: {self.entry_keywords_text(latest) or '-'}\n\n"
            f"完整意见:\n{latest.get('full_review', '') or '暂无'}\n\n"
            f"整理结果:\n{latest.get('simplified_review', '') or '暂无'}"
        )

    def open_history_selected_version(self):
        if not hasattr(self, "history_versions_table"):
            return
        selected = self.history_versions_table.selectedItems()
        if selected:
            row = selected[0].data(Qt.UserRole)
        else:
            item = self.history_tree.currentItem()
            data = item.data(0, Qt.UserRole) if item else None
            rows = data.get("rows", []) if isinstance(data, dict) else []
            row = rows[-1] if rows else -1
        if isinstance(row, int) and 0 <= row < self.project_manager.get_entry_count():
            self.select_review_row_from_review_mode(row)
            self.set_view_mode("review")

    def select_review_row_from_review_mode(self, row):
        if not (0 <= row < self.project_manager.get_entry_count()):
            return
        self.review_table.blockSignals(True)
        self.review_table.setCurrentCell(row, max(0, self.review_table.currentColumn()))
        self.review_table.blockSignals(False)
        target_item = None
        for col in range(self.review_table.columnCount()):
            target_item = self.review_table.item(row, col)
            if target_item:
                break
        if target_item:
            self.review_table.scrollToItem(target_item)

    def on_table_current_cell_changed(self, current_row, current_col, previous_row, previous_col):
        if hasattr(self, "review_mode_panel") and current_row >= 0:
            self.review_mode_panel.set_current_row(current_row, emit=False)

    def show_table_context_menu(self, pos):
        index = self.review_table.indexAt(pos)
        row, col = index.row(), index.column()
        
        if row < 0:
            context_menu = QMenu(self)
            add_blank_action = context_menu.addAction("在末尾添加空白行")
            selected_row = self.review_table.currentRow()
            if selected_row >= 0:
                context_menu.addSeparator()
                delete_action = context_menu.addAction("删除选中行")
            else:
                delete_action = None
            action = context_menu.exec(self.review_table.mapToGlobal(pos))
            if action == add_blank_action:
                self.insert_blank_review_row(self.project_manager.get_entry_count())
            elif delete_action is not None and action == delete_action:
                self.confirm_and_delete_row(selected_row)
            return

        context_menu = QMenu(self)
        entry = self.project_manager.review_entries[row]
        
        if col == COL_SCREENSHOT:
            context_menu.addAction("用系统查看器打开大图").triggered.connect(lambda: self.open_file(self._resolve_temp_path(entry.get("screenshot_path"))))
            context_menu.addAction("涂鸦/编辑截图").triggered.connect(lambda: self.start_doodle_editor(row))
        elif col in [COL_TIMESTAMP, COL_SHOT]:
            context_menu.addAction("自动重新识别").triggered.connect(lambda: self.handle_re_recognize_ocr(row, col))
            context_menu.addAction("选择区域重新识别").triggered.connect(lambda: self.retry_ocr(row, col))
        elif col == COL_FULL_REVIEW:
            context_menu.addAction("AI优化此条并替换完整意见").triggered.connect(lambda: self.process_single_review_with_ai(row))
            context_menu.addAction("重新识别录音").triggered.connect(lambda: self.manual_transcribe(row))
            if entry.get("audio_path"):
                context_menu.addAction("打开录音文件").triggered.connect(lambda: self.open_file(self._resolve_temp_path(entry.get("audio_path"))))
        elif col == COL_REFERENCE:
            action = context_menu.addAction("打开参考文件夹")
            action.triggered.connect(lambda: self.open_containing_folder(entry, "reference_files"))
        elif col == COL_MEDIA:
            action = context_menu.addAction("打开媒体文件夹")
            action.triggered.connect(lambda: self.open_containing_folder(entry, "media_files"))
        
        context_menu.addSeparator()
        context_menu.addAction("在下方插入空白行").triggered.connect(lambda: self.insert_blank_review_row(row + 1))
        context_menu.addAction("删除此行").triggered.connect(lambda: self.confirm_and_delete_row(row))
        
        context_menu.exec(self.review_table.mapToGlobal(pos))

    def show_input_table_context_menu(self, pos):
        index = self.latest_table.indexAt(pos)
        input_row, input_col = index.row(), index.column()
        row = self._input_table_source_row(input_row)
        col = self._input_table_source_col(input_col)

        if row < 0 or row >= self.project_manager.get_entry_count():
            context_menu = QMenu(self)
            add_blank_action = context_menu.addAction("在末尾添加空白行")
            action = context_menu.exec(self.latest_table.mapToGlobal(pos))
            if action == add_blank_action:
                self.insert_blank_review_row(self.project_manager.get_entry_count())
            return

        context_menu = QMenu(self)
        entry = self.project_manager.review_entries[row]

        if col == COL_SCREENSHOT:
            context_menu.addAction("用系统查看器打开大图").triggered.connect(lambda: self.open_file(self._resolve_temp_path(entry.get("screenshot_path"))))
            context_menu.addAction("涂鸦/编辑截图").triggered.connect(lambda: self.start_doodle_editor(row))
        elif col in [COL_TIMESTAMP, COL_SHOT]:
            context_menu.addAction("自动重新识别").triggered.connect(lambda: self.handle_re_recognize_ocr(row, col))
            context_menu.addAction("选择区域重新识别").triggered.connect(lambda: self.retry_ocr(row, col))
        elif col == COL_FULL_REVIEW:
            context_menu.addAction("AI优化此条并替换完整意见").triggered.connect(lambda: self.process_single_review_with_ai(row))
            context_menu.addAction("重新识别录音").triggered.connect(lambda: self.manual_transcribe(row))
            if entry.get("audio_path"):
                context_menu.addAction("打开录音文件").triggered.connect(lambda: self.open_file(self._resolve_temp_path(entry.get("audio_path"))))
        elif col == COL_REFERENCE:
            context_menu.addAction("打开参考文件夹").triggered.connect(lambda: self.open_containing_folder(entry, "reference_files"))
        elif col == COL_MEDIA:
            context_menu.addAction("打开媒体文件夹").triggered.connect(lambda: self.open_containing_folder(entry, "media_files"))

        context_menu.addSeparator()
        context_menu.addAction("在下方插入空白行").triggered.connect(lambda: self.insert_blank_review_row(row + 1))
        context_menu.addAction("删除此行").triggered.connect(lambda: self.confirm_and_delete_row(row))
        context_menu.exec(self.latest_table.mapToGlobal(pos))

    def insert_blank_review_row(self, row_index):
        inserted_row = self.project_manager.insert_blank_entry(row_index)
        if self.project_manager.current_project_file:
            self.project_manager.save_project(autosave=True)
        self.review_table.setCurrentCell(inserted_row, COL_FULL_REVIEW)
        if self.current_view_mode == "review":
            self.review_mode_panel.set_current_row(inserted_row, emit=False)
        self.statusBar().showMessage(f"已插入第 {inserted_row + 1} 行空白审阅。", 3000)

    def open_containing_folder(self, entry, file_key):
        files = entry.get(file_key, [])
        path_to_open = None
        
        if files:
            path_to_open = self._resolve_temp_path(files[0])
        elif file_key == "media_files":
            path_to_open = self._resolve_temp_path(entry.get("audio_path"))

        if path_to_open and os.path.exists(path_to_open):
            self.open_file(os.path.dirname(path_to_open))
        else:
            QMessageBox.information(self, "提示", f"此条目没有关联的 {file_key} 文件。")
            
    def confirm_and_delete_row(self, row):
        reply = QMessageBox.question(self, "确认删除", f"确定要删除第 {row + 1} 行吗？\n此操作可以撤销。", QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if reply == QMessageBox.Yes:
            self.project_manager.remove_review_entry(row)
            if self.project_manager.current_project_file:
                self.project_manager.save_project(autosave=True)
            self.refresh_review_mode()

    def _apply_review_table_edit(self, row, col, new_text):
        if not (0 <= row < self.project_manager.get_entry_count()):
            return
        self._is_updating_table = True
        try:
            if col == COL_SHOT:
                self.project_manager.update_shot_number_and_move_files(row, new_text)
            else:
                field_map = {
                    COL_EPISODE: "episode",
                    COL_SCENE: "scene",
                    COL_TIMESTAMP: "timestamp",
                    COL_FULL_REVIEW: "full_review",
                    COL_SIMPLIFIED: "simplified_review",
                    COL_DEPARTMENT: "department",
                }
                if col == COL_KEYWORDS:
                    keywords = [part.strip() for part in re.split(r"[,，、\n]", new_text) if part.strip()]
                    self.project_manager.update_entry(row, {"keywords": keywords}, snapshot_action="Edit Keywords")
                elif col in field_map:
                    value = self._normalize_episode(new_text) if col == COL_EPISODE else self._normalize_scene(new_text) if col == COL_SCENE else new_text
                    self.project_manager.update_entry(row, {field_map[col]: value}, snapshot_action="Edit Cell")
                if self.project_manager.current_project_file:
                    self.project_manager.save_project(autosave=True)
                if col in (COL_EPISODE, COL_SCENE, COL_FULL_REVIEW, COL_SIMPLIFIED, COL_KEYWORDS, COL_DEPARTMENT):
                    self.apply_filters()
        finally:
            self._is_updating_table = False


    def _set_department_combo(self, table, row, col, department, source_row):
        combo = QComboBox()
        combo.setEditable(True)
        combo.setFocusPolicy(Qt.StrongFocus)
        combo.setStyleSheet("QComboBox { background-color: transparent; border: none; padding-left: 5px; } QComboBox::drop-down { border: none; }")
        deps = self.settings.get("departments", [])
        if "未分类" not in deps:
            deps = ["未分类"] + deps
        combo.addItems(deps)
        combo.blockSignals(True)
        combo.setCurrentText(department)
        combo.blockSignals(False)
        
        def on_text_changed(text):
            if hasattr(self, '_is_updating_table') and self._is_updating_table: return
            self.project_manager.update_entry(source_row, {"department": text}, snapshot_action="Edit Department")
            if self.project_manager.current_project_file:
                self.project_manager.save_project(autosave=True)
            self.apply_filters()
            
        combo.currentTextChanged.connect(on_text_changed)
        table.setCellWidget(row, col, combo)

    def handle_item_changed(self, item):
        if self._is_updating_table:
            return
        row, col = item.row(), item.column()
        new_text = item.text()
        if self._current_cell_value is not None and new_text == self._current_cell_value:
            return
        self._apply_review_table_edit(row, col, new_text)

    def _input_table_source_row(self, input_row):
        header_item = self.latest_table.verticalHeaderItem(input_row) if hasattr(self, "latest_table") else None
        if header_item:
            try:
                return int(header_item.text()) - 1
            except (TypeError, ValueError):
                pass
        rows = self.input_review_rows()
        return rows[input_row] if 0 <= input_row < len(rows) else -1

    def _input_table_source_col(self, input_col):
        return INPUT_TABLE_COLUMNS[input_col] if 0 <= input_col < len(INPUT_TABLE_COLUMNS) else -1

    def handle_input_item_changed(self, item):
        if self._is_updating_table:
            return
        source_row = item.data(Qt.UserRole)
        source_col = item.data(Qt.UserRole + 1)
        if not isinstance(source_row, int):
            source_row = self._input_table_source_row(item.row())
        if not isinstance(source_col, int):
            source_col = self._input_table_source_col(item.column())
        new_text = item.text()
        if self._current_cell_value is not None and new_text == self._current_cell_value:
            return
        self._apply_review_table_edit(source_row, source_col, new_text)
    
    def on_doodle_saved(self, row, new_annotated_abs_path):
        if not (0 <= row < self.project_manager.get_entry_count()):
            return
        entry = self.project_manager.review_entries[row]
        target_rel_path = entry.get("screenshot_path") 
        if not target_rel_path:
            QMessageBox.warning(self, "错误", "找不到原始截图，无法保存涂鸦。")
            return
        target_abs_path = self._resolve_temp_path(target_rel_path)
        try:
            if os.path.exists(target_abs_path):
                os.remove(target_abs_path)
            shutil.move(new_annotated_abs_path, target_abs_path)
            self.project_manager.update_entry(row, {}, snapshot_action="Edit Screenshot")
            print(f"涂鸦已保存并覆盖: {target_abs_path}")
        except Exception as e:
            QMessageBox.critical(self, "文件错误", f"保存涂鸦时发生文件错误，无法替换原始文件。\n{e}")
    
    def toggle_window_visibility(self):
        if self.isVisible() and not self.isMinimized():
            self.hide()
            if self.recording_manager.is_recording():
                self.recording_indicator.set_text("正在录制")
                self.recording_indicator.show_at_corner()
        else:
            self.showNormal()
            self.activateWindow()
            self.recording_indicator.hide()
        
    def changeEvent(self, event):
        if event.type() == QEvent.WindowStateChange:
            if self.windowState() & Qt.WindowMinimized:
                event.ignore()
                self.hide()
                if self.recording_manager.is_recording():
                    self.recording_indicator.set_text("正在录制")
                    self.recording_indicator.show_at_corner()
                self.tray_icon.showMessage("提示", "审阅助手已最小化到托盘。", QSystemTrayIcon.Information, 2000)
                return
        super().changeEvent(event)
        
    def closeEvent(self, event):
        if self.is_packing:
            QMessageBox.warning(self, "操作正在进行", "项目正在打包中，请稍后重试。")
            event.ignore()
            return
        temp_dir = self.project_manager.current_temp_dir
        if temp_dir and os.path.isdir(temp_dir):
            reply = QMessageBox.question(self, "清理临时文件", f"是否要删除与此项目关联的临时文件夹？\n\n{temp_dir}",
                                         QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel, QMessageBox.Yes)
            if reply == QMessageBox.Yes:
                try:
                    shutil.rmtree(temp_dir)
                    print(f"临时文件夹已删除: {temp_dir}")
                except Exception as e:
                    QMessageBox.warning(self, "删除失败", f"无法删除临时文件夹，它可能正在被使用。\n{e}")
                self.unregister_hotkeys()
                event.accept()
                QApplication.instance().quit()
            elif reply == QMessageBox.No:
                self.unregister_hotkeys()
                event.accept()
                QApplication.instance().quit()
            else:
                event.ignore()
        else:
            reply = QMessageBox.question(self, "确认退出", "确定要关闭协同审阅平台吗？", QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if reply == QMessageBox.Yes:
                self.unregister_hotkeys()
                event.accept()
                QApplication.instance().quit()
            else:
                event.ignore()
            
    def transcribe_audio_worker(self, audio_path, row):
        final_text = ""
        try:
            selected_model = self.settings.get("selected_model", "funasr-paraformer-zh")
            if not self.whisper_model or self._transcription_model_name != selected_model:
                self.load_transcription_model(show_dialog=False)
            if self.whisper_model:
                if 0 <= row < self.project_manager.get_entry_count() and self.project_manager.review_entries[row].get("entry_type") == "long_video_full":
                    detailed = self.transcribe_long_audio_with_loaded_model(audio_path)
                    final_text = detailed.get("text") or "没有识别到声音"
                    QApplication.instance().postEvent(self, CustomEvent({
                        "row": row,
                        "text": final_text,
                        "segments": detailed.get("segments", []),
                        "is_long_video": True,
                    }, TRANSCRIPTION_DONE_EVENT_TYPE))
                    return
                transcribed_text = self.transcribe_with_loaded_model(audio_path)
                final_text = transcribed_text or "没有识别到声音"
            else:
                final_text = "语音模型未加载"
        except Exception as e:
            print(f"语音转录失败: {e}")
            final_text = "语音转录失败"
        QApplication.instance().postEvent(self, CustomEvent({"row": row, "text": final_text}, TRANSCRIPTION_DONE_EVENT_TYPE))
        
    def open_settings(self):
        dialog = SettingsDialog(self.settings.copy(), self)
        if dialog.exec():
            self.settings.update(dialog.get_settings())
            self.save_settings()
            self.recording_manager.settings = self.settings
            self.recording_manager.ffmpeg_path = check_ffmpeg_availability(self.settings)
            self.recording_manager.is_ffmpeg_available = self.recording_manager.ffmpeg_path is not None
            self.update_toolbar_state()
            apply_app_stylesheet(QApplication.instance(), self.settings.get("theme", "light"))
            self.refresh_views()
            QMessageBox.information(self, "成功", "设置已保存并应用。部分设置需要重启后生效。")
            
    def handle_re_recognize_ocr(self, row, column):
        if not (0 <= row < self.project_manager.get_entry_count()):
            return
        entry = self.project_manager.review_entries[row]
        rel_image_path = entry.get("screenshot_path")
        abs_image_path = self._resolve_temp_path(rel_image_path)
        if not (abs_image_path and os.path.exists(abs_image_path)):
            QMessageBox.warning(self, "文件丢失", f"无法找到用于 OCR 的截图文件:\n{abs_image_path}")
            return
        field_name = "时间戳" if column == COL_TIMESTAMP else "镜头号"
        self.statusBar().showMessage(f"正在重新识别第 {row + 1} 行的 {field_name}...", 0)
        threading.Thread(target=self.re_recognize_ocr_worker, args=(row, column, abs_image_path), daemon=True).start()
        
    def re_recognize_ocr_worker(self, row, column, image_path):
        try:
            with Image.open(image_path) as img:
                if column == COL_TIMESTAMP:
                    text = ocr_utils.ocr_timestamp_from_image(img)
                elif column == COL_SHOT:
                    text = ocr_utils.ocr_shot_number_from_image(img)
                else:
                    return
                QApplication.instance().postEvent(self, CustomEvent({"row": row, "text": text, "column": column}, RETRY_OCR_DONE_EVENT_TYPE))
        except Exception as e:
            print(f"重新识别 OCR 时失败: {e}")
            self.statusBar().showMessage("重新识别失败", 3000)

    def update_volume_bar(self, level):
        self.volume_bar.setValue(level)

    def update_recording_ui_state(self, is_recording, status_text=""):
        if is_recording:
            display_text = status_text or "正在录制"
            self.record_toggle_action.setText("停止录制")
            self.record_toggle_action.setToolTip("停止当前审阅录制")
            self.recording_status_label.setText("● " + display_text)
            self.recording_status_label.setStyleSheet(
                "QLabel { color: #ff4d4f; font-weight: 800; padding: 2px 8px; }"
            )
            self.volume_bar.show()
            if self.isMinimized() or self.isHidden():
                self.recording_indicator.set_text(display_text)
                self.recording_indicator.show_at_corner()
            else:
                self.recording_indicator.hide()
        else:
            self.record_toggle_action.setText("开始录制")
            self.record_toggle_action.setToolTip("开始审阅录制")
            self.recording_status_label.setText("未录制")
            self.recording_status_label.setStyleSheet(
                "QLabel { color: #7a7f87; font-weight: 700; padding: 2px 8px; }"
            )
            self.volume_bar.hide()
            self.recording_indicator.hide()

    def handle_recording_error(self, message):
        QMessageBox.critical(self, "录制错误", message)
        self.statusBar().showMessage("录制失败", 5000)
        self.update_recording_ui_state(False)

    def _ensure_project_ready_for_assets(self):
        if self.project_manager.current_project_file and self.project_manager.current_temp_dir:
            return True
        QMessageBox.information(self, "提示", "请先新建或加载一个项目，并保存它。")
        if not self.handle_save_project():
            return False
        if not self.project_manager.current_temp_dir:
            QMessageBox.critical(self, "错误", "无法设定项目临时目录，请重启程序。")
            return False
        return True

    def import_long_video_review(self):
        if not self._ensure_project_ready_for_assets():
            return
        video_path, _ = QFileDialog.getOpenFileName(
            self,
            "选择长视频反馈文件",
            "",
            "视频文件 (*.mp4 *.mov *.mkv *.avi *.webm);;所有文件 (*.*)"
        )
        if not video_path:
            return
        if not self.recording_manager.ffmpeg_path:
            QMessageBox.warning(self, "FFmpeg 未找到", "导入长视频需要 FFmpeg 提取音频和首帧，请先在设置中配置 FFmpeg。")
            return
        self.import_long_video_action.setEnabled(False)
        self.statusBar().showMessage("正在导入长视频并提取音频...", 0)
        threading.Thread(target=self.import_long_video_worker, args=(video_path,), daemon=True).start()

    def import_long_video_worker(self, video_path):
        try:
            temp_base_dir = self.project_manager.current_temp_dir
            base_name = os.path.splitext(os.path.basename(video_path))[0]
            shot_name = re.sub(r'[\\/:*?"<>|]', '_', base_name.strip()) or "LONG_VIDEO"
            timestamp = int(time.time())

            recordings_dir = os.path.join(temp_base_dir, "recordings", shot_name)
            snapshots_dir = os.path.join(temp_base_dir, "snapshots", shot_name)
            audio_dir = os.path.join(temp_base_dir, "audio", shot_name)
            os.makedirs(recordings_dir, exist_ok=True)
            os.makedirs(snapshots_dir, exist_ok=True)
            os.makedirs(audio_dir, exist_ok=True)

            video_ext = os.path.splitext(video_path)[1] or ".mp4"
            video_dest = os.path.join(recordings_dir, f"{shot_name}_{timestamp}{video_ext}")
            if os.path.abspath(video_path) != os.path.abspath(video_dest):
                shutil.copy2(video_path, video_dest)

            screenshot_dest = os.path.join(snapshots_dir, f"{shot_name}_{timestamp}_frame.png")
            audio_dest = os.path.join(audio_dir, f"{shot_name}_{timestamp}.wav")

            self._run_ffmpeg_hidden([
                self.recording_manager.ffmpeg_path, "-y", "-ss", "00:00:01", "-i", video_dest,
                "-frames:v", "1", screenshot_dest
            ], timeout=90)
            if not os.path.exists(screenshot_dest):
                Image.new("RGB", (1280, 720), "#20242b").save(screenshot_dest)

            audio_ok = self._run_ffmpeg_hidden([
                self.recording_manager.ffmpeg_path, "-y", "-i", video_dest,
                "-vn", "-ac", "1", "-ar", "16000", audio_dest
            ], timeout=600)
            if not audio_ok or not os.path.exists(audio_dest):
                audio_dest = None

            def rel(abs_path):
                if not abs_path:
                    return None
                return os.path.relpath(abs_path, temp_base_dir).replace(os.sep, "/")

            review_data = {
                "entry_type": "long_video_full",
                "shot_number": shot_name,
                "timestamp": "00:00:00:00",
                "screenshot_path": rel(screenshot_dest),
                "original_screenshot_path": rel(screenshot_dest),
                "audio_path": rel(audio_dest),
                "media_files": [rel(video_dest)],
                "reference_files": [],
                "source_video": rel(video_dest),
                "full_review": "",
                "simplified_review": "",
                "keywords": [],
                "department": "完整转录",
            }
            QApplication.instance().postEvent(self, CustomEvent({"success": True, "review_data": review_data}, LONG_VIDEO_IMPORT_EVENT_TYPE))
        except Exception as e:
            QApplication.instance().postEvent(self, CustomEvent({"success": False, "message": str(e)}, LONG_VIDEO_IMPORT_EVENT_TYPE))

    def _run_ffmpeg_hidden(self, command, timeout=120):
        startupinfo = subprocess.STARTUPINFO() if sys.platform == "win32" else None
        if startupinfo:
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        try:
            result = subprocess.run(
                command,
                check=False,
                capture_output=True,
                text=True,
                startupinfo=startupinfo,
                timeout=timeout,
                encoding="utf-8",
                errors="ignore",
            )
            if result.returncode != 0:
                print(f"FFmpeg 命令失败: {' '.join(command)}\n{result.stderr[-1000:]}")
            return result.returncode == 0
        except Exception as e:
            print(f"FFmpeg 执行失败: {e}")
            return False

    def start_long_video_segmentation(self, row, segments):
        if not (0 <= row < self.project_manager.get_entry_count()):
            return
        if self.settings.get("ai_provider") in LOCAL_AI_PROVIDERS and not self._is_local_ai_server_available():
            self.statusBar().showMessage("长视频全文已转写；AI 服务未连接，暂未自动分析讨论片段。", 8000)
            return
        entry = self.project_manager.review_entries[row]
        source_video = self._resolve_temp_path(entry.get("source_video") or (entry.get("media_files") or [None])[0])
        if not source_video or not os.path.exists(source_video):
            self.statusBar().showMessage("长视频全文已转写，但源视频丢失，无法生成讨论片段。", 8000)
            return
        self.statusBar().showMessage("长视频全文转写完成，正在用 AI 判断讨论问题片段...", 0)
        threading.Thread(target=self.long_video_segmentation_worker, args=(row, source_video, segments), daemon=True).start()

    def open_long_video_workspace(self, row):
        if not (0 <= row < self.project_manager.get_entry_count()):
            return
        entry = self.project_manager.review_entries[row]
        source_video = self._resolve_temp_path(entry.get("source_video") or (entry.get("media_files") or [None])[0])
        dialog = self.long_video_dialogs.get(row)
        if dialog:
            try:
                if shiboken6.isValid(dialog):
                    dialog.show()
                    dialog.raise_()
                    dialog.activateWindow()
                    return
            except RuntimeError:
                pass
        dialog = LongVideoTranscriptionDialog(source_video, self)
        dialog.set_transcript(entry.get("full_review", ""), entry.get("transcript_segments", []))
        if entry.get("long_video_summary"):
            dialog.set_summary(entry.get("long_video_summary"))
        if entry.get("long_video_issues"):
            dialog.set_issues(entry.get("long_video_issues"))
        dialog.summary_requested.connect(lambda r=row: self.generate_long_video_summary(r))
        dialog.issues_requested.connect(lambda r=row: self.organize_long_video_to_table(r))
        dialog.issues_commit_requested.connect(lambda issues, r=row: self.commit_long_video_issues_to_table(r, issues))
        dialog.transcript_save_requested.connect(lambda text, r=row: self.save_long_video_transcript_edit(r, text))
        dialog.destroyed.connect(lambda: self.long_video_dialogs.pop(row, None))
        self.long_video_dialogs[row] = dialog
        dialog.show()

    def save_long_video_transcript_edit(self, row, text):
        if not (0 <= row < self.project_manager.get_entry_count()):
            return
        self.project_manager.update_entry(row, {"full_review": text}, snapshot_action="Edit Transcript")
        if self.project_manager.current_project_file:
            self.project_manager.save_project(autosave=True)
        self.statusBar().showMessage("长视频逐字稿已保存。", 4000)

    def generate_long_video_summary(self, row):
        if not (0 <= row < self.project_manager.get_entry_count()):
            return
        if self.settings.get("ai_provider") in LOCAL_AI_PROVIDERS and not self._is_local_ai_server_available():
            self.statusBar().showMessage("AI 服务未连接，无法生成长视频纲要。", 6000)
            return
        dialog = self.long_video_dialogs.get(row)
        if dialog:
            dialog.set_status("正在生成长视频纲要...", busy=True)
        text = dialog.transcript_text.toPlainText() if dialog else self.project_manager.review_entries[row].get("full_review", "")
        self.project_manager.review_entries[row]["full_review"] = text
        threading.Thread(target=self.long_video_summary_worker, args=(row, text), daemon=True).start()

    def long_video_summary_worker(self, row, text):
        try:
            ai_proc = AIProcessor(
                provider=self.settings.get("ai_provider", "local-ai"),
                api_key=self.settings.get("api_key", "local"),
                base_url=self.settings.get("base_url", DEFAULT_LOCAL_AI_BASE_URL),
                model_name=self.settings.get("model_name", DEFAULT_QWEN_MODEL),
            )
            result = ai_proc.summarize_long_review(text, self.settings.get("departments"))
            summary = result.get("rewritten_review") or result.get("simplified_review") or "未生成纲要。"
            QApplication.instance().postEvent(self, CustomEvent({"row": row, "summary": summary}, LONG_VIDEO_SUMMARY_EVENT_TYPE))
        except Exception as e:
            QApplication.instance().postEvent(self, CustomEvent({"row": row, "error": str(e)}, LONG_VIDEO_SUMMARY_EVENT_TYPE))

    def organize_long_video_to_table(self, row):
        if not (0 <= row < self.project_manager.get_entry_count()):
            return
        dialog = self.long_video_dialogs.get(row)
        if dialog:
            text = dialog.transcript_text.toPlainText()
            self.project_manager.review_entries[row]["full_review"] = text
            dialog.set_status("正在整理讨论片段到表格...", busy=True)
        if self.project_manager.current_project_file:
            self.project_manager.save_project(autosave=True)
        self.start_long_video_segmentation(row, self.project_manager.review_entries[row].get("transcript_segments", []))

    def commit_long_video_issues_to_table(self, row, issues):
        if not (0 <= row < self.project_manager.get_entry_count()):
            return
        if not issues:
            QMessageBox.information(self, "提示", "问题清单为空，请先整理问题或手动标记讨论区间。")
            return
        existing = [
            entry for entry in self.project_manager.review_entries
            if entry.get("entry_type") == "long_video_segment"
            and entry.get("parent_long_video") == self.project_manager.review_entries[row].get("source_video")
        ]
        if existing:
            reply = QMessageBox.question(
                self,
                "已有问题行",
                "这个长视频已经整理过问题行。\n\n选择“是”覆盖旧问题行；选择“否”追加新问题行。",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if reply == QMessageBox.Yes:
                parent_source = self.project_manager.review_entries[row].get("source_video")
                self.project_manager.review_entries = [
                    entry for entry in self.project_manager.review_entries
                    if not (
                        entry.get("entry_type") == "long_video_segment"
                        and entry.get("parent_long_video") == parent_source
                    )
                ]
                self.project_manager.update_table_display()
        source_video = self._resolve_temp_path(self.project_manager.review_entries[row].get("source_video") or (self.project_manager.review_entries[row].get("media_files") or [None])[0])
        if not source_video or not os.path.exists(source_video):
            QMessageBox.warning(self, "源视频丢失", "无法找到长视频源文件，不能截图和剪辑片段。")
            return
        dialog = self.long_video_dialogs.get(row)
        if dialog:
            dialog.set_status("正在截图 OCR、剪辑片段并写入表格...", busy=True)
        threading.Thread(target=self.long_video_commit_worker, args=(row, source_video, issues), daemon=True).start()

    def long_video_commit_worker(self, parent_row, source_video, issues):
        try:
            child_entries = self.build_long_video_child_entries(parent_row, source_video, issues)
            QApplication.instance().postEvent(self, CustomEvent({
                "success": True,
                "parent_row": parent_row,
                "entries": child_entries,
            }, LONG_VIDEO_SEGMENTS_EVENT_TYPE))
        except Exception as e:
            QApplication.instance().postEvent(self, CustomEvent({
                "success": False,
                "message": str(e),
            }, LONG_VIDEO_SEGMENTS_EVENT_TYPE))

    def long_video_segmentation_worker(self, parent_row, source_video, transcript_segments):
        try:
            timed_text = self._format_timed_segments_for_ai(transcript_segments)
            if not timed_text:
                timed_text = self.project_manager.review_entries[parent_row].get("full_review", "")
            ai_proc = AIProcessor(
                provider=self.settings.get("ai_provider", "local-ai"),
                api_key=self.settings.get("api_key", "local"),
                base_url=self.settings.get("base_url", DEFAULT_LOCAL_AI_BASE_URL),
                model_name=self.settings.get("model_name", DEFAULT_QWEN_MODEL),
            )
            result = ai_proc.segment_long_video_discussions(timed_text, self.settings.get("departments"))
            QApplication.instance().postEvent(self, CustomEvent({
                "success": True,
                "parent_row": parent_row,
                "issues": result.get("segments", []),
            }, LONG_VIDEO_ISSUES_EVENT_TYPE))
        except Exception as e:
            QApplication.instance().postEvent(self, CustomEvent({
                "success": False,
                "message": str(e),
            }, LONG_VIDEO_ISSUES_EVENT_TYPE))

    def _format_timed_segments_for_ai(self, segments):
        lines = []
        for segment in segments or []:
            text = str(segment.get("text", "")).strip()
            if not text:
                continue
            start = float(segment.get("start") or 0)
            end = float(segment.get("end") or start)
            lines.append(f"[{start:.2f}-{end:.2f}] {text}")
        return "\n".join(lines)

    def build_long_video_child_entries(self, parent_row, source_video, ai_segments):
        if not (0 <= parent_row < self.project_manager.get_entry_count()):
            return []
        parent_entry = self.project_manager.review_entries[parent_row]
        temp_base_dir = self.project_manager.current_temp_dir
        parent_name = parent_entry.get("shot_number") or "LONG_VIDEO"
        safe_parent = re.sub(r'[\\/:*?"<>|]', '_', parent_name.strip()) if parent_name else "LONG_VIDEO"
        entries = []
        for index, segment in enumerate(ai_segments, 1):
            start = max(0.0, float(segment.get("start") or 0))
            end = max(start + 1.0, float(segment.get("end") or (start + 8.0)))
            stamp = f"{int(time.time())}_{index:03d}"
            segment_dir_name = f"{safe_parent}_片段{index:03d}"

            clip_dir = os.path.join(temp_base_dir, "recordings", segment_dir_name)
            snapshot_dir = os.path.join(temp_base_dir, "snapshots", segment_dir_name)
            os.makedirs(clip_dir, exist_ok=True)
            os.makedirs(snapshot_dir, exist_ok=True)

            clip_path = os.path.join(clip_dir, f"{segment_dir_name}_{stamp}.mp4")
            screenshot_path = os.path.join(snapshot_dir, f"{segment_dir_name}_{stamp}.png")

            duration = max(1.0, end - start)
            clip_ok = self._run_ffmpeg_hidden([
                self.recording_manager.ffmpeg_path, "-y", "-ss", f"{start:.3f}", "-i", source_video,
                "-t", f"{duration:.3f}", "-c", "copy", "-avoid_negative_ts", "make_zero", clip_path
            ], timeout=180)
            if not clip_ok or not os.path.exists(clip_path):
                self._run_ffmpeg_hidden([
                    self.recording_manager.ffmpeg_path, "-y", "-ss", f"{start:.3f}", "-i", source_video,
                    "-t", f"{duration:.3f}", "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
                    "-c:a", "aac", "-b:a", "128k", clip_path
                ], timeout=300)

            self._run_ffmpeg_hidden([
                self.recording_manager.ffmpeg_path, "-y", "-ss", f"{start:.3f}", "-i", source_video,
                "-frames:v", "1", screenshot_path
            ], timeout=90)
            if not os.path.exists(screenshot_path):
                Image.new("RGB", (1280, 720), "#20242b").save(screenshot_path)

            shot_number, timestamp_text = self._ocr_shot_and_timestamp_from_file(screenshot_path)
            if not timestamp_text or timestamp_text in ["未识别", "OCR失败"]:
                timestamp_text = self._format_seconds_as_timecode(start)
            if not shot_number or shot_number in ["UNASSIGNED", "OCR_FAILED"]:
                shot_number = f"{safe_parent}_片段{index:03d}"

            def rel(abs_path):
                if not abs_path:
                    return None
                return os.path.relpath(abs_path, temp_base_dir).replace(os.sep, "/")

            entries.append({
                "entry_type": "long_video_segment",
                "parent_long_video": parent_entry.get("source_video"),
                "segment_start": start,
                "segment_end": end,
                "shot_number": shot_number,
                "timestamp": timestamp_text,
                "screenshot_path": rel(screenshot_path),
                "original_screenshot_path": rel(screenshot_path),
                "audio_path": None,
                "media_files": [rel(clip_path)] if os.path.exists(clip_path) else [],
                "reference_files": [],
                "full_review": str(segment.get("meeting_note") or segment.get("discussion") or segment.get("raw_discussion") or "").strip(),
                "simplified_review": str(segment.get("simplified_review") or "").strip(),
                "keywords": segment.get("keywords", []) or [],
                "department": segment.get("department", "未分类"),
            })
        return entries

    def _ocr_shot_and_timestamp_from_file(self, image_path):
        shot_number = "UNASSIGNED"
        timestamp_text = "未识别"
        try:
            with Image.open(image_path) as img:
                shot_img = img
                if self.settings.get("shot_number_crop_rect"):
                    shot_img = img.crop(tuple(self.settings["shot_number_crop_rect"]))
                else:
                    width, height = img.size
                    shot_img = img.crop((width // 2, height // 2, width, height))
                shot_number = ocr_utils.ocr_shot_number_from_image(shot_img) or "UNASSIGNED"

                time_img = img
                if self.settings.get("timestamp_crop_rect"):
                    time_img = img.crop(tuple(self.settings["timestamp_crop_rect"]))
                timestamp_text = ocr_utils.ocr_timestamp_from_image(time_img) or "未识别"
        except Exception as e:
            print(f"长视频片段 OCR 失败: {e}")
        return shot_number, timestamp_text

    @staticmethod
    def _format_seconds_as_timecode(seconds):
        seconds = max(0, int(seconds))
        h = seconds // 3600
        m = (seconds % 3600) // 60
        s = seconds % 60
        return f"{h:02d}:{m:02d}:{s:02d}"

    def _resolve_temp_path(self, relative_path):
        return self.project_manager.resolve_existing_temp_path(relative_path)

    def _build_screenshot_widget(self, image_abs_path, width=120, height=68):
        thumb_label = QLabel()
        if image_abs_path and os.path.exists(image_abs_path):
            pixmap = QPixmap(image_abs_path)
            thumb_label.setPixmap(pixmap.scaled(width, height, Qt.KeepAspectRatio, Qt.SmoothTransformation))
            thumb_label.setToolTip(image_abs_path)
        else:
            thumb_label.setText("无截图")
        thumb_label.setAlignment(Qt.AlignCenter)
        return thumb_label

    def update_screenshot_cell(self, row, image_abs_path):
        thumb_label = QLabel()
        if image_abs_path and os.path.exists(image_abs_path): 
            try:
                with open(image_abs_path, "rb") as f:
                    image_data = f.read()
                pixmap = QPixmap()
                pixmap.loadFromData(image_data)
                thumb_label.setPixmap(pixmap.scaled(150, 84, Qt.KeepAspectRatio, Qt.SmoothTransformation))
            except Exception as e:
                print(f"Error loading image into memory: {e}")
                thumb_label.setText("图片加载失败")
                thumb_label.setStyleSheet("color: red;")
        else: 
            thumb_label.setText("图片丢失")
            thumb_label.setStyleSheet("color: red;")
        thumb_label.setAlignment(Qt.AlignCenter)
        self.review_table.setCellWidget(row, COL_SCREENSHOT, thumb_label)

    def start_doodle_editor(self, row):
        if hasattr(self, 'doodle_editor_instance') and self.doodle_editor_instance:
            try:
                if not shiboken6.isValid(self.doodle_editor_instance):
                    self.doodle_editor_instance = None
            except RuntimeError:
                self.doodle_editor_instance = None

        if row < self.project_manager.get_entry_count():
            entry = self.project_manager.review_entries[row]
            rel_path = entry.get("screenshot_path")
            abs_path = self._resolve_temp_path(rel_path)
            if abs_path and os.path.exists(abs_path):
                self.doodle_editor_instance = DoodleEditor(abs_path, row)
                self.doodle_editor_instance.doodle_saved.connect(self.on_doodle_saved)
                self.doodle_editor_instance.show()
            else:
                QMessageBox.warning(self, "文件丢失", f"无法找到用于涂鸦的图片文件:\n{abs_path}")

    def update_ocr_cell(self, row, text, column):
        self.review_table.removeCellWidget(row, column)
        display_text = text or "未识别"
        item = QTableWidgetItem(display_text)
        if display_text in ["未识别", "OCR失败"]:
            item.setForeground(Qt.GlobalColor.red)
            item.setToolTip("可双击手动修改，或右键选择重新识别。")
        self.review_table.setItem(row, column, item)

    def retry_ocr(self, row, column):
        if row < self.project_manager.get_entry_count():
            rel_image_path = self.project_manager.review_entries[row].get("screenshot_path")
            abs_image_path = self._resolve_temp_path(rel_image_path)
            if abs_image_path and os.path.exists(abs_image_path):
                self.crop_window_instance = CropWindow(abs_image_path, row, column)
                self.crop_window_instance.ocr_retry_signal.connect(self.on_ocr_retry)
                self.crop_window_instance.show()
            else:
                QMessageBox.warning(self, "文件丢失", f"无法找到用于 OCR 的截图文件:\n{abs_image_path}")

    def on_ocr_retry(self, row, crop_rect, column):
        if row < self.project_manager.get_entry_count():
            rel_image_path = self.project_manager.review_entries[row].get("screenshot_path")
            abs_image_path = self._resolve_temp_path(rel_image_path)
            if abs_image_path and os.path.exists(abs_image_path):
                threading.Thread(target=self.retry_ocr_worker, args=(row, abs_image_path, crop_rect, column)).start()

    def retry_ocr_worker(self, row, image_abs_path, crop_rect, column):
        try:
            with Image.open(image_abs_path) as img: 
                box = (crop_rect.left(), crop_rect.top(), crop_rect.right(), crop_rect.bottom())
                text = ""
                if column == COL_TIMESTAMP:
                    text = ocr_utils.ocr_timestamp_from_image(img.crop(box))
                    self.settings["timestamp_crop_rect"] = box  # Store the crop rect
                elif column == COL_SHOT:
                    text = ocr_utils.ocr_shot_number_from_image(img.crop(box))
                    self.settings["shot_number_crop_rect"] = box  # Store the crop rect
                else:
                    text = ocr_utils.image_to_string(img.crop(box))
                
                # Save settings after updating crop rect
                self.save_settings() 
                
                QApplication.instance().postEvent(self, CustomEvent({"row": row, "text": text, "column": column}, RETRY_OCR_DONE_EVENT_TYPE))
        except Exception as e:
            print(f"二次 OCR 失败: {e}")

    def _build_reference_cell_widget(self, row):
        if row >= len(self.project_manager.review_entries):
            return QWidget()
        entry = self.project_manager.review_entries[row]
        ref_files_rel = entry.get("reference_files", [])
        cell_widget = QWidget()
        layout = QGridLayout(cell_widget)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setHorizontalSpacing(4)
        layout.setVerticalSpacing(4)
        for idx, rel_path in enumerate(ref_files_rel):
            abs_path = self._resolve_temp_path(rel_path)
            label = QLabel(os.path.basename(rel_path))
            label.setToolTip(abs_path)
            label.setStyleSheet("color: #d8dee9;")
            view_btn = self._make_cell_tool_button("查看", QStyle.StandardPixmap.SP_FileDialogContentsView)
            view_btn.clicked.connect(lambda _, p=abs_path: self.open_file(p))
            remove_btn = self._make_cell_tool_button("移除", QStyle.StandardPixmap.SP_DialogCloseButton)
            remove_btn.clicked.connect(lambda _, r=row, p=rel_path: self.remove_reference_file(r, p))
            layout.addWidget(label, idx, 0)
            layout.addWidget(view_btn, idx, 1)
            layout.addWidget(remove_btn, idx, 2)
        add_btn = self._make_cell_tool_button("添加", QStyle.StandardPixmap.SP_FileDialogNewFolder)
        add_btn.clicked.connect(lambda _, r=row: self.handle_add_reference_file(r))
        layout.addWidget(add_btn, len(ref_files_rel), 0, 1, 3)
        return cell_widget

    def update_reference_cell(self, row):
        cell_widget = self._build_reference_cell_widget(row)
        self.review_table.setCellWidget(row, COL_REFERENCE, cell_widget)

    def remove_reference_file(self, row, rel_path):
        if row < self.project_manager.get_entry_count() and "reference_files" in self.project_manager.review_entries[row]:
            self.project_manager._snapshot_state("Remove Reference")
            try:
                self.project_manager.review_entries[row]["reference_files"].remove(rel_path)
            except ValueError:
                print(f"尝试删除一个不存在的参考文件条目: {rel_path}")
            self.update_reference_cell(row)
            self.refresh_views()
            if self.project_manager.current_project_file:
                self.project_manager.save_project(autosave=True)

    def handle_table_double_click(self, index):
        if index.column() == COL_SCREENSHOT:
            row = index.row()
            if row < self.project_manager.get_entry_count():
                entry = self.project_manager.review_entries[row]
                rel_image_path = entry.get("screenshot_path")
                abs_image_path = self._resolve_temp_path(rel_image_path)
                if abs_image_path and os.path.exists(abs_image_path):
                    self.open_file(abs_image_path)
                else:
                    QMessageBox.warning(self, "文件未找到", f"无法找到对应的截图文件：{abs_image_path}")

    def handle_input_table_double_click(self, index):
        source_col = self._input_table_source_col(index.column())
        if source_col != COL_SCREENSHOT:
            return
        row = self._input_table_source_row(index.row())
        if row < self.project_manager.get_entry_count():
            entry = self.project_manager.review_entries[row]
            rel_image_path = entry.get("screenshot_path")
            abs_image_path = self._resolve_temp_path(rel_image_path)
            if abs_image_path and os.path.exists(abs_image_path):
                self.open_file(abs_image_path)
            else:
                QMessageBox.warning(self, "文件未找到", f"无法找到对应的截图文件：{abs_image_path}")

    def store_cell_value_on_press(self, row, column):
        item = self.review_table.item(row, column)
        if item:
            self._current_cell_value = item.text()

    def store_input_cell_value_on_press(self, row, column):
        item = self.latest_table.item(row, column)
        self._current_cell_value = item.text() if item else None

    def setup_hotkey_listener(self):
        if sys.platform != "win32":
            print("WARNING: 全局快捷键目前仅在 Windows 下启用。")
            return

        hwnd = int(self.winId())
        user32 = ctypes.windll.user32
        self._annotation_hotkey_label = None

        if user32.RegisterHotKey(hwnd, HOTKEY_REVIEW_ID, MOD_CONTROL, VK_R):
            self._registered_hotkeys.append(HOTKEY_REVIEW_ID)
        else:
            error_code = ctypes.windll.kernel32.GetLastError()
            print(f"WARNING: 注册快捷键 Ctrl+R 失败，错误码: {error_code}")

        annotation_candidates = [
            (MOD_CONTROL | MOD_SHIFT, VK_A, "Ctrl+Shift+A"),
            (MOD_CONTROL | MOD_ALT, VK_A, "Ctrl+Alt+A"),
        ]
        annotation_failures = []
        for modifiers, key, label in annotation_candidates:
            if user32.RegisterHotKey(hwnd, HOTKEY_ANNOTATION_ID, modifiers, key):
                self._registered_hotkeys.append(HOTKEY_ANNOTATION_ID)
                self._annotation_hotkey_label = label
                break
            error_code = ctypes.windll.kernel32.GetLastError()
            annotation_failures.append(f"{label}: {error_code}")
        if not self._annotation_hotkey_label:
            print(f"WARNING: 截图批注全局快捷键注册失败（{'; '.join(annotation_failures)}），请使用工具栏“截图批注”按钮。")
        if self._registered_hotkeys:
            annotation_label = self._annotation_hotkey_label or "工具栏按钮"
            print(f"协同审阅平台已激活。快捷键: Ctrl+R (审阅), {annotation_label} (截图批注)")

    def unregister_hotkeys(self):
        if sys.platform != "win32" or not self._registered_hotkeys:
            return
        hwnd = int(self.winId())
        user32 = ctypes.windll.user32
        for hotkey_id in self._registered_hotkeys:
            user32.UnregisterHotKey(hwnd, hotkey_id)
        self._registered_hotkeys.clear()

    def nativeEvent(self, event_type, message):
        if sys.platform == "win32":
            try:
                msg = wintypes.MSG.from_address(int(message))
            except Exception:
                msg = None
            if msg and msg.message == WM_HOTKEY:
                if msg.wParam == HOTKEY_REVIEW_ID:
                    self.hotkey_pressed_signal.emit()
                    return True, 0
                if msg.wParam == HOTKEY_ANNOTATION_ID:
                    self.annotation_hotkey_signal.emit()
                    return True, 0
        return super().nativeEvent(event_type, message)

    def _begin_quiet_capture_window_state(self):
        state = {
            "visible": self.isVisible() and not self.isMinimized(),
            "opacity": self.windowOpacity(),
        }
        if state["visible"]:
            self.setWindowOpacity(0.0)
            QApplication.processEvents()
            time.sleep(0.04)
            self.hide()
            QApplication.processEvents()
            time.sleep(0.08)
        return state

    def _restore_quiet_capture_window_state(self, state=None):
        state = state or self._quiet_capture_state
        self._quiet_capture_state = None
        if not state or not state.get("visible"):
            return
        previous_opacity = state.get("opacity", 1.0)
        self.setWindowOpacity(0.0)
        self.showNormal()
        QApplication.processEvents()
        self.setWindowOpacity(previous_opacity)

    def toggle_review_capture(self):
        if self.recording_manager.is_recording():
            self.recording_manager.stop()
            self.statusBar().showMessage("正在处理...", 0)
            self.update_recording_ui_state(False)
        else:
            if not self._ensure_project_ready_for_assets():
                return
            should_record_video = self.record_video_checkbox.isChecked()
            status_text = self.recording_manager.start(should_record_video, self.project_manager.current_temp_dir)
            if status_text:
                self.update_recording_ui_state(True, status_text)
                self.statusBar().showMessage(status_text, 0)

    def open_recording_annotation_overlay(self):
        if self._annotation_capture_busy:
            return
        # 清理已被 Qt 删除的 overlay 引用
        if self.annotation_overlay:
            try:
                if not shiboken6.isValid(self.annotation_overlay):
                    self.annotation_overlay = None
            except RuntimeError:
                self.annotation_overlay = None

        if not self.recording_manager.is_recording():
            self._direct_annotation_mode = True
        else:
            self._direct_annotation_mode = False

        if self.annotation_overlay and self.annotation_overlay.isVisible():
            self.annotation_overlay.activateWindow()
            return
        if not self.project_manager.current_temp_dir:
            QMessageBox.warning(self, "无法批注", "项目临时目录未设置，请先保存项目。")
            return
        self._annotation_capture_busy = True
        self._quiet_capture_state = self._begin_quiet_capture_window_state()
        try:
            import mss
            with mss.mss() as sct:
                monitor_index = self.settings.get("screen_record_monitor", 0)
                if monitor_index >= len(sct.monitors):
                    monitor_index = 0
                monitor = sct.monitors[monitor_index]
                sct_img = sct.grab(monitor)
                img = Image.frombytes("RGB", sct_img.size, sct_img.bgra, "raw", "BGRX")
                if self._direct_annotation_mode:
                    pending_dir = os.path.join(self.project_manager.current_temp_dir, "snapshots")
                else:
                    pending_dir = os.path.join(self.project_manager.current_temp_dir, "_pending_annotations")
                os.makedirs(pending_dir, exist_ok=True)
                capture_path = os.path.join(pending_dir, f"direct_snap_{int(time.time())}.png" if self._direct_annotation_mode else f"annotation_source_{int(time.time())}.png")
                img.save(capture_path, quality=95)
        except Exception as e:
            self._annotation_capture_busy = False
            self._restore_quiet_capture_window_state()
            QMessageBox.critical(self, "截图失败", f"无法创建批注截图:\n{e}")
            return

        self.annotation_overlay = AnnotationOverlay(capture_path, os.path.dirname(capture_path), None)
        self.annotation_overlay.destroyed.connect(self.on_annotation_overlay_closed)
        self.annotation_overlay.annotation_saved.connect(self.on_recording_annotation_saved)
        self.annotation_overlay.show()

    def on_annotation_overlay_closed(self):
        self.annotation_overlay = None
        self._annotation_capture_busy = False
        QTimer.singleShot(80, lambda: self._restore_quiet_capture_window_state())

    def on_recording_annotation_saved(self, annotated_path):
        if not annotated_path or not os.path.exists(annotated_path):
            return
        if hasattr(self, "_direct_annotation_mode") and self._direct_annotation_mode:
            import threading
            review_data = {
                "screenshot_path": annotated_path,
                "audio_path": None,
                "media_files": [],
                "reference_files": [],
                "full_review": "",
                "simplified_review": "",
                "keywords": [],
                "department": "未分类",
                "timestamp": "未识别",
                "shot_number": "UNASSIGNED"
            }
            threading.Thread(target=self.process_ocr_task, args=(review_data,), daemon=True).start()
            self.statusBar().showMessage("截图已保存并生成审阅条目，正在进行OCR识别...", 5000)
        else:
            self.recording_manager.pending_review_data.setdefault("pending_reference_files", []).append(annotated_path)
            self.statusBar().showMessage(f"批注截图已保存，将在本条审阅完成后加入参考: {os.path.basename(annotated_path)}", 5000)

    def on_recording_finished(self, data):
        threading.Thread(target=self.process_ocr_task, args=(data,), daemon=True).start()

    def process_ocr_task(self, review_data):
        try:
            with Image.open(review_data["screenshot_path"]) as img:
                                # OCR for shot number
                                shot_number_img = img
                                if self.settings.get("shot_number_crop_rect"):
                                    box = tuple(self.settings["shot_number_crop_rect"])
                                    shot_number_img = img.crop(box)
                                else:
                                    # Fallback to bottom-right quarter if no stored crop
                                    width, height = img.size
                                    shot_number_img = img.crop((width // 2, height // 2, width, height))
                                review_data["shot_number"] = ocr_utils.ocr_shot_number_from_image(shot_number_img) or "UNASSIGNED"
                
                                # OCR for timestamp
                                timestamp_img = img
                                if self.settings.get("timestamp_crop_rect"):
                                    box = tuple(self.settings["timestamp_crop_rect"])
                                    timestamp_img = img.crop(box)
                                # No fallback for timestamp, it always uses full image if no stored crop
                                review_data["timestamp"] = ocr_utils.ocr_timestamp_from_image(timestamp_img) or "未识别"
        except Exception as e:
            print(f"OCR 处理失败: {e}")
            review_data["shot_number"] = "OCR_FAILED"
            review_data["timestamp"] = "OCR失败"
        shot_name = review_data.get("shot_number", "UNASSIGNED")
        sane_shot_name = re.sub(r'[\\/:*?"<>|]', '_', shot_name.strip()) if shot_name else "UNASSIGNED"
        temp_base_dir = self.project_manager.current_temp_dir
        if not temp_base_dir:
            QMessageBox.critical(self, "错误", "项目临时目录未设定，无法保存文件。")
            return
        def move_and_get_relative_path(abs_path, asset_type, shot_folder, dest_filename=None):
            if not abs_path or not os.path.exists(abs_path):
                return None
            filename = dest_filename or os.path.basename(abs_path)
            relative_path = os.path.join(asset_type, shot_folder, filename).replace(os.sep, '/')
            dest_path = os.path.join(temp_base_dir, relative_path.replace('/', os.sep))
            dest_path = self.project_manager._unique_destination_path(dest_path, abs_path)
            relative_path = os.path.relpath(dest_path, temp_base_dir).replace(os.sep, '/')
            os.makedirs(os.path.dirname(dest_path), exist_ok=True)
            if os.path.abspath(abs_path) != os.path.abspath(dest_path):
                shutil.move(abs_path, dest_path)
            return relative_path
        new_ss_rel_path = move_and_get_relative_path(review_data.get("screenshot_path"), "snapshots", sane_shot_name)
        review_data["screenshot_path"] = new_ss_rel_path
        review_data["original_screenshot_path"] = new_ss_rel_path 
        new_audio_rel_path = move_and_get_relative_path(review_data.get("audio_path"), "audio", sane_shot_name)
        review_data["audio_path"] = new_audio_rel_path
        new_media_rel_paths = []
        for media_file_abs in review_data.get("media_files", []):
            feedback_video_name = (
                self.project_manager.feedback_video_filename(shot_name, media_file_abs)
                if self.project_manager._is_video_file(media_file_abs)
                else None
            )
            rel_path = move_and_get_relative_path(media_file_abs, "recordings", sane_shot_name, feedback_video_name)
            if rel_path:
                new_media_rel_paths.append(rel_path)
        review_data["media_files"] = new_media_rel_paths
        new_reference_rel_paths = []
        for ref_file_abs in review_data.get("pending_reference_files", []):
            rel_path = move_and_get_relative_path(ref_file_abs, "reference", sane_shot_name)
            if rel_path:
                new_reference_rel_paths.append(rel_path)
        review_data["reference_files"] = review_data.get("reference_files", []) + new_reference_rel_paths
        review_data.pop("pending_reference_files", None)
        review_data["full_review"] = ""
        QApplication.instance().postEvent(self, CustomEvent(review_data, ADD_REVIEW_EVENT_TYPE))

    def manual_transcribe(self, row):
        if hasattr(self, 'mobile_text_override') and self.mobile_text_override:
            text = self.mobile_text_override
            self.mobile_text_override = None
            QApplication.instance().postEvent(self, CustomEvent({"row": row, "text": text}, TRANSCRIPTION_DONE_EVENT_TYPE))
            return
        if self.is_transcribing_batch:
            QMessageBox.information(self, "提示", "批量转录任务正在进行中。")
            return
        if row < self.project_manager.get_entry_count():
            entry = self.project_manager.review_entries[row]
            rel_audio_path = entry.get("audio_path")
            abs_audio_path = self._resolve_temp_path(rel_audio_path)
            if not abs_audio_path or not os.path.exists(abs_audio_path):
                QMessageBox.warning(self, "文件未找到", f"无法找到待转录的音频文件:\n{abs_audio_path or rel_audio_path}")
                return
            if self._transcription_loading:
                self.statusBar().showMessage(f"语音模型仍在加载，加载完成后转录第 {row + 1} 行...", 0)
            else:
                self.statusBar().showMessage(f"正在转录第 {row + 1} 行...", 0)
            widget = self.review_table.cellWidget(row, COL_FULL_REVIEW)
            if widget and isinstance(widget, QPushButton):
                widget.setEnabled(False)
                widget.setText("转录中...")
            threading.Thread(target=self.transcribe_audio_worker, args=(abs_audio_path, row), daemon=True).start()

    def transcribe_all_pending(self):
        if self.is_transcribing_batch:
            QMessageBox.information(self, "提示", "已有转录任务正在进行中。")
            return
        self.pending_batch_rows = [
            r for r, entry in enumerate(self.project_manager.review_entries)
            if not entry.get("full_review") and entry.get("audio_path")
        ]
        if not self.pending_batch_rows:
            QMessageBox.information(self, "提示", "没有需要转录的条目。")
            return
        self.is_transcribing_batch = True
        self.transcribe_all_action.setEnabled(False)
        self.statusBar().showMessage(f"开始批量转录 {len(self.pending_batch_rows)} 个条目...", 0)
        self.manual_transcribe(self.pending_batch_rows.pop(0))

    def process_all_reviews_with_ai(self):
        if self.is_ai_processing:
            QMessageBox.information(self, "提示", "AI 正在处理中。")
            return
        if self._ai_requires_api_key() and not self.settings.get("api_key"):
            QMessageBox.warning(self, "缺少 API Key", "请在 AI 设置中输入 API Key。")
            self.open_settings()
            return
        if not self._ensure_local_ai_ready():
            return
        tasks_to_process, original_indices = [], {}
        for row in range(self.project_manager.get_entry_count()):
            entry = self.project_manager.review_entries[row]
            if entry.get("entry_type") == "long_video_full":
                continue
            if entry.get("full_review") and not entry.get("simplified_review"):
                tasks_to_process.append({"text": entry["full_review"], "entry_type": entry.get("entry_type", "short_review")})
                original_indices[len(tasks_to_process) - 1] = row
        if not tasks_to_process:
            QMessageBox.information(self, "提示", "没有需要 AI 处理的有效条目。")
            return
        self.is_ai_processing = True
        self.ai_process_action.setEnabled(False)
        self.statusBar().showMessage(f"AI 批量处理中 (0/{len(tasks_to_process)})...", 0)
        threading.Thread(target=self.ai_processing_worker, args=(tasks_to_process, original_indices), daemon=True).start()

    def process_all_reviews_with_ai_auto(self):
        if self.settings.get("ai_provider") in LOCAL_AI_PROVIDERS and not self._is_local_ai_server_available():
            self.statusBar().showMessage("转录完成；AI 服务未连接，已跳过自动批量优化。", 5000)
            return
        self.process_all_reviews_with_ai()

    def process_selected_review_with_ai(self):
        row = self.review_table.currentRow()
        if row < 0:
            QMessageBox.information(self, "提示", "请先选中一条审阅记录。")
            return
        self.process_single_review_with_ai(row)

    def process_single_review_with_ai(self, row, silent=False):
        if self.is_ai_processing:
            if not silent:
                QMessageBox.information(self, "提示", "AI 正在处理中。")
            return
        if not (0 <= row < self.project_manager.get_entry_count()):
            return
        if self._ai_requires_api_key() and not self.settings.get("api_key"):
            if not silent:
                QMessageBox.warning(self, "缺少 API Key", "请在 AI 设置中输入 API Key。")
                self.open_settings()
            return
        if silent:
            if not self._is_local_ai_server_available():
                self.statusBar().showMessage("转录完成；AI 服务未连接，已跳过自动优化。", 5000)
                return
        elif not self._ensure_local_ai_ready():
            return
        text = self.project_manager.review_entries[row].get("full_review", "").strip()
        if not text:
            if not silent:
                QMessageBox.information(self, "提示", "这条记录没有完整意见，无法优化。")
            return
        if self.project_manager.review_entries[row].get("entry_type") == "long_video_full":
            self.start_long_video_segmentation(row, self.project_manager.review_entries[row].get("transcript_segments", []))
            return
        self.is_ai_processing = True
        self.ai_process_action.setEnabled(False)
        self.ai_rewrite_selected_action.setEnabled(False)
        self.statusBar().showMessage(f"正在优化第 {row + 1} 条完整意见...", 0)
        threading.Thread(target=self.ai_rewrite_worker, args=(row, text), daemon=True).start()

    def ai_rewrite_worker(self, row, text):
        try:
            ai_proc = AIProcessor(
                provider=self.settings.get("ai_provider", "local-ai"),
                api_key=self.settings.get("api_key", "local"),
                base_url=self.settings.get("base_url", DEFAULT_LOCAL_AI_BASE_URL),
                model_name=self.settings.get("model_name", DEFAULT_QWEN_MODEL),
            )
            entry = self.project_manager.review_entries[row] if 0 <= row < self.project_manager.get_entry_count() else {}
            if entry.get("entry_type") == "long_video_segment":
                result = ai_proc.analyze(text, self.settings.get("departments"))
                QApplication.instance().postEvent(self, CustomEvent({"row": row, "result": result, "replace_full_review": False}, AI_UPDATE_EVENT_TYPE))
            else:
                result = ai_proc.rewrite_review(text, self.settings.get("departments"))
                QApplication.instance().postEvent(self, CustomEvent({"row": row, "result": result, "replace_full_review": True}, AI_UPDATE_EVENT_TYPE))
        except Exception as e:
            QApplication.instance().postEvent(self, CustomEvent({"error": str(e)}, AI_UPDATE_EVENT_TYPE))
        finally:
            QApplication.instance().postEvent(self, CustomEvent({"completed": True}, AI_UPDATE_EVENT_TYPE))

    def ai_processing_worker(self, tasks, indices_map):
        try:
            ai_proc = AIProcessor(
                provider=self.settings.get("ai_provider", "local-ai"),
                api_key=self.settings.get("api_key", "local"),
                base_url=self.settings.get("base_url", DEFAULT_LOCAL_AI_BASE_URL),
                model_name=self.settings.get("model_name", DEFAULT_QWEN_MODEL),
            )
            departments = self.settings.get("departments")
            with ThreadPoolExecutor(max_workers=self._ai_max_workers()) as executor:
                future_to_row = {}
                for i, task in enumerate(tasks):
                    if task.get("entry_type") == "long_video":
                        future = executor.submit(ai_proc.summarize_long_review, task["text"], departments)
                    else:
                        future = executor.submit(ai_proc.analyze, task["text"], departments)
                    future_to_row[future] = indices_map[i]
                completed_count, total_tasks = 0, len(tasks)
                for future in future_to_row:
                    row, result = future_to_row[future], future.result()
                    if result:
                        QApplication.instance().postEvent(self, CustomEvent({"row": row, "result": result}, AI_UPDATE_EVENT_TYPE))
                    completed_count += 1
                    self.statusBar().showMessage(f"AI 批量处理中 ({completed_count}/{total_tasks})...", 0)
        except Exception as e:
            print(f"AI 处理工作线程发生错误: {e}")
            QApplication.instance().postEvent(self, CustomEvent({"error": str(e)}, AI_UPDATE_EVENT_TYPE))
        finally:
            QApplication.instance().postEvent(self, CustomEvent({"completed": True}, AI_UPDATE_EVENT_TYPE))

    def _ai_requires_api_key(self):
        return self.settings.get("ai_provider") not in LOCAL_AI_PROVIDERS

    def _ai_max_workers(self):
        return 1 if self.settings.get("ai_provider") in LOCAL_AI_PROVIDERS else 5

    def _local_ai_base_url(self):
        base_url = (self.settings.get("base_url") or DEFAULT_LOCAL_AI_BASE_URL).strip().rstrip("/")
        if self.settings.get("ai_provider") in LOCAL_AI_PROVIDERS and base_url and not base_url.endswith("/v1"):
            base_url = f"{base_url}/v1"
        return base_url

    def _is_local_ai_server_available(self):
        if self.settings.get("ai_provider") not in LOCAL_AI_PROVIDERS:
            return True
        base_url = self._local_ai_base_url()
        candidates = [f"{base_url}/models"]
        if base_url.endswith("/v1"):
            candidates.append(f"{base_url[:-3]}/models")
        last_error = None
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        for url in dict.fromkeys(candidates):
            try:
                request = urllib.request.Request(url)
                with opener.open(request, timeout=2) as response:
                    if 200 <= response.status < 300:
                        return True
            except Exception as e:
                last_error = e
        print(f"本地 AI 服务检测失败: {last_error}")
        return False

    def _find_lm_studio_executable(self):
        candidates = [
            os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs", "LM Studio", "LM Studio.exe"),
            os.path.join(os.environ.get("LOCALAPPDATA", ""), "LM Studio", "LM Studio.exe"),
            os.path.join(os.environ.get("ProgramFiles", ""), "LM Studio", "LM Studio.exe"),
            os.path.join(os.environ.get("ProgramFiles(x86)", ""), "LM Studio", "LM Studio.exe"),
        ]
        for path in candidates:
            if path and os.path.isfile(path):
                return path
        return None

    def _local_ai_host_port(self):
        base_url = self._local_ai_base_url()
        match = re.search(r"https?://([^/:]+)(?::(\d+))?", base_url)
        if not match:
            return "127.0.0.1", 8080
        host = match.group(1) or "127.0.0.1"
        port = int(match.group(2) or 8080)
        return host, port

    def _local_model_roots(self):
        roots = []
        configured_root = self.settings.get("local_model_root") or self.settings.get("model_root")
        for root in [configured_root, *PREFERRED_LOCAL_MODEL_ROOTS, app_base_path()]:
            if root and root not in roots:
                roots.append(root)
        return roots

    def _find_bundled_qwen_files(self):
        for root in self._local_model_roots():
            llama_dir = os.path.join(root, LLAMA_CPP_DIR)
            model_dir = os.path.join(root, QWEN_MODEL_DIR)
            server_path = os.path.join(llama_dir, "llama-server.exe")
            model_path = os.path.join(model_dir, DEFAULT_QWEN_MODEL)
            if not os.path.isfile(server_path) or not os.path.isfile(model_path):
                continue

            mmproj_path = ""
            for name in (
                "mmproj-Qwen3VL-8B-Instruct-F16.gguf",
                "mmproj-Qwen3VL-8B-Instruct-Q8_0.gguf",
            ):
                candidate = os.path.join(model_dir, name)
                if os.path.isfile(candidate):
                    mmproj_path = candidate
                    break
            if not mmproj_path:
                for name in os.listdir(model_dir):
                    if name.lower().endswith(".gguf") and "mmproj" in name.lower():
                        mmproj_path = os.path.join(model_dir, name)
                        break
            return llama_dir, server_path, model_path, mmproj_path
        return None

    def _try_start_bundled_qwen_server(self):
        files = self._find_bundled_qwen_files()
        if not files:
            print("Bundled Qwen3-VL server files were not found.")
            return False

        llama_dir, server_path, model_path, mmproj_path = files
        host, port = self._local_ai_host_port()
        command = [
            server_path,
            "--model", model_path,
            "--host", host,
            "--port", str(port),
            "--ctx-size", "8192",
            "--n-gpu-layers", "99",
            "--parallel", "1",
        ]
        if mmproj_path:
            command.extend(["--mmproj", mmproj_path])

        try:
            log_path = os.path.join(app_base_path(), "qwen_server.log")
            log_file = open(log_path, "a", encoding="utf-8", errors="replace")
            log_file.write("\n\n=== Starting bundled Qwen3-VL server ===\n")
            log_file.write(" ".join(f'"{part}"' if " " in part else part for part in command) + "\n")
            log_file.flush()
            env = os.environ.copy()
            env["PATH"] = llama_dir + os.pathsep + env.get("PATH", "")
            self.local_ai_process = subprocess.Popen(
                command,
                cwd=llama_dir,
                stdout=log_file,
                stderr=subprocess.STDOUT,
                close_fds=True,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                env=env,
            )
            print(f"Started bundled Qwen3-VL server on {host}:{port}. Log: {log_path}")
            return True
        except Exception as e:
            print(f"Failed to start bundled Qwen3-VL server: {e}")
            return False

    def _try_start_lm_studio(self):
        lm_studio_path = self._find_lm_studio_executable()
        if not lm_studio_path:
            print("LM Studio.exe not found.")
            return False
        try:
            subprocess.Popen(
                [lm_studio_path],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                close_fds=True,
            )
            print(f"已尝试启动 LM Studio: {lm_studio_path}")
            return True
        except Exception as e:
            print(f"启动 LM Studio 失败: {e}")
            return False

    def _try_start_local_ai_server(self):
        startup_scripts = [
            os.path.join(root, "启动Qwen.bat")
            for root in self._local_model_roots()
        ]
        for startup_script in startup_scripts:
            if not os.path.isfile(startup_script):
                continue
            script_root = os.path.dirname(startup_script)
            server_path = os.path.join(script_root, LLAMA_CPP_DIR, "llama-server.exe")
            model_path = os.path.join(script_root, QWEN_MODEL_DIR, DEFAULT_QWEN_MODEL)
            if not os.path.isfile(server_path) or not os.path.isfile(model_path):
                print(f"跳过本地 AI 启动脚本，缺少服务端或模型: {startup_script}")
                continue
            try:
                command = [os.environ.get("ComSpec", "cmd.exe"), "/c", "call", startup_script]
                self.local_ai_process = subprocess.Popen(
                    command,
                    cwd=script_root,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    close_fds=True,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )
                print(f"已尝试启动本地 AI 服务脚本: {startup_script}")
                return True
            except Exception as e:
                print(f"启动本地 AI 服务脚本失败: {e}")
        return self._try_start_bundled_qwen_server()

    def start_local_ai_on_app_start(self):
        if self.settings.get("ai_provider") not in LOCAL_AI_PROVIDERS:
            return
        if self._is_local_ai_server_available():
            print("本地 AI 服务已可用。")
            return
        if self._local_ai_launching:
            return
        self._local_ai_launching = True
        threading.Thread(target=self._local_ai_start_worker, daemon=True).start()

    def _local_ai_start_worker(self):
        try:
            if not self._try_start_local_ai_server():
                print("未找到可自动启动的本地 AI 服务。")
                return
            for _ in range(30):
                if self._is_local_ai_server_available():
                    print("本地 AI 服务启动完成。")
                    return
                time.sleep(1)
            print("本地 AI 服务已尝试启动，但检测仍未通过。")
        finally:
            self._local_ai_launching = False

    def start_background_services_on_app_start(self):
        if self.settings.get("auto_start_transcription_service", True):
            threading.Thread(target=self.load_transcription_model, kwargs={"show_dialog": False}, daemon=True).start()
        if self.settings.get("auto_start_ai_service", True):
            self.start_local_ai_on_app_start()

    def _ensure_local_ai_ready(self):
        if self.settings.get("ai_provider") not in LOCAL_AI_PROVIDERS:
            return True
        if self._is_local_ai_server_available():
            return True

        QMessageBox.information(
            self,
            "AI 服务未连接",
            "当前没有连接到 AI 服务。\n\n"
            "转写功能可以单独使用，不会自动联动 AI。\n"
            "需要 AI 分析时，请在设置里配置可用的 OpenAI 兼容服务地址和模型名。",
        )
        self.open_settings()
        return False
    def load_settings(self):
        default_settings = {
            "project_name": "未命名项目", "producer": "", "reviewer": "",
            "selected_model": "funasr-paraformer-zh", "ai_provider": "local-ai",
            "api_key": "local", "base_url": DEFAULT_LOCAL_AI_BASE_URL, "model_name": DEFAULT_QWEN_MODEL, 
            "realtime_transcribe": True, "screen_record_fps": 25, 
            "screen_record_monitor": 0, "ffmpeg_path": "", 
            "departments": ["解算", "动画", "合成", "灯光", "特效", "UE特效", "传统特效", "调色", "AE", "AI", "组装", "地编"],
            "audio_device_index": None,
            "shot_number_crop_rect": None, "timestamp_crop_rect": None,
            "transcription_device": "auto", "transcription_compute_type": "auto",
            "screen_capture_backend": "gdigrab", "video_encoder": "libx264",
            "enable_annotation_overlay": True, "theme": "light",
            "auto_start_transcription_service": True,
            "auto_start_ai_service": True,
            "table_column_widths": [],
            "table_column_ratios": [],
            "table_default_row_height": 110,
            "table_row_heights": {},
            "recent_projects": [],
            "cgtw_sync": default_cgtw_settings(),
        }
        try:
            if os.path.exists("settings.json"):
                with open("settings.json", "r", encoding="utf-8") as f:
                    loaded_settings = json.load(f)
                    settings = default_settings | loaded_settings
                    settings["cgtw_sync"] = default_cgtw_settings() | loaded_settings.get("cgtw_sync", {})
                    if (
                        settings.get("ai_provider") in LOCAL_AI_PROVIDERS
                        and settings.get("base_url") in {"http://127.0.0.1:1234/v1", "http://127.0.0.1:1234"}
                    ):
                        settings["ai_provider"] = "local-ai"
                        settings["base_url"] = DEFAULT_LOCAL_AI_BASE_URL
                        settings["model_name"] = DEFAULT_QWEN_MODEL
                    if not str(settings.get("selected_model", "")).startswith("funasr"):
                        settings["selected_model"] = "funasr-paraformer-zh"
                    return settings
            else:
                self.settings = default_settings
                self.save_settings()
                return default_settings
        except Exception:
            return default_settings

    def save_settings(self):
        try:
            with open("settings.json", "w", encoding="utf-8") as f:
                json.dump(self.settings, f, indent=4, ensure_ascii=False)
        except Exception as e:
            print(f"保存设置失败: {e}")

    def on_model_changed(self, model_name):
        self.settings["selected_model"] = model_name
        self.whisper_model = None
        self._transcription_model_name = None
        self._whisper_load_error = None
        self._post_model_load_status("未加载", model_name)
        self.save_settings()
        self.statusBar().showMessage(f"语音转写模型已设置为 {model_name}，正在后台预热...", 4000)
        threading.Thread(target=self.load_transcription_model, kwargs={"show_dialog": False}, daemon=True).start()

    def transcribe_with_loaded_model(self, audio_path):
        detailed = self.transcribe_with_loaded_model_detailed(audio_path)
        return detailed.get("text", "")

    def transcribe_long_audio_with_loaded_model(self, audio_path, chunk_seconds=300):
        try:
            with wave.open(audio_path, "rb") as source:
                channels = source.getnchannels()
                sample_width = source.getsampwidth()
                frame_rate = source.getframerate()
                total_frames = source.getnframes()
                frames_per_chunk = max(1, int(frame_rate * chunk_seconds))
                chunk_dir = os.path.join(os.path.dirname(audio_path), "_long_audio_chunks")
                os.makedirs(chunk_dir, exist_ok=True)
                all_segments = []
                text_parts = []
                chunk_index = 0
                while source.tell() < total_frames:
                    start_frame = source.tell()
                    frames = source.readframes(frames_per_chunk)
                    if not frames:
                        break
                    chunk_duration = len(frames) / max(1, sample_width * channels * frame_rate)
                    offset = start_frame / frame_rate
                    chunk_path = os.path.join(chunk_dir, f"chunk_{chunk_index:04d}.wav")
                    with wave.open(chunk_path, "wb") as chunk:
                        chunk.setnchannels(channels)
                        chunk.setsampwidth(sample_width)
                        chunk.setframerate(frame_rate)
                        chunk.writeframes(frames)
                    detailed = self.transcribe_with_loaded_model_detailed(chunk_path)
                    chunk_text = detailed.get("text", "").strip()
                    if chunk_text:
                        text_parts.append(chunk_text)
                    for segment in detailed.get("segments", []):
                        seg_text = str(segment.get("text", "")).strip()
                        if not seg_text:
                            continue
                        start = float(segment.get("start") or 0) + offset
                        end = float(segment.get("end") or 0) + offset
                        if end <= start:
                            end = offset + chunk_duration
                        all_segments.append({"start": start, "end": end, "text": seg_text})
                    if chunk_text and not detailed.get("segments"):
                        all_segments.append({"start": offset, "end": offset + chunk_duration, "text": chunk_text})
                    chunk_index += 1
                return {"text": "\n".join(text_parts).strip(), "segments": all_segments}
        except Exception as e:
            print(f"长音频分块转写失败，回退到单次转写: {e}")
            return self.transcribe_with_loaded_model_detailed(audio_path)

    def transcribe_with_loaded_model_detailed(self, audio_path):
        model_name = self._transcription_model_name or self.settings.get("selected_model", "funasr-paraformer-zh")
        if not model_name.startswith("funasr"):
            self.settings["selected_model"] = "funasr-paraformer-zh"
        result = self.whisper_model.generate(input=audio_path, batch_size_s=300)
        return self._parse_funasr_transcription_result(result)

    def _parse_funasr_transcription_result(self, result):
        raw_items = result if isinstance(result, list) else [result]
        detail_segments = []
        text_parts = []
        for item in raw_items:
            if not isinstance(item, dict):
                text = str(item).strip()
                if text:
                    text_parts.append(text)
                continue
            text = str(item.get("text", "")).strip()
            if text:
                text_parts.append(text)

            sentence_info = item.get("sentence_info") or item.get("sentences") or []
            for sentence in sentence_info:
                if not isinstance(sentence, dict):
                    continue
                sentence_text = str(sentence.get("text", "")).strip()
                start = self._funasr_time_to_seconds(sentence.get("start") or sentence.get("start_time"))
                end = self._funasr_time_to_seconds(sentence.get("end") or sentence.get("end_time"))
                if sentence_text and end > start:
                    detail_segments.append({"start": start, "end": end, "text": sentence_text})

            timestamps = item.get("timestamp") or item.get("timestamps") or []
            if timestamps and text and not detail_segments:
                words = re.split(r"([，。！？；、,.!?;])", text)
                chunks = []
                current = ""
                for part in words:
                    current += part
                    if part in "，。！？；、,.!?;" and current.strip():
                        chunks.append(current.strip())
                        current = ""
                if current.strip():
                    chunks.append(current.strip())
                if chunks and isinstance(timestamps, list):
                    total = len(chunks)
                    for idx, chunk in enumerate(chunks):
                        if not chunk:
                            continue
                        ts_index = min(int(idx * len(timestamps) / total), len(timestamps) - 1)
                        ts_next_index = min(int((idx + 1) * len(timestamps) / total), len(timestamps) - 1)
                        ts = timestamps[ts_index]
                        ts_next = timestamps[ts_next_index]
                        start = self._funasr_time_to_seconds(ts[0] if isinstance(ts, (list, tuple)) else ts)
                        end = self._funasr_time_to_seconds(ts_next[1] if isinstance(ts_next, (list, tuple)) and len(ts_next) > 1 else ts_next)
                        if end <= start:
                            end = start + max(1.0, len(chunk) / 6.0)
                        detail_segments.append({"start": start, "end": end, "text": chunk})
        full_text = "".join(text_parts).strip()
        if full_text and not detail_segments:
            detail_segments.append({"start": 0.0, "end": 0.0, "text": full_text})
        return {"text": full_text, "segments": detail_segments}

    @staticmethod
    def _funasr_time_to_seconds(value):
        try:
            number = float(value)
        except (TypeError, ValueError):
            return 0.0
        return number / 1000.0 if number >= 1000 else number

    def _post_model_load_status(self, status, model_name=None, error=None):
        app = QApplication.instance()
        if app:
            app.postEvent(self, CustomEvent({
                "status": status,
                "model_name": model_name or self.settings.get("selected_model", ""),
                "error": error,
            }, MODEL_LOAD_STATUS_EVENT_TYPE))

    def load_transcription_model(self, show_dialog=True):
        selected_model = self.settings.get("selected_model", "funasr-paraformer-zh")
        if not selected_model.startswith("funasr"):
            selected_model = "funasr-paraformer-zh"
            self.settings["selected_model"] = selected_model
        if self.whisper_model and self._transcription_model_name == selected_model:
            self._post_model_load_status("已就绪", selected_model)
            return True
        self._post_model_load_status("加载中", selected_model)
        loaded = self.load_funasr_model(show_dialog=show_dialog)
        self._post_model_load_status("已就绪" if loaded else "加载失败", selected_model, self._whisper_load_error)
        return loaded

    def update_model_status_label(self, status, model_name=None, error=None):
        self._transcription_model_status = status
        self._transcription_loading = status == "加载中"
        self._transcription_loading_name = model_name if self._transcription_loading else None
        if not hasattr(self, "model_status_label"):
            return
        color = {
            "未加载": "#7a7f87",
            "加载中": "#d19a66",
            "已就绪": "#2f9e44",
            "加载失败": "#d9534f",
        }.get(status, "#7a7f87")
        text = f"模型: {status}"
        if model_name:
            text += f" ({model_name})"
        if error and status == "加载失败":
            self.model_status_label.setToolTip(str(error))
        else:
            self.model_status_label.setToolTip("")
        self.model_status_label.setText(text)
        self.model_status_label.setStyleSheet(f"QLabel {{ color: {color}; padding: 2px 8px; }}")

    def load_funasr_model(self, show_dialog=True):
        with self._whisper_loading_lock:
            if self.whisper_model and self._transcription_model_name == self.settings.get("selected_model"):
                return True
        print("--- 开始加载 FunASR 语音模型: paraformer-zh + fsmn-vad + ct-punc ---")

        import traceback
        try:
            logging.getLogger("jieba").setLevel(logging.WARNING)
            logging.getLogger("funasr").setLevel(logging.WARNING)
            logging.getLogger("modelscope").setLevel(logging.WARNING)
            source_path = funasr_source_path()
            if os.path.isdir(source_path) and source_path not in sys.path:
                sys.path.insert(0, source_path)

            cache_dir = os.path.join(app_base_path(), "FunASR_models")
            os.makedirs(cache_dir, exist_ok=True)
            os.environ["MODELSCOPE_CACHE"] = cache_dir
            os.environ["HF_HOME"] = cache_dir
            asr_model = funasr_cached_model_path(
                "speech_seaco_paraformer_large_asr_nat-zh-cn-16k-common-vocab8404-pytorch",
                "paraformer-zh",
            )
            vad_model = funasr_cached_model_path(
                "speech_fsmn_vad_zh-cn-16k-common-pytorch",
                "fsmn-vad",
            )
            punc_model = funasr_cached_model_path(
                "punc_ct-transformer_cn-en-common-vocab471067-large",
                "ct-punc",
            )

            import torch
            with contextlib.redirect_stdout(io.StringIO()):
                from funasr import AutoModel

            device = "cuda:0" if torch.cuda.is_available() else "cpu"
            print(f"INFO: FunASR 使用设备: {device}")
            root_logger = logging.getLogger()
            previous_root_level = root_logger.level
            root_logger.setLevel(logging.ERROR)
            try:
                with contextlib.redirect_stdout(io.StringIO()):
                    self.whisper_model = AutoModel(
                        model=asr_model,
                        vad_model=vad_model,
                        punc_model=punc_model,
                        device=device,
                        disable_update=True,
                    )
            finally:
                root_logger.setLevel(previous_root_level)
            self._transcription_model_name = self.settings.get("selected_model", "funasr-paraformer-zh")
            self._whisper_load_error = None
            print("--- FunASR 模型加载成功。---")
            return True
        except ImportError as e:
            error_msg = f"加载 FunASR 失败，缺少依赖库: {e}"
            print(f"ERROR: {error_msg}")
            traceback.print_exc()
            if show_dialog:
                QMessageBox.critical(self, "库缺失", error_msg)
            self.whisper_model = None
            self._transcription_model_name = None
            self._whisper_load_error = error_msg
            return False
        except Exception as e:
            error_msg = f"加载 FunASR 模型时发生错误: {e}"
            print(f"FATAL: {error_msg}")
            traceback.print_exc()
            if show_dialog:
                QMessageBox.warning(self, "模型加载失败", "加载 FunASR 模型失败，请查看 app_output.log。")
            self.whisper_model = None
            self._transcription_model_name = None
            self._whisper_load_error = error_msg
            return False
        
    def handle_save_project(self):
        if self.project_manager.current_project_file:
            success, _ = self.project_manager.save_project()
            if success:
                self.add_recent_project(self.project_manager.current_project_file)
            return success
        else:
            file_path, _ = QFileDialog.getSaveFileName(self, "保存审阅项目", "", "Review Project Files (*.rev)")
            if file_path:
                success, _ = self.project_manager.save_project(file_path)
                if success:
                    self.add_recent_project(file_path)
                return success
            else:
                return False

    def handle_open_project(self):
        file_paths, _ = QFileDialog.getOpenFileNames(self, "打开审阅项目", "", "Review Project/Package (*.rev *.revpack)")
        if file_paths:
            self.project_manager.load_projects(file_paths)
            for path in file_paths:
                self.add_recent_project(path)

    def handle_append_revpack(self):
        file_paths, _ = QFileDialog.getOpenFileNames(self, "追加导入 revpack", "", "Review Package (*.revpack)")
        if file_paths:
            self.project_manager.append_revpack_collection(file_paths)

    def handle_pack_project(self):
        if self.is_packing:
            self.statusBar().showMessage("已有一个打包任务正在进行中...", 3000)
            return
        if not self.project_manager.review_entries:
            QMessageBox.warning(self, "提示", "项目为空，无法打包。")
            return
        if not self.project_manager.current_project_file:
            QMessageBox.warning(self, "提示", "请先保存项目，然后再打包。")
            return
        project_file_path = self.project_manager.current_project_file
        base_path = os.path.splitext(project_file_path)[0]
        save_path = base_path + ".revpack"
        reply = QMessageBox.question(self, "确认打包", f"项目将打包到:\n{save_path}\n\n是否继续？", QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes)
        if reply == QMessageBox.Yes:
            self.is_packing = True
            self.pack_action.setEnabled(False)
            self.statusBar().showMessage("正在打包项目，请稍候...", 0)
            threading.Thread(target=self.pack_project_worker, args=(save_path,), daemon=True).start()

    def pack_project_worker(self, save_path):
        success, message = self.project_manager.do_pack_project(save_path)
        QApplication.instance().postEvent(self, CustomEvent({"success": success, "message": message}, PROJECT_STATUS_EVENT_TYPE))

    def copy_file_to_clipboard(self, file_path):
        if not file_path or not os.path.exists(file_path):
            return False
        mime_data = QMimeData()
        mime_data.setUrls([QUrl.fromLocalFile(os.path.abspath(file_path))])
        mime_data.setText(os.path.abspath(file_path))
        QApplication.clipboard().setMimeData(mime_data)
        return True

    def open_web_viewer(self):
        self.start_cgtw_bridge_server()
        viewer_path = resource_path(os.path.join("web_viewer", "index.html"))
        if not os.path.exists(viewer_path):
            QMessageBox.warning(self, "网页预览器缺失", f"无法找到网页预览器:\n{viewer_path}")
            return
        self.open_file(viewer_path)

    def start_cgtw_bridge_server(self):
        bridge = getattr(self, "cgtw_bridge_server", None)
        if bridge and bridge.thread and bridge.thread.is_alive():
            return True
        self.cgtw_bridge_server = CgtwBridgeServer(
            lambda: self.settings,
            lambda: self.project_manager.current_temp_dir or "",
        )
        if self.cgtw_bridge_server.start():
            print("CGTeamWork bridge server started at http://127.0.0.1:8787")
            return True
        print("WARNING: CGTeamWork bridge server failed to start on http://127.0.0.1:8787")
        return False

    def open_project_folder(self):
        project_file = self.project_manager.current_project_file
        temp_dir = self.project_manager.current_temp_dir
        folder = ""
        if project_file:
            folder = os.path.dirname(project_file)
        elif temp_dir:
            folder = temp_dir
        if not folder or not os.path.isdir(folder):
            QMessageBox.information(self, "提示", "当前还没有可打开的工程文件夹，请先保存或加载工程。")
            return
        self.open_file(folder)

    def handle_add_reference_file(self, row):
        if not self.project_manager.current_temp_dir:
            QMessageBox.warning(self, "提示", "请先加载或保存项目，再添加参考文件。")
            return
        file_paths, _ = QFileDialog.getOpenFileNames(self, "选择参考文件", "", "All Files (*.*)")
        if not file_paths:
            return
        if not (0 <= row < self.project_manager.get_entry_count()):
            return
        entry = self.project_manager.review_entries[row]
        shot_number = entry.get("shot_number", "UNASSIGNED")
        sane_shot_name = re.sub(r'[\\/:*?"<>|]', '_', shot_number.strip()) if shot_number else "UNASSIGNED"
        reference_shot_dir = os.path.join(self.project_manager.current_temp_dir, "reference", sane_shot_name)
        os.makedirs(reference_shot_dir, exist_ok=True)
        added_rel_paths = []
        for src_path in file_paths:
            if not os.path.exists(src_path):
                print(f"警告: 参考文件 {src_path} 不存在，跳过。")
                continue
            filename = os.path.basename(src_path)
            dest_abs_path = os.path.join(reference_shot_dir, filename)
            if os.path.exists(dest_abs_path):
                reply = QMessageBox.question(self, "文件已存在", f"文件 {filename} 已存在，是否覆盖？", QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
                if reply == QMessageBox.No:
                    continue
            shutil.copy(src_path, dest_abs_path)
            rel_path = os.path.relpath(dest_abs_path, self.project_manager.current_temp_dir).replace(os.sep, '/')
            added_rel_paths.append(rel_path)
        if added_rel_paths:
            self.project_manager.add_reference_file(row, added_rel_paths)
            self.update_reference_cell(row)

    def handle_export(self):
        default_path = os.path.join(os.getcwd(), f"{self.settings.get('project_name', 'review_export')}.xlsx")
        file_path, _ = QFileDialog.getSaveFileName(self, "导出为 Excel", default_path, "Excel Files (*.xlsx)")
        if file_path:
            self.export_action.setEnabled(False)
            self.statusBar().showMessage("正在导出为 Excel...", 0)
            threading.Thread(target=self.export_worker, args=(file_path,), daemon=True).start()

    def export_worker(self, file_path):
        success, message = export_to_excel(self.project_manager.review_entries, self.settings, file_path)
        QApplication.instance().postEvent(self, CustomEvent({"success": success, "message": message}, EXPORT_STATUS_EVENT_TYPE))

    def handle_cgtw_sync(self):
        if self.is_cgtw_syncing:
            QMessageBox.information(self, "CGTeamWork", "已有 CGTeamWork 同步任务正在进行中。")
            return
        if not self.project_manager.review_entries:
            QMessageBox.warning(self, "CGTeamWork", "当前项目没有可同步的反馈。")
            return

        # ---------------- PRE-FLIGHT CHECK ----------------
        problematic_entries = []
        import urllib.request
        import json
        
        # Pipeline 到部门名称的映射
        pipeline_to_dept = {
            "Cache": "解算",
            "Animation": "动画",
            "Comp": "合成", # 主要映射
            "UE_FX": "UE特效",
            "Effect": "传统特效",
            "AAI": "组装",
            "TE": "地编"
        }
        
        for i, entry in enumerate(self.project_manager.review_entries):
            dep = str(entry.get("department", "")).strip()
            shot_num = str(entry.get("shot_number", ""))
            
            if dep == "未分类" or dep == "" or dep == "特效":
                # 尝试联系 Bridge Server 获取真实环节
                available_depts = []
                try:
                    config = get_cgtw_settings(self.settings)
                    db = config.get("db")
                    if db and shot_num:
                        url = f"http://127.0.0.1:8787/api/v1/get_task_pipelines?shot_number={shot_num}&db={db}"
                        req = urllib.request.Request(url)
                        with urllib.request.urlopen(req, timeout=2) as response:
                            res_data = json.loads(response.read().decode('utf-8'))
                            pipelines = res_data.get("pipelines", [])
                            
                            if dep == "特效":
                                fx_pipelines = [p for p in pipelines if p in ("UE_FX", "Effect")]
                                if len(fx_pipelines) == 1:
                                    new_dep = "UE特效" if fx_pipelines[0] == "UE_FX" else "传统特效"
                                    self.project_manager.update_entry(i, {"department": new_dep}, snapshot_action="自动解析特效部门")
                                    continue # 成功静默解决，跳过弹窗
                                elif len(fx_pipelines) > 1:
                                    available_depts = ["UE特效", "传统特效"]
                                    problematic_entries.append((i, shot_num, "该镜头同时包含【传统特效】和【UE特效】，请勾选", available_depts))
                                    continue
                            
                            # 获取该镜头在 CGTW 中存在的所有映射部门
                            for p in pipelines:
                                if p in pipeline_to_dept and pipeline_to_dept[p] not in available_depts:
                                    available_depts.append(pipeline_to_dept[p])
                                    
                except Exception:
                    pass
                
                # 如果是未分类或者上面因为没有找到特定特效而掉下来
                if dep == "未分类" or dep == "":
                    reason = "未指定部门，请勾选" if available_depts else "后台未查到该镜头的有效环节，请手动补充"
                    problematic_entries.append((i, shot_num, reason, available_depts))
                elif dep == "特效":
                    problematic_entries.append((i, shot_num, "未找到任何特效环节(UE_FX/Effect)，请核查", available_depts))
        
        if problematic_entries:
            from PySide6.QtWidgets import QDialog, QVBoxLayout, QLabel, QFormLayout, QDialogButtonBox, QScrollArea, QWidget, QLineEdit, QCheckBox, QHBoxLayout, QPushButton, QMenu
            from PySide6.QtGui import QAction
            
            class UncategorizedApproveDialog(QDialog):
                def __init__(self, items, all_departments, parent=None):
                    super().__init__(parent)
                    self.setWindowTitle("同步预检：部门确认")
                    self.resize(650, 450)
                    self.items = items
                    self.all_departments = all_departments
                    self.results = {}
                    
                    layout = QVBoxLayout(self)
                    layout.addWidget(QLabel("发现以下镜头的【部门】无法自动匹配。\n若成功从 CGTeamWork 读取，会直接显示复选框；若未查到，您可以手动输入或使用右侧按钮快速勾选："))
                    
                    form_layout = QFormLayout()
                    self.inputs = {}
                    for row, shot, reason, available_depts in self.items:
                        widget = QWidget()
                        h_layout = QHBoxLayout(widget)
                        h_layout.setContentsMargins(0, 0, 0, 0)
                        
                        checkboxes = []
                        if available_depts:
                            for dept in available_depts:
                                cb = QCheckBox(dept)
                                h_layout.addWidget(cb)
                                checkboxes.append(cb)
                        else:
                            # 降级为文本框 + 选择按钮
                            le = QLineEdit()
                            le.setPlaceholderText("手动输入，或点击右侧选择...")
                            h_layout.addWidget(le)
                            checkboxes.append(le)
                            
                            btn = QPushButton("≡ 选择部门")
                            menu = QMenu(btn)
                            
                            # 创建动作并绑定
                            def make_action(d, m, l):
                                act = QAction(d, m)
                                act.setCheckable(True)
                                act.triggered.connect(lambda: self.update_le_from_menu(l, m))
                                return act
                                
                            for d in self.all_departments:
                                action = make_action(d, menu, le)
                                menu.addAction(action)
                                
                            btn.setMenu(menu)
                            h_layout.addWidget(btn)
                            
                        self.inputs[row] = checkboxes
                        
                        label = QLabel(f"第 {row+1} 行 - {shot}\n({reason})")
                        label.setStyleSheet("color: #ff9999; font-size: 11px;")
                        form_layout.addRow(label, widget)
                        
                    scroll = QScrollArea()
                    scroll.setWidgetResizable(True)
                    w = QWidget()
                    w.setLayout(form_layout)
                    scroll.setWidget(w)
                    layout.addWidget(scroll)
                    
                    btn_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
                    btn_box.accepted.connect(self.accept)
                    btn_box.rejected.connect(self.reject)
                    layout.addWidget(btn_box)
                    
                def update_le_from_menu(self, le, menu):
                    selected = [act.text() for act in menu.actions() if act.isChecked()]
                    le.setText(", ".join(selected))
                    
                def accept(self):
                    for row, inputs in self.inputs.items():
                        selected = []
                        for inp in inputs:
                            if isinstance(inp, QCheckBox) and inp.isChecked():
                                selected.append(inp.text())
                            elif isinstance(inp, QLineEdit):
                                txt = inp.text().strip()
                                if txt: selected.append(txt)
                                
                        if selected:
                            self.results[row] = ", ".join(selected)
                    super().accept()
            dlg = UncategorizedApproveDialog(problematic_entries, self.settings.get("departments", []), self)
            if dlg.exec() == QDialog.Accepted:
                if dlg.results:
                    for row, text in dlg.results.items():
                        self.project_manager.update_entry(row, {"department": text}, snapshot_action="批量指定预检部门")
            else:
                return  # 取消了同步
        # --------------------------------------------------

        config = get_cgtw_settings(self.settings)
        payload = prepare_cgtw_payload(
            self.project_manager.review_entries,
            self.project_manager.current_temp_dir,
            self.settings,
        )
        if not payload["items"]:
            QMessageBox.warning(self, "CGTeamWork", "没有可同步的有效反馈。请确认镜头号和反馈意见已填写。")
            return

        dry_run = bool(config.get("dry_run", True))
        if not dry_run:
            errors = validate_cgtw_settings(config, require_runtime=True)
            if errors:
                QMessageBox.warning(self, "CGTeamWork 配置不完整", "\n".join(errors))
                return
        else:
            errors = validate_cgtw_settings(config, require_runtime=False)
            if errors:
                self.statusBar().showMessage("CGTeamWork 当前为模拟同步，配置未完整时只做本地预检。", 6000)

        mode_text = "模拟同步" if dry_run else "真实同步"
        target_text = f"数据库: {config.get('db') or '未配置'}\n模块: {config.get('module') or '未配置'}\n镜头字段: {config.get('shot_field') or '未配置'}"
        reply = QMessageBox.question(
            self,
            f"确认{mode_text}",
            f"{summarize_payload(payload)}\n\n{target_text}\n\n是否继续？",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        self.is_cgtw_syncing = True
        self.cgtw_sync_action.setEnabled(False)
        self.statusBar().showMessage(f"CGTeamWork {mode_text}进行中...", 0)
        
        self.cgtw_progress_dialog = QProgressDialog("正在同步至 CGTeamWork...", "取消", 0, len(self.project_manager.review_entries), self)
        self.cgtw_progress_dialog.setWindowTitle("同步进度")
        self.cgtw_progress_dialog.setWindowModality(Qt.WindowModal)
        self.cgtw_progress_dialog.setMinimumDuration(0)
        self.cgtw_progress_dialog.setValue(0)
        self.cgtw_progress_dialog.canceled.connect(self._cancel_cgtw_sync)
        self._cgtw_cancel_flag = False
        
        threading.Thread(target=self.cgtw_sync_worker, args=(dry_run,), daemon=True).start()

    def _cancel_cgtw_sync(self):
        self._cgtw_cancel_flag = True

    def cgtw_sync_worker(self, dry_run):
        try:
            entries = self.project_manager.review_entries
            total_items = len(entries)
            success_count = 0
            failed_count = 0
            skipped_count = 0
            all_results = []
            
            for i, entry in enumerate(entries):
                if getattr(self, '_cgtw_cancel_flag', False):
                    raise Exception("同步已被用户取消。")
                    
                QApplication.instance().postEvent(self, CustomEvent({"current": i, "total": total_items, "shot": entry.get("shot_number", "")}, CGTW_SYNC_PROGRESS_EVENT_TYPE))
                
                result = run_cgtw_sync(
                    [entry],
                    self.project_manager.current_temp_dir,
                    self.settings,
                    force_dry_run=dry_run
                )
                
                res_items = result.get("results", [])
                item_result = res_items[0] if res_items else {}
                
                if not result.get("success") or item_result.get("error"):
                    failed_count += 1
                elif item_result.get("skipped"):
                    skipped_count += 1
                else:
                    success_count += 1
                    
                all_results.extend(res_items)

            final_msg = f"CGTeamWork 同步完成：成功 {success_count} 条，失败 {failed_count} 条，跳过 {skipped_count} 条。"
            final_result = {
                "success": failed_count == 0,
                "message": final_msg,
                "results": all_results,
                "payload": {"skipped": []}
            }
        except Exception as e:
            final_result = {"success": False, "message": str(e)}
            
        QApplication.instance().postEvent(self, CustomEvent(final_result, CGTW_SYNC_STATUS_EVENT_TYPE))

    def handle_export_merged_video(self):
        if self.is_video_exporting:
            QMessageBox.information(self, "提示", "已有视频合并任务正在进行中。")
            return
        if not self.project_manager.review_entries:
            QMessageBox.warning(self, "提示", "当前项目没有可导出的视频。")
            return
        ffmpeg_path = check_ffmpeg_availability(self.settings)
        if not ffmpeg_path:
            QMessageBox.warning(self, "缺少 FFmpeg", "请先在设置中配置 FFmpeg 路径。")
            return
        default_path = os.path.join(os.getcwd(), f"{self.settings.get('project_name', 'merged_review')}_合并视频.mp4")
        file_path, _ = QFileDialog.getSaveFileName(self, "合并导出视频", default_path, "MP4 Video (*.mp4)")
        if not file_path:
            return
        if not file_path.lower().endswith(".mp4"):
            file_path += ".mp4"
        self.is_video_exporting = True
        self.export_video_action.setEnabled(False)
        self.statusBar().showMessage("正在按镜头号合并导出视频...", 0)
        threading.Thread(target=self.export_merged_video_worker, args=(file_path, ffmpeg_path), daemon=True).start()

    def export_merged_video_worker(self, file_path, ffmpeg_path):
        success, message = export_merged_video(
            self.project_manager.review_entries,
            self.project_manager.current_temp_dir,
            file_path,
            ffmpeg_path,
        )
        QApplication.instance().postEvent(self, CustomEvent({"success": success, "message": message}, VIDEO_EXPORT_STATUS_EVENT_TYPE))

    def toggle_mobile_connection(self):
        if self.mobile_connection_action.isChecked():
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                s.connect(("8.8.8.8", 80))
                local_ip = s.getsockname()[0]
                s.close()
                self.websocket_server = websocket_receiver.WebSocketReceiver(host='0.0.0.0', port=8765, on_message_callback=self.handle_websocket_message)
                self.websocket_server.start_server()
                self.mobile_connection_active = True
                self.statusBar().showMessage(f"手机连接已启用。请在手机上访问 ws://{local_ip}:8765")
                print(f"WebSocket server started on ws://{local_ip}:8765")
            except Exception as e:
                self.statusBar().showMessage(f"启动手机连接失败: {e}")
                self.mobile_connection_action.setChecked(False)
                self.mobile_connection_active = False
                if self.websocket_server:
                    self.websocket_server.stop_server()
                    self.websocket_server = None
        else:
            if self.websocket_server:
                self.websocket_server.stop_server()
                self.websocket_server = None
            self.mobile_connection_active = False
            self.statusBar().showMessage("手机连接已关闭。")
            print("WebSocket server stopped.")

    def handle_websocket_message(self, message):
        try:
            data = json.loads(message)
            message_type = data.get("type")
            if message_type == "start_recording":
                QApplication.instance().postEvent(self, CustomEvent({}, MOBILE_START_RECORDING_EVENT_TYPE))
                print("Received start_recording command from mobile.")
            elif message_type == "text_input":
                received_text = data.get("text")
                if received_text is not None:
                    self.mobile_text_override = received_text
                    if self.recording_manager.is_recording():
                        QApplication.instance().postEvent(self, CustomEvent({}, MOBILE_STOP_RECORDING_EVENT_TYPE))
                        print(f"Received text_input from mobile, stopping current recording: {received_text}")
                    else:
                        QApplication.instance().postEvent(self, CustomEvent({}, MOBILE_START_RECORDING_EVENT_TYPE))
                        QApplication.instance().postEvent(self, CustomEvent({}, MOBILE_STOP_RECORDING_EVENT_TYPE))
                        print(f"Received text_input from mobile, creating new entry: {received_text}")
        except json.JSONDecodeError:
            print(f"Received non-JSON message: {message}")
        except Exception as e:
            print(f"Error handling WebSocket message: {e}")

    def _format_cgtw_sync_details(self, result):
        lines = []
        payload = result.get("payload") or {}
        summary = payload.get("summary") or result.get("payload_summary") or {}
        if summary:
            lines.append(json.dumps(summary, ensure_ascii=False, indent=2))
        skipped = payload.get("skipped") or []
        if skipped:
            lines.append("跳过条目:")
            for item in skipped[:30]:
                lines.append(json.dumps(item, ensure_ascii=False))
            if len(skipped) > 30:
                lines.append(f"... 还有 {len(skipped) - 30} 条")
        results = result.get("results") or []
        if results:
            lines.append("同步结果:")
            for item in results[:50]:
                lines.append(json.dumps(item, ensure_ascii=False))
            if len(results) > 50:
                lines.append(f"... 还有 {len(results) - 50} 条")
        return "\n".join(lines)

    def event(self, event):
        event_type = event.type()
        if event_type == ADD_REVIEW_EVENT_TYPE:
            new_row_index = self.project_manager.get_entry_count()
            self.project_manager.add_review_entry(event.data)
            if self.settings.get("realtime_transcribe", True):
                self.manual_transcribe(new_row_index)
            return True
        elif event_type == MODEL_LOAD_STATUS_EVENT_TYPE:
            data = event.data
            self.update_model_status_label(data.get("status", "未加载"), data.get("model_name"), data.get("error"))
            return True
        elif event_type == AI_UPDATE_EVENT_TYPE:
            data = event.data
            if data.get("completed"):
                self.is_ai_processing = False
                self.ai_process_action.setEnabled(True)
                self.ai_rewrite_selected_action.setEnabled(True)
                self.statusBar().showMessage("AI 处理完成。", 5000)
            elif data.get("error"):
                error_msg = data["error"]
                if "proxy" in error_msg.lower() or "tcp" in error_msg.lower() or "http" in error_msg.lower():
                    QMessageBox.critical(self, "AI 处理错误", f"网络连接失败，请检查代理设置或网络防火墙。\n\n详细信息: {error_msg}")
                else:
                    QMessageBox.critical(self, "AI 处理错误", error_msg)
            elif "row" in data:
                row = data["row"]
                result = data["result"]
                if data.get("replace_full_review") and 0 <= row < self.project_manager.get_entry_count():
                    entry = self.project_manager.review_entries[row]
                    update_data = dict(result)
                    if not entry.get("original_full_review"):
                        update_data["original_full_review"] = entry.get("full_review", "")
                    rewritten_review = result.get("rewritten_review") or result.get("simplified_review")
                    update_data["full_review"] = rewritten_review
                    update_data.pop("rewritten_review", None)
                    self.project_manager.update_entry(row, update_data, snapshot_action="AI Update")
                    if self.project_manager.current_project_file:
                        self.project_manager.save_project(autosave=True)
                else:
                    clean_result = dict(result)
                    clean_result.pop("rewritten_review", None)
                    self.project_manager.update_entry(row, clean_result, snapshot_action="AI Update")
            return True
        elif event_type == TRANSCRIPTION_DONE_EVENT_TYPE:
            data = event.data
            row, text = data["row"], data["text"]
            if row < self.project_manager.get_entry_count():
                update_data = {"full_review": text}
                if data.get("segments") is not None:
                    update_data["transcript_segments"] = data.get("segments", [])
                self.project_manager.update_entry(row, update_data, snapshot_action="Transcription Update")
                if data.get("is_long_video"):
                    dialog = self.long_video_dialogs.get(row)
                    if dialog:
                        dialog.set_transcript(text, data.get("segments", []))
            if self.is_transcribing_batch and hasattr(self, 'pending_batch_rows'):
                if self.pending_batch_rows:
                    self.manual_transcribe(self.pending_batch_rows.pop(0))
                else:
                    self.is_transcribing_batch = False
                    self.transcribe_all_action.setEnabled(True)
                    delattr(self, 'pending_batch_rows')
                    self.statusBar().showMessage("所有条目转写完成，正在检查 AI 服务...", 5000)
                    QTimer.singleShot(0, self.process_all_reviews_with_ai_auto)
            else:
                self.statusBar().showMessage(f"第 {row + 1} 行转写完成。", 3000)
                if data.get("is_long_video"):
                    self.statusBar().showMessage("长视频完整转写完成，未自动启动 AI 分析。", 8000)
                else:
                    self.process_single_review_with_ai(row, silent=True)
            return True
        elif event_type == EXPORT_STATUS_EVENT_TYPE:
            self.export_action.setEnabled(True)
            if event.data["success"]:
                self.statusBar().showMessage(f"成功导出到 {event.data['message']}", 5000)
                QMessageBox.information(self, "成功", f"已成功导出到:\n{event.data['message']}")
            else:
                self.statusBar().showMessage(f"导出失败: {event.data['message']}", 5000)
                QMessageBox.critical(self, "导出失败", f"导出 Excel 时发生错误:\n{event.data['message']}")
            return True
        elif event_type == VIDEO_EXPORT_STATUS_EVENT_TYPE:
            self.is_video_exporting = False
            self.export_video_action.setEnabled(True)
            if event.data["success"]:
                self.statusBar().showMessage(f"视频合并导出完成: {event.data['message']}", 8000)
                QMessageBox.information(self, "视频导出完成", event.data["message"])
            else:
                self.statusBar().showMessage(f"视频合并导出失败: {event.data['message']}", 8000)
                QMessageBox.critical(self, "视频导出失败", event.data["message"])
            return True
        elif event_type == CGTW_SYNC_PROGRESS_EVENT_TYPE:
            if hasattr(self, 'cgtw_progress_dialog'):
                self.cgtw_progress_dialog.setValue(event.data.get("current", 0))
                self.cgtw_progress_dialog.setLabelText(f"正在同步: {event.data.get('shot', '')}")
            return True
        elif event_type == CGTW_SYNC_STATUS_EVENT_TYPE:
            if hasattr(self, 'cgtw_progress_dialog'):
                self.cgtw_progress_dialog.close()
            self.is_cgtw_syncing = False
            self.update_toolbar_state()
            message = event.data.get("message", "")
            details = self._format_cgtw_sync_details(event.data)
            if event.data.get("success"):
                self.statusBar().showMessage(message, 8000)
                box = QMessageBox(QMessageBox.Information, "CGTeamWork 同步完成", message, QMessageBox.Ok, self)
            else:
                self.statusBar().showMessage(f"CGTeamWork 同步失败: {message}", 8000)
                box = QMessageBox(QMessageBox.Critical, "CGTeamWork 同步失败", message, QMessageBox.Ok, self)
            if details:
                box.setDetailedText(details)
            box.exec()
            return True
        elif event_type == PROJECT_STATUS_EVENT_TYPE:
            self.is_packing = False
            self.pack_action.setEnabled(True)
            self.statusBar().clearMessage()
            if event.data["success"]:
                copied = self.copy_file_to_clipboard(event.data["message"])
                copy_note = "\n\n已复制打包文件到系统剪贴板，可在目标文件夹直接粘贴。" if copied else ""
                QMessageBox.information(self, "成功", f"项目已成功打包到:\n{event.data['message']}{copy_note}")
            else:
                QMessageBox.critical(self, "打包失败", event.data['message'])
            return True
        elif event_type == RETRY_OCR_DONE_EVENT_TYPE:
            data = event.data
            row, text, column = data["row"], data["text"], data.get("column")
            if not text or text in ["UNASSIGNED", "未识别", "OCR失败"]:
                field_name = "时间戳" if column == COL_TIMESTAMP else "镜头号"
                self.statusBar().showMessage(f"{field_name}自动识别失败，请框选区域重新识别。", 5000)
                QTimer.singleShot(0, lambda r=row, c=column: self.retry_ocr(r, c))
                return True
            if column == COL_TIMESTAMP:
                self.project_manager.update_entry(row, {"timestamp": text}, snapshot_action="OCR Update")
            elif column == COL_SHOT:
                self.project_manager.update_shot_number_and_move_files(row, text)
            return True
        elif event_type == LONG_VIDEO_IMPORT_EVENT_TYPE:
            self.import_long_video_action.setEnabled(True)
            if event.data.get("success"):
                new_row_index = self.project_manager.get_entry_count()
                review_data = event.data["review_data"]
                self.project_manager.add_review_entry(review_data)
                video_path = self._resolve_temp_path(review_data.get("source_video") or (review_data.get("media_files") or [None])[0])
                dialog = LongVideoTranscriptionDialog(video_path, self)
                dialog.set_status("正在完整转写长视频音频...", busy=True)
                dialog.summary_requested.connect(lambda r=new_row_index: self.generate_long_video_summary(r))
                dialog.issues_requested.connect(lambda r=new_row_index: self.organize_long_video_to_table(r))
                dialog.issues_commit_requested.connect(lambda issues, r=new_row_index: self.commit_long_video_issues_to_table(r, issues))
                dialog.transcript_save_requested.connect(lambda text, r=new_row_index: self.save_long_video_transcript_edit(r, text))
                dialog.destroyed.connect(lambda: self.long_video_dialogs.pop(new_row_index, None))
                dialog.show()
                self.long_video_dialogs[new_row_index] = dialog
                self.statusBar().showMessage("长视频已导入，开始转写音频...", 5000)
                if review_data.get("audio_path"):
                    self.manual_transcribe(new_row_index)
                else:
                    QMessageBox.warning(self, "导入完成但没有音频", "长视频已加入表格，但未能提取可转写的音频。")
            else:
                message = event.data.get("message", "未知错误")
                self.statusBar().showMessage(f"长视频导入失败: {message}", 8000)
                QMessageBox.critical(self, "长视频导入失败", message)
            return True
        elif event_type == LONG_VIDEO_SEGMENTS_EVENT_TYPE:
            if event.data.get("success"):
                entries = event.data.get("entries", [])
                for entry in entries:
                    self.project_manager.add_review_entry(entry)
                if self.project_manager.current_project_file:
                    self.project_manager.save_project(autosave=True)
                dialog = self.long_video_dialogs.get(event.data.get("parent_row"))
                if dialog:
                    dialog.set_status(f"已整理 {len(entries)} 条问题到表格", busy=False)
                self.statusBar().showMessage(f"长视频讨论分析完成，已生成 {len(entries)} 条问题记录。", 8000)
                if not entries:
                    QMessageBox.information(self, "整理完成", "没有写入新的问题行，请在问题清单中手动标记讨论区间。")
            else:
                message = event.data.get("message", "未知错误")
                self.statusBar().showMessage(f"长视频讨论分析失败: {message}", 8000)
                QMessageBox.warning(self, "长视频讨论分析失败", message)
            return True
        elif event_type == LONG_VIDEO_ISSUES_EVENT_TYPE:
            row = event.data.get("parent_row")
            dialog = self.long_video_dialogs.get(row)
            if event.data.get("success"):
                issues = event.data.get("issues", [])
                if dialog:
                    dialog.set_issues(issues)
                if 0 <= row < len(self.project_manager.review_entries):
                    self.project_manager.review_entries[row]["long_video_issues"] = issues
                    if self.project_manager.current_project_file:
                        self.project_manager.save_project(autosave=True)
                if not issues:
                    if dialog:
                        dialog.set_status("未自动识别到问题，可在时间轴手动标记讨论区间。", busy=False)
                    self.statusBar().showMessage("未自动识别到问题，可在时间轴手动标记讨论区间。", 8000)
                else:
                    self.statusBar().showMessage(f"已整理 {len(issues)} 条问题，请确认后入表。", 8000)
            else:
                message = event.data.get("message", "未知错误")
                if dialog:
                    dialog.set_status("问题整理失败，可手动标记讨论区间。", busy=False)
                QMessageBox.warning(self, "问题整理失败", message)
            return True
        elif event_type == LONG_VIDEO_SUMMARY_EVENT_TYPE:
            row = event.data.get("row")
            dialog = self.long_video_dialogs.get(row)
            if event.data.get("error"):
                message = event.data.get("error")
                if dialog:
                    dialog.set_status("纲要生成失败", busy=False)
                QMessageBox.warning(self, "纲要生成失败", message)
            else:
                summary = event.data.get("summary", "")
                if 0 <= row < len(self.project_manager.review_entries):
                    self.project_manager.review_entries[row]["long_video_summary"] = summary
                    if self.project_manager.current_project_file:
                        self.project_manager.save_project(autosave=True)
                if dialog:
                    dialog.set_summary(summary)
                self.statusBar().showMessage("长视频纲要已生成。", 5000)
            return True
        elif event_type == MOBILE_START_RECORDING_EVENT_TYPE:
            if not self.recording_manager.is_recording():
                self.statusBar().showMessage("收到手机开始指令，启动审阅...", 2000)
                self.toggle_review_capture()
            else:
                self.statusBar().showMessage("已在录制中，忽略手机开始指令。", 2000)
            return True
        elif event_type == MOBILE_STOP_RECORDING_EVENT_TYPE:
            if self.recording_manager.is_recording():
                self.statusBar().showMessage("收到手机文本，停止审阅...", 2000)
                self.toggle_review_capture()
            else:
                self.statusBar().showMessage("未在录制中，忽略手机停止指令。", 2000)
            return True
        return super().event(event)

    @staticmethod
    def open_file(path):
        import subprocess
        if not path or not os.path.exists(path):
            QMessageBox.warning(None, "错误", f"文件或目录不存在:\n{path}")
            return
        if sys.platform == "win32":
            os.startfile(path)
        elif sys.platform == "darwin":
            subprocess.call(["open", path])
        else:
            subprocess.call(["xdg-open", path])

if __name__ == "__main__":
    if hasattr(sys, '_MEIPASS'):
        log_dir = os.path.dirname(sys.executable)
        log_file_path = os.path.join(log_dir, "app_output.log")
        
        # --- START: Force local caching for bundled app ---
        print("INFO: Application is bundled. Forcing local cache for models.")
        local_cache_dir = os.path.join(log_dir, "model_cache")
        os.makedirs(local_cache_dir, exist_ok=True)
        
        print(f"INFO: Setting cache directory to: {local_cache_dir}")
        os.environ['HF_HOME'] = local_cache_dir
        os.environ['TORCH_HOME'] = local_cache_dir
        os.environ['CTRANSLATE2_CACHE_DIR'] = local_cache_dir
        # --- END: Force local caching ---

        sys.stdout = open(log_file_path, 'a', encoding='utf-8')
        sys.stderr = open(log_file_path, 'a', encoding='utf-8')
        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Application started. Output redirected to {log_file_path}")
    
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
