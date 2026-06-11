# -*- coding: utf-8 -*-
"""
DaVinci Resolve launcher for the standalone CGT review panel.

Copy this file to:
%APPDATA%\\Blackmagic Design\\DaVinci Resolve\\Support\\Fusion\\Scripts\\Utility
"""
import os
import json
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse


APP_ROOT = os.environ.get(
    "DAVINCI_CGT_REVIEW_ROOT",
    r"F:\alienbrainWork\killen\协同审阅平台\director_review_app-原文件\director_review_app",
)
APP_ENTRY = os.path.join(APP_ROOT, "davinci_review_tool", "davinci_review_app.py")
BRIDGE_HOST = "127.0.0.1"
BRIDGE_PORT = 8791
_BRIDGE_HTTPD = None
_BRIDGE_THREAD = None


def _resolve_app():
    fusion_obj = globals().get("fusion")
    if fusion_obj and hasattr(fusion_obj, "GetResolve"):
        try:
            resolve = fusion_obj.GetResolve()
            if resolve:
                return resolve
        except Exception:
            pass
    candidates = []
    if "bmd" in globals():
        candidates.append(globals()["bmd"])
    try:
        import DaVinciResolveScript as dvr_script
        candidates.append(dvr_script)
    except Exception:
        pass
    for candidate in candidates:
        scriptapp = getattr(candidate, "scriptapp", None)
        if not scriptapp:
            continue
        try:
            resolve = scriptapp("Resolve")
            if resolve:
                return resolve
        except Exception:
            continue
    return None


def _shot_from_name(name):
    import re
    match = re.search(r"(?i)(ep\d+[_-]sc\d+[_-]\d+[a-zA-Z0-9-]*)", str(name or ""))
    if not match:
        return ""
    text = os.path.splitext(os.path.basename(match.group(1)))[0]
    return re.sub(
        r"(?i)^ep(\d+)[_-]sc(\d+)[_-](.+)$",
        lambda m: f"EP{int(m.group(1)):03d}_SC{int(m.group(2)):03d}_{m.group(3)}",
        text,
    )


def _episode_from_shot(shot):
    import re
    match = re.match(r"(?i)EP(\d+)", str(shot or ""))
    return f"EP{int(match.group(1)):03d}" if match else ""


def _frame_to_tc(frame, fps):
    frame = int(frame or 0)
    fps_int = max(1, int(round(float(fps or 24.0))))
    hours = frame // (fps_int * 3600)
    frame %= fps_int * 3600
    minutes = frame // (fps_int * 60)
    frame %= fps_int * 60
    seconds = frame // fps_int
    frames = frame % fps_int
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}:{frames:02d}"


def _current_project_timeline():
    resolve = _resolve_app()
    if not resolve:
        raise RuntimeError("Resolve bridge 无法获取 Resolve 对象。")
    project_manager = resolve.GetProjectManager()
    project = project_manager.GetCurrentProject() if project_manager else None
    if not project:
        raise RuntimeError("Resolve bridge 未找到当前项目。")
    timeline = project.GetCurrentTimeline()
    if not timeline:
        raise RuntimeError("Resolve bridge 未找到当前时间线。")
    return resolve, project, timeline


def _current_clip_info():
    _, project, timeline = _current_project_timeline()
    clip = timeline.GetCurrentVideoItem()
    if not clip:
        raise RuntimeError("播放头下没有当前视频片段。")
    clip_name = clip.GetName() or ""
    shot = _shot_from_name(clip_name)
    if not shot:
        raise RuntimeError(f"无法从当前片段名解析镜头号: {clip_name}")
    try:
        start_frame = int(clip.GetStart())
    except Exception:
        start_frame = 0
    return {
        "clip_name": clip_name,
        "shot_number": shot,
        "episode": _episode_from_shot(shot),
        "start_frame": start_frame,
        "project_name": project.GetName() if hasattr(project, "GetName") else "",
        "timeline_name": timeline.GetName() if hasattr(timeline, "GetName") else "",
    }


