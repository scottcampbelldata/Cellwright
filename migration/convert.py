# SPDX-License-Identifier: EUPL-1.2
"""Assisted conversion: preserve originals, produce candidates and reviewable diffs."""
import difflib
import hashlib
import json
import re
import shutil
import subprocess
from pathlib import Path

from migration import controls, formatting, office, operations, ui, vba

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
    range = ThisComponent.Sheets.getByName(sheetName).getCellRangeByName(address)
    MFRange = MFOnlyCell(range)
End Function
Function MFOnlyCell(range As Object) As Object
    Dim bounds
    bounds = range.getRangeAddress()
    If bounds.StartRow <> bounds.EndRow Or bounds.StartColumn <> bounds.EndColumn Then
        Err.Raise 5, "Cellwright", "Native UNO multi-cell values require manual migration"
    End If
    MFOnlyCell = range.getCellByPosition(0, 0)
End Function
Function MFCells(sheetName As String, row As Long, column As Long) As Object
    MFCells = ThisComponent.Sheets.getByName(sheetName).getCellByPosition(column - 1, row - 1)
End Function
Function MFGet(cell As Object) As Variant
    If cell.getError() <> 0 Then
        Err.Raise 5, "Cellwright", "Cell errors require manual migration"
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


def basic_expression(node, ranges=()):
    kind = node["kind"]
    if kind == "literal": return '"' + node["value"].replace('"', '""') + '"'
    if kind == "number": return node["value"]
    if kind == "identifier": return str(formatting.CONSTANTS[node["name"]]) if node["name"] in formatting.CONSTANTS else node["name"]
    if kind == "unary": return "(" + node["op"] + " " + basic_expression(node["value"], ranges) + ")"
    if kind == "binary": return "(" + basic_expression(node["left"], ranges) + " " + node["op"] + " " + basic_expression(node["right"], ranges) + ")"
    if kind == "call":
        obj = node["object"]
        rgb = obj.get("name") == "rgb" and (obj["kind"] == "identifier" or obj["kind"] == "member" and obj["object"].get("name") == "vba")
        callee = "MFVbaRGB" if rgb else basic_expression(obj, ranges)
        return callee + "(" + ", ".join(basic_expression(a, ranges) for a in node["args"]) + ")"
    if kind == "member":
        if formatting.target(node): raise vba.Unsupported("Reading formatting properties requires manual migration")
        if node["name"] in ("value", "value2", "formula"):
            cell=uno_cell(node["object"], ranges=ranges)
            return cell+".Formula" if node["name"]=="formula" else "MFGet("+cell+")"
        return basic_expression(node["object"], ranges) + "." + node["name"]
    raise vba.Unsupported("Unknown expression")


def uno_cell(node, format_range=False, ranges=()):
    if node["kind"] == "identifier" and node["name"] in ranges:
        return node["name"] if format_range else "MFOnlyCell(" + node["name"] + ")"
    if node["kind"] != "call" or node["object"]["kind"] != "member":
        raise vba.Unsupported("Native UNO requires an explicit worksheet and cell")
    member = node["object"]
    sheet = member["object"]
    if sheet["kind"] != "call" or sheet["object"].get("name") not in ("worksheets", "sheets") or len(sheet["args"]) != 1:
        raise vba.Unsupported("Native UNO requires Worksheets(name)")
    if member["name"] == "range" and len(node["args"]) == 1:
        return ("MFFormatRange(" if format_range else "MFRange(") + basic_expression(sheet["args"][0]) + ", " + basic_expression(node["args"][0]) + ")"
    if member["name"] == "cells" and len(node["args"]) == 2:
        return "MFCells(" + ", ".join(basic_expression(a) for a in sheet["args"] + node["args"]) + ")"
    raise vba.Unsupported("Native UNO supports Range and Cells assignments")


