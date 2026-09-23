from pathlib import Path
import json
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[2]
HERE=Path(__file__).resolve().parent

def read(p):
    return pd.read_csv(ROOT/p,float_precision="round_trip")

own=read("work/research_r21_review/independent_nowcast_scores.csv")
board=read("output/research_r21/nowcast/evaluation/scoreboard.csv")
mapping={"common66":"common_fitted","alerts":"all_alerts"}
for r in own.itertuples():
    p=board[board.model.eq(r.model)&board["sample"].eq(mapping.get(r.sample,r.sample))].iloc[0]
    for field in ["n","rmse","mae","material_wins","material_losses"]:
        np.testing.assert_allclose(p[field],getattr(r,field),atol=1e-12,rtol=0,equal_nan=True)

previous=read("output/research_r17/attribution/primary_support.csv")
oldkeys=set(map(tuple,previous[["origin","h"]].drop_duplicates().to_numpy()))
assert len(oldkeys)==969
metrics={"headline_yy":("yy_exante","yy_actual"),"headline_mm":("mm_forecast","mm_actual"),
         "headline_cumulative_log":("cumulative_log_forecast","cumulative_log_actual"),
         "core_mm":("core_mm_forecast","core_mm_actual"),
         "core_cumulative_log":("core_cumulative_log_forecast","core_cumulative_log_actual")}
counts={}
for family in ["path","path_anchor"]:
    rows=read(f"output/research_r21/{family}/evaluation/primary_rows.csv")
    board=read(f"output/research_r21/{family}/evaluation/primary_scoreboard.csv")
    for model,g in rows.groupby("model"):
        assert not g.duplicated(["origin","h"]).any()
        assert set(map(tuple,g[["origin","h"]].to_numpy()))==oldkeys
    for r in board.itertuples():
        g=rows[rows.model.eq(r.model)&rows.h.eq(r.h)]
        mask={"full":np.ones(len(g),bool),"origins_2019_2021":g.origin.lt("2022-01"),
              "origins_2022_2023":g.origin.ge("2022-01")&g.origin.lt("2024-01"),
              "origins_2024plus":g.origin.ge("2024-01"),"recent_targets":g.target.ge("2024-01")}[r.sample]
        g=g[mask]
        predicted,actual=metrics[r.metric]
        e=(g[predicted]-g[actual]).dropna()
        assert len(e)==r.n==r.n_intended and r.n_missing_forecasts==0
        np.testing.assert_allclose([e.abs().mean(),np.sqrt(np.mean(e**2)),e.mean()],
                                   [r.mae,r.rmse,r.bias],rtol=0,atol=1e-12)
    counts[family]=len(board)
result={"nowcast_scoreboard_rows_checked":len(own),"path_primary_scoreboard_rows_checked":counts,"unchanged_primary_keys":len(oldkeys)}
(HERE/"scoreboard_results.json").write_text(json.dumps(result,indent=2),encoding="utf-8")
print(json.dumps(result,indent=2))
