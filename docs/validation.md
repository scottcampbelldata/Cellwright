# Validation (10 October 2026)

The current static checks run on Windows x64 and Ubuntu in WSL with Rust/Cargo 1.99.0, Windows Python 3.15 and Linux Python 3.14. pandas 3.0.6/openpyxl 3.1.5 are optional dependencies. Earlier engine comparisons used LibreOffice 26.8.1.1 on Windows and 26.2.6.3 on Linux. Excel captures were made on Windows with Excel 16.0.20430.20092 x64; Linux reused the saved captures. Reference tools and test runtimes are kept in ignored local cache directories.

| Current check | Windows | Ubuntu |
| --- | --- | --- |
| `cargo fmt --all -- --check` | Pass | Pass |
| `cargo clippy --locked --all-targets -- -D warnings` | Pass | Pass |
| `cargo test --locked` | 27 passed: 17 unit, 10 integration | 28 passed: 17 unit, 11 integration |
| Python unittest discovery | 34 passed | 33 passed, one Windows-path test skipped |

The extra Ubuntu integration test covers launcher fallback to `python3`. Regression coverage includes skipped oversized non-VBA parts with retained VBA/unknown coverage, preserved aggregate and nested ZIP limits, accumulated VML warnings, form/control estimate caps, boilerplate document overhead, weight validation and UNO interpreter selection. UNO-launch unit tests mock every subprocess.

The latest conversion checks add formatting rules, nested range/Font `With` blocks, colour byte-order conversion, style/value preservation, unsupported values/getters, cell budgets and button eligibility/rebinding. Tests compile new Python candidates without invoking them. An owned source-only XLSM with a VML push button converted to Basic/UNO on Windows and Ubuntu with zero TODOs. Reopening the ODS on both platforms confirmed the document-local wrapper binding, one retained button shape, removal of the imported Basic library and unchanged original cell colour. Direct property calls on separate empty UNO workbooks verified font, colour, fill, wrap, alignment and number-format adapters. No macro or button handler was executed. Runtime behavior of the new Basic helpers remains unverified under that restriction. [Static conversion evidence](examples/formatting-button-static.json) records the scope.


The first-migration checks cover bounded control metadata, form/control rewrites and unresolved source retention, imported dialog sanitization and geometry, source-matched private event wrappers, operation argument ordering, typed native sort descriptors, guided-case validation and redacted review exports. Windows and Ubuntu static checks on owned dialogs/worksheet controls confirm their local event bindings survive saving and reopening. Direct adapter calls on blank owned workbooks check sorting, filtering, copying and sheet creation/renaming. Macros, dialog display and callbacks were not invoked. The real InvoiceGenerator pilot retains four dialog layouts with complex handlers and its multipage form explicitly unresolved. [Form/control evidence](examples/first-migration-static.json) records the scope.

Release scans inspect all 30 local corpus files on both platforms, including Automated Invigilation and CosMoS. Full-source and source-free JSON pass the schema; inventories match after removing host metadata. Independent olevba checks confirm all 1,261 extracted modules, with the two previously documented undefined-code-page bytes verified against raw source. All original SHA-256 values match. The inventory contains 145 forms and 1,166 control sites. [Current corpus evidence](examples/real-corpus-round2-summary.json) and [per-file before/after estimates](examples/real-corpus-estimate-comparison.json) record the results. The skipped parts remain unknown, and the hour ranges remain uncalibrated.

