"""Shared bootstrap for the R23B review probes. Read-only with respect to the repository."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
FINAL = ROOT / 'output' / 'research_r23b' / 'final'
EVAL = FINAL / 'evaluation'
HERE = Path(__file__).resolve().parent


class Report:
    """Collects PASS/FAIL lines so every probe ends with a machine-checkable tally."""
    def __init__(self, name):
        self.name = name; self.passed = 0; self.failed = 0; self.notes = []
        print(f'##### {name}')

    def check(self, label, ok, detail=''):
        ok = bool(ok)
        self.passed += ok; self.failed += (not ok)
        print(f'[{"PASS" if ok else "FAIL"}] {label}' + (f' :: {detail}' if detail else ''))
        return ok

    def note(self, text):
        self.notes.append(text); print(f'[NOTE] {text}')

    def done(self):
        print(f'##### {self.name}: {self.passed} passed, {self.failed} failed, {len(self.notes)} notes')
