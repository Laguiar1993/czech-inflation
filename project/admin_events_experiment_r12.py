"""Frozen R12 energy evidence audit, baseline replay and unchanged R9 scenarios.

Run offline from any directory. Writes only output/research_r12/energy.
Builds and writes all forecasts before opening first-release outcomes/surveys.
"""
from __future__ import annotations

import csv
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
import platform
import subprocess

import numpy as np
import pandas as pd

from models.admin_events_r12 import assess, VERSION

ROOT = Path(__file__).resolve().parent
OUT = ROOT/'output/research_r12/energy'
FIX = ROOT/'tests/fixtures/cleanup'
BASELINE_COMMIT = 'c1dacdf4ec946bd5d59d0d7f96876ad9efd1f0a3'
SPEC_COMMIT = 'abd1342'
MODELS = ('BASE', 'CATEGORY', 'HARD_HALF', 'HARD_FULL', 'STRICT_ALL_MONTH_ADDITIONS')
COMMON_GAPS = ('missing_dated_bills', 'missing_dated_household_exposure',
               'missing_embedded_energy_baseline')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def git_provenance(root):
    """Optional local-checkout metadata; never discover an enclosing repository."""
    git_path = Path(root)/'.git'
    if not git_path.exists():
        return dict(git_head=None, git_provenance='portable_snapshot_no_local_git')
    try:
        head = subprocess.check_output(['git','--git-dir='+str(git_path),'rev-parse','HEAD'],
            cwd=root,text=True,stderr=subprocess.DEVNULL,timeout=5).strip()
    except (OSError, subprocess.SubprocessError) as exc:
        return dict(git_head=None,git_provenance='git_metadata_unavailable',
                    git_error=type(exc).__name__)
    return dict(git_head=head,git_provenance='local_checkout')


def load_inputs():
    """Load hashed forecast inputs, excluding all survey/evaluation columns."""
    hashes = json.loads((FIX/'MANIFEST.json').read_text())
    for name, expected in hashes.items():
        if sha(FIX/name) != expected:
            raise ValueError(f'Frozen fixture mismatch: {name}')
    def monthly(relative, usecols=None):
        d = pd.read_csv(ROOT/relative, index_col=0, float_precision='round_trip', usecols=usecols)
        d.index = pd.PeriodIndex(d.index, freq='M')
        return d
    ref = monthly('output/independent_nowcast_forecasts.csv')
    btcols = ['period','as_of_eve','adm_pred_eve','STRUCT_EVE','core_pred_eve']
    return dict(reference=ref, backtest=monthly('output/cz_struct_backtest.csv', btcols),
        category=monthly('output/core_split_forecasts.csv', ['period','TARGET_OWN']),
        headline=monthly('tests/fixtures/cleanup/target_headline_cpi_mm.csv').iloc[:,0],
        components=monthly('tests/fixtures/cleanup/component_food_fuel_mm.csv'),
        core=monthly('tests/fixtures/cleanup/cnb_core_mm.csv').iloc[:,0],
        regulated=monthly('tests/fixtures/cleanup/cnb_regulated_mm.csv').iloc[:,0],
        alcohol=monthly('tests/fixtures/cleanup/alcohol_tobacco.csv').iloc[:,0],
        ledger=pd.read_csv(ROOT/'data/energy_policy_ledger.csv', keep_default_na=False),
        fixture_hashes=hashes)


def replay_origin(data, target, cutoff):
    import cz_struct as s
    # Remove current/future rows before passing any series into baseline routines.
    released = lambda d: d.loc[(d.index < target) & s._released_index(d.index, cutoff)]
    y, c, core, reg, alc = (released(data[k]) for k in
        ('headline','components','core','regulated','alcohol'))
    weights = s.solve_weights(y,c,core,reg,target-1,as_of=cutoff,alc=alc)[s._regime(target)]
    adm = s.admin_forecast(reg,target,as_of=cutoff,announce_mode='documented',
                           w_adm=weights['administered'])
    return dict(admin=adm, administered_weight=weights['administered'],
        core_weight=weights['core'], eligible_history_end=str(reg.index.max()),
        eligible_history_n=len(reg), basket_available_at=s._basket_available_from(
            s._regime(target) if s._basket_available_from(s._regime(target)) <= cutoff
            else s._regime(target)-2).isoformat())


