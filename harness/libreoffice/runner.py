# SPDX-License-Identifier: EUPL-1.2
"""UNO worker: no automatic macro execution or link updates when opening files."""
import importlib.util
import json
import sys
import time
from pathlib import Path

import uno

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


def property_value(name, value):
    prop = uno.createUnoStruct("com.sun.star.beans.PropertyValue")
    prop.Name, prop.Value = name, value
    return prop


def snapshot(document, ranges):
    from migration.runtime import coordinates, column_name
    result, total = {}, 0
    for sheet_name, addresses in ranges.items():
        sheet, cells = document.Sheets.getByName(sheet_name), {}
        for address in addresses:
            r1, c1, r2, c2 = coordinates(address)
            total += (r2 - r1 + 1) * (c2 - c1 + 1)
            if total > 100_000:
                raise ValueError("Snapshot exceeds 100,000 cells")
            for row in range(r1, r2 + 1):
                for column in range(c1, c2 + 1):
                    cell = sheet.getCellByPosition(column - 1, row - 1)
                    typ = str(cell.getType().value)
                    value = None if typ == "EMPTY" else cell.String if typ == "TEXT" else cell.Value
                    if cell.getError():
                        value = {"error": cell.getError(), "text": cell.String}
                    formula = cell.Formula if typ == "FORMULA" else None
                    cells[column_name(column) + str(row)] = {"value": value, "formula": formula}
        result[sheet_name] = cells
    return {"schema_version": "1", "engine": "libreoffice", "sheets": result}


def main():
    pipe = sys.argv[1]
    job = json.load(sys.stdin)
    local = uno.getComponentContext()
    resolver = local.ServiceManager.createInstanceWithContext("com.sun.star.bridge.UnoUrlResolver", local)
    context = None
    for _ in range(600):
        try:
            context = resolver.resolve("uno:pipe,name=" + pipe + ";urp;StarOffice.ComponentContext")
            break
        except Exception:
            time.sleep(0.1)
    if context is None:
        raise TimeoutError("LibreOffice UNO connection timed out")
    desktop = context.ServiceManager.createInstanceWithContext("com.sun.star.frame.Desktop", context)
    options = [property_value("Hidden", True), property_value("ReadOnly", False), property_value("MacroExecutionMode", 0), property_value("UpdateDocMode", 0)]
    from migration.office import local_path
    document = desktop.loadComponentFromURL(local_path(job["input"]).as_uri(), "_blank", 0, tuple(options))
    if document is None:
        raise ValueError("LibreOffice could not load the workbook")
    try:
        if job["mode"] == "convert":
            libraries = document.BasicLibraries
            for name in tuple(libraries.getElementNames()):
                if name != "Standard":libraries.removeLibrary(name)
            for target in (document, *tuple(document.Sheets.getByIndex(index) for index in range(document.Sheets.Count))):
                for event in target.Events.getElementNames():
                    uno.invoke(target.Events,"replaceByName",(event,uno.Any("[]com.sun.star.beans.PropertyValue",())))
            if not libraries.hasByName("Standard"):
                libraries.createLibrary("Standard")
            library = libraries.getByName("Standard")
            # Imported code is replaced; preserved originals are in the conversion source archive.
            for name in tuple(library.getElementNames()): library.removeByName(name)
            for name, source in job["modules"].items(): library.insertByName(name, source)
            from migration.controls import rebind
            buttons = rebind(document, job.get("button_handlers", []), job["input"], job["modules"], uno)
            if buttons["wrapper_source"]:
                library.insertByName(buttons["wrapper_module"], buttons["wrapper_source"])
            document.storeAsURL(local_path(job["output"]).as_uri(), (property_value("FilterName", "calc8"), property_value("Overwrite", False)))
            result = {"output": job["output"], "module_names": list(job["modules"]), "status": "candidate", "buttons": buttons}
        elif job["mode"] == "capture":
            if job.get("macro"):
                if not job.get("allow_execution"):
                    raise PermissionError("Execution requires --allow-execution")
                if job.get("python_module"):
                    from migration.runtime import Workbook
                    from migration.vba import safe_name
                    spec = importlib.util.spec_from_file_location("converted_macro", job["python_module"])
                    module = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(module)
                    module.configure(Workbook(document, uno=True))
                    getattr(module, safe_name(job["macro"].lower()))(*job.get("inputs", []))
                else:
                    # Invoke only the requested routine; loading with NEVER_EXECUTE suppresses open events.
                    script = document.getScriptProvider().getScript("vnd.sun.star.script:" + job["macro"] + "?language=Basic&location=document")
                    script.invoke(tuple(job.get("inputs", [])), (), ())
            document.calculateAll()
            result = snapshot(document, job["ranges"])
            if job.get("output_workbook"):
                document.storeAsURL(local_path(job["output_workbook"]).as_uri(), (property_value("FilterName", "calc8"), property_value("Overwrite", False)))
        else:
            raise ValueError("Unknown UNO job mode")
        print(json.dumps(result, ensure_ascii=True))
    finally:
        document.close(True)
        desktop.terminate()


if __name__ == "__main__":
    main()
