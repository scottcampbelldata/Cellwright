# Estate checks and effort calibration

## Real workbook stress test (10 October 2026)

The local `calibration-corpus` contains 30 third-party VBA workbooks/add-ins: 17 XLSM, five XLS, four XLSB, three XLAM and one XLA. The manifest and independent oletools extraction agree on nonempty module and nonblank line counts. Attribute-only/empty modules are retained by Cellwright, while its executable code-line count excludes comments; these definitions explain the different totals. The manifest and designer-stream check identify **11 workbooks with 145 UserForms**; four OOXML workbooks contain ActiveX binary parts. Legacy/binary worksheet control coverage remains partial.

The initial scan inspected 26 files. Two valid workbook containers had legacy VML drawings with HTML-style `<br>` tags that failed strict XML parsing. Cellwright now retains their VBA and marks drawing coverage unknown with MF060. Structured worksheet XML remains strict. Buffered JSON output also avoids excessive small writes on Windows-mounted WSL paths.

The current release scans inspect **all 30 files** on Windows and Ubuntu with no discovery errors. The inventory contains 1,261 extracted modules including empty/document modules, 992 unique normalized nonempty modules, 145 UserForms and 1,166 form-control sites. Ten sites have unknown/custom control types; counting designer sites does not prove layout or runtime compatibility. RelaxTools contributes **369 modules, 80 forms and 666 control sites**, with no form-stream parsing errors. The [previous baseline](examples/real-corpus-summary.json) inspected 28 files; its counts and hours are historical measurements.

All 30 extracted VBA projects were cross-checked independently. Twenty-eight match olevba text after line-ending and VBA module-name case normalization. The crypto example and mx contain one undefined Windows-code-page byte each (1252/1257); oletools replaces these with U+FFFD, while Cellwright preserves their C1 values. Independent decompression of the original bytes confirms those two sources as well. All 30 original SHA-256 values still match the supplied checksum file. No third-party macro was executed. Source-bearing reports stay local; [current portable evidence](examples/real-corpus-round2-summary.json) contains counts, hashes, findings and uncalibrated ranges only.

The two previously blocked files now retain their VBA inventories with unknown skipped-part coverage:

| Workbook | Limit encountered | Effect |
| --- | --- | --- |
| CosMoS costing model | `sheet5.xml` expands to 59,740,611 bytes, exceeding 16 MiB | Skip that part; inspect 13 modules, including six nonempty modules; MF060/unknown coverage |
| Automated Invigilation Planning System | Five worksheets exceed 16 MiB and `calcChain.xml` expands to 73,462,074 bytes | Skip those six parts; inspect 303 modules, including 165 nonempty modules, one form and four sites; MF060/unknown coverage |

The archive limits remain intact: skipped non-VBA parts are never decompressed, and retained parts stay within 16 MiB each and 256 MiB combined. The scheduler's declared expansion is 396,541,091 bytes overall, but its retained parts total less than 256 MiB. Oversized VBA, too many entries, encrypted entries and retained aggregate violations still reject input. Nested Power Query packages remain strict. Both full corpus scans exit 0; inspected files with incomplete coverage have an unknown verdict. Windows and Linux inventories match after normalizing host-specific metadata.

Limits measure expanded ZIP parts, not just file size: CosMoS is 2,890,788 bytes on disk but has a roughly 57 MiB worksheet; the scheduler is 44,518,656 bytes on disk. Warnings name every skipped part, its declared expanded bytes and the active limit. Other VML warnings are retained alongside them. The scanner does not assess content inside skipped parts, and the estimate excludes that unknown work.

```powershell
cellwright.exe scan .\calibration-corpus --out .\reports\real-corpus --no-source
```

Use a fresh output directory. On Linux use `cellwright` and forward-slash paths. The corpus is ignored by Git and excluded by the release packager's explicit directory allowlist. Finance Tracker and CosMoS are GPL files and must not be bundled in a release. The Macquarie course workbook remains local testing only; no corpus workbook or extracted VBA is included in Cellwright archives.

### What the estimates show

Forms now add `hours_per_userform + min(control_sites, control_site_cap) × hours_per_control_site` per form and per workbook. Defaults are two hours per form plus 0.1 hour per site, capped at 50 sites per form. The cap limits the estimate, not inventory counts; custom/unknown sites are counted too. MF050 still flags forms but its flat eight-hour charge is removed to avoid double counting. These weights are planning assumptions, not observations of human labour.

Empty modules cost zero. Document modules containing only attributes, options or empty procedures omit base/testing overhead; line and finding costs remain. Modules with executable statements still receive the normal overhead, regardless of whether they are named ThisWorkbook or Sheet1. The low/high multipliers remain 0.5 and 2.0.

[Per-file before/after evidence](examples/real-corpus-estimate-comparison.json) covers all 30 files. Before ranges are recorded baseline measurements for the previously inspected 28; null marks the two previously uninspected files. A separate previous-model calculation on the current inventory gives those two files a comparable baseline. The following current ranges deduplicate modules within each workbook and include feature/form costs:

| Workbook | Executable code lines | Default range, hours |
| --- | ---: | ---: |
| Stock daily-return calculation | 12 | 1.37-5.48 |
| VBmail | 14 | 8.39-33.56 |
| Invoice Generator, four forms/38 sites | 412 | 33.72-134.88 |
| SalesInvoice, no forms | 1,049 | 39.49-157.96 |
| MacroTools add-in | 13,093 | 478.91-1,915.64 |
| RelaxTools | 42,876 | 1,564.84-6,259.36 |

Invoice Generator remains below SalesInvoice; no ranking inversion was forced. Its central estimate combines 30.64 hours of unique-module costs, 25 hours of workbook findings and 11.8 hours for forms/sites. SalesInvoice has 61.98 hours of unique-module costs plus 17 hours of workbook findings. Removing three hours of document overhead and replacing the old eight-hour flat form charge yields a net 0.8-hour central increase for Invoice Generator. Its UI burden does not outweigh SalesInvoice's larger code/finding burden under these assumptions.

The current estate range is **4,062.24-16,248.96 hours**, with shared modules deduplicated across all 30 files. It excludes unknown work despite complete VBA-project extraction. MF060 adds zero hours for unknown coverage; control rendering, external services and repeated deployment/integration testing need separate assessment. The cap also means exceptionally dense forms need review beyond the default range. These limitations prevent using the range as a quoted budget. No human effort observations were invented.

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

To calibrate later, retain a source-free inventory of 20 to 50 representative production workbooks, record actual review, rewrite, integration and regression-test hours, and identify shared modules so work is not counted twice. Fit weights using part of that set, then evaluate prediction errors and interval coverage on held-out workbooks. Include failed/blocked migrations and previously unknown work. Publish the sample scope, observed hours, weight changes and validation errors before treating the range as a budget.
