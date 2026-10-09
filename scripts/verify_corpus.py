# SPDX-License-Identifier: EUPL-1.2
"""Execute only MacroFerry's controlled arithmetic fixture and retain case evidence."""
import argparse
import json
import os
from pathlib import Path
from migration.convert import convert
from migration.verify import verify

ROOT=Path(__file__).resolve().parents[1]


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out',required=True,type=Path)
    parser.add_argument('--binary',default=ROOT/('target/release/macroferry.exe' if os.name=='nt' else 'target/release/macroferry'),type=Path)
    parser.add_argument('--golden-suite',type=Path,help='Previously captured suite for Linux verification')
    parser.add_argument('--allow-execution',action='store_true')
    args=parser.parse_args()
    if not args.allow_execution:parser.error('Controlled suite requires --allow-execution')
    args.out=args.out.resolve()
    if args.out.exists():raise FileExistsError(args.out)
    args.out.mkdir(parents=True)
    original=ROOT/'corpus/generated/arithmetic-source-only.xlsm'
    cases=[]
    for target in ('basic','basic-uno','python-uno'):
        destination=args.out/target
        convert(original,destination,args.binary,target)
        for index,amount in enumerate((2,0,2.5,-2)):
            converted={'input':str(destination/'converted.ods'),'macro':'Standard.Arithmetic.Calculate','inputs':[amount]}
            if target=='python-uno':converted.update(macro='Calculate',python_module=str(destination/'source/arithmetic.py'))
            case={'original':{'input':str(original),'macro':'Arithmetic.Calculate','inputs':[amount]},'converted':converted,'ranges':{'Data':['A1:D5']}}
            if args.golden_suite:case['golden']=str(args.golden_suite/f'{target}-case-{index}'/'excel.json')
            result=verify(case,args.out/f'{target}-case-{index}',allow_execution=True)
            print(f"{target}, input {amount}: {'PASS' if result['passed'] else 'FAIL'} · {result['cells_checked']} cells",flush=True)
            cases.append({'target':target,'input':amount,'passed':result['passed'],'cells_checked':result['cells_checked'],'differences':result['differences']})
    (args.out/'suite.json').write_text(json.dumps(cases,indent=2),encoding='utf-8')
    if not all(case['passed'] for case in cases):raise AssertionError('Execution comparison failed')


if __name__=='__main__':main()
