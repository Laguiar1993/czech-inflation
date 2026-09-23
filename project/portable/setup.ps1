[CmdletBinding()]
param(
    [string]$PythonExe,
    [switch]$CheckOnly,
    [switch]$WithBloomberg,
    [ValidatePattern('^[0-9]+(\.[0-9]+)+$')]
    [string]$BloombergVersion = '3.26.9.1',
    [string]$X13Path = $env:CZ_X13_PATH
)

# Windows PowerShell 5.1 and PowerShell 7. Install only into this checkout.
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
$venvDir = Join-Path $repoRoot '.venv'
$venvPython = Join-Path $venvDir 'Scripts\python.exe'
$requirements = Join-Path $PSScriptRoot 'requirements-runtime.txt'

function Read-PythonInfo([string]$Executable) {
    $probe = 'import json,sys,struct,platform; print(json.dumps(dict(version=list(sys.version_info[:3]),bits=struct.calcsize("P")*8,implementation=platform.python_implementation(),platform=sys.platform,machine=platform.machine(),prefix=sys.prefix,base_prefix=sys.base_prefix)))'
    $output = $probe | & $Executable -I -B -
    if ($LASTEXITCODE -ne 0) { throw "Python probe failed for '$Executable'. Select an installed CPython 3.12 x64 python.exe." }
    try { return ($output | ConvertFrom-Json) }
    catch { throw "Cannot read Python identity from '$Executable'. Pass python.exe itself, not py.exe or a shell command." }
}

function Assert-PythonInfo($Info, [string]$Label) {
    if ($Info.implementation -ne 'CPython' -or $Info.platform -ne 'win32' -or
        $Info.bits -ne 64 -or $Info.machine -notin @('AMD64', 'x86_64') -or
        $Info.version[0] -ne 3 -or $Info.version[1] -ne 12) {
        throw "$Label is $($Info.implementation) $($Info.version -join '.') / $($Info.bits)-bit / $($Info.machine). This lock requires Windows x64 CPython 3.12 (tested 3.12.14). Install/select that interpreter explicitly; setup never installs Python or changes major/minor automatically. Historical Python 3.14 locks are separate environments."
    }
}

function Invoke-VenvPython([string[]]$PythonArgs, [string]$Step) {
    & $venvPython -I -B @PythonArgs
    if ($LASTEXITCODE -ne 0) {
        throw "$Step failed (exit $LASTEXITCODE). No global install was attempted. Review the error above, fix connectivity or wheel availability, then rerun the same setup command. The partial .venv is retained."
    }
}

function Invoke-VenvCode([string]$Code, [string[]]$ScriptArgs, [string]$Step) {
    # stdin preserves Python quotes on Windows PowerShell 5.1 native argument passing.
    $Code | & $venvPython -I -B - @ScriptArgs
    if ($LASTEXITCODE -ne 0) { throw "$Step failed (exit $LASTEXITCODE). See the Python error above; .venv is retained." }
}

