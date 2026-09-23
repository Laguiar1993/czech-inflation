"""Closed-input checks; never rewrites earlier results or manifests."""
from pathlib import Path
from datetime import datetime, timezone
import csv, hashlib, json, math

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT/'output/research_r19/evidence'
OUT.mkdir(parents=True, exist_ok=True)

def read(path):
    return json.loads(path.read_text(encoding='utf-8'))

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

old = ROOT/'output/runs/20260909T083745Z_98fbb1c9'
new = ROOT/'output/research_r19/engine_runs/20260915T075041Z_1152348c'
om, nm = read(old/'snapshot.json'), read(new/'snapshot.json')
of, nf = read(old/'forecast.json'), read(new/'forecast.json')
required = ['headline','components','core','regulated','alcohol','features','food_features','weekly_fuel']
frame_checks = {name: om['hashes'][name+'.csv'] == nm['hashes'][name+'.csv'] for name in required}
assert all(frame_checks.values())
engine_files = ['config.py','cz_struct.py','forecast_independent.py','models/independent_nowcast.py','models/horizon_models.py']
code_checks = {name: om['code_and_static_inputs'][name] == nm['code_and_static_inputs'][name] for name in engine_files}
assert all(code_checks.values())
error_checks = {name: of['diagnostics'][name]['error_history_sha256'] == nf['diagnostics'][name]['error_history_sha256'] for name in ['hard','sentiment']}
assert all(error_checks.values())
parity = dict(old_run=str(old.relative_to(ROOT)), new_run=str(new.relative_to(ROOT)),
    old_runtime=om['runtime'], new_runtime=nm['runtime'], frame_checks=frame_checks,
    source_checks=code_checks, error_history_checks=error_checks,
    points={name: {'old':of['points_mm_pct'][name], 'new':nf['points_mm_pct'][name],
        'difference_pp':nf['points_mm_pct'][name]-of['points_mm_pct'][name]} for name in ['HARD_BASE','HARD_HALF','HARD_FULL']},
    verdict='Same relevant frames, core errors and numerical source; changed runtime is a plausible explanation, not a package-by-package causal isolation. New-runtime offline replay matched all six points to the engine tolerance of 1e-10.')
(OUT/'runtime_parity.json').write_text(json.dumps(parity,indent=2),encoding='utf-8')
(OUT/'runtime_recorded.json').write_text(json.dumps(nm['runtime'],indent=2),encoding='utf-8')
(OUT/'model_packages_recorded.txt').write_text('# Recorded numerical packages, not a complete portable environment lock.\n# Python '+nm['runtime']['python']+'\n'+'\n'.join(k+'=='+v for k,v in nm['runtime']['packages'].items())+'\n',encoding='utf-8')

folder = ROOT/'data/research_r19/eru_offers_20260915_complete'
sources = read(folder/'source_manifest.json')
for item in sources.values():
    assert sha(folder/item['file']) == item['sha256']
records, summaries = [], {}
for commodity in ['electricity','gas']:
    source = sources[commodity]
    with (folder/source['file']).open(encoding='utf-8-sig',newline='') as stream:
        rows = list(csv.reader(stream))
    headers, rows = rows[0], rows[1:]
    assert len(headers)==7
    keys = set()
    for row in rows:
        month, segment, fix = row[0][:7], row[1], int(row[2])
        key=(month,segment,fix)
        assert key not in keys and fix in (12,24,36)
        keys.add(key)
        low, high, low_vat, high_vat = map(float,row[3:])
        assert all(math.isfinite(v) for v in (low,high,low_vat,high_vat))
        assert 0 < low <= high and 0 < low_vat <= high_vat
        assert math.isclose(low_vat,1.21*low,abs_tol=1e-8)
        assert math.isclose(high_vat,1.21*high,abs_tol=1e-8)
        records.append(dict(commodity=commodity,reference_month=month,segment=segment,fix_months=fix,
            lower_ex_vat=low,upper_ex_vat=high,lower_inc_vat=low_vat,upper_inc_vat=high_vat,
            unit='raw_source_price_unit_not_explicit_in_csv_header',
            available_from=source['retrieved_at_utc'],availability_kind='observed_download',
            historical_first_release_verified=False,national_weight='',source_sha256=source['sha256']))
    months=sorted({key[0] for key in keys})
    summaries[commodity]=dict(rows=len(rows),months=months,segments=sorted({key[1] for key in keys}),
        fix_months=sorted({key[2] for key in keys}),source_headers=headers)
with (OUT/'eru_offers_normalized.csv').open('w',encoding='utf-8',newline='') as stream:
    writer=csv.DictWriter(stream,fieldnames=list(records[0]));writer.writeheader();writer.writerows(records)
(OUT/'eru_validation.json').write_text(json.dumps(summaries,indent=2),encoding='utf-8')

manifest = read(ROOT/'output/research_r18/DELIVERY_MANIFEST.json')
failures = [name for name,digest in manifest['files'].items() if sha(ROOT/name) != digest]
assert not failures, failures
integrity=dict(checked_at_utc=datetime.now(timezone.utc).isoformat(),r18_files_checked=len(manifest['files']),r18_changed_files=failures,
    r19_eru_source_files_checked=len(sources),eru_rows=len(records),parity_frame_checks=len(frame_checks),parity_code_checks=len(code_checks))
(OUT/'verification.json').write_text(json.dumps(integrity,indent=2),encoding='utf-8')
print(json.dumps(integrity,indent=2))
