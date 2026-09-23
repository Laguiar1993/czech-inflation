"""Create-only R34 context exports from local, verified research archives."""
import argparse
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
from . import analysis,sources

ROOT=sources.ROOT
HERE=Path(__file__).resolve().parent


def assemble(*,as_of,bundle=None,record=None,ledger_input=None):
    decision=analysis.clock(as_of)
    historical=sources.load_historical_errors()
    seasonal=analysis.seasonal_context(bundle or sources.DEFAULT_BUNDLE,record or sources.DEFAULT_RECORD)
    if decision < analysis.clock(seasonal['completed_at']):
        raise ValueError('as_of predates completion of the recorded forecast')
    ranges=analysis.empirical_ranges(historical['errors'],as_of=as_of,release_calendar=historical['release_calendar'])
    eligible={r['origin'] for r in ranges['samples']['full']['0']['observations']}
    disagreement=sources.historical_disagreement(historical['nowcast_rows'],eligible)
    points=seasonal['recorded_alternative_points_mm']
    disagreement['current']=dict(target=seasonal['target'],as_of=seasonal['as_of'],points_mm=points,
        min_mm=min(points.values()),max_mm=max(points.values()),spread_pp=max(points.values())-min(points.values()),
        definition='Recorded HARD_BASE/HARD_HALF/HARD_FULL challenger disagreement, not uncertainty or an error band; no model promotion')
    ledger=None
    if ledger_input is not None:
        ledger=analysis.base_effect_ledger(ledger_input['history_mm'],ledger_input['forecast_mm'])
        if ledger[0]['month']!=seasonal['target'] or abs(ledger[0]['mm']-seasonal['point_mm'])>1e-12:
            raise ValueError('Ledger h0 must preserve the recorded target and HARD_BASE point')
    inputs={**historical['inputs'],**seasonal.pop('inputs')}
    return dict(schema_version='forecast_context_r34/v1',as_of=decision.isoformat(),
                empirical_ranges=ranges,seasonal=seasonal,model_disagreement=disagreement,
                base_effect_ledger=ledger,
                base_effect_definition='Exact removal-then-add: first divide by the outgoing gross monthly factor, then multiply by the incoming factor; effects are percentage points, not log points',
                ledger_status='provided' if ledger else 'Parent current path not supplied; use analysis.base_effect_ledger(history_mm,forecast_mm)',
                sources=dict(inputs=inputs,support_definition=historical['support_definition'],truth_definition=historical['truth_definition'],
                             ready_false_origins_retained=historical['ready_false_origins'],
                             readiness_note='Six archived December rows have ready=False. All remain in the fixed 90-origin historical scoring roster; no readiness-based selection is applied.'),
                limitations='Research explanation sidecar. No data pull, fit, backtest, model selection, promotion, or calibrated prospective probability is performed.')


def build(output,*,as_of,bundle=None,record=None,ledger_input=None):
    out=Path(output).resolve()
    if not out.is_relative_to(ROOT): raise ValueError('Output must be within repository')
    if out.exists(): raise FileExistsError('Context exports are create-only; choose a new output directory')
    context=assemble(as_of=as_of,bundle=bundle,record=record,ledger_input=ledger_input)
    encoded=json.dumps(context,ensure_ascii=False,allow_nan=False,indent=2)+'\n'
    code={sources.input_key(p):sources.digest(p.read_bytes()) for p in HERE.iterdir() if p.is_file()}
    payloads={'.gitattributes':b'* -text\n','forecast_context.json':encoded.encode('utf-8')}
    manifest=dict(schema_version='forecast_context_r34/artifact-v1',built_at_utc=datetime.now(timezone.utc).isoformat(),
                  as_of=context['as_of'],delivery_seal=False,inputs=context['sources']['inputs'],code=code,
                  outputs={name:sources.digest(raw) for name,raw in payloads.items()})
    manifest_bytes=(json.dumps(manifest,indent=2,allow_nan=False)+'\n').encode('utf-8')
    out.mkdir(parents=True,exist_ok=False)
    for name,raw in payloads.items(): (out/name).write_bytes(raw)
    (out/'manifest.json').write_bytes(manifest_bytes)
    return dict(output=str(out/'forecast_context.json'),manifest=str(out/'manifest.json'),schema_version=context['schema_version'])


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--as-of',required=True)
    parser.add_argument('--bundle',type=Path,default=sources.DEFAULT_BUNDLE)
    parser.add_argument('--record',type=Path,default=sources.DEFAULT_RECORD)
    parser.add_argument('--ledger-input',type=Path,help='JSON with history_mm and forecast_mm month-to-rate mappings')
    args=parser.parse_args()
    ledger=json.loads(args.ledger_input.read_text(encoding='utf-8-sig')) if args.ledger_input else None
    print(json.dumps(build(args.output,as_of=args.as_of,bundle=args.bundle,record=args.record,ledger_input=ledger)))


if __name__=='__main__':main()
