# Estate checks and effort calibration

## Real workbook stress test — 9 October 2026

The local `calibration-corpus` contains 30 third-party VBA workbooks/add-ins: 17 XLSM, five XLS, four XLSB, three XLAM and one XLA. The manifest and independent oletools extraction agree on nonempty module and nonblank line counts. Attribute-only/empty modules are retained by MacroFerry, while its executable code-line count excludes comments; these definitions explain the different totals. The manifest and designer-stream check identify **11 workbooks with 145 UserForms**; four OOXML workbooks contain ActiveX binary parts. These counts differ from the earlier verbal totals of 13 and seven. Legacy/binary worksheet control coverage remains partial.

The initial scan inspected 26 files. Two valid workbook containers had legacy VML drawings with HTML-style `<br>` tags that failed strict XML parsing. MacroFerry now retains their VBA and marks drawing coverage unknown with MF060. Structured worksheet XML remains strict. Buffered JSON output also avoids excessive small writes on Windows-mounted WSL paths.

The final static scan inspected **28 of 30 files**, with no discovery errors, in about **1.6 seconds on Windows and 1.2 seconds on Ubuntu WSL**. The inventory contains 945 extracted modules including empty/document modules, 821 unique normalized nonempty modules, 144 UserForms and 1,162 form-control sites. Ten sites have unknown/custom control types; counting designer sites does not prove layout or runtime compatibility. RelaxTools contributed **369 modules, 80 forms and 666 control sites**, with no form-stream parsing errors.

All 28 extracted VBA projects were cross-checked independently. Twenty-six matched olevba text after line-ending and VBA module-name case normalization. The crypto example and mx contain one undefined Windows-code-page byte each (1252/1257); oletools replaces these with U+FFFD, while MacroFerry preserves their C1 values. Independent decompression of the original bytes confirmed those two sources as well. All 30 original SHA-256 values still match the supplied checksum file. No third-party macro was executed. Source-bearing reports stay local; [portable evidence](examples/real-corpus-summary.json) contains counts, hashes, findings and uncalibrated ranges only.

Two files remain explicitly uninspected:

| Workbook | Limit encountered | Effect |
| --- | --- | --- |
| CosMoS costing model | A worksheet expands to 59,740,611 bytes, exceeding the 16 MiB part limit | No native inventory or effort estimate |
| Automated Invigilation Planning System | A part expands to 73,462,074 bytes; total declared expanded size is 396,541,091 bytes, also exceeding 256 MiB | No native inventory or effort estimate; its one form is absent from the native total |

The archive limits remain intact. A scan exits 1 and retains the partial reports for these failures; an inspected file with incomplete feature coverage still has an unknown verdict. Windows and Linux inventories match after normalizing paths, owner IDs and generation time.

```powershell
macroferry.exe scan .\calibration-corpus --out .\reports\real-corpus --no-source
```

Use a fresh output directory. On Linux use `macroferry` and forward-slash paths. The corpus is ignored by Git and excluded by the release packager's explicit directory allowlist. Finance Tracker and CosMoS are GPL files and must not be bundled in a release. The Macquarie course workbook remains local testing only; no corpus workbook or extracted VBA is included in MacroFerry archives.

### What the estimates show

The default model ranks a tiny calculation below larger API/UI add-ins, which is useful for triage. The following ranges deduplicate modules within each workbook and include its feature costs; they are assumptions, not measured migration hours.

| Workbook | Executable code lines | Default range, hours |
| --- | ---: | ---: |
| Stock daily-return calculation | 12 | 1.37–5.48 |
| VBmail | 14 | 8.39–33.56 |
| Invoice Generator | 412 | 33.32–133.28 |
| Xero API demo | 7,107 | 199.56–798.24 |
| MacroTools add-in | 13,093 | 459.66–1,838.64 |
| RelaxTools | 42,876 | 1,456.29–5,825.16 |

The much larger VBmail range despite its small code size illustrates dependency costs; the large add-ins expose the model's per-module overhead. The incomplete estate range is **3,530.11–14,120.44 hours**, with shared modules deduplicated across inspected files. It excludes both failed workbooks and unknown work. MF060 adds zero hours for unknown coverage, and the default test overhead is per unique module; designer rebuilding, external services and repeated deployment/integration testing require separate assessment. These limitations prevent using the range as a quoted budget. No estimate weights were changed and no human effort observations were invented.

## Simulated business scenarios

The scenario suite generates 30 project-owned workbooks. [The recorded run](examples/simulated-summary.json) passed all 30 inventory/conversion cases and 15 safe Python calculation checks. Five calculation templates cover budgeting, payroll, inventory, forecasts and invoices, each with 12, 120 and 1,200 transaction rows, Excel tables, summary formulas and scalar macro inputs. Other cases exercise Outlook COM, Windows API declarations, ADO refresh, document-open events and the controlled constant-record sales Power Query. Three copies of each template exercise source deduplication; the three query copies intentionally share the same pipeline.

The script asserts workbook discovery, extraction, blocker rules, document entry points, query extraction, duplicate detection, conversion TODOs and unchanged originals. With execution consent it runs only the 15 owned calculation candidates through openpyxl, checking calculated values and stored formula text. It never invokes the COM/API/event candidates. Formula results are not recalculated by openpyxl. These source-only VBA projects lack compiled p-code; the suite does not cover real UserForm designers, legacy BIFF data, external data services or deployment integration.

From the source checkout:

```powershell
cargo build --locked --release
cargo build --locked --example generate_vba_fixture
python -m scripts.simulate_estate --out .\reports\simulated-estate --allow-execution
```

Use `python3` and forward-slash paths on Linux. The destination must not exist. Generated source, workbooks, inventory reports, candidates and `summary.json` stay in the ignored reports directory; the portable summary can be shared without production data. Execution is limited to this script's own calculation templates.

**Hour estimates remain uncalibrated.** Successful simulated cases establish scenario behavior, not human migration time. Dataset row counts do not directly affect a model based on code and findings. Scan/conversion wall-clock times are machine timings, not labour hours, and synthetic labour times must not be fitted as observations.

To calibrate later, retain a source-free inventory of 20–50 representative production workbooks, record actual review, rewrite, integration and regression-test hours, and identify shared modules so work is not counted twice. Fit weights using part of that set, then evaluate prediction errors and interval coverage on held-out workbooks. Include failed/blocked migrations and previously unknown work. Publish the sample scope, observed hours, weight changes and validation errors before treating the range as a budget.
