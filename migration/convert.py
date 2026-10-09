# SPDX-License-Identifier: EUPL-1.2
"""Assisted conversion: preserve originals, produce candidates and reviewable diffs."""
import difflib
import hashlib
import json
import re
import shutil
import subprocess
from pathlib import Path

from migration import office, vba

# Qualified language intrinsics; object model calls are handled separately.
BASIC_INTRINSICS = ('Abs Asc Chr CInt CLng CDbl CStr Date DateAdd Day Fix Hex IIf InStr Int IsNumeric Join LBound LCase Left Len LTrim Mid Month Now Replace Right Round RTrim Sgn Space Split Sqr Str Trim UBound UCase Val Weekday Year').split()
BASIC_NAMES = {name.lower():name for name in BASIC_INTRINSICS}


def basic_intrinsics(line):
    changed=[]
    def replace(match):
        name=match[1]
        if name and name.lower() in BASIC_NAMES:
            changed.append('BASIC-INTRINSIC-'+name.upper())
            return BASIC_NAMES[name.lower()] + ('$' if match[0].endswith('$') else '')
        return match[0]
    return re.sub(r'"(?:[^"]|"")*"|\x27[^\n]*|\bVBA\s*\.\s*([A-Za-z_]\w*)\$?',replace,line,flags=re.I),changed


UNO_HELPERS = '''
Function MFRange(sheetName As String, address As String) As Object
    Dim range As Object
    Dim bounds
    range = ThisComponent.Sheets.getByName(sheetName).getCellRangeByName(address)
    bounds = range.getRangeAddress()
    If bounds.StartRow <> bounds.EndRow Or bounds.StartColumn <> bounds.EndColumn Then
        Err.Raise 5, "MacroFerry", "Native UNO multi-cell values require manual migration"
    End If
    MFRange = range.getCellByPosition(0, 0)
End Function
Function MFCells(sheetName As String, row As Long, column As Long) As Object
    MFCells = ThisComponent.Sheets.getByName(sheetName).getCellByPosition(column - 1, row - 1)
End Function
Function MFGet(cell As Object) As Variant
    If cell.getError() <> 0 Then
        Err.Raise 5, "MacroFerry", "Cell errors require manual migration"
    ElseIf cell.getType() = 0 Then
        MFGet = Empty
    ElseIf cell.getType() = 2 Then
        MFGet = cell.String
    Else
        MFGet = cell.Value
    End If
End Function
Sub MFSet(cell As Object, value As Variant)
    If IsEmpty(value) Then
        cell.clearContents(23)
    ElseIf VarType(value) = 8 Then
        cell.String = value
    Else
        cell.Value = value
    End If
End Sub
'''


def basic_expression(node):
    kind = node["kind"]
    if kind == "literal": return '"' + node["value"].replace('"', '""') + '"'
    if kind == "number": return node["value"]
    if kind == "identifier": return node["name"]
    if kind == "unary": return "(" + node["op"] + " " + basic_expression(node["value"]) + ")"
    if kind == "binary": return "(" + basic_expression(node["left"]) + " " + node["op"] + " " + basic_expression(node["right"]) + ")"
    if kind == "call": return basic_expression(node["object"]) + "(" + ", ".join(basic_expression(a) for a in node["args"]) + ")"
    if kind == "member":
        if node["name"] in ("value", "value2", "formula"):
            cell=uno_cell(node["object"])
            return cell+".Formula" if node["name"]=="formula" else "MFGet("+cell+")"
        return basic_expression(node["object"]) + "." + node["name"]
    raise vba.Unsupported("Unknown expression")


def uno_cell(node):
    if node["kind"] != "call" or node["object"]["kind"] != "member":
        raise vba.Unsupported("Native UNO requires an explicit worksheet and cell")
    member = node["object"]
    sheet = member["object"]
    if sheet["kind"] != "call" or sheet["object"].get("name") not in ("worksheets", "sheets") or len(sheet["args"]) != 1:
        raise vba.Unsupported("Native UNO requires Worksheets(name)")
    if member["name"] == "range" and len(node["args"]) == 1:
        return "MFRange(" + basic_expression(sheet["args"][0]) + ", " + basic_expression(node["args"][0]) + ")"
    if member["name"] == "cells" and len(node["args"]) == 2:
        return "MFCells(" + ", ".join(basic_expression(a) for a in sheet["args"] + node["args"]) + ")"
    raise vba.Unsupported("Native UNO supports Range and Cells assignments")


