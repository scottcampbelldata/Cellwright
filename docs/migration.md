# Conversion and execution comparison

Use the full distribution archive for conversion and the dashboard. Python 3.11+ is required; LibreOffice Basic and Python UNO targets also require LibreOffice and its UNO Python. The single scanner executable needs neither. Standalone Python and M targets require the pinned optional packages in `requirements.txt`.

```powershell
macroferry.exe serve --port 8768 --data .\reports\dashboard
macroferry.exe convert .\Budget.xlsm --out .\candidate --target basic
macroferry.exe convert .\Budget.xlsm --out .\native --target basic-uno
macroferry.exe convert .\Budget.xlsm --out .\python-candidate --target python-uno
macroferry.exe convert .\Budget.xlsm --out .\standalone --target python
```

The dashboard is at http://127.0.0.1:8768 or http://localhost:8768. It stores scan history, assignments, notes, conversion jobs, verification evidence and schedules in a local SQLite database. Scheduled scans run while the server runs; schedules default to source-free reports. Verification requires starting it with `serve --allow-execution` and checking the consent box for each case. Local programs can obtain its session token; enabling this flag grants them execution capability. Keep the default for routine scanning/conversion. On Linux, fill in the saved Excel capture JSON path in the comparison dialog; it must cover the same routine, inputs and cells. Use separate data directories for separate teams. This release binds only to loopback; remote users, TLS and multi-user access control require a separate deployment design.

The launcher tries `python`, falling back to `python3` only when the first executable is missing. Set `MACROFERRY_PYTHON` to select an explicit interpreter; errors from that interpreter are reported without retry. Set `MACROFERRY_LIBREOFFICE` to LibreOffice's `program` directory, or pass `--libreoffice` to conversion/capture/verify. On Linux install LibreOffice Calc and `python3-uno`. The UNO worker defaults to `/usr/bin/python3` on Linux and the installed LibreOffice `program/python.exe` on Windows. Set `MACROFERRY_UNO_PYTHON` to the full path of another interpreter with UNO available. Development-cache LibreOffice installations are used only when explicitly selected.

Conversion never runs macros. It writes a new destination, original source, candidates, unified diffs and `conversion.json`. Basic targets create a new `converted.ods`, remove other imported Basic libraries and document/sheet event bindings, and install the generated Standard modules. Review embedded controls and other event bindings manually. Source workbooks are preserved. Conversion status remains **candidate**, even when a separately recorded test case passes.

The Basic converter has 40 named rules that remove a qualified `VBA.` prefix from supported language intrinsics, preserving strings/comments, plus targeted tree-based Range/Cells Value, Value2 and Formula rewrites. The intrinsic rules are:

```text
Abs Asc Chr CInt CLng CDbl CStr Date DateAdd Day Fix Hex IIf InStr Int
IsNumeric Join LBound LCase Left Len LTrim Mid Month Now Replace Right
Round RTrim Sgn Space Split Sqr Str Trim UBound UCase Val Weekday Year
```

These are language namespace rewrites, not 40 Excel object-model ports. Both Basic targets retain `Option VBASupport 1` for VBA language behavior. Native UNO helpers support explicit single-cell `Worksheets(name).Range(address)` and `Cells(row,column)` reads/writes. Unsupported Basic lines remain intact with TODO comments; a Basic candidate can still contain original shell, COM or other unsafe code. Review it before execution. Function behavior remains subject to engine/version-specific verification. [LibreOffice's VBA function documentation](https://help.libreoffice.org/latest/en-GB/text/sbasic/shared/special_vba_func.html) distinguishes VBA-only functions.

The Python generator supports ordinary procedures/functions, ByVal parameters, scalar declarations, assignments, If/ElseIf, For/For Each, While, With, calls and common VBA intrinsics. The shared workbook helper supplies explicit A1 ranges, Cells, values/formulas, Offset/Resize, iteration and common worksheet aggregations for UNO/openpyxl. Unsupported statements raise `NotImplementedError`, with the original adjacent. Classes, event wiring, ByRef, optional/array parameters, advanced error handling, VBA coercion/overflow, locale-sensitive behavior and shadowed intrinsic names require review. The copy helper copies values only and rejects formulas; formatting requires manual migration. openpyxl writes formulas but cannot calculate them.

To compare behavior, provide a JSON case:

```json
{
  "original": {"input": "C:/path/Budget.xlsm", "macro": "Module1.Calculate", "inputs": [2]},
  "converted": {"input": "C:/path/candidate/converted.ods", "macro": "Standard.Module1.Calculate", "inputs": [2]},
  "ranges": {"Data": ["A1:D5"]}
}
```

For Python UNO set converted `python_module` to the generated `.py` file and `macro` to the procedure name. For Linux verification add top-level `golden` pointing to a previously captured Excel JSON.

```powershell
macroferry.exe migrate verify .\case.json --out .\proof --allow-execution
macroferry.exe migrate capture .\excel-case.json --engine excel --out .\golden.json --allow-execution
macroferry.exe migrate compare .\golden.json .\actual.json --out .\comparison.json
macroferry.exe migrate run-python .\Budget.xlsx .\standalone\source\module1.py Calculate --inputs "[2]" --out .\result.xlsx --allow-execution
```

Execution is an explicit opt-in for trusted code. It is **not sandboxed**: a macro may access files, network or services. Excel requires Windows and an installed desktop Excel. Automatic open events and external-link updates are suppressed; only the named routine is invoked. Workers use private LibreOffice profiles and bounded runtimes. A pass proves only the named routine, inputs and captured cells. Values, missing cells, types and formulas are compared with configurable numeric tolerance. Date systems, locale, error representations, formatting, external side effects and unobserved cells need additional case-specific validation.

Power Query sections are preserved intact. Workbook conversion also exports M/pandas sidecars under `power-query/`, with query names and parser TODOs. For an extracted M file:

```powershell
macroferry.exe migrate m-convert .\Section1.m --out .\query-candidate
python .\query-candidate\query.py --query Sales --data-root .\input-data --out .\sales.csv
```

The bounded M parser and allowlisted pandas runtime support common Table.SelectRows, Group, NestedJoin (left/inner), ExpandTableColumn, Pivot, AddColumn, column selection/removal/rename/types, Distinct, Sort, FirstN/Skip, Combine and list/text/numeric operations. Unsupported functions fail explicitly. File sources must resolve inside `--data-root`; network/SQL/SharePoint providers require manual migration. General M semantics, custom comparers, nullable coercions and arbitrary query features are not implemented. ODS files do not refresh M queries; the pandas sidecar is a separate pipeline. Compare its complete output against an Excel golden table before adoption.

The generated arithmetic suite exercises four inputs and 20 cells on all three LibreOffice targets. The Power Query proof compares the extracted sales query against Excel. These fixtures demonstrate the pipeline and are not evidence about an organisation's workbooks.
