param(
    [Parameter(Mandatory=$true)][string]$Target,
    [string]$Database,
    [string]$X13,
    [switch]$WithPath,
    [switch]$ExpectationsComparison
)
$ErrorActionPreference = 'Stop'
if ($Target -notmatch '^\d{4}-(0[1-9]|1[0-2])$') { throw 'Target must have YYYY-MM format.' }
if ($Database) { $env:CZ_CPI_DB = (Resolve-Path -LiteralPath $Database).Path }
if ($X13) { $env:CZ_X13_PATH = (Resolve-Path -LiteralPath $X13).Path }
$pythonPath = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $pythonPath)) { $pythonPath = 'python' }
$forecastArgs = @('-B', (Join-Path $PSScriptRoot 'forecast_independent.py'), '--live', '--target', $Target)
if ($WithPath) { $forecastArgs += '--path' }
if ($ExpectationsComparison) { $forecastArgs += '--include-expectations-comparison' }
& $pythonPath @forecastArgs
exit $LASTEXITCODE