def evidence_audit(data):
    """Evidence inventory, not a numerical event-to-CPI mapping."""
    rows = []
    for source in data['ledger'].to_dict('records'):
        r = {k: source[k] for k in ('policy_id','event','effective_month','source_pub_date',
             'treatment_known_date','affected_items','provenance','source_url')}
        treatment = source['treatment_known_date'] or None
        treatment_note = 'Frozen ledger date claim; not upgraded by the R12 wrapper.'
        gap = list(COMMON_GAPS)
        if source['policy_id'] == 'vat_waiver_2021':
            treatment = '2021-12-10'
            treatment_note = ('Methodology linked in dated 10 Dec 2021 release. Current Czech note footer '
                'says updated 9 Dec; no timestamped archive establishes earlier public availability. '
                'Conservative confirmation date only, not a claim of first publication.')
        if source['policy_id'] in ('saving_tariff','poze_waiver'):
            treatment = '2022-11-10'
            treatment_note = ('CZSO October 2023 note explicitly says methodology published with October '
                '2022 release. October 2022 page updated footer 9 Nov is not publication proof. '
                'POZE persistence can reuse established treatment; later confirmations are not new onset.')
        if source['policy_id'] == 'saving_tariff':
            gap += ['missing_cpi_total_expenditure_and_credit_spreading_base']
        if source['policy_id'] in ('supplier_repricing_2022','price_caps_2023'):
            gap += ['missing_contract_cohort_prices_and_repricing_exposure']
        if source['event'] == 'extension':
            gap += ['extension_must_preserve_original_start_and_supersede_only_supported_expiry']
        linked = data['ledger'].loc[data['ledger'].policy_id.eq(source['policy_id']), 'event'].tolist()
        rows.append(r | dict(r12_treatment_confirmation=treatment, treatment_evidence=treatment_note,
            policy_link_actions=';'.join(linked), bill_available_at=None,
            exposure_available_at=None, embedded_baseline_available_at=None,
            strict_payload_complete=False, missing_inputs=';'.join(gap)))
    for month in ('2022-09','2022-11'):
        rows.append(dict(policy_id=f'unknown_supplier_repricing_{month}', event='unmapped',
            effective_month=month, source_pub_date=None,treatment_known_date=None,
            affected_items='electricity;gas',provenance='evidence_gap',source_url=None,
            r12_treatment_confirmation=None, treatment_evidence='No independent dated magnitude or '
            'contract-exposure row in the audited local inventory; this is not an exhaustive claim '
            'that no announcement existed.',policy_link_actions='',bill_available_at=None,
            exposure_available_at=None,embedded_baseline_available_at=None,
            strict_payload_complete=False,missing_inputs=';'.join(COMMON_GAPS+('missing_supplier_event',))))
    return pd.DataFrame(rows)


