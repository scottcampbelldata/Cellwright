# Public test corpus

Only public or project-owned test data is included. Do not add private government/customer workbooks. The scanner never executes anything. Engine verification executes only the controlled arithmetic fixture with explicit consent; public third-party macros are extraction-only.

| File | Origin | License | Expected result |
|---|---|---|---|
| calamine-vba.xlsm | [tafia/calamine tests/vba.xlsm](https://github.com/tafia/calamine/blob/master/tests/vba.xlsm) | MIT, LICENSE-calamine.txt | Five modules: Sheet1, Sheet2, Sheet3, ThisWorkbook, testVBA; unprotected project; one nonempty code module |
| encrypted.xlsb | [tafia/calamine tests/pass_protected.xlsb](https://github.com/tafia/calamine/blob/master/tests/pass_protected.xlsb) | MIT, LICENSE-calamine.txt | Password-to-open encryption; unknown verdict and nonzero scan status |
| xlsxwriter-macro01.xlsm | [XlsxWriter macro01.xlsm](https://github.com/jmcnamara/XlsxWriter/blob/main/xlsxwriter/test/comparison/xlsx_files/macro01.xlsm) | BSD-2-Clause, LICENSE-xlsxwriter.txt | Three modules: Module1, Sheet1, ThisWorkbook; unprotected project; one nonempty code module |

Integration tests generate synthetic OOXML connections, drawings, ActiveX/OLE/Data Model markers, nested M sections, malformed containers and a compressed oversized part. These exercise the scanner without installing Office. The synthetic files validate parsing and inventory behavior, not Excel or LibreOffice interoperability.

`expected.json` records independent olevba module names, line counts and SHA-256 hashes of source after CRLF/CR normalization. `scripts/crosscheck.py` compares every extracted source byte after newline normalization. Fixture file hashes are also recorded so a changed corpus is visible.

`Arithmetic.bas` is an owned, deterministic macro with scalar inputs, loops/branching, cell reads/writes, a formula and a helper function. `generated/arithmetic-source-only.xlsm` contains that source with no compiled p-code cache. `examples/generate_vba_fixture.rs`/`scripts/generate_source_fixture.py` assemble it without changing Excel security settings. Only type-library reference metadata is retained from the MIT calamine fixture; its notices remain applicable. Do not execute third-party fixtures to obtain these results.

`Sales.m` is an owned, constant-record filter/group query. `scripts/generate_query_fixture.ps1` loads it into a new Excel table without external data. `generated/sales-query.xlsx` retains the genuine DataMashup section and loaded table. `scripts/verify_query.py` extracts/translates it and compares the pandas table with Excel. These fixtures prove controlled paths, not real-estate compatibility. The alternative Excel COM VBA generator requires an already-enabled VBProject setting; it never changes that setting.
