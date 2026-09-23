"""Download the primary evidence used in the R14 food design; no model fits."""
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import json
import urllib.request

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'data/research_r14/food'
SOURCES={
    'ecb_wp1168.pdf':'https://www.ecb.europa.eu/pub/pdf/scpwps/ecbwp1168.pdf',
    'cnb_food_prices_2020.html':'https://www.cnb.cz/en/monetary-policy/inflation-reports/boxes-and-annexes-contained-in-inflation-reports/What-drives-food-prices/',
    'ecb_food_pipeline_2024.html':'https://www.ecb.europa.eu/press/economic-bulletin/focus/2024/html/ecb.ebbox202402_04~9b36bced23.en.html',
    'worldbank_commodity_data.html':'https://www.worldbank.org/en/research/commodity-markets',
}

def fetch(item):
    name,url=item
    req=urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0 (research source archival)'})
    try:
        with urllib.request.urlopen(req,timeout=30) as response:
            payload=response.read(); status=response.status; resolved=response.url
        (OUT/name).write_bytes(payload)
        return dict(file=name,url=url,resolved_url=resolved,status=status,bytes=len(payload),
                    sha256=hashlib.sha256(payload).hexdigest())
    except Exception as exc:
        return dict(file=name,url=url,error=f'{type(exc).__name__}: {exc}')

if __name__=='__main__':
    OUT.mkdir(parents=True,exist_ok=True)
    with ThreadPoolExecutor(max_workers=4) as pool:
        records=list(pool.map(fetch,SOURCES.items()))
    manifest=dict(retrieved_at_utc=datetime.now(timezone.utc).isoformat(),purpose='Primary evidence; no model estimation',sources=records)
    (OUT/'source_manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    print(json.dumps(records,indent=2))
