from pathlib import Path
from urllib.request import urlopen, Request
from datetime import datetime, timezone
import hashlib, json
root = Path('data/research_r19/eru_offers_20260915_complete')
url = 'https://eru.gov.cz/sites/default/files/obsah/prilohy/metodika-ipnc.pdf'
with urlopen(Request(url, headers={'User-Agent': 'Czech CPI research source validation'}), timeout=40) as response:
    raw = response.read()
with (root/'methodology.pdf').open('xb') as stream:
    stream.write(raw)
manifest = json.loads((root/'source_manifest.json').read_text())
manifest['methodology_pdf'] = dict(url=url, file='methodology.pdf', retrieved_at_utc=datetime.now(timezone.utc).isoformat(), sha256=hashlib.sha256(raw).hexdigest(), bytes=len(raw))
(root/'source_manifest.json').write_text(json.dumps(manifest,indent=2), encoding='utf-8')
print(len(raw))
