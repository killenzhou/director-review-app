# -*- coding: utf-8 -*-
import os
import re
import shutil
import tempfile
import threading
import time

from PIL import Image
from PySide6.QtCore import QObject, Signal, QTimer
from PySide6.QtWidgets import QApplication, QMessageBox

from ai_processor import AIProcessor, DEFAULT_LOCAL_BASE_URL, DEFAULT_LOCAL_MODEL, LOCAL_AI_PROVIDERS
from app_constants import DEFAULT_DEPARTMENTS
from recording_manager import RecordingManager, check_ffmpeg_availability
from ui_components import AnnotationOverlay


class ReviewCaptureSession(QObject):
    recording_started = Signal(str)
    recording_stopped = Signal()
    review_ready = Signal(dict)
    error_occurred = Signal(str)

    def __init__(self, settings, parent=None):
        super().__init__(parent)
        self.settings = dict(settings or {})
        self.settings["departments"] = DEFAULT_DEPARTMENTS.copy()
        self.temp_root = os.path.join(tempfile.gettempdir(), "davinci_cgt_review")
        os.makedirs(self.temp_root, exist_ok=True)
        self.recording_manager = RecordingManager(self.settings, self)
        self.recording_manager.recording_finished.connect(self._on_recording_finished)
        self.recording_manager.error_occurred.connect(self.error_occurred.emit)
        self.annotation_overlay = None
        self.active_shot = ""
        self.active_save_dir = ""

    def is_recording(self):
        return self.recording_manager.is_recording()

    def start(self, shot_number, record_video=True):
        if self.is_recording():
            return
        self.active_shot = shot_number or "UNASSIGNED"
        safe_shot = re.sub(r'[\\/:*?"<>|]', "_", self.active_shot)
        self.active_save_dir = os.path.join(self.temp_root, safe_shot, time.strftime("%Y%m%d_%H%M%S"))
        os.makedirs(self.active_save_dir, exist_ok=True)
        status = self.recording_manager.start(bool(record_video), self.active_save_dir)
        if status:
            self.recording_started.emit(status)

    def stop(self):
        if not self.is_recording():
            return
        self.recording_manager.stop()
        self.recording_stopped.emit()

    def open_annotation_overlay(self):
        if not self.active_save_dir:
            QMessageBox.warning(None, "无法批注", "请先开始返修录制。")
            return
        source_path = self._capture_screen_to_file()
        if not source_path:
            return
        self.annotation_overlay = AnnotationOverlay(source_path, self.active_save_dir, None)
        self.annotation_overlay.annotation_saved.connect(self._on_annotation_saved)
        self.annotation_overlay.show()

    def _capture_screen_to_file(self):
        try:
            import mss
            with mss.mss() as sct:
                monitor_index = self.settings.get("screen_record_monitor", 0)
                if monitor_index >= len(sct.monitors):
                    monitor_index = 0
                monitor = sct.monitors[monitor_index]
                sct_img = sct.grab(monitor)
                img = Image.frombytes("RGB", sct_img.size, sct_img.bgra, "raw", "BGRX")
                max_width = 1280
                if img.width > max_width:
                    ratio = max_width / img.width
                    new_height = int(img.height * ratio)
                    img = img.resize((max_width, new_height), Image.Resampling.LANCZOS)
                path = os.path.join(self.active_save_dir, f"annotation_source_{int(time.time())}.png")
                img.save(path, quality=95)
                return path
        except Exception as exc:
            self.error_occurred.emit(f"截图批注失败: {exc}")
            return ""

    def _on_annotation_saved(self, path):
        if path and os.path.exists(path):
            self.recording_manager.pending_review_data.setdefault("pending_reference_files", []).append(path)

    def _on_recording_finished(self, data):
        threading.Thread(target=self._prepare_review, args=(dict(data or {}),), daemon=True).start()

    def _prepare_review(self, data):
        try:
            entry = self._build_entry(data)
            text = self._transcribe(entry.get("audio_path"))
            entry["full_review"] = text
            if text and not text.startswith("语音模型"):
                ai_result = self._analyze(text)
                entry.update({
                    "simplified_review": ai_result.get("simplified_review", ""),
                    "keywords": ai_result.get("keywords", []),
                    "department": ai_result.get("department", "未分类"),
                })
            self.review_ready.emit(entry)
        except Exception as exc:
            self.error_occurred.emit(f"返修数据处理失败: {exc}")

    def _build_entry(self, data):
        refs = []
        refs.extend(data.get("reference_files") or [])
        refs.extend(data.get("pending_reference_files") or [])
        return {
            "entry_type": "davinci_retake",
            "shot_number": self.active_shot,
            "timestamp": "",
            "screenshot_path": data.get("screenshot_path"),
            "original_screenshot_path": data.get("screenshot_path"),
            "audio_path": data.get("audio_path"),
            "media_files": data.get("media_files") or [],
            "reference_files": refs,
            "full_review": "",
            "simplified_review": "",
            "keywords": [],
            "department": "未分类",
            "approved": False,
        }

    def _transcribe(self, audio_path):
        if not audio_path or not os.path.exists(audio_path):
            return ""
        try:
            from funasr import AutoModel
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            model_root = os.path.join(base_dir, "FunASR_models")
            model = AutoModel(
                model=os.path.join(model_root, "speech_paraformer-large_asr_nat-zh-cn-16k-common-vocab8404-pytorch"),
                vad_model=os.path.join(model_root, "speech_fsmn_vad_zh-cn-16k-common-pytorch"),
                punc_model=os.path.join(model_root, "punc_ct-transformer_zh-cn-common-vocab272727-pytorch"),
                disable_update=True,
            )
            result = model.generate(input=audio_path, batch_size_s=300)
            if isinstance(result, list) and result:
                return str(result[0].get("text") or "").strip() or "没有识别到声音"
            return "没有识别到声音"
        except Exception as exc:
            return f"语音模型未加载或转写失败: {exc}"

    def _analyze(self, text):
        try:
            if self.settings.get("ai_provider") in LOCAL_AI_PROVIDERS and not self._is_local_ai_available():
                return {"simplified_review": "", "keywords": [], "department": "未分类"}
            ai_proc = AIProcessor(
                provider=self.settings.get("ai_provider", "local-ai"),
                api_key=self.settings.get("api_key", "local"),
                base_url=self.settings.get("base_url", DEFAULT_LOCAL_BASE_URL),
                model_name=self.settings.get("model_name", DEFAULT_LOCAL_MODEL),
            )
            return ai_proc.rewrite_review(text, DEFAULT_DEPARTMENTS)
        except Exception:
            return {"simplified_review": "", "keywords": [], "department": "未分类"}

    def _is_local_ai_available(self):
        import urllib.request
        base_url = (self.settings.get("base_url") or DEFAULT_LOCAL_BASE_URL).rstrip("/")
        if not base_url.endswith("/v1"):
            base_url = f"{base_url}/v1"
        try:
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
            with opener.open(f"{base_url}/models", timeout=2) as response:
                return 200 <= response.status < 300
        except Exception:
            return False


def copy_references_to_entry(paths, entry):
    if not paths:
        return entry
    entry = dict(entry)
    target_dir = os.path.dirname(entry.get("screenshot_path") or "") or tempfile.gettempdir()
    refs = list(entry.get("reference_files") or [])
    for src in paths:
        if not src or not os.path.exists(src):
            continue
        dst = os.path.join(target_dir, os.path.basename(src))
        if os.path.abspath(src) != os.path.abspath(dst):
            base, ext = os.path.splitext(dst)
            index = 1
            while os.path.exists(dst):
                dst = f"{base}_{index}{ext}"
                index += 1
            shutil.copy2(src, dst)
        refs.append(dst)
    entry["reference_files"] = refs
    return entry