The [implementation CI run](https://github.com/scottcampbelldata/Cellwright/actions/runs/38038290143) passed for `4de3c24`, including Windows/Ubuntu checks, packaging and parser fuzzing. GitHub source is public and private vulnerability reporting is enabled; the [security policy](../SECURITY.md) links the private reporting form.

## Earlier controlled validation (9 October 2026)

- Native and Python checks passed on both platforms; the table above records the current counts. Coverage includes tolerant VBA conversion/semantic limits, 40 intrinsic namespace rules, M table operations/unsupported functions, comparator behavior and dashboard persistence/HTTP protections. Dashboard JavaScript syntax and Python compilation passed.
- Own bounded VBA parser matched independent olevba extraction on all 11 modules across calamine, XlsxWriter and the owned arithmetic fixture. CFB v4 regression coverage passes; calamine is now only a test/reference dependency.
- Fixture scans retained source hashes, reported encrypted files without decryption, and validated privacy, code pages, owner IDs, real DataMashup extraction, connections, protected skipping, corrupt input, compressed limits and output protection. Full-source, no-source and query reports validated against the JSON Schema.
- **12 Windows and 12 Linux execution cases passed**, four scalar inputs across compatibility Basic, native-cell UNO Basic and Python UNO. Each compared Data!A1:D5 (20 cells), including formula results and formula text. Linux reused saved Excel goldens. Only the owned source-only arithmetic fixture was executed.
- Standalone openpyxl output matched **19 non-formula cell values** for input 2, retaining the remaining cell's formula text. Formula results were not evaluated by openpyxl.
- Extracted sales M query translated to pandas and matched Excel's loaded table: **4 cells**, including headers. Join/expand/pivot tests also passed. Workbook conversion exports working pandas sidecars.
- Portable controlled-case evidence is in [verification-summary.json](examples/verification-summary.json). Detailed captures/diffs remain in `target/final-verified-suite`, `target/linux-verified-suite`, `target/verified-query-final` and dashboard job directories; they are not universal compatibility claims.
- Nightly/libFuzzer smoke campaigns completed without crashes: **163,345 runs** from an empty seed set and **50,833 runs** seeded with real ZIP/CFB/dir/XML/M inputs (about 30 seconds each). This is short parser coverage, not a security audit.
- Browser checks passed: source-free scan/history, search, assignments, native candidate, source/diff downloads, complete ZIP download, explicit comparison (20 cells, zero differences), M candidate and paused schedule persistence. The Windows extended-path URL failure found during testing was fixed and covered by a regression test; its failed historical job remains visible for audit.
- REUSE lint passed with all project files licensed and dependency notices retained. The generated **108-component** lockfile SBOM validated against the primary CycloneDX 1.6 schema and reference graph checks.
- Linux clean builds from Windows-mounted and native Linux source paths produced identical SHA-256: `68a4b546002b41967ed7dbef396472d385f4797f11d044a4a9f8399be1aa88de`.
- Windows clean/default target builds matched after enabling MSVC `/Brepro`: `7627b16f900bd6ae76bb67e92b8697c1b6bf87ef79d0ae55424b1175201ecd76`. Prior builds differed only in timestamp/debug identifiers. This proves reproducibility on these local toolchains, not every host.
- Full Windows/Linux archives contain tools, docs, SBOM and per-file hashes. Packaging checks ZIP integrity, preserves Linux executable permissions, refuses overwrites and uses deterministic entry order/timestamps. Archive verification is part of the local release check.

Not checked: representative private/government estates, real UNC shares, UserForm rendering/runtime equivalence, native-language review, calibrated estimates, full VBA/M semantics, OS memory sandboxing, independent security audit, signing or public binary release/mirror. Complex macros, external providers and unobserved side effects require workload-specific review and proof.

## Dashboard follow-up (9 October 2026)

Regression checks cover option-like scan paths, localhost with matching Origin, hostile/cross-origin hosts, default execution rejection, explicit startup/case consent, and saved Excel captures for Linux. The Linux CLI test exercises python3 fallback, explicit interpreter errors and absence of retry after a Python failure. In this earlier round, stock Ubuntu conversion to native UNO Basic succeeded without setting CELLWRIGHT_PYTHON, and a Linux dashboard comparison passed using a saved Excel capture: 20 cells, zero differences. The default dashboard refused execution requests even with a valid session token and case consent.

The [30-workbook simulation](calibration.md) passed discovery, source extraction, blocker rules, document-open entry points, Power Query extraction, shared-template deduplication and standalone conversion. Fifteen safe candidates passed value/formula-text checks; COM/API/event candidates were not executed. Human migration hours and formula recalculation were not measured. [Portable scenario evidence](examples/simulated-summary.json) records this scope.

## Real corpus follow-up (9 October 2026)

The previous [real workbook stress test](calibration.md) discovered all 30 supplied workbooks and inspected 28. VML drawing failures retained VBA with explicit unknown coverage; malformed worksheet XML remained strict. Buffered report JSON reduced that scan to approximately 1.6 seconds on Windows and 1.2 seconds on Ubuntu in WSL.

Independent olevba checks covered all 945 extracted modules, including empty ones: 26 projects matched decoded text after line-ending/module-name case normalization; two projects had one undefined Windows-code-page C1 byte each, confirmed against independently decompressed source bytes. Native form counts match the designer-stream counts for all inspected files: 144 forms, 1,162 control sites, ten unknown/custom types and zero form-stream errors. RelaxTools has 369 modules, 80 forms and 666 control sites. All 30 original hashes match the supplied checksums. Full-source and no-source JSON pass the schema, and the Windows/Linux inventories agree after normalizing host-specific metadata.

CosMoS and Automated Invigilation were uninspected in that baseline because ZIP parts exceeded the 16 MiB limit. The current scan skips those non-VBA parts and retains both VBA inventories under the unchanged bounds. No third-party macro execution, designer rendering or human migration effort was measured. Corpus binaries and extracted source remain local and are excluded from release archives; [baseline measurements](examples/real-corpus-summary.json) remain available for comparison.

The [current main CI runs](https://github.com/scottcampbelldata/Cellwright/actions/workflows/ci.yml?query=branch%3Amain) include three website checks on Windows and Ubuntu: palette restrictions, bounded engagement collection and foreground time/opt-outs. [Website operation and private traffic reports](site.md) are documented separately.
