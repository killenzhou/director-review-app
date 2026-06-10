# -*- coding: utf-8 -*-
# --- START OF FILE recording_manager.py ---

import os
import sys
import time
import wave
import threading
import subprocess
import shutil
import numpy as np
import sounddevice as sd
from PIL import Image
from PySide6.QtCore import QObject, Signal

try:
    import mss
except ImportError:
    mss = None

def check_ffmpeg_availability(settings):
    user_path = settings.get("ffmpeg_path", "")
    if user_path and os.path.isfile(user_path): return user_path
    try:
        exe_dir = os.path.dirname(sys.executable) if getattr(sys, "frozen", False) else os.path.dirname(os.path.abspath(__file__))
        portable_path = os.path.join(exe_dir, 'external_files', 'ffmpeg.exe')
        if os.path.isfile(portable_path): return portable_path
    except Exception:
        pass
    if hasattr(sys, '_MEIPASS'):
        bundled_path = os.path.join(sys._MEIPASS, 'external_files', 'ffmpeg.exe')
        if os.path.isfile(bundled_path): return bundled_path
    try:
        base_dir = os.path.dirname(os.path.abspath(__file__))
        dev_path = os.path.join(base_dir, 'external_files', 'ffmpeg.exe')
        if os.path.isfile(dev_path): return dev_path
    except NameError: pass
    return shutil.which('ffmpeg')

