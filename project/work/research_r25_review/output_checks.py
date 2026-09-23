"""Author's own reconstruction checks of the R25 outputs (not an independent review). Writes nothing."""
import json, sys
from pathlib import Path
import numpy as np, pandas as pd
ROOT = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(ROOT))
from models.cost_gaps_r23 import monthly_correction
from models.panel_persistence_r25 import estimate_lambda, BANDS

root = ROOT / 'output/research_r25/final'
native = pd.read_csv(root / 'native_forecasts.csv', low_memory=False); fits = [json.loads(l) for l in (root / 'fits.jsonl').read_text().splitlines()]
audit = pd.read_csv(root / 'lambda_audit.csv'); panel = pd.read_csv(root / 'panel_rows.csv'); states = json.loads((ROOT / 'output/research_r15/states.json').read_text())
food = pd.read_csv(ROOT / 'output/research_r24/final/native_forecasts.csv', low_memory=False)
base = native[native.model.eq('STATE_FAST_R15')].set_index(['origin', 'h']).sort_index()
assert native.origin.nunique() == 90 and native.groupby('model').size().eq(1170).all() and 'CZ' not in set(panel.geo) and panel.geo.nunique() == 26
fixed_all = [c for c in native if c.startswith('weight_') or ((c.startswith('value_') or c.startswith('contribution_')) and not c.endswith('_core'))]
worst = 0.
for rec in fits:
    o = rec['origin']; t = pd.Period(o, 'M'); assert rec['status'] == 'estimated'
    # 1. the panel weight is the pooled no-intercept slope on rows whose band ended by t-1, clipped to [0, 1]
    for b in BANDS:
        z = panel[(panel.band == b) & (pd.PeriodIndex(panel.label_end, freq='M') <= t - 1)].dropna(subset=['f', 'r', 'mu'])
        lam = estimate_lambda(z.f - z.mu, z.r - z.mu); a = audit[(audit.origin == o) & (audit.band == b)].iloc[0]
        assert abs(lam - a.panel_lambda) < 1e-12 and len(z) == a.panel_n and 0 <= lam <= 1
        assert abs(rec['lambdas']['CORE_PANEL_SHRINK_R25'][b - 1] - lam) < 1e-12
    # 2. corrections = monthly map of (lambda - 1) * (f - mu); sign opposes the deviation; exported core = FAST log rates + correction
    f = np.array(rec['f_cz']); mu = rec['mu_cz']
    for model, lams in rec['lambdas'].items():
        bands = (np.array(lams) - 1) * (f - mu); assert np.all(bands * (f - mu) <= 1e-15)
        np.testing.assert_allclose(monthly_correction(bands), rec['corrections'][model], atol=1e-14)
        own = native[(native.model == model) & (native.origin == o)].set_index('h').sort_index(); fast = base.loc[o]
        got = 100 * np.log1p(own.value_core.loc[1:12].to_numpy() / 100) - 100 * np.log1p(fast.value_core.loc[1:12].to_numpy() / 100)
        np.testing.assert_allclose(got, rec['corrections'][model], atol=1e-11); worst = max(worst, float(np.abs(got - rec['corrections'][model]).max()))
        fixed = [c for c in fixed_all if not (model.endswith('FOODNORM_R25') and c.endswith('_food'))]
        np.testing.assert_allclose(own[fixed].loc[1:12].to_numpy(float), fast[fixed].loc[1:12].to_numpy(float), rtol=0, atol=0)
        assert own.mm_forecast.loc[0] == fast.mm_forecast.loc[0]
        if model.endswith('FOODNORM_R25'):
            want = food[(food.model == 'FOOD_NORM_SHIFT_R24') & (food.origin == o)].set_index('h').value_food.loc[1:12]
            np.testing.assert_allclose(own.value_food.loc[1:12], want, rtol=0, atol=0)
    # 3. the Czech band means come from the saved FAST state less its own seasonal
    s = states[o]; adj = np.array([s['forecasts_log']['fast'][str(h)] - s['seasonal'][str((t + h).month)] for h in range(1, 13)]).reshape(4, 3).mean(axis=1)
    np.testing.assert_allclose(adj, f, atol=1e-12)
print(json.dumps(dict(status='pass', origins=len(fits), models=sorted(fits[0]['lambdas']), panel_rows=len(panel), panel_countries=int(panel.geo.nunique()),
                      max_core_reconstruction_gap=worst, checks=['panel weight = clipped pooled slope on bands ended by t-1', 'correction sign opposes the deviation',
                      'monthly map and exported core', 'h0, other blocks and weights untouched', 'food block equals R24 in the combination', 'Czech band means from the saved state']), indent=1))
