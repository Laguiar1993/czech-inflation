# Czech inflation

**Full research archive**: all tracked models, research data/results, recorded nowcasts and paths, and the exact R35 dashboard. The original project is in `project/`.

## Smaller downloads

**[Working package — 119 MB](https://github.com/Laguiar1993/czech-inflation/releases/download/r35-portable-2026-09-23/czech-inflation-small-r35.zip)** is the recommended download for the Bloomberg computer. It contains every model source file, the production inputs, exact dashboard, setup and manual-input guide. Extract it completely, then double-click **open-dashboard.cmd**. Old bulk backtest outputs and unused research downloads stay in the full archive.

**[Page only — 0.6 MB](https://github.com/Laguiar1993/czech-inflation/releases/download/r35-portable-2026-09-23/czech-inflation-page-r35.zip)** opens the same saved dashboard immediately; extract and open **index.html**. This tiny option does not run models.

These are prebuilt ZIPs. GitHub's **Code → Download ZIP** still downloads the much larger full research archive.

The working ZIP was extracted and checked: all 57 model source files retained; exact reproduction of the three saved nowcasts and 39 path rows; new nowcast/path/momentum input preparation passed. [Verification](distribution/SMALL_DOWNLOAD_VERIFICATION.json).

## Open the page

Clone this repository and double-click **open-dashboard.cmd**, or open **project/output/inflation_dashboard_r35/index.html** in Chrome. It works immediately without Bloomberg or Python.

## Run the models on the Bloomberg computer

Start with **[project/portable/START_HERE.md](project/portable/START_HERE.md)**. It contains the setup, verification and production commands.

- **[Manual inputs: precise download and entry instructions](project/portable/MANUAL_INPUTS.md)**
- **[Windows environment and Bloomberg setup](project/portable/ENVIRONMENT.md)**
- **[Transfer verification](TRANSFER_VERIFICATION.json)**

The dashboard is the dated September 22, 2026 snapshot. Fresh model runs create new records; they do not automatically rewrite this historical page. All dashboard builders are included for the next dated publication.

Two oversized historical CSVs and the legacy database are losslessly compressed. Run `python -m portable restore` from `project/` after setup. The release contains the original Git-history bundle. No source research files were rewritten to relocate the project.