def basic(source, findings, native=False):
    output = ["Option VBASupport 1"]
    todos, rewrites = [], []
    by_line = {}
    shadowed=bool(re.search(r'(?im)\b(?:Dim|Static|Sub|Function)\s+VBA\b|^Attribute\s+VB_Name\s*=\s*"VBA"',source))
    for finding in findings:
        if finding.get("line"):
            by_line.setdefault(finding["line"], []).append(finding)
    for number, line in enumerate(source.replace("\r\n", "\n").replace("\r", "\n").splitlines(), 1):
        if re.match(r"(?i)^\s*attribute\b|^\s*option\s+vbasupport\b", line):
            continue
        for finding in by_line.get(number, []):
            message = finding["messages"][0]
            output.append("' MACROFERRY TODO(" + finding["rule_id"] + "): " + message)
            todos.append({"line": number, "rule_id": finding["rule_id"], "reason": message})
        replacement, ids = basic_intrinsics(line)
        if ids and not shadowed and not re.match(r'(?i)^\s*rem\b',line):
            rewrites.extend({"line":number,"rule_id":rule,"before":line,"after":replacement} for rule in ids)
            line=replacement
        elif ids and shadowed:
            output.append("' MACROFERRY TODO: VBA identifier is shadowed; review qualified intrinsics")
            todos.append({"line":number,"reason":"VBA identifier is shadowed"})
        if native and re.search(r"(?i)\b(range|cells)\s*\(", line):
            try:
                parts = list(vba.split_statements(line))
                if len(parts) != 1 or "=" not in parts[0][1]:
                    raise vba.Unsupported("Native UNO rewrite requires a single assignment")
                statement = parts[0][1]
                left, right = statement.split("=", 1)
                node = vba.expression(left.strip())
                if node["kind"] != "member" or node["name"] not in ("value", "value2", "formula"):
                    raise vba.Unsupported("Native UNO rewrite supports Value and Formula")
                cell = uno_cell(node["object"])
                rhs = vba.expression(right.strip())
                if node["name"] == "formula":
                    replacement = cell + ".Formula = " + basic_expression(rhs)
                else:
                    replacement = "MFSet " + cell + ", " + basic_expression(rhs)
                output.append(replacement)
                rewrites.append({"line": number, "rule_id": "UNO-RANGE-SET", "before": line, "after": replacement})
                continue
            except vba.Unsupported as error:
                output.append("' MACROFERRY TODO(UNO-MANUAL): " + str(error))
                todos.append({"line": number, "rule_id": "UNO-MANUAL", "reason": str(error)})
        output.append(line)
    if native:
        output.append(UNO_HELPERS)
    return {"source": "\n".join(output) + "\n", "todos": todos, "rewrites": rewrites}


def convert(input_path, destination, binary, target="basic", libreoffice=None):
    input_path, destination = office.local_path(input_path), office.local_path(destination)
    if destination.exists() and any(destination.iterdir()):
        raise FileExistsError("Conversion destination must be new or empty")
    if not input_path.is_file():
        raise FileNotFoundError(input_path)
    destination.mkdir(parents=True, exist_ok=True)
    subprocess.run([str(Path(binary).resolve()), "extract", str(input_path), "--out", str(destination / "inventory")], check=True, capture_output=True, timeout=120)
    inventory = json.loads((destination / "inventory/scan.json").read_text(encoding="utf-8"))
    workbook = inventory["workbooks"][0]
    modules, records = {}, []
    source_dir = destination / "source"
    source_dir.mkdir()
    for index, module in enumerate(workbook["modules"]):
        name = module["name"]
        safe = re.sub(r"[^\w-]", "_", name)
        original = source_dir / f"{index:04d}-{safe}.original.bas"
        original.write_text(module["source"], encoding="utf-8")
        if target in ("basic", "basic-uno"):
            result = basic(module["source"], module["findings"], target == "basic-uno")
            candidate = source_dir / f"{index:04d}-{safe}.bas"
            if module["kind"] != "standard" and module["code_lines"]:
                result["todos"].append({"line": 1, "reason": "Document events, classes and form layouts require manual wiring"})
            modules[name] = result["source"]
        else:
            result = vba.to_python(module["source"])
            candidate = source_dir / f"{safe.lower()}.py"
            if candidate.exists():
                raise ValueError("Module names collide in the Python target")
            for finding in module["findings"]:
                if finding["verdict"] in ("needs_rewrite", "unknown"):
                    result["todos"].append({"line": finding.get("line"), "rule_id": finding["rule_id"], "reason": finding["messages"][0]})
        candidate.write_text(result["source"], encoding="utf-8")
        diff = candidate.with_suffix(candidate.suffix + ".diff")
        diff.write_text("".join(difflib.unified_diff(module["source"].splitlines(True), result["source"].splitlines(True), fromfile=name + ".original", tofile=candidate.name)), encoding="utf-8")
        records.append({"name": name, "kind": module["kind"], "original": original.relative_to(destination).as_posix(), "candidate": candidate.relative_to(destination).as_posix(), "diff": diff.relative_to(destination).as_posix(), "todos": result["todos"], "rewrites": result.get("rewrites", []), "procedures": result.get("procedures", [])})
    if target in ("basic", "basic-uno"):
        office.run({"mode": "convert", "input": str(input_path), "output": str(destination / "converted.ods"), "modules": modules}, libreoffice)
    else:
        package = destination / "migration"
        package.mkdir()
        for filename in ("__init__.py", "runtime.py"):
            shutil.copyfile(Path(__file__).parent / filename, package / filename)
        if target == "python":
            (destination / "requirements.txt").write_text("openpyxl==3.1.5\n", encoding="utf-8")
        else:
            office.run({"mode": "convert", "input": str(input_path), "output": str(destination / "converted.ods"), "modules": {}}, libreoffice)
    queries=[]
    if workbook['queries']:
        from migration.m_runtime import convert as convert_m
        for index,query in enumerate(workbook['queries']):
            original=source_dir/f'query-{index:04d}.original.m'
            original.write_text(query['source'],encoding='utf-8')
            item={'name':query['name'],'original':original.relative_to(destination).as_posix()}
            try:
                directory=destination/'power-query'/f'{index:04d}'
                summary=convert_m(original,directory)
                item.update(candidate=(directory/'query.py').relative_to(destination).as_posix(),queries=summary['queries'],todos=summary['todos'])
            except ValueError as error:item['todos']=[{'reason':str(error)}]
            queries.append(item)
    report = {"schema_version": "1", "status": "candidate", "verified": False, "input": str(input_path), "input_sha256": hashlib.sha256(input_path.read_bytes()).hexdigest(), "target": target, "modules": records, "power_queries":queries, "workbook_findings": workbook["findings"], "automatic_execution": False, "limitations": ["Review every TODO and supply a golden case before adopting a candidate", "Events, UserForms, external links and embedded controls need manual migration", "Power Query scripts require pandas and a separate table comparison; ODS does not refresh M queries"]}
    (destination / "conversion.json").write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return report
