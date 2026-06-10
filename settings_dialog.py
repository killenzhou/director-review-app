# -*- coding: utf-8 -*-
import numpy as np

try:
    import sounddevice as sd
    import mss
except ImportError:
    print("警告: sounddevice 或 mss 库未安装，设备选择功能将受限。")
    sd = None
    mss = None

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QFormLayout, QComboBox, QLineEdit,
    QDialogButtonBox, QCheckBox, QGroupBox, QSpinBox,
    QPushButton, QHBoxLayout, QFileDialog, QProgressBar,
    QScrollArea, QWidget
)
from PySide6.QtCore import Signal 
from cgtw_sync import DEFAULT_CGTW_BASE_PATH, DEFAULT_CGTW_PYTHON_PATH, get_cgtw_settings

class SettingsDialog(QDialog):
    volume_updated_signal = Signal(int)

    def __init__(self, settings, parent=None):
        super().__init__(parent)
        self.setWindowTitle("设置")
        self.setMinimumWidth(500)
        
        self.settings = settings
        self.audio_stream = None
        self.is_monitoring_audio = False
        
        main_layout = QVBoxLayout(self)
        
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_widget = QWidget()
        layout = QVBoxLayout(scroll_widget)
        
        project_group = QGroupBox("项目信息")
        project_layout = QFormLayout()
        self.project_name_input = QLineEdit()
        self.producer_input = QLineEdit()
        self.reviewer_input = QLineEdit()
        project_layout.addRow("项目名称:", self.project_name_input)
        project_layout.addRow("制作人:", self.producer_input)
        project_layout.addRow("审阅人:", self.reviewer_input)
        project_group.setLayout(project_layout)
        
        ai_group = QGroupBox("AI 服务设置")
        ai_layout = QFormLayout()
        self.provider_combo = QComboBox(); self.provider_combo.addItems(["local-ai", "lm-studio", "openai-compatible", "deepseek", "doubao", "openai", "google-gemini"])
        self.api_key_input = QLineEdit(); self.api_key_input.setEchoMode(QLineEdit.Password)
        self.base_url_input = QLineEdit()
        self.model_name_input = QLineEdit()
        self.api_key_input.setPlaceholderText("本地 AI 可留空")
        self.base_url_input.setPlaceholderText("例如: http://127.0.0.1:8080/v1")
        self.model_name_input.setPlaceholderText("LM Studio 中已加载的模型名称")
        ai_layout.addRow("服务商:", self.provider_combo)
        ai_layout.addRow("API Key:", self.api_key_input)
        ai_layout.addRow("API Base URL:", self.base_url_input)
        ai_layout.addRow("模型名称:", self.model_name_input)
        ai_group.setLayout(ai_layout)

        workflow_group = QGroupBox("工作流与设备设置")
        workflow_layout = QFormLayout()
        self.theme_combo = QComboBox()
        self.theme_combo.addItem("浅色", "light")
        self.theme_combo.addItem("深色", "dark")
        self.realtime_transcribe_check = QCheckBox("录音后立即进行语音转文字")
        self.screen_record_fps_spinbox = QSpinBox()
        self.screen_record_fps_spinbox.setRange(1, 60)
        self.screen_record_fps_spinbox.setSuffix(" FPS")
        
        self.monitor_combo = QComboBox()
        self.audio_device_combo = QComboBox()
        self.populate_monitors()
        self.populate_audio_devices()

        self.volume_preview_bar = QProgressBar()
        self.volume_preview_bar.setRange(0, 100)
        self.volume_preview_bar.setValue(0)
        self.volume_preview_bar.setTextVisible(False)
        self.volume_preview_bar.setToolTip("选择设备后，请说话以测试音量")
        
        audio_device_layout = QHBoxLayout()
        audio_device_layout.addWidget(self.audio_device_combo)
        audio_device_layout.addWidget(self.volume_preview_bar)

        self.ffmpeg_path_input = QLineEdit()
        self.ffmpeg_path_input.setPlaceholderText("留空则自动检测系统路径")
        ffmpeg_browse_btn = QPushButton("...")
        ffmpeg_browse_btn.setFixedSize(30, 22)
        ffmpeg_browse_btn.clicked.connect(self.browse_ffmpeg_path)
        
        ffmpeg_path_layout = QHBoxLayout()
        ffmpeg_path_layout.addWidget(self.ffmpeg_path_input)
        ffmpeg_path_layout.addWidget(ffmpeg_browse_btn)

        self.departments_input = QLineEdit()
        
        workflow_layout.addRow("界面主题:", self.theme_combo)
        workflow_layout.addRow(self.realtime_transcribe_check)
        workflow_layout.addRow("录屏帧率:", self.screen_record_fps_spinbox)
        workflow_layout.addRow("录制屏幕:", self.monitor_combo)
        workflow_layout.addRow("录音设备:", audio_device_layout)
        workflow_layout.addRow("FFmpeg 路径 (可选):", ffmpeg_path_layout)
        workflow_layout.addRow("制作部门 (逗号分隔):", self.departments_input)
        workflow_group.setLayout(workflow_layout)

        cgtw_group = QGroupBox("CGTeamWork 同步")
        cgtw_layout = QFormLayout()
        self.cgtw_enabled_check = QCheckBox("启用 CGTeamWork 同步入口")
        self.cgtw_dry_run_check = QCheckBox("模拟同步（只预检，不写入 CGTeamWork）")
        self.cgtw_base_path_input = QLineEdit()
        self.cgtw_base_path_input.setPlaceholderText(DEFAULT_CGTW_BASE_PATH)
        cgtw_base_browse_btn = QPushButton("...")
        cgtw_base_browse_btn.setFixedSize(30, 22)
        cgtw_base_browse_btn.clicked.connect(self.browse_cgtw_base_path)
        cgtw_base_layout = QHBoxLayout()
        cgtw_base_layout.addWidget(self.cgtw_base_path_input)
        cgtw_base_layout.addWidget(cgtw_base_browse_btn)

        self.cgtw_python_path_input = QLineEdit()
        self.cgtw_python_path_input.setPlaceholderText(DEFAULT_CGTW_PYTHON_PATH)
        cgtw_python_browse_btn = QPushButton("...")
        cgtw_python_browse_btn.setFixedSize(30, 22)
        cgtw_python_browse_btn.clicked.connect(self.browse_cgtw_python_path)
        cgtw_python_layout = QHBoxLayout()
        cgtw_python_layout.addWidget(self.cgtw_python_path_input)
        cgtw_python_layout.addWidget(cgtw_python_browse_btn)

        self.cgtw_db_input = QLineEdit()
        self.cgtw_module_input = QLineEdit()
        self.cgtw_shot_field_input = QLineEdit()
        self.cgtw_task_name_input = QLineEdit()
        self.cgtw_filebox_sign_input = QLineEdit()
        self.cgtw_filebox_id_input = QLineEdit()
        self.cgtw_flow_field_input = QLineEdit()
        self.cgtw_flow_field_input.setPlaceholderText("task.supervise_status")
        self.cgtw_flow_status_input = QLineEdit()
        self.cgtw_flow_status_input.setPlaceholderText("内部返修")
        self.cgtw_sync_note_check = QCheckBox("写入 Note")
        self.cgtw_submit_review_check = QCheckBox("提交到审核文件框")
        self.cgtw_upload_filebox_check = QCheckBox("上传到指定文件框 ID")
        self.cgtw_update_status_check = QCheckBox("同步后更新任务状态")
        self.cgtw_target_status_input = QLineEdit()
        self.cgtw_target_status_input.setPlaceholderText("例如 Retake / Wait / Approve")

        cgtw_layout.addRow(self.cgtw_enabled_check)
        cgtw_layout.addRow(self.cgtw_dry_run_check)
        cgtw_layout.addRow("CGTW API 路径:", cgtw_base_layout)
        cgtw_layout.addRow("Python 路径:", cgtw_python_layout)
        cgtw_layout.addRow("数据库 db:", self.cgtw_db_input)
        cgtw_layout.addRow("模块 module:", self.cgtw_module_input)
        cgtw_layout.addRow("镜头字段:", self.cgtw_shot_field_input)
        cgtw_layout.addRow("任务名过滤:", self.cgtw_task_name_input)
        cgtw_layout.addRow("审核文件框标识:", self.cgtw_filebox_sign_input)
        cgtw_layout.addRow("文件框 ID:", self.cgtw_filebox_id_input)
        cgtw_layout.addRow("流程反馈字段:", self.cgtw_flow_field_input)
        cgtw_layout.addRow("流程反馈状态:", self.cgtw_flow_status_input)
        cgtw_layout.addRow(self.cgtw_sync_note_check)
        cgtw_layout.addRow(self.cgtw_submit_review_check)
        cgtw_layout.addRow(self.cgtw_upload_filebox_check)
        cgtw_layout.addRow(self.cgtw_update_status_check)
        cgtw_layout.addRow("目标状态:", self.cgtw_target_status_input)
        cgtw_group.setLayout(cgtw_layout)

        self.button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.button_box.accepted.connect(self.accept); self.button_box.rejected.connect(self.reject)
        
        layout.addWidget(project_group); layout.addWidget(ai_group)
        layout.addWidget(workflow_group); layout.addWidget(cgtw_group)
        
        scroll_area.setWidget(scroll_widget)
        main_layout.addWidget(scroll_area)
        main_layout.addWidget(self.button_box)
        
        self.load_settings_to_ui()
        self.provider_combo.currentTextChanged.connect(self.update_defaults)
        self.update_defaults(self.provider_combo.currentText())

        self.volume_updated_signal.connect(self._update_volume_preview_bar)
        self.audio_device_combo.currentIndexChanged.connect(self.start_audio_monitor)
        self.start_audio_monitor()

    def browse_ffmpeg_path(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "选择 ffmpeg.exe", "", "Executable Files (ffmpeg.exe)")
        if file_path: self.ffmpeg_path_input.setText(file_path)

    def browse_cgtw_base_path(self):
        directory = QFileDialog.getExistingDirectory(self, "选择 CGTeamWork API 路径", self.cgtw_base_path_input.text() or DEFAULT_CGTW_BASE_PATH)
        if directory:
            self.cgtw_base_path_input.setText(directory)

    def browse_cgtw_python_path(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "选择 Python 可执行文件", "", "Executable Files (python.exe)")
        if file_path:
            self.cgtw_python_path_input.setText(file_path)
        
    def populate_monitors(self):
        if not mss: self.monitor_combo.addItem("mss 库未安装"); self.monitor_combo.setEnabled(False); return
        try:
            with mss.mss() as sct:
                monitors = sct.monitors; self.monitor_combo.addItem(f"全屏 ({monitors[0]['width']}x{monitors[0]['height']})", 0)
                for i, mon in enumerate(monitors[1:], 1): self.monitor_combo.addItem(f"显示器 {i} ({mon['width']}x{mon['height']})", i)
        except Exception as e: print(f"无法获取显示器列表: {e}"); self.monitor_combo.addItem("获取显示器失败"); self.monitor_combo.setEnabled(False)

    def populate_audio_devices(self):
        if not sd: self.audio_device_combo.addItem("sounddevice库未安装"); self.audio_device_combo.setEnabled(False); return
        try:
            devices = sd.query_devices(); self.audio_device_combo.addItem("系统默认设备", -1)
            input_devices_found = False
            for i, device in enumerate(devices):
                if device['max_input_channels'] > 0: self.audio_device_combo.addItem(f"{i}: {device['name']}", i); input_devices_found = True
            if not input_devices_found: self.audio_device_combo.addItem("未检测到麦克风设备"); self.audio_device_combo.setEnabled(False)
        except Exception as e: print(f"无法获取音频设备: {e}"); self.audio_device_combo.addItem("获取设备失败"); self.audio_device_combo.setEnabled(False)
            
    def update_defaults(self, provider):
        defaults = {
            "openai": ("https://api.openai.com/v1", "gpt-4o-mini", True),
            "deepseek": ("https://api.deepseek.com", "deepseek-v4-flash", True),
            "doubao": ("https://ark.cn-beijing.volces.com/api/v3", "doubao-seed-2-0-pro-260215", True),
            "openai-compatible": (self.settings.get("base_url", ""), self.settings.get("model_name", ""), True),
            "lm-studio": ("http://127.0.0.1:1234/v1", "local-model", True),
            "local-ai": ("http://127.0.0.1:8080/v1", "Qwen3VL-8B-Instruct-Q4_K_M.gguf", True),
            "google-gemini": ("N/A", "gemini-2.5-flash", False),
        }
        base_url, model_name, base_enabled = defaults.get(provider, defaults["openai-compatible"])
        if provider == self.settings.get("ai_provider"):
            base_url = self.settings.get("base_url", base_url)
            model_name = self.settings.get("model_name", model_name)
        self.base_url_input.setText(base_url)
        self.model_name_input.setText(model_name)
        self.base_url_input.setEnabled(base_enabled)
        self.api_key_input.setEnabled(provider not in ["lm-studio", "local-ai"])
            
    def load_settings_to_ui(self):
        self.project_name_input.setText(self.settings.get("project_name", "未命名项目")); self.producer_input.setText(self.settings.get("producer", "")); self.reviewer_input.setText(self.settings.get("reviewer", ""))
        self.provider_combo.setCurrentText(self.settings.get("ai_provider", "local-ai")); self.api_key_input.setText(self.settings.get("api_key", "local")); self.base_url_input.setText(self.settings.get("base_url", "http://127.0.0.1:8080/v1")); self.model_name_input.setText(self.settings.get("model_name", "Qwen3VL-8B-Instruct-Q4_K_M.gguf"))
        theme = self.settings.get("theme", "light")
        for i in range(self.theme_combo.count()):
            if self.theme_combo.itemData(i) == theme:
                self.theme_combo.setCurrentIndex(i)
                break
        self.realtime_transcribe_check.setChecked(self.settings.get("realtime_transcribe", True)); self.screen_record_fps_spinbox.setValue(self.settings.get("screen_record_fps", 10)); self.ffmpeg_path_input.setText(self.settings.get("ffmpeg_path", ""))
        
        saved_monitor_idx = self.settings.get("screen_record_monitor", 0)
        for i in range(self.monitor_combo.count()):
            if self.monitor_combo.itemData(i) == saved_monitor_idx: self.monitor_combo.setCurrentIndex(i); break

        saved_device_idx = self.settings.get("audio_device_index", -1)
        if saved_device_idx is None: saved_device_idx = -1 # Handle None case
        for i in range(self.audio_device_combo.count()):
            if self.audio_device_combo.itemData(i) == saved_device_idx: self.audio_device_combo.setCurrentIndex(i); break
        
        departments = self.settings.get("departments", ["动画", "灯光", "模型", "特效", "合成", "剪辑", "解算", "地编", "组装", "传统特效", "UE特效", "AI", "AE"]); self.departments_input.setText(", ".join(departments))
        cgtw = get_cgtw_settings(self.settings)
        self.cgtw_enabled_check.setChecked(cgtw.get("enabled", False))
        self.cgtw_dry_run_check.setChecked(cgtw.get("dry_run", True))
        self.cgtw_base_path_input.setText(cgtw.get("base_path", DEFAULT_CGTW_BASE_PATH))
        self.cgtw_python_path_input.setText(cgtw.get("python_path", ""))
        self.cgtw_db_input.setText(cgtw.get("db", ""))
        self.cgtw_module_input.setText(cgtw.get("module", "shot"))
        self.cgtw_shot_field_input.setText(cgtw.get("shot_field", "etask.url"))
        self.cgtw_task_name_input.setText(cgtw.get("task_name", ""))
        self.cgtw_filebox_sign_input.setText(cgtw.get("filebox_sign", "review"))
        self.cgtw_filebox_id_input.setText(cgtw.get("filebox_id", ""))
        self.cgtw_flow_field_input.setText(cgtw.get("flow_field_sign", "task.supervise_status"))
        self.cgtw_flow_status_input.setText(cgtw.get("flow_status", "内部返修"))
        self.cgtw_sync_note_check.setChecked(cgtw.get("sync_note", True))
        self.cgtw_submit_review_check.setChecked(cgtw.get("submit_review", False))
        self.cgtw_upload_filebox_check.setChecked(cgtw.get("upload_filebox", False))
        self.cgtw_update_status_check.setChecked(cgtw.get("update_status", False))
        self.cgtw_target_status_input.setText(cgtw.get("target_status", ""))

    def get_settings(self):
        departments = [dep.strip() for dep in self.departments_input.text().split(",") if dep.strip()]
        audio_device_index = self.audio_device_combo.currentData()
        if audio_device_index == -1: audio_device_index = None
        cgtw_shot_field = self.cgtw_shot_field_input.text().strip() or "etask.url"
        if cgtw_shot_field in {"shot.entity", "task.entity"}:
            cgtw_shot_field = "etask.url"
        cgtw_sync = {
            "enabled": self.cgtw_enabled_check.isChecked(),
            "dry_run": self.cgtw_dry_run_check.isChecked(),
            "base_path": self.cgtw_base_path_input.text().strip() or DEFAULT_CGTW_BASE_PATH,
            "python_path": self.cgtw_python_path_input.text().strip(),
            "db": self.cgtw_db_input.text().strip(),
            "module": self.cgtw_module_input.text().strip() or "shot",
            "module_type": "task",
            "target_api": "etask",
            "shot_field": cgtw_shot_field,
            "shot_filter_operator": "has",
            "task_name_field": "pipeline.entity",
            "task_name": self.cgtw_task_name_input.text().strip() or "UE_FX",
            "filebox_sign": self.cgtw_filebox_sign_input.text().strip() or "review",
            "filebox_id": self.cgtw_filebox_id_input.text().strip(),
            "sync_mode": "flow",
            "flow_field_sign": self.cgtw_flow_field_input.text().strip() or "task.supervise_status",
            "flow_status": self.cgtw_flow_status_input.text().strip() or "内部返修",
            "sync_note": self.cgtw_sync_note_check.isChecked(),
            "submit_review": self.cgtw_submit_review_check.isChecked(),
            "upload_filebox": self.cgtw_upload_filebox_check.isChecked(),
            "update_status": self.cgtw_update_status_check.isChecked(),
            "target_status": self.cgtw_target_status_input.text().strip(),
        }
        return {
            "project_name": self.project_name_input.text(), "producer": self.producer_input.text(), "reviewer": self.reviewer_input.text(),
            "ai_provider": self.provider_combo.currentText(), "api_key": self.api_key_input.text(), "base_url": self.base_url_input.text(),
            "model_name": self.model_name_input.text(), "realtime_transcribe": self.realtime_transcribe_check.isChecked(),
            "screen_record_fps": self.screen_record_fps_spinbox.value(), "screen_record_monitor": self.monitor_combo.currentData(),
            "ffmpeg_path": self.ffmpeg_path_input.text(), "departments": departments, "audio_device_index": audio_device_index,
            "theme": self.theme_combo.currentData(), "cgtw_sync": cgtw_sync
        }

    def _audio_monitor_callback(self, indata, frames, time, status):
        if status: print(f"Audio monitor status: {status}")
        volume_norm = np.linalg.norm(indata) * 10
        self.volume_updated_signal.emit(int(np.clip(volume_norm, 0, 100)))

    def _update_volume_preview_bar(self, level):
        self.volume_preview_bar.setValue(level)

    def start_audio_monitor(self):
        self.stop_audio_monitor()
        if not sd or not self.audio_device_combo.isEnabled(): return
        try:
            device_index = self.audio_device_combo.currentData()
            if device_index == -1: device_index = None
            self.audio_stream = sd.InputStream(device=device_index, channels=1, samplerate=16000, callback=self._audio_monitor_callback)
            self.audio_stream.start()
            self.is_monitoring_audio = True
        except Exception as e:
            print(f"无法启动音频预览: {e}"); self.volume_preview_bar.setValue(0)

    def stop_audio_monitor(self):
        if self.is_monitoring_audio and self.audio_stream:
            try:
                self.audio_stream.stop()
                self.audio_stream.close()
            except Exception as e:
                print(f"停止音频预览时出错: {e}")
        self.audio_stream = None
        self.is_monitoring_audio = False
        self.volume_preview_bar.setValue(0)

    def accept(self):
        self.stop_audio_monitor()
        super().accept()

    def reject(self):
        self.stop_audio_monitor()
        super().reject()

    def closeEvent(self, event):
        self.stop_audio_monitor()
        super().closeEvent(event)
