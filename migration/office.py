# SPDX-License-Identifier: EUPL-1.2
"""Launch a bounded, private LibreOffice process; imports UNO only in the worker."""
import json
import os
import subprocess
import tempfile
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def local_path(path):
    candidate=Path(path)
    value=str(candidate if candidate.is_absolute() else candidate.resolve())
    if os.name=='nt':
        if value.startswith('\\\\?\\UNC\\'):value='\\\\'+value[8:]
        elif value.startswith('\\\\?\\'):value=value[4:]
    return Path(value)


def program(path=None):
    candidates = [path, os.environ.get("CELLWRIGHT_LIBREOFFICE"), Path(os.environ.get("ProgramFiles", "/usr/lib")) / "LibreOffice/program", Path("/usr/lib/libreoffice/program")]
    for candidate in candidates:
        if candidate:
            candidate = Path(candidate)
            if candidate.is_file(): candidate = candidate.parent
            if (candidate / ("soffice.exe" if os.name == "nt" else "soffice")).exists():
                return candidate.resolve()
    raise FileNotFoundError("LibreOffice not found; use --libreoffice <program-directory> or CELLWRIGHT_LIBREOFFICE")


def run(job, location=None, timeout=90):
    directory = program(location)
    executable = directory / ("soffice.com" if os.name == "nt" else "soffice")
    default_interpreter = directory / "python.exe" if os.name == "nt" else Path("/usr/bin/python3")
    interpreter = Path(os.environ.get("CELLWRIGHT_UNO_PYTHON") or default_interpreter)
    if not interpreter.exists():
        raise FileNotFoundError("LibreOffice UNO Python is unavailable; install python3-uno or set CELLWRIGHT_UNO_PYTHON")
    with tempfile.TemporaryDirectory(prefix="cellwright-office-") as temporary:
        profile = local_path(Path(temporary) / "profile")
        pipe = "cellwright_" + uuid.uuid4().hex
        flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        environment = dict(os.environ, SAL_DISABLE_OPENCL="1")
        office = subprocess.Popen([str(executable), "--headless", "--nologo", "--nodefault", "--nofirststartwizard", "--norestore", "-env:UserInstallation=" + profile.as_uri(), "--accept=pipe,name=" + pipe + ";urp;StarOffice.ComponentContext"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=flags, env=environment, start_new_session=os.name != "nt")
        try:
            result = subprocess.run([str(interpreter), str(ROOT / "harness/libreoffice/runner.py"), pipe], input=json.dumps(job), text=True, encoding="utf-8", capture_output=True, timeout=timeout, creationflags=flags)
            if result.returncode:
                raise RuntimeError(result.stderr.strip() or "LibreOffice worker failed")
            return json.loads(result.stdout)
        finally:
            if office.poll() is None:
                if os.name == "nt":
                    subprocess.run(["taskkill.exe", "/PID", str(office.pid), "/T", "/F"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=flags)
                else:
                    import signal
                    os.killpg(office.pid, signal.SIGTERM)
            try: office.wait(timeout=10)
            except subprocess.TimeoutExpired:
                office.kill()
                office.wait()
