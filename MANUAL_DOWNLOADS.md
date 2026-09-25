# Getting the by-hand inputs on the Bloomberg computer

Most of the data arrives through the Terminal. Four things do not, because the Terminal does not carry them: the
37-group CPI panel, farm-gate prices, the official release figures, and the CNB report table. This is how to fetch each
one by hand, where to put it, and how to confirm it landed. Nothing here needs a login.

Work in PowerShell opened in the package folder, with the environment already set up (`portable\setup.ps1`, then the
shorthands in section 1 of `OFFLINE_OPERATOR_GUIDE.md`). Replace `<you>` with your Windows user name and the dates with
the current ones. Every output directory must be new: the commands refuse to overwrite.

## Before you start: what is actually missing

```powershell
cpi ledger show
```

This prints every series the models read, the last figure held, **the day it actually reached us**, how old that is,
and how often that series delivers. It flags a series only when its own rhythm says a newer figure should already be
in hand. Work the list top to bottom. Run it again at the end; nothing should be left overdue except series whose
next figure genuinely is not out.

---

## 1. The 37-group CPI panel (CZSO CEN0101E)

Feeds the eight blocks, the drivers and the breadth figure on the overview, and the category momentum panel. Monthly,
published with the detailed release, roughly the tenth to fourteenth of the following month. It is descriptive: no
forecast reads it.

1. Open **https://data.csu.gov.cz/opendata/sady/CEN0101E/distribuce/csv** in the browser.
2. The file downloads as `CEN0101E.csv` (tens of megabytes; let it finish). Leave it in `Downloads`.
3. Stage it, prepare it, then run both lanes:

```powershell
manual stage --kind categories --file C:\Users\<you>\Downloads\CEN0101E.csv --source-url https://data.csu.gov.cz/opendata/sady/CEN0101E/distribuce/csv --output output\momentum_r35_inputs\categories_2026-10-13 --database C:\czech-inflation-data\operator.sqlite
cpi prepare-momentum --capture output\momentum_r35_inputs\categories_2026-10-13 --through 2026-09 --output output\momentum_r35_inputs\prepared_2026-09
cpi momentum         --prepared output\momentum_r35_inputs\prepared_2026-09 --output output\momentum_r35\run_2026-09
cpi monitor          --prepared output\momentum_r35_inputs\prepared_2026-09 --snapshot output\manual_inputs\<your latest nowcast capture> --output output\inflation_monitor_2026-09
```

`--through` is the **last complete published month**, not the current one. The prepare step records the download in
the ledger by itself, so `cpi ledger show` will show the new date without any further action.

**Check:** `cpi monitor` prints `groups_month`. It must be the month you passed to `--through`. If it is a month
behind, the download happened before the detailed release; wait for the release and download again.

## 2. Farm-gate prices (CZSO CEN0203B)

A real model input: it drives the food block of the nowcast. Monthly, published inside the producer-price release on
the sixteenth or seventeenth of the following month. The model admits it from the eighteenth.

```powershell
cpi capture-public --kind farm --output output\current_path_r34_inputs\farm_capture_2026-10-16
```

That fetches **https://data.csu.gov.cz/opendata/sady/CEN0203B/distribuce/csv** directly and records the download time,
which is what the availability rule and the ledger both use. If the machine cannot reach the site, download the URL in
the browser and stage the file instead:

```powershell
manual stage --kind farm --file C:\Users\<you>\Downloads\CEN0203B.csv --source-url https://data.csu.gov.cz/opendata/sady/CEN0203B/distribuce/csv --output output\current_path_r34_inputs\farm_capture_2026-10-16 --database C:\czech-inflation-data\operator.sqlite
```

**Check:** `cpi ledger show` should show `CZSO CEN0203B` holding the month before last with today's date as `obtained`.
The capture refuses if it arrives after the forecast clock you then use, which is deliberate: capture before you
record a nowcast, not after.

## 3. The official release figures (outcomes)

These score the forecast and supply the goods and services split the page reports. Twice per month: the flash around
the fourth to seventh, the detailed release around the tenth to fourteenth.

1. Open the release page on **https://csu.gov.cz/rychle-informace/** and find "Consumer price indices - inflation -
   <month> <year>". Save the page as HTML next to the file you will write, so the source travels with it.
2. Fill in the outcomes template (`templates\outcomes.json` in the package) with the month, the stage (`flash` or
   `detailed`), the headline y/y and m/m, and the page URL.
3. Stage it:

```powershell
manual stage --kind outcomes --file C:\Users\<you>\Downloads\outcomes_2026-09_flash.json --source-url <the release page URL> --output output\manual_inputs\outcomes_2026-09_flash --database C:\czech-inflation-data\operator.sqlite
```

**Check:** the staging command prints the parsed values back. They must match the page. Stage the flash and the
detailed release as two separate files; never edit the first one.

## 4. The CNB Monetary Policy Report table

Only four times a year, after each report (February, May, August, November). It extends the rounds replay.

1. Open the report page on **https://www.cnb.cz/en/monetary-policy/monetary-policy-report/** and download the
   key-indicators workbook (the forecast table).
2. Note the **report date** and the **cut-off date** printed on that page. You need both.
3. Stage and append, as in section 3.9 of the operator guide.

**Check:** `rounds add` prints the round it created and refuses a path run recorded after the report day, which is the
protection against back-dating. If it refuses, use the run recorded before the report day.

---

## What to do when something says OVERDUE

`cpi ledger show` flags a series when its own history says a newer figure should have arrived. The order to work in:

1. **Bloomberg series.** Run the two captures again (`cpi capture-bloomberg --lane nowcast` and `--lane path`). If the
   ticker still shows the same last figure, the Terminal itself has not received it; note that and move on. The
   ledger will keep showing its true age, which is correct.
2. **CZSO files.** Sections 1 and 2 above. If the statistics office has not published yet, the flag is telling you the
   release is late, not that you missed it; check the release page before assuming.
3. **Outcomes and CNB tables.** These only appear when you stage them, so an overdue flag means the staging step is
   outstanding.

Never resolve a flag by editing a date, a hash, or a file. The commands refuse it, and the flag is the only thing
standing between you and a forecast built on old numbers.

## What is never obtained by hand

The Bloomberg captures cover everything else the models read: headline, food, alcohol and tobacco, the CNB core and
regulated indices, the fuel item, import prices, food producer prices, weekly pump prices and the koruna fixing. If
one of those is overdue, the answer is a new capture, never a typed number. The only typed inputs the package accepts
are the ones listed above, plus the January energy announcements and the consensus, both covered in the operator guide.
