"""Prepare a NEW current R31C h0 bundle without filling unavailable observations.

Historical training rows remain frozen. New rows use sourced observations and the
unchanged pure cz_struct.assemble_feature_frames function. No network calls.
"""
from __future__ import annotations
import argparse
import io
import json
from pathlib import Path

import numpy as np
import pandas as pd

from tools.live_bundle_r32 import adapter
from . import workflow as w

SERIES = {"headline": ("cpi_mm", "CZCPMOM Index"), "core": ("core", "CZCIXM Index"),
          "regulated": ("regulated", "CZCIRM Index"),
          "alcohol": ("alcohol_tobacco", "CZCPAMOM Index")}
MANUAL = {"core": "CZCIXM Index", "regulated": "CZCIRM Index"}
MARKET = ("CP7FCZ Index", "ECOBETCZ Index", "ECOBOTCZ Index", "EURCZK CNB Curncy")


def monthly(series):
    series = series.copy()
    series.index = series.index.to_period("M")
    return series.groupby(level=0).last().sort_index()


def empty():
    return pd.Series(dtype=float, index=pd.PeriodIndex([],freq="M"))


def load_snapshot(folder, as_of):
    raw = (Path(folder)/"MANIFEST.json").read_bytes()
    manifest = json.loads(raw)
    files = adapter.checked_files(folder,manifest["sha256"])
    request = json.loads(adapter.required(files,"request.json"))
    if w.clock(request["completed_at"]) > w.clock(as_of):
        raise ValueError("snapshot was completed after the requested as-of")
    df = pd.read_csv(io.BytesIO(adapter.required(files,"history_long.csv")))
    if not {"ticker","observation_date","value"} <= set(df):
        raise ValueError("snapshot schema is invalid")
    df["date"] = pd.to_datetime(df.observation_date)
    if df.date.dt.tz is not None or (df.date != df.date.dt.normalize()).any() or df.date.isna().any():
        raise ValueError("snapshot requires naive observation dates at midnight")
    if df.duplicated(["ticker","date"]).any():
        raise ValueError("duplicate snapshot observations")
    df["value"] = pd.to_numeric(df.value,errors="raise")
    if not np.isfinite(df.value).all():
        raise ValueError("nonfinite snapshot observation")
    # A current raw capture may include observations stamped on the call day.
    # The adapter separately excludes the Prague call day from its FX MTD mean.
    date = pd.Timestamp(as_of).tz_convert("Europe/Prague").tz_localize(None).normalize()
    if (df.date > date).any():
        raise ValueError("future raw observation")
    return {ticker:g.set_index("date").value.sort_index() for ticker,g in df.groupby("ticker")}, {
        "path":str(Path(folder).resolve()),"manifest_sha256":w.sha(raw),"files":manifest["sha256"],
        "retrieved_at":request["retrieved_at"],"completed_at":request["completed_at"]}


def load_manual(path, as_of):
    raw = Path(path).read_bytes()
    df = pd.read_csv(io.BytesIO(raw),dtype=str).fillna("")
    cols = {"series","observation_month","value","units","source","available_from"}
    if not cols <= set(df):
        raise ValueError("manual input requires series, observation_month, value, units, source, available_from")
    seen=set()
    rows=[]
    for row in df.to_dict("records"):
        key=(row["series"],w.month(row["observation_month"]))
        if key[0] not in MANUAL or key in seen:
            raise ValueError("unknown or duplicate manual series/month")
        seen.add(key)
        if row["units"]!="mm_pct" or not row["source"].strip():
            raise ValueError("manual CNB core/regulated requires sourced m/m percent, not rounded y/y")
        if w.clock(row["available_from"])>w.clock(as_of):
            raise ValueError("manual observation was unavailable at as-of")
        row["value"]=w.number(float(row["value"]))
        rows.append(row)
    if not rows:
        raise ValueError("manual input has no observations")
    return rows,raw


