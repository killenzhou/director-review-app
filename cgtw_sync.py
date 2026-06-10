# -*- coding: utf-8 -*-
import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
from datetime import datetime


DEFAULT_CGTW_BASE_PATH = r"D:\CgTeamWork_v7\bin\base"
DEFAULT_CGTW_PYTHON_PATH = r"D:\CgTeamWork_v7\python\py3\python.exe"
SUPPORTED_CGTW_PYTHON = {
    (2, 7),
    (3, 7),
    (3, 9),
    (3, 10),
    (3, 11),
    (3, 12),
}
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".bmp", ".gif", ".webp", ".tif", ".tiff"}


def default_cgtw_settings():
    return {
        "enabled": True,
        "dry_run": False,
        "base_path": DEFAULT_CGTW_BASE_PATH,
        "python_path": DEFAULT_CGTW_PYTHON_PATH if os.path.isfile(DEFAULT_CGTW_PYTHON_PATH) else r"D:\CgTeamWork_v7\python\py3\python.exe",
        "db": "proj_ssdsy_cs",
        "module": "shot",
        "module_type": "task",
        "target_api": "etask",
        "shot_field": "etask.url",
        "shot_filter_operator": "has",
        "task_name_field": "pipeline.entity",
        "task_name": "UE_FX",
        "department_pipeline_map": {
            "解算": "Cache",
            "动画": "Animation",
            "合成": "Comp",
            "灯光": "Comp",
            "特效": "AUTO_RESOLVE_FX",
            "UE特效": "UE_FX",
            "传统特效": "Effect",
            "调色": "TC",
            "AE": "AE",
            "AI": "AI",
            "组装": "AAI",
            "地编": "TE",
        },
        "filebox_sign": "review",
        "filebox_id": "",
        "sync_mode": "field",
        "flow_field_sign": "task.supervise_status",
        "flow_status": "内部返修",
        "sync_note": True,       # 必须为 True: 同步文本修改意见
        "submit_review": True,   # 必须为 True: 上传参考图/视频到审核文件框
        "upload_filebox": False,
        "update_status": False,
        "target_status": "",
        "cc_account_id": "",
        "timeout_seconds": 600,
    }


def get_cgtw_settings(settings):
    # 强制返回写死的默认配置，忽略本地可能存错的配置，防止被意外修改
    merged = default_cgtw_settings()
    if str(merged.get("target_api") or "").lower() == "etask":
        shot_field = str(merged.get("shot_field") or "").strip()
        if shot_field in {"", "shot.entity", "task.entity"}:
            merged["shot_field"] = "etask.url"
            merged["shot_filter_operator"] = "has"
        task_name_field = str(merged.get("task_name_field") or "").strip()
        if task_name_field in {"", "task.entity"}:
            merged["task_name_field"] = "pipeline.entity"
    if str(merged.get("sync_mode") or "").lower() == "flow" and not str(merged.get("flow_status") or "").strip():
        merged["flow_status"] = "内部返修"
    if not merged.get("python_path") and os.path.isfile(DEFAULT_CGTW_PYTHON_PATH):
        merged["python_path"] = DEFAULT_CGTW_PYTHON_PATH
    if not merged.get("db"):
        discovered = discover_cgtw_context(merged)
        if discovered.get("db"):
            merged["db"] = discovered["db"]
    return merged


def validate_cgtw_settings(config, require_runtime=False):
    errors = []
    if not config.get("db"):
        errors.append("未配置 CGTeamWork 数据库名(db)。")
    if not config.get("module"):
        errors.append("未配置 CGTeamWork 模块名(module)。")
    if not config.get("shot_field"):
        errors.append("未配置镜头号字段标识。")
    base_path = config.get("base_path") or DEFAULT_CGTW_BASE_PATH
    cgtw2_path = os.path.join(base_path, "cgtw2.py")
    if require_runtime and not os.path.isfile(cgtw2_path):
        errors.append("未找到 cgtw2.py，请检查 CGTeamWork API 路径。")
    if require_runtime:
        python_path = choose_python_executable(config)
        if not python_path:
            errors.append("当前 Python 版本不兼容 cgtw2.py，请配置 Python 3.7/3.9/3.10/3.11/3.12 可执行文件。")
    return errors


