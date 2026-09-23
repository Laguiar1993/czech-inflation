"""Probe 1: look-ahead audit of the R27 food error-correction inputs.

Checks, with the reviewer's own code only:
  a. the origin clocks (h0 rows) are the eve of the origin month's CPI detail release, and are the same in R24;
  b. the food availability stamps equal the CPI detail release dates (09:00 Prague) for every month of the panel;
  c. the PPI and farm-price stamps follow the declared reconstruction rule; how much slack each series has
     against the clock at the last common month (how wrong the reconstruction could be before it matters);
  d. published_levels / last_common_month behave as claimed: L = origin-1 at every origin, and the reviewer's
     own re-derivation of gap_last, alpha_raw and the h1-6 corrections reproduces ecm_audit.csv / food_log_rates.csv;
  e. vintage sensitivity: how much gap_last and the h6 cumulative correction move if the last farm or producer
     level were later revised by a typical monthly change.
"""
import json

import numpy as np
import pandas as pd

import probe_common as pc

OUT = pc.HERE / 'probe_01_lookahead'
OUT.mkdir(exist_ok=True)

levels = pc.load_levels(); available = pc.load_available(); cal = pc.load_calendar()
native = pc.load_native(); clocks = pc.clocks(native)
audit = pc.load_audit(); rates_file = pd.read_csv(pc.R27 / 'food_log_rates.csv', float_precision='round_trip')
findings = {}

# a. clocks -------------------------------------------------------------------------------------------------
r24 = pc.load_native(pc.R24)
r24_clocks = pc.clocks(r24)
fast_clocks = {o: pd.Timestamp(c) for o, c in zip(*[native[(native.model == pc.FAST) & (native.h == 0)][k] for k in ('origin', 'as_of_utc')])}
same_r24 = all(clocks[o] == r24_clocks[o] for o in clocks); same_fast = all(clocks[o] == fast_clocks[o] for o in clocks)
detail = pd.to_datetime(cal.detail_release_dt)
rows = []
for o, clock in clocks.items():
    t = pd.Period(o, 'M')
    rel = detail.loc[t]
    eve = (rel - pd.Timedelta(days=1)).replace(hour=23, minute=59).tz_localize(pc.PRAGUE)
    local = clock.tz_convert(pc.PRAGUE)
    food_t = available.loc[t, 'food']; food_prev = available.loc[t - 1, 'food']
    rows.append(dict(origin=o, clock_prague=str(local), detail_release=str(rel.date()), kind=cal.loc[t, 'first_release_kind'],
                     is_eve_of_detail=bool(local == eve), origin_food_visible=bool(food_t <= clock), prev_food_visible=bool(food_prev <= clock),
                     hours_before_release=float((rel.tz_localize(pc.PRAGUE) + pd.Timedelta(hours=9) - local).total_seconds() / 3600)))
clock_table = pd.DataFrame(rows); clock_table.to_csv(OUT / 'clocks.csv', index=False)
findings['a_clocks'] = dict(n_origins=len(clock_table), same_as_r24=same_r24, same_as_fast_rows=same_fast,
                            all_eve_of_detail_release=bool(clock_table.is_eve_of_detail.all()),
                            origins_not_eve=clock_table[~clock_table.is_eve_of_detail].origin.tolist(),
                            origin_month_food_never_visible=bool(~clock_table.origin_food_visible.any()),
                            previous_month_food_always_visible=bool(clock_table.prev_food_visible.all()),
                            hours_before_release_min=float(clock_table.hours_before_release.min()), hours_before_release_max=float(clock_table.hours_before_release.max()))

# b. food stamps against the release calendar --------------------------------------------------------------
expected_food = (pd.to_datetime(cal.detail_release_dt).dt.normalize() + pd.Timedelta(hours=9)).dt.tz_localize(pc.PRAGUE).dt.tz_convert('UTC')
cmp = pd.DataFrame(dict(stamp=available.food, expected=expected_food.reindex(available.index)))
cmp['match'] = cmp.stamp == cmp.expected
flash = cal[cal.first_release_kind.ne('regular')]
findings['b_food_stamps'] = dict(months=len(cmp), matches=int(cmp.match.sum()), mismatches=cmp[~cmp.match].index.astype(str).tolist(),
                                 flash_months=flash.index.astype(str).tolist(), flash_kinds=flash.first_release_kind.unique().tolist(),
                                 note='food stamps use the detail release (not the flash), which is the later of the two')