def build_forecasts(data, strict_payloads=None):
    """Optional future reviewed payloads enter only through strict assess()."""
    strict_payloads = {} if strict_payloads is None else strict_payloads
    ref, bt = data['reference'], data['backtest']
    if len(ref) != 90 or not ref.index.equals(bt.index):
        raise ValueError('Expected unchanged 90-origin reference frame')
    audit = evidence_audit(data)
    rows, replay = [], []
    for t, r in ref.iterrows():
        clock = pd.Timestamp(r.as_of_eve)
        utc = clock.tz_localize('Europe/Prague').tz_convert('UTC').to_pydatetime()
        result = replay_origin(data, t, clock)
        replay.append(dict(period=str(t),as_of_eve=clock.isoformat(), **result,
            admin_reference=bt.loc[t,'adm_pred_eve'],admin_replay_delta=result['admin']-bt.loc[t,'adm_pred_eve'],
            coreweight_delta=result['core_weight']-r.coreweight))
        events = audit.loc[audit.effective_month.eq(str(t))]
        reasons, effect, eligible = '', None, False
        if t.month == 1:
            status = 'baseline_january_preserved'
            reasons = 'Existing January overlap retained; baseline is not strict-vintage certified.'
        elif str(t) in strict_payloads:
            args = dict(strict_payloads[str(t)])
            args.update(month=str(t), previous_month=str(t-1), as_of=utc)
            a = assess(**args)
            status, effect = a.status, a.incremental_pp
            eligible = status == 'strict_eligible'
            reasons = ';'.join(a.reasons)
        elif len(events):
            status = 'mapping_unavailable'
            reasons = ';'.join(sorted(set(';'.join(events.missing_inputs).split(';'))))
        else:
            status = 'no_evidenced_event'
            reasons = 'No complete independent incremental event payload; retain baseline.'
        adjustment = effect if eligible else 0.
        row = dict(period=str(t),as_of_eve=clock.isoformat(),as_of_utc=utc.isoformat(),
            BASE=r.HARD_BASE,CATEGORY=data['category'].loc[t,'TARGET_OWN'],
            HARD_HALF=r.HARD_HALF,HARD_FULL=r.HARD_FULL,
            STRICT_ALL_MONTH_ADDITIONS=r.HARD_BASE+adjustment,
            candidate_effect_pp=effect,applied_adjustment_pp=adjustment,
            strict_eligible=eligible,status=status,reasons=reasons,
            event_ids=';'.join(events.policy_id),admin_forecast=result['admin'],
            admin_weight=result['administered_weight'])
        rows.append(row)
    replay = pd.DataFrame(replay).set_index('period')
    if replay[['admin_replay_delta','coreweight_delta']].abs().max().max() >= 1e-10:
        raise ValueError('Frozen baseline replay failed')
    frame = pd.DataFrame(rows).set_index('period')
    frame.index = pd.PeriodIndex(frame.index, freq='M')
    return frame, replay


def scenario_replay():
    from energy_ledger_experiment import build_results
    rows, manifest = build_results()
    handle = io.StringIO(newline='')
    writer = csv.DictWriter(handle, fieldnames=list(dict.fromkeys(k for row in rows for k in row)))
    writer.writeheader()
    writer.writerows(rows)
    return handle.getvalue(), manifest


def origin_evidence_clocks(audit, forecasts, replay):
    """Full inventory at each cutoff, with unknown inputs kept separate from zero."""
    def end_of_day(value):
        if value is None or pd.isna(value) or value == '':
            return None
        return pd.Timestamp(value).normalize().tz_localize('UTC') + pd.Timedelta(hours=23,minutes=59,seconds=59)
    rows = []
    for t, f in forecasts.iterrows():
        cutoff = pd.Timestamp(f.as_of_utc)
        weight_time = end_of_day(replay.loc[str(t),'basket_available_at'])
        for e in audit.to_dict('records'):
            source_time = end_of_day(e['source_pub_date'])
            treatment_time = end_of_day(e['r12_treatment_confirmation'])
            source_visible = source_time is not None and source_time <= cutoff
            treatment_visible = treatment_time is not None and treatment_time <= cutoff
            rows.append(dict(period=str(t),as_of_utc=cutoff.isoformat(),policy_id=e['policy_id'],
                event=e['event'],effective_month=e['effective_month'],
                transition_this_month=e['effective_month']==str(t),
                source_available_utc=source_time.isoformat() if source_time else None,
                treatment_confirmed_utc=treatment_time.isoformat() if treatment_time else None,
                source_visible=source_visible,treatment_visible=treatment_visible,
                bill_available_utc=None,exposure_available_utc=None,embedded_baseline_available_utc=None,
                weight_available_utc=weight_time.isoformat(),weight_visible=weight_time<=cutoff,
                strict_eligible=False,missing_inputs=e['missing_inputs'],
                interpretation='Source-clock audit only; no complete monetary/exposure/baseline payload.'))
    return pd.DataFrame(rows)


