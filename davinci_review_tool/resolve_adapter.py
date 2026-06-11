# -*- coding: utf-8 -*-
import os
import re
import json
import urllib.error
import urllib.parse
import urllib.request


SHOT_PATTERN = re.compile(r"(?i)(ep\d+[_-]sc\d+[_-]\d+[a-zA-Z0-9-]*)")


def normalize_shot_id(value):
    text = str(value or "").strip()
    match = SHOT_PATTERN.search(text)
    if match:
        text = match.group(1)
    text = os.path.splitext(os.path.basename(text))[0]
    def repl(match):
        shot = match.group(3)
        if shot.isdigit():
            shot = shot[-3:] if len(shot) > 3 and shot.startswith("0") else shot.zfill(3)
        return f"Ep{int(match.group(1)):03d}_sc{int(match.group(2)):03d}_{shot}"
    text = re.sub(r"(?i)^ep(\d+)[_-]sc(\d+)[_-](.+)$", repl, text)
    return text


def parse_shot_from_name(name):
    match = SHOT_PATTERN.search(str(name or ""))
    if not match:
        return ""
    return normalize_shot_id(match.group(1))


def parse_episode_from_shot(shot_number):
    match = re.match(r"(?i)EP(\d+)", str(shot_number or ""))
    return f"Ep{int(match.group(1)):03d}" if match else ""


class ResolveAdapter:
    def __init__(self):
        self._dvr_script = None
        self._bmd = None
        self.bridge_url = os.environ.get("DAVINCI_CGT_RESOLVE_BRIDGE", "").rstrip("/")
        self._load_module()

    def _load_module(self):
        try:
            import DaVinciResolveScript as dvr_script
            if hasattr(dvr_script, "scriptapp"):
                self._dvr_script = dvr_script
                self._bmd = dvr_script
            else:
                self._dvr_script = None
                self._bmd = None
        except Exception:
            self._dvr_script = None
            self._bmd = None

    def is_available(self):
        return bool(self.bridge_url) or self._bmd is not None

    def _bridge_get(self, path, params=None):
        if not self.bridge_url:
            raise RuntimeError("Resolve bridge 未启动。")
        query = ""
        if params:
            query = "?" + urllib.parse.urlencode(params)
        try:
            with urllib.request.urlopen(f"{self.bridge_url}{path}{query}", timeout=5) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except urllib.error.URLError as exc:
            raise RuntimeError("Resolve bridge 未连接。请关闭本面板后，从 DaVinci Resolve 的脚本菜单重新启动。") from exc
        if not payload.get("ok"):
            raise RuntimeError(payload.get("error") or "Resolve bridge 请求失败")
        return payload.get("data", payload)

    def get_objects(self):
        if not self._bmd:
            self._load_module()
        if not self._bmd:
            raise RuntimeError("无法导入 DaVinciResolveScript。请从 DaVinci Resolve 脚本菜单启动。")
        resolve = self._bmd.scriptapp("Resolve")
        if not resolve:
            raise RuntimeError("无法连接到 DaVinci Resolve。")
        project_manager = resolve.GetProjectManager()
        project = project_manager.GetCurrentProject() if project_manager else None
        if not project:
            raise RuntimeError("未找到当前 Resolve 项目。")
        timeline = project.GetCurrentTimeline()
        if not timeline:
            raise RuntimeError("未找到当前时间线。")
        return resolve, project, timeline

    def get_current_clip_info(self):
        if self.bridge_url:
            data = self._bridge_get("/current")
            data["shot_number"] = normalize_shot_id(data.get("shot_number"))
            data["episode"] = data.get("episode") or parse_episode_from_shot(data["shot_number"])
            return data
        resolve, project, timeline = self.get_objects()
        clip = timeline.GetCurrentVideoItem()
        if not clip:
            raise RuntimeError("播放头下没有当前视频片段。")
        clip_name = clip.GetName() or ""
        shot_number = parse_shot_from_name(clip_name)
        if not shot_number:
            raise RuntimeError(f"无法从当前片段名解析镜头号: {clip_name}")
        try:
            start_frame = int(clip.GetStart())
        except Exception:
            start_frame = 0
        return {
            "clip_name": clip_name,
            "shot_number": shot_number,
            "episode": parse_episode_from_shot(shot_number),
            "start_frame": start_frame,
            "timeline_name": timeline.GetName() if hasattr(timeline, "GetName") else "",
            "project_name": project.GetName() if hasattr(project, "GetName") else "",
        }

    def scan_timeline_clips(self):
        if self.bridge_url:
            data = self._bridge_get("/clips")
            for item in data:
                item["shot_number"] = normalize_shot_id(item.get("shot_number"))
            return data
        _, _, timeline = self.get_objects()
        clips = []
        for track_index in range(1, int(timeline.GetTrackCount("video") or 0) + 1):
            for clip in timeline.GetItemListInTrack("video", track_index) or []:
                clip_name = clip.GetName() or ""
                shot_number = parse_shot_from_name(clip_name)
                if not shot_number:
                    continue
                try:
                    start_frame = int(clip.GetStart())
                except Exception:
                    start_frame = 0
                clips.append({
                    "clip": clip,
                    "clip_name": clip_name,
                    "shot_number": shot_number,
                    "track_index": track_index,
                    "start_frame": start_frame,
                })
        return clips

    def find_clip_by_shot(self, shot_number):
        target = normalize_shot_id(shot_number).lower()
        for info in self.scan_timeline_clips():
            if info["shot_number"].lower() == target or target in info["clip_name"].lower():
                return info
        return None

    def jump_to_shot(self, shot_number):
        if self.bridge_url:
            query = urllib.parse.urlencode({"shot": normalize_shot_id(shot_number)})
            try:
                with urllib.request.urlopen(f"{self.bridge_url}/jump?{query}", timeout=5) as response:
                    payload = json.loads(response.read().decode("utf-8"))
            except urllib.error.URLError as exc:
                raise RuntimeError("Resolve bridge 未连接。请关闭本面板后，从 DaVinci Resolve 的脚本菜单重新启动。") from exc
            return bool(payload.get("ok"))
        _, _, timeline = self.get_objects()
        info = self.find_clip_by_shot(shot_number)
        if not info:
            return False
        fps = self._timeline_fps(timeline)
        return bool(timeline.SetCurrentTimecode(self.frame_to_timecode(info["start_frame"], fps)))

    def _timeline_fps(self, timeline):
        try:
            return float(timeline.GetSetting("timelineFrameRate") or 24.0)
        except Exception:
            return 24.0

    def frame_to_timecode(self, frame, fps):
        frame = int(frame or 0)
        fps_int = max(1, int(round(float(fps or 24.0))))
        hours = frame // (fps_int * 3600)
        frame %= fps_int * 3600
        minutes = frame // (fps_int * 60)
        frame %= fps_int * 60
        seconds = frame // fps_int
        frames = frame % fps_int
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}:{frames:02d}"
