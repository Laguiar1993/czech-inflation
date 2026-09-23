"""Freeze and load broad Czech national-CPI measurements for R18 research.

No estimation, source selection from realised outcomes, seasonal adjustment,
tax adjustment, reclassification reconstruction, or CPI/core aggregation occurs.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
PACKAGE = ROOT / "data/research_r18/categories"
RAW_SHA256 = "e81dc0dece758d0e89adc88e6f8c31f3ba97f8a68dfa67795a794dbe3b858880"
SOURCE_URL = "https://data.csu.gov.cz/opendata/sady/CEN0101E/distribuce/csv"

# Chosen solely from official group definitions and current basket child labels.
# These are sector measurements, not CNB core membership classifications.
# code: (column, sector, primary, scope note)
CATEGORIES = {
    "011": ("food", "food", False, "Food aggregate; outside the primary core-associated panel."),
    "012": ("nonalcoholic_beverages", "food", False, "Beverages aggregate; outside primary panel."),
    "021": ("alcoholic_beverages", "alcohol_tobacco", False, "Includes excise-tax effects."),
    "023": ("tobacco", "alcohol_tobacco", False, "Includes excise-tax effects; older baskets use 022."),
    "031": ("clothing", "mixed_goods_services", False, "Includes cleaning, repair, tailoring and rental; goods-dominant."),
    "032": ("footwear", "mixed_goods_services", False, "Includes cleaning, repair and rental; goods-dominant."),
    "041": ("actual_rent", "housing", True, "Actual housing rent; national CPI raw group, not a CNB-core flag."),
    "042": ("imputed_rent", "housing", True, "Owner housing costs; national CPI includes this; HICP differs."),
    "043": ("housing_maintenance", "mixed_goods_services", False, "Minor repair, maintenance and security: mixed materials/services."),
    "044": ("water_housing_services", "regulated_exposure", False, "Water and other dwelling services; regulation exposure."),
    "045": ("household_energy", "energy", False, "Electricity, gas and other fuels."),
    "051": ("furniture", "mixed_goods_services", False, "Includes repair, installation and rental; goods-dominant."),
    "052": ("household_textiles", "goods", True, "Household textiles."),
    "053": ("household_appliances", "mixed_goods_services", False, "Includes repair, installation and rental; goods-dominant."),
    "054": ("tableware_utensils", "goods", True, "Glassware, tableware and household utensils."),
    "055": ("house_garden_tools", "goods", True, "Tools and equipment for house and garden."),
    "056": ("household_goods_services", "mixed_goods_services", False, "Household consumables plus domestic/household services."),
    "071": ("vehicle_purchases", "goods", True, "Purchase of cars, motorcycles and bicycles."),
    "072": ("vehicle_operation", "mixed_energy_goods_services", False, "Fuel, parts, repair and other operation services; no fuel subtraction."),
    "073": ("passenger_transport", "regulated_exposure", False, "Service aggregate with regulated public-transport exposure."),
    "074": ("transport_postal_services", "regulated_exposure", False, "Postal and other transport services; regulated-price exposure possible."),
    "081": ("ict_equipment", "goods", True, "Information/communication equipment; reclassified from old 08/09 components."),
    "083": ("ict_services", "services", True, "Telecom/internet, equipment repairs/rental and other ICT services including broadcasting."),
    "091": ("recreation_durables", "goods", True, "Current basket: photographic/cinematographic/optical equipment; not old broad 091."),
    "092": ("other_recreation_goods", "goods", True, "Games/toys/hobby and sport/camping/outdoor equipment."),
    "093": ("garden_pets_goods", "goods", True, "Garden goods, plants, pets and pet products; veterinary services are 094."),
    "094": ("recreation_services", "services", True, "Includes equipment rental/repair, veterinary, recreation/sport and gambling services."),
    "095": ("musical_instruments_media", "goods", True, "Musical instruments and recorded audiovisual media."),
    "096": ("cultural_services", "services", True, "Cinema/theatre/concerts, cultural institutions and photography services; old 096 was holidays."),
    "097": ("books_stationery", "goods", True, "Books, newspapers/periodicals, other printed matter and stationery."),
    "098": ("package_holidays", "services", True, "Organised holidays/tours; historical basket 096 through 2024."),
    "111": ("catering", "services", True, "Includes restaurants, canteens and school canteens."),
    "112": ("accommodation", "services", True, "Includes hotels, recreation accommodation and student dormitories."),
    "06": ("health", "mixed_goods_services", False, "Division aggregate; pharmaceuticals/equipment and health services."),
    "10": ("education", "regulated_exposure", False, "Division aggregate; public/regulated exposure possible."),
    "12": ("insurance_financial_services", "mixed_scope_services", False, "Division aggregate; financial/insurance service measurement differs from ordinary unit prices."),
    "13": ("personal_social_misc", "mixed_goods_services", False, "Division aggregate of personal/social care and miscellaneous goods/services."),
}
PRIMARY_COLUMNS = [value[0] for value in CATEGORIES.values() if value[2]]


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def extract_levels(raw: pd.DataFrame, required_codes=None) -> pd.DataFrame:
    """Select national, all-household, monthly 2015-base levels; fail on collisions."""
    mapping = required_codes or {code: row[0] for code, row in CATEGORIES.items()}
    required = {"IndicatorType", "TYPUDAJE4A", "EKAKTIOCDS", "UZ02P", "CASMKMQRM12",
                "CZCOICOP2.CZCOP1", "CZCOICOP2.CZCOP23", "Hodnota"}
    if not required.issubset(raw.columns):
        raise ValueError("Unexpected frozen raw schema; never silently apply a current schema")
    selected = raw.loc[(raw.IndicatorType == "6134") & (raw.TYPUDAJE4A == "IZ2015")
                       & (raw.EKAKTIOCDS == "0") & (raw.UZ02P == "CZ")
                       & raw.CASMKMQRM12.str.fullmatch(r"\d{4}-\d{2}", na=False)].copy()
    selected["code"] = selected["CZCOICOP2.CZCOP23"].fillna(selected["CZCOICOP2.CZCOP1"])
    selected = selected.loc[selected.code.isin(mapping)]
    if selected.duplicated(["CASMKMQRM12", "code"]).any():
        raise ValueError("duplicate category-month source observations")
    selected["value"] = pd.to_numeric(selected.Hodnota, errors="raise")
    if not np.isfinite(selected.value).all() or (selected.value <= 0).any():
        raise ValueError("Nonpositive or nonfinite category level")
    wide = selected.pivot(index="CASMKMQRM12", columns="code", values="value")
    missing = set(mapping) - set(wide.columns)
    if missing:
        raise ValueError(f"Missing required category codes: {sorted(missing)}")
    wide = wide.reindex(columns=list(mapping)).rename(columns=mapping).sort_index()
    wide.index.name = "target_month"
    wide.columns.name = None
    expected = pd.period_range(wide.index[0], wide.index[-1], freq="M").astype(str)
    if wide.isna().any().any() or wide.index.tolist() != expected.tolist():
        raise ValueError("Missing monthly source values; interpolation is forbidden")
    return wide


def levels_asof(levels: pd.DataFrame, availability: pd.DataFrame, origin) -> pd.DataFrame:
    """Use only releases available at origin, with reference month before origin month.

    Date-only origins mean midnight Europe/Prague, matching the existing approved
    experiment convention. This gates a frozen current-vintage history and does
    not create archived observation vintages.
    """
    if availability.target_month.duplicated().any() or levels.index.duplicated().any():
        raise ValueError("duplicate availability or monthly observations")
    gate = availability.set_index("target_month").reindex(levels.index)
    dates = pd.to_datetime(gate.available_from, errors="coerce")
    if dates.isna().any():
        raise ValueError("Missing or invalid availability dates")
    months = pd.PeriodIndex(levels.index, freq="M")
    if (dates.to_numpy() <= months.to_timestamp(how="end").to_numpy()).any():
        raise ValueError("availability must be after its reference month")
    clock = pd.Timestamp(origin)
    clock = clock.tz_localize("Europe/Prague") if clock.tzinfo is None else clock.tz_convert("Europe/Prague")
    local_dates = dates.dt.tz_localize("Europe/Prague")
    origin_month = pd.Period(clock.strftime("%Y-%m"), freq="M")
    mask = (local_dates <= clock).to_numpy() & (months < origin_month)
    return levels.loc[mask].copy()


def load_categories(package_dir: Path | str = PACKAGE, primary: bool = True, verify: bool = True):
    """Return (wide levels indexed by YYYY-MM, per-series metadata, availability).

    Call levels_asof before constructing any feature, monthly transformation or
    fitting sample. Raw levels are provided so transformations remain explicit.
    """
    package = Path(package_dir)
    manifest = json.loads((package / "manifest.json").read_text(encoding="utf-8"))
    if verify:
        for name, record in manifest["files"].items():
            path = (package / name).resolve()
            if not path.is_relative_to(package.resolve()) or _sha(path) != record["sha256"]:
                raise ValueError(f"Category snapshot integrity failure: {name}")
    levels = pd.read_csv(package / "monthly_levels.csv", index_col="target_month")
    meta = pd.read_csv(package / "series_metadata.csv", dtype={"coicop2018_code": str})
    availability = pd.read_csv(package / "availability.csv", dtype=str)
    if primary:
        levels = levels[meta.loc[meta.primary_measurement, "column"].tolist()]
    return levels, meta, availability


def _make_availability(calendar: pd.DataFrame, levels: pd.DataFrame) -> pd.DataFrame:
    if calendar.target_month.duplicated().any():
        raise ValueError("duplicate source calendar rows")
    availability = calendar.set_index("target_month").reindex(levels.index).reset_index()
    availability = availability.rename(columns={"detail_release_dt": "available_from"})
    availability["availability_rule"] = "detailed_CPI_date_at_midnight_Europe_Prague"
    availability["vintage_status"] = "historical_release_gate_assumption_on_frozen_current_history"
    # Reuse validation; the far-future clock is validation only, never model input.
    levels_asof(levels, availability, "2100-01-01")
    return availability


def _extract_baskets(source_dir: Path, raw_dir: Path, calendar: pd.DataFrame) -> pd.DataFrame:
    import openpyxl  # Read-only official workbook extraction; no workbook authoring.
    rows = []
    # Only the five previously audited concordances are carried into old baskets.
    audited = {"041": "041", "042": "042", "111": "111", "112": "112", "096": "098"}
    for year in range(2014, 2027, 2):
        filename = f"spot_kos{year}.xlsx"
        shutil.copyfile(source_dir / filename, raw_dir / filename)
        ws = openpyxl.load_workbook(raw_dir / filename, read_only=True, data_only=True).worksheets[0]
        jan = calendar.loc[calendar.target_month == f"{year}-01", "detail_release_dt"]
        availability = jan.iloc[0] if len(jan) and pd.notna(jan.iloc[0]) else f"{year}-02-15"
        for number, row in enumerate(ws.values, start=1):
            code = str(row[0] or "").strip().removeprefix("E")
            if not re.fullmatch(r"0|\d{2}(?:\.\d{1,2})?", code):
                continue
            if not isinstance(row[4], (int, float)):
                raise ValueError(f"Nonnumeric official weight at {filename}:E{number}")
            canonical = code.replace(".", "")
            mapped = canonical if year == 2026 and canonical in CATEGORIES else audited.get(canonical) if year < 2026 else None
            mapping_status = ("current_COICOP2018_code" if year == 2026 else "previous_five_group_audit") if mapped else "native_basket_only_no_verified_concordance"
            rows.append({"effective_year": year, "basis_year": year - 2, "basket_code": code,
                         "basket_label_cs": row[1], "weight_permille": row[4],
                         "mapped_series": CATEGORIES[mapped][0] if mapped else "",
                         "mapping_status": mapping_status,
                         "eligible_for_exact_core_aggregation": False,
                         "available_from_assumption": availability,
                         "availability_kind": "January detailed-CPI date proxy; February 15 fallback",
                         "source_file": f"raw/{filename}", "source_sheet": ws.title,
                         "source_cell": f"E{number}"})
    return pd.DataFrame(rows)


def freeze(raw_path: Path, basket_dir: Path, calendar_path: Path, output: Path, evidence_dir: Path | None = None):
    """Create a new package, refusing overwrite and a changed source snapshot."""
    if output.exists():
        raise FileExistsError(f"Refusing to overwrite {output}")
    if _sha(raw_path) != RAW_SHA256:
        raise ValueError("Raw CEN0101E is not the previously audited frozen snapshot")
    raw = pd.read_csv(raw_path, dtype=str)
    levels = extract_levels(raw)
    if levels.shape != (139, 37) or levels.index[[0, -1]].tolist() != ["2015-01", "2026-07"]:
        raise ValueError("Unexpected frozen coverage")
    calendar = pd.read_csv(calendar_path, dtype=str)
    availability = _make_availability(calendar, levels)
    raw_dir = output / "raw"
    raw_dir.mkdir(parents=True)
    # Gzip preserves every byte of the original, with deterministic gzip metadata.
    (raw_dir / "CEN0101E.csv.gz").write_bytes(gzip.compress(raw_path.read_bytes(), mtime=0))
    shutil.copyfile(calendar_path, raw_dir / "release_calendar_cz_cpi.csv")
    shutil.copyfile(ROOT / "data/core_split/audit/manifest.json", raw_dir / "previous_source_audit.json")
    shutil.copyfile(ROOT / "data/core_split/audit/basket_manifest.json", raw_dir / "previous_basket_audit.json")
    shutil.copyfile(ROOT / "data/core_split/canonical_metadata.json", raw_dir / "previous_five_group_metadata.json")
    if evidence_dir and evidence_dir.exists():
        shutil.copytree(evidence_dir, raw_dir / "online_verification")
    baskets = _extract_baskets(basket_dir, raw_dir, calendar)
    baskets.to_csv(output / "basket_weights_long.csv", index=False)
    raw_levels = raw.loc[(raw.TYPUDAJE4A == "IZ2015") & (raw.EKAKTIOCDS == "0") & (raw.CASMKMQRM12 == "2015-01")]
    meta_rows = []
    for code, (name, sector, primary, note) in CATEGORIES.items():
        matching = raw_levels.loc[raw_levels["CZCOICOP2.CZCOP23"] == code] if len(code) == 3 else raw_levels.loc[(raw_levels["CZCOICOP2.CZCOP1"] == code) & raw_levels["CZCOICOP2.CZCOP23"].isna()]
        label_col = "Klasifikace COICOP 2018-Skupina a třída" if len(code) == 3 else "Klasifikace COICOP 2018-Oddíl"
        label = matching[label_col].iloc[0]
        meta_rows.append({"column": name, "coicop2018_code": code, "label_cs": label,
                         "level": "group" if len(code) == 3 else "division", "sector": sector,
                         "primary_measurement": primary, "scope_note": note,
                         "first_month": "2015-01", "last_month": "2026-07", "observations": 139,
                         "index_base": "2015=100", "seasonal_adjustment": "NSA", "geography": "CZ",
                         "households": "all households (0)", "tax_adjustment": "none; first-round taxes retained",
                         "cnb_core_membership": "not supplied; measurement proxy only",
                         "classification_vintage": "current COICOP2018 history in 2026-09-07 snapshot",
                         "available_from_rule": "availability.csv available_from; detail release <= origin Prague clock; reference month < origin month",
                         "available_from_kind": "historical calendar assumption, not observation vintage",
                         "source_dataset": "CZSO CEN0101E", "source_url": SOURCE_URL,
                         "source_raw_sha256": RAW_SHA256})
    metadata = pd.DataFrame(meta_rows)
    metadata.to_csv(output / "series_metadata.csv", index=False)
    levels.to_csv(output / "monthly_levels.csv")
    levels[PRIMARY_COLUMNS].to_csv(output / "primary_monthly_levels.csv")
    availability.to_csv(output / "availability.csv", index=False)
    old = pd.read_csv(ROOT / "data/core_split/monthly_levels.csv", index_col="target_month")
    differences = (levels[old.columns] - old).abs()
    if differences.isna().any().any() or differences.to_numpy().max() != 0:
        raise ValueError("New extract does not match the five previously audited groups")
    current = baskets.loc[(baskets.effective_year == 2026) & baskets.mapped_series.isin(PRIMARY_COLUMNS)]
    facts = {
        "schema_version": 1, "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "purpose": "R18 broad national CPI statistical measurements, not an exact CNB-core decomposition",
        "source_snapshot": {"url": SOURCE_URL, "raw_sha256": RAW_SHA256,
                            "bytes_uncompressed": raw_path.stat().st_size,
                            "prior_audit_time_utc": "2026-09-09T09:22:59.597273+00:00",
                            "original_cache_mtime": "2026-09-07; not a certified source release timestamp",
                            "vintage_status": "frozen current-vintage history; no retained first-release observations"},
        "coverage": {"first_month": "2015-01", "last_month": "2026-07", "months": 139,
                     "all_columns": len(CATEGORIES), "primary_columns": PRIMARY_COLUMNS,
                     "primary_counts": metadata.loc[metadata.primary_measurement, "sector"].value_counts().to_dict(),
                     "primary_2026_base_weight_permille": float(current.weight_permille.sum()),
                     "weight_meaning": "context only: 2024 expenditure base weights effective 2026, not historical/current shares or model loadings"},
        "selection": "Predetermined category definitions and composition; no realised outcomes, forecasting errors, fit, likelihood or correlation used",
        "availability": {"file": "availability.csv", "time_zone": "Europe/Prague", "time_of_day": "00:00:00",
                         "rule": "detailed CPI date <= origin; reference month strictly before origin month",
                         "calendar_provenance": "existing repo release calendar, largely bbg_eco_release_dt plus CZSO page overrides; no newly invented dates",
                         "vintage_caveat": "Calendar gates prevent use before assumed release but do not undo historical revisions or classification recoding"},
        "transformations": "Exact selection/pivot of positive IZ2015 levels. No rebasing, chain linking, filling, seasonal adjustment or tax correction. For monthly percent changes use 100*(level/level.shift(1)-1), after origin gating; rounded level changes can differ from published IM.",
        "validation": {"duplicate_keys": 0, "missing_months": 0, "missing_values": 0,
                       "old_five_comparison_cells": int(differences.size), "old_five_max_abs_difference": float(differences.to_numpy().max())},
        "weights": {"file": "basket_weights_long.csv", "unit": "per mille of headline national CPI basket",
                    "effective_years": list(range(2014, 2027, 2)),
                    "availability": "January detailed CPI release proxy; not verified workbook publication date",
                    "concordance": "2026 matching current codes; pre-2026 mapped only five previously audited groups; other native codes deliberately not equated to recoded history",
                    "limitations": "Odd-year baskets not included. Weights are base expenditure weights, not origin-current shares. No exact core aggregation; no unverified crosswalk, price updating or future-year weights used."},
        "alternatives": [
            {"source": "existing core_split package", "result": "Only five service/housing groups; superseded for broad measurements by full raw extraction; old package untouched"},
            {"source": "Firecrawl CLI", "result": "Unavailable on PATH; public primary web tool and urllib used"},
            {"source": "CZSO DataStat information page", "result": "JavaScript-only text response; official time-series page directly confirms dataset download and schema links"},
            {"source": "current CEN0101E schema", "result": "Live schema has split time/geography columns differing from frozen CSV; retained as current evidence only, not parsed against old data"},
            {"source": "Eurostat HICP", "result": "Considered but not acquired: national CPI covers requested measurements and owner housing. HICP ECOICOP2/current recoding is not national CPI or CNB tax-adjusted core"},
            {"source": "CNB ARAD broad goods/services yoy", "result": "Already frozen in core_split but annual inflation is not a monthly category level; raw tax treatment differs from CNB adjusted core"}
        ],
    }
    (output / "metadata.json").write_text(json.dumps(facts, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    (output / "README.md").write_text(_readme(facts), encoding="utf-8")
    files = {str(path.relative_to(output)).replace("\\", "/"): {"sha256": _sha(path), "bytes": path.stat().st_size}
             for path in sorted(output.rglob("*")) if path.is_file()}
    manifest = {"schema_version": 1, "created_at_utc": facts["created_at_utc"], "hash_algorithm": "SHA256",
                "builder_sha256": _sha(Path(__file__)), "source_raw_uncompressed_sha256": RAW_SHA256,
                "files": files}
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return facts


def _readme(facts):
    return f"""# R18 national CPI category measurements

