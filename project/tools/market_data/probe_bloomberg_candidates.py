"""Probe Bloomberg candidate tickers for the Czech CPI model inputs and save an immutable snapshot.

Run with the Bloomberg-enabled Python (anaconda base, xbbg) while the Terminal is logged in:

  PATH="/c/Users/luis_/anaconda3/Library/bin:$PATH" /c/Users/luis_/anaconda3/python.exe \
      tools/market_data/probe_bloomberg_candidates.py --output data/market_snapshots/20260912_bloomberg_probe

For every candidate it stores the reference fields (name, source, seasonal-adjustment label, frequency, notes) and the
PX_LAST history, so an invalid or mislabelled ticker is visible before any comparison. It also runs Bloomberg's
instrument search for the inputs that still have no ticker. Nothing here changes a model input.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import importlib.metadata
import json
from pathlib import Path
import sys
from zoneinfo import ZoneInfo

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
HISTORY_START = "1990-01-01"  # a --config file may set 'history_start' for longer histories
# purpose -> tickers. Pattern probes (e.g. the CZEII* import groups) are expected to fail when the name does not exist.
CANDIDATES = {
    "cpi_czso_index": ["CZCPI Index", "CZCPF Index", "CZCPA Index", "CZCPC Index", "CZCPH Index", "CZCPN Index", "CZCPHE Index",
                       "CZCPTR Index", "CZCPP Index", "CZCPR Index", "CZCPE Index", "CZCPSH Index", "CZCP12 Index", "CZCP13 Index"],
    "hicp_food_index": ["CPALCZ Index", "CPF1CZ Index", "CPFOCZ Index", "CP11CZ Index", "CP12CZ Index", "CP13CZ Index", "CP14CZ Index",
                        "CP15CZ Index", "CP16CZ Index", "CP17CZ Index", "CP18CZ Index", "CP19CZ Index", "CPNACZ Index"],
    "ppi_czso_mom": ["CZPPMOM Index", "CZPPAMOM Index", "CZPPCAM Index", "CZPPA10M Index", "CZPPA01M Index", "CZPPA03M Index",
                     "CZPPA04M Index", "CZPPA05M Index", "CZPPA06M Index", "CZPPA07M Index", "CZPPBM Index", "CZPPCM Index"],
    "ppi_eurostat": ["EUPPCZY Index", "PPENCZY Index", "EPT00BCZ Index", "EPT00CCZ Index", "EPT010CZ Index", "EPTC10CZ Index", "EPT0BCCZ Index"],
    "trade_prices": ["CZEII Index", "CZEIE Index", "CZEIIF Index", "CZEIIB Index", "CZEIII Index", "CZEIIL Index", "CZEIIO Index",
                     "CZEIIC Index", "CZEIIG Index", "CZEIIT Index", "CZEIIM Index"],
    "surveys": ["EUA7CZ Index", "EUA8CZ Index", "EUESCZ Index", "CZCCCOM Index", "EUR6CZ Index", "EUS6CZ Index", "EUA3CZ Index"],
    "labour": ["CZUEUR Index", "CZJLUNR Index", "UMRTCZ Index", "CZUEL Index"],
    "loans": ["CZBLHPTV Index", "CZBLHHTV Index", "LDHHLHCZ Index", "LDHHCCCZ Index", "LDHHOLCZ Index"],
    "trade_balance": ["CZTBAL Index", "CZTBNAL Index"],
    "rates": ["GTCZK10Y Govt"],
}
DAILY = {"GTCZK10Y Govt"}
REFERENCE_FIELDS = ["NAME", "SECURITY_DES", "INDX_SOURCE", "SEASONALITY_AND_TRANSFORMATION", "INDX_FREQ", "LAST_UPDATE_DT", "COUNTRY", "DES_NOTES"]
SEARCHES = ["Czech core inflation", "Czech Republic core CPI", "Czech administered prices", "Czech regulated prices",
            "Czech CPI services", "Czech CPI goods", "Czech CPI fuels", "Czech Republic CPI fuel", "CNB fixing EUR CZK",
            "Czech National Bank exchange rate fixing", "Czech Republic gasoline price", "Czech Republic diesel price",
            "Czech repo rate", "Czech National Bank 2 week repo", "Czech Republic real effective exchange rate",
            "Czech Republic trade balance", "Czech agricultural producer prices", "Czech Republic household loans",
            "Czech inflation expectations", "Czech Republic import prices"]


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def write_json(path: Path, value) -> None:
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, default=str), encoding="utf-8")


def instrument_search(queries: list[str], max_results: int = 15) -> dict:
    """Bloomberg security lookup (//blp/instruments instrumentListRequest), the API form of the SECF search."""
    import blpapi
    options = blpapi.SessionOptions()
    options.setServerHost("localhost")
    options.setServerPort(8194)
    session = blpapi.Session(options)
    if not session.start() or not session.openService("//blp/instruments"):
        raise RuntimeError("could not open //blp/instruments")
    service = session.getService("//blp/instruments")
    results = {}
    for query in queries:
        request = service.createRequest("instrumentListRequest")
        request.set("query", query)
        request.set("yellowKeyFilter", "YK_FILTER_INDX")
        request.set("maxResults", max_results)
        session.sendRequest(request)
        found = []
        while True:
            event = session.nextEvent(15000)
            for message in event:
                if message.hasElement("results"):
                    for item in message.getElement("results").values():
                        found.append({"security": item.getElementAsString("security"),
                                      "description": item.getElementAsString("description")})
            if event.eventType() in (blpapi.Event.RESPONSE, blpapi.Event.TIMEOUT):
                break
        results[query] = found
        print(f"search '{query}': {len(found)} results", flush=True)
    session.stop()
    return results


def probe(folder: Path, end: str) -> list:
    from xbbg import blp
    folder.mkdir(parents=True, exist_ok=False)
    (folder / "raw").mkdir()
    request = {"retrieved_at": now(), "end_date": end, "candidates": CANDIDATES, "reference_fields": REFERENCE_FIELDS,
               "history": "PX_LAST; MONTHLY periodicity for Index tickers, DAILY for Govt", "history_start": HISTORY_START,
               "vintage_status": "Current-vintage download; not an original-vintage archive.",
               "python_executable": sys.executable,
               "versions": {p: importlib.metadata.version(p) for p in ["xbbg", "blpapi", "pandas"]}}
    write_json(folder / "request.json", request)
    coverage, metadata, errors, long = [], {}, [], []
    for group, tickers in CANDIDATES.items():
        for ticker in tickers:
            item = {"group": group, "ticker": ticker, "retrieved_at": now()}
            try:
                ref = blp.bdp(ticker, REFERENCE_FIELDS, timeout=30000)
                if ref is None or ref.empty:
                    raise ValueError("no reference data (ticker probably invalid)")
                row = {k: (None if pd.isna(v) else v) for k, v in ref.iloc[0].to_dict().items()}
                metadata[ticker] = row
                item.update(name=row.get("name"), source=row.get("indx_source"), adjustment=row.get("seasonality_and_transformation"),
                            frequency=row.get("indx_freq"), last_update=row.get("last_update_dt"))
            except Exception as exc:
                item.update(status="bdp_error", error=f"{type(exc).__name__}: {exc}")
                errors.append({"ticker": ticker, "stage": "bdp", "error": item["error"]})
                coverage.append(item)
                print(f"{ticker}: BDP ERROR {exc}", flush=True)
                continue
            try:
                periodicity = "DAILY" if ticker in DAILY else "MONTHLY"
                raw = blp.bdh(ticker, "PX_LAST", start_date=HISTORY_START, end_date=end, timeout=30000, periodicitySelection=periodicity)
                if raw is None or raw.empty:
                    raise ValueError("no history")
                values = raw[(ticker, "PX_LAST")].dropna()
                values.index = pd.to_datetime(values.index)
                safe = ticker.replace(" ", "_")
                values.to_frame("PX_LAST").to_csv(folder / "raw" / f"{safe}.csv", index_label="observation_date")
                long.append(pd.DataFrame({"ticker": ticker, "observation_date": values.index.date, "value": values.to_numpy()}))
                item.update(status="ok", periodicity=periodicity, observations=int(len(values)),
                            first_date=values.index.min().date().isoformat(), last_date=values.index.max().date().isoformat(),
                            last_value=float(values.iloc[-1]))
                print(f"{ticker}: {len(values)} obs {item['first_date']}..{item['last_date']} | {item.get('name')}", flush=True)
            except Exception as exc:
                item.update(status="bdh_error", error=f"{type(exc).__name__}: {exc}")
                errors.append({"ticker": ticker, "stage": "bdh", "error": item["error"]})
                print(f"{ticker}: BDH ERROR {exc}", flush=True)
            coverage.append(item)
            pd.DataFrame(coverage).to_csv(folder / "coverage.csv", index=False)
            write_json(folder / "metadata.json", metadata)
            write_json(folder / "errors.json", errors)
    if long:
        pd.concat(long, ignore_index=True).to_csv(folder / "history_long.csv", index=False)
    try:
        write_json(folder / "instrument_search.json", instrument_search(SEARCHES))
    except Exception as exc:
        errors.append({"stage": "instrument_search", "error": f"{type(exc).__name__}: {exc}"})
        print(f"instrument search failed: {exc}", flush=True)
    write_json(folder / "errors.json", errors)
    request["completed_at"] = now()
    write_json(folder / "request.json", request)
    hashes = {str(p.relative_to(folder)).replace("\\", "/"): hashlib.sha256(p.read_bytes()).hexdigest()
              for p in sorted(folder.rglob("*")) if p.is_file()}
    write_json(folder / "MANIFEST.json", {"sha256": hashes, "probe_script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest()})
    return errors


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--end-date")
    parser.add_argument("--config", type=Path, help="JSON with 'candidates' {group: [tickers]}, optional 'daily' [tickers], "
                                                    "'searches' [queries], 'max_results' and 'history_start'; replaces the built-in lists")
    args = parser.parse_args()
    if args.config:
        import functools
        config = json.loads(args.config.read_text(encoding="utf-8"))
        CANDIDATES, DAILY = config["candidates"], set(config.get("daily", []))
        SEARCHES = config.get("searches", [])
        HISTORY_START = config.get("history_start", HISTORY_START)
        # probe() looks the search function up at call time, so the configured result count applies to it.
        instrument_search = functools.partial(instrument_search, max_results=int(config.get("max_results", 15)))
    today = datetime.now(ZoneInfo("Europe/Prague")).date()
    end_date = args.end_date or (today - timedelta(days=1)).isoformat()
    failures = probe(args.output if args.output.is_absolute() else ROOT / args.output, end_date)
    print(f"saved {args.output}; errors={len(failures)}", flush=True)
