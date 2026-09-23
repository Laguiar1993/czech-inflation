"""R29 cross-country producer prices: Eurostat industry (B-E36) domestic-market PPI, EU members except Czechia.

    python -m data.ppi_panel_r29 --output data/research_r29/ppi_panel_YYYYMMDD     (one frozen download)

Only the phase of upstream momentum (building or fading) is ever read from this panel, to condition a
persistence weight estimated on the R25 HICP-core panel. No level, forecast or Czech observation comes from it.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import urllib.request

import pandas as pd

from data.hicp_panel_r25 import MEMBERS, parse_jsonstat

ROOT = Path(__file__).resolve().parents[1]
URL = ('https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/sts_inppd_m'
       '?format=JSON&lang=EN&nace_r2=B-E36&s_adj=NSA&unit=I21')
SNAPSHOT = 'data/research_r29/ppi_panel_20260918'
PUBLICATION_DAY = 10          # month m is treated as published on day 10 of month m+2


def parse(payload):
    """The HICP parser expects freq/unit/coicop/geo/time; the PPI cube carries indic_bt/nace_r2/s_adj instead."""
    ids = list(payload['id'])
    fixed = [k for k in ids if k not in ('geo', 'time')]
    if any(payload['size'][ids.index(k)] != 1 for k in fixed):
        raise ValueError('Every dimension but geo and time must be a single category')
    relabelled = dict(payload); relabelled['id'] = ['freq', 'unit', 'coicop', 'geo', 'time']
    sizes = dict(zip(ids, payload['size'])); relabelled['size'] = [1, 1, 1, sizes['geo'], sizes['time']]
    dims = dict(payload['dimension']); relabelled['dimension'] = {'freq': {}, 'unit': {}, 'coicop': {}, 'geo': dims['geo'], 'time': dims['time']}
    return parse_jsonstat(relabelled)


def fetch(output):
    output = Path(output); output.mkdir(parents=True, exist_ok=False)
    request = urllib.request.Request(URL, headers={'User-Agent': 'Mozilla/5.0 (research snapshot of published producer price indices)', 'Accept': 'application/json'})
    raw = urllib.request.urlopen(request, timeout=180).read(); (output / 'sts_inppd_m_B-E36_NSA_I21.json').write_bytes(raw)
    payload = json.loads(raw); table = parse(payload); missing = [g for g in MEMBERS if g not in table]
    if missing:
        raise ValueError('Member states absent from the download: ' + ', '.join(missing))
    table[MEMBERS].to_csv(output / 'ppi_index.csv', index_label='period')
    sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
    (output / 'manifest.json').write_text(json.dumps(dict(
        retrieved_at_utc=datetime.now(timezone.utc).isoformat(), url=URL, eurostat_updated=payload.get('updated'), label=payload.get('label'),
        members=MEMBERS, excluded='CZ (the evaluation country) and every non-member or aggregate', first=str(table.index.min()), last=str(table.index.max()),
        coverage={g: int(table[g].notna().sum()) for g in MEMBERS},
        files={name: sha(output / name) for name in ('sts_inppd_m_B-E36_NSA_I21.json', 'ppi_index.csv')},
        availability_rule=f'month m treated as published on day {PUBLICATION_DAY} of month m+2'), indent=2), encoding='utf-8')
    return table[MEMBERS]


def load(folder=ROOT / SNAPSHOT):
    """Index levels by member state and their assumed publication stamps; hashes verified."""
    folder = Path(folder); manifest = json.loads((folder / 'manifest.json').read_text(encoding='utf-8'))
    for name, digest in manifest['files'].items():
        if hashlib.sha256((folder / name).read_bytes()).hexdigest() != digest:
            raise ValueError('Frozen panel file changed: ' + name)
    index = pd.read_csv(folder / 'ppi_index.csv', index_col=0, float_precision='round_trip'); index.index = pd.PeriodIndex(index.index, freq='M')
    if list(index.columns) != MEMBERS or 'CZ' in index.columns:
        raise ValueError('Exactly the declared member states are required, without CZ')
    published = pd.Series((index.index + 2).to_timestamp() + pd.Timedelta(days=PUBLICATION_DAY - 1), index=index.index)
    return index, published, manifest


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument('--output', type=Path, required=True); args = parser.parse_args()
    frozen = fetch(args.output)
    print(frozen.notna().sum().to_string()); print('first', frozen.index.min(), 'last', frozen.index.max())
