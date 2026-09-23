"""C (continued). Are the frozen baseline modules the ones older rounds recorded, and are the R24 outputs the ones
the run and the evaluation recorded? Hash comparisons only; nothing is written besides this probe's stdout."""
import hashlib
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
os.chdir(ROOT)
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
targets = ['models/food_stable_r14b.py', 'models/food_path_r14.py']
now = {t: sha(t) for t in targets}
print('current sha256:')
for t in targets:
    print('  ', t, now[t])

hits = set()


def walk(obj, source):
    if isinstance(obj, dict):
        for k, v in obj.items():
            key = str(k).replace(chr(92), '/')
            match = [t for t in targets if key.endswith(t)]
            if isinstance(v, str) and match:
                hits.add((source, match[0], v == now[match[0]]))
            else:
                walk(v, source)
    elif isinstance(obj, list):
        for v in obj:
            walk(v, source)


for dirpath, dirs, files in os.walk('output'):
    dirs[:] = [d for d in dirs if 'pytest' not in d]
    for f in files:
        if f.endswith('manifest.json'):
            p = Path(dirpath) / f
            try:
                walk(json.loads(p.read_text(encoding='utf-8')), p.as_posix())
            except Exception:      # noqa: BLE001 - unreadable manifests are simply skipped
                continue
print('\nolder manifests recording these files (manifest, file, recorded hash equals current):')
for h in sorted(hits):
    print('  ', h)
print('all equal:', all(h[2] for h in hits), ' n =', len(hits))

run = Path('output/research_r24/final')
m = json.loads((run / 'manifest.json').read_text())
print('\nR24 run manifest: %d inputs, changed since the run: %s' % (len(m['inputs']), [k for k, v in m['inputs'].items() if sha(k) != v]))
print('R24 run manifest: %d outputs, changed since the run: %s' % (len(m['outputs']), [k for k, v in m['outputs'].items() if sha(run / k) != v]))
print('   code recorded as input:', [k for k in m['inputs'] if k.endswith('.py')])
e = json.loads((run / 'evaluation/input_manifest.json').read_text())
print('R24 evaluation manifest: %d inputs, changed: %s, missing: %s' % (len(e['inputs']), [k for k, v in e['inputs'].items() if Path(k).exists() and sha(k) != v], [k for k in e['inputs'] if not Path(k).exists()]))
print('R24 evaluation manifest: %d outputs, changed: %s' % (len(e['outputs']), [k for k, v in e['outputs'].items() if sha(run / 'evaluation' / k) != v]))
print('   evaluation code recorded:', sorted(Path(k).name for k in e['inputs'] if k.endswith('.py')))
listed = set(e['outputs']); present = {p.name for p in (run / 'evaluation').iterdir() if p.is_file()} - {'input_manifest.json'}
print('   evaluation files not in its manifest:', sorted(present - listed))
