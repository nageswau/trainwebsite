$ErrorActionPreference = "Stop"
$sourceDir = Join-Path $PSScriptRoot "..\docs\sources"
$outFile = Join-Path $PSScriptRoot "..\docs\evidence\SOURCE_HASHES_CURRENT.txt"

Get-ChildItem $sourceDir -File |
    Where-Object { $_.Name -ne ".gitkeep" } |
    Sort-Object Name |
    ForEach-Object {
        $h = Get-FileHash $_.FullName -Algorithm SHA256
        "$($h.Hash.ToLower())  $($_.Name)"
    } | Set-Content -Encoding UTF8 $outFile

Write-Host "Written: $outFile"
