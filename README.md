# Czech inflation

**Full research archive**: all tracked models, research data/results, recorded nowcasts and paths, and the exact R35 dashboard. The original project is in `project/`.

## Smaller downloads

**[Working package — 119 MB](https://github.com/Laguiar1993/czech-inflation/releases/download/r35-portable-2026-09-23/czech-inflation-small-r35.zip)** is the recommended download for the Bloomberg computer. It contains every model source file, the production inputs, exact dashboard, setup and manual-input guide. Extract it completely, then double-click **open-dashboard.cmd**. Old bulk backtest outputs and unused research downloads stay in the full archive.

**[Page only — 0.6 MB](https://github.com/Laguiar1993/czech-inflation/releases/download/r35-portable-2026-09-23/czech-inflation-page-r35.zip)** opens the same saved dashboard immediately; extract and open **index.html**. This tiny option does not run models.

These are prebuilt ZIPs. GitHub's **Code → Download ZIP** still downloads the much larger full research archive.

The working ZIP was extracted and checked: all 57 model source files retained; exact reproduction of the three saved nowcasts and 39 path rows; new nowcast/path/momentum input preparation passed. [Verification](distribution/SMALL_DOWNLOAD_VERIFICATION.json).

## Offline operator package (R48f, 25 September 2026) — start here on the Bloomberg computer

Download **[czech-inflation-offline-r48f.zip](https://github.com/Laguiar1993/czech-inflation/releases/download/r48f-offline-2026-09-25/czech-inflation-offline-r48f.zip)** from release [r48f-offline-2026-09-25](https://github.com/Laguiar1993/czech-inflation/releases/tag/r48f-offline-2026-09-25): 151,294,734 bytes, SHA-256 `80753944b3a899ef0ff43924c87647b88ec77d2278556e524e9d28356b9dbb78`, built from commit `55f60f0` (3,600 members; `PACKAGE_MANIFEST.json` inside lists every member hash). Check the file says **r48f**.

**After extracting, double-click `OPEN-THIS-PAGE.cmd`.** The package contains eleven earlier dashboard editions, kept because the verification chain reads their files; each of those opens and shows the forecast as it stood when it was sealed, so opening one by hand shows an old number. The front door goes to the current page, `START_HERE.txt` names it, and every superseded folder says so on disk.

The current forecast is September 2026 at **-0.187% m/m (2.3% y/y)**, with prices through August everywhere. If you see -0.204 you are looking either at a sealed earlier edition or at `verify --models`, which replays a 22 September reference record to prove the code still reproduces it and now says so in its output.

**Working with an assistant on that computer?** Paste it **[BLOOMBERG_MACHINE_HANDOFF.md](BLOOMBERG_MACHINE_HANDOFF.md)** first: the rules, clocks, monthly order and what it must not override.

Then read `START_HERE.txt` and **`OFFLINE_OPERATOR_GUIDE.md`**, and keep **[MANUAL_DOWNLOADS.md](MANUAL_DOWNLOADS.md)** beside you for the inputs the Terminal does not carry.

What the R48 line gives you: `cpi ledger show` answers "what is out of date" from evidence, printing for every series the last figure held, the day it actually reached us, how old that is and how often the series delivers, and calling a series overdue only when its own rhythm says a newer figure should already be in hand; the 37-group blocks build on the staged download and advance with everything else; farm prices are admitted from the 18th under versioned availability rules; the page is rebuilt from your runs with a computed overview and no frozen text; the three-model roster; live CNB rounds appended after each report; the release calendar captured from Bloomberg; and the Python 3.10 lock (numpy 2.2.4, pandas 2.2.3, scipy 1.15.2, statsmodels 0.14.4, scikit-learn 1.6.1) on which `portable verify --models` reproduces the reference nowcast and path exactly. Works with Python 3.10, 3.11 or 3.12; no command calls the CNB ARAD API or any AI service.

## Previous offline packages

Releases [r48e](https://github.com/Laguiar1993/czech-inflation/releases/tag/r48e-offline-2026-09-25), [r48d](https://github.com/Laguiar1993/czech-inflation/releases/tag/r48d-offline-2026-09-25), [r48c](https://github.com/Laguiar1993/czech-inflation/releases/tag/r48c-offline-2026-09-25), [r48b](https://github.com/Laguiar1993/czech-inflation/releases/tag/r48b-offline-2026-09-25) and [r48](https://github.com/Laguiar1993/czech-inflation/releases/tag/r48-offline-2026-09-24) are the same route at earlier stages. Use R48f above.

## Open the page

Clone this repository and double-click **open-dashboard.cmd**, or open **project/output/inflation_dashboard_r35/index.html** in Chrome. It works immediately without Bloomberg or Python.

## Run the models on the Bloomberg computer

Start with **[project/portable/START_HERE.md](project/portable/START_HERE.md)**. It contains the setup, verification and production commands.

- **[Manual inputs: precise download and entry instructions](project/portable/MANUAL_INPUTS.md)**
- **[Windows environment and Bloomberg setup](project/portable/ENVIRONMENT.md)**
- **[Transfer verification](TRANSFER_VERIFICATION.json)**

The dashboard is the dated September 22, 2026 snapshot. Fresh model runs create new records; they do not automatically rewrite this historical page. All dashboard builders are included for the next dated publication.

Two oversized historical CSVs and the legacy database are losslessly compressed. Run `python -m portable restore` from `project/` after setup. The release contains the original Git-history bundle. No source research files were rewritten to relocate the project.
