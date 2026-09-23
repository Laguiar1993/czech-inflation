"""Fresh final source/output integrity checks; emits a portable delivery index."""
from pathlib import Path
from datetime import datetime,timezone
import csv,hashlib,json,re,subprocess,sys
ROOT=Path(__file__).resolve().parents[2]
HERE=Path(__file__).resolve().parent

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def dump(p,x):p.write_text(json.dumps(x,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')

def main():
    files=set();checks={};entries=0
    canonical=['output/research_r18_category_verified/manifest.json','output/research_r18_food/manifest.json',
        'output/research_r18_nowcast_final/manifest.json','output/research_r18/path_v2/manifest.json',
        'output/research_r18/path_v2/evaluation/input_manifest.json','output/research_r18/uncertainty_final/manifest.json']
    for name in canonical:
        path=ROOT/name;m=read(path);own=0;files.add(path)
        for group,base in [('inputs',ROOT),('outputs',path.parent)]:
            for rel,digest in m[group].items():
                p=base/rel
                assert sha(p)==digest,('hash_changed',str(p))
                files.add(p.resolve());own+=1;entries+=1
        checks[name]={'checked_hashes':own,'sha256':sha(path)}
    path=ROOT/'data/research_r18/categories/manifest.json';m=read(path);files.add(path)
    for name,meta in m['files'].items():
        p=path.parent/name
        assert sha(p)==meta['sha256'] and p.stat().st_size==meta['bytes']
        files.add(p)
    assert sha(ROOT/'tools/research_r18/category_inputs.py')==m['builder_sha256']
    with (ROOT/'data/research_r18/energy/source_register.csv').open(encoding='utf-8-sig',newline='') as f:
        energy=list(csv.DictReader(f))
    for row in energy:
        p=ROOT/row['file'];assert sha(p)==row['sha256'];files.add(p)
    path=ROOT/'work/research_r18_energy/output'
    for name,digest in read(path/'output_hashes.json').items():
        p=path/name;assert sha(p)==digest;files.add(p)
    energy_summary=read(path/'summary.json')
    assert energy_summary['scenario_rows']==60 and energy_summary['national_point'] is None
    assert sha(ROOT/'docs/implementation/R18_ENERGY_SPEC_2026-09-15.md')==energy_summary['spec_sha256']
    for name,digest in read(ROOT/'output/research_r18/presentation/manifest.json').items():
        p=ROOT/name;assert sha(p)==digest;files.add(p)
    old=subprocess.run([sys.executable,str(ROOT/'work/research_r17_review/verify_r17_final.py')],cwd=ROOT,capture_output=True,text=True)
    assert old.returncode==0,old.stdout+old.stderr
    old_result=json.loads(old.stdout)
    assert old_result['manifests']==14 and old_result['hash_entries']==1623
    log=(HERE/'tests_final.log').read_text(encoding='utf-8')
    assert re.search(r'\b523 passed\b',log) and not re.search(r'\d+ failed|ERROR collecting',log)
    behavior=read(HERE/'replay_behavior_receipt.json')
    assert sha(ROOT/behavior['artifact'])==behavior['sha256']
    assert behavior['report_rounds']==behavior['cutoff_rounds']==19
    review=read(ROOT/'work/research_r18_integration_review/integration_verification.json')
    assert review['models']==11 and review['origins']==90 and review['primary_keys_per_model']==969
    assert review['controls_exact_max']==0 and review['candidate_h0_max']==0
    # Include delivery sources, declarations and review evidence, excluding test
    # caches and obsolete output branches. Prior-model input dependencies above
    # are included explicitly, without traversing unrelated work directories.
    for folder in ['models','tests','docs/implementation']:
        files.update(p for p in (ROOT/folder).glob('*') if p.is_file() and 'r18' in p.name.lower())
    files.update(p for p in ROOT.glob('*r18*.py') if p.is_file())
    files.update(p for p in (ROOT/'tools/research_r18').glob('*.py'))
    for folder in ['data/research_r18','output/research_r18/presentation']:
        files.update(p for p in (ROOT/folder).rglob('*') if p.is_file())
    for folder in ['work/research_r18_category_review','work/research_r18_food','work/research_r18_nowcast_review',
        'work/research_r18_integration_review','work/research_r18_energy','work/research_r18_energy/output',
        'work/research_r18_final']:
        files.update(p for p in (ROOT/folder).glob('*') if p.is_file() and p.name!='final_integrity.json')
    docs=[ROOT/'R18_RESULTS_2026-09-15.md',ROOT/'R18_RUN_AND_FILE_MAP_2026-09-15.md']
    files.update(docs)
    delivery=ROOT/'output/research_r18/DELIVERY_MANIFEST.json'
    payload={}
    for p in sorted(files):
        p=p.resolve()
        # Old audit input maps occasionally use absolute names. Keep a relative
        # index here and fail rather than claiming out-of-repo files portable.
        rel=p.relative_to(ROOT).as_posix()
        payload[rel]=sha(p)
    dump(delivery,dict(created_at_utc=datetime.now(timezone.utc).isoformat(),
        status='research_replay_no_operating_promotion',canonical_manifests=canonical,
        entry_document='R18_RESULTS_2026-09-15.md',files=payload))
    receipt=dict(status='pass',verified_at_utc=datetime.now(timezone.utc).isoformat(),
        canonical=checks,canonical_hash_entries=entries,category_files=len(m['files']),energy_sources=len(energy),
        earlier_manifests=old_result['manifests'],earlier_hash_entries=old_result['hash_entries'],tests_passed=523,
        delivery_files=len(payload),delivery_sha256=sha(delivery),replay=behavior,
        scope='implementation and historical replay; no calibrated bands, prospective record or CNB dominance',
        verification_script_sha256=sha(Path(__file__)))
    dump(HERE/'final_integrity.json',receipt)
    for p in docs:
        for link in re.findall(r'\]\(([^)]+)\)',p.read_text(encoding='utf-8')):
            if link.startswith(('http://','https://','#')):continue
            assert (p.parent/link.split('#')[0]).is_file(),('broken_link',p.name,link)
    # Re-read every delivery byte after all writes, catching accidental binding
    # to a receipt that the verifier itself subsequently changes.
    for rel,digest in read(delivery)['files'].items():assert sha(ROOT/rel)==digest,rel
    print(json.dumps({k:receipt[k] for k in ['status','canonical_hash_entries','earlier_hash_entries','tests_passed','delivery_files']},indent=2))

if __name__=='__main__':main()
