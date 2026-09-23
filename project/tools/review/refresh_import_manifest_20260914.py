"""Version the stale import manifest only after an exact offline source replay."""
from pathlib import Path
import hashlib
import json
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    from tools.r14b_imports import prepare
    source = ROOT/'data/research_r14b/imports'
    replay = ROOT/'output/audit_fixes_20260914/import_manifest_refresh'
    replay.mkdir(parents=True, exist_ok=False)
    old_path = source/'manifest.json'
    old_bytes = old_path.read_bytes()
    old = json.loads(old_bytes)
    fresh = prepare.run(replay)
    changes = {k for k in old['inputs'] if old['inputs'][k] != fresh['inputs'].get(k)}
    if set(old['inputs']) != set(fresh['inputs']) or changes != {'data/local_adapter.py'}:
        raise ValueError('Unexpected dependency changes: '+str(changes))
    expected = {**old, 'inputs':fresh['inputs']}
    if fresh != expected:
        raise ValueError('Replay differs beyond the documented adapter fingerprint')
    for name, expected_hash in old['outputs'].items():
        if sha(source/name) != expected_hash or sha(replay/name) != expected_hash:
            raise ValueError('Import replay changed output: '+name)
        if (source/name).read_bytes() != (replay/name).read_bytes():
            raise ValueError('Nonidentical output: '+name)
    backup = source/'manifest.pre_audit_20260914.json'
    with backup.open('xb') as f:
        f.write(old_bytes)
    receipt = dict(
        old_manifest=str(backup.relative_to(ROOT)), old_sha256=sha(backup),
        replay_manifest=str((replay/'manifest.json').relative_to(ROOT)),
        new_sha256=sha(replay/'manifest.json'),
        changed_inputs={k:dict(old=old['inputs'][k], new=fresh['inputs'][k]) for k in changes},
        byte_identical_outputs=old['outputs'],
        reason='Existing NFC total-plus-maturity double-count correction changed the adapter hash. '
               'Unmodified import preparer reproduced all five CSVs exactly offline. '
               'The strict runtime hash guard remains unchanged; this records a verified regeneration.')
    (replay/'refresh_receipt.json').write_text(json.dumps(receipt, indent=2)+'\n', encoding='utf-8')
    old_path.write_bytes((replay/'manifest.json').read_bytes())
    print(json.dumps(receipt, indent=2))


if __name__ == '__main__':
    main()
