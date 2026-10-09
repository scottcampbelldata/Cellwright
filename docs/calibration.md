# Simulated estate checks and effort calibration

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
