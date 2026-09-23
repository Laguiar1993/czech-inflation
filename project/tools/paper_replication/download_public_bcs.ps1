<#
Download the public ECFIN Business and Consumer Survey archives used by the
CNB WP 9/2026 A6 data checklist.

The research environment may not permit outbound downloads. Run this script
on a machine with internet access, then copy the resulting extracted files
into data/paper_replication/raw_bcs. It does not touch the operating nowcast.
#>
[CmdletBinding()]
param(
    [string]$OutputRoot = (Join-Path $PSScriptRoot '..\..\data\paper_replication\raw_bcs')
)

$base = 'https://ec.europa.eu/economy_finance/db_indicators/surveys/documents/series/nace2_ecfin_2608'
$archives = [ordered]@{
    'industry_total_sa_nace2.zip'  = "$base/industry_total_sa_nace2.zip"
    'services_total_sa_nace2.zip'  = "$base/services_total_sa_nace2.zip"
    'retail_total_sa_nace2.zip'    = "$base/retail_total_sa_nace2.zip"
    'building_total_sa_nace2.zip'  = "$base/building_total_sa_nace2.zip"
    'consumer_total_sa_nace2.zip'  = "$base/consumer_total_sa_nace2.zip"
    'consumer_inflation_nace2.zip' = "$base/consumer_inflation_nace2.zip"
}

$OutputRoot = [System.IO.Path]::GetFullPath($OutputRoot)
New-Item -ItemType Directory -Force -Path $OutputRoot | Out-Null

foreach ($entry in $archives.GetEnumerator()) {
    $zipPath = Join-Path $OutputRoot $entry.Key
    $extractPath = Join-Path $OutputRoot ([System.IO.Path]::GetFileNameWithoutExtension($entry.Key))
    Write-Host "Downloading $($entry.Key)"
    Invoke-WebRequest -Uri $entry.Value -OutFile $zipPath -UseBasicParsing -ErrorAction Stop
    if (Test-Path $extractPath) {
        Remove-Item -LiteralPath $extractPath -Recurse -Force
    }
    Expand-Archive -LiteralPath $zipPath -DestinationPath $extractPath -Force
}

Write-Host "Downloaded and extracted $($archives.Count) archives under $OutputRoot"
