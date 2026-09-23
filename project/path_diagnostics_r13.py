"""Rebuild descriptive CNB comparisons from frozen forecasts; no model fits."""
from __future__ import annotations

import argparse
from contextlib import ExitStack
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import tempfile
from unittest.mock import patch

import pandas as pd

from evaluation.path_diagnostics_r13 import prepare_rows, summarise, revision_rows

ROOT = Path(__file__).resolve().parent
OUTPUT = ROOT/'output/research_r13/path_diagnostics'
SOURCE = ROOT/'output/research_r12/path/cnb_quarters.csv'
FILES = ('rows.csv','summary.csv','revisions.csv','coverage.csv')


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def source_hashes():
    names = ['path_diagnostics_r13.py','evaluation/path_diagnostics_r13.py',
             'docs/implementation/R13_PATH_DIAGNOSTIC_SPEC.md',
             'output/research_r12/path/cnb_quarters.csv',
             'output/research_r12/path/manifest.json',
             'data/cnb_mpr_cpi_quarterly.csv']
    return {name:digest(ROOT/name) for name in names}


def generate(folder):
    before = source_hashes()
    original = json.loads((ROOT/'output/research_r12/path/manifest.json').read_text())
    candidates = [v for key,v in original.items() if isinstance(v,dict) and 'cnb_quarters.csv' in v]
    if len(candidates) != 1 or candidates[0]['cnb_quarters.csv'] != digest(SOURCE):
        raise AssertionError('frozen R12 CNB payload does not match manifest')
    rows = prepare_rows(pd.read_csv(SOURCE,float_precision='round_trip'))
    summary = summarise(rows)
    revisions = revision_rows(rows)
    coverage = rows[['report_date','quarter','origin','as_of_utc','report_clock_utc',
                     'quarters_ahead','complete','forecast_available','scored','age_days']].copy()
    folder.mkdir(parents=True,exist_ok=True)
    for name,frame in zip(FILES,(rows,summary,revisions,coverage)):
        frame.to_csv(folder/name,index=False)
    if before != source_hashes():
        raise AssertionError('input/code changed during diagnostic generation')
    return before


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--verify',action='store_true')
    parser.add_argument('--output-dir',type=Path,default=OUTPUT)
    args = parser.parse_args()
    output = args.output_dir
    if args.verify:
        manifest = json.loads((output/'manifest.json').read_text())
        if source_hashes() != manifest['source_hashes']:
            raise AssertionError('source hash mismatch')
        with tempfile.TemporaryDirectory(prefix='r13_cnb_') as temporary, ExitStack() as stack:
            for method in ('socket.socket','socket.create_connection','requests.sessions.Session.request','duckdb.connect'):
                stack.enter_context(patch(method,side_effect=AssertionError('offline diagnostic attempted external access')))
            folder = Path(temporary)
            generate(folder)
            for name in FILES:
                if digest(folder/name) != manifest['output_hashes'][name] or digest(output/name) != manifest['output_hashes'][name]:
                    raise AssertionError(f'deterministic diagnostic mismatch: {name}')
        print(json.dumps(dict(status='passed',files=len(FILES),refits=0,scope='frozen descriptive diagnostic'),indent=2))
    else:
        hashes = generate(output)
        manifest = dict(source_hashes=hashes,output_hashes={name:digest(output/name) for name in FILES},
                        specification_commit='b84835a',created_at=datetime.now(timezone.utc).isoformat(),
                        interpretation='Agreement and common errors are descriptive, not identified exogenous shocks.')
        (output/'manifest.json').write_text(json.dumps(manifest,indent=2))
        summary = pd.read_csv(output/'summary.csv')
        columns = ['panel','horizon','n_scored','n_unique_quarters','model_rmse','cnb_rmse',
                   'disagreement_rmse','shared_large_miss','age_days_median']
        print(summary.loc[summary.panel.isin(['all_reports','recent_reports']),columns].to_string(index=False))


if __name__ == '__main__':
    main()
