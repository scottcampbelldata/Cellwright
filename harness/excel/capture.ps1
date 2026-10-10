# SPDX-License-Identifier: EUPL-1.2
param([Parameter(Mandatory)][string]$CaseFile, [Parameter(Mandatory)][string]$Output, [switch]$AllowExecution, [string]$PidFile)
$ErrorActionPreference = 'Stop'
$case = Get-Content -LiteralPath $CaseFile -Raw | ConvertFrom-Json
if ($case.macro -and -not $AllowExecution) { throw 'Macro execution requires -AllowExecution' }
if (Test-Path -LiteralPath $Output) { throw 'Output already exists' }
$excel = $null
$book = $null
try {
    $excel = New-Object -ComObject Excel.Application
    if ($PidFile) {
        Add-Type -TypeDefinition 'public static class CellwrightProcess { [System.Runtime.InteropServices.DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(System.IntPtr window, out uint processId); }'
        [uint32]$excelProcessId = 0
        [CellwrightProcess]::GetWindowThreadProcessId([IntPtr]$excel.Hwnd, [ref]$excelProcessId) | Out-Null
        $excelProcessId | Set-Content -LiteralPath $PidFile
    }
    $excel.Visible = $false
    $excel.DisplayAlerts = $false
    $excel.EnableEvents = $false
    $excel.AskToUpdateLinks = $false
    $excel.AutomationSecurity = $(if ($AllowExecution) { 1 } else { 3 })
    $book = $excel.Workbooks.Open([IO.Path]::GetFullPath($case.input), 0, $true)
    if ($case.macro) {
        $arguments = @(("'" + $book.Name.Replace("'", "''") + "'!" + $case.macro)) + @($case.inputs)
        if ($arguments.Length -gt 8) { throw 'Harness supports up to seven scalar macro parameters' }
        switch ($arguments.Length) {
            1 { $excel.Run($arguments[0]) | Out-Null }
            2 { $excel.Run($arguments[0],$arguments[1]) | Out-Null }
            3 { $excel.Run($arguments[0],$arguments[1],$arguments[2]) | Out-Null }
            4 { $excel.Run($arguments[0],$arguments[1],$arguments[2],$arguments[3]) | Out-Null }
            5 { $excel.Run($arguments[0],$arguments[1],$arguments[2],$arguments[3],$arguments[4]) | Out-Null }
            6 { $excel.Run($arguments[0],$arguments[1],$arguments[2],$arguments[3],$arguments[4],$arguments[5]) | Out-Null }
            7 { $excel.Run($arguments[0],$arguments[1],$arguments[2],$arguments[3],$arguments[4],$arguments[5],$arguments[6]) | Out-Null }
            8 { $excel.Run($arguments[0],$arguments[1],$arguments[2],$arguments[3],$arguments[4],$arguments[5],$arguments[6],$arguments[7]) | Out-Null }
        }
    }
    $excel.CalculateFull()
    $sheets = @{}
    $total = 0
    foreach ($sheetProperty in $case.ranges.PSObject.Properties) {
        $sheet = $book.Worksheets.Item($sheetProperty.Name)
        $cells = @{}
        foreach ($address in $sheetProperty.Value) {
            $range = $sheet.Range($address)
            $total += $range.Cells.CountLarge
            if ($total -gt 100000) { throw 'Snapshot exceeds 100,000 cells' }
            foreach ($cell in $range.Cells) {
                $key = $cell.Address($false, $false)
                $value = $cell.Value2
                $formula = $(if ($cell.HasFormula) { $cell.Formula } else { $null })
                $cells[$key] = @{value=$value; formula=$formula}
                [Runtime.InteropServices.Marshal]::FinalReleaseComObject($cell) | Out-Null
            }
            [Runtime.InteropServices.Marshal]::FinalReleaseComObject($range) | Out-Null
        }
        $sheets[$sheetProperty.Name] = $cells
        [Runtime.InteropServices.Marshal]::FinalReleaseComObject($sheet) | Out-Null
    }
    $json = @{schema_version='1'; engine='excel'; sheets=$sheets} | ConvertTo-Json -Depth 12
    $stream = [IO.File]::Open([IO.Path]::GetFullPath($Output), [IO.FileMode]::CreateNew, [IO.FileAccess]::Write)
    try { $bytes = [Text.UTF8Encoding]::new($false).GetBytes($json); $stream.Write($bytes,0,$bytes.Length) } finally { $stream.Dispose() }
} finally {
    if ($book) { $book.Close($false); [Runtime.InteropServices.Marshal]::FinalReleaseComObject($book) | Out-Null }
    if ($excel) { $excel.Quit(); [Runtime.InteropServices.Marshal]::FinalReleaseComObject($excel) | Out-Null }
    [GC]::Collect()
    [GC]::WaitForPendingFinalizers()
}
