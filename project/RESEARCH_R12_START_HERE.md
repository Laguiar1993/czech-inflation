# CZK Cpi Forecasting - Latest models

Start with `docs/implementation/R12_RESULTS_2026-09-09.md` for the latest research
verdict. Original formulas remain unchanged. This entry supersedes any inference
that new experiments automatically become operating models.

- Main next-release nowcast: HARD_BASE; category TARGET_OWN is the research accuracy
  challenger; HARD_HALF/HARD_FULL are independent baseline-error corrections.
- Main path research reference: BRIDGE_HARD / INDEPENDENT_BRIDGE.
- R12 category pooling: small headline gains, weak incremental evidence, retained
  in research; no automatic adoption.
- R12 food trend/cost and direct cumulative paths: no promotion.
- R12 all-month energy wrapper: operational but no historically complete strict
  payload; no scored gain claimed. See energy NOTES for the missing information.

New source files are `models/*_r12.py`; runners are
`core_pooling_experiment_r12.py`, `path_improvements_experiment_r12.py`, and
`admin_events_experiment_r12.py`. Specs and independent review are under
`docs/implementation/R12*`. Results, release-level comparisons and input hashes
are under `output/research_r12/`. No online retailer data was collected.

Install `requirements-r9-lock.txt` in a compatible scientific Python environment.
From this folder:

```powershell
python -m pytest test_core_pooling_r12.py test_path_improvements_r12.py test_admin_events_r12.py -q
python core_pooling_experiment_r12.py --verify
python path_improvements_experiment_r12.py --verify
python admin_events_experiment_r12.py
```

For an actual fresh fit of all four paths, use:

```powershell
python path_improvements_experiment_r12.py --output-dir output/research_r12/path/fresh_run
```

The path quick verification re-scores saved predictions rather than refitting them.
Its fresh fit reuses only unchanged h1–h3 X13 values after frozen dependency checks;
all other baseline path arithmetic and the new forecasts are recomputed. Full
legacy/live operations may require Census X13 and a refreshed local database; this
research reproduction uses the supplied frozen inputs.
