# -*- coding: utf-8 -*-
import json
import os
import time
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from cgtw_sync import discover_cgtw_context, get_cgtw_settings, run_cgtw_sync, validate_cgtw_settings


DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8787


class CgtwBridgeServer:
    def __init__(self, settings_getter, temp_dir_getter=None, host=DEFAULT_HOST, port=DEFAULT_PORT):
        self.settings_getter = settings_getter
        self.temp_dir_getter = temp_dir_getter or (lambda: "")
        self.host = host
        self.port = port
        self.last_heartbeat = time.time()
        self.httpd = None
        self.thread = None

    def start(self):
        if self.thread and self.thread.is_alive():
            return True
        handler = self._make_handler()
        try:
            self.httpd = ThreadingHTTPServer((self.host, self.port), handler)
        except OSError:
            return False
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()
        return True

    def stop(self):
        if self.httpd:
            self.httpd.shutdown()
            self.httpd.server_close()
        self.httpd = None

    def _make_handler(self):
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, fmt, *args):
                return

            def do_OPTIONS(self):
                self._send_json({"ok": True})

            def do_GET(self):
                if self.path.rstrip("/") == "/cgtw/heartbeat":
                    outer.last_heartbeat = time.time()
                    self._send_json({"ok": True})
                    return
                if self.path.rstrip("/") == "/cgtw/status":
                    settings = outer.settings_getter() or {}
                    config = get_cgtw_settings(settings)
                    self._send_json({
                        "ok": True,
                        "config": _public_config(config),
                        "errors": validate_cgtw_settings(config, require_runtime=False),
                        "discovered": discover_cgtw_context(config),
                    })
                    return
                self._send_json({"ok": False, "error": "not found"}, status=404)

            def do_POST(self):
                if self.path == '/api/v1/cgtw/query':
                    try:
                        content_length = int(self.headers.get('Content-Length', 0))
                        post_data = self.rfile.read(content_length)
                        payload = json.loads(post_data.decode('utf-8'))
                        
                        db = payload.get("db")
                        module = payload.get("module", "shot")
                        fields = payload.get("fields", [])
                        filters = payload.get("filters", [])
                        limit = str(payload.get("limit", "100"))
                        
                        if not db:
                            return self._send_json({"error": "Missing db"}, status=400)
                            
                        import cgtw2
                        tw = cgtw2.tw()
                        
                        task_ids = tw.etask.get_id(db, filters, limit=limit)
                        if not task_ids:
                            return self._send_json({"data": []})
                            
                        data = tw.task.get(db, module, task_ids, fields)
                        return self._send_json({"data": data})
                    except Exception as e:
                        return self._send_json({"error": str(e)}, status=500)
                        
                if self.path == '/api/v1/cgtw/update':
                    try:
                        content_length = int(self.headers.get('Content-Length', 0))
                        post_data = self.rfile.read(content_length)
                        payload = json.loads(post_data.decode('utf-8'))
                        
                        db = payload.get("db")
                        module = payload.get("module", "shot")
                        task_id_list = payload.get("task_id_list", [])
                        update_data = payload.get("update_data", {})
                        
                        if not db or not task_id_list or not update_data:
                            return self._send_json({"error": "Missing parameters"}, status=400)
                            
                        import cgtw2
                        tw = cgtw2.tw()
                        
                        res = tw.task.set(db, module, task_id_list, update_data)
                        return self._send_json({"success": res})
                    except Exception as e:
                        return self._send_json({"error": str(e)}, status=500)
                        
                if self.path == '/api/v1/cgtw/update_flow':
                    try:
                        content_length = int(self.headers.get('Content-Length', 0))
                        post_data = self.rfile.read(content_length)
                        payload = json.loads(post_data.decode('utf-8'))
                        
                        db = payload.get("db")
                        module = payload.get("module", "shot")
                        task_id = payload.get("task_id")
                        field_sign = payload.get("field_sign")
                        status = payload.get("status")
                        message_data = payload.get("message_data", [])
                        image_list = payload.get("image_list", [])
                        
                        if not all([db, module, task_id, field_sign, status]):
                            return self._send_json({"error": "Missing parameters"}, status=400)
                            
                        import cgtw2
                        tw = cgtw2.tw()
                        
                        res = tw.task.update_flow(db, module, task_id, field_sign, status, message_data, image_list)
                        return self._send_json({"success": res})
                    except Exception as e:
                        return self._send_json({"error": str(e)}, status=500)

                if self.path.rstrip("/") != "/cgtw/sync":
                    self._send_json({"ok": False, "error": "not found"}, status=404)
                    return
                try:
                    length = int(self.headers.get("Content-Length") or "0")
                    body = self.rfile.read(length).decode("utf-8")
                    payload = json.loads(body or "{}")
                    entries = payload.get("entries") or []
                    settings = outer.settings_getter() or {}
                    force_dry_run = payload.get("dry_run")
                    result = run_cgtw_sync(entries, outer.temp_dir_getter(), settings, force_dry_run=force_dry_run)
                    self._send_json({"ok": bool(result.get("success")), "result": result})
                except Exception as exc:
                    self._send_json({"ok": False, "error": str(exc)}, status=500)

            def _send_json(self, data, status=200):
                raw = json.dumps(data, ensure_ascii=False).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(raw)))
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
                self.send_header("Access-Control-Allow-Headers", "Content-Type")
                self.end_headers()
                self.wfile.write(raw)

        return Handler


def _public_config(config):
    hidden = {"password", "token", "api_key"}
    return {key: value for key, value in config.items() if key not in hidden}


def _load_settings_file():
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "settings.json")
    if not os.path.exists(path):
        path = os.path.abspath("settings.json")
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def main():
    settings_cache = _load_settings_file()
    server = CgtwBridgeServer(lambda: settings_cache)
    if not server.start():
        print(f"CGTeamWork bridge already running or failed on http://{DEFAULT_HOST}:{DEFAULT_PORT}")
        return 1
    print(f"CGTeamWork bridge running at http://{DEFAULT_HOST}:{DEFAULT_PORT}")
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        server.stop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
