# SPDX-License-Identifier: EUPL-1.2
"""Assemble a source-only VBA fixture without changing Excel security settings."""
import subprocess
import zipfile
from pathlib import Path

import openpyxl

ROOT=Path(__file__).resolve().parents[1]


def assemble(temporary, binary, output):
    output=Path(output)
    if output.exists():raise FileExistsError(output)
    output.parent.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(temporary) as source,zipfile.ZipFile(output,'x',zipfile.ZIP_DEFLATED) as target:
        for entry in source.infolist():
            value=source.read(entry.filename)
            if entry.filename=='[Content_Types].xml':
                value=value.replace(b'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml',b'application/vnd.ms-excel.sheet.macroEnabled.main+xml')
                value=value.replace(b'</Types>',b'<Override PartName="/xl/vbaProject.bin" ContentType="application/vnd.ms-office.vbaProject"/></Types>')
            elif entry.filename=='xl/_rels/workbook.xml.rels':
                value=value.replace(b'</Relationships>',b'<Relationship Type="http://schemas.microsoft.com/office/2006/relationships/vbaProject" Target="vbaProject.bin" Id="rIdVBA"/></Relationships>')
            elif entry.filename=='xl/workbook.xml':value=value.replace(b'<workbookPr',b'<workbookPr codeName="ThisWorkbook"',1)
            elif entry.filename=='xl/worksheets/sheet1.xml':value=value.replace(b'<sheetPr>',b'<sheetPr codeName="Sheet1">',1)
            target.writestr(entry.filename,value)
        target.writestr('xl/vbaProject.bin',Path(binary).read_bytes())


def main():
    output=ROOT/'corpus/generated/arithmetic-source-only.xlsm'
    if output.exists():raise FileExistsError(output)
    temporary=ROOT/'target/arithmetic.xlsx'
    book=openpyxl.Workbook();book.active.title='Data';book.save(temporary)
    binary=ROOT/'target/arithmetic-vba.bin'
    subprocess.run(['cargo','run','--quiet','--example','generate_vba_fixture','--',str(binary)],check=True,cwd=ROOT)
    assemble(temporary,binary,output)
    print(output)


if __name__=='__main__':main()