Frozen CZSO CEN0101E national-CPI data: **139 months, January 2015–July 2026**,
37 nonoverlapping reported groups/divisions; **18 primary measurements** consisting
of ten goods, two housing and six service groups. These are statistical inputs for
a common/sector trend model. They are not an exhaustive partition of CNB adjusted
core inflation. They retain taxes and have no CNB regulation/membership filter.

## Files and recommended use

`primary_monthly_levels.csv` contains the 18 definition-selected inputs. Start with
these and keep the 19 broader/excluded groups in `monthly_levels.csv` for diagnostics.
`series_metadata.csv` defines every column, the source code, sector, inclusion decision
and scope. Housing should have its own factor because imputed rent represents owner
housing costs. Recreation services include gambling; caterers include school canteens;
accommodation includes student dormitories. These composition issues remain relevant
even though the categories are services. No category was selected using realised
inflation, model performance, likelihood, correlation or later forecast errors.

## Source and definitions

The [official CZSO time-series page](https://csu.gov.cz/produkty/isc_ts) links the
[CEN0101E CSV]({SOURCE_URL}). The complete previously audited raw file is retained,
byte for byte after gzip decompression, in `raw/CEN0101E.csv.gz`. Its SHA256 is
`{RAW_SHA256}`. The original cache is dated September 7, 2026 and was audited on
September 9; its retrieval timestamp is not a historical release vintage. We reused
this frozen file to keep the existing July endpoint, rather than replacing data.
All 695 cells of the old five-group package match exactly.

Selection: indicator 6134, household 0, geography CZ, index type IZ2015, calendar
monthly codes YYYY-MM. Values are NSA index levels with 2015=100; despite the raw
unit symbol %, these rows are index levels, not monthly percentage changes.
No interpolation, rebase, seasonal adjustment or tax adjustment was applied. Convert
after gating with `100*(level_t/level_(t-1)-1)` or an explicitly documented log change.
The level series are rounded; derived monthly changes need not equal published IM.

The frozen source already carries **current COICOP2018 categories back to 2015**.
This is current recoded history, not proof that current group composition was
historically observable. Old 096 was holidays; current 096 is cultural services and
current 098 is holidays. ICT and recreation were rearranged across groups/divisions.
Do not connect old and new numeric codes by equality. No historical item-level
concordance or first-release vintages have been reconstructed. The live schema now
has different time/geography columns, so refresh requires a reviewed schema adapter.

## Availability and leakage limits

`availability.csv` repeats the existing calendar's **detailed** CPI date, never its
earlier flash date. A level is eligible only when `available_from <= origin` in
Europe/Prague, and its reference month is strictly before the origin month. The
existing experiment's approved midnight date convention is preserved. Source
calendar rows are retained, including their Bloomberg/CZSO provenance; these are
historical availability assumptions, not archived releases. Missing gates fail
closed. `load_categories()` verifies all package hashes; then call `levels_asof()`
before transforming or fitting. Latest-vintage history can still contain revisions
and later classification recoding: a calendar gate is not a true real-time vintage.

## Weights and mapping limits

Official [basket archive](https://csu.gov.cz/spotrebni_kos_archiv) workbooks for even
years 2014–2026 are saved unchanged. `basket_weights_long.csv` extracts original
division/group/class labels and weights with sheet/cell references. Headers identify
constant weights from effective year minus two. Pre-2026 canonical mappings are
provided only for the five previously audited groups. Other historical codes remain
native and unmapped; 2026 codes match the current classification. Odd-year files
were not acquired, and historical workbook publication dates are unverified.
Their availability field is the existing January detailed-release proxy (February
15 fallback); only regimes effective no later than an origin year and published
by that origin could be used for a later diagnostic. The primary 2026 base weights
sum to {facts['coverage']['primary_2026_base_weight_permille']:.6f} per mille of headline CPI;
this is context only, not core coverage or historical/current expenditure shares.
No weights enter the primary measurement recommendation or loader.

Base weights cannot directly reconstruct monthly official contributions: this
requires price updating, validated regime/concordance selection and tax/regulation
reconciliation. The CNB adjusted-core target must remain a separate measurement
with explicit mapping/residual error. HICP is not substituted for national CPI;
in particular national CPI owner housing differs. No exact weighted core total
is offered by this package.

## Reproducibility and alternatives

`manifest.json` hashes every frozen file. `metadata.json` records coverage, gates,
transformation, validation and alternatives. `raw/online_verification/` contains
public source-page/schema/manual snapshots and a URL/retrieval/hash log when the
direct download succeeded. The web tool confirmed official CSV/XLSX links but does
not render those binary formats; the DataStat information page needed JavaScript;
the Firecrawl CLI was unavailable. Eurostat HICP was unnecessary after locating
the fuller national dataset; ARAD broad year-on-year rates cannot replace monthly
category levels. No existing package, manifest, fit or model path was modified.

Build a *new* destination using `tools/research_r18/category_inputs.py --raw PATH
--output NEW_PATH`. It requires the exact previously audited raw checksum and
refuses to overwrite a package. All raw/package paths are portable after freezing.
"""


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw", type=Path, required=True)
    parser.add_argument("--baskets", type=Path, default=ROOT / "data/baskets")
    parser.add_argument("--calendar", type=Path, default=ROOT / "data/release_calendar_cz_cpi.csv")
    parser.add_argument("--output", type=Path, default=PACKAGE)
    parser.add_argument("--evidence", type=Path, default=ROOT / "work/research_r18_categories/source_verification")
    args = parser.parse_args()
    result = freeze(args.raw, args.baskets, args.calendar, args.output, args.evidence)
    print(json.dumps({"coverage": result["coverage"], "validation": result["validation"]}, indent=2))
