from pathlib import Path
from urllib.request import Request,urlopen
from datetime import datetime,timezone
import hashlib,json
root=Path('data/research_r19/eru_offers_20260915_complete');root.mkdir(parents=True,exist_ok=False)
urls={'electricity':'https://eru.gov.cz/sites/default/files/obsah/prilohy/elektrina_4.csv','gas':'https://eru.gov.cz/sites/default/files/obsah/prilohy/plyn_3.csv','methodology':'https://eru.gov.cz/metodika-stanoveni-ipnc','overview':'https://eru.gov.cz/ipnc'}
records={}
for name,url in urls.items():
 with urlopen(Request(url,headers={'User-Agent':'Czech CPI research source validation'}),timeout=40) as response:raw=response.read()
 path=root/(name+('.csv' if name in ['electricity','gas'] else '.html'))
 path.write_bytes(raw)
 records[name]={'url':url,'file':path.name,'retrieved_at_utc':datetime.now(timezone.utc).isoformat(),'sha256':hashlib.sha256(raw).hexdigest(),'bytes':len(raw)}
 (root/'source_manifest.json').write_text(json.dumps(records,indent=2),encoding='utf-8')
 print(name,len(raw),flush=True)