def choose_python_executable(config):
    configured = str(config.get("python_path") or "").strip()
    if configured and os.path.isfile(configured):
        return configured
    if os.path.isfile(DEFAULT_CGTW_PYTHON_PATH):
        return DEFAULT_CGTW_PYTHON_PATH
    version_key = (sys.version_info.major, sys.version_info.minor)
    if version_key in SUPPORTED_CGTW_PYTHON and os.path.isfile(sys.executable):
        return sys.executable
    return ""


def discover_cgtw_context(config=None):
    config = config or {}
    python_path = choose_python_executable(config)
    base_path = config.get("base_path") or DEFAULT_CGTW_BASE_PATH
    if not python_path or not os.path.isfile(os.path.join(base_path, "cgtw2.py")):
        return {}

    script = r"""
import json, sys, traceback
sys.path.insert(0, r'%s')
try:
    import cgtw2
    tw = cgtw2.tw()
    data = {
        'login': tw.login.is_login(),
        'account': tw.login.account() if tw.login.is_login() else '',
        'server': tw.login.http_server_ip() if tw.login.is_login() else '',
        'client_db': tw.client.get_database(),
        'client_module': tw.client.get_module(),
        'client_module_type': tw.client.get_module_type(),
        'projects': tw.project.get_filter(['project.entity','project.database','project.status'], [['project.status','!=','Close']], limit='20'),
    }
    active = [p for p in data.get('projects') or [] if p.get('project.status') == 'Active' and p.get('project.database')]
    if data.get('client_db'):
        data['db'] = data['client_db']
    elif len(active) == 1:
        data['db'] = active[0].get('project.database')
        data['project'] = active[0].get('project.entity')
    print(json.dumps(data, ensure_ascii=False))
except Exception as exc:
    print(json.dumps({'error': str(exc)}, ensure_ascii=False))
""" % base_path.replace("\\", "\\\\")
    try:
        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"
        # 强制隔离 Python 环境，防止系统 Python 3.13 标准库污染 CGTeamWork Python 3.7
        cgtw_python_home = os.path.dirname(python_path)
        env["PYTHONHOME"] = cgtw_python_home
        env["PYTHONNOUSERSITE"] = "1"
        env.pop("PYTHONPATH", None)
        proc = subprocess.run(
            [python_path, "-c", script],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=20,
            env=env,
        )
        if proc.returncode != 0:
            _err = (proc.stderr or proc.stdout or "").strip()
            print(f"[cgtw_sync] discover 子进程失败 (rc={proc.returncode}): {_err[:300]}")
            return {"error": _err or f"exit code {proc.returncode}"}
        return json.loads(_last_json_line(proc.stdout.strip()))
    except Exception as exc:
        print(f"[cgtw_sync] discover 异常: {exc}")
        return {"error": str(exc)}