def extend_frames(loaded,fresh,target,agri_shifted,manual_rows=()):
    """Preserve all old training rows; build added months without interpolation."""
    import cz_struct
    frames={key:frame.copy(deep=True) for key,frame in loaded.frames.items()}
    monthly_raw={key:monthly(values) for key,values in fresh.items()}
    cutoff=min(frame.iloc[:,0].dropna().index.max() for key,frame in frames.items()
               if key in ("headline","core","regulated","alcohol"))
    if target<=cutoff:
        raise ValueError("current preparation target must be after frozen component history")
    new_months=pd.period_range(cutoff+1,target,freq="M")
    for row in manual_rows:
        t=pd.Period(row["observation_month"],freq="M")
        if not cutoff<t<target:
            raise ValueError("manual inputs may only add post-baseline, pre-target observations")
        ticker=MANUAL[row["series"]]
        s=monthly_raw.get(ticker,empty()).copy()
        if t in s and pd.notna(s.loc[t]) and abs(s.loc[t]-row["value"])>w.TOL:
            raise ValueError("manual/Bloomberg observation conflict")
        s.loc[t]=row["value"]
        monthly_raw[ticker]=s.sort_index()
    for key,(col,ticker) in SERIES.items():
        history=frames[key].index.union(new_months[new_months<target])
        frame=frames[key].reindex(history)
        source=monthly_raw.get(ticker,empty())
        edge=frames[key][col].dropna().index.max()
        for t in history[history>edge]:
            if t<target:
                frame.loc[t,col]=source.get(t,np.nan)
        frames[key]=frame
    comp=frames["components"].reindex(frames["components"].index.union(new_months[new_months<target]))
    edge=loaded.frames["components"].food.dropna().index.max()
    food=monthly_raw.get("CZCPFMOM Index",empty())
    for t in comp.index[comp.index>edge]:
        comp.loc[t,"food"]=food.get(t,np.nan)

    # Pin historical market observations; add only absent dates from the new
    # capture. This preserves R31C's exact historical fuel/pump verification.
    market={key:value.copy() for key,value in loaded.market.items()}
    for ticker in MARKET:
        source=fresh.get(ticker,pd.Series(dtype=float,index=pd.DatetimeIndex([])))
        market[ticker]=market.get(ticker,pd.Series(dtype=float,index=pd.DatetimeIndex([]))).combine_first(source).sort_index()
    fuel=monthly(market["CP7FCZ Index"])
    fuel=fuel.reindex(pd.period_range(fuel.index.min(),fuel.index.max(),freq="M"))
    fuel_mm=100*(fuel/fuel.shift(1)-1)
    fuel_edge=loaded.frames["components"].fuel.dropna().index.max()
    for t in comp.index[comp.index>fuel_edge]:
        comp.loc[t,"fuel"]=fuel_mm.get(t,np.nan)
    frames["components"]=comp
    weekly=frames["weekly_fuel"].copy()
    for col,ticker in (("petrol95","ECOBETCZ Index"),("diesel","ECOBOTCZ Index")):
        source=market[ticker].copy()
        source.index-=pd.to_timedelta(source.index.dayofweek,unit="D")
        source=source[~source.index.duplicated(keep="last")]/1000.
        weekly=weekly.reindex(weekly.index.union(source.index[source.index>weekly.index.max()]))
        weekly[col]=weekly[col].combine_first(source.reindex(weekly.index))
    frames["weekly_fuel"]=weekly.sort_index()

    fx=market.get("EURCZK CNB Curncy",pd.Series(dtype=float,index=pd.DatetimeIndex([])))
    fx_mean=fx.groupby(fx.index.to_period("M")).mean().round(3)
    if len(fx_mean):
        fx_mean=fx_mean.reindex(pd.period_range(fx_mean.index.min(),fx_mean.index.max(),freq="M"))
    fx_mm=100*(fx_mean/fx_mean.shift(1)-1)
    fx_mm.loc[fx_mm.index>=target]=np.nan  # MTD is supplied only by R32's as-of gate.
    old=frames["features"]
    get=lambda col: old[col] if col in old else empty()
    x,_,f=cz_struct.assemble_feature_frames(
        new_months,core=frames["core"].core,trailing_yoy=monthly_raw.get("CZCPYOY Index",empty()),
        exp12=get("exp12"),exp36=get("exp36"),household_exp=get("household_exp"),esi=get("esi"),
        eurczk_mm=fx_mm,services=empty(),imports=monthly_raw.get("CZEIIMOM Index",empty()),
        food=comp.food,agri_shifted=agri_shifted,food_ppi=monthly_raw.get("CZPPA10M Index",empty()))
    x=x.drop(columns=["services_l1"],errors="ignore")
    for key,new in (("features",x),("food_features",f)):
        frame=frames[key].reindex(frames[key].index.union(new_months))
        frame.loc[new_months,:]=new.reindex(columns=frame.columns)
        frames[key]=frame
    return frames,market


