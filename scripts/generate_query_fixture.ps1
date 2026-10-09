# SPDX-License-Identifier: EUPL-1.2
param([string]$OutputDirectory = (Join-Path $PSScriptRoot '..\corpus\generated'))
$ErrorActionPreference = 'Stop'
$destination = [IO.Path]::GetFullPath($OutputDirectory)
New-Item -ItemType Directory -Path $destination -Force | Out-Null
$output = Join-Path $destination 'sales-query.xlsx'
if (Test-Path -LiteralPath $output) { throw 'Fixture already exists' }
$source = Get-Content -LiteralPath (Join-Path $PSScriptRoot '..\corpus\Sales.m') -Raw
$excel = $null
$book = $null
try {
    $excel = New-Object -ComObject Excel.Application
    $excel.Visible = $false
    $excel.DisplayAlerts = $false
    $excel.EnableEvents = $false
    $book = $excel.Workbooks.Add()
    $sheet = $book.Worksheets.Item(1)
    $sheet.Name = 'Sales'
    $book.Queries.Add('Sales', $source) | Out-Null
    $connection = 'OLEDB;Provider=Microsoft.Mashup.OleDb.1;Data Source=$Workbook$;Location=Sales;Extended Properties=""'
    $table = $sheet.ListObjects.Add(0, $connection, $true, 1, $sheet.Range('A1'))
    $table.QueryTable.CommandType = 2
    $table.QueryTable.CommandText = 'SELECT * FROM [Sales]'
    $table.QueryTable.BackgroundQuery = $false
    $table.QueryTable.Refresh($false) | Out-Null
    $book.SaveAs($output, 51)
    Write-Output ('Power Query fixture: ' + $output)
} finally {
    if ($book) { $book.Close($false); [Runtime.InteropServices.Marshal]::FinalReleaseComObject($book) | Out-Null }
    if ($excel) { $excel.Quit(); [Runtime.InteropServices.Marshal]::FinalReleaseComObject($excel) | Out-Null }
}
