# SPDX-License-Identifier: EUPL-1.2
"""Compare the extracted controlled M query against its Excel-loaded table."""
import argparse
import json
import subprocess
from pathlib import Path
from harness.compare import compare
from migration.m_runtime import convert, run
from migration.verify import excel

ROOT=Path(__file__).resolve().parents[1]


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--binary',type=Path,required=True)
    parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args()
    destination=args.out.resolve();destination.mkdir()
    workbook=ROOT/'corpus/generated/sales-query.xlsx'
    subprocess.run([str(args.binary.resolve()),'extract',str(workbook),'--out',str(destination/'inventory')],check=True)
    source=next((destination/'inventory/extract').rglob('*.m'))
    convert(source,destination/'candidate')
    result=run(json.loads((destination/'candidate/query.json').read_text()),'Sales',ROOT/'corpus')
    assert list(result.columns)==['Region','Total'] and len(result)==1
    excel({'input':str(workbook),'ranges':{'Sales':['A1:B2']}},destination/'excel.json')
    cells={'A1':{'value':'Region','formula':None},'B1':{'value':'Total','formula':None},'A2':{'value':str(result.iloc[0,0]),'formula':None},'B2':{'value':float(result.iloc[0,1]),'formula':None}}
    actual={'schema_version':'1','engine':'pandas','sheets':{'Sales':cells}}
    (destination/'pandas.json').write_text(json.dumps(actual,indent=2),encoding='utf-8')
    proof=compare(json.loads((destination/'excel.json').read_text(encoding='utf-8-sig')),actual)
    (destination/'verification.json').write_text(json.dumps(proof,indent=2),encoding='utf-8')
    assert proof['passed'],proof
    print('Power Query / pandas: PASS, 4 cells')


if __name__=='__main__':main()