try {
    if ([string]::IsNullOrWhiteSpace($PythonExe)) {
        throw 'Pass -PythonExe with the explicit full path to an installed CPython 3.12 x64 python.exe. See portable/ENVIRONMENT.md. No default interpreter is guessed.'
    }
    if (-not (Test-Path -LiteralPath $PythonExe -PathType Leaf)) {
        throw "Python executable not found: '$PythonExe'. Pass -PythonExe with the full python.exe path."
    }
    $PythonExe = (Resolve-Path -LiteralPath $PythonExe).Path
    $baseInfo = Read-PythonInfo $PythonExe
    Assert-PythonInfo $baseInfo 'Selected interpreter'
    if (-not (Test-Path -LiteralPath $requirements -PathType Leaf)) { throw "Missing requirements: $requirements" }

    if (Test-Path -LiteralPath $venvDir) {
        $venvItem = Get-Item -LiteralPath $venvDir -Force
        if (-not $venvItem.PSIsContainer -or ($venvItem.Attributes -band [IO.FileAttributes]::ReparsePoint)) {
            throw "Refusing existing .venv file/junction/symlink at '$venvDir'. Use a real checkout-local directory."
        }
        $cfgPath = Join-Path $venvDir 'pyvenv.cfg'
        if (-not (Test-Path -LiteralPath $cfgPath -PathType Leaf)) {
            throw "Existing '$venvDir' has no pyvenv.cfg. It was left unchanged; move it aside deliberately before retrying."
        }
        $cfg = Get-Content -LiteralPath $cfgPath -Raw
        if ($cfg -notmatch '(?m)^version\s*=\s*3\.12\.') {
            throw 'Existing .venv is not a Python 3.12 environment. It was left unchanged; move it aside and rerun with a Python 3.12 executable.'
        }
        if ($cfg -notmatch '(?im)^include-system-site-packages\s*=\s*false\s*$') {
            throw 'Existing .venv must set include-system-site-packages = false. Move it aside and recreate; setup will not use global packages.'
        }
        if (-not (Test-Path -LiteralPath $venvPython -PathType Leaf)) { throw "Existing .venv is incomplete: missing '$venvPython'. Move it aside and rerun." }
        $venvInfo = Read-PythonInfo $venvPython
        Assert-PythonInfo $venvInfo 'Existing .venv'
        if ([IO.Path]::GetFullPath($venvInfo.prefix).TrimEnd('\') -ine [IO.Path]::GetFullPath($venvDir).TrimEnd('\') -or
            $venvInfo.prefix -eq $venvInfo.base_prefix) {
            throw 'Existing .venv interpreter does not belong to this checkout. Recreate .venv after moving/cloning the repository.'
        }
    }

    if ([string]::IsNullOrWhiteSpace($X13Path)) {
        $bundledX13 = Join-Path $repoRoot 'portable\vendor\x13as\x13as.exe'
        if (Test-Path -LiteralPath $bundledX13 -PathType Leaf) { $X13Path = $bundledX13 }
    }
    if (-not [string]::IsNullOrWhiteSpace($X13Path)) {
        if (-not [IO.Path]::IsPathRooted($X13Path)) { $X13Path = Join-Path $repoRoot $X13Path }
        if (-not (Test-Path -LiteralPath $X13Path -PathType Leaf)) { throw "X13 executable not found: '$X13Path'. Check CZ_X13_PATH / -X13Path or the bundled vendor file." }
        $X13Path = (Resolve-Path -LiteralPath $X13Path).Path
        Write-Host "X13 selected for this process: $X13Path"
    } else {
        Write-Warning 'X13 is not configured. Python setup can finish, but production verification needs portable/vendor/x13as/x13as.exe or an explicit CZ_X13_PATH.'
    }
    Write-Host "Selected CPython $($baseInfo.version -join '.') x64: $PythonExe"
    Write-Host "Target environment: $venvDir"
    if ($CheckOnly) { Write-Host 'Prerequisites checked; no files installed or changed.'; return }

    # Restore process environment settings even on failure. No user/machine changes.
    $savedEnv = @{}
    foreach ($name in @('TEMP','TMP','MPLCONFIGDIR','NUMBA_CACHE_DIR','PIP_CONFIG_FILE','CZ_X13_PATH')) {
        $savedEnv[$name] = [Environment]::GetEnvironmentVariable($name, 'Process')
    }
    try {
        $createVenv = -not (Test-Path -LiteralPath $venvDir)
        $cacheDir = Join-Path $venvDir 'portable-cache'
        New-Item -ItemType Directory -Force -Path $cacheDir | Out-Null
        $env:TEMP = $cacheDir
        $env:TMP = $cacheDir
        $env:MPLCONFIGDIR = Join-Path $cacheDir 'matplotlib'
        $env:NUMBA_CACHE_DIR = Join-Path $cacheDir 'numba'
        $env:PIP_CONFIG_FILE = 'NUL'
        if ($X13Path) { $env:CZ_X13_PATH = $X13Path }
        if ($createVenv) {
            Write-Host 'Creating isolated .venv with the selected interpreter...'
            & $PythonExe -I -B -m venv $venvDir
            if ($LASTEXITCODE -ne 0) { throw 'venv creation failed. The selected Python must include venv and ensurepip. No global bootstrap or Python installation was attempted.' }
        }
        $pipArgs = @('-m','pip','--isolated','--disable-pip-version-check','--no-cache-dir','--require-virtualenv')
        Invoke-VenvPython ($pipArgs + @('install','--only-binary=:all:','--index-url','https://pypi.org/simple','-r',$requirements)) 'Runtime installation'
        if ($WithBloomberg) {
            # 3.25.5.1 is archived evidence but unavailable as a CPython 3.12 wheel.
            # Keep capture with its original interpreter for historical client parity.
            Write-Host "Optional Bloomberg API version: $BloombergVersion (historical capture: 3.25.5.1)."
            Invoke-VenvPython ($pipArgs + @('install','--only-binary=:all:','--index-url','https://blpapi.bloomberg.com/repository/releases/python/simple/','-c',$requirements,"blpapi==$BloombergVersion")) 'Optional Bloomberg API installation'
            Invoke-VenvPython ($pipArgs + @('install','--only-binary=:all:','--no-binary=pdblp','--index-url','https://pypi.org/simple','-c',$requirements,'xbbg==0.7.7','pdblp==0.1.8','pytz==2026.2','ruamel.yaml==0.18.17','ruamel.yaml.clib==0.2.15')) 'Optional Bloomberg wrappers installation'
            Invoke-VenvCode -Code 'import blpapi, pdblp; from xbbg import blp; print("Bloomberg imports OK; Terminal connectivity and entitlements still require a live test.")' -ScriptArgs @() -Step 'Bloomberg import check'
        }
        Invoke-VenvPython ($pipArgs + @('check')) 'Dependency consistency check'
        $verify = @'
import importlib, importlib.metadata as md, pathlib, sys
for line in pathlib.Path(sys.argv[1]).read_text(encoding="utf-8-sig").splitlines():
    line = line.partition("#")[0].strip()
    if line:
        name, expected = line.split("==")
        actual = md.version(name)
        if actual != expected:
            raise RuntimeError(f"Version mismatch: {name}: {actual} != {expected}")
for name in ("numpy", "pandas", "scipy.linalg", "statsmodels.api", "sklearn", "quantile_forest", "duckdb", "requests", "openpyxl", "pyarrow", "matplotlib", "pytest", "bs4", "pdfplumber", "tsdisagg", "shap", "xlrd"):
    module = importlib.import_module(name)
    if not pathlib.Path(module.__file__).resolve().is_relative_to(pathlib.Path(sys.prefix).resolve()):
        raise RuntimeError(f"External package leaked into .venv: {name}: {module.__file__}")
print("All pinned versions match; numerical, model, data and test dependencies import from .venv.")
'@
        Invoke-VenvCode -Code $verify -ScriptArgs @($requirements) -Step 'Runtime version and binary import check'
        Write-Host 'Python environment installed and checked. Restore packed assets before model verification:'
        Write-Host "  Set-Location '$repoRoot'"
        Write-Host "  & '$venvPython' -E -s -B -m portable restore"
        Write-Host 'Use portable/ENVIRONMENT.md and portable/START_HERE.md for activation, local data/X13 paths and production commands.'
    } finally {
        foreach ($name in $savedEnv.Keys) { [Environment]::SetEnvironmentVariable($name, $savedEnv[$name], 'Process') }
    }
} catch {
    Write-Error -Message $_.Exception.Message -ErrorAction Continue
    exit 1
}