# c. PPI / farm stamps: reconstruction rule and slack at L ------------------------------------------------------
exceptions = {1: 9, 3: 4, 4: 4, 6: 1, 12: 1}
rule_ppi = pd.Series([((m + 1).to_timestamp() + pd.Timedelta(days=15 + exceptions.get(m.month, 0))).tz_localize(pc.PRAGUE).tz_convert('UTC') for m in available.index], index=available.index)
rule_agri = pd.Series([((m + 1).to_timestamp() + pd.Timedelta(days=25)).tz_localize(pc.PRAGUE).tz_convert('UTC') for m in available.index], index=available.index)
findings['c_rule'] = dict(ppi_rule_matches=int((rule_ppi == available.food_ppi).sum()), agri_rule_matches=int((rule_agri == available.agri4).sum()), months=len(available),
                          ppi_rule='day 16 of the following month (+9 Jan, +4 Mar/Apr, +1 Jun/Dec), midnight Prague',
                          agri_rule='day 26 of the following month, midnight Prague', source='tools/r14_food/prepare_inputs.py, reconstructed, not observed release dates')
slack = []
for o, clock in clocks.items():
    t = pd.Period(o, 'M'); L = t - 1
    slack.append(dict(origin=o, L=str(L), **{f'slack_days_{c}': float((clock - available.loc[L, c]).total_seconds() / 86400) for c in ('agri4', 'food_ppi', 'food')},
                      # days by which the reconstructed stamp of month L could be late before L stops being published by the clock
                      ))
slack = pd.DataFrame(slack); slack.to_csv(OUT / 'slack_at_L.csv', index=False)
findings['c_slack_days_at_L'] = {c: dict(min=float(slack[f'slack_days_{c}'].min()), median=float(slack[f'slack_days_{c}'].median()), max=float(slack[f'slack_days_{c}'].max()))
                                 for c in ('agri4', 'food_ppi', 'food')}
# what the actual CZSO calendar would have to look like for L to move: the PPI of month t-1 would have to come out after the CPI of month t
findings['c_reading'] = ('L = t-1 needs the producer and farm prices of month t-1 to be out before the eve of the CPI release of month t '
                         '(about the 10th of t+1). The reconstruction puts them on the 16th-25th and 26th of month t; the minimum slack is the '
                         'smallest number of days the true release could be later than the reconstruction before any origin loses month t-1.')

# d. published_levels / last_common_month, and reproduction of the audit ------------------------------------------
rep = []
for o, clock in clocks.items():
    t = pd.Period(o, 'M')
    pub = pc.published_before(levels, available, o, clock)
    last_each = {c: pub[c].last_valid_index() for c in pub}
    L = pub.dropna().index.max()
    masked_after_L = {c: int(pub.loc[pub.index > L, c].notna().sum()) for c in pub}
    for model, regs in (('FOOD_ECM_R27', ('food_ppi', 'agri4')), ('FOOD_ECM_PPI_R27', ('food_ppi',))):
        gap, info = pc.own_gap(pub, L, regs)
        alpha, raw, npairs = pc.own_speed(pub, gap)
        corr = pc.own_correction(alpha, float(gap.loc[L]), L, o)
        a = audit[(audit.origin == o) & (audit.model == model)].iloc[0]
        f = rates_file[(rates_file.origin == o) & (rates_file.model == model)].set_index('h').correction
        rep.append(dict(origin=o, model=model, L=str(L), L_is_origin_minus_1=bool(L == t - 1), audit_L=a.last_common_month, L_matches_audit=bool(str(L) == a.last_common_month),
                        last_food=str(last_each['food']), last_ppi=str(last_each['food_ppi']), last_agri=str(last_each['agri4']),
                        months_published_after_L=sum(masked_after_L.values()), n_window=info['n'], audit_n=int(a.n), window_start=info['window_start'], audit_window_start=a.window_start,
                        gap_last_own=float(gap.loc[L]), gap_last_audit=float(a.gap_last), gap_diff=abs(float(gap.loc[L]) - float(a.gap_last)),
                        alpha_raw_own=raw, alpha_raw_audit=float(a.speed_alpha_raw), alpha_raw_diff=abs(raw - float(a.speed_alpha_raw)), alpha_own=alpha, alpha_audit=float(a.alpha),
                        n_pairs_own=npairs, n_pairs_audit=int(a.speed_n_pairs),
                        max_corr_diff_h1_6=max(abs(corr[h] - float(f.loc[h])) for h in range(1, 7)), max_corr_h7_12=max(abs(float(f.loc[h])) for h in range(7, 13)),
                        coef_ppi_own=float(info['beta'][2]), coef_ppi_audit=float(a.coef_food_ppi), trend_own=float(info['beta'][1]), trend_audit=float(a.trend_per_month)))
