# SPDX-License-Identifier: EUPL-1.2
"""Capture a named, explicitly authorised test case on both engines and retain evidence."""
import hashlib
import json
import math
import os
import re
import subprocess
import tempfile
from pathlib import Path
from harness.compare import compare
from migration import office

ROOT=Path(__file__).resolve().parents[1]


def excel(case, output, allow_execution=False):
    if os.name!='nt':raise RuntimeError('Excel golden capture requires Windows; use a previously captured golden JSON on Linux')
    if case.get('macro') and allow_execution is not True:raise PermissionError('Capture execution requires --allow-execution')
    if Path(output).exists():raise FileExistsError(output)
    case=dict(case,input=str(office.local_path(case['input'])))
    with tempfile.TemporaryDirectory(prefix='cellwright-excel-') as temporary:
        case_path=Path(temporary)/'case.json';case_path.write_text(json.dumps(case),encoding='utf-8')
        pid_file=Path(temporary)/'excel.pid'
        command=['powershell.exe','-NoProfile','-NonInteractive','-File',str(ROOT/'harness/excel/capture.ps1'),'-CaseFile',str(case_path),'-Output',str(Path(output).resolve()),'-PidFile',str(pid_file)]
        if allow_execution:command.append('-AllowExecution')
        try:
            result=subprocess.run(command,capture_output=True,text=True,timeout=90)
            if result.returncode:raise RuntimeError(result.stderr.strip())
        except subprocess.TimeoutExpired:
            if pid_file.exists():
                pid=int(pid_file.read_text().strip())
                if pid>0:subprocess.run(['taskkill.exe','/PID',str(pid),'/T','/F'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,creationflags=subprocess.CREATE_NO_WINDOW)
            raise


def validate(case):
    from migration.runtime import coordinates
    ranges=case.get('ranges')
    if not isinstance(ranges,dict) or not 1<=len(ranges)<=100:raise ValueError('Specify 1–100 sheets and explicit cells to compare')
    total=0
    for sheet,addresses in ranges.items():
        if not isinstance(sheet,str) or not sheet or len(sheet)>31 or '\0' in sheet or not isinstance(addresses,list) or not 1<=len(addresses)<=100:
            raise ValueError('Provide sheet names and lists of explicit A1 ranges')
        for address in addresses:
            if not isinstance(address,str):raise ValueError('Cell ranges must be A1 addresses')
            r1,c1,r2,c2=coordinates(address);total+=(r2-r1+1)*(c2-c1+1)
            if total>100000:raise ValueError('Snapshot exceeds 100,000 cells')
    for spec in (case['original'],case['converted']):
        if not isinstance(spec.get('macro'),str) or not re.fullmatch(r'[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*',spec['macro']):raise ValueError('Use a qualified procedure name without workbook or script URLs')
        if not isinstance(spec.get('inputs',[]),list) or len(spec.get('inputs',[]))>7:raise ValueError('Provide up to seven scalar inputs')
        if any(not isinstance(value,(str,int,float,bool,type(None))) or isinstance(value,float) and not math.isfinite(value) for value in spec.get('inputs',[])):raise ValueError('Only finite scalar macro inputs are supported')


def verify(case,destination,allow_execution=False,libreoffice=None):
    if allow_execution is not True:raise PermissionError('Verification executes macros and requires --allow-execution')
    destination=Path(destination).resolve()
    if destination.exists() and any(destination.iterdir()):raise FileExistsError('Verification destination must be new or empty')
    validate(case)
    original=case['original'];converted=case['converted']
    destination.mkdir(parents=True,exist_ok=True)
    before=hashlib.sha256(Path(original['input']).read_bytes()).hexdigest()
    golden=destination/'excel.json'
    if case.get('golden'):
        golden.write_bytes(Path(case['golden']).read_bytes())
    else:excel(dict(original,ranges=case['ranges']),golden,allow_execution=True)
    actual=office.run(dict(converted,mode='capture',ranges=case['ranges'],allow_execution=True),libreoffice)
    (destination/'libreoffice.json').write_text(json.dumps(actual,indent=2),encoding='utf-8')
    result=compare(json.loads(golden.read_text(encoding='utf-8-sig')),actual,case.get('absolute_tolerance',1e-9),case.get('relative_tolerance',1e-9),case.get('compare_formulas',True))
    result.update(scope='Only the named procedure, inputs and captured cells in this case',case=case,original_sha256=before,converted_sha256=hashlib.sha256(Path(converted['input']).read_bytes()).hexdigest())
    if hashlib.sha256(Path(original['input']).read_bytes()).hexdigest()!=before:raise RuntimeError('Original workbook changed during execution; investigate side effects')
    (destination/'verification.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    return result
