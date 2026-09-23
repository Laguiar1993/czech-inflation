"""R25 cross-country panel: Eurostat HICP excluding energy, food, alcohol and tobacco, EU members except Czechia.

    python -m data.hicp_panel_r25 --output data/research_r25/hicp_core_panel_YYYYMMDD     (one frozen download)

Only a persistence parameter is ever borrowed from this panel. No level, forecast or Czech observation
comes from it.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import urllib.request

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
URL = ('https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/prc_hicp_midx'
       '?format=JSON&lang=EN&coicop=TOT_X_NRG_FOOD&unit=I15')
MEMBERS = ['AT', 'BE', 'BG', 'CY', 'DE', 'DK', 'EE', 'EL', 'ES', 'FI', 'FR', 'HR', 'HU', 'IE', 'IT', 'LT', 'LU', 'LV', 'MT', 'NL', 'PL', 'PT', 'RO',
           'SE', 'SI', 'SK']            # the 27 member states without CZ
SNAPSHOT = 'data/research_r25/hicp_core_panel_20260917'


def parse_jsonstat(payload):
    """Eurostat JSON-stat 2.0 -> index levels, monthly periods by geo."""
    ids, sizes = payload['id'], payload['size']
    if sorted(ids) != sorted(['freq', 'unit', 'coicop', 'geo', 'time']) or any(sizes[ids.index(k)] != 1 for k in ('freq', 'unit', 'coicop')):
        raise ValueError('Unexpected Eurostat cube layout')
    geo = payload['dimension']['geo']['category']['index']; time = payload['dimension']['time']['category']['index']
    stride = {name: int(np.prod(sizes[i + 1:])) for i, name in enumerate(ids)}
    table = pd.DataFrame(np.nan, index=pd.PeriodIndex(sorted(time, key=time.get), freq='M'), columns=sorted(geo, key=geo.get))
    for g, gi in geo.items():
        for t, ti in time.items():
            value = payload['value'].get(str(gi * stride['geo'] + ti * stride['time']))
            if value is not None:
                table.loc[pd.Period(t, 'M'), g] = float(value)
    return table


def fetch(output):
    output = Path(output); output.mkdir(parents=True, exist_ok=False)
    request = urllib.request.Request(URL, headers={'User-Agent': 'Mozilla/5.0 (research snapshot of published HICP indices)', 'Accept': 'application/json'})
    raw = urllib.request.urlopen(request, timeout=180).read(); (output / 'prc_hicp_midx_TOT_X_NRG_FOOD_I15.json').write_bytes(raw)
    payload = json.loads(raw); table = parse_jsonstat(payload); missing = [g for g in MEMBERS if g not in table]
    if missing:
        raise ValueError('Member states absent from the download: ' + ', '.join(missing))
    table[MEMBERS].to_csv(output / 'hicp_core_index.csv', index_label='period')
    sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
    (output / 'manifest.json').write_text(json.dumps(dict(
        retrieved_at_utc=datetime.now(timezone.utc).isoformat(), url=URL, eurostat_updated=payload.get('updated'), label=payload.get('label'),
        members=MEMBERS, excluded='CZ (the evaluation country) and every non-member or aggregate', first=str(table.index.min()), last=str(table.index.max()),
        files={name: sha(output / name) for name in ('prc_hicp_midx_TOT_X_NRG_FOOD_I15.json', 'hicp_core_index.csv')},
        availability_rule='month m treated as published on day 20 of month m+1'), indent=2), encoding='utf-8')
    return table[MEMBERS]


def load(folder=ROOT / SNAPSHOT):
    """Monthly percentage rates by member state and their assumed publication stamps; hashes verified."""
    folder = Path(folder); manifest = json.loads((folder / 'manifest.json').read_text(encoding='utf-8'))
    for name, digest in manifest['files'].items():
        if hashlib.sha256((folder / name).read_bytes()).hexdigest() != digest:
            raise ValueError('Frozen panel file changed: ' + name)
    index = pd.read_csv(folder / 'hicp_core_index.csv', index_col=0, float_precision='round_trip'); index.index = pd.PeriodIndex(index.index, freq='M')
    if list(index.columns) != MEMBERS or 'CZ' in index.columns:
        raise ValueError('Exactly the declared member states are required, without CZ')
    rates = 100 * (index / index.shift(1) - 1)
    published = pd.Series((rates.index + 1).to_timestamp() + pd.Timedelta(days=19), index=rates.index)
    return rates, published, manifest


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument('--output', type=Path, required=True); args = parser.parse_args()
    frozen = fetch(args.output)
    print(frozen.notna().sum().to_string()); print('first', frozen.index.min(), 'last', frozen.index.max())
