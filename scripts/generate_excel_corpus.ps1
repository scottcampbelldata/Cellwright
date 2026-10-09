# SPDX-License-Identifier: EUPL-1.2
param([string]$OutputDirectory = (Join-Path $PSScriptRoot '..\corpus\generated'))
$ErrorActionPreference = 'Stop'
$destination = [IO.Path]::GetFullPath($OutputDirectory)
if (Test-Path -LiteralPath $destination) { throw 'Corpus destination already exists' }
New-Item -ItemType Directory -Path $destination | Out-Null
$excel = $null
$book = $null
try {
    $excel = New-Object -ComObject Excel.Application
    $excel.Visible = $false
    $excel.DisplayAlerts = $false
    $excel.EnableEvents = $false
    $book = $excel.Workbooks.Add()
    $book.Worksheets.Item(1).Name = 'Data'
    $project = $book.VBProject
    if (-not $project) { throw 'Excel denies VBA project access; generate this fixture manually without changing security policy' }
    $module = $project.VBComponents.Add(1)
    $module.Name = 'Arithmetic'
    $source = Get-Content -LiteralPath (Join-Path $PSScriptRoot '..\corpus\Arithmetic.bas') -Raw
    $module.CodeModule.AddFromString($source)
    $book.SaveAs((Join-Path $destination 'arithmetic.xlsm'), 52)
    $book.SaveAs((Join-Path $destination 'arithmetic.xlsb'), 50)
    $book.SaveAs((Join-Path $destination 'arithmetic.xls'), 56)
    Write-Output ('Generated controlled arithmetic fixtures: ' + $destination)
} finally {
    if ($book) { $book.Close($false); [Runtime.InteropServices.Marshal]::FinalReleaseComObject($book) | Out-Null }
    if ($excel) { $excel.Quit(); [Runtime.InteropServices.Marshal]::FinalReleaseComObject($excel) | Out-Null }
}
