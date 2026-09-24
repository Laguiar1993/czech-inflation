# Czech inflation

**Full research archive**: all tracked models, research data/results, recorded nowcasts and paths, and the exact R35 dashboard. The original project is in `project/`.

## Smaller downloads

**[Working package — 119 MB](https://github.com/Laguiar1993/czech-inflation/releases/download/r35-portable-2026-09-23/czech-inflation-small-r35.zip)** is the recommended download for the Bloomberg computer. It contains every model source file, the production inputs, exact dashboard, setup and manual-input guide. Extract it completely, then double-click **open-dashboard.cmd**. Old bulk backtest outputs and unused research downloads stay in the full archive.

**[Page only — 0.6 MB](https://github.com/Laguiar1993/czech-inflation/releases/download/r35-portable-2026-09-23/czech-inflation-page-r35.zip)** opens the same saved dashboard immediately; extract and open **index.html**. This tiny option does not run models.

These are prebuilt ZIPs. GitHub's **Code → Download ZIP** still downloads the much larger full research archive.

The working ZIP was extracted and checked: all 57 model source files retained; exact reproduction of the three saved nowcasts and 39 path rows; new nowcast/path/momentum input preparation passed. [Verification](distribution/SMALL_DOWNLOAD_VERIFICATION.json).

## Offline operator package (R48, 24 September 2026) — start here on the Bloomberg computer

Download **[czech-inflation-offline-r48.zip](https://github.com/Laguiar1993/czech-inflation/releases/download/r48-offline-2026-09-24/czech-inflation-offline-r48.zip)** from release [r48-offline-2026-09-24](https://github.com/Laguiar1993/czech-inflation/releases/tag/r48-offline-2026-09-24): 150,904,040 bytes, SHA-256 `41f571cf8b0cd0fad71eb3ed0e3c493d173c84e53ba41341b6afa1e19ea76301`, built from commit `1f78769` (3,403 members; `PACKAGE_MANIFEST.json` inside lists every member hash).

Extract it, read `START_HERE.txt`, then **`OFFLINE_OPERATOR_GUIDE.md`**. New since R45: the page is rebuilt from your runs with a computed overview analysis and no frozen text (guide 3.10); the three-model roster; live CNB rounds appended after each report (3.9); the release calendar captured from Bloomberg (3.3); Python 3.10 supported with its own lock (numpy 2.2.4, pandas 2.2.3, scipy 1.15.2, statsmodels 0.14.4, scikit-learn 1.6.1), on which `portable verify --models` reproduces the main nowcast and the path exactly. Works with Python 3.10, 3.11 or 3.12; no command calls the CNB ARAD API or any AI service.

## Previous offline package (R45, 23 September 2026)

Download **[czech-inflation-offline-r45.zip](https://github.com/Laguiar1993/czech-inflation/releases/download/r45-offline-2026-09-23/czech-inflation-offline-r45.zip)** from release [r45-offline-2026-09-23](https://github.com/Laguiar1993/czech-inflation/releases/tag/r45-offline-2026-09-23): 143,904,538 bytes, SHA-256 `1480a04e4cbab0ba84f756f0d36667832a0028c22842fb06dbc6f34744298dec`, built from commit `dca4ec19` (3,303 files; `PACKAGE_MANIFEST.json` inside lists every member hash).

Extract it, read `START_HERE.txt`, then **`OFFLINE_OPERATOR_GUIDE.md`**. It is written for a machine with a Bloomberg Terminal and no AI assistant: Bloomberg captures for every series the Terminal holds, browser downloads and typed CSV/JSON templates for the rest, staged with an offline importer that validates them with the model's own parsers and journals them in a local SQLite database. It contains the model source, the inputs the production nowcast and path read, the R44 page (dated September 2026), the templates and the source catalog. No command in it calls the CNB ARAD API or any AI service. After extraction, `portable restore`, `doctor` and `verify --models` reproduce the recorded September forecasts offline; the release notes record the rehearsal.

The full-project transfer below (`project/`, R35 release) is unchanged and remains the complete research archive.

## Open the page

Clone this repository and double-click **open-dashboard.cmd**, or open **project/output/inflation_dashboard_r35/index.html** in Chrome. It works immediately without Bloomberg or Python.

## Run the models on the Bloomberg computer

Start with **[project/portable/START_HERE.md](project/portable/START_HERE.md)**. It contains the setup, verification and production commands.

- **[Manual inputs: precise download and entry instructions](project/portable/MANUAL_INPUTS.md)**
- **[Windows environment and Bloomberg setup](project/portable/ENVIRONMENT.md)**
- **[Transfer verification](TRANSFER_VERIFICATION.json)**

The dashboard is the dated September 22, 2026 snapshot. Fresh model runs create new records; they do not automatically rewrite this historical page. All dashboard builders are included for the next dated publication.

Two oversized historical CSVs and the legacy database are losslessly compressed. Run `python -m portable restore` from `project/` after setup. The release contains the original Git-history bundle. No source research files were rewritten to relocate the project.
