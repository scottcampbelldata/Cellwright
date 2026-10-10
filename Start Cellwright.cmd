@rem SPDX-License-Identifier: EUPL-1.2
@echo off
cd /d "%~dp0"
if exist "cellwright.exe" (
  cellwright.exe serve --open --data "%LOCALAPPDATA%\Cellwright\workspace"
) else (
  target\release\cellwright.exe serve --open --data "%LOCALAPPDATA%\Cellwright\workspace"
)
if errorlevel 1 (
  echo Install Python 3.11 or newer from https://www.python.org/downloads/ and reopen this launcher.
  pause
)
