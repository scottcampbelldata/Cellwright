# Manual migration recipes

These examples show the bounded cases used by Cellwright's regression checks. Generated Basic helpers are inspected as source and their saved layouts/bindings are checked without running routines. Python adapters are checked directly on owned blank workbooks. Neither establishes runtime equivalence for a customer's workbook. Keep the original and add a comparison case for each change.

## UserForms and worksheet ActiveX

Start with a Basic candidate. The converter retains supported imported dialog positions, sizes, captions, styles and tab order in `DialogLibraries.Standard`. It rewrites explicit text/value, caption, enabled/visible and single-list selection properties for text boxes, labels, push buttons, check boxes, option buttons, list boxes and combo boxes. For example:

```vb
Private Sub Apply_Click()
    Worksheets("Data").Range("A1").Value = Me.Amount.Value
    Me.Hide
End Sub
```

The candidate reads the dialog's `Amount` control through `MFUIGet(MFUIControl("dialog", "EntryForm", "Amount", "TextBox"), "value")`; the Basic UNO target writes A1 through `MFSet`. `Me.Hide` becomes `MFUIHide "EntryForm"`. A source-matched parameterless click routine receives a generated public wrapper in the same module, which can call the original private routine. The corresponding dialog event points to that wrapper in the document. Opening/converting a workbook never invokes the routine or displays its dialog.

Worksheet ActiveX controls become imported LibreOffice form models, rather than COM objects. The converter checks the source class and worksheet code name against the imported model before wiring a supported click/change event. Explicit `Me.Amount.Value` reads/writes use the native worksheet control model. Missing controls, custom classes, bound data fields, dynamic `Controls(...)`, modeless forms, complex list population, multi-selection, tri-state values and lifecycle events need manual work. Unknown inventory coverage remains unknown even when a layout candidate exists.

For manual work, open the candidate's dialog editor, inspect each control against the original and replace custom widgets with standard controls. Use `dialog.getControl("Amount").Model.Text`, `.Label`, `.Enabled` or `.EnableVisible` as appropriate. A check box/option button uses `.State` (0/1); check for tri-state 2 before treating it as a Boolean. A single list selection uses `.SelectedItems` (zero-based indexes). Reconnect only a reviewed event in the editor. Compare an interaction including initial state, edited values and the resulting cells. Automatic initialization/activation/close and worksheet/document events are deliberately left detached.

## Clearing, copying, sorting and filtering

Use explicit worksheets and bounded A1 ranges. Candidates refuse operations over 100,000 cells. Unsupported arguments remain TODOs.

| Excel operation | LibreOffice Basic candidate | Python adapter |
| --- | --- | --- |
| `Worksheets("Data").Range("A1:B4").ClearContents` | `MFClear MFFormatRange("Data", "A1:B4"), 23` | `book.worksheets("Data").range("A1:B4").clearcontents()` |
| Same range with `.Clear` | `MFClear ..., 887` | `.clear()` |
| `.Copy Destination:=Worksheets("Data").Range("D1")` | `MFCopy sourceRange, destinationRange` uses Calc's `copyRange` | `.copy(destination)`; UNO uses native copy, standalone refuses formulas |
| `.Sort Key1:=Worksheets("Data").Range("A1"), Order1:=xlAscending, Header:=xlYes` | `MFSort range, keyRange, 1, 1` | `.sort(keyRange, 1, 1)` |
| `.AutoFilter Field:=2, Criteria1:="Open"` | `MFFilter range, 2, "Open"` | `.autofilter(2, "Open")` |

Sorting supports one numeric constant key column, explicit ascending/descending order and explicit yes/no header. Locale-dependent text sorts, guessed headers, multi-key sorts and unsupported sort options stay manual. Standalone Python also refuses formula rows before changing cells. Equality filters assume a header and accept a literal string or number; strings match without case sensitivity. Wildcards, expressions, multiple criteria and formula results in standalone workbooks need manual migration. Inspect row visibility as well as cell values when checking filters. Standalone clearing preserves row/column dimensions and copying covers constant values; use Calc for formula translation and full formatting behavior.

For unsupported sorts/filters, use Calc's range `createSortDescriptor()` / `createFilterDescriptor(True)` with explicitly chosen fields and options. Keep sample rows that expose blanks, duplicate keys, locale/case differences and header handling. Compare those rows before adopting the change.

## Creating and renaming sheets

`Set summary = Worksheets.Add` becomes `Set summary = MFAddSheet()` in the Basic UNO target; `Worksheets.Add.Name = "Summary"` is lowered to an explicit new sheet before renaming. Python uses `summary = book.worksheets.add()` and `summary.name = "Summary"`. New sheets are appended and selected. Renaming must use an unused Excel-compatible name, at most 31 characters and without `[]:*?/\`. Insertion before/after a sheet, template copies and multi-sheet operations remain manual. Check formulas and downstream dependencies after renaming.

## External services and data sources

For Outlook/COM/Windows API code, identify the actual business operation, then replace it with a reviewed API or a manual step. For example, prepare an email draft with Python's standard `email.message.EmailMessage`; keep sending separate and explicitly authorized. A shell/COM TODO is not made safe by converting neighboring statements. Do not run the original to discover behavior.

For Power Query, inspect the original M and generated pandas script, configure source paths locally and compare a saved output table. Connections, credentials, provider-specific semantics and refresh schedules need explicit review. ODS candidates do not refresh M automatically.

## Review handoff

The conversion card's review summary previews an allowlisted JSON export. Paths, source/diffs, captured values/formulas, hashes, owner notes and free-text reasons never enter this export. Module/routine names are excluded by default and can be included after reviewing the preview. Save it locally, inspect it again and choose whether to share it. The dashboard sends nothing to consulting services.