class RecordingManager(QObject):
    recording_finished = Signal(dict)
    mobile_text_capture_finished = Signal(dict) # New signal for mobile workflow
    volume_updated = Signal(int)
    error_occurred = Signal(str)

    def __init__(self, settings, parent=None):
        super().__init__(parent)
        self.settings = settings
        self.ffmpeg_path = None
        self.is_ffmpeg_available = False
        self.pending_review_data = {}
        self.audio_buffer = []
        self._is_recording_flag = threading.Event()
        self.is_screen_recording_active = False
        self.audio_stream = None
        self.ffmpeg_process = None
        self.video_only_path = None
        self.update_ffmpeg_status()

    def update_ffmpeg_status(self):
        self.ffmpeg_path = check_ffmpeg_availability(self.settings)
        self.is_ffmpeg_available = self.ffmpeg_path is not None

    def is_mss_available(self): return mss is not None
    def is_recording(self): return self._is_recording_flag.is_set()

    def start(self, enable_screen_recording, save_dir):
        if self.is_recording(): return None
        os.makedirs(save_dir, exist_ok=True)
        timestamp = int(time.time())
        screenshot_path = os.path.join(save_dir, f"capture_{timestamp}.png")
        
        try:
            with mss.mss() as sct:
                monitor_index = self.settings.get("screen_record_monitor", 0)
                if monitor_index >= len(sct.monitors): monitor_index = 0
                monitor = sct.monitors[monitor_index]
                sct_img = sct.grab(monitor)
                img = Image.frombytes("RGB", sct_img.size, sct_img.bgra, "raw", "BGRX")
                max_width = 1280
                if img.width > max_width:
                    ratio = max_width / img.width; new_height = int(img.height * ratio)
                    img = img.resize((max_width, new_height), Image.Resampling.LANCZOS)
                img.save(screenshot_path, quality=85)
        except Exception as e:
            self.error_occurred.emit(f"截图失败: {e}"); return None
        
        self.pending_review_data = {"screenshot_path": screenshot_path, "media_files": []}
        self.audio_buffer.clear()
        
        try:
            device_index = self.settings.get("audio_device_index", None)
            self.audio_stream = sd.InputStream(callback=self.audio_callback, samplerate=16000, channels=1, device=device_index)
            self.audio_stream.start()
        except Exception as e:
            self.error_occurred.emit(f"无法启动录音设备: {e}\n\n请在“设置”中检查并选择有效的麦克风。"); return None
        
        self._is_recording_flag.set(); status_text = "正在录音..."
        self.is_screen_recording_active = enable_screen_recording and self.is_ffmpeg_available
        
        if self.is_screen_recording_active:
            self._start_ffmpeg_screen_recording(save_dir)
            status_text = "正在录音和录屏..."
        return status_text

    def _start_ffmpeg_screen_recording(self, save_dir):
        monitor_index = self.settings.get("screen_record_monitor", 0)
        with mss.mss() as sct:
            if monitor_index >= len(sct.monitors): monitor_index = 0
            monitor = sct.monitors[monitor_index]
        
        fps = self.settings.get("screen_record_fps", 10)
        self.video_only_path = os.path.join(save_dir, f"video_only_{int(time.time())}.mp4")
        command = [self.ffmpeg_path, '-f', 'gdigrab', '-draw_mouse', '1', '-framerate', str(fps), 
                   '-offset_x', str(monitor["left"]), '-offset_y', str(monitor["top"]), 
                   '-s', f'{monitor["width"]}x{monitor["height"]}', '-i', 'desktop', '-c:v', 'libx264', 
                   '-preset', 'ultrafast', '-crf', '28', '-pix_fmt', 'yuv420p', '-y', self.video_only_path]
        
        startupinfo = subprocess.STARTUPINFO() if sys.platform == "win32" else None
        if startupinfo: startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        self.ffmpeg_process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, startupinfo=startupinfo)

    def stop(self, is_mobile_text=False):
        if not self.is_recording(): return
        self._is_recording_flag.clear()
        
        if self.audio_stream:
            self.audio_stream.stop(); self.audio_stream.close(); self.audio_stream = None
        
        if self.ffmpeg_process:
            try: self.ffmpeg_process.communicate(input=b'q\n', timeout=5)
            except subprocess.TimeoutExpired: self.ffmpeg_process.kill(); self.ffmpeg_process.communicate()
            finally: self.ffmpeg_process = None

        self.volume_updated.emit(0)
        
        if is_mobile_text:
            self.pending_review_data['audio_path'] = None
            if self.is_screen_recording_active and self.video_only_path and os.path.exists(self.video_only_path):
                # We need to move the video file to a persistent name before OCR
                final_video_path = self.video_only_path.replace("video_only", f"review_video_{int(time.time())}")
                os.rename(self.video_only_path, final_video_path)
                self.pending_review_data["media_files"].append(final_video_path)
            self.mobile_text_capture_finished.emit(self.pending_review_data)
            return

        threading.Thread(target=self._process_recordings_thread, daemon=True).start()

    def audio_callback(self, indata, frames, time, status):
        try:
            if status: print(status, file=sys.stderr)
            self.audio_buffer.append(indata.copy())
            volume_norm = np.linalg.norm(indata) * 10
            self.volume_updated.emit(int(np.clip(volume_norm, 0, 100)))
        except Exception as e:
            print(f"Audio callback error: {e}", file=sys.stderr)

    def _process_recordings_thread(self):
        if not self.pending_review_data: return
        save_dir = os.path.dirname(self.pending_review_data["screenshot_path"])
        base_name = f"review_{int(time.time())}"
        audio_path = os.path.join(save_dir, f"{base_name}.wav")
        self._save_audio_to_wav(audio_path)
        self.pending_review_data["audio_path"] = audio_path
        
        if self.is_screen_recording_active and self.video_only_path and os.path.exists(self.video_only_path):
            final_video_path = os.path.join(save_dir, f"{base_name}_final.mp4")
            try:
                if os.path.getsize(self.video_only_path) > 0:
                    command = [self.ffmpeg_path, '-y', '-i', self.video_only_path, '-i', audio_path,
                               '-c:v', 'copy', '-c:a', 'aac', '-b:a', '128k', '-shortest', final_video_path]
                    startupinfo = subprocess.STARTUPINFO() if sys.platform == "win32" else None
                    if startupinfo: startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                    subprocess.run(command, check=True, capture_output=True, text=True, startupinfo=startupinfo, timeout=60, encoding='utf-8', errors='ignore')
                    self.pending_review_data["media_files"].append(final_video_path)
                    os.remove(self.video_only_path)
                else: self.pending_review_data["media_files"].append(audio_path)
            except Exception as e:
                print(f"视频合并失败: {e}"); self.pending_review_data["media_files"].append(audio_path)
        else: self.pending_review_data["media_files"].append(audio_path)
        
        self.recording_finished.emit(self.pending_review_data)

    def _save_audio_to_wav(self, path):
        samplerate = 16000
        audio_data = np.concatenate(self.audio_buffer, axis=0) if self.audio_buffer else np.array([], dtype=np.float32)
        try:
            with wave.open(path, 'wb') as wf:
                wf.setnchannels(1); wf.setsampwidth(2); wf.setframerate(samplerate)
                wf.writeframes((audio_data * 32767).astype(np.int16).tobytes())
        except Exception as e: print(f"保存WAV文件失败: {e}")