def prepare_cgtw_payload(review_entries, temp_dir, settings):
    config = get_cgtw_settings(settings)
    items = []
    skipped = []

    for index, entry in enumerate(review_entries):
        shot_number = str(entry.get("shot_number") or "").strip()
        if not shot_number or shot_number in {"UNASSIGNED", "OCR_FAILED", "未识别", "OCR失败"}:
            skipped.append({"row": index + 1, "reason": "缺少有效镜头号"})
            continue

        full_review = str(entry.get("full_review") or "").strip()
        simplified_review = str(entry.get("simplified_review") or "").strip()
        if not full_review and not simplified_review:
            skipped.append({"row": index + 1, "shot_number": shot_number, "reason": "没有反馈意见"})
            continue

        is_approved = "通过" in full_review or "通过" in simplified_review

        screenshot_path = _resolve_path(entry.get("screenshot_path"), temp_dir)
        reference_paths = [_resolve_path(path, temp_dir) for path in _ensure_list(entry.get("reference_files"))]
        media_paths = [_resolve_path(path, temp_dir) for path in _ensure_list(entry.get("media_files"))]

        all_paths = []
        if screenshot_path:
            all_paths.append(screenshot_path)
        all_paths.extend(path for path in reference_paths if path)
        all_paths.extend(path for path in media_paths if path)
        # if audio_path:
        #     all_paths.append(audio_path)

        existing_paths = [path for path in all_paths if path and os.path.exists(path)]
        missing_paths = [path for path in all_paths if path and not os.path.exists(path)]
        image_paths = [path for path in existing_paths if _is_image(path)]
        attachment_paths = [path for path in existing_paths if path not in image_paths]

        note_blocks = _build_note_blocks(entry, shot_number, image_paths, attachment_paths)
        
        raw_dept = str(entry.get("department") or "")
        departments = [d.strip() for d in raw_dept.replace("，", ",").split(",") if d.strip()]
        if not departments:
            departments = [""]
            
        for dep in departments:
            temp_entry = dict(entry)
            temp_entry["department"] = dep
            if is_approved and dep == "未分类":
                temp_entry["department"] = "AUTO_DISCOVER"
            items.append({
                "row": index + 1,
                "shot_number": shot_number,
                "cgtw_shot_number": _normalize_cgtw_shot_number(shot_number),
                "filter": _build_task_filter(config, _normalize_cgtw_shot_number(shot_number), temp_entry),
                "note_blocks": note_blocks if not is_approved else [{"type": "text", "content": f"[协同审阅平台同步]\n镜头号: {shot_number}\n状态: 通过"}],
                "image_paths": image_paths if not is_approved else [],
                "submit_paths": existing_paths if not is_approved else [],
                "missing_paths": missing_paths if not is_approved else [],
                "is_approved": is_approved,
            })

    return {
        "config": config,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "summary": {
            "total_entries": len(review_entries),
            "ready": len(items),
            "skipped": len(skipped),
            "missing_files": sum(len(item["missing_paths"]) for item in items),
        },
        "items": items,
        "skipped": skipped,
    }


def summarize_payload(payload):
    summary = payload.get("summary", {})
    return (
        f"待同步 {summary.get('ready', 0)} 条，"
        f"跳过 {summary.get('skipped', 0)} 条，"
        f"缺失附件 {summary.get('missing_files', 0)} 个。"
    )


def run_cgtw_sync(review_entries, temp_dir, settings, force_dry_run=None):
    payload = prepare_cgtw_payload(review_entries, temp_dir, settings)
    config = payload["config"]
    dry_run = config.get("dry_run", True) if force_dry_run is None else bool(force_dry_run)
    if dry_run:
        return _dry_run_result(payload)

    errors = validate_cgtw_settings(config, require_runtime=True)
    if errors:
        return {
            "success": False,
            "dry_run": False,
            "message": "\n".join(errors),
            "payload": payload,
        }

    return _run_worker_subprocess(payload)


def _dry_run_result(payload):
    return {
        "success": True,
        "dry_run": True,
        "message": "CGTeamWork 模拟同步完成：" + summarize_payload(payload),
        "payload": payload,
        "results": [
            {
                "row": item["row"],
                "shot_number": item["shot_number"],
                "status": "ready",
                "filter": item["filter"],
                "sync_mode": payload.get("config", {}).get("sync_mode", "note"),
                "flow_field": payload.get("config", {}).get("flow_field_sign", ""),
                "flow_status": payload.get("config", {}).get("flow_status", ""),
                "files": len(item["submit_paths"]),
                "missing_files": len(item["missing_paths"]),
            }
            for item in payload["items"]
        ],
    }


