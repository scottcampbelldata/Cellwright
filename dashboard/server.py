# SPDX-License-Identifier: EUPL-1.2
"""Loopback-only migration dashboard using SQLite and the existing scanner/converter."""
import argparse
import concurrent.futures
import contextlib
import hmac
import json
import os
import secrets
import sqlite3
import subprocess
import threading
import time
import uuid
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit, quote

ROOT = Path(__file__).resolve().parents[1]


class Store:
    def __init__(self, directory, binary, allow_execution=False):
        self.directory, self.binary = Path(directory).resolve(), Path(binary).resolve()
        self.allow_execution = allow_execution
        self.directory.mkdir(parents=True, exist_ok=True)
        self.database = self.directory / "dashboard.sqlite3"
        self.pool = concurrent.futures.ThreadPoolExecutor(max_workers=2)
        with self.connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS jobs (id TEXT PRIMARY KEY, kind TEXT, label TEXT, state TEXT, created INTEGER, finished INTEGER, input TEXT, options TEXT, result TEXT, error TEXT);
                CREATE TABLE IF NOT EXISTS assignments (path TEXT PRIMARY KEY, owner TEXT NOT NULL DEFAULT '', state TEXT NOT NULL DEFAULT 'pending', notes TEXT NOT NULL DEFAULT '', updated INTEGER);
                CREATE TABLE IF NOT EXISTS schedules (id TEXT PRIMARY KEY, label TEXT, paths TEXT, interval_hours INTEGER, next_run INTEGER, enabled INTEGER);
                UPDATE jobs SET state='failed', error='Dashboard stopped before this job completed', finished=strftime('%s','now') WHERE state IN ('queued','running');
            """)

    @contextlib.contextmanager
    def connect(self):
        db = sqlite3.connect(self.database, timeout=15)
        db.row_factory = sqlite3.Row
        try:
            with db: yield db
        finally: db.close()

    def list(self, table):
        if table not in ("jobs", "assignments", "schedules"): raise ValueError("Unknown table")
        with self.connect() as db:
            return [dict(row) for row in db.execute("SELECT * FROM " + table + (" ORDER BY created DESC LIMIT 100" if table == "jobs" else ""))]

    def job(self, identifier):
        with self.connect() as db:
            row = db.execute("SELECT * FROM jobs WHERE id=?", (identifier,)).fetchone()
        if not row: raise KeyError("Job not found")
        return dict(row)

    def submit(self, kind, label, input_value, options):
        if kind not in ("scan", "convert", "verify"): raise ValueError("Unsupported job kind")
        if kind == "verify" and not self.allow_execution: raise PermissionError("Restart the dashboard with --allow-execution to enable macro verification")
        identifier = uuid.uuid4().hex
        with self.connect() as db:
            db.execute("INSERT INTO jobs VALUES (?,?,?,?,?,?,?,?,?,?)", (identifier, kind, str(label)[:120], "queued", int(time.time()), None, json.dumps(input_value), json.dumps(options), None, None))
        self.pool.submit(self.execute, identifier)
        return identifier

    def execute(self, identifier):
        directory = self.directory / identifier
        with self.connect() as db:
            db.execute("UPDATE jobs SET state='running' WHERE id=?", (identifier,))
        job = self.job(identifier)
        inputs, options = json.loads(job["input"]), json.loads(job["options"])
        try:
            if job["kind"] == "scan":
                command = [str(self.binary), "scan", "--out", str(directory), "--lang", options.get("lang", "en")]
                if not options.get("source"): command.append("--no-source")
                command.extend(["--", *inputs])
                result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", timeout=3600)
                if result.returncode not in (0, 1): raise RuntimeError(result.stderr[-4000:])
                report = directory / "scan.json"
                summary = json.loads(report.read_text(encoding="utf-8"))
                state = "completed" if result.returncode == 0 else "partial"
                data = {"workbooks": len(summary["workbooks"]), "unique_modules": summary["unique_modules"], "hours_low": summary["estimated_hours_low"], "hours_high": summary["estimated_hours_high"], "source_included": summary["source_included"]}
            elif job["kind"] == "convert":
                from migration.convert import convert
                summary = convert(inputs, directory, self.binary, options["target"])
                data = {"modules": len(summary["modules"]), "queries":len(summary.get('power_queries',[])), "todos": sum(len(module["todos"]) for module in summary["modules"])+sum(len(query['todos']) for query in summary.get('power_queries',[])), "target": summary["target"], "verified": False}
                with zipfile.ZipFile(directory/'candidate.zip','x',zipfile.ZIP_DEFLATED) as archive:
                    for filename in sorted(directory.rglob('*')):
                        if filename.is_file() and filename!=directory/'candidate.zip':archive.write(filename,filename.relative_to(directory).as_posix())
                state = "completed"
            else:
                if not self.allow_execution: raise PermissionError("Dashboard macro execution is disabled")
                from migration.verify import verify
                summary=verify(inputs,directory,allow_execution=True)
                data={"passed":summary["passed"],"cells_checked":summary["cells_checked"],"differences":len(summary["differences"]),"conversion_id":options["conversion_id"]}
                state="completed" if summary["passed"] else "partial"
            with self.connect() as db:
                db.execute("UPDATE jobs SET state=?, finished=?, result=? WHERE id=?", (state, int(time.time()), json.dumps(data), identifier))
        except Exception as error:
            with self.connect() as db:
                db.execute("UPDATE jobs SET state='failed', finished=?, error=? WHERE id=?", (int(time.time()), str(error)[:4000], identifier))

    def assignment(self, value):
        path, state = value.get("path"), value.get("state", "pending")
        if not isinstance(path, str) or not path or len(path) > 32768: raise ValueError("Invalid workbook path")
        if state not in ("pending", "in_review", "converted", "verified", "blocked"): raise ValueError("Invalid status")
        owner, notes = value.get("owner", ""), value.get("notes", "")
        if not isinstance(owner, str) or not isinstance(notes, str) or len(owner) > 120 or len(notes) > 10000: raise ValueError("Assignment text too long")
        with self.connect() as db:
            db.execute("INSERT INTO assignments VALUES (?,?,?,?,?) ON CONFLICT(path) DO UPDATE SET owner=excluded.owner,state=excluded.state,notes=excluded.notes,updated=excluded.updated", (path, owner, state, notes, int(time.time())))

    def schedule(self, value):
        paths, interval = value.get("paths"), value.get("interval_hours", 24)
        validate_paths(paths)
        if type(interval) is not int or not 1 <= interval <= 8760: raise ValueError("Interval must be 1–8760 hours")
        identifier = value.get("id") or uuid.uuid4().hex
        label, enabled = str(value.get("label", "Scheduled scan"))[:120], bool(value.get("enabled", True))
        with self.connect() as db:
            db.execute("INSERT INTO schedules VALUES (?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET label=excluded.label,paths=excluded.paths,interval_hours=excluded.interval_hours,enabled=excluded.enabled", (identifier, label, json.dumps(paths), interval, int(time.time()) + interval * 3600, enabled))
        return identifier

    def due(self, now=None):
        now = int(time.time()) if now is None else now
        with self.connect() as db:
            due = list(db.execute("SELECT * FROM schedules WHERE enabled=1 AND next_run<=?", (now,)))
            for row in due:
                db.execute("UPDATE schedules SET next_run=? WHERE id=?", (now + row["interval_hours"] * 3600, row["id"]))
        for row in due:
            self.submit("scan", row["label"], json.loads(row["paths"]), {"source": False, "lang": "en"})
        return len(due)


def validate_paths(paths):
    if not isinstance(paths, list) or not 1 <= len(paths) <= 100 or any(not isinstance(path, str) or not path.strip() or len(path) > 32768 or "\0" in path for path in paths):
        raise ValueError("Provide 1–100 workbook or folder paths")


class Server(ThreadingHTTPServer):
    daemon_threads = True
    def __init__(self, address, store):
        super().__init__(address, Handler)
        self.store = store
        self.token = secrets.token_urlsafe(32)
        self.authority = f"127.0.0.1:{self.server_port}"
        self.authorities = {self.authority, f"localhost:{self.server_port}"}
        self.requires_golden = os.name != "nt"


class Handler(BaseHTTPRequestHandler):
    def log_message(self, format, *args): pass

    def allowed_host(self):
        host = self.headers.get("Host")
        if host not in self.server.authorities:
            raise PermissionError("Invalid Host header")
        origin = self.headers.get("Origin")
        if origin and origin != "http://" + host:
            raise PermissionError("Cross-origin requests are rejected")

    def authorize(self, cookie=False):
        self.allowed_host()
        token = self.headers.get("X-MacroFerry-Token", "")
        if cookie:
            from http.cookies import SimpleCookie
            cookies = SimpleCookie(self.headers.get("Cookie", ""))
            token = cookies["mf_session"].value if "mf_session" in cookies else ""
        if not hmac.compare_digest(token, self.server.token): raise PermissionError("Invalid session token")

    def reply(self, value, status=200, content_type="application/json", cookie=False, attachment=False):
        data = json.dumps(value).encode() if content_type == "application/json" else value
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Referrer-Policy", "no-referrer")
        if cookie: self.send_header("Set-Cookie", "mf_session=" + self.server.token + "; HttpOnly; SameSite=Strict; Path=/")
        if attachment: self.send_header("Content-Disposition", "attachment; filename*=UTF-8''" + quote(attachment,safe=''))
        self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-src 'self'; frame-ancestors 'none'; base-uri 'none'; object-src 'none'")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        try:
            self.allowed_host()
            path = unquote(urlsplit(self.path).path)
            if path == "/":
                html = (ROOT / "dashboard/index.html").read_bytes().replace(b"SESSION_TOKEN", self.server.token.encode())
                self.reply(html, content_type="text/html; charset=utf-8", cookie=True)
            elif path in ("/app.js", "/style.css"):
                self.reply((ROOT / "dashboard" / path[1:]).read_bytes(), content_type="text/javascript; charset=utf-8" if path.endswith(".js") else "text/css; charset=utf-8")
            elif path == "/api/state":
                self.authorize()
                self.reply({"jobs": self.server.store.list("jobs"), "assignments": self.server.store.list("assignments"), "schedules": self.server.store.list("schedules"), "version": "0.1.0", "offline": True, "allow_execution": self.server.store.allow_execution, "requires_golden": self.server.requires_golden})
            elif path.startswith("/api/jobs/"):
                self.authorize()
                identifier = path.split("/")[-1]
                job = self.server.store.job(identifier)
                filename = "scan.json" if job["kind"] == "scan" else "verification.json" if job["kind"]=="verify" else "conversion.json"
                self.reply(json.loads((self.server.store.directory / identifier / filename).read_text(encoding="utf-8")))
            elif path.startswith("/files/"):
                self.authorize(cookie=True)
                parts = path.split("/")
                identifier = parts[2]
                self.server.store.job(identifier)
                directory = self.server.store.directory / identifier
                filename = directory.joinpath(*parts[3:]).resolve()
                if not filename.is_relative_to(directory.resolve()) or not filename.is_file(): raise PermissionError("Invalid artifact path")
                if filename.stat().st_size > 128 * 1024 * 1024: raise ValueError("Artifact too large")
                self.reply(filename.read_bytes(), content_type="application/octet-stream", attachment=filename.name)
            else:
                self.reply({"error": "Not found"}, 404)
        except Exception as error:
            self.reply({"error": str(error)}, 403 if isinstance(error, PermissionError) else 404 if isinstance(error, (FileNotFoundError, KeyError)) else 400)

    def do_POST(self):
        try:
            self.authorize()
            if self.headers.get("Content-Type") != "application/json": raise ValueError("JSON content type required")
            length = int(self.headers.get("Content-Length", 0))
            if not 0 < length <= 256 * 1024: raise ValueError("Invalid request size")
            self.connection.settimeout(10)
            value = json.loads(self.rfile.read(length))
            if not isinstance(value, dict): raise ValueError("JSON object required")
            if self.path == "/api/scans":
                validate_paths(value.get("paths"))
                if value.get("lang", "en") not in ("en", "fr", "de"): raise ValueError("Invalid language")
                result = {"id": self.server.store.submit("scan", value.get("label", "Estate scan"), value["paths"], {"lang": value.get("lang", "en"), "source": bool(value.get("source", False))})}
            elif self.path == "/api/conversions":
                if value.get("target") not in ("basic", "basic-uno", "python-uno", "python"): raise ValueError("Invalid target")
                validate_paths([value.get("path")])
                result = {"id": self.server.store.submit("convert", Path(value["path"]).name, value["path"], {"target": value["target"]})}
            elif self.path == "/api/assignments":
                self.server.store.assignment(value)
                result = {"saved": True}
            elif self.path == "/api/verifications":
                if not self.server.store.allow_execution:raise PermissionError("Restart the dashboard with --allow-execution to enable macro verification")
                if value.get("allow_execution") is not True:raise PermissionError("Explicit execution consent required")
                golden=value.get("golden")
                if self.server.requires_golden and not golden:raise ValueError("Linux verification requires a saved Excel capture JSON path")
                if golden:
                    validate_paths([golden])
                    if not Path(golden).is_file():raise ValueError("Saved Excel capture JSON not found")
                job=self.server.store.job(value.get("conversion_id"))
                if job["kind"]!='convert' or job["state"]!='completed':raise ValueError("Select a completed conversion")
                target=json.loads(job["options"])["target"]
                if target=='python':raise ValueError("Standalone Python candidates use the CLI run-python and comparison tools")
                candidate=self.server.store.directory/job["id"]
                original={"input":json.loads(job["input"]),"macro":value["macro"],"inputs":value.get("inputs",[])}
                converted={"input":str(candidate/'converted.ods'),"macro":value.get("converted_macro") or 'Standard.'+value["macro"],"inputs":value.get("inputs",[])}
                if target=='python-uno':
                    report=json.loads((candidate/'conversion.json').read_text(encoding='utf-8'))
                    module_name=value["macro"].split('.')[0]
                    module=next((module for module in report['modules'] if module['name']==module_name),None)
                    if not module:raise ValueError("Python module not found")
                    converted['python_module']=str(candidate/module['candidate']);converted['macro']=value["macro"].split('.')[-1]
                case={"original":original,"converted":converted,"ranges":value["ranges"]}
                if golden:case["golden"]=str(Path(golden).resolve())
                result={"id":self.server.store.submit('verify','Verify '+job['label'],case,{"conversion_id":job['id']})}
            elif self.path == "/api/schedules":
                result = {"id": self.server.store.schedule(value)}
            elif self.path == "/api/schedules/delete":
                with self.server.store.connect() as db: db.execute("DELETE FROM schedules WHERE id=?", (value.get("id"),))
                result = {"deleted": True}
            else:
                self.reply({"error": "Not found"}, 404)
                return
            self.reply(result, 200)
        except Exception as error:
            self.reply({"error": str(error)}, 403 if isinstance(error, PermissionError) else 400)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8768)
    parser.add_argument("--allow-execution", action="store_true", help="Enable trusted macro verification; any local process can access this dashboard")
    parser.add_argument("--data", type=Path, default=ROOT / "reports/dashboard")
    parser.add_argument("--binary", type=Path, default=ROOT / ("target/release/macroferry.exe" if os.name=='nt' else "target/release/macroferry"))
    args = parser.parse_args()
    if not 0 <= args.port <= 65535: parser.error("Invalid port")
    store = Store(args.data, args.binary, args.allow_execution)
    server = Server(("127.0.0.1", args.port), store)
    stop = threading.Event()
    def scheduler():
        while not stop.wait(30):
            try: store.due()
            except Exception as error: print("Schedule error:", error, flush=True)
    thread = threading.Thread(target=scheduler, daemon=True)
    thread.start()
    print("MacroFerry dashboard: http://" + server.authority, flush=True)
    try: server.serve_forever()
    except KeyboardInterrupt: pass
    finally:
        stop.set()
        server.server_close()
        store.pool.shutdown(wait=True)


if __name__ == "__main__": main()
