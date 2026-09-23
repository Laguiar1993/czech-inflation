# R11 supporting evidence

The main model comparison is `output/core_remainder/` and the user-facing
assessment is `docs/LATEST_MODEL_ASSESSMENT_2026-09-09.md`.

This directory records read-only diagnoses of the frozen R9/R10 forecasts.
No realized component error enters a new forecast. RMSEs of separate component
errors are not additive; the exact signed error identities and covariance terms
are supplied. Path figures are annual inflation unless labelled monthly.

Reproduce from the repository root with the numerical environment in
`requirements-r9-lock.txt`:

```text
python tools/r11_review/noncore_audit.py
python tools/r11_review/noncore_food_replay.py
python tools/r11_review/path_review.py
```

The second command requires the existing X-13 executable through `CZ_X13_PATH`.
The other diagnoses use the frozen inputs only. The scripts write to this
directory and preserve the original model forecasts. The path manifest hashes
every input and output CSV. Non-core manifests retain runtime/source paths as
audit provenance; numerical replay is portable even though those paths change
on another computer.

`noncore/NOTES.md` and `path/REVIEW.md` preserve the independent reviewers'
original findings. Their scratch locations and initial runtime describe that
first audit. The adapted scripts above and regenerated `validation.json` /
`manifest.json` describe the portable replay in this delivery. Legacy reference
commit labels identify the model originally audited, not the current repository
HEAD. Two source heads can differ while every specified input hash is identical.

The prior `large_surprise_diagnosis/release_attribution.csv` is frozen evidence
from the question that motivated this experiment; the non-core script compares
its independently reconstructed fixed contribution against it.
