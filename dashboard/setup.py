# SPDX-License-Identifier: EUPL-1.2
"""Dependency checks without opening Office or running a workbook."""
import importlib.util
import os
import subprocess
import sys
from pathlib import Path
from migration import office


def check(binary):
    checks=[]
    def add(key,label,available,needed,action):checks.append({'id':key,'label':label,'available':bool(available),'needed_for':needed,'action':action})
    add('scanner','Workbook scanner',Path(binary).is_file(),'Inventory','Use the full Cellwright archive, or build the scanner with cargo build --locked --release.')
    add('python','Python 3.11+',sys.version_info>=(3,11),'Dashboard and conversion','Install Python 3.11 or newer from python.org and add it to PATH; reopen the launcher.')
    for name,needed in [('openpyxl','Standalone Python workbooks'),('pandas','Power Query candidates')]:
        add(name,name,importlib.util.find_spec(name) is not None,needed,'Install the optional packages with python -m pip install -r requirements.txt.')
    try:
        directory=office.program()
        add('libreoffice','LibreOffice Calc',True,'Basic and UNO candidates','')
        interpreter=Path(os.environ.get('CELLWRIGHT_UNO_PYTHON') or (directory/'python.exe' if os.name=='nt' else '/usr/bin/python3'))
        try:
            flags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0
            result=subprocess.run([str(interpreter),'-c','import uno'],capture_output=True,timeout=10,creationflags=flags)
            ready=result.returncode==0
        except (OSError,subprocess.TimeoutExpired):ready=False
        add('uno','LibreOffice UNO Python',ready,'Basic and UNO candidates','On Ubuntu install python3-uno. On Windows use LibreOffice with its Python runtime; set CELLWRIGHT_UNO_PYTHON if using a separate UNO interpreter.')
    except FileNotFoundError:
        add('libreoffice','LibreOffice Calc',False,'Basic and UNO candidates','Install LibreOffice Calc. On Ubuntu: sudo apt install libreoffice-calc python3-uno. Set CELLWRIGHT_LIBREOFFICE to its program directory for a custom installation.')
    excel=False
    if os.name=='nt':
        import winreg
        try:
            with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT,'Excel.Application'):excel=True
        except OSError:pass
    add('excel','Desktop Excel',excel,'New reference captures','Use a saved Excel capture on Linux, or a Windows machine with Excel for new captures. Inventory and conversion do not need Excel.')
    demo=office.ROOT/'corpus/generated/formatting-button.xlsm'
    if not demo.exists():demo=office.ROOT/'demo/formatting-button.xlsm'
    return {'checks':checks,'first_scan_ready':all(c['available'] for c in checks if c['id'] in ('scanner','python')),'demo':str(demo) if demo.exists() else None,'consulting_url':os.environ.get('CELLWRIGHT_CONSULTING_URL','https://scottcampbellconsulting.com/')}
