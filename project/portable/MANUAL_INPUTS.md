# Manual and public inputs for the private migration

Verified against production R32/R33/R34/R35 code and official sources on **22 September 2026**. Use [ENVIRONMENT.md](ENVIRONMENT.md) for the pinned environment and the migration quickstart for the full production workflow. This file describes source acquisition, exact data contracts and handoffs. The R31 handoff's instructions to rebuild shared calendars/use the database loader are superseded.

All paths below are relative to the **project directory containing `portable/` and `cz_struct.py`**: `project/` in the migrated GitHub layout, or the current `cpi-independent/` directory before migration. Run commands there after activating the pinned environment (`python` below). Without activation, replace `python -B` with `& .\.venv\Scripts\python.exe -E -s -B`. Replace every `NEW_*` directory with a fresh name, preferably a UTC timestamp. Keep original downloads, their metadata, prepared inputs and forecast outputs separate. Never replace `data/`, an existing capture, a frozen manifest or a recorded forecast to make a new run pass.

## Quick checklist

1. Restore the migration assets and configure the pinned environment; retain [static dependencies](#9-static-dependencies-carry-the-archive-do-not-re-download-it-into-place).
2. Make **two** [Bloomberg captures](#start-a-fresh-decision-two-bloomberg-snapshots), then capture [farm prices](#5-farm-prices-one-raw-download-two-different-transforms). Use a new directory and [actual source metadata](#2-archive-original-bytes-and-clocks-once-per-capture) for every capture.
3. Check released observations; add only supported [CNB core/regulated supplements](#3-monthly-observed-cpi-bloomberg-coverage-and-official-fallback) if needed. Create the [release-calendar overlay](#4-first-and-detailed-release-calendar-append-only-overlay).
4. Review [annual energy announcements and basket weights](#6-administered-announcements-and-basket-weights); pass any new energy CSV explicitly with `--announcements`.
5. [Prepare, check readiness and record nowcast/path](#10-preparation-readiness-and-handoff-checks), keeping the two captures separate and using the explicit farm source.
6. Optionally refresh the [37-group momentum monitor](#7-cen0101e-37-group-monitor-not-a-forecast-input) and [comparison evidence](#8-optional-benchmark-and-analytical-inputs). New nowcast/path/momentum runs write new output directories; **the delivered R35 HTML remains a sealed snapshot and does not update automatically**.

## 1. What you actually need

| Input | Required for | Obtain/check when | New destination and consumer |
|---|---|---|---|
| Bloomberg observations | Independent nowcast and path | Each decision; check released monthly observations, weekly pumps and daily FX | **Two** captures below; R33 current bundle and R34 path preparer |
| CZSO CEN0203B farm prices | Nowcast **seven** products; path **four** products | Monthly; check again when farm lag becomes due | `output/manual_inputs/NEW_FARM/CEN0203B.csv` plus adjacent metadata; explicit `--farm-raw` |
| CPI first/detail release calendar | Nowcast eligibility, path and publication gates | After every detailed CPI release; check again before recording | `output/manual_inputs/NEW_CALENDAR/live_calendar.csv`; portable `--calendar` |
| Observed CNB core/regulated supplement | Only if the exact Bloomberg m/m feed lacks a released month | After detailed CPI; inspect each new capture | `output/manual_inputs/NEW_CNB/manual_inputs.csv`; `--manual-inputs` |
| January energy announcements | Review for every live call; new rows when an approved change is known | September, November, December checkpoints and amendments | New prospective-rows CSV plus raw evidence; portable wrapper's explicit `--announcements` |
| Basket weights | Existing values are required; no monthly re-entry | Review annual basket; next **expected** new weight regime is 2028 | Preserve shipped workbooks/tables; new basket requires a versioned integration, section 6 |
| Historical/static inputs and X-13 | Required as described in section 9 | Copy once; validate on setup | Retain repository assets; configure local executable |
| CZSO CEN0101E 37-group panel | R35 momentum/dashboard analysis only | Each detailed CPI release | New category capture/prepared package, section 7 |
| CNB report tables; analytical observed y/y; consensus | Comparison/analysis only | Each report/release or benchmark capture | Separate evidence packages, section 8; never independent forecast features |

Opening `output/inflation_dashboard_r35/index.html` needs **none of these refreshes**. It is the self-contained delivered snapshot. Fresh input preparation does not update that HTML or constitute a forecast. Commands here are operator instructions; writing this guide did not execute forecasts or seasonal adjustment.

### Start a fresh decision: two Bloomberg snapshots

Use a past/completed observation end date appropriate to the actual run, not a future date. The following date is an example from the delivery; change it for a later decision. Download completion is always recorded at the actual current time.

```powershell
python -B -m portable capture-bloomberg --lane nowcast --output output/manual_inputs/NEW_BBG_NOWCAST --end-date 2026-09-21
python -B -m portable capture-bloomberg --lane path --output output/manual_inputs/NEW_BBG_PATH --end-date 2026-09-21
python -B -m portable capture-public --kind farm --output output/manual_inputs/NEW_FARM
```

The portable interfaces above are implemented in `portable/cli.py`. The source implementations are `tools.market_data.probe_bloomberg_candidates`, with **unchanged** `tools/forecast_updates_r33/bloomberg_current_config.json` for nowcast and `tools/current_path_r34/capture_config.json` for path. The first starts in 2026 and extends the frozen history; the second starts in January 2015. Do not combine them: R34's monthly validator rejects repeated ticker/month observations in a daily nowcast capture.

Nowcast config: `CZCPMOM Index`, `CZCPYOY Index`, `CZCPFMOM Index`, `CZCPAMOM Index`, `CZCIXM Index`, `CZCIRM Index`, `CP7FCZ Index`, `CZEIIMOM Index`, `CZPPA10M Index`, `ECOBETCZ Index`, `ECOBOTCZ Index`, `EURCZK CNB Curncy`. Path config: `CZCPI Index`, `CZCPF Index`, `CZPPA10M Index`, `CZCPYOY Index`, `CZCPMOM Index`. These are existing configured identities, not suggested substitutes.

Then: prepare the release overlay (section 4); inspect coverage and capture CNB supplements if needed (section 3); prepare the new nowcast with **explicit external farm input**; run readiness with the actual clock; record the nowcast; prepare the path with its separate monthly capture and the same farm archive. Section 10 lists the exact existing readiness/path entry points and the remaining integration boundaries.

## 2. Archive original bytes and clocks once per capture

For farm/categories prefer `portable capture-public`: it archives actual source metadata. For other HTML/PDF/XLSX/JSON sources, use this standard-library recipe. It writes only a **new** directory. Paste into a Python session started with `python -B`; change the URL, filename and output directory in the final call. For a browser-only download, preserve the original downloaded bytes and record the same fields manually; saving a screenshot alone is insufficient evidence for a numerical table.

```python
from pathlib import Path
from datetime import datetime, timezone
import hashlib, json, urllib.request

def capture_file(url, output, filename, *, body=None):
    out = Path(output)
    out.mkdir(parents=True, exist_ok=False)
    started = datetime.now(timezone.utc).isoformat()
    headers = {"User-Agent": "Mozilla/5.0 (Czech inflation source archive)"}
    if body is not None:
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=body, headers=headers)
    with urllib.request.urlopen(req, timeout=45) as response:
        raw = response.read()
        final_url, response_headers = response.url, dict(response.headers)
    completed = datetime.now(timezone.utc).isoformat()
    if not raw:
        raise ValueError("Empty response; retain failed directory, retry in a NEW one")
    digest = hashlib.sha256(raw).hexdigest()
    with (out / filename).open("xb") as f:
        f.write(raw)
    meta = dict(source=url, final_url=final_url, sha256=digest, bytes=len(raw),
                retrieved_at=started, completed_at=completed,
                available_from=completed, published_at=None,
                headers=response_headers,
                method="POST" if body is not None else "GET")
    if body is not None:
        meta["request_json"] = json.loads(body)
    with (out / (filename + ".metadata.json")).open("x", encoding="utf-8") as f:
        json.dump(meta, f, indent=2, ensure_ascii=False)
        f.write("\n")
    with (out / ".gitattributes").open("x", encoding="utf-8") as f:
        f.write("* -text\n")
    return raw, meta

# Direct standard-library farm capture alternative (choose one capture route):
raw, meta = capture_file(
    "https://data.csu.gov.cz/opendata/sady/CEN0203B/distribuce/csv",
    "output/manual_inputs/NEW_FARM", "CEN0203B.csv")
```

Each `capture_file` call needs a different new directory. For several documents from one publication, use children such as `NEW_CNB_REPORT/table/`, `NEW_CNB_REPORT/report/` and `NEW_CNB_REPORT/page/`; keep their paths in a companion provenance file. This is a documentation recipe, not an extra repository command or a model run. It does not create a model manifest. Let each preparation command write its own new manifest; never repair/reseal an old artifact.

**Clock rule:** reference month, source publication, retrieval start, retrieval completion, preparation time and forecast decision time are separate. Store aware UTC/offset timestamps in metadata. `available_from` for a newly obtained current-vintage response is conservatively its completion (or later if the publication itself is later). HTTP `Date`/`Last-Modified` is supporting evidence, not an invented release time. Historical rows in a new download do not become archived real-time vintages. A new forecast's clock must follow all source and preparation clocks; prospective R33 recording must start within 300 seconds of its explicit clock and finish before first release.

Store dated publication evidence in a separate `publication.json` if discovered later, citing the raw document/hash and exact page/table; do not edit the capture metadata to backdate availability. Every normalized CSV should cite raw path/hash, selector, unit conversion and availability in its companion provenance.

## 3. Monthly observed CPI: Bloomberg coverage and official fallback

The current bundle uses headline, food, alcohol/tobacco, CNB core, CNB regulated and fuel histories through **target minus one**. Inspect `coverage.csv`, `errors.json` and `history_long.csv` in the new Bloomberg snapshot, then readiness; a successful connection alone does not establish current coverage. Values are NSA **m/m percent**, e.g. `0.3` means +0.3%, except the raw fuel input which is an index level.

| Required observation | Existing input | If missing |
|---|---|---|
| CNB core | `CZCIXM Index` | Official ARAD `SCPIMZM09MOMPECNA`; R33 manual CSV supports `core` |
| CNB regulated/administered | `CZCIRM Index` | Official ARAD `SCPIMZM02MOMPECNA`; supports `regulated` |
| Headline/food/alcohol | `CZCPMOM` / `CZCPFMOM` / `CZCPAMOM Index` | Capture official CZSO release/CEN0101E evidence; **R33 manual CSV does not accept these series** |
| Historical fuel component | `CP7FCZ Index` | R31C requires consecutive Bloomberg levels, `100*(I[t]/I[t-1]-1)`; no CZSO substitution |
| Weekly pumps | `ECOBETCZ` / `ECOBOTCZ Index` | Both required; divide CZK/1000 litres by 1000 to CZK/l, map to ISO Monday; no manual/CZSO substitution |
| Imports and food PPI | `CZEIIMOM` / `CZPPA10M Index` | No manual hook in current R33; wait for the exact feed or obtain a separately reviewed adapter |

R33 preserves old training/market cells and extends observed months; it does not rewrite older history with a current download. A gap in headline/food/alcohol or another unsupported series is an actual preparation boundary, not permission to put that series under `core` or fabricate a Bloomberg capture.

### Capture observed CNB core and regulated

Official endpoint: [ARAD indicators API](https://www.cnb.cz/aradb/api/v13/indicators-data-by-codes). Method and parsing are the existing `data.local_adapter.fetch_cnb_arad_direct`; its in-memory helper alone does not archive raw evidence. [CNB methodology](https://www.cnb.cz/docs/ARADY/MET_LIST/cpi_mz_cs.pdf) describes the analytical inflation family. The following reproducible **POST** route was verified with both exact codes; no key or login was required. Query parameters alone are not the complete request.

After defining `capture_file` above, run this in the same Python session. Set `wanted` to the released missing month strictly before the forecast target. Each code gets its own new raw directory; the parent `NEW_CNB` directory must not exist initially.

```python
from datetime import datetime, timezone
from urllib.parse import urlencode
import csv, math

out = Path("output/manual_inputs/NEW_CNB")
out.mkdir(parents=True, exist_ok=False)
wanted = "2026-08"  # example: missing released month for September's forecast
rows = []
for series, code in [("core", "SCPIMZM09MOMPECNA"),
                     ("regulated", "SCPIMZM02MOMPECNA")]:
    params = dict(snList="", periodFrom=1735689600000,  # 2025-01-01 UTC
                  periodTo=int(datetime.now(timezone.utc).timestamp()*1000),
                  roleId="U", type="single", setParams="", chartData=code+":0")
    url = "https://www.cnb.cz/aradb/api/v13/indicators-data-by-codes?"+urlencode(params)
    raw, meta = capture_file(url, out/code, code+".json",
                             body=json.dumps([code]).encode("utf-8"))
    indicator = json.loads(raw)["data"][0]["indicators"][0]
    if indicator["code"] != code:
        raise ValueError("Unexpected series identity")
    points = indicator["snapshots_data"][0]["data"]
    matches = [v for ms, v in points
               if datetime.fromtimestamp(ms/1000, timezone.utc).strftime("%Y-%m") == wanted]
    if len(matches) != 1 or matches[0] is None or not math.isfinite(float(matches[0])):
        raise ValueError("Requested month absent/duplicate/nonfinite: "+code)
    rows.append(dict(series=series, observation_month=wanted, value=float(matches[0]),
                     units="mm_pct", source=url+" ; sha256="+meta["sha256"],
                     available_from=meta["completed_at"]))
with (out/"manual_inputs.csv").open("x", encoding="utf-8", newline="") as f:
    writer = csv.DictWriter(f, fieldnames=["series", "observation_month", "value",
                                         "units", "source", "available_from"])
    writer.writeheader()
    writer.writerows(rows)
```

The returned values are already percentage changes: the verified August 2026 values were **core 0.3, regulated 0.0**. Although the ARAD English series title says “m-o-m index”, do **not** subtract 100 from these responses. Do not derive a monthly change from a rounded y/y press-commentary number.

Exact CSV contract:

```csv
series,observation_month,value,units,source,available_from
```

Only `core` and `regulated`; month `YYYY-MM`; finite decimal value; units exactly `mm_pct`; nonempty source; aware timestamp no later than the decision. Rows must be after the baseline component cutoff and before target. Duplicates or disagreement with an existing Bloomberg value fail. Pass this file with `--manual-inputs` during preparation. It is copied/hash-listed in the new bundle; R33 rechecks its availability when recording/loading.

The shipped worked evidence is `output/forecast_updates_r33/cnb_observed_20260922/`, and `current_bundle_20260922_v2` includes those two August observations. Their old capture clock is for that archive only. For later months, inspect what the source actually contains; future availability is not promised.

### Official alcohol/food/headline coverage if Bloomberg is late

Open [CZSO CPI time series](https://csu.gov.cz/produkty/isc_ts) → **Open data → Data (CSV)**, or download [CEN0101E](https://data.csu.gov.cz/opendata/sady/CEN0101E/distribuce/csv). Archive into a new category capture (section 7). The detailed [August release](https://csu.gov.cz/rychle-informace/consumer-price-indices-inflation-august-2026) also links **Table 1**, **Table 2** and **Table 3** under Annexes.

For alcohol/tobacco select `IndicatorType=6134`, `EKAKTIOCDS=0`, `UZ02P=CZ`, `CZCOICOP2.CZCOP1=02`, **blank** `CZCOICOP2.CZCOP23`, monthly `CASMKMQRM12=YYYY-MM`. Food/nonalcoholic beverages is division `01`, also with blank subgroup. Preserve leading zeroes. For a published m/m index use `TYPUDAJE4A=IM`, then `mm_pct=Hodnota-100`; verified August alcohol was `100.6`, hence `0.6%`. Alternatively `IZ2015` is a level: `100*(level[t]/level[t-1]-1)`, requiring adjacent months. Its rounded-level ratio may differ from the published monthly rate; record which measure you captured. `IR` is a y/y index and is not a monthly substitute.

These data can document or resolve the source gap, but **there is no existing `--manual-inputs alcohol|food|headline` contract**. Keep a clearly labelled review CSV such as `series,observation_month,value,units,source,available_from` beside the raw source, and obtain an explicit validated adapter extension before using it in production. Do not overwrite any prepared frame/manifest. CNB core and regulated cannot be reconstructed by substituting CZSO division totals.

## 4. First and detailed release calendar: append-only overlay

After each detailed release:

1. Open [CZSO inflation](https://csu.gov.cz/inflace-spotrebitelske-ceny), follow its latest **Rychlé informace / Consumer price indices – inflation** release and scroll to **Next News Release**. Record both the flash and detailed dates for the **next target/reference month**.
2. Capture that release page and [Information for Media](https://csu.gov.cz/statistika/information_for_media) into separate new evidence directories using section 2. The media page states that news releases are posted at **09:00**. Its publication rule plus the dated release page supplies the timestamp; a date-only schedule alone is insufficient.
3. Create `output/manual_inputs/NEW_CALENDAR/live_calendar.csv` with the exact header below. Use Prague's offset on each **release date** (`+01:00` in winter, `+02:00` in summer), not the receiving PC's London timezone. Use `ZoneInfo("Europe/Prague")` when constructing dates. Set `available_from` to the later evidence-capture completion. Record both URLs in `source` and raw hashes in companion provenance.

```csv
target_month,first_release_dt,detail_release_dt,available_from,source
```

Verified date fields for September 2026 are `2026-10-06T09:00:00+02:00` and `2026-10-13T09:00:00+02:00`; the official August page supplies those dates. Fill `available_from` with **your** actual evidence completion, not the historic delivery timestamp. Example timestamp construction:

```python
from datetime import datetime
from zoneinfo import ZoneInfo
stamp = datetime(2026, 10, 6, 9, tzinfo=ZoneInfo("Europe/Prague")).isoformat()
```

The frozen calendar ends at target `2026-08`. An overlay may contain unique sourced targets **strictly after its last target**, retaining earlier eligible overlay rows needed by a later decision. It cannot correct, backfill or replace a frozen row. All three timestamp columns require explicit offsets, and future-known rows are invisible until `available_from`. Pass `--calendar` to portable nowcast/readiness (`--live-calendar` in the underlying R32/R33 CLI); the R33 attempt retains an immutable copy which R34 subsequently uses. The current wrapper overrides the calendar in process and restores it; it does not rewrite `data/release_calendar_cz_cpi.csv`.

Do not run `tools/build_release_calendar.py` to maintain production: it writes the frozen calendar. The inherited historical-calendar conflict remains a separate unresolved research issue; the overlay does not erase it.

## 5. Farm prices: one raw download, two different transforms

Official [CEN0203B CSV](https://data.csu.gov.cz/opendata/sady/CEN0203B/distribuce/csv) returned HTTP 200 and the expected 13-column schema during verification. Use the `capture-public --kind farm` command or section 2's direct recipe; save **the entire original CSV**, not an Excel resave/filter.

Required columns: `CASMKMQR` (monthly `YYYY-MM`), `Reprezentant`, `REPRCENZEM`, `UZ02HU.STAT`, `UZ02HU.KRAJ`, `IndicatorType`, `Hodnota`, `MJ_TEXT`, `MJ_SYMBOL`. Select national rows: state `CZ`, **blank/NaN region**, and monthly codes only. The verified indicator is `6277`, mean agricultural product price in CZK. `Hodnota` is a physical price per unit in the product label, not an index or m/m percentage.

| Exact `Reprezentant` label | Code | Physical unit | Seven-product nowcast | Four-product path |
|---|---|---|---|---|
| `Pšenice potravinářská [t]` | 1011 | CZK/tonne | Yes | Yes |
| `Mléko kravské Q. tř. j. [tis. l.]` | 4911 | CZK/1000 litres | Yes | Yes |
| `Vejce slepičí konzumní tříděná [tis. ks]` | 5512 | CZK/1000 eggs | Yes | No |
| `Prasata jatečná  j.tř. SEU v JUT [t]` | 4621 | CZK/tonne | Yes | Yes |
| `Kuřata jatečná v živém I.tř.j [t]` | 5011 | CZK/tonne | Yes | Yes |
| `Brambory pozdní konzumní [t]` | 1620 | CZK/tonne | Yes | No |
| `Jablka konzumní [t]` | 2011 | CZK/tonne | Yes | No |

Keep the **double space** after `jatečná` in the pigs label. Labels above are the existing `data.struct_inputs.AGRI_BASKET`; R34 reuses positions `(0,1,3,4)` from `tools.r14_food.prepare_inputs.PRODUCTS`.

**Nowcast transform:** compute each product's `100*diff(log(price))`, then equal cross-product mean. The unchanged seven-product loader uses `skipna=True`, so report missing product coverage explicitly; do not claim it enforces all seven positive observations or silently replace it with the stricter four-product path. Reject duplicate national product/months before preparing a new source rather than relying on `pivot_table` averaging. Shift the **month labels** forward one month: a farm observation for August occupies shifted September. For target September, `agri_l0` is August and `agri_l1` is July. The frozen gate for `agri_l0` opens on the 26th of target month; `agri_l1` is due at its start. This is a model convention, not a verified publication timestamp. A newly downloaded August observation does not bypass that nowcast gate.

**Path transform:** require all four positive prices and contiguous monthly history from January 2015. Calculate each `100*log(price/January2015_price)` and average the four levels; call the output `agri4`. Do not average physical prices across incompatible units. In the verified August 2026 source, wheat/milk/pigs/chickens were 4557/9724/35489/30425. R34 preserves accepted overlapping training values and rejects conflicting normalized overlap. Newly obtained official observations become usable at actual capture completion. Unlike the nowcast's fixed current-row gate, R34 can use an already observed August row before September 26 if its source clock permits; its inherited 26th convention governs expected freshness, not proof of publication.

**Files and handoff:** `CEN0203B.csv.metadata.json` adjacent to the CSV must contain at least `source`, `sha256`, aware `retrieved_at`, aware `completed_at`. R34 validates raw bytes, metadata and clocks on every load. The portable nowcast preparer copies and pins this external capture in the new bundle.

```text
portable prepare-nowcast: --farm-raw output/manual_inputs/NEW_FARM/CEN0203B.csv
R34 inputs CLI:          --farm-raw output/manual_inputs/NEW_FARM/CEN0203B.csv
```

These are argument handoffs; section 10 gives the complete portable preparation commands. **Unwrapped `tools.forecast_updates_r33.current_bundle.prepare` always reads `data/cz_agri_prices_raw.csv`.** It has no external farm flag. For fresh farm data use the implemented `python -m portable prepare-nowcast --farm-raw ...` wrapper, which supplies the same seven-product transformation from an explicit new source. Never update that frozen CSV to make the older preparer current. Check the new provenance's farm path/hash against the capture before running.

Cadence: monthly download after the farm publication, plus a recheck before a due input blocks readiness. Retain actual capture time; no fabricated “25th/26th at 09:00” source release clock. A full current download may extend beyond an older replay origin; R34 will reject future/origin realized farm months instead of silently trimming them.

## 6. Administered announcements and basket weights

### Annual energy input: archive levels, calculate household paid-price changes

These are **future January inputs**, not realized regulated CPI or a CNB forecast. Start a new `output/manual_inputs/NEW_ENERGY/` package. Retain the shipped announcement history as historical training evidence, and create a separate CSV containing **only new prospective rows**, plus new evidence/ledger rows. Do not append to any frozen `data/*.csv`.

Official routes verified for this guide:

| Source | Exact route and what to save |
|---|---|
| [ERÚ price decisions](https://eru.gov.cz/cenove-vymery) | Filter **Rok** by issue year, **Odvětví** by `Elektřina`, `Plyn`, `Teplo` or `POZE`, and **Stav** as appropriate; press **Použít**. Open the relevant **Energetický regulační věstník / Cenový výměr**; under **Ke stažení**, download the PDF. Check the effective dates in the document, not just the issue year. Include amendments. |
| [Actual amendment example: 19/2025](https://eru.gov.cz/kopie-z-energeticky-regulacni-vestnik-192025) | **Ke stažení → Energetický regulační věstník 19/2025 → Stáhnout**. This is the actual linked URL, including `kopie-z-`; do not synthesize PDF/page names. |
| [ERÚ 2026 original announcement](https://eru.gov.cz/eru-vydal-cenove-vymery-kterymi-stanovi-regulovane-ceny-elektriny-plynu-na-rok-2026-0) and [later amendment](https://eru.gov.cz/eru-vydal-zmenovy-cenovy-vymer-kterym-upravuje-regulovane-ceny-na-rok-2026) | Capture the dated pages and attached decisions. The conditional November statement and approved December reduction are different events with different knowledge clocks. A regulated-component percentage is not a total-bill percentage. |
| [ČEZ dated supplier example](https://www.cez.cz/cs/pro-media/tiskove-zpravy/cez-prodej-od-1.-ledna-zlevnuje-elektrinu-i-plyn-pro-16-milionu-domacnosti.-zalohy-se-snizuji-i-diky-poklesu-regulovane-slozky-230772) | Capture the release and the applicable dated tariff PDF when linked. The 30 December 2025 release specifies commodity prices, VAT-inclusive equivalents, affected products and effective 1 January. For a new event follow **Pro média → Tiskové zprávy**, then the actual dated announcement; retain tariff, distribution area, consumption band and contract coverage. |
| [MPO policy/expiry example](https://mpo.gov.cz/cz/rozcestnik/pro-media/tiskove-zpravy/usporny-tarif-i-odpusteni-poplatku-za-oze--vlada-schvalila-valecny-balicek-na-pomoc-firmam-a-domacnostem--268357/) | Capture the dated approved-policy announcement and its linked enacted decision/attachments. Record each credit, cap and levy waiver separately, including expiry/extension. A policy proposal is not an approved price input. |
| [CZSO energy-treatment note](https://csu.gov.cz/note-to-consumer-prices-of-energy-october-2022) | Capture the dated methodological note establishing how CPI treats the policy. For new notes use [Inflace, spotřebitelské ceny](https://csu.gov.cz/inflace-spotrebitelske-ceny). Record this knowledge date separately from announcement/effectiveness. |

Use section 2's recipe on the actual attachment URL copied from the official page. Save originals under e.g. `NEW_ENERGY/raw/eru_<decision>/`, `raw/supplier_<product>/`, `raw/policy_<id>/`, each with metadata. A missing supplier cohort share, household consumption/spreading base, heat tariff or CPI-treatment rule remains an explicit unknown. A press release about one supplier does not establish a national household weight. Do not treat zero as “unknown” or calibrate the missing parameter to realized CPI.

Prepare `output/manual_inputs/NEW_ENERGY/announcements.csv` with the **portable wrapper's exact required columns**:

```csv
effective_month,available_from,elec_pct,gas_pct,heat_pct,provenance,source_url
```

Additional `notes`, `source_kind`, `announced_window` and raw-hash fields are useful evidence. Do not include the historical rows: `portable.runtime.announcements` appends these new rows to the unchanged frozen history in memory and restores the cached `_ANN` afterward. The `_ANN_PATH` file is never overwritten. The inherited full-file schema in `data/admin_announcements_history.csv` is not the portable supplement contract.

Fill the supplement as follows:

- `effective_month=YYYY-01`, **January 2027 or later**; `provenance` must be exactly `prospective`; `source_url` must be nonempty and identify exact primary documents. `notes` should give raw hashes, formulas, affected households and any supersession. Duplicate effective-month/availability pairs are rejected. The current scope rejects all additions before `2027-01`; historical amendments remain separate research.
- `elec_pct`, `gas_pct`, `heat_pct`: finite total-household-paid-price percentage changes from December to January, each greater than -100. `-5.0` means a 5% fall, not a fraction or headline contribution. Use `0.0` only for an evidenced unchanged fuel; unknown heat is not zero. Do not supply a fitted block-unit shock: the wrapper deliberately sets `announced_regulated_mm_est_pct` to missing.
- `available_from`: **timezone-aware ISO timestamp**, e.g. the actual UTC capture/derivation completion, no earlier than all required publications and any necessary CPI-treatment knowledge. A future effective date is not an availability date. Retain publication, effective and capture clocks separately in the evidence. The wrapper requires an offset and converts it to the model's internal naive Prague wall time; do not strip timezone information or mix a copied date-only history into this file.
- Governing rows are chosen by the model's decision-time gate. A not-yet-available row will not affect that decision. A proposal/conditional measure is not an approved magnitude; retain it only as source-check evidence until approved. If an existing prospective row is amended, use a new package with its original row and a new later-availability row, both prospective, preserving the earlier package.

Keep supporting policy and arithmetic records alongside the supplement; they are **not automatically consumed by HARD_BASE**:

```csv
# energy_policy_ledger.csv
policy_id,event,effective_month,source_pub_date,treatment_known_date,affected_items,provenance,notes,source_url

# energy_accounting_params.csv
param,value,unit,applies_from,applies_to,status,source,notes

# source_checks.csv
checked_at,source_url,raw_sha256,status,notes
```

The comment lines identify schemas; omit them from actual CSVs. Ledger `event` is `start`, `expiry`, `extension`, `amendment` or `void`; use different policy IDs for a credit and a levy waiver. Unknown `treatment_known_date` stays blank, rather than implying that CPI treatment was known. Create a new package for corrections and preserve old files. Use section 2's raw evidence recipe, record per-parameter units and source page/table, and quote CSV fields containing commas. No placeholder numeric 2027 announcement is supplied here: the future source documents must establish it.

**Arithmetic and units:** put commodity, network and levy charges on a consistent CZK/MWh basis (CZK/kWh ×1000; CZK/GJ ×3.6). Separate VAT-exclusive from VAT-inclusive prices; apply VAT once. Fixed CZK/month or CZK/connection credits require a sourced consumption/spreading denominator. Apply a cap only to its covered charge and eligibility period. Construct paid-price levels, then `100*(January/December-1)` for each fuel. Reverse expiring fixed CZK credits **additively**; do not reverse a waiver that continues. The 2023 credit and POZE waiver had different expiries. The historical parameter file still documents approximations/denominator limitations; it is not a source of new 2027 tariffs.

**Exact January gate:** `forecast_independent.calculate` and the R34 component path call `cz_struct.admin_forecast(..., announce_mode='documented')`. That mode admits `sourced_retrospective` and `prospective` rows; latest admitted `available_from <= decision` governs. All three fuel changes must be finite. Using the latest basket published by that clock, the code calculates:

```text
headline_pp = (electricity_permille*elec_pct
             + network_gas_permille*gas_pct
             + heat_permille*heat_pct) / 1000
```

The gate fires at **abs(headline_pp) >= 1.1 percentage points**, and only January forecasts receive the override. It adds `headline_pp / this_call_administered_weight` to the shock-excluded seasonal base. Do not store that quotient in the new input row. The legacy “8 block units” threshold belongs to reconstructed-scenario rows, not the current documented input contract. Non-January measures can be retained in the ledger, but the accepted forecast does not acquire a general monthly policy-shock override merely because they are entered.

**Consumption:** add `--announcements output/manual_inputs/NEW_ENERGY/announcements.csv` to `python -B -m portable readiness` and `python -B -m portable nowcast`, using the bundle/target/calendar arguments in section 10. The wrapper validates new rows, archives the CSV as `prospective_announcements.csv` and its identity in `portable_input.json`, then scopes it into the R32 calculation subprocess. Stock R32/R33 CLI has no such option.

For a path containing a future January, also use `python -B -m portable run-path ... --announcements <the-same-file>`. Its implemented wrapper requires the same announcement hash as h0 and rejects omission when h0 used a supplement. Existing `tools.current_path_r34.run` alone has no external-announcement option. Check the archived source path/hash rather than assuming a CSV was consumed because it exists on disk.

**Cadence:** check relevant decisions before every live call; review supplier/policy changes monthly, other administered fees quarterly. Fixed checkpoints are end September (heat/POZE), end November (electricity/gas), mid-December (supplier/budget changes), and immediately after amendments. ERÚ's official page also lists a gas decision around May/June. Record an entry within seven days of its source publication and before year-end under `ANNOUNCEMENT_PROTOCOL.md`; this guide's scope is preparation only. Keep a dated source-check log in the new package. Do not run the old `tools/check_announcement_sources.py` as a create-only capture recipe: it writes its shared historical log.

### Basket weights: retain 2026, plan a reviewed 2028 update

Open [CZSO Spotřební koš](https://csu.gov.cz/spotrebni_kos_archiv) → **Spotřební koš ... od ledna 2026** → XLSX icon/title. The verified [2026 XLSX](https://csu.gov.cz/docs/107516/6b4e0d00-121e-0412-a640-6f80d1c65f46/spot_kos2026.xlsx?version=1.3) is sheet `List1`, code in column A, label B, weight **E in permille**. Header says all households, effective January 2026, expenditure basis 2024; total `0` equals 1000. Archive the XLSX and archive page into `output/manual_inputs/NEW_BASKET/` with section 2's metadata; never save over `data/baskets/spot_kos2026.xlsx`.

Record a review table:

```csv
effective_year,basis_year,code,label_cs,weight_permille,source_sheet,source_cell,source,available_from
```

Keep full precision and string codes. A weight of `168.584131` permille is `0.168584131` as a model share. Extract division `01` (food/nonalcoholic beverages), division `02` (alcohol/tobacco), the fuel aggregate used by the existing anchors, and the exact electricity/network-gas/heat items and petrol/diesel pair. Match official **labels and the current classification**, not a stale numeric code: historical `04.510/04.521/04.550` and `07.222/07.221` mappings cannot simply be presumed unchanged after reclassification.

Verified 2026 extraction checks (sheet `List1`, permille; use the new workbook's actual cells for a later year):

| Code | Item | Weight | Cell |
|---|---|---:|---|
| `01` | Food/nonalcoholic beverages | 168.584131 | E6 |
| `02` | Alcohol/tobacco | 82.870815 | E86 |
| `07.22` | Motor fuels and lubricants | 30.630713 | E429 |
| `04.510` | Electricity | 43.034809 | E242 |
| `04.521` | Network gas | 17.985589 | E245 |
| `04.550` | Heat/other heating and cooling energy | 12.003732 | E261 |
| `07.222` | Petrol (95 plus 98) | 17.396233 | E432 |
| `07.221` | Diesel | 12.269359 | E430 |

The pump blend uses `petrol/(petrol+diesel)`, rounded to the existing six-decimal convention (2026: `0.586409`). The fuel **anchor** uses the broader `07.22` weight; it is not the pump-pair weight sum. Divide the three aggregate anchors by 1000; retain energy-item weights in permille for the gate calculation.

The forecast embeds `_OFFICIAL_FOOD`, `_OFFICIAL_FUEL`, `_OFFICIAL_ALC`, `_ENERGY_ITEM_WEIGHTS` in `cz_struct.py` and `OFFICIAL_PETROL_SHARE` in `models/components.py`. Merely downloading a workbook updates none of them. A new regime needs reviewed versioned tables/code, sourced classification mapping and publication evidence outside the frozen archive. `solve_weights` estimates the administered coefficient; official 37-group weights are not replacements for those fitted model shares.

The accepted model uses even-year regimes (2026/27 share the 2026 regime). **2028, around the January detailed release in February, is the next expected maintenance point under this biennial convention**, not a verified future publication date or an available 2028 file. Check the annual official archive for intervening changes. Existing `_basket_available_from` uses the January detailed-release **date normalized to midnight**, with February 15 fallback where absent; this is inherited proxy timing, not an actual intraday workbook-publication certificate. Capture the real date/time and avoid using new weights before the source is known.

R35 independently fixes 2026 weights: its loader requires effective year 2026, basis 2024, original workbook cells and a total of 1000 across its 37 groups. A later-weight monitor needs a new reviewed package/mapping, not replacing `weights.csv` inside R35 or renormalizing changed weights to force a pass.

## 7. CEN0101E: 37-group monitor, not a forecast input

There is no dataset named “CEN0101E37”: this is the **37-group selection from CEN0101E**. Open [CPI time series](https://csu.gov.cz/produkty/isc_ts) → **Open data → Data (CSV)**, or use the [verified direct CSV](https://data.csu.gov.cz/opendata/sady/CEN0101E/distribuce/csv). Download monthly after the detailed CPI release; a flash print does not provide the full group panel.

```powershell
python -B -m portable capture-public --kind categories --output output/momentum_r35_inputs/NEW_CAPTURE
```

Prepare the captured panel, then optionally run the momentum analysis:

```powershell
python -B -m portable prepare-momentum --capture output/momentum_r35_inputs/NEW_CAPTURE --output output/momentum_r35_inputs/NEW_PREPARED --through 2026-08
python -B -m portable momentum --prepared output/momentum_r35_inputs/NEW_PREPARED --output output/momentum_r35/NEW_RUN
```

The existing source API is `tools.momentum_r35.inputs.capture/prepare/load_prepared`; the portable wrapper configures the receiving runtime. Replace the required `--through` with the last complete released month. The underlying legacy preparer's default is fixed at `2026-08`; do not rely on that default for later refreshes. Momentum writes a new analysis output directory, not an updated R35 dashboard. A new capture retains `CEN0101E.csv.gz`, `request.json`, local attributes and `MANIFEST.json`; deterministic gzip (`mtime=0`) decompresses to the exact original HTTP bytes. The request records URL, headers, raw byte count/hash and retrieval start/completion.

Read codes as strings. Exact selectors: `IndicatorType=6134`, `TYPUDAJE4A=IZ2015`, `EKAKTIOCDS=0`, `UZ02P=CZ`, monthly `CASMKMQRM12=YYYY-MM`. The 17-column CSV's `Hodnota` is an NSA **2015=100 index level**, despite `%` in its general unit field. Use `CZCOICOP2.CZCOP23`, falling back to `CZCOICOP2.CZCOP1` only for division aggregates. The ordered mapping in `tools.research_r18.category_inputs.CATEGORIES` is:

```text
011 food; 012 nonalcoholic_beverages; 021 alcoholic_beverages; 023 tobacco;
031 clothing; 032 footwear; 041 actual_rent; 042 imputed_rent;
043 housing_maintenance; 044 water_housing_services; 045 household_energy;
051 furniture; 052 household_textiles; 053 household_appliances;
054 tableware_utensils; 055 house_garden_tools; 056 household_goods_services;
071 vehicle_purchases; 072 vehicle_operation; 073 passenger_transport;
074 transport_postal_services; 081 ict_equipment; 083 ict_services;
091 recreation_durables; 092 other_recreation_goods; 093 garden_pets_goods;
094 recreation_services; 095 musical_instruments_media; 096 cultural_services;
097 books_stationery; 098 package_holidays; 111 catering; 112 accommodation;
06 health; 10 education; 12 insurance_financial_services; 13 personal_social_misc.
```

All 37 must be positive, unique and contiguous from January 2015 to `through`. A changed ordered schema, official label, household/geographic scope or missing category fails; HICP, regional data and broad division substitutes do not repair it. Vehicle operation includes fuel, repairs, parts and services; actual and imputed rents remain separate.

Prepared files are `monthly_levels.csv` (`period` plus those 37 columns), `series_metadata.csv`, `weights.csv` (`group,weight_permille`), `provenance.json`, and `MANIFEST.json`. The loader validates the frozen R18 source/parser/workbook evidence and all new raw bytes. It retains a full overlap-revision audit; current descriptive revisions can be accepted and disclosed without rewriting frozen history. Availability is capture completion for the entire current-vintage source, with preparation time separately recorded. R35 seasonal/momentum analysis consumes these frames through `tools.momentum_r35.inputs.load_prepared`; capture/preparation does not run X-13 or rebuild a dashboard.

## 8. Optional benchmark and analytical inputs

### CNB Monetary Policy Report: comparison only

Open the [official Summer 2026 report page](https://www.cnb.cz/en/monetary-policy/monetary-policy-reports/Monetary-Policy-Report-Summer-2026/) → **Chartbook and underlying data → Table of key macroeconomic indicators**. Download the linked [macro-indicator XLSX](https://www.cnb.cz/export/sites/cnb/cs/menova-politika/.galleries/zpravy_o_menove_politice/2026/leto_2026/download/zomp_2026_leto_makroindikatory.xlsx), the report PDF and the page into `output/manual_inputs/NEW_CNB_REPORT/` using section 2. For subsequent reports follow **Monetary Policy Reports** on that page and the actual report link; do not construct an assumed future URL.

Record report publication/approval date, its stated information cutoff, and actual capture completion separately. The verified Summer page states approval on 13 August 2026 and information generally through 24 July 2026. The archive's `report_date` convention must remain explicit; neither date makes today's capture a July vintage. Cadence is each new report (normally winter/spring/summer/autumn), and each revised table as a new capture.

Use the **existing pure parser** on saved bytes:

```python
from pathlib import Path
from tools.cnb_tracker.fetch_tables import parse
raw = Path("output/manual_inputs/NEW_CNB_REPORT/table/macroindicators.xlsx").read_bytes()
table = parse(raw)  # English version sheet; preserves full numerical precision
# Add sourced report_date, cutoff_date, season and vintage_year before saving.
```

It returns `section,row_label,indicator,frequency,period,value,is_forecast`. The full archival table prefixes `report_date,cutoff_date,season,vintage_year`. Keep `frequency=Q` and `period=YYYYQn` for quarterly comparisons. CPI is quarterly-average **y/y percent**; select `indicator=cpi` and the source row “Consumer Price Index (%, y-o-y, average)”. The parser uses the workbook's **bold-cell** forecast flag. Component rows include `core`, `administered`, `food_alc_tobacco`, `fuel`; the CNB food aggregate includes alcohol/tobacco and is not the model's food-only block.

Write the resulting CSV with exclusive creation and keep its raw hash/units in provenance. Compare only complete model quarters (three monthly y/y values averaged) against like-unit CNB quarterly forecasts. No monthly interpolation, and no quarter-end substitution. Existing dashboard/rounds packages remain tied to their frozen tables; fresh comparison publication needs a separate explicit build recipe. `tools.cnb_tracker.fetch_tables --output NEW` only re-fetches the reports already in its frozen registry; it does not discover a new report. **Do not execute `tools/cnb_mpr_cpi_quarterly.py` to update production**: its `main()` writes the frozen registry. CNB report forecasts must never enter independent nowcast/path features or fill an observed-series gap.

### Observed CNB analytical y/y and release briefing

These are optional descriptive observations, separate from CNB forecasts. The same verified ARAD POST request in section 3 accepts these existing codes:

| Code | Actual scope and unit |
|---|---|
| `SCPIMZM09YOYPECNA` | CNB core inflation, y/y percent |
| `SCPICLEM02YOYPECNA` | Other tradable prices **excluding food and fuel**, y/y percent |
| `SCPICLEM03YOYPECNA` | Nontradable prices **excluding regulated prices**, y/y percent |

Capture into `output/manual_inputs/NEW_ARAD_ANALYSIS/` and normalize as `series,observation_month,value,units,source,available_from`, using `units=yy_pct`. This is an **analysis staging schema**, not the accepted R33 manual-input file. On the verified August response the three values were 3.0, 0.6 and 4.5 respectively. Keep first-round tax effects and the stated exclusions; see [CNB tradables methodology](https://www.cnb.cz/docs/ARADY/MET_LIST/cpi_cle_en.pdf). These are not broad CZSO goods/services, and `services_l1` stays excluded from the approved R31C core model.

For headline/goods/services/rents narrative, capture the dated [CZSO detailed release](https://csu.gov.cz/rychle-informace/consumer-price-indices-inflation-august-2026) and use its labelled actual values. The [CNB August commentary](https://www.cnb.cz/en/public/media-service/the-cnb-comments-on-the-statistical-data-on-inflation-and-gdp/Fuel-prices-again-increase-inflation-in-August/) is an observed y/y cross-check, not a source for exact monthly core. Preserve current briefing evidence as a new package; do not edit `tools/inflation_dashboard_r33/official_release.json` or assume R35 replaces every inherited dated panel automatically.

Consensus surveys remain optional benchmarks under the separate Bloomberg survey workflow. FMIE/ESI/household expectations, SZIF/EC agrifood, Eurostat HICP/LCI, OTE, unemployment, activity, excise and experimental energy ledgers are retained research inputs, not missing requirements for HARD_BASE plus the accepted R34 path. No manual refresh of these archives is required to run that production model. In particular, R30 excise-step research has not become a production alcohol override; alcohol remains its released seasonal component.

## 9. Static dependencies: carry the archive, do not re-download it into place

| Retain/configure | Why it is needed; source/recovery and cadence |
|---|---|
| `data/bloomberg_inputs_20260922_foodppi/`, its manifest and any hash-pinned `data/market_snapshots/` ancestors | Baseline training frames, historical market/farm paths and availability; source is the retained Bloomberg/CZSO capture chain. Copy once with the full private repository. A current download cannot recreate identical historical source bytes. R32/R33 validate those hashes and R34 retains baseline overlaps. |
| `data/research_r14/food/coverage_extension/` including source manifest, CSV, schema and documentation | R24's `models.food_drift_r24.LONG_HISTORY` supplies pre-2015 food history. Its [original CZSO CSV](https://csu.gov.cz/docs/107508/cfcf22e1-06b0-92a6-cf41-fb554acc545a/010022-25data011326.csv?version=1.0) was downloaded and hash-matched in this review. Selector `ucel_kod=01`, `casz_kod=Z`; `rok`/`mesic` form months and `hodnota` is the positive base index. `long_food_rates` differences `100*log(index)` and splices the model food changes from February 2015. No periodic refresh of the historical splice. If auditing/recovering, save the official file in a NEW directory and compare to `source_manifest.json`; do not overwrite the accepted history. |
| Headline history in the baseline bundle and `output/independent_path_frozen_inputs.csv` | Retained pre-2007/older history and historical comparison ancestry. Current R34 preserves older accepted monthly history, then uses adjacent captured `CZCPI` level ratios where available for annual compounding. These are percentage changes, not levels. Retain once; no hand entry or rerun of the database pull is required. |
| `data/baskets/`, `data/admin_announcements_history.csv`, `data/release_calendar_cz_cpi.csv` | Static model weights/history/timing, with the new-source policies in sections 4–6. Embedded constants are code inputs. Keep historical raw/source evidence too. |
| `data/research_r18/categories/` including raw basket XLSX, metadata, parser manifest and all original files | Required for R35 validation of labels, 2026 weights, workbook cells and frozen overlap, even when using fresh category data. Copy once; no rebuild with a different raw hash. |
| Recorded R33 nowcast, R34 path, R35 momentum/dashboard and inherited evaluation/rounds exports | Required for viewing/rebuilding the exact delivered page and its comparisons. Preserve every referenced manifest/input/code byte. Absolute source-computer paths are provenance; use the portable read-only relocation layer, never edit them inside sealed JSON. |
| Survey-history CSVs and other tracked research snapshots/results | Preserve for the full-project migration and historical comparisons. They are not manual independent-model inputs to refresh on each run. Their unavailable historic capture vintages cannot be recreated by entering a current survey value. |
| X-13 executable and numerical environment | The portable runtime defaults to the shipped `portable/vendor/x13as/x13as.exe`; retain its verified bytes. Installation is not a CPI data source. If recovery or a deliberately reviewed replacement is needed: [Official Census download page](https://www.census.gov/data/software/x13as.X-13ARIMA-SEATS.html) → **Download → PC (Windows) Version Archives → ASCII-output executable ZIP**. Save the ZIP to a new software archive with URL/hash/capture metadata; extract into a new installation directory and set `CZ_X13_PATH` to the actual executable. Retain the binary hash/version for reproduction; do not silently exchange builds. R32 food adjustment and R35 seasonal analysis require real X-13; fallback results are not production forecasts. Use the pinned environment setup/diagnostics for NumPy/pandas/SciPy/scikit-learn/statsmodels/quantile-forest/duckdb/requests/tzdata and workbook libraries. |

The current R32/R33 bundle route supplies changing observations directly to `forecast_independent.calculate`; it does **not** need to revive `cz_struct.load_all` or copy the entire external `economic_db` merely to run production. Some archived research/legacy live entry points still read that database; preserve/configure it only if deliberately reproducing those workflows. Do not invoke `pull_all_local.py`, `run_nowcast.py` or the legacy live loader as an undocumented replacement for the portable production recipe.

## 10. Preparation, readiness and handoff checks

The implemented portable commands configure the local runtime and take explicit inputs. Set the target to the **actual current Prague month**; `2026-09` below is the delivery example. Omit `--manual-inputs` only when Bloomberg covers every required observed month.

```powershell
python -B -m portable prepare-nowcast --snapshot output/manual_inputs/NEW_BBG_NOWCAST --farm-raw output/manual_inputs/NEW_FARM/CEN0203B.csv --manual-inputs output/manual_inputs/NEW_CNB/manual_inputs.csv --target 2026-09 --output output/forecast_updates_r33/NEW_BUNDLE
python -B -m portable readiness --bundle output/forecast_updates_r33/NEW_BUNDLE --target 2026-09 --calendar output/manual_inputs/NEW_CALENDAR/live_calendar.csv
```

The baseline defaults to `data/bloomberg_inputs_20260922_foodppi`; override only with an intentionally chosen compatible bundle via `--base-bundle`. Preparation defaults to an actual clock after capture. Readiness defaults to prospective mode and a new current clock. If a new energy supplement is being used, append the same `--announcements` option to readiness and the subsequent nowcast/path recording commands. Portable uses `--calendar`; the underlying R32/R33 commands use **`--live-calendar`**.

Ready inspection is not a forecast. Record only after resolving due gaps:

```powershell
python -B -m portable nowcast --bundle output/forecast_updates_r33/NEW_BUNDLE --target 2026-09 --calendar output/manual_inputs/NEW_CALENDAR/live_calendar.csv
```

Use its **successful run directory** from the recorded result/pointer for the later path, never the newest failed attempt. A released target, due missing input, earlier/future clock, missing dependency or X-13/forest fallback is a block to resolve, not an instruction to change a source hash or claim replay as prospective. See the migration quickstart for the full recording/publication lifecycle. This command writes a new run archive; it does not rebuild the sealed R35 HTML.

After the nowcast inputs are complete, the portable wrapper calls the existing R34 external-farm API with the **separate path capture**:

```powershell
python -B -m portable prepare-path --current-bundle output/forecast_updates_r33/NEW_BUNDLE --capture output/manual_inputs/NEW_BBG_PATH --farm-raw output/manual_inputs/NEW_FARM/CEN0203B.csv --origin 2026-09 --output output/current_path_r34_inputs/NEW_PREPARED
```

The output contains `food_levels.csv` (`period,food,food_ppi,agri4`, 100 log-level points rebased to January 2015), aligned `food_available.csv` (UTC ISO timestamps), `pump_weekly.csv` (`date,gross_petrol95,gross_diesel`, CZK/l), `headline_history.csv` (`period,headline_mm`), `headline_levels.csv` (`period,headline_level`), provenance and manifest. Food CPI level is `100*log(CZCPF/Jan2015)`; food PPI is cumulative `100*log1p(CZPPA10M/100)`, rebased to January 2015. All required monthly overlaps must agree with the baseline. A complete twelve-month consumer history and the required adjacent headline levels are checked. Gross pumps come from the current bundle, not from the monthly path capture.

For execution, replace `SUCCESSFUL_NOWCAST_RUN` below with the returned immutable successful archive directory:

```powershell
python -B -m portable run-path --bundle output/forecast_updates_r33/NEW_BUNDLE --inputs output/current_path_r34_inputs/NEW_PREPARED --nowcast-run output/forecast_updates_r33/portable/runs/SUCCESSFUL_NOWCAST_RUN --output output/current_path_r34/NEW_RUN
```

If h0 used an announcement supplement, append **the same** `--announcements` file. R34 takes the prepared directory, same verified nowcast bundle and a successful **prospective R33 nowcast-run archive**; it keeps recorded h0 unchanged. Input preparation alone cannot supply that archive. The future path is available only before the origin's first release; use an explicitly labelled historical rehearsal for development, never a backdated new source capture.

Before handing off to calculation, confirm:

1. New raw captures have actual start/completion clocks, original bytes, URLs and matching hashes; none occupies a frozen destination.
2. The nowcast/path Bloomberg directories are distinct. Required components reach target minus one; manual file has only supported observed CNB rows; no CNB report forecasts are in either input lane.
3. Farm provenance points to the new explicit raw file; seven-product nowcast and four-product path transformations remain distinct. Calendar overlay includes target/previous metadata without replacing frozen history.
4. Announcement review is documented; any supplied new event is pinned and actually scoped into the selected runner. The path also uses it if a future January is being updated. Weight vintage/publication and unverified parameters remain explicit.
5. Preparation timestamps precede recording, target is before first release, readiness reports no due gaps, and runtime diagnostics pass. New source/schema revisions require a reviewed new adapter/package, not edits to hashes or old outputs.

**Boundaries requiring engineering/source work if encountered:** unsupported monthly supplements beyond core/regulated; changed CZSO schemas/classifications or conflicting path overlaps; a new basket regime; missing national tariff/consumption/treatment evidence; the frozen historical-calendar conflict. A current download cannot recover an unarchived historical vintage. These conditions should produce an explicit blocked result or dated limitation; none prevents copying/viewing the existing complete R35 snapshot.
