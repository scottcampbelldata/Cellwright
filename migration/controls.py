# SPDX-License-Identifier: EUPL-1.2
"""Reconnect imported push buttons to known Basic routines without invoking scripts."""
import re
from pathlib import Path
from urllib.parse import parse_qs, unquote

from migration import vba


def handlers(modules, records):
    result = []
    for module, record in zip(modules, records):
        for node in vba.syntax(module["source"]):
            if node["kind"] != "procedure": continue
            reason = None
            if module["kind"] != "standard": reason = "Document, class and UserForm handlers require manual wiring"
            elif record["todos"]: reason = "Handler module has unresolved TODOs"
            elif node["name"] in ("auto_open", "auto_close") or node["name"].startswith(("workbook_", "worksheet_")):
                reason = "Automatic event handlers require manual wiring"
            elif node["procedure_kind"] != "sub" or node["parameters"].strip(): reason = "Button handler must be a parameterless Sub"
            elif re.match(r"(?i)^(private|friend)\b", node["source"]): reason = "Button handler must be public"
            elif re.search(r"(?im)^\s*Option\s+Private\s+Module\b", module["source"]): reason = "Private modules require manual wiring"
            if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*", module["name"]): reason = "Module name cannot be used in a Basic callback"
            result.append({"module": module["name"], "procedure": node["name"], "reason": reason})
    return result


def resolve(code, script_type, known, workbook):
    document_local = False
    if script_type == "Script" and code.startswith("vnd.sun.star.script:"):
        name, _, query = code[len("vnd.sun.star.script:"):].partition("?")
        if parse_qs(query) != {"language": ["Basic"], "location": ["document"]}:
            raise ValueError("Only document-local Basic callbacks can be rebound")
        name = unquote(name)
        document_local = True
    elif script_type == "StarBasic": name = code
    else: raise ValueError("Unsupported callback language or location")
    if "!" in name:
        owner, name = name.rsplit("!", 1)
        if owner not in ("[0]", workbook, "'" + workbook + "'"):
            raise ValueError("External workbook callbacks require manual migration")
    parts = name.split(".")
    if len(parts) == 3 and (document_local or parts[0].lower() in ("standard", "vbaproject")):
        if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*", parts[0]): raise ValueError("Invalid callback library name")
        parts = parts[1:]
    if len(parts) not in (1, 2) or any(not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*", part) for part in parts):
        raise ValueError("Callback name or arguments require manual migration")
    matches = [entry for entry in known if entry["procedure"].lower() == parts[-1].lower()
               and (len(parts) == 1 or entry["module"].lower() == parts[0].lower())]
    if len(matches) != 1: raise ValueError("Callback is missing or ambiguous")
    if matches[0]["reason"]: raise ValueError(matches[0]["reason"])
    return matches[0]


def rebind(document, known, workbook, module_names, uno):
    records, wrappers = [], []
    wrapper_module = "MacroFerryButtons"
    while wrapper_module.lower() in {name.lower() for name in module_names}: wrapper_module += "X"
    count = 0

    def visit(container, sheet, path, depth=0):
        nonlocal count
        if depth > 32: raise ValueError("Form hierarchy exceeds 32 levels")
        for index in range(container.getCount()):
            count += 1
            if count > 10000: raise ValueError("Form hierarchy exceeds 10,000 components")
            model = container.getByIndex(index)
            events = tuple(container.getScriptEvents(index))
            container.revokeScriptEvents(index)
            name = path + "/" + model.Name
            button = model.supportsService("com.sun.star.form.component.CommandButton")
            if button and not events:
                records.append({"sheet": sheet, "control": name, "status": "manual", "reason": "Imported button has no readable callback", "before": ""})
            for event in events:
                record = {"sheet": sheet, "control": name, "event": event.EventMethod, "listener": event.ListenerType, "parameter": event.AddListenerParam, "before": event.ScriptCode, "status": "manual"}
                records.append(record)
                try:
                    if not button or len(events) != 1 or event.ListenerType not in ("XActionListener", "com.sun.star.awt.XActionListener") or event.EventMethod != "actionPerformed" or event.AddListenerParam:
                        raise ValueError("Only a single push-button action callback is supported")
                    if model.ButtonType.value != "PUSH" or model.Toggle or model.TargetURL:
                        raise ValueError("URL, submit, reset and toggle buttons require manual migration")
                    handler = resolve(event.ScriptCode, event.ScriptType, known, Path(workbook).name)
                    routine = "Button" + str(len(wrappers) + 1)
                    wrappers.append("Sub " + routine + "(actionEvent As Object)\n    " + handler["module"] + "." + handler["procedure"] + "\nEnd Sub\n")
                    replacement = uno.createUnoStruct("com.sun.star.script.ScriptEventDescriptor")
                    replacement.ListenerType, replacement.EventMethod = event.ListenerType, event.EventMethod
                    replacement.AddListenerParam, replacement.ScriptType = "", "Script"
                    replacement.ScriptCode = "vnd.sun.star.script:Standard." + wrapper_module + "." + routine + "?language=Basic&location=document"
                    container.registerScriptEvent(index, replacement)
                    record.update(status="rewritten", rule_id="BUTTON-ACTION", after=replacement.ScriptCode, handler=handler["module"] + "." + handler["procedure"])
                except ValueError as error: record["reason"] = str(error)
            if model.supportsService("com.sun.star.form.component.Form"):
                visit(model, sheet, name, depth + 1)

    for index in range(document.Sheets.Count):
        sheet = document.Sheets.getByIndex(index)
        visit(sheet.DrawPage.Forms, sheet.Name, "")
    return {"records": records, "wrapper_module": wrapper_module, "wrapper_source": "\n".join(wrappers)}
