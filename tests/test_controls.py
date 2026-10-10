# SPDX-License-Identifier: EUPL-1.2
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from migration import controls
from migration.convert import convert, todo_count
from test_formatting import SOURCE


def event(code="vnd.sun.star.script:Cellwright.Formatting.FormatSheet?language=Basic&location=document", method="actionPerformed"):
    return SimpleNamespace(ScriptCode=code, ScriptType="Script", ListenerType="XActionListener", EventMethod=method, AddListenerParam="")


class Container:
    def __init__(self, children, events=None):
        self.children, self.events = children, events or {}
    def getCount(self): return len(self.children)
    def getByIndex(self, index): return self.children[index]
    def getScriptEvents(self, index): return self.events.get(index, ())
    def revokeScriptEvents(self, index): self.events[index] = ()
    def registerScriptEvent(self, index, value): self.events[index] += (value,)


class ControlsTests(unittest.TestCase):
    def setUp(self):
        self.module = {"name": "Formatting", "kind": "standard", "source": SOURCE, "code_lines": 11, "findings": []}
        self.records = [{"todos": []}]
        self.known = controls.handlers([self.module], self.records)

    def test_local_names_and_handler_eligibility(self):
        for name in ("FormatSheet", "Formatting.FormatSheet", "[0]!Formatting.FormatSheet", "'Book.xlsm'!Formatting.FormatSheet"):
            self.assertEqual(controls.resolve(name, "StarBasic", self.known, "Book.xlsm")["module"], "Formatting")
        for code, typ in (("'other.xlsm'!Formatting.FormatSheet", "StarBasic"), ("FormatSheet(1)", "StarBasic"), ("Missing", "StarBasic"),
                          ("vnd.sun.star.script:Formatting.FormatSheet?language=Basic&location=application", "Script")):
            with self.assertRaises(ValueError): controls.resolve(code, typ, self.known, "Book.xlsm")
        with self.assertRaisesRegex(ValueError, "ambiguous"):
            controls.resolve("FormatSheet", "StarBasic", self.known * 2, "Book.xlsm")
        for source, kind, todos in (("Private Sub Test()\nEnd Sub", "standard", []), ("Sub Test(ByVal x As Long)\nEnd Sub", "standard", []),
                                    ("Function Test()\nEnd Function", "standard", []), ("Sub Auto_Open()\nEnd Sub", "standard", []), ("Sub Test()\nEnd Sub", "document", []), (SOURCE, "standard", [{"reason": "manual"}])):
            item = {**self.module, "source": source, "kind": kind}
            known = controls.handlers([item], [{"todos": todos}])
            with self.assertRaises(ValueError): controls.resolve(known[0]["procedure"], "StarBasic", known, "Book.xlsm")
        local = event()
        self.assertEqual(controls.resolve(local.ScriptCode, local.ScriptType, self.known, 'Book.xlsm')['module'], 'Formatting')

    def test_rebinding_detaches_unsupported_events_and_never_invokes(self):
        button = SimpleNamespace(Name="Format", ButtonType=SimpleNamespace(value="PUSH"), Toggle=False, TargetURL="", supportsService=lambda name: name.endswith("CommandButton"))
        other = SimpleNamespace(Name="Text", supportsService=lambda name: False)
        nested = Container([button, button, button, other], {0: (event(),), 1: (event(method="mouseEntered"),), 2: (), 3: (event(),)})
        nested.Name = "Form"
        nested.supportsService = lambda name: name.endswith(".Form")
        root = Container([nested], {0: (event(),)})
        sheet = SimpleNamespace(Name="Data", DrawPage=SimpleNamespace(Forms=root))
        document = SimpleNamespace(Sheets=SimpleNamespace(Count=1, getByIndex=lambda index: sheet), getScriptProvider=Mock(side_effect=AssertionError("Must never execute")))
        uno = SimpleNamespace(createUnoStruct=lambda name: SimpleNamespace())
        result = controls.rebind(document, self.known, "Book.xlsm", ["CellwrightButtons"], uno)
        self.assertEqual(result["wrapper_module"], "CellwrightButtonsX")
        self.assertIn("Formatting.formatsheet", result["wrapper_source"])
        self.assertEqual(sum(item["status"] == "rewritten" for item in result["records"]), 1)
        self.assertEqual(sum(item["status"] == "manual" for item in result["records"]), 4)
        self.assertFalse(root.events[0])
        self.assertEqual(nested.events[0][0].ScriptCode, "vnd.sun.star.script:Standard.CellwrightButtonsX.Button1?language=Basic&location=document")
        self.assertFalse(nested.events[1] or nested.events[2] or nested.events[3])
        document.getScriptProvider.assert_not_called()

    def test_conversion_report_preserves_originals_packages_helpers_and_counts_button_todos(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            original = root / "Book.xlsm"
            original.write_bytes(b"owned fixture placeholder")
            digest = hashlib.sha256(original.read_bytes()).hexdigest()
            workbook = {"modules": [self.module], "queries": [], "findings": [], "macro_assignments": ["[0]!Formatting.FormatSheet"]}
            def extract(command, **kwargs):
                directory = Path(command[command.index("--out") + 1])
                directory.mkdir()
                (directory / "scan.json").write_text(json.dumps({"workbooks": [workbook]}), encoding="utf-8")
            buttons = {"records": [{"status": "rewritten", "before": "[0]!Formatting.FormatSheet", "handler": "Formatting.formatsheet", "after": "wrapper"}],
                       "wrapper_module": "CellwrightButtons", "wrapper_source": "Sub Button1(event As Object)\nFormatting.formatsheet\nEnd Sub\n"}
            with patch("migration.convert.subprocess.run", side_effect=extract), patch("migration.convert.office.run", return_value={"buttons": buttons}) as worker:
                report = convert(original, root / "basic", root / "scanner", "basic-uno")
                self.assertEqual(todo_count(report), 0)
                self.assertTrue(worker.call_args.args[0]["button_handlers"])
                self.assertNotIn("allow_execution", worker.call_args.args[0])
                self.assertEqual((root / "basic/source/0000-Formatting.original.bas").read_text(encoding="utf-8"), SOURCE)
                self.assertTrue((root / "basic/source/button-wrappers.bas").exists())
                report = convert(original, root / "python", root / "scanner", "python")
                self.assertEqual(todo_count(report), 1)
                self.assertTrue((root / "python/migration/formatting.py").exists())
                self.assertEqual(worker.call_count, 1)
                workbook['features'] = ['activex']
                buttons['wrapper_source'] = ''
                convert(original, root / 'activex', root / 'scanner', 'basic')
                self.assertIn('ActiveX', worker.call_args.args[0]['button_handlers'][0]['reason'])
                workbook['features'], workbook['macro_assignments'] = ['macro_assignment'], []
                report = convert(original, root / 'unreadable-assignment', root / 'scanner', 'python')
                self.assertEqual(todo_count(report), 1)
            self.assertEqual(report["input_sha256"], digest)
            self.assertFalse(report["automatic_execution"] or report["verified"])
            self.assertEqual(hashlib.sha256(original.read_bytes()).hexdigest(), digest)