def basic(source, findings, native=False):
    output = ["Option VBASupport 1"]
    todos, rewrites = [], []
    has_formatting = False
    has_operations = False
    created_sheets = set()
    contexts, ranges = [], set()
    nodes, source_tokens = vba.syntax(source), set(vba.tokens(source))
    reserved = set(formatting.CONSTANTS) | {"rgb", "mfformat", "mfformatrange", "mfvbargb", "mfrange", "mfonlycell", "mfget", "mfset", "mfcells"}
    formatting_shadowed = any(set(vba.tokens(node["source"])) & reserved for node in nodes
                              if node["kind"] == "procedure" or re.match(r"(?i)^(dim|static|const)\b", node["source"]))
    operation_names=set(operations.CONSTANTS)|{'mfclear','mfcopy','mfsort','mffilter','mfaddsheet','mfrenamesheet','mfrangebound'}
    operation_shadowed=any(set(vba.tokens(node['source'])) & operation_names for node in nodes if node['kind']=='procedure' or re.match(r'(?i)^(dim|static|const|private|public)\b',node['source']))
    uses_formatting = any(formatting.has_property(vba.tokens(node["source"])) for node in nodes)
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
            output.append("' CELLWRIGHT TODO(" + finding["rule_id"] + "): " + message)
            todos.append({"line": number, "rule_id": finding["rule_id"], "reason": message})
        replacement, ids = basic_intrinsics(line)
        if ids and not shadowed and not re.match(r'(?i)^\s*rem\b',line):
            rewrites.extend({"line":number,"rule_id":rule,"before":line,"after":replacement} for rule in ids)
            line=replacement
        elif ids and shadowed:
            output.append("' CELLWRIGHT TODO: VBA identifier is shadowed; review qualified intrinsics")
            todos.append({"line":number,"reason":"VBA identifier is shadowed"})
        parts = list(vba.split_statements(line))
        statement = " : ".join(part for _, part in parts)
        context = contexts[-1] if contexts else None
        if statement.lower().startswith("with "):
            try:
                if not native and not uses_formatting: raise vba.Unsupported("Keep compatibility With unchanged")
                if formatting_shadowed: raise vba.Unsupported("Formatting names are shadowed")
                value = statement[5:]
                if value.startswith("."):
                    if not context: raise vba.Unsupported("Member outside a supported With range")
                    value = context + value
                root = vba.expression(value)
                if root["kind"] == "member" and root["name"] in ("font", "interior"):
                    uno_cell(root["object"], True, ranges)
                    contexts.append(value)
                    replacement = "If True Then"
                else:
                    cell = uno_cell(root, True, ranges)
                    alias = "mfwith" + str(number)
                    while alias in source_tokens: alias += "x"
                    ranges.add(alias)
                    contexts.append(alias)
                    replacement = "Dim " + alias + " As Object\nSet " + alias + " = " + cell + "\nIf True Then"
                output.append(replacement)
                has_formatting = True
                rewrites.append({"line": number, "rule_id": "FORMAT-WITH", "before": line, "after": replacement})
                continue
            except vba.Unsupported as error:
                contexts.append(None)
                if uses_formatting or context:
                    output.append("' CELLWRIGHT TODO(UNO-MANUAL): " + str(error))
                    todos.append({"line": number, "rule_id": "UNO-MANUAL", "reason": str(error)})
        elif statement.lower() == "end with" and contexts:
            if contexts.pop():
                output.append("End If")
                rewrites.append({"line": number, "rule_id": "FORMAT-WITH", "before": line, "after": "End If"})
                continue
        if statement.startswith(".") and context: statement = context + statement
        if re.search(r'(?i)\.(clearcontents|clear|copy|sort|autofilter)\b', statement) and not statement.startswith("'"):
            try:
                if len(parts) != 1: raise vba.Unsupported("Compound range operations need manual migration")
                if operation_shadowed: raise vba.Unsupported("Operation constants or helpers are shadowed")
                replacement = operations.basic(statement,ranges)
                if replacement:
                    output.append(replacement)
                    rewrites.append({"line":number,"rule_id":"RANGE-OPERATION","before":line,"after":replacement})
                    has_operations = True
                    continue
            except vba.Unsupported as error:
                output.append("' CELLWRIGHT TODO(RANGE-MANUAL): "+str(error))
                todos.append({"line":number,"rule_id":"RANGE-MANUAL","reason":str(error)})
        if native and "name" in set(vba.tokens(statement)):
            try:
                replacement=operations.rename(statement,created_sheets)
                if replacement:
                    output.append(replacement)
                    rewrites.append({"line":number,"rule_id":"SHEET-RENAME","before":line,"after":replacement})
                    has_operations=True
                    continue
            except vba.Unsupported: pass
        if native and re.fullmatch(r'(?i)\s*(?:Set\s+)?[A-Za-z_]\w*\s*=\s*(?:Worksheets|Sheets)\.Add(?:\(\s*\))?\s*', statement):
            created_sheets.add(vba.assignment(statement)[0]["name"])
            replacement=re.sub(r'(?i)(?:Worksheets|Sheets)\.Add(?:\(\s*\))?', 'MFAddSheet()', statement)
            output.append(replacement)
            rewrites.append({"line":number,"rule_id":"SHEET-ADD","before":line,"after":replacement})
            has_operations=True
            continue
        token_list = vba.tokens(statement)
        words = set(token_list)
        is_formatting = formatting.has_property(token_list)
        if is_formatting or ("with" not in words and (native and bool(words & {"range", "cells"}) or bool(words.intersection(ranges)) or context and "." in words)):
            try:
                if not parts:
                    output.append(line)
                    continue
                if len(parts) != 1 or "=" not in parts[0][1]:
                    raise vba.Unsupported("UNO rewrite requires a single assignment; compound/continued statements need review")
                pair = vba.assignment(statement)
                if pair is None: raise vba.Unsupported("UNO rewrite requires an assignment")
                node, rhs = pair
                formatted = formatting.target(node)
                if formatted:
                    if formatting_shadowed or shadowed: raise vba.Unsupported("Formatting constants, RGB or helper names are shadowed")
                    root, prop = formatted
                    formatting.check_expression(prop, rhs)
                    replacement = 'MFFormat ' + uno_cell(root, True, ranges) + ', "' + prop + '", ' + basic_expression(rhs, ranges)
                    output.append(replacement)
                    rewrites.append({"line": number, "rule_id": "FORMAT-" + prop.upper().replace(".", "-"), "before": line, "after": replacement})
                    has_formatting = True
                    continue
                if not native and not words.intersection(ranges):
                    output.append(line)
                    continue
                if node["kind"] != "member" or node["name"] not in ("value", "value2", "formula"):
                    raise vba.Unsupported("Native UNO rewrite supports Value and Formula")
                cell = uno_cell(node["object"], ranges=ranges)
                if node["name"] == "formula":
                    replacement = cell + ".Formula = " + basic_expression(rhs, ranges)
                else:
                    replacement = "MFSet " + cell + ", " + basic_expression(rhs, ranges)
                output.append(replacement)
                rewrites.append({"line": number, "rule_id": "UNO-RANGE-SET", "before": line, "after": replacement})
                continue
            except (vba.Unsupported, NotImplementedError) as error:
                output.append("' CELLWRIGHT TODO(UNO-MANUAL): " + str(error))
                todos.append({"line": number, "rule_id": "UNO-MANUAL", "reason": str(error)})
        output.append(line)
    if contexts:
        todos.append({"reason": "Unclosed With block requires manual migration"})
    if has_operations: output.append(operations.helpers())
    if native or has_formatting or has_operations:
        output.append(UNO_HELPERS)
    if has_formatting or 'MFVbaRGB(' in '\n'.join(output): output.append(formatting.basic_helpers())
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
    ui_specs = ui.inventory(workbook, input_path)
    modules, records = {}, []
    source_dir = destination / "source"
    source_dir.mkdir()
    for index, module in enumerate(workbook["modules"]):
        name = module["name"]
        safe = re.sub(r"[^\w-]", "_", name)
        original = source_dir / f"{index:04d}-{safe}.original.bas"
        original.write_text(module["source"], encoding="utf-8")
        if target in ("basic", "basic-uno"):
            lowered = ui.rewrite(module["source"], name, ui_specs) if ui_specs else {"source":module["source"], "todos":[], "rewrites":[]}
            result = basic(lowered["source"], module["findings"], target == "basic-uno")
            result["todos"].extend(lowered["todos"])
            result["rewrites"].extend(lowered["rewrites"])
            candidate = source_dir / f"{index:04d}-{safe}.bas"
            if module["kind"] != "standard" and module["code_lines"] and not any(spec["name"] == name for spec in ui_specs):
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
        records.append({"name": name, "kind": module["kind"], "original": original.relative_to(destination).as_posix(), "candidate": candidate.relative_to(destination).as_posix(), "diff": diff.relative_to(destination).as_posix(), "todos": result["todos"], "rewrites": result.get("rewrites", []), "procedures": [{"name":node["name"], "parameters":node["parameters"], "kind":node["procedure_kind"]} for node in vba.syntax(module["source"]) if node["kind"]=="procedure"]})
    buttons = {"records": [], "wrapper_source": ""}
    if target in ("basic", "basic-uno"):
        eligible = controls.handlers(workbook["modules"], records)
        features = set(workbook.get("features", []))
        if "activex" in features and not any(spec["scope"]=="sheet" for spec in ui_specs):
            for handler in eligible:handler["reason"]="ActiveX control inventory is incomplete; wire manually"
        if features & {"legacy_features_uninspected", "binary_features_uninspected", "vml_uninspected", "oversized_parts_uninspected"}:
            for handler in eligible: handler["reason"] = "Incomplete control coverage requires manual migration"
        for spec in ui_specs:
            module = next((m for m in workbook["modules"] if m["name"]==spec["name"]),None)
            record = next((r for r in records if r["name"]==spec["name"]),None)
            spec["callbacks"] = ui.bindings(module, spec) if module else []
            for index, callback in enumerate(spec["callbacks"]):
                if callback["status"] != "candidate": continue
                if not ui.NAME.fullmatch(spec["name"]) or record is None or record["todos"] or spec.get("error"):
                    callback.update(status="manual", reason="Handler module or control inventory has unresolved work")
                    continue
                wrapper = "MFUIEvent"+str(index+1)
                while wrapper.lower() in set(vba.tokens(module["source"])): wrapper += "X"
                callback["wrapper"] = wrapper
                modules[spec["name"]] += "\nPublic Sub "+wrapper+"(event As Object)\n    "+callback["procedure"]+"\nEnd Sub\n"
        if ui_specs:
            helper_name="CellwrightUI"
            while helper_name.lower() in {name.lower() for name in modules}:helper_name += "X"
            modules[helper_name] = ui.helpers(ui_specs)
        converted = office.run({"mode": "convert", "input": str(input_path), "output": str(destination / "converted.ods"), "modules": modules, "button_handlers": eligible, "ui":ui_specs}, libreoffice)
        buttons = converted["buttons"]
    else:
        package = destination / "migration"
        package.mkdir()
        for filename in ("__init__.py", "runtime.py", "formatting.py"):
            shutil.copyfile(Path(__file__).parent / filename, package / filename)
        if target == "python":
            (destination / "requirements.txt").write_text("openpyxl==3.1.5\n", encoding="utf-8")
        else:
            buttons = office.run({"mode": "convert", "input": str(input_path), "output": str(destination / "converted.ods"), "modules": {}}, libreoffice)["buttons"]
    if buttons["wrapper_source"]:
        candidate = source_dir / "button-wrappers.bas"
        candidate.write_text(buttons["wrapper_source"], encoding="utf-8")
        buttons["candidate"] = candidate.relative_to(destination).as_posix()
    del buttons["wrapper_source"]
    handled = {record["before"] for record in buttons["records"] if record["status"] == "rewritten"}
    for assignment in workbook.get("macro_assignments", []):
        try:
            handler = controls.resolve(assignment, "StarBasic", controls.handlers(workbook["modules"], records), input_path.name)
            matched = any(record.get("handler", "").lower() == (handler["module"] + "." + handler["procedure"]).lower() for record in buttons["records"])
        except ValueError: matched = assignment in handled
        if not matched:
            buttons["records"].append({"status": "manual", "before": assignment, "reason": "Source assignment has no matching imported button; recreate and wire manually"})
    if "macro_assignment" in workbook.get("features", []) and not buttons["records"]:
        buttons["records"].append({"status": "manual", "before": "Button/shape assignments", "reason": "No readable imported button binding in this target; wire manually"})
    interfaces = converted.get("user_interfaces",[]) if target in ("basic", "basic-uno") else []
    if target not in ("basic", "basic-uno"):
        interfaces = [{"name":spec["name"], "scope":spec["scope"], "status":"manual", "reason":"This target exports routines only; migrate the interface with the Basic target or manual recipes", "records":[]} for spec in ui_specs]
    for index, interface in enumerate(interfaces):
        for key, suffix in (("original_xml", ".original.xdl"),("candidate_xml", ".xdl")):
            if key in interface:
                path = source_dir / ("dialog-"+str(index)+suffix)
                path.write_text(interface.pop(key), encoding="utf-8")
                interface["original" if key=="original_xml" else "candidate"] = path.relative_to(destination).as_posix()
    for record in records:
        if record["name"] in modules:
            candidate=destination/record["candidate"]
            candidate.write_text(modules[record["name"]],encoding="utf-8")
            original=(destination/record["original"]).read_text(encoding="utf-8")
            (destination/record["diff"]).write_text("".join(difflib.unified_diff(original.splitlines(True), modules[record["name"]].splitlines(True), fromfile=record["name"]+".original", tofile=candidate.name)),encoding="utf-8")
    if ui_specs and target in ("basic", "basic-uno"):
        (source_dir/"ui-helpers.bas").write_text(modules[helper_name],encoding="utf-8")
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
    report = {"schema_version": "1", "status": "candidate", "verified": False, "input": str(input_path), "input_sha256": hashlib.sha256(input_path.read_bytes()).hexdigest(), "target": target, "modules": records, "buttons": buttons, "user_interfaces":interfaces, "power_queries":queries, "workbook_findings": workbook["findings"], "automatic_execution": False, "limitations": ["Review every TODO and supply a golden case before adopting a candidate", "Common imported dialog and worksheet controls have local candidates; custom controls, lifecycle events and missing layouts need manual migration", "Power Query scripts require pandas and a separate table comparison; ODS does not refresh M queries"]}
    from migration.checklist import checklist
    report["checklist"] = checklist(report)
    (destination / "conversion.json").write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return report


def todo_count(report):
    return (sum(len(module["todos"]) for module in report["modules"])
            + sum(len(query["todos"]) for query in report.get("power_queries", []))
            + sum(record["status"] == "manual" for record in report.get("buttons", {}).get("records", []))
            + sum(item["status"] == "manual" for item in report.get("user_interfaces", []))
            + sum(record["status"] == "manual" for item in report.get("user_interfaces", []) for record in item.get("records", [])))
