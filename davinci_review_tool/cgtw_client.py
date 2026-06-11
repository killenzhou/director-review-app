# -*- coding: utf-8 -*-
import json
import os
import subprocess
import sys
import tempfile

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from app_constants import DEFAULT_DEPARTMENTS
from cgtw_sync import (
    APPROVED_CGTW_STATUS,
    DEFAULT_CGTW_BASE_PATH,
    _last_json_line,
    choose_python_executable,
    get_cgtw_settings,
    run_cgtw_sync,
    validate_cgtw_settings,
)


CHECK_STATUSES = ["待审核", "待Check", "需要check", "Check"]
VFX_PIPELINES = {"UE_FX", "Effect", "AE"}


def load_app_settings(base_dir=None):
    base_dir = base_dir or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    settings_path = os.path.join(base_dir, "settings.json")
    try:
        with open(settings_path, "r", encoding="utf-8") as f:
            settings = json.load(f)
    except Exception:
        settings = {}
    settings["departments"] = DEFAULT_DEPARTMENTS.copy()
    return settings


class CgtwClient:
    def __init__(self, settings=None, temp_dir=None):
        self.settings = settings or load_app_settings()
        self.settings["departments"] = DEFAULT_DEPARTMENTS.copy()
        self.temp_dir = temp_dir or tempfile.gettempdir()

    def public_status(self):
        config = get_cgtw_settings(self.settings)
        errors = validate_cgtw_settings(config, require_runtime=False)
        return {
            "ok": not errors,
            "db": config.get("db", ""),
            "module": config.get("module", "shot"),
            "errors": errors,
        }

    def approve_shot_from_resolve(self, shot_number, department="AUTO_DISCOVER"):
        entry_department = "未分类" if department in ("", "AUTO_DISCOVER", None) else department
        entry = {
            "entry_type": "davinci_approve",
            "shot_number": shot_number,
            "full_review": "通过",
            "simplified_review": "通过",
            "keywords": ["通过"],
            "department": entry_department,
            "approved": True,
            "reference_files": [],
            "media_files": [],
        }
        return run_cgtw_sync([entry], self.temp_dir, self.settings, force_dry_run=False)

    def submit_retake_from_resolve(self, entry):
        payload = dict(entry or {})
        payload.setdefault("entry_type", "davinci_retake")
        payload.setdefault("approved", False)
        payload.setdefault("department", "未分类")
        payload.setdefault("keywords", [])
        payload.setdefault("reference_files", [])
        payload.setdefault("media_files", [])
        return run_cgtw_sync([payload], self.temp_dir, self.settings, force_dry_run=False)

    def list_check_tasks(self, episode):
        result = self._run_query_worker({"action": "list_check_tasks", "episode": episode})
        if not result.get("ok"):
            raise RuntimeError(result.get("error") or "查询待 Check 列表失败")
        return result.get("tasks", [])

    def get_shot_status(self, shot_number):
        result = self._run_query_worker({"action": "get_shot_status", "shot_number": shot_number})
        if not result.get("ok"):
            raise RuntimeError(result.get("error") or "查询镜头状态失败")
        return result.get("tasks", [])

    def _run_query_worker(self, payload):
        config = get_cgtw_settings(self.settings)
        errors = validate_cgtw_settings(config, require_runtime=True)
        if errors:
            return {"ok": False, "error": "\n".join(errors)}
        python_path = choose_python_executable(config)
        fd, payload_path = tempfile.mkstemp(prefix="davinci_cgtw_query_", suffix=".json")
        os.close(fd)
        try:
            with open(payload_path, "w", encoding="utf-8") as f:
                json.dump({"config": config, "payload": payload}, f, ensure_ascii=False, indent=2)
            cmd = [python_path, os.path.abspath(__file__), "--worker", payload_path]
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=int(config.get("timeout_seconds") or 600),
                env=self._worker_env(config),
            )
            stdout = (proc.stdout or "").strip()
            stderr = (proc.stderr or "").strip()
            if proc.returncode != 0:
                return {"ok": False, "error": stderr or stdout or f"CGT 查询进程退出码: {proc.returncode}"}
            return json.loads(_last_json_line(stdout))
        except Exception as exc:
            return {"ok": False, "error": str(exc)}
        finally:
            try:
                os.remove(payload_path)
            except OSError:
                pass

    def _worker_env(self, config):
        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"
        python_path = choose_python_executable(config)
        if python_path:
            env["PYTHONHOME"] = os.path.dirname(python_path)
        env["PYTHONNOUSERSITE"] = "1"
        env.pop("PYTHONPATH", None)
        return env


def _task_value(row, *keys):
    for key in keys:
        value = row.get(key)
        if value not in (None, ""):
            return value
    return ""


def _normalize_worker_task(row, shot_field):
    shot = _task_value(row, shot_field, "shot.entity", "task.entity", "etask.url")
    return {
        "task_id": str(_task_value(row, "task.id", "id")),
        "shot_number": str(shot or ""),
        "pipeline": str(_task_value(row, "pipeline.entity", "task.pipeline")),
        "supervise_status": str(_task_value(row, "task.supervise_status")),
        "task_status": str(_task_value(row, "task.status")),
        "artist": str(_task_value(row, "task.account_id", "task.artist", "artist")),
        "updated_at": str(_task_value(row, "task.update_time", "task.last_update_time", "last_update_time")),
    }


def _worker(payload_path):
    with open(payload_path, "r", encoding="utf-8") as f:
        wrapper = json.load(f)
    config = wrapper["config"]
    payload = wrapper["payload"]
    base_path = config.get("base_path") or DEFAULT_CGTW_BASE_PATH
    if base_path not in sys.path:
        sys.path.insert(0, base_path)
    import cgtw2

    tw = cgtw2.tw()
    db = config["db"]
    module = config.get("module") or "shot"
    shot_field = config.get("shot_field") or "etask.url"
    fields = [
        "task.id",
        shot_field,
        "shot.entity",
        "pipeline.entity",
        "task.status",
        "task.supervise_status",
        "task.account_id",
        "task.update_time",
    ]
    action = payload.get("action")
    if action == "list_check_tasks":
        episode = str(payload.get("episode") or "").strip()
        if not episode:
            return {"ok": False, "error": "缺少集号，无法查询待 Check 列表"}
        filters = [[shot_field, config.get("shot_filter_operator") or "has", episode]]
        ids = tw.etask.get_id(db, filters, limit="5000")
    elif action == "get_shot_status":
        shot_number = str(payload.get("shot_number") or "").strip()
        if not shot_number:
            return {"ok": False, "error": "缺少镜头号，无法查询状态"}
        filters = [[shot_field, config.get("shot_filter_operator") or "has", shot_number]]
        ids = tw.etask.get_id(db, filters, limit="200")
    else:
        return {"ok": False, "error": f"未知查询动作: {action}"}

    if not ids:
        return {"ok": True, "tasks": []}
    rows = tw.task.get(db, module, ids, fields)
    tasks = [_normalize_worker_task(row, shot_field) for row in rows or []]
    if action == "list_check_tasks":
        statuses = {item.lower() for item in CHECK_STATUSES}
        tasks = [
            task for task in tasks
            if task.get("supervise_status", "").lower() in statuses
            and (not task.get("pipeline") or task.get("pipeline") in VFX_PIPELINES)
        ]
    return {"ok": True, "tasks": tasks}


def main(argv=None):
    argv = argv or sys.argv[1:]
    if len(argv) == 2 and argv[0] == "--worker":
        print(json.dumps(_worker(argv[1]), ensure_ascii=False))
        return 0
    print("This module is used by davinci_review_app.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
