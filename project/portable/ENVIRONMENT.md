# Portable Windows environment

Run these commands from the **project/** directory in the portable GitHub
layout, using Windows PowerShell 5.1 or PowerShell 7. The outer repository root
holds the migration README; project/ preserves the original project files and
contains portable/. Below, "project root" means that project/ directory.
Use **64-bit x86 CPython 3.12** with venv/ensurepip; the inspected base was **3.12.14**.
The script requires an explicit executable path. It does not install Python, change
the registry, edit user/machine environment variables, or change execution policy
persistently. A venv must be recreated after cloning or moving the repository.

## Install and restore

Choose an already installed Python 3.12 x64 executable. If necessary, obtain Python
separately through your organization's approved installation process or
[Python's Windows downloads](https://www.python.org/downloads/windows/).
A different 3.12 patch is accepted but is not a claim of identical runtime results.
Python 3.13/3.14, 32-bit Python, ARM64 Python and PyPy fail with an explanation.

~~~powershell
Set-Location 'D:\Research\czech-inflation\project'  # your clone's project directory
$python312 = 'C:\Path\To\Python312\python.exe'  # full executable path, not py.exe
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\portable\setup.ps1 -PythonExe $python312 -CheckOnly
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\portable\setup.ps1 -PythonExe $python312

# Required before model/archive verification; restoration itself uses only stdlib.
& .\.venv\Scripts\python.exe -E -s -B -m portable restore
& .\.venv\Scripts\python.exe -E -s -B -m portable doctor
& .\.venv\Scripts\python.exe -E -s -B -m portable verify --models
& .\.venv\Scripts\python.exe -E -s -B -m portable --help
~~~

The command-line execution-policy override applies only to that child process.
If organization policy prevents scripts, use an approved shell/process; do not
change machine policy. Setup resolves its root from its own location, so it also
works when invoked by absolute path from another directory.

Setup creates/reuses only the project directory's .venv, installs the exact package pins
from PyPI, runs pip check, verifies every pinned version, and imports the native
numerical/data dependencies from inside that venv. It ignores inherited
PYTHONPATH/PYTHONHOME and pip user/config overrides while installing. It uses
binary wheels for the default runtime; no global pip invocation or hidden Python
installation occurs. Temporary pip/build and package-cache files are placed
under .venv/portable-cache. Rerunning the same command keeps matching packages;
it does not delete an existing environment or silently change the requirements.
A failed download leaves the partial environment available for retry. An invalid
or incompatible .venv is rejected; deliberately move it aside before recreating.

The fresh GitHub snapshot preserves all tracked project content under project/,
including the original README and attributes. Two CSVs larger
than GitHub's file limit are shipped compressed under portable/packed and restored
losslessly by portable restore before verification. The legacy DuckDB archive is
restored to portable/local/czechia.duckdb. Original Git history is preserved
separately as the private release .bundle asset. Runtime setup does not unpack
these assets, alter frozen records, or change Git history. Use the parent
migration's START_HERE.md/portable CLI for restoration and archive verification.

## Activate and run

Activation is optional. Explicit .venv Python commands are the least ambiguous:

~~~powershell
# -E ignores inherited PYTHON* settings; -s excludes user site packages.
# Keep the project root as cwd so "-m portable" can find the portable package.
& .\.venv\Scripts\python.exe -E -s -B -m portable --help
& .\.venv\Scripts\python.exe -I -B -m pip --isolated check
~~~

Do not add the old Temp/cpi-r32-runtime or sibling pythonlibs folders to PYTHONPATH.
The -I flag is suitable for pip and standalone package checks; it removes the
working directory from Python's import search, so use -E -s for repository modules.

For an interactive activated session:

~~~powershell
.\.venv\Scripts\Activate.ps1
Remove-Item Env:PYTHONPATH -ErrorAction SilentlyContinue
Remove-Item Env:PYTHONHOME -ErrorAction SilentlyContinue
$env:PYTHONNOUSERSITE = '1'
$env:PYTHONDONTWRITEBYTECODE = '1'
python -m portable restore
python -m portable --help
# When finished:
deactivate
~~~

If activation is blocked by shell policy, use the explicit executable commands
above. Activation and these environment assignments affect only the current
PowerShell process.

The portable launcher derives repository-relative local inputs. For direct
historical Python entry points, set these in each new PowerShell session:

~~~powershell
$repo = (Get-Location).Path
$env:CZ_X13_PATH = Join-Path $repo 'portable\vendor\x13as\x13as.exe'
$env:CZ_CPI_DB = Join-Path $repo 'portable\local\czechia.duckdb'
$env:MPLCONFIGDIR = Join-Path $repo '.venv\portable-cache\matplotlib'
$env:NUMBA_CACHE_DIR = Join-Path $repo '.venv\portable-cache\numba'
$env:TEMP = Join-Path $repo '.venv\portable-cache'
$env:TMP = $env:TEMP
& .\.venv\Scripts\python.exe -E -s -B -m portable --help
~~~

Set CZ_X13_PATH before importing the legacy data adapter/paper-panel modules:
they read it at import time. Setup prefers an explicit -X13Path or inherited
CZ_X13_PATH, then portable/vendor/x13as/x13as.exe. It reports the selected path
and restores its process settings when it exits. It writes no config.local.json;
the launcher derives the defaults. Passing -X13Path does not persist an override
for a later process. Missing default X13 permits Python-only setup, with a warning;
an explicitly supplied invalid path is an error.

The launcher includes doctor, restore, verify --models, serve, capture-bloomberg,
capture-public farm/categories, prepare-nowcast, nowcast/readiness, and
prepare-path/run-path; consult each command's --help for required arguments.
Use the supported commands in START_HERE.md and portable --help for R32-R35
production, with newly captured input directories and valid decision clocks.
Installing packages alone does not establish live source access, data readiness,
seasonal-adjustment validity, or forecast parity. Avoid rerunning historical
write-producing commands against their frozen output directories.

## Versions and coverage

On 2026-09-22 the effective source environment was inspected with the bundled
Python executable and the existing path order:

- Python: C:/Users/luis_/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe.
- PYTHONPATH: C:/Users/luis_/AppData/Local/Temp/cpi-r32-runtime;../pythonlibs,
  resolved from the original project root.
- NumPy 2.5.2; pandas 3.0.1; SciPy 1.18.1; statsmodels 0.15.0;
  scikit-learn 1.9.0; quantile-forest 1.4.2.
- DuckDB 1.5.5; requests 2.34.2; matplotlib 3.11.1; PyArrow 25.0.1;
  openpyxl 3.1.5; pytest 9.1.1.

These are the versions actually imported, not the root requirements-r9-lock.txt
or requirements-numerical-lock.txt (which describe older Python 3.14 runs).
The portable requirements preserve all available installed package versions in
the dependency closure, including timezone data and numerical support packages.

An AST import audit covered 456 tracked Python files outside output/ and work/.
The default requirements cover all model families: NumPy/SciPy/statsmodels
regressions and time-series models, scikit-learn/quantile-forest, SHAP,
temporal disaggregation, plotting, pytest, DuckDB, requests, Parquet/Arrow,
XLSX/XLS reading, HTML parsing and PDF input extraction.

The source environment lacked beautifulsoup4, tsdisagg, shap, xlrd and formulaic
(a declared statsmodels dependency). Those and their missing transitive packages
are separately identified in requirements-runtime.txt and pinned from a clean
Windows/Python 3.12 resolution. Their inclusion extends import coverage; it does
not establish historical numerical parity for research paths that previously
could not import. The full pin list is an environment lock without artifact
hashes; access to the named PyPI wheels is required.

## Optional Bloomberg installation

Bloomberg is optional for archive viewing and offline models. The archived
market-snapshot request.json files record xbbg 0.7.7 and blpapi 3.25.5.1
under Anaconda, which may use a different Python/pandas stack from the model
runtime. **Prefer keeping the working Bloomberg interpreter separate**:

~~~powershell
& .\.venv\Scripts\python.exe -E -s -B -m portable capture-bloomberg --help
# Supply the capture's other required arguments shown by --help:
& .\.venv\Scripts\python.exe -E -s -B -m portable capture-bloomberg --python 'C:\Path\To\Anaconda\python.exe'
~~~

The launcher prepends that interpreter's directory, Library/bin and Scripts to
the child PATH for Anaconda DLL resolution. Its environment changes apply to the
capture child, keeping the model .venv separate. New capture evidence must record
the actual Bloomberg Python/package versions. Use this route if xbbg/pandas or
DLL compatibility fails in the numerical venv.

If explicitly choosing a combined environment, install into the same .venv:

~~~powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\portable\setup.ps1 -PythonExe $python312 -WithBloomberg
~~~

The switch defaults to blpapi **3.26.9.1**; its version is printed before install.
The historical **3.25.5.1** pin was tested against the official index and no
compatible CPython 3.12 wheel was available. This is a client-version difference,
not a replacement claim for archived captures. To request another explicitly
reviewed version, pass -BloombergVersion X.Y.Z. Numerical pins remain fixed.

The switch obtains blpapi from
[Bloomberg's official API wheel index](https://blpapi.bloomberg.com/repository/releases/python/simple/)
and the wrappers from PyPI, constrained by every exact runtime pin. A conflict
fails installation instead of downgrading/upgrading numerical packages; a final
version audit verifies the pins again. It also installs
pdblp 0.1.8 for the older data/bloomberg_adapter.py path, plus pinned pytz and
ruamel.yaml dependencies. pdblp is distributed only as a source archive; pip
builds that pure Python wrapper in an isolated temporary build environment.
Numerical packages and blpapi remain wheel-only.

The [official Bloomberg API installation instructions](https://professional.bloomberg.com/support/api-library/)
confirm that current Python wheels include their required C++ API runtime.
Do not copy Terminal DLLs or credentials into this repository. Setup does not
install or configure Bloomberg Terminal, request credentials, or initiate a
market-data download.

You may inspect imports without connecting:

~~~powershell
& .\.venv\Scripts\python.exe -I -B -c 'import blpapi; print(blpapi.version())'
& .\.venv\Scripts\python.exe -I -B -c 'from xbbg import blp; import pdblp; print(blp.__file__)'
~~~

A successful import is not a Terminal connection or entitlement check. On the
destination Bloomberg computer, log into Terminal, run the supported portable
Bloomberg diagnostic/capture command, and retain the new request/version evidence.
The historical xbbg wrapper also needs a live compatibility check against pandas
3.0.1; do not silently downgrade numerical packages to make a wrapper work.
If the exact Bloomberg wheel is unavailable for the chosen interpreter, setup
fails and retains the environment; review any version change explicitly.

## Census X-13

The migration includes the exact previously installed Census executable at
portable/vendor/x13as/x13as.exe, together with source/hash metadata. Use that
binary for reproducible runs and check its hash against the packaged metadata.
It is independent of the Python packages. The parent archive verifier validates
the shipped bytes; setup checks path existence only.

~~~powershell
Get-FileHash -Algorithm SHA256 .\portable\vendor\x13as\x13as.exe
~~~

For a replacement installation, the
[official Census X-13 Windows download page](https://www.census.gov/data/software/x13as.X-13ARIMA-SEATS.html)
provides ZIP archives, documentation and testairline.spc. It currently lists
Version 1.1 Build 62 and separate ASCII/HTML output executables. Prefer the ASCII
output executable for the statsmodels reader. Extract to a local folder without
an installer or PATH/registry change, set CZ_X13_PATH to the full executable path,
and record its SHA-256 and build banner. Do not overwrite the bundled historical
binary or assume that a newer official release reproduces its forecasts.

To test an independently downloaded Census archive, copy its testairline.spc to
a new work subdirectory, run the selected executable there with argument
testairline (no extension), check the process exit code, and inspect its .err/.out
and generated output files. This establishes execution, not forecast equivalence.
Then run the R35 seasonal wrapper checks from the restored repository:

~~~powershell
# After portable restore, with CZ_X13_PATH set as above:
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD = '1'
& .\.venv\Scripts\python.exe -E -s -B -m pytest .\tools\momentum_r35\test_seasonal.py -q -p no:cacheprovider --basetemp .\work\portable-x13-check
~~~

Pytest owns and clears the specified --basetemp directory; use a dedicated
disposable work directory, never a data or frozen output folder. Production
R32-R35 checks also need real inputs and must validate availability/status,
rather than accepting an X13 fallback as a production result.

## Verification scope

Verified on 2026-09-22 in work/portable-setup-check using the inspected base
Python and a clean network installation from PyPI:

- All 55 default package pins matched; pip check passed and all required binary
  imports resolved inside the test .venv.
- Imported __version__ values matched the inspected distribution versions for all
  twelve primary numerical/data/test packages listed above.
- Native linear algebra, an OLS fit, Ridge and quantile-forest fitting, DuckDB SQL
  and an in-memory XLSX write/read succeeded without loading project snapshots.
- Twelve PowerShell setup tests passed, covering explicit Python selection,
  incompatible versions/bitness, path names with spaces, inherited Python path
  isolation, protected existing directories, local X13 discovery and failed-install
  preservation of a newly created local venv.
- Optional blpapi 3.26.9.1, xbbg 0.7.7 and pdblp 0.1.8 installed/imported under
  Windows PowerShell 5.1; pip check and every numerical pin still matched.
  No Terminal connection or market-data request was made.

Installation
logs and resolver evidence are local scratch files and are not portable inputs.
The setup contract tests can be rerun without network:

~~~powershell
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD = '1'
& .\.venv\Scripts\python.exe -E -s -B -m pytest .\portable\test_setup.py -q -p no:cacheprovider --basetemp .\work\portable-setup-tests
~~~

Fresh-clone restore, exact dashboard bytes, full production runtime/forecast
verification, legacy DuckDB completeness and live Bloomberg verification are
owned by the parent migration. Consult START_HERE.md for its final evidence.