def _run_worker_subprocess(payload):
    config = payload["config"]
    python_path = choose_python_executable(config)
    timeout = int(config.get("timeout_seconds") or 600)
    fd, payload_path = tempfile.mkstemp(prefix="cgtw_sync_", suffix=".json")
    os.close(fd)
    try:
        with open(payload_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        cmd = [python_path, os.path.abspath(__file__), "--worker", payload_path]
        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"
        # 强制隔离 Python 环境，防止系统 Python 3.13 标准库污染 CGTeamWork Python 3.7
        cgtw_python_home = os.path.dirname(python_path)
        env["PYTHONHOME"] = cgtw_python_home
        env["PYTHONNOUSERSITE"] = "1"
        env.pop("PYTHONPATH", None)
        proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout, env=env)
        stdout = (proc.stdout or "").strip()
        stderr = (proc.stderr or "").strip()
        if proc.returncode != 0:
            return {
                "success": False,
                "dry_run": False,
                "message": stderr or stdout or f"CGTeamWork 同步进程退出码: {proc.returncode}",
                "payload": payload,
            }
        try:
            return json.loads(_last_json_line(stdout))
        except json.JSONDecodeError:
            return {
                "success": False,
                "dry_run": False,
                "message": "CGTeamWork 同步进程返回了无法解析的结果。\n" + stdout,
                "payload": payload,
            }
    except Exception as exc:
        return {
            "success": False,
            "dry_run": False,
            "message": str(exc),
            "payload": payload,
        }
    finally:
        try:
            os.remove(payload_path)
        except OSError:
            pass


def _run_worker(payload_path):
    with open(payload_path, "r", encoding="utf-8") as f:
        payload = json.load(f)
    config = payload["config"]
    base_path = config.get("base_path") or DEFAULT_CGTW_BASE_PATH
    if base_path not in sys.path:
        sys.path.insert(0, base_path)
    import cgtw2

    tw = _login_cgtw(cgtw2, config)
    results = []
    for item in payload["items"]:
        result = _sync_one_item(tw, config, item)
        results.append(result)

    success_count = sum(1 for item in results if item.get("success"))
    failed_count = len(results) - success_count
    return {
        "success": failed_count == 0,
        "dry_run": False,
        "message": f"CGTeamWork 同步完成：成功 {success_count} 条，失败 {failed_count} 条。",
        "results": results,
        "payload_summary": payload.get("summary", {}),
    }


def _last_json_line(text):
    for line in reversed((text or "").splitlines()):
        line = line.strip()
        if line.startswith("{") and line.endswith("}"):
            return line
    return text


def _login_cgtw(cgtw2, config):
    http_ip = str(config.get("http_ip") or "").strip()
    account = str(config.get("account") or "").strip()
    password = str(config.get("password") or "").strip()
    token = str(config.get("token") or "").strip()
    api_key = str(config.get("api_key") or "").strip()
    if http_ip and token:
        return cgtw2.tw(http_ip=http_ip, token=token, api_key=api_key)
    if http_ip and account:
        return cgtw2.tw(http_ip=http_ip, account=account, password=password)
    return cgtw2.tw()