rep = pd.DataFrame(rep); rep.to_csv(OUT / 'reproduction_of_audit.csv', index=False)
findings['d_published_levels'] = dict(origins=int(rep.origin.nunique()), L_equals_origin_minus_1_all=bool(rep.L_is_origin_minus_1.all()), L_matches_audit_all=bool(rep.L_matches_audit.all()),
                                      months_published_after_L_total=int(rep.months_published_after_L.sum()), window_n_matches_audit=bool((rep.n_window == rep.audit_n).all()),
                                      window_start_matches=bool((rep.window_start == rep.audit_window_start).all()),
                                      max_abs_gap_last_diff=float(rep.gap_diff.max()), max_abs_alpha_raw_diff=float(rep.alpha_raw_diff.max()),
                                      alpha_all_minus_025=bool((rep.alpha_own == -.25).all() and (rep.alpha_audit == -.25).all()),
                                      alpha_raw_range=[float(rep.alpha_raw_own.min()), float(rep.alpha_raw_own.max())],
                                      max_abs_correction_diff_h1_6=float(rep.max_corr_diff_h1_6.max()), max_abs_correction_h7_12=float(rep.max_corr_h7_12.max()),
                                      n_pairs_matches=bool((rep.n_pairs_own == rep.n_pairs_audit).all()),
                                      first_window_n=int(rep.n_window.min()), origins_with_full_96_window=int((rep[rep.model == 'FOOD_ECM_R27'].n_window == 96).sum()))

# d2. the mask actually bites somewhere? (which series would be masked at t-1 under an earlier clock, e.g. the flash date)
bite = []
for o, clock in clocks.items():
    t = pd.Period(o, 'M')
    for c in ('agri4', 'food_ppi', 'food'):
        bite.append(dict(origin=o, series=c, stamp_t_minus_1=str(available.loc[t - 1, c]), stamp_t=str(available.loc[t, c]), clock=str(clock),
                         t_minus_1_visible=bool(available.loc[t - 1, c] <= clock), t_visible=bool(available.loc[t, c] <= clock)))
bite = pd.DataFrame(bite); bite.to_csv(OUT / 'visibility_t_and_t_minus_1.csv', index=False)
findings['d2_visibility'] = {c: dict(t_minus_1_visible_share=float(bite[bite.series == c].t_minus_1_visible.mean()), t_visible_share=float(bite[bite.series == c].t_visible.mean())) for c in ('agri4', 'food_ppi', 'food')}

# e. vintage sensitivity of gap_last / cumulative h6 correction -----------------------------------------------------
sens = []
d_agri = levels.agri4.diff().dropna(); d_ppi = levels.food_ppi.diff().dropna()
findings['e_monthly_change_sd'] = dict(agri4=float(d_agri.std()), food_ppi=float(d_ppi.std()), food=float(levels.food.diff().dropna().std()))
for o, clock in clocks.items():
    t = pd.Period(o, 'M'); L = t - 1
    pub = pc.published_before(levels, available, o, clock)
    gap0, _ = pc.own_gap(pub, L, ('food_ppi', 'agri4')); a0, _, _ = pc.own_speed(pub, gap0); c0 = sum(pc.own_correction(a0, float(gap0.loc[L]), L, o)[h] for h in range(1, 7))
    row = dict(origin=o, gap_last=float(gap0.loc[L]), cum6=c0)
    for col, shock in (('agri4', 1.), ('agri4', 3.), ('food_ppi', .5), ('food_ppi', 1.)):
        p = pub.copy(); p.loc[L, col] += shock
        gap1, _ = pc.own_gap(p, L, ('food_ppi', 'agri4')); a1, _, _ = pc.own_speed(p, gap1); c1 = sum(pc.own_correction(a1, float(gap1.loc[L]), L, o)[h] for h in range(1, 7))
        row[f'd_gap_{col}_{shock}'] = float(gap1.loc[L]) - float(gap0.loc[L]); row[f'd_cum6_{col}_{shock}'] = c1 - c0
    sens.append(row)
sens = pd.DataFrame(sens); sens.to_csv(OUT / 'vintage_sensitivity.csv', index=False)
findings['e_vintage_sensitivity'] = {k: dict(median_abs=float(sens[k].abs().median()), max_abs=float(sens[k].abs().max())) for k in sens.columns if k.startswith('d_')}
findings['e_cum6_reference'] = dict(median_abs_cum6=float(sens.cum6.abs().median()))

(OUT / 'findings.json').write_text(json.dumps(findings, indent=1, default=str), encoding='utf-8')
print(json.dumps(findings, indent=1, default=str))