def _timeline_clips():
    _, _, timeline = _current_project_timeline()
    clips = []
    for track_index in range(1, int(timeline.GetTrackCount("video") or 0) + 1):
        for clip in timeline.GetItemListInTrack("video", track_index) or []:
            clip_name = clip.GetName() or ""
            shot = _shot_from_name(clip_name)
            if not shot:
                continue
            try:
                start_frame = int(clip.GetStart())
            except Exception:
                start_frame = 0
            clips.append({
                "clip_name": clip_name,
                "shot_number": shot,
                "track_index": track_index,
                "start_frame": start_frame,
            })
    return clips


def _jump_to_shot(shot):
    _, _, timeline = _current_project_timeline()
    target = str(shot or "").lower()
    found = None
    for item in _timeline_clips():
        if item["shot_number"].lower() == target or target in item["clip_name"].lower():
            found = item
            break
    if not found:
        return False
    try:
        fps = float(timeline.GetSetting("timelineFrameRate") or 24.0)
    except Exception:
        fps = 24.0
    return bool(timeline.SetCurrentTimecode(_frame_to_tc(found["start_frame"], fps)))


class ResolveBridgeHandler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        return

    def do_GET(self):
        try:
            parsed = urlparse(self.path)
            if parsed.path == "/health":
                return self._send({"ok": True})
            if parsed.path == "/current":
                return self._send({"ok": True, "data": _current_clip_info()})
            if parsed.path == "/clips":
                return self._send({"ok": True, "data": _timeline_clips()})
            if parsed.path == "/jump":
                shot = (parse_qs(parsed.query).get("shot") or [""])[0]
                return self._send({"ok": _jump_to_shot(shot)})
            self._send({"ok": False, "error": "not found"}, status=404)
        except Exception as exc:
            self._send({"ok": False, "error": str(exc)}, status=500)

    def _send(self, data, status=200):
        raw = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)


def ensure_bridge():
    global _BRIDGE_HTTPD, _BRIDGE_THREAD
    if _BRIDGE_THREAD and _BRIDGE_THREAD.is_alive():
        return True
    try:
        _BRIDGE_HTTPD = ThreadingHTTPServer((BRIDGE_HOST, BRIDGE_PORT), ResolveBridgeHandler)
    except OSError:
        return True
    _BRIDGE_THREAD = threading.Thread(target=_BRIDGE_HTTPD.serve_forever)
    _BRIDGE_THREAD.daemon = False
    _BRIDGE_THREAD.start()
    return True


def _candidate_pythons():
    configured = os.environ.get("DAVINCI_CGT_REVIEW_PYTHON")
    if configured:
        yield configured
    yield os.path.join(APP_ROOT, "director_tool_env", "Scripts", "pythonw.exe")
    yield os.path.join(APP_ROOT, "director_tool_env", "Scripts", "python.exe")
    yield sys.executable


def launch():
    if not os.path.isfile(APP_ENTRY):
        print(f"找不到达芬奇 CGT 审核面板入口: {APP_ENTRY}")
        return 1
    python_exe = next((path for path in _candidate_pythons() if path and os.path.isfile(path)), "")
    if not python_exe:
        print("找不到可用 Python，请设置 DAVINCI_CGT_REVIEW_PYTHON。")
        return 1

    env = os.environ.copy()
    resolve_pythonpath = os.pathsep.join(sys.path)
    if env.get("PYTHONPATH"):
        env["PYTHONPATH"] = resolve_pythonpath + os.pathsep + env["PYTHONPATH"]
    else:
        env["PYTHONPATH"] = resolve_pythonpath
    env["DAVINCI_CGT_REVIEW_ROOT"] = APP_ROOT
    ensure_bridge()
    env["DAVINCI_CGT_RESOLVE_BRIDGE"] = f"http://{BRIDGE_HOST}:{BRIDGE_PORT}"

    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    subprocess.Popen([python_exe, APP_ENTRY], cwd=APP_ROOT, env=env, close_fds=True, creationflags=creationflags)
    return 0


if __name__ == "__main__":
    raise SystemExit(launch())