def _sync_one_item(tw, config, item):
    db = config["db"]
    module = config["module"]
    module_type = config.get("module_type") or "task"
    result = {
        "row": item["row"],
        "shot_number": item["shot_number"],
        "success": False,
        "actions": [],
    }
    try:
        target_api = str(config.get("target_api") or "task").lower()
        
        task_name_filter = next((f for f in item["filter"] if len(f) >= 3 and f[0] == config.get("task_name_field", "pipeline.entity") and f[2] in ("AUTO_DISCOVER", "AUTO_RESOLVE_FX")), None)
        if task_name_filter:
            base_filter = [f for f in item["filter"] if f[0] != config.get("task_name_field", "pipeline.entity")]
            if target_api == "etask":
                task_ids = tw.etask.get_id(db, base_filter, limit="20")
            else:
                task_ids = tw.task.get_id(db, module, base_filter, limit="20")
            if not task_ids:
                result["error"] = "未找到该镜头的任何任务，无法自动通过"
                return result
            
            data = tw.task.get(db, "shot", task_ids, ['task.id', 'task.supervise_status', 'task.status', 'pipeline.entity'])
            
            if task_name_filter[2] == "AUTO_RESOLVE_FX":
                fx_tasks = [t for t in data if t.get('pipeline.entity') in ('UE_FX', 'Effect')]
                unique_pipelines = list(set(t.get('pipeline.entity') for t in fx_tasks))
                if len(unique_pipelines) == 1:
                    task_id = [t['task.id'] for t in fx_tasks if t['pipeline.entity'] == unique_pipelines[0]][0]
                elif len(unique_pipelines) > 1:
                    result["error"] = "自动匹配失败：该镜头同时包含【传统特效】和【UE特效】任务，系统无法确定。请在表格手动指定具体特效部门。"
                    return result
                else:
                    result["error"] = "自动匹配失败：未找到该镜头的任何特效(UE_FX/Effect)环节任务。"
                    return result
            else:
                retake_tasks = [t for t in data if "返修" in str(t.get('task.supervise_status', '')) or "Retake" in str(t.get('task.supervise_status', ''))]
                
                if len(retake_tasks) == 1:
                    task_id = retake_tasks[0]['task.id']
                elif len(retake_tasks) > 1:
                    result["error"] = "自动匹配失败：找到多个处于返修的环节，请在表格【部门】列手动指定通过哪个环节"
                    return result
                else:
                    result["error"] = "自动匹配失败：没有找到处于返修状态的环节，请在表格【部门】列手动指定"
                    return result
        else:
            if target_api == "etask":
                task_ids = tw.etask.get_id(db, item["filter"], limit="20")
            else:
                task_ids = tw.task.get_id(db, module, item["filter"], limit="20")
            if not task_ids:
                result["error"] = "未匹配到 CGTeamWork 任务"
                return result
            if len(task_ids) > 1:
                result["error"] = "匹配到多个 CGTeamWork 任务，请收紧筛选条件"
                result["matched_ids"] = task_ids
                return result
            task_id = task_ids[0]
        result["matched_id"] = task_id
        sync_mode = str(config.get("sync_mode") or "note").lower()
        if sync_mode == "flow":
            field_sign = str(config.get("flow_field_sign") or "task.supervise_status").strip()
            status = str(config.get("flow_status") or config.get("target_status") or "内部返修").strip()
            if item.get("is_approved"):
                status = "通过"
            if not field_sign or not status:
                result["error"] = "未配置 CGTeamWork 流程反馈字段或状态"
                return result
            if target_api == "etask":
                flow_ret = tw.etask.update_flow(
                    db, task_id, field_sign, status, item["note_blocks"], []
                )
            else:
                flow_ret = tw.task.update_flow(
                    db, module, task_id, field_sign, status, item["note_blocks"], []
                )
            result["actions"].append({"flow_field": field_sign, "flow_status": status, "flow_result": flow_ret})

        elif sync_mode == "field":
            field_sign = str(config.get("flow_field_sign") or "task.supervise_status").strip()
            status = str(config.get("flow_status") or config.get("target_status") or "内部返修").strip()
            if item.get("is_approved"):
                status = "通过"
            if not field_sign or not status:
                result["error"] = "未配置 CGTeamWork 字段或状态"
                return result
            # 使用更底层的 tw.task.set 强制修改字段，绕过 etask/flow 的权限或QC状态校验
            update_data = {field_sign: status}
            # 为了让CGTW客户端的任务块颜色也能跟着变（标红/标绿），如果主签名字段不是 task.status，我们强制带上 task.status
            if field_sign != "task.status":
                update_data["task.status"] = status
            set_ret = tw.task.set(db, module, [task_id], update_data)
            result["actions"].append({"set_field": ",".join(update_data.keys()), "set_status": status, "set_result": set_ret})

        if config.get("sync_note", True) and sync_mode != "flow" and not item.get("is_approved"):
            note_id = tw.note.create(
                db,
                module,
                module_type,
                [task_id],
                item["note_blocks"],
                config.get("cc_account_id") or "",
                item["image_paths"],  # 仅上传图片以防 API 崩溃
                tag_list=["director_review_sync"],
            )
            result["actions"].append({"note_id": note_id})

        # 过滤掉已经上传到 note 的图片，防止双传。如果全是图片，就不再提交 filebox
        final_submit_paths = [p for p in item["submit_paths"] if p not in item["image_paths"]]
        
        if config.get("submit_review") and final_submit_paths:
            try:
                if target_api == "etask":
                    tw.etask.submit(
                        db,
                        task_id,
                        final_submit_paths,
                        note=item["note_blocks"],  # 留空，因为 note.create 已经发过文本了
                        filebox_sign=config.get("filebox_sign") or "review",
                        argv_dict={"is_submit": False},
                    )
                else:
                    tw.task.submit(
                        db,
                        module,
                        task_id,
                        final_submit_paths,
                        note=item["note_blocks"],
                        filebox_sign=config.get("filebox_sign") or "review",
                        argv_dict={"is_submit": False},
                    )
                result["actions"].append({"submitted_files": len(final_submit_paths)})
            except Exception as e:
                result["actions"].append({"submit_warning": str(e)})

        if config.get("upload_filebox") and config.get("filebox_id") and item["submit_paths"]:
            tw.media_file.upload_filebox(
                db,
                module,
                module_type,
                task_id,
                config["filebox_id"],
                item["submit_paths"],
            )
            result["actions"].append({"uploaded_filebox_files": len(item["submit_paths"])})

        if config.get("update_status") and config.get("target_status"):
            if target_api == "etask":
                tw.etask.update_task_status(db, [task_id], config["target_status"], note=item["note_blocks"])
            else:
                tw.task.update_task_status(db, module, [task_id], config["target_status"], note=item["note_blocks"])
            result["actions"].append({"status": config["target_status"]})

        result["success"] = True
        return result
    except Exception as exc:
        result["error"] = str(exc)
        return result


