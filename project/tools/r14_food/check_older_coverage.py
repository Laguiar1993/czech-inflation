"""Read-only source audit for a separately declared food follow-up; no fitting."""
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime,timezone
import hashlib,json,urllib.request

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'data/research_r14/food/coverage_extension'
URLS={
 'czso_cpi_1995_2025.csv':'https://csu.gov.cz/docs/107508/cfcf22e1-06b0-92a6-cf41-fb554acc545a/010022-25data011326.csv?version=1.0',
 'czso_cpi_schema.json':'https://csu.gov.cz/docs/107508/a09a9e70-51a2-a4ad-6c9a-6f95c6ba18cf/010022-25schema011326.json?version=1.0',
 'czso_cpi_documentation.docx':'https://csu.gov.cz/docs/107508/808c2eaa-5f53-9fc8-2b5c-dbf07f500e1d/010022-23dds.docx?version=1.0'}

def fetch(item):
    name,url=item
    request=urllib.request.Request(url,headers={'User-Agent':'Czech-food-research-source-audit/1.0'})
    with urllib.request.urlopen(request,timeout=90) as response:data=response.read()
    (OUT/name).write_bytes(data)
    return dict(file=name,url=url,bytes=len(data),sha256=hashlib.sha256(data).hexdigest())

if __name__=='__main__':
    OUT.mkdir(parents=True,exist_ok=True)
    with ThreadPoolExecutor(max_workers=3) as pool:records=list(pool.map(fetch,URLS.items()))
    (OUT/'source_manifest.json').write_text(json.dumps(dict(retrieved_at=datetime.now(timezone.utc).isoformat(),sources=records),indent=2))
    print(json.dumps(records,indent=2))
