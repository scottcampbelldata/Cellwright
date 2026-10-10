# Architecture and roadmap status

One Cargo package contains the scanner: bounded ZIP/CFB/XML/Mashup handling (`container.rs`), native MS-OVBA compression/dir/code pages (`ovba.rs`), MS-OFORMS control inventory (`forms.rs`), token/IDL rules, isolated workers, deduplication and offline writers. Calamine is an independent **test dependency**, not the runtime decoder. Workers receive frozen configuration and have time/output bounds; they are not an OS memory sandbox.

Python sidecars reuse scanner JSON. A tolerant handwritten VBA statement/expression tree produces reviewable Basic/Python candidates. The shared workbook helper adapts explicit cell operations to UNO/openpyxl. A bounded M parser and allowlisted pandas runtime migrate common tables. Excel COM/private UNO workers and the comparator retain case evidence. The loopback dashboard persists scans, schedules, assignments and jobs in SQLite.

| Milestone | Implemented | Outstanding gate or limit |
|---|---|---|
| M0 | Project, pinned toolchain/dependencies, CI, license/REUSE, public GitHub source and private vulnerability reporting | publiccode/mirror metadata and governance |
| M1 | Own decompressor/dir/code pages/types/protection, CFB v3/v4, VBA from ZIP/legacy, encryption, forms inventory/designer evidence, queries/connections, fuzz target/corpus | Broader real forms/legacy corpus, full binary feature/p-code analysis, extra ovba reference tool |
| M2 | Discovery/shares, isolated workers, 60 translated rules, verdicts/dedup/CSV/JSON | Estate pilots and performance/security validation |
| M3 | Offline reports/estimates/privacy, Windows/Linux full archives, SBOM/hashes, three-language guides, reproducibility procedure | Signing, publication/mirror, language review and calibration |
| M4 | Pinned IDL snapshot, partial member/type checks, integrated tolerant tree/parser | Full name/type resolution; declared is not tested |
| M5 | Excel COM capture, private UNO worker, formula/numeric comparison, controlled suites | Workload-specific cases, dates/locales/errors/formats/side effects |
| M6 | Basic compatibility/native cell candidates, TODOs/diffs, 40 named qualified-intrinsic rules and cell rewrites | General object model/forms/events/APIs; namespace rules are not 40 object-model ports |
| M7 | Python UNO and standalone openpyxl generators/helper | Advanced VBA semantics/classes/coercions and engine-native formula copies/formatting |
| M8 | M parser/metadata, common pandas table operations, extracted-query comparison | General M/comparers/null coercion/network/SQL providers |
| M9 | Dashboard scans/history, assignment/status/notes, schedules, candidates/downloads and opt-in comparisons | Multi-user/remote deployment; schedules need a running server |

This is a bounded first release across the roadmap, not a universal VBA/M transpiler. Release gates needing credentials, real users or confidential estates cannot be replaced with fixtures.

IDL revision `1fd99223bf371e8d34d4b09b4988bb34ff2ec0d2` covers 276 files and 553 declared members, with per-file source URLs/hashes in `data/lo-vba-support.json`. The global `tested` list stays empty: a case proof is not member certification. Inference supports common explicit roots and declarations; scope/shadowing, aliases, return types and dynamic dispatch need review.

The handwritten parser keeps conversion dependency-free and tolerates unsupported lines. It reuses extraction/token boundaries. Evaluate a larger external parser when supported syntax expands; it cannot eliminate TODOs or execution tests. Syntax acceptance and engine equivalence are separate checks.