def _normalize_cgtw_shot_number(shot_number):
    text = str(shot_number or "").strip()
    match = re.fullmatch(r"(?i)ep(\d+)_sc(\d+)_(\d+)", text)
    if match:
        ep, sc, shot = match.groups()
        return f"Ep{ep}_sc{sc}_{shot}"
    return text


def _build_task_filter(config, shot_number, entry=None):
    filters = [[config.get("shot_field") or "shot.entity", config.get("shot_filter_operator") or "=", shot_number]]
    task_name = _pipeline_for_entry(config, entry or {})
    task_field = str(config.get("task_name_field") or "task.entity").strip()
    if task_name and task_field:
        filters.append([task_field, "=", task_name])
    return filters


def _pipeline_for_entry(config, entry):
    department = str(entry.get("department") or "").strip()
    if department == "AUTO_DISCOVER":
        return "AUTO_DISCOVER"
    if department == "特效":
        return "AUTO_RESOLVE_FX"
    mapping = config.get("department_pipeline_map") or {}
    mapped = str(mapping.get(department) or "").strip()
    if mapped:
        return mapped
    return str(config.get("task_name") or "").strip()


def _build_note_blocks(entry, shot_number, image_paths, attachment_paths):
    parts = [
        "[协同审阅平台同步]",
        f"镜头号: {shot_number}",
    ]
    timestamp = str(entry.get("timestamp") or "").strip()
    if timestamp:
        parts.append(f"时间码: {timestamp}")
    department = str(entry.get("department") or "").strip()
    if department:
        parts.append(f"部门: {department}")
    simplified = str(entry.get("simplified_review") or "").strip()
    if simplified:
        parts.append(f"简化意见: {simplified}")
    full_review = str(entry.get("full_review") or "").strip()
    if full_review:
        parts.append("完整意见:\n" + full_review)
    keywords = entry.get("keywords")
    if isinstance(keywords, list) and keywords:
        parts.append("关键词: " + ", ".join(str(item) for item in keywords if item))

    blocks = [{"type": "text", "content": "\n".join(parts)}]
    for path in image_paths:
        blocks.append({"type": "image", "path": path})
    for path in attachment_paths:
        blocks.append({"type": "attachment", "path": path})
    return blocks


def _resolve_path(path, temp_dir):
    if not path:
        return None
    path = str(path)
    if os.path.isabs(path):
        return os.path.normpath(path)
    if temp_dir:
        return os.path.normpath(os.path.join(temp_dir, path.replace("/", os.sep)))
    return os.path.normpath(path)


def _ensure_list(value):
    if not value:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _is_image(path):
    return os.path.splitext(str(path).lower())[1] in IMAGE_EXTENSIONS


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--worker", help="Run CGTeamWork sync worker with a payload JSON file.")
    args = parser.parse_args(argv)
    if args.worker:
        result = _run_worker(args.worker)
        print(json.dumps(result, ensure_ascii=False))
        return 0 if result.get("success") else 1
    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
