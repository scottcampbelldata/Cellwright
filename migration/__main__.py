# SPDX-License-Identifier: EUPL-1.2
import argparse
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

from harness.compare import compare
from migration import office
from migration.convert import convert, todo_count

ROOT = Path(__file__).resolve().parents[1]


def write_json(path, value):
    with Path(path).open("x", encoding="utf-8") as stream:
        json.dump(value, stream, indent=2, ensure_ascii=False)
        stream.write("\n")


def main():
    parser = argparse.ArgumentParser(description="Cellwright assisted conversion and execution comparison")
    commands = parser.add_subparsers(dest="command", required=True)
    conversion = commands.add_parser("convert")
    conversion.add_argument("input", type=Path)
    conversion.add_argument("--out", required=True, type=Path)
    conversion.add_argument("--binary", default=ROOT / ("target/release/cellwright.exe" if os.name == "nt" else "target/release/cellwright"), type=Path)
    conversion.add_argument("--target", choices=["basic", "basic-uno", "python-uno", "python"], default="basic")
    conversion.add_argument("--libreoffice", type=Path)
    capture = commands.add_parser("capture")
    capture.add_argument("case", type=Path)
    capture.add_argument("--out", type=Path, required=True)
    capture.add_argument("--engine", choices=["excel", "libreoffice"], required=True)
    capture.add_argument("--allow-execution", action="store_true")
    capture.add_argument("--libreoffice", type=Path)
    comparison = commands.add_parser("compare")
    comparison.add_argument("expected", type=Path)
    comparison.add_argument("actual", type=Path)
    comparison.add_argument("--out", type=Path, required=True)
    comparison.add_argument("--absolute", type=float, default=1e-9)
    comparison.add_argument("--relative", type=float, default=1e-9)
    comparison.add_argument("--values-only", action="store_true")
    run_python = commands.add_parser("run-python")
    run_python.add_argument("workbook", type=Path)
    run_python.add_argument("module", type=Path)
    run_python.add_argument("macro")
    run_python.add_argument("--inputs", default="[]")
    run_python.add_argument("--out", type=Path, required=True)
    run_python.add_argument("--allow-execution", action="store_true")
    m_conversion = commands.add_parser("m-convert")
    m_conversion.add_argument("source", type=Path)
    m_conversion.add_argument("--out", type=Path, required=True)
    verification=commands.add_parser("verify")
    verification.add_argument("case",type=Path)
    verification.add_argument("--out",type=Path,required=True)
    verification.add_argument("--allow-execution",action="store_true")
    verification.add_argument("--libreoffice",type=Path)
    args = parser.parse_args()
    if args.command == "convert":
        result = convert(args.input, args.out, args.binary, args.target, args.libreoffice)
        count=todo_count(result)
        print(f"Candidate created: {args.out}; {count} TODO(s); verify before use")
    elif args.command == "verify":
        from migration.verify import verify
        result=verify(json.loads(args.case.read_text(encoding="utf-8-sig")),args.out,args.allow_execution,args.libreoffice)
        print(f"{'PASS' if result['passed'] else 'FAIL'}: {result['cells_checked']} cells, {len(result['differences'])} differences")
        return 0 if result['passed'] else 1
    elif args.command == "capture":
        case = json.loads(args.case.read_text(encoding="utf-8-sig"))
        if args.out.exists(): raise FileExistsError(args.out)
        if case.get("macro") and not args.allow_execution: raise PermissionError("Capture execution requires --allow-execution")
        if args.engine == "excel":
            from migration.verify import excel
            excel(case,args.out,args.allow_execution)
        else:
            case.update(mode="capture", allow_execution=args.allow_execution)
            write_json(args.out, office.run(case, args.libreoffice))
    elif args.command == "compare":
        result = compare(json.loads(args.expected.read_text(encoding="utf-8-sig")), json.loads(args.actual.read_text(encoding="utf-8-sig")), args.absolute, args.relative, not args.values_only)
        write_json(args.out, result)
        print(f"{'PASS' if result['passed'] else 'FAIL'}: {result['cells_checked']} cells, {len(result['differences'])} differences")
        return 0 if result["passed"] else 1
    elif args.command == "m-convert":
        from migration.m_runtime import convert as convert_m
        result = convert_m(args.source, args.out)
        print(f"M candidate created: {args.out}; {len(result['queries'])} query(s); {len(result['todos'])} TODO(s); compare tables before adoption")
    elif args.command == "run-python":
        if not args.allow_execution: raise PermissionError("Running a converted macro requires --allow-execution")
        if args.out.exists(): raise FileExistsError(args.out)
        import openpyxl
        from migration.runtime import Workbook
        from migration.vba import safe_name
        native = openpyxl.load_workbook(args.workbook, keep_vba=False)
        spec = importlib.util.spec_from_file_location("converted", args.module)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        module.configure(Workbook(native))
        getattr(module, safe_name(args.macro.lower()))(*json.loads(args.inputs))
        with args.out.open('xb') as stream:native.save(stream)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as error:
        print(f"Cellwright: {error}", file=sys.stderr)
        if isinstance(error,subprocess.CalledProcessError) and error.stderr:
            print(error.stderr.decode() if isinstance(error.stderr,bytes) else error.stderr,file=sys.stderr)
        sys.exit(2)
