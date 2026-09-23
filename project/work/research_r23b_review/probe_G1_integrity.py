"""Probe G1: what was reviewed is what ran. Manifest hashes, unmodified reuse of R23 code, file times."""
import hashlib
import json
from datetime import datetime
from pathlib import Path

from _common import ROOT, FINAL, EVAL, Report

R = Report('G1 integrity and pre-declaration')


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


m = json.loads((FINAL / 'manifest.json').read_text())
bad_in = [k for k, v in m['inputs'].items() if not (ROOT / k).exists() or sha(ROOT / k) != v]
bad_out = [k for k, v in m['outputs'].items() if sha(FINAL / k) != v]
R.check(f'fit manifest: all {len(m["inputs"])} input hashes match the files on disk now', not bad_in, str(bad_in[:5]))
R.check(f'fit manifest: all {len(m["outputs"])} output hashes match', not bad_out, str(bad_out[:5]))
listed = set(m['outputs']) | {'manifest.json'}
on_disk = {p.name for p in FINAL.iterdir() if p.is_file()}
R.check('every file in final/ is covered by the manifest', on_disk <= listed, str(sorted(on_disk - listed)))
for needed in ['data/cost_pressure_r23b.py', 'models/cost_pressure_r23b.py', 'models/cost_gaps_r23.py', 'data/cost_gaps_r23.py', 'tools/research_r23b/run.py',
               'docs/implementation/R23B_MEASUREMENT_REPAIR_SPEC_2026-09-17.md', 'output/research_r21/path_anchor/native_forecasts.csv', 'output/research_r15/states.json', 'r17_common.py']:
    R.check(f'manifest pins {needed}', needed in m['inputs'])

e = json.loads((EVAL / 'input_manifest.json').read_text())
bad_e = [k for k, v in e['inputs'].items() if not Path(k).exists() or sha(k) != v]
bad_eo = [k for k, v in e['outputs'].items() if sha(EVAL / k) != v]
R.check(f'evaluation manifest: all {len(e["inputs"])} input hashes match (absolute paths)', not bad_e, str(bad_e[:5]))
R.check(f'evaluation manifest: all {len(e["outputs"])} output hashes match', not bad_eo, str(bad_eo[:5]))
names = {Path(k).as_posix().split('cpi-independent/')[-1] for k in e['inputs']}
for needed in ['tools/research_r23b/evaluate.py', 'tools/research_r23/lead.py', 'tools/review/evaluate_r17.py', 'tools/review/evaluate_r15.py', 'tools/review/evaluate_r16.py',
               *['tools/path_diagnostics/' + f for f in ('gates.py', 'bootstrap.py', 'attribution.py', 'benchmarks.py', 'lead_baselines.py')]]:
    R.check(f'evaluation manifest pins {needed}', needed in names)
missing_pins = [p for p in ['output/research_r14b/attribution/actual_component_targets.csv', 'output/independent_path_frozen_inputs.csv', 'data/release_calendar_cz_cpi.csv', 'tools/path_diagnostics/__init__.py']
                if p not in names and (ROOT / p).exists()]
print('   evaluation inputs read by evaluate.py but not pinned by the evaluation manifest itself:', missing_pins)

# unmodified reuse of the R23 code and evaluator
r23 = json.loads((ROOT / 'output/research_r23/final/manifest.json').read_text())['inputs']
for k in ['data/cost_gaps_r23.py', 'models/cost_gaps_r23.py', 'r17_common.py']:
    R.check(f'{k} is byte-identical to the file the sealed R23 final run used', r23.get(k) == m['inputs'].get(k) == sha(ROOT / k))
r23e = json.loads((ROOT / 'output/research_r23/final/evaluation/input_manifest.json').read_text())['inputs']
r23e = {Path(k).as_posix().split('cpi-independent/')[-1]: v for k, v in r23e.items()}
e_by_name = {Path(k).as_posix().split('cpi-independent/')[-1]: v for k, v in e['inputs'].items()}
for k in ['tools/review/evaluate_r17.py', 'tools/review/evaluate_r15.py', 'tools/review/evaluate_r16.py', 'tools/research_r23/lead.py', 'data/cnb_mpr_cpi_quarterly.csv']:
    R.check(f'{k} identical to the one R23 was evaluated with', k in r23e and r23e[k] == e_by_name.get(k), f'in R23 manifest={k in r23e}')

# times: specification before code before outputs
stamp = lambda p: datetime.fromtimestamp(Path(p).stat().st_mtime)
spec = stamp(ROOT / 'docs/implementation/R23B_MEASUREMENT_REPAIR_SPEC_2026-09-17.md'); first_output = min(stamp(p) for p in FINAL.iterdir() if p.is_file())
code = {p: stamp(ROOT / p) for p in ['data/cost_pressure_r23b.py', 'models/cost_pressure_r23b.py', 'tools/research_r23b/run.py', 'tools/research_r23b/evaluate.py', 'tests/test_cost_pressure_r23b.py', 'tests/test_path_diagnostics.py',
                                     *['tools/path_diagnostics/' + f for f in ('gates.py', 'bootstrap.py', 'attribution.py', 'benchmarks.py', 'lead_baselines.py')]]}
print(f'   specification last written {spec:%H:%M:%S}; newest reviewed code file {max(code.values()):%H:%M:%S}; first fit output {first_output:%H:%M:%S}; evaluation manifest {stamp(EVAL / "input_manifest.json"):%H:%M:%S}')
R.check('specification file predates every fit output (and its hash is the one pinned in the manifest)', spec < first_output)
R.check('no reviewed code file was written after the first fit output', max(code.values()) < first_output, str({k: f'{v:%H:%M:%S}' for k, v in code.items() if v >= first_output}))
others = sorted(p.name for p in (ROOT / 'output/research_r23b').iterdir())
print('   directories under output/research_r23b:', others, '(a single run directory; earlier trial runs, if any, left no trace here)')
extra = sorted(p.name for p in (ROOT / 'tools/path_diagnostics').iterdir() if p.suffix == '.py' and p.name not in ('gates.py', 'bootstrap.py', 'attribution.py', 'benchmarks.py', 'lead_baselines.py', '__init__.py'))
print('   path_diagnostics files newer than the run and outside this review:', {n: f'{stamp(ROOT / "tools/path_diagnostics" / n):%H:%M:%S}' for n in extra})
# R23 sealed delivery untouched
d = json.loads((ROOT / 'output/research_r23/DELIVERY_MANIFEST.json').read_text())['files']
changed = [k for k, v in d.items() if not (ROOT / k).exists() or sha(ROOT / k) != v]
R.check(f'R23 sealed delivery: all {len(d)} hashed files unchanged on disk', not changed, str(changed[:5]))
R.done()