def prepare(base,snapshot,target,as_of,output,manual=None):
    output=w.owned(output,output_only=True)
    target=adapter.target_month(target)
    if w.clock(as_of)>w.utcnow():
        raise ValueError("future as-of")
    if adapter.decision_clock(as_of).to_period("M")!=target:
        raise ValueError("current preparation requires target equal to the Prague as-of month")
    if output.exists():
        raise ValueError("output exists; choose a NEW bundle directory")
    loaded=adapter.load_bundle(base,w.ROOT)
    fresh,capture=load_snapshot(snapshot,as_of)
    rows,manual_raw=load_manual(manual,as_of) if manual else ([],None)
    from data.struct_inputs import load_agri_price_mm
    agri_path=w.ROOT/"data/cz_agri_prices_raw.csv"
    agri_hash=w.sha(agri_path.read_bytes())
    agri=load_agri_price_mm()
    if w.sha(agri_path.read_bytes())!=agri_hash:
        raise ValueError("farm source changed during preparation")
    frames,market=extend_frames(loaded,fresh,target,agri,rows)
    output.mkdir(parents=True,exist_ok=False)
    (output/"nowcast").mkdir()
    (output/"market").mkdir()
    for key,name in adapter.NAMES.items():
        frames[key].to_csv(output/"nowcast"/name,index_label="period")
    frames["weekly_fuel"].to_csv(output/"nowcast/fuel_weekly_variant_b.csv",index_label="date")
    pd.concat([pd.DataFrame({"ticker":key,"observation_date":series.index.strftime("%Y-%m-%d"),"value":series.to_numpy()})
               for key,series in sorted(market.items()) if key in MARKET],ignore_index=True).to_csv(
                   output/"market/history_long.csv",index=False)
    if manual_raw is not None:
        (output/"manual_inputs.csv").write_bytes(manual_raw)
    provenance={"prepared_at":w.utcnow().isoformat(),"as_of":as_of,"target":str(target),
                "base_bundle":str(Path(base).resolve()),"base_provenance":loaded.provenance,"snapshot":capture,
                "farm_source":{"path":str(agri_path),"sha256":agri_hash,
                               "last_observation_month":str(agri.dropna().index.max()-1),
                               "transform":"unchanged data.struct_inputs.load_agri_price_mm; national seven-product log-change basket"},
                "manual_rows":rows,"feature_function":"unchanged cz_struct.assemble_feature_frames",
                "policy":"Preserve baseline training rows and market observations; extend observed months only. Missing observations stay NaN. Current FX is gated by R32.",
                "forecast_available":False,"path_available":False}
    w.write_new(output/"provenance.json",provenance)
    files={p.relative_to(output).as_posix():w.sha(p.read_bytes()) for p in sorted(output.rglob("*")) if p.is_file()}
    w.write_new(output/"MANIFEST.json",{"files":files})
    # Confirm portable schema, hashes and exact R31C fuel/pump source identities.
    adapter.load_bundle(output,w.ROOT)
    return {"status":"prepared","bundle":str(output),"forecast_available":False,
            "reason":"Prepared inputs only; invoke R33 readiness/run with explicit calendar and clock.",
            "base_unchanged":w.sha((Path(base)/"MANIFEST.json").read_bytes())==loaded.provenance["bundle_manifest_sha256"]}


def main(argv=None):
    from .cli import Parser
    p=Parser(description=__doc__)
    p.add_argument("--base-bundle",type=Path,required=True)
    p.add_argument("--snapshot",type=Path,required=True)
    p.add_argument("--target",required=True)
    p.add_argument("--as-of",required=True)
    p.add_argument("--output",type=Path,required=True)
    p.add_argument("--manual-inputs",type=Path)
    try:
        args=p.parse_args(argv)
        result=prepare(args.base_bundle,args.snapshot,args.target,args.as_of,args.output,args.manual_inputs)
        code=0
    except Exception as exc:
        result={"status":"blocked","forecast_available":False,"reason":f"{type(exc).__name__}: {exc}"}
        code=2
    print(w.encoded(result).decode(),end="")
    return code


if __name__=="__main__":
    raise SystemExit(main())
