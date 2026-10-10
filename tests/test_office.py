# SPDX-License-Identifier: EUPL-1.2
import json
import os
import subprocess
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from migration import office


class OfficeTests(unittest.TestCase):
    def test_local_cache_requires_explicit_location(self):
        cached = office.ROOT / "target/tools/libreoffice/program"
        executable = "soffice.exe" if os.name == "nt" else "soffice"
        with patch.dict(os.environ, {}, clear=True), patch.object(Path, "is_file", return_value=False), patch.object(Path, "exists", lambda path: path == cached / executable):
            with self.assertRaises(FileNotFoundError):
                office.program()
            self.assertEqual(office.program(cached), cached.resolve())

    def test_uno_python_default_and_override(self):
        directory = office.ROOT / "target/test-office-program"
        default = directory / "python.exe" if os.name == "nt" else Path("/usr/bin/python3")
        override = office.ROOT / "target/custom-uno-python"
        for selected in [None, override]:
            with self.subTest(selected=selected), patch.dict(os.environ, {}, clear=True), patch.object(office, "program", return_value=directory), patch.object(Path, "exists", return_value=True), patch.object(office.subprocess, "Popen", return_value=Mock(poll=Mock(return_value=0))) as launch, patch.object(office.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, '{"converted": true}', '')) as worker:
                if selected:
                    os.environ["MACROFERRY_UNO_PYTHON"] = str(selected)
                job = {"mode": "convert", "modules": {}}
                self.assertEqual(office.run(job), {"converted": True})
                self.assertEqual(worker.call_args.args[0][0], str(selected or default))
                self.assertEqual(json.loads(worker.call_args.kwargs["input"]), job)
                launch.assert_called_once()

    def test_missing_override_fails_before_office_launch(self):
        with patch.dict(os.environ, {"MACROFERRY_UNO_PYTHON": str(office.ROOT / "target/missing-uno-python")}), patch.object(office, "program", return_value=office.ROOT), patch.object(Path, "exists", return_value=False), patch.object(office.subprocess, "Popen") as launch:
            with self.assertRaisesRegex(FileNotFoundError, "MACROFERRY_UNO_PYTHON"):
                office.run({"mode": "convert", "modules": {}})
            launch.assert_not_called()
