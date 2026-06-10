# -*- coding: utf-8 -*-
import os
import json
import shutil
import zipfile
import re
import copy
import time
from collections import defaultdict
from PySide6.QtWidgets import QMessageBox
from PySide6.QtCore import QEvent

VIDEO_EXTENSIONS = (".mp4", ".mov", ".mkv", ".avi", ".webm")
ASSET_ROOTS = ("snapshots", "recordings", "audio", "reference")
PROJECT_STATUS_EVENT_TYPE = QEvent.Type(QEvent.User + 6)

class CustomEvent(QEvent):
    def __init__(self, data, event_type):
        super().__init__(event_type)
        self.data = data

class ProjectManager:
    def __init__(self, main_window):
        self.main_window = main_window
        self.review_entries = []
        self.current_project_file = None
        self.current_temp_dir = None
        self.source_revpack_collection = []
        self.undo_stack = []
        self.redo_stack = []

    def _snapshot_state(self, action_name):
        # For simplicity, we'll snapshot the entire review_entries list.
        # For larger projects, a more granular diff/patch approach would be better.
        snapshot = {
            "action": action_name,
            "entries": copy.deepcopy(self.review_entries)
        }
        self.undo_stack.append(snapshot)
        self.redo_stack.clear() # Any new action clears the redo stack
        self.main_window.undo_action.setEnabled(True)
        self.main_window.redo_action.setEnabled(False)

    def undo(self):
        if len(self.undo_stack) > 1: # Keep at least one state (the initial one)
            current_state = self.undo_stack.pop()
            self.redo_stack.append(current_state)
            
            previous_state = self.undo_stack[-1]
            self.review_entries = copy.deepcopy(previous_state["entries"])
            
            self.main_window.project_manager.update_table_display()
            self.main_window.undo_action.setEnabled(len(self.undo_stack) > 1)
            self.main_window.redo_action.setEnabled(True)

    def redo(self):
        if self.redo_stack:
            next_state = self.redo_stack.pop()
            self.undo_stack.append(next_state)
            
            self.review_entries = copy.deepcopy(next_state["entries"])
            
            self.main_window.project_manager.update_table_display()
            self.main_window.redo_action.setEnabled(bool(self.redo_stack))
            self.main_window.undo_action.setEnabled(True)

    def new_project(self):
        self._snapshot_state("New Project")
        self.review_entries.clear()
        self.current_project_file = None
        self.current_temp_dir = None
        self.source_revpack_collection = []
        self.update_table_display()
        self.main_window.setWindowTitle("协同审阅平台 v3.0 (Faster-Whisper) - 未命名项目*")

    def save_project(self, file_path=None, autosave=False):
        if not file_path:
            file_path = self.current_project_file
        
        if not file_path:
            # This should be handled by the main window's save dialog
            return False, "未提供文件路径"

        self.current_project_file = file_path
        project_name = os.path.splitext(os.path.basename(file_path))[0]
        self.main_window.settings["project_name"] = project_name
        
        if not self.current_temp_dir:
            temp_dir_name = f"{project_name}_review_temp"
            # Place temp dir next to the project file or in a standard location
            temp_dir_path = os.path.join(os.path.dirname(file_path), temp_dir_name)
            self.current_temp_dir = temp_dir_path.replace('\\', '/')
            print(f"项目临时文件夹设置为: {self.current_temp_dir}")

        os.makedirs(self.current_temp_dir, exist_ok=True)

        project_data = {
            "settings": self.main_window.settings,
            "reviews": self.review_entries,
            "temp_dir_name": os.path.basename(self.current_temp_dir)
        }
        if self.source_revpack_collection:
            project_data["source_revpack_collection"] = self.source_revpack_collection
        
        try:
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(project_data, f, indent=4, ensure_ascii=False)
            
            if not autosave:
                self.main_window.statusBar().showMessage(f"项目已保存到 {file_path}", 3000)
                self.main_window.setWindowTitle(f"协同审阅平台 v3.0 (Faster-Whisper) - {project_name}")
            
            return True, "保存成功"
        except Exception as e:
            QMessageBox.critical(self.main_window, "保存失败", f"无法保存项目文件到 {file_path}.\n错误: {e}")
            return False, str(e)

    def load_project(self, file_path):
        self._snapshot_state("Load Project")
        if file_path.endswith(".revpack"):
            self.unpack_and_load_project(file_path)
            return

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                project_data = json.load(f)
            
            self.review_entries = project_data.get("reviews", [])
            # Compatibility: handle old list-based media_files
            for entry in self.review_entries:
                if isinstance(entry.get("media_files"), str):
                    entry["media_files"] = [entry["media_files"]]

            loaded_settings = project_data.get("settings", {})
            self.main_window.settings.update(loaded_settings)
            self.source_revpack_collection = project_data.get("source_revpack_collection", [])
            
            self.current_project_file = file_path
            project_name = loaded_settings.get("project_name", os.path.splitext(os.path.basename(file_path))[0])
            
            temp_dir_name = project_data.get("temp_dir_name")
            if temp_dir_name:
                self.current_temp_dir = os.path.join(os.path.dirname(file_path), temp_dir_name).replace('\\', '/')
            else: # Fallback for older projects
                self.current_temp_dir = os.path.join(os.path.dirname(file_path), f"{project_name}_review_temp").replace('\\', '/')
            self.current_temp_dir = self._resolve_loaded_temp_dir(file_path, project_name)

            self.main_window.setWindowTitle(f"协同审阅平台 v3.0 (Faster-Whisper) - {project_name}")
            self.main_window.statusBar().showMessage(f"项目 {project_name} 已加载", 3000)
            self.update_table_display()
            self._snapshot_state("After Load") # Set initial state for undo
        except Exception as e:
            QMessageBox.critical(self.main_window, "加载失败", f"无法加载项目文件: {file_path}.\n错误: {e}")

    def load_projects(self, file_paths):
        paths = [path for path in file_paths or [] if path]
        if not paths:
            return
        if len(paths) == 1:
            self.load_project(paths[0])
            return
        if any(not path.lower().endswith(".revpack") for path in paths):
            QMessageBox.warning(self.main_window, "暂不支持", "多文件合并导入当前只支持 .revpack 文件。")
            return
        self.load_revpack_collection(paths)

    def load_revpack_collection(self, pack_paths):
        self._snapshot_state("Load Revpack Collection")
        try:
            base_dir = os.path.dirname(pack_paths[0])
            collection_name = f"merged_review_{time.strftime('%Y%m%d_%H%M%S')}"
            collection_dir = os.path.join(base_dir, f"{collection_name}_temp")
            project_file = os.path.join(base_dir, f"{collection_name}.rev")
            os.makedirs(collection_dir, exist_ok=True)

            merged_entries = []
            package_names = []
            for index, pack_path in enumerate(pack_paths, 1):
                package_stem = self._sanitize_filename(os.path.splitext(os.path.basename(pack_path))[0])
                package_dir_name = f"{index:03d}_{package_stem}"
                package_dir = os.path.join(collection_dir, package_dir_name)
                if os.path.exists(package_dir):
                    shutil.rmtree(package_dir)
                os.makedirs(package_dir, exist_ok=True)

                with zipfile.ZipFile(pack_path, "r") as zf:
                    zf.extractall(package_dir)

                project_file_path = self._find_rev_file(package_dir)
                if not project_file_path:
                    raise FileNotFoundError(f"在 {pack_path} 中未找到 .rev 项目文件。")
                with open(project_file_path, "r", encoding="utf-8") as f:
                    project_data = json.load(f)

                settings = project_data.get("settings", {})
                package_name = settings.get("project_name") or os.path.splitext(os.path.basename(pack_path))[0]
                package_names.append(package_name)
                package_root = self._resolve_project_temp_dir(
                    project_file_path,
                    package_name,
                    project_data.get("temp_dir_name"),
                )
                package_prefix = os.path.relpath(package_root, collection_dir).replace(os.sep, "/")
                entries = project_data.get("reviews", [])
                for entry_index, entry in enumerate(entries):
                    if isinstance(entry.get("media_files"), str):
                        entry["media_files"] = [entry["media_files"]]
                    self._prefix_entry_paths(entry, package_prefix)
                    entry.setdefault("reference_files", [])
                    entry["source_revpack"] = os.path.basename(pack_path)
                    entry["source_project"] = package_name
                    entry["source_entry_index"] = entry_index
                    merged_entries.append(entry)

            self.review_entries = merged_entries
            self.current_project_file = project_file
            self.current_temp_dir = collection_dir.replace("\\", "/")
            self.source_revpack_collection = [os.path.abspath(path) for path in pack_paths]
            self.main_window.settings["project_name"] = collection_name
            project_data = {
                "settings": self.main_window.settings,
                "reviews": self.review_entries,
                "temp_dir_name": os.path.basename(self.current_temp_dir),
                "source_revpack_collection": self.source_revpack_collection,
            }
            with open(project_file, "w", encoding="utf-8") as f:
                json.dump(project_data, f, indent=4, ensure_ascii=False)

            self.main_window.setWindowTitle(f"协同审阅平台 v3.0 - {collection_name}")
            self.main_window.statusBar().showMessage(
                f"已合并加载 {len(pack_paths)} 个 revpack，{len(merged_entries)} 条记录", 5000
            )
            self.update_table_display()
            self._snapshot_state("After Load Revpack Collection")
        except Exception as e:
            QMessageBox.critical(self.main_window, "合并加载失败", f"无法合并加载 revpack:\n{e}")

    def append_revpack_collection(self, pack_paths):
        paths = [path for path in pack_paths or [] if path and path.lower().endswith(".revpack")]
        if not paths:
            return
        if not self.current_project_file or not self.current_temp_dir:
            self.load_revpack_collection(paths)
            return
        self._snapshot_state("Append Revpack Collection")
        try:
            os.makedirs(self.current_temp_dir, exist_ok=True)
            existing_dirs = [
                name for name in os.listdir(self.current_temp_dir)
                if os.path.isdir(os.path.join(self.current_temp_dir, name)) and re.match(r"^\d{3}_", name)
            ]
            next_index = max([int(name[:3]) for name in existing_dirs] or [0]) + 1
            added_entries = []
            for offset, pack_path in enumerate(paths):
                index = next_index + offset
                package_stem = self._sanitize_filename(os.path.splitext(os.path.basename(pack_path))[0])
                package_dir_name = f"{index:03d}_{package_stem}"
                package_dir = os.path.join(self.current_temp_dir, package_dir_name)
                if os.path.exists(package_dir):
                    shutil.rmtree(package_dir)
                os.makedirs(package_dir, exist_ok=True)
                with zipfile.ZipFile(pack_path, "r") as zf:
                    zf.extractall(package_dir)
                project_file_path = self._find_rev_file(package_dir)
                if not project_file_path:
                    raise FileNotFoundError(f"在 {pack_path} 中未找到 .rev 项目文件。")
                with open(project_file_path, "r", encoding="utf-8") as f:
                    project_data = json.load(f)
                settings = project_data.get("settings", {})
                package_name = settings.get("project_name") or os.path.splitext(os.path.basename(pack_path))[0]
                package_root = self._resolve_project_temp_dir(
                    project_file_path,
                    package_name,
                    project_data.get("temp_dir_name"),
                )
                package_prefix = os.path.relpath(package_root, self.current_temp_dir).replace(os.sep, "/")
                for entry_index, entry in enumerate(project_data.get("reviews", [])):
                    if isinstance(entry.get("media_files"), str):
                        entry["media_files"] = [entry["media_files"]]
                    self._prefix_entry_paths(entry, package_prefix)
                    entry.setdefault("reference_files", [])
                    entry["source_revpack"] = os.path.basename(pack_path)
                    entry["source_project"] = package_name
                    entry["source_entry_index"] = entry_index
                    added_entries.append(entry)
                self.source_revpack_collection.append(os.path.abspath(pack_path))
            self.review_entries.extend(added_entries)
            self.save_project(autosave=True)
            self.update_table_display()
            self.main_window.statusBar().showMessage(f"已追加导入 {len(paths)} 个 revpack，新增 {len(added_entries)} 条记录", 5000)
            self._snapshot_state("After Append Revpack Collection")
        except Exception as e:
            QMessageBox.critical(self.main_window, "追加导入失败", f"无法追加导入 revpack:\n{e}")

    def _find_rev_file(self, root_dir):
        for root, _, files in os.walk(root_dir):
            for file in files:
                if file.endswith(".rev"):
                    return os.path.join(root, file)
        return None

    def _prefix_entry_paths(self, entry, package_prefix):
        for field in ("screenshot_path", "original_screenshot_path", "audio_path", "source_video"):
            entry[field] = self._prefixed_rel_path(entry.get(field), package_prefix)
        for field in ("media_files", "reference_files", "pending_reference_files"):
            values = entry.get(field)
            if isinstance(values, str):
                values = [values]
            if isinstance(values, list):
                entry[field] = [self._prefixed_rel_path(value, package_prefix) for value in values if value]

    def _prefixed_rel_path(self, value, package_prefix):
        if not value:
            return value
        normalized = str(value).replace("\\", "/").lstrip("/")
        if os.path.isabs(str(value)):
            return normalized
        if package_prefix in ("", "."):
            return normalized
        if normalized.startswith(f"{package_prefix}/"):
            return normalized
        return f"{package_prefix}/{normalized}"

    def update_shot_number_and_move_files(self, row, new_shot_number):
        if not (0 <= row < len(self.review_entries)):
            return
        
        entry = self.review_entries[row]
        old_shot_number = entry.get("shot_number", "UNASSIGNED")
        
        if new_shot_number == old_shot_number:
            return

        self._snapshot_state("Update Shot Number")
        entry["shot_number"] = new_shot_number
        
        if not self.current_temp_dir:
            print("WARNING: No temp dir set, cannot move files.")
            return

        old_sane_name = self._sanitize_filename(old_shot_number)
        new_sane_name = self._sanitize_filename(new_shot_number)

        # Move associated files
        for key in ["screenshot_path", "audio_path", "media_files", "reference_files"]:
            paths = entry.get(key)
            if not paths:
                continue
            
            is_list = isinstance(paths, list)
            if not is_list:
                paths = [paths]

            new_paths = []
            for rel_path in paths:
                normalized_rel_path = str(rel_path).replace('\\', '/')
                asset_path = self._split_managed_asset_path(normalized_rel_path)
                rename_feedback_video = (
                    key == "media_files"
                    and self._entry_uses_feedback_video_names(entry)
                    and self._is_video_file(normalized_rel_path)
                )
                should_move_shot_folder = (
                    asset_path
                    and old_sane_name != new_sane_name
                    and asset_path["shot_folder"] == old_sane_name
                )
                should_rename_feedback_video = (
                    asset_path
                    and asset_path["asset_type"] == "recordings"
                    and rename_feedback_video
                )

                if should_move_shot_folder or should_rename_feedback_video:
                    new_filename = (
                        self.feedback_video_filename(new_shot_number, normalized_rel_path)
                        if should_rename_feedback_video
                        else asset_path["filename"]
                    )
                    new_rel_path = self._join_asset_path(
                        asset_path["prefix"],
                        asset_path["asset_type"],
                        new_sane_name if should_move_shot_folder else asset_path["shot_folder"],
                        new_filename,
                    )
                    old_abs_path = self.resolve_existing_temp_path(normalized_rel_path)
                    new_abs_path = os.path.join(self.current_temp_dir, new_rel_path)
                    new_abs_path = self._unique_destination_path(new_abs_path, old_abs_path)
                    new_rel_path = os.path.relpath(new_abs_path, self.current_temp_dir).replace(os.sep, '/')

                    if old_abs_path and os.path.abspath(old_abs_path) == os.path.abspath(new_abs_path):
                        new_paths.append(new_rel_path)
                        continue

                    if old_abs_path and os.path.exists(old_abs_path):
                        os.makedirs(os.path.dirname(new_abs_path), exist_ok=True)
                        try:
                            shutil.move(old_abs_path, new_abs_path)
                            new_paths.append(new_rel_path)
                            print(f"Moved {old_abs_path} to {new_abs_path}")
                        except Exception as e:
                            print(f"Error moving file: {e}")
                            new_paths.append(normalized_rel_path) # Keep old path if move fails
                    else:
                        new_paths.append(normalized_rel_path) # Keep old path if it doesn't exist
                else:
                    new_paths.append(normalized_rel_path) # Path doesn't match expected structure
            
            entry[key] = new_paths if is_list else new_paths[0]

        self.save_project(autosave=True)
        self.update_table_display()


    def add_review_entry(self, entry_data):
        self._snapshot_state("Add Entry")
        self.review_entries.append(entry_data)
        self.update_table_display()

    def insert_blank_entry(self, row_index=None):
        self._snapshot_state("Insert Blank Entry")
        if row_index is None:
            row_index = len(self.review_entries)
        row_index = max(0, min(int(row_index), len(self.review_entries)))
        entry_data = {
            "entry_type": "manual",
            "shot_number": "",
            "timestamp": "",
            "screenshot_path": None,
            "original_screenshot_path": None,
            "audio_path": None,
            "media_files": [],
            "reference_files": [],
            "full_review": "",
            "simplified_review": "",
            "keywords": [],
            "department": "未分类",
        }
        self.review_entries.insert(row_index, entry_data)
        self.update_table_display()
        return row_index

    def remove_review_entry(self, row):
        if 0 <= row < len(self.review_entries):
            self._snapshot_state("Remove Entry")
            del self.review_entries[row]
            self.update_table_display()

    def update_entry(self, row, update_data, snapshot_action=None):
        if 0 <= row < len(self.review_entries):
            if snapshot_action:
                self._snapshot_state(snapshot_action)
            self.review_entries[row].update(update_data)
            self.main_window.populate_row(row, self.review_entries[row])
            if hasattr(self.main_window, "refresh_views"):
                self.main_window.refresh_views()

    def add_reference_file(self, row, file_paths):
        if 0 <= row < len(self.review_entries):
            self._snapshot_state("Add Reference")
            if "reference_files" not in self.review_entries[row]:
                self.review_entries[row]["reference_files"] = []
            self.review_entries[row]["reference_files"].extend(file_paths)
            self.main_window.update_reference_cell(row)
            if hasattr(self.main_window, "refresh_views"):
                self.main_window.refresh_views()

    def merge_duplicate_shots(self):
        grouped = defaultdict(list);
        for idx, entry in enumerate(self.review_entries):
            shot = entry.get("shot_number", "").strip()
            if shot and shot not in ["未识别", "OCR失败", "UNASSIGNED"]: grouped[shot].append((idx, entry))
        
        merged_count = 0; indices_to_delete = []
        ignore_phrases = ["（音频中未识别到有效语音）", "（转录失败）"]

        for shot, items in grouped.items():
            if len(items) > 1:
                items.sort(key=lambda x: x[1].get("timestamp", "")); main_idx, main_entry = items[0]
                valid_reviews = []
                if main_entry.get("full_review") and not any(phrase in main_entry["full_review"] for phrase in ignore_phrases):
                    valid_reviews.append(main_entry["full_review"])
                
                for other_idx, other_entry in items[1:]:
                    if other_entry.get("full_review") and not any(phrase in other_entry["full_review"] for phrase in ignore_phrases):
                        valid_reviews.append(other_entry["full_review"])
                    main_entry.setdefault("media_files", []).extend(other_entry.get("media_files", []))
                    indices_to_delete.append(other_idx); merged_count += 1
                
                main_entry["full_review"] = "\n".join([f"{i+1}. {review}" for i, review in enumerate(valid_reviews)])

        if merged_count > 0:
            indices_to_delete.sort(reverse=True)
            for idx in indices_to_delete: self.review_entries.pop(idx)
            self.update_table_display()
        return merged_count

    def get_entry_count(self):
        return len(self.review_entries)

    def update_table_display(self):
        self.main_window.review_table.setRowCount(0)
        self.main_window.review_table.setRowCount(len(self.review_entries))
        for i, entry in enumerate(self.review_entries):
            self.main_window.populate_row(i, entry)
        if hasattr(self.main_window, "apply_saved_table_layout"):
            self.main_window.apply_saved_table_layout()
        if hasattr(self.main_window, "refresh_views"):
            self.main_window.refresh_views()

    def _sanitize_filename(self, filename):
        # Basic sanitization for folder names
        return re.sub(r'[\\/:*?"<>|]', '_', filename.strip()) if filename else "UNASSIGNED"

    def resolve_existing_temp_path(self, relative_path):
        if not relative_path or os.path.isabs(str(relative_path)):
            return relative_path
        if not self.current_temp_dir:
            return None

        normalized = str(relative_path).replace('\\', '/')
        exact_path = os.path.join(self.current_temp_dir, normalized.replace('/', os.sep))
        if os.path.exists(exact_path):
            return exact_path

        basename = os.path.basename(normalized)
        matches = []
        for root, _, files in os.walk(self.current_temp_dir):
            if basename in files:
                matches.append(os.path.join(root, basename))
                if len(matches) > 1:
                    break
        if len(matches) == 1:
            return matches[0]

        asset_path = self._split_managed_asset_path(normalized)
        if not asset_path:
            return exact_path
        folder = os.path.join(
            self.current_temp_dir,
            self._join_asset_path(asset_path["prefix"], asset_path["asset_type"], asset_path["shot_folder"], "").replace('/', os.sep),
        )
        if not os.path.isdir(folder):
            return exact_path
        _, ext = os.path.splitext(basename)
        sibling_matches = [
            os.path.join(folder, name)
            for name in os.listdir(folder)
            if os.path.isfile(os.path.join(folder, name)) and (not ext or os.path.splitext(name)[1].lower() == ext.lower())
        ]
        if asset_path["asset_type"] == "recordings":
            sibling_matches = [path for path in sibling_matches if self._is_video_file(path)]
        return sibling_matches[0] if len(sibling_matches) == 1 else exact_path

    def _is_video_file(self, path):
        return os.path.splitext(str(path).lower())[1] in VIDEO_EXTENSIONS

    def _entry_uses_feedback_video_names(self, entry):
        return not str(entry.get("entry_type", "")).startswith("long_video")

    def feedback_video_filename(self, shot_number, source_path):
        safe_shot = self._sanitize_filename(str(shot_number or "UNASSIGNED"))
        _, ext = os.path.splitext(str(source_path))
        ext = ext or ".mp4"
        return f"{safe_shot}_反馈_{self._feedback_stamp_for_path(source_path)}{ext}"

    def _feedback_stamp_for_path(self, path):
        basename = os.path.basename(str(path).replace('\\', '/'))
        match = re.search(r"_反馈_(\d{8}(?:_\d{6})?)", basename)
        if match:
            return match.group(1)
        abs_path = str(path)
        if not os.path.isabs(abs_path) and self.current_temp_dir:
            abs_path = os.path.join(self.current_temp_dir, str(path).replace('/', os.sep))
        try:
            timestamp = os.path.getmtime(abs_path)
        except OSError:
            timestamp = time.time()
        return time.strftime("%Y%m%d_%H%M%S", time.localtime(timestamp))

    def _split_managed_asset_path(self, rel_path):
        parts = str(rel_path).replace('\\', '/').split('/')
        for index, part in enumerate(parts):
            if part in ASSET_ROOTS and len(parts) >= index + 3:
                return {
                    "prefix": parts[:index],
                    "asset_type": part,
                    "shot_folder": parts[index + 1],
                    "filename": parts[-1],
                }
        return None

    def _join_asset_path(self, prefix, asset_type, shot_folder, filename):
        return "/".join([part for part in [*prefix, asset_type, shot_folder, filename] if part])

    def _unique_destination_path(self, dest_path, source_path=None):
        if source_path and os.path.abspath(dest_path) == os.path.abspath(source_path):
            return dest_path
        if not os.path.exists(dest_path):
            return dest_path
        root, ext = os.path.splitext(dest_path)
        counter = 2
        while True:
            candidate = f"{root}_{counter}{ext}"
            if source_path and os.path.abspath(candidate) == os.path.abspath(source_path):
                return candidate
            if not os.path.exists(candidate):
                return candidate
            counter += 1

    def _resolve_project_temp_dir(self, project_file_path, project_name, temp_dir_name=None, preferred_temp_dir=None):
        project_dir = os.path.dirname(project_file_path)
        if preferred_temp_dir and os.path.isdir(preferred_temp_dir):
            return preferred_temp_dir

        # Older .revpack files place asset folders directly beside the extracted
        # .rev, while the .rev still records the original temp_dir_name.
        resource_roots = ("snapshots", "recordings", "audio", "reference")
        if any(os.path.isdir(os.path.join(project_dir, root)) for root in resource_roots):
            return project_dir.replace('\\', '/')

        if temp_dir_name:
            recorded_temp_dir = os.path.join(project_dir, temp_dir_name).replace('\\', '/')
            if os.path.isdir(recorded_temp_dir):
                return recorded_temp_dir

        fallback = os.path.join(project_dir, f"{project_name}_review_temp").replace('\\', '/')
        if os.path.isdir(fallback):
            return fallback
        return fallback.replace('\\', '/')

    def _resolve_loaded_temp_dir(self, project_file_path, project_name):
        return self._resolve_project_temp_dir(
            project_file_path,
            project_name,
            preferred_temp_dir=self.current_temp_dir,
        )

    def do_pack_project(self, save_path):
        if not self.current_temp_dir or not os.path.isdir(self.current_temp_dir):
            return False, "错误: 找不到项目临时文件夹。请先保存项目。"

        # 1. Save the current project file to ensure it's up-to-date
        self.save_project(self.current_project_file)

        # 2. Create the zip file
        try:
            with zipfile.ZipFile(save_path, 'w', zipfile.ZIP_DEFLATED) as zf:
                # Add the project file itself
                zf.write(self.current_project_file, os.path.basename(self.current_project_file))
                
                # Walk through the temp directory and add all files
                for root, _, files in os.walk(self.current_temp_dir):
                    for file in files:
                        file_path = os.path.join(root, file)
                        # Arcname is the path inside the zip file
                        arcname = os.path.relpath(file_path, self.current_temp_dir)
                        zf.write(file_path, arcname)
            return True, save_path
        except Exception as e:
            return False, f"创建压缩包时出错: {e}"

    def unpack_and_load_project(self, pack_path):
        try:
            extract_dir = os.path.splitext(pack_path)[0] + "_unpacked"
            if os.path.exists(extract_dir):
                reply = QMessageBox.question(self.main_window, "目录已存在", 
                                             f"解包目录 '{extract_dir}' 已存在.\n是否要删除它并重新解包？",
                                             QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
                if reply == QMessageBox.Yes:
                    shutil.rmtree(extract_dir)
                else:
                    return # User cancelled

            os.makedirs(extract_dir, exist_ok=True)

            with zipfile.ZipFile(pack_path, 'r') as zf:
                zf.extractall(extract_dir)

            # Find the .rev file in the unpacked directory
            project_file_path = None
            for root, _, files in os.walk(extract_dir):
                for file in files:
                    if file.endswith(".rev"):
                        project_file_path = os.path.join(root, file)
                        break
                if project_file_path:
                    break
            if not project_file_path:
                raise FileNotFoundError("在压缩包中未找到 .rev 项目文件。")

            self.load_project(project_file_path)

        except Exception as e:
            QMessageBox.critical(self.main_window, "解包失败", f"无法解包或加载项目: {e}")