def score(forecasts, targets):
    """Evaluation-only target inputs; paired uncertainty never selects scenarios."""
    sv = targets.reindex(forecasts.index)
    if sv[['actual','survey_median']].isna().any().any():
        raise ValueError('Missing first-release evaluation targets')
    surprise = sv.actual-sv.survey_median
    big = surprise.abs() >= .4-1e-9
    frames = [('all',np.ones(len(sv),bool)),('recent2024+',sv.index>=pd.Period('2024-01')),
        ('ex_jan',sv.index.month!=1),('flash2025+',sv.index>=pd.Period('2025-01')),
        ('big',big),('big_up',big & (surprise>0)),('big_down',big & (surprise<0))]
    scores, events, bootstrap = [], [], []
    baseerror = forecasts.BASE-sv.actual
    for model in MODELS:
        if model not in forecasts:
            continue
        e = forecasts[model]-sv.actual
        dev = forecasts[model]-sv.survey_median
        ev = pd.DataFrame(dict(model=model,actual=sv.actual,consensus=sv.survey_median,
            forecast=forecasts[model],error=e,surprise=surprise,deviation=dev,
            gain_vs_consensus=surprise.abs()-e.abs(),gain_vs_base=baseerror.abs()-e.abs(),
            big=big,alert=dev.abs()>=.2-1e-9,direction_correct=dev*surprise>0))
        events.append(ev)
        for frame, mask in frames:
            z = ev.loc[mask]
            if not len(z):
                continue
            scores.append(dict(model=model,frame=frame,n=len(z),bias=z.error.mean(),
                mae=z.error.abs().mean(),rmse=np.sqrt(np.mean(z.error**2)),
                direction_n=int((z.surprise!=0).sum()),direction_correct=int(z.direction_correct.sum()),
                material_win_vs_base=int((z.gain_vs_base>=.15-1e-9).sum()),
                material_loss_vs_base=int((z.gain_vs_base<=-.15+1e-9).sum()),
                material_win_vs_consensus=int((z.gain_vs_consensus>=.15-1e-9).sum()),
                material_loss_vs_consensus=int((z.gain_vs_consensus<=-.15+1e-9).sum()),
                alerts=int(z.alert.sum()),alerted_big=int((z.alert & z.big).sum()),
                false_alarm=int((z.alert & ~z.big).sum()),missed_big=int((~z.alert & z.big).sum())))
    rng = np.random.default_rng(1209)
    for frame,mask in frames:
        a = (forecasts.STRICT_ALL_MONTH_ADDITIONS-sv.actual).loc[mask].to_numpy()
        b = baseerror.loc[mask].to_numpy()
        if not len(a):
            continue
        n = len(a)
        starts = rng.integers(0,n,(2000,int(np.ceil(n/6))))
        ix = ((starts[:,:,None]+np.arange(6))%n).reshape(2000,-1)[:,:n]
        for name, measure in [('mae',lambda v,axis:np.abs(v).mean(axis)),
                               ('rmse',lambda v,axis:np.sqrt(np.square(v).mean(axis)))]:
            d = measure(a[ix],1)-measure(b[ix],1)
            bootstrap.append(dict(frame=frame,metric=name,n=n,block=6,replicates=2000,seed=1209,
                delta=measure(a,0)-measure(b,0),lower=np.quantile(d,.025),upper=np.quantile(d,.975)))
    return pd.DataFrame(scores), pd.concat(events), pd.DataFrame(bootstrap)


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    data = load_inputs()
    forecasts, replay = build_forecasts(data)
    forecasts.to_csv(OUT/'forecasts.csv',float_format='%.17g',index_label='period')
    replay.to_csv(OUT/'baseline_replay.csv',float_format='%.17g')
    audit = evidence_audit(data)
    audit.to_csv(OUT/'evidence_audit.csv',index=False)
    origin_evidence_clocks(audit,forecasts,replay).to_csv(OUT/'origin_evidence_clocks.csv',index=False)
    scenario_text, scenario_manifest = scenario_replay()
    frozen_scenario = (ROOT/'output/energy_ledger_scenarios.csv').read_bytes()
    if scenario_text.encode() != frozen_scenario:
        raise ValueError('R9 scenario replay is not byte-identical')
    (OUT/'scenario_replay.csv').write_bytes(scenario_text.encode())
    (OUT/'scenario_manifest.json').write_text(json.dumps(scenario_manifest,indent=2,default=str))
    # Forecast files are complete before opening any evaluation outcome/survey.
    forecast_hash_before_scoring = sha(OUT/'forecasts.csv')
    sv = pd.read_csv(ROOT/'data/czcpmom_survey_history_extended.csv',float_precision='round_trip')
    sv = sv.loc[sv.era.ne('flash_survey_suspect')].set_index('target_month')
    sv.index = pd.PeriodIndex(sv.index,freq='M')
    if not sv.index.is_unique:
        raise ValueError('Duplicate first-release evaluation target')
    scores, events, uncertainty = score(forecasts,sv)
    scores.to_csv(OUT/'scores.csv',index=False,float_format='%.17g')
    events.to_csv(OUT/'release_scores.csv',index_label='period',float_format='%.17g')
    events.loc[events.alert].to_csv(OUT/'alerts.csv',index_label='period',float_format='%.17g')
    events.loc[events.big].to_csv(OUT/'large_surprises.csv',index_label='period',float_format='%.17g')
    uncertainty.to_csv(OUT/'paired_uncertainty.csv',index=False,float_format='%.17g')
    summary = dict(n=len(forecasts),strict_eligible_additions=int(forecasts.strict_eligible.sum()),
        changed_forecasts=int((forecasts.STRICT_ALL_MONTH_ADDITIONS!=forecasts.BASE).sum()),
        status_counts={k:int(v) for k,v in forecasts.status.value_counts().items()},
        admin_replay_max_abs_delta=float(replay.admin_replay_delta.abs().max()),
        coreweight_replay_max_abs_delta=float(replay.coreweight_delta.abs().max()),
        event_inventory_rows=len(audit),scenario_rows=len(list(csv.DictReader(io.StringIO(scenario_text)))),
        scenario_byte_identical=True,forecast_hash_before_scoring=forecast_hash_before_scoring,
        main_scores=scores.loc[scores.frame.eq('all')].to_dict('records'),
        conclusion='No complete strict event payload. Baseline retained at all origins; no measured accuracy improvement.',
        promotion=False)
    (OUT/'summary.json').write_text(json.dumps(summary,indent=2))
    sources = ['models/admin_events_r12.py','admin_events_experiment_r12.py','test_admin_events_r12.py',
        'docs/implementation/R12_ENERGY_SPEC.md','cz_struct.py','config.py','data/local_adapter.py',
        'models/energy_ledger.py','energy_ledger_experiment.py','data/energy_policy_ledger.csv',
        'data/energy_accounting_params.csv','data/admin_announcements_history.csv',
        'data/release_calendar_cz_cpi.csv','output/independent_nowcast_forecasts.csv',
        'output/core_split_forecasts.csv','output/cz_struct_backtest.csv',
        'output/energy_ledger_scenarios.csv','data/czcpmom_survey_history_extended.csv',
        'tests/fixtures/cleanup/MANIFEST.json']
    sources += ['tests/fixtures/cleanup/'+k for k in data['fixture_hashes']]
    sources += list(scenario_manifest['inputs']['source_hashes'])
    sources += [p.relative_to(ROOT).as_posix() for p in (ROOT/'data/announcement_sources').rglob('*') if p.is_file()]
    sources += [p.relative_to(ROOT).as_posix() for p in (OUT/'sources').rglob('*') if p.is_file()]
    manifest = dict(version=VERSION,baseline_commit=BASELINE_COMMIT,specification_commit=SPEC_COMMIT,
        completed_at=datetime.now(timezone.utc).isoformat(),python=platform.python_version(),
        **git_provenance(ROOT),
        source_hashes={p:sha(ROOT/p) for p in sorted(set(sources))},
        output_hashes={p.name:sha(p) for p in OUT.iterdir() if p.is_file() and p.name!='manifest.json'},
        selection='No tuning, no scenario outcome scoring, no promotion.',
        new_source_format='Web tool-extracted primary pages, retrieved 2026-09-09; not original historical HTTP bytes.',
        clock_rule='Source day end UTC; naive baseline release-eve clocks interpreted Europe/Prague.',
        limitations=['Frozen latest-vintage fixture history and publication rules are not historical input vintages.',
            'BASE January retrospective mapping is preserved as comparator, not certified strict.',
            'No complete household exposure, current bill panel, or embedded seasonal energy decomposition.',
            'Static basket contributions approximate, rather than reproduce, chain-linked official CPI.',
            'No addition indicates evidence failure, not a tested zero economic policy effect.'])
    if forecast_hash_before_scoring != sha(OUT/'forecasts.csv'):
        raise ValueError('Scoring changed a forecast')
    (OUT/'manifest.json').write_text(json.dumps(manifest,indent=2))
    print(json.dumps(summary,indent=2))


if __name__ == '__main__':
    main()
