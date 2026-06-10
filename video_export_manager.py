# -*- coding: utf-8 -*-
import os
import re
import subprocess
import tempfile


def natural_shot_key(shot_number):
    text = str(shot_number or "")
    parts = re.split(r"(\d+)", text)
    return [int(part) if part.isdigit() else part.lower() for part in parts]


def first_video_path(entry, temp_dir):
    for rel_path in entry.get("media_files", []) or []:
        if not rel_path or not str(rel_path).lower().endswith(".mp4"):
            continue
        if os.path.isabs(rel_path):
            return rel_path
        if temp_dir:
            return resolve_existing_media_path(temp_dir, rel_path)
    return None


def resolve_existing_media_path(temp_dir, rel_path):
    normalized = str(rel_path).replace("\\", "/")
    exact_path = os.path.join(temp_dir, normalized.replace("/", os.sep))
    if os.path.exists(exact_path):
        return exact_path

    basename = os.path.basename(normalized)
    matches = []
    for root, _, files in os.walk(temp_dir):
        if basename in files:
            matches.append(os.path.join(root, basename))
            if len(matches) > 1:
                break
    if len(matches) == 1:
        return matches[0]

    parts = normalized.split("/")
    try:
        recordings_index = parts.index("recordings")
    except ValueError:
        return exact_path
    if len(parts) < recordings_index + 3:
        return exact_path

    folder = os.path.join(temp_dir, *parts[:recordings_index + 2])
    if not os.path.isdir(folder):
        return exact_path
    videos = [
        os.path.join(folder, name)
        for name in os.listdir(folder)
        if os.path.isfile(os.path.join(folder, name)) and name.lower().endswith(".mp4")
    ]
    return videos[0] if len(videos) == 1 else exact_path


def truncate_text(text, max_len=72):
    clean = re.sub(r"\s+", " ", str(text or "")).strip()
    return clean if len(clean) <= max_len else clean[:max_len - 1] + "…"


def overlay_text_for_entry(entry):
    review = entry.get("simplified_review") or truncate_text(entry.get("full_review"), 80)
    keywords = entry.get("keywords") or []
    if isinstance(keywords, str):
        keywords = [part.strip() for part in re.split(r"[,，、/]", keywords) if part.strip()]
    keyword_line = " / ".join(str(item).strip() for item in keywords if str(item).strip())
    return truncate_text(review, 80), truncate_text(keyword_line, 80)


def find_yahei_font():
    candidates = [
        r"C:\Windows\Fonts\msyh.ttc",
        r"C:\Windows\Fonts\msyh.ttf",
        r"C:\Windows\Fonts\simhei.ttf",
        r"C:\Windows\Fonts\simsun.ttc",
    ]
    for path in candidates:
        if os.path.exists(path):
            return path
    return None


def escape_drawtext_text(text):
    value = str(text or "")
    value = value.replace("\\", "\\\\")
    value = value.replace(":", "\\:")
    value = value.replace("'", "\\'")
    value = value.replace("%", "\\%")
    value = value.replace(",", "\\,")
    value = value.replace("\n", " ")
    return value


def escape_filter_path(path):
    value = str(path or "").replace("\\", "/")
    value = value.replace(":", "\\:")
    value = value.replace("'", "\\'")
    return value


def build_overlay_filter(line1, line2, font_path=None):
    font = f"fontfile='{escape_filter_path(font_path)}':" if font_path else ""
    text1 = escape_drawtext_text(line1)
    text2 = escape_drawtext_text(line2)
    box = "drawbox=x=0:y=ih-118:w=iw:h=118:color=black@0.58:t=fill:enable='lte(t,3)'"
    draw1 = (
        f"drawtext={font}text='{text1}':x=40:y=h-100:fontsize=28:"
        "fontcolor=white:enable='lte(t,3)'"
    )
    draw2 = (
        f"drawtext={font}text='{text2}':x=40:y=h-58:fontsize=22:"
        "fontcolor=0xdbeafe:enable='lte(t,3)'"
    )
    return ",".join([box, draw1, draw2])


def collect_video_entries(review_entries, temp_dir):
    collected = []
    skipped = []
    for entry in sorted(review_entries, key=lambda item: natural_shot_key(item.get("shot_number"))):
        video_path = first_video_path(entry, temp_dir)
        if video_path and os.path.exists(video_path):
            collected.append((entry, video_path))
        else:
            skipped.append(entry.get("shot_number") or "未命名镜头")
    return collected, skipped


def export_merged_video(review_entries, temp_dir, output_path, ffmpeg_path):
    if not ffmpeg_path or not os.path.exists(ffmpeg_path):
        return False, "找不到 FFmpeg，请先在设置中配置 FFmpeg 路径。"
    videos, skipped = collect_video_entries(review_entries, temp_dir)
    if not videos:
        return False, "没有找到可合并的 mp4 视频。"

    font_path = find_yahei_font()
    try:
        with tempfile.TemporaryDirectory(prefix="review_video_merge_") as work_dir:
            segment_paths = []
            for index, (entry, video_path) in enumerate(videos):
                line1, line2 = overlay_text_for_entry(entry)
                segment_path = os.path.join(work_dir, f"segment_{index:04d}.mp4")
                command = [
                    ffmpeg_path,
                    "-y",
                    "-i",
                    video_path,
                    "-vf",
                    build_overlay_filter(line1, line2, font_path),
                    "-c:v",
                    "libx264",
                    "-preset",
                    "veryfast",
                    "-crf",
                    "20",
                    "-c:a",
                    "aac",
                    "-b:a",
                    "160k",
                    "-movflags",
                    "+faststart",
                    segment_path,
                ]
                proc = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="ignore")
                if proc.returncode != 0:
                    return False, f"处理视频失败: {entry.get('shot_number', index)}\n{proc.stderr[-1200:]}"
                segment_paths.append(segment_path)

            concat_list = os.path.join(work_dir, "concat.txt")
            with open(concat_list, "w", encoding="utf-8") as f:
                for path in segment_paths:
                    safe_path = path.replace("\\", "/").replace("'", "'\\''")
                    f.write(f"file '{safe_path}'\n")

            os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
            concat_command = [
                ffmpeg_path,
                "-y",
                "-f",
                "concat",
                "-safe",
                "0",
                "-i",
                concat_list,
                "-c",
                "copy",
                output_path,
            ]
            proc = subprocess.run(concat_command, capture_output=True, text=True, encoding="utf-8", errors="ignore")
            if proc.returncode != 0:
                return False, f"合并视频失败:\n{proc.stderr[-1200:]}"
    except Exception as exc:
        return False, f"合并视频时发生错误: {exc}"

    skipped_msg = f"，跳过 {len(skipped)} 条无视频记录: {', '.join(skipped[:8])}" if skipped else ""
    return True, f"{output_path}{skipped_msg}"
