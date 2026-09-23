"""Read-only diagnosis of the Bloomberg core/regulated mapping and latest values."""
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
from xbbg import blp
from tools.market_data.probe_bloomberg_candidates import instrument_search,REFERENCE_FIELDS

out=Path('output/bloomberg_core_check_r33')
out.mkdir(exist_ok=False)
(out/'.gitattributes').write_text('* -text\n',encoding='utf-8')
result={'retrieved_at':datetime.now(timezone.utc).isoformat(),'purpose':'Verify latest reference values and daily/native histories; does not alter model inputs.','tickers':{}}
for ticker in ['CZCIXM Index','CZCIRM Index']:
 item={}
 try:
  ref=blp.bdp(ticker,REFERENCE_FIELDS+['PX_LAST'],timeout=20000)
  item['reference']=ref.to_dict(orient='index')
  raw=blp.bdh(ticker,'PX_LAST',start_date='2026-07-01',end_date='2026-09-22',timeout=20000,periodicitySelection='DAILY')
  item['daily_history']=raw.reset_index().to_json(orient='split',date_format='iso')
 except Exception as e:item['error']=str(e)
 result['tickers'][ticker]=item
result['search']=instrument_search(['Czech Inflation Overall Items','Czech Inflation Regulated'],max_results=8)
(out/'diagnosis.json').write_text(json.dumps(result,indent=2,default=str),encoding='utf-8')
(out/'manifest.json').write_text(json.dumps({'outputs':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in out.iterdir() if p.is_file()}},indent=2),encoding='utf-8')
print(json.dumps(result,default=str))
