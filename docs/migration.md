# Conversion and execution comparison

Use the full distribution archive for conversion and the dashboard. Python 3.11+ is required; LibreOffice Basic and Python UNO targets also require LibreOffice and its UNO Python. The single scanner executable needs neither. Standalone Python and M targets require the pinned optional packages in `requirements.txt`.

```powershell
cellwright.exe serve --port 8768 --data .\reports\dashboard
cellwright.exe convert .\Budget.xlsm --out .\candidate --target basic
cellwright.exe convert .\Budget.xlsm --out .\native --target basic-uno
cellwright.exe convert .\Budget.xlsm --out .\python-candidate --target python-uno
cellwright.exe convert .\Budget.xlsm --out .\standalone --target python
```

Extract the full release archive and open **Start Cellwright.cmd** or **start-cellwright.sh** to reach the dashboard without commands. The setup panel checks the scanner, Python, optional packages, LibreOffice/UNO and Excel, and gives a fix for each missing dependency. The owned demo workbook is bundled in `demo/`; **Scan demonstration workbook** scans it without execution.

The dashboard is at http://127.0.0.1:8768 or http://localhost:8768. It stores scan history, assignments, notes, conversion jobs, verification evidence and schedules in a local SQLite database. Scheduled scans run while the server runs; schedules default to source-free reports. Verification requires starting it with `serve --allow-execution` and checking the consent box for each case. Local programs can obtain its session token; enabling this flag grants them execution capability. Keep the default for routine scanning/conversion. On Linux, fill in the saved Excel capture JSON path in the comparison dialog; it must cover the same routine, inputs and cells. Use separate data directories for separate teams. This release binds only to loopback; remote users, TLS and multi-user access control require a separate deployment design.

The launcher tries `python`, falling back to `python3` only when the first executable is missing. Set `CELLWRIGHT_PYTHON` to select an explicit interpreter; errors from that interpreter are reported without retry. Set `CELLWRIGHT_LIBREOFFICE` to LibreOffice's `program` directory, or pass `--libreoffice` to conversion/capture/verify. On Linux install LibreOffice Calc and `python3-uno`. The UNO worker defaults to `/usr/bin/python3` on Linux and the installed LibreOffice `program/python.exe` on Windows. Set `CELLWRIGHT_UNO_PYTHON` to the full path of another interpreter with UNO available. Development-cache LibreOffice installations are used only when explicitly selected.

Conversion never runs macros. It writes a new destination, original source, candidates, unified diffs and `conversion.json`. ODS targets remove other imported Basic libraries and document/sheet event bindings, detach imported form-control callbacks, and install the generated Standard modules. Basic targets reconnect eligible worksheet push buttons as described below. Source workbooks are preserved. Conversion status remains **candidate**, even when a separately recorded test case passes. Rewriting uses local parser rules and needs no external service or API key.

The Basic converter has 40 named rules that remove a qualified `VBA.` prefix from supported language intrinsics, preserving strings/comments, plus targeted tree-based Range/Cells Value, Value2 and Formula rewrites. The intrinsic rules are:

```text
Abs Asc Chr CInt CLng CDbl CStr Date DateAdd Day Fix Hex IIf InStr Int
IsNumeric Join LBound LCase Left Len LTrim Mid Month Now Replace Right
Round RTrim Sgn Space Split Sqr Str Trim UBound UCase Val Weekday Year
```

