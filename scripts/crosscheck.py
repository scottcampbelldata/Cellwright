# SPDX-License-Identifier: EUPL-1.2
"""Development-only source cross-check; requires oletools, never executes VBA."""
import argparse
import json
import subprocess
import tempfile
from pathlib import Path

from oletools.olevba import VBA_Parser


def normalized(source):
    return source.replace("\r\n", "\n").replace("\r", "\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("binary", type=Path)
    parser.add_argument("workbooks", nargs="+", type=Path)
    args = parser.parse_args()
    checked = 0
    for workbook in args.workbooks:
        reference = VBA_Parser(str(workbook))
        try:
            expected = {
                Path(name).stem: normalized(source)
                for _, _, name, source in reference.extract_macros()
            }
        finally:
            reference.close()
        with tempfile.TemporaryDirectory(prefix="cellwright-crosscheck-") as directory:
            destination = Path(directory) / "reports"
            subprocess.run(
                [str(args.binary.resolve()), "extract", str(workbook.resolve()), "--out", str(destination)],
                check=True,
                timeout=60,
                capture_output=True,
            )
            report = json.loads((destination / "scan.json").read_text(encoding="utf-8"))
            actual = {
                module["name"]: normalized(module["source"])
                for module in report["workbooks"][0]["modules"]
            }
            if actual != expected:
                raise AssertionError(f"VBA sources differ from olevba: {workbook}")
        print(f"OK: {workbook.name}: {len(expected)} modules, exact source match")
        checked += 1
    if checked == 0:
        raise AssertionError("No workbooks checked")


if __name__ == "__main__":
    main()