These are language namespace rewrites, not 40 Excel object-model ports. Both Basic targets retain `Option VBASupport 1` for VBA language behavior. Native UNO helpers support explicit single-cell `Worksheets(name).Range(address)` and `Cells(row,column)` reads/writes. Unsupported Basic lines remain intact with TODO comments; a Basic candidate can still contain original shell, COM or other unsafe code. Review it before execution. Function behavior remains subject to engine/version-specific verification. [LibreOffice's VBA function documentation](https://help.libreoffice.org/latest/en-GB/text/sbasic/shared/special_vba_func.html) distinguishes VBA-only functions.

The Python generator supports ordinary procedures/functions, ByVal parameters, scalar declarations, assignments, If/ElseIf, For/For Each, While, With, calls and common VBA intrinsics. The shared workbook helper supplies explicit A1 ranges, Cells, values/formulas, Offset/Resize, iteration and common worksheet aggregations for UNO/openpyxl. Unsupported statements raise `NotImplementedError`, with the original adjacent. Classes, general event wiring, ByRef, optional/array parameters, advanced error handling, VBA coercion/overflow, locale-sensitive behavior and shadowed intrinsic names require review. The standalone copy helper copies constant values and rejects formulas; UNO uses native Calc copying for formulas and formatting. openpyxl writes formulas but cannot calculate them.

Formatting assignments are rewritten for all four targets. Supported properties are `Font.Bold`, `Font.Italic`, `Font.Name`, `Font.Size`, `Font.Color`, `Interior.Color`, `WrapText`, `HorizontalAlignment`, `VerticalAlignment` and `NumberFormat`. Basic supports explicit `Worksheets(name).Range(address)`/`Cells(row,column)` and range `With` blocks, including nested `With .Font`/`.Interior`; native value reads/writes remain single-cell. Python uses the existing range adapter. Each assignment records its `FORMAT-*` rule, original line and replacement. For example:

```vb
Worksheets("Data").Range("A1:B2").Font.Color = RGB(255, 0, 1)
' Basic candidate:
MFFormat MFFormatRange("Data", "A1:B2"), "font.color", MFVbaRGB(255, 0, 1)
```

The helpers translate Excel's colour byte order into UNO/openpyxl RGB, accept explicit RGB colours and VBA colour constants, and limit each formatting operation to 100,000 cells. Horizontal alignment supports general/left/center/right; vertical alignment supports top/center/bottom, with the corresponding `xlHAlign*`/`xlVAlign*` aliases. Supported number formats are `General`, `0`, `0.00`, `#,##0`, `#,##0.00`, `0%`, `0.00%` and `@`; UNO registers them with an English/US locale. Installed fonts affect rendering. Theme/system colours, indexed colours, borders, merging, custom/date/localized formats and formatting getters require manual work. Unsupported constant values generate TODOs; unsupported dynamic values fail when a candidate is later run. Basic compound/continued formatting statements require review.

Basic targets preserve the imported button's label and geometry and replace its single `actionPerformed` callback with a document-local `CellwrightButtons` wrapper. The handler must be an unambiguous public, parameterless `Sub` in a standard module with no unresolved TODOs. Wrappers accept the action event and call that routine directly; conversion never invokes them. `conversion.json` records the sheet/control, old/new binding and handler, and `source/button-wrappers.bas` holds the generated source. Dashboard review shows these records, and disconnected controls count as TODOs.

Private/parameterized handlers, missing or ambiguous routines, URL/submit/reset/toggle buttons and other form-control callbacks remain detached with reasons. Supported worksheet ActiveX models are handled by the source-matched control rules below; unreadable or unknown controls retain manual findings. Document-open and sheet events are never reattached. Shapes without imported control models and missing layouts remain manual. Python targets export routines but do not install button handlers; their imported callbacks are detached. [LibreOffice's command-button model](https://api.libreoffice.org/docs/idl/ref/servicecom_1_1sun_1_1star_1_1form_1_1component_1_1CommandButton.html) and [event registration interface](https://api.libreoffice.org/docs/idl/ref/interfacecom_1_1sun_1_1script_1_1XEventAttacherManager.html) describe the bindings used here. These rules produce reviewable candidates, not proof of runtime equivalence.

## Forms, controls and common operations

Basic targets retain imported UserForm layouts as editable dialogs for standard buttons, text boxes, labels, check boxes, option buttons, single-selection lists and combo boxes. Explicit control Value/Text/Caption/Enabled/Visible/ListIndex references and modal Show/Hide/Unload calls get deterministic rewrites. Existing dialog callbacks and external resource/data bindings are removed before source-matched parameterless Click/Change handlers receive document-local wrappers. Eligible private handlers stay in their own module. Worksheet ActiveX controls use the same source matching and native model checks. Original/candidate XDL and binding records are included in the source review.

Custom controls, multipage/dynamic/modeless forms, AddItem/default properties, lifecycle events, tri-state/multi-selection, unknown layouts, bound controls and handlers with unresolved code remain manual. Python targets export routines but do not install dialog or control listeners. Layout candidates and saved bindings have static Windows/Ubuntu checks; dialog display, interactions and Basic helper execution have not been verified. No workbook macro is executed during inventory or conversion.

Clearing contents/full ranges, native copying, one numeric constant-key sort and literal equality filtering use bounded explicit ranges. Sorting requires an explicit order and named Header; advanced options are manual. Basic UNO and Python can append/select and rename sheets with validated names. [Manual recipes](recipes.md) give examples, restrictions and direct adapter checks.

Each conversion card opens an actionable checklist with a location, reason and next action for unresolved work. Skipped or unreadable parts remain prominently marked **unknown coverage**. **Candidate generated**, **manual work required**, **not tested** and **selected tests passed** are separate states. A comparison pass covers only its selected routine, inputs and cells.

The guided comparison form lets users choose an ordinary routine, enter typed scalar inputs, add worksheet/cell ranges and supply a saved Excel capture on Linux. No configuration file is needed. Execution remains disabled unless the server started with `--allow-execution` and the user consents to the individual case; the UI never enables it automatically.

The optional review summary previews a JSON export before saving. Paths, source, captured cells/formulas, hashes, owner details and free-text notes are excluded; module/routine names are removed by default. Users choose whether to include those identifiers and whether to share the saved file.

For command-line verification, provide a JSON case:

```json
{
  "original": {"input": "C:/path/Budget.xlsm", "macro": "Module1.Calculate", "inputs": [2]},
  "converted": {"input": "C:/path/candidate/converted.ods", "macro": "Standard.Module1.Calculate", "inputs": [2]},
  "ranges": {"Data": ["A1:D5"]}
}
```

For Python UNO set converted `python_module` to the generated `.py` file and `macro` to the procedure name. For Linux verification add top-level `golden` pointing to a previously captured Excel JSON.

```powershell
cellwright.exe migrate verify .\case.json --out .\proof --allow-execution
cellwright.exe migrate capture .\excel-case.json --engine excel --out .\golden.json --allow-execution
cellwright.exe migrate compare .\golden.json .\actual.json --out .\comparison.json
cellwright.exe migrate run-python .\Budget.xlsx .\standalone\source\module1.py Calculate --inputs "[2]" --out .\result.xlsx --allow-execution
```

Execution is an explicit opt-in for trusted code. It is **not sandboxed**: a macro may access files, network or services. Excel requires Windows and an installed desktop Excel. Automatic open events and external-link updates are suppressed; only the named routine is invoked. Workers use private LibreOffice profiles and bounded runtimes. A pass proves only the named routine, inputs and captured cells. Values, missing cells, types and formulas are compared with configurable numeric tolerance. Date systems, locale, error representations, formatting, external side effects and unobserved cells need additional case-specific validation.

Power Query sections are preserved intact. Workbook conversion also exports M/pandas sidecars under `power-query/`, with query names and parser TODOs. For an extracted M file:

```powershell
cellwright.exe migrate m-convert .\Section1.m --out .\query-candidate
python .\query-candidate\query.py --query Sales --data-root .\input-data --out .\sales.csv
```

The bounded M parser and allowlisted pandas runtime support common Table.SelectRows, Group, NestedJoin (left/inner), ExpandTableColumn, Pivot, AddColumn, column selection/removal/rename/types, Distinct, Sort, FirstN/Skip, Combine and list/text/numeric operations. Unsupported functions fail explicitly. File sources must resolve inside `--data-root`; network/SQL/SharePoint providers require manual migration. General M semantics, custom comparers, nullable coercions and arbitrary query features are not implemented. ODS files do not refresh M queries; the pandas sidecar is a separate pipeline. Compare its complete output against an Excel golden table before adoption.

The generated arithmetic suite exercises four inputs and 20 cells on all three LibreOffice targets. The Power Query proof compares the extracted sales query against Excel. These fixtures demonstrate the pipeline and are not evidence about an organisation's workbooks.
