# R35 single-series seasonal adjustment

## API and integration

```python
from tools.momentum_r35.seasonal import adjust_series
sa, diagnostic = adjust_series(levels[group], group, output_dir)
```

The directory must be new. The wrapper creates it, including missing parents, and
never reuses or removes it. An existing directory raises `FileExistsError`.
Evidence-write errors also propagate; a result without its archive is not usable.

Input is a real numeric pandas Series with a monthly `PeriodIndex`, in increasing
order, at least 96 observations, no duplicates/gaps/missing values, and strictly
positive finite CPI levels. No sorting, coercion of text to numbers, interpolation,
rescaling, or adjustment of the caller's Series occurs.

Success returns `status="ok"` and a positive finite Series with exactly the input
index and the supplied name. Input, executable, process, or result failures return
`status="unavailable"` and an all-NaN Series on the input index, with `reason`,
`failure_stage`, and flags. This is intentionally unsuitable for a calculation
requiring positive finite levels. There is no NSA, median, alternate-model, or
alternate-specification fallback.

The parent owns full-sample versus through-July calls, overlapping July M3
comparison, the fixed 0.5 pp endpoint-revision flag, and coverage/aggregation.
The wrapper does not read future months beyond the Series it receives.

## Fixed specification and shocks

Every group receives exactly one specification:

```text
transform { function=log }
automdl { }
outlier { types=(ao ls tc) }
x11 { mode=mult save=(d10 d11 d12 d13)
      appendfcst=no appendbcst=no savelog=all }
spectrum { logqs=yes robustsa=no print=all savelog=all }
check { }
```

The series block contains the supplied monthly index levels at 17-digit precision.
The executable runs once with the `-s` diagnostics switch and a 120-second timeout,
inside the new evidence directory. No shell is invoked; windows are hidden.
Default executable:
`C:/Users/luis_/x13as/x13as/x13as.exe`.
An explicit `CZ_X13_PATH` environment override is supported and hashed identically.
All otherwise unspecified X13 settings are the installed binary's defaults; its
hash and effective settings in `series.udg` identify those defaults. There is no
selection among specifications according to results.

D11 is the final seasonally adjusted series, not the smoothed D12 trend or
extreme-value-modified E2 series. The X11 `final` argument is deliberately omitted:
AO/LS/TC effects are estimated for seasonal-factor extraction and **retained in the
returned series**. A real-binary 25% one-off shock test checks retention.

No Easter or trading-day regressors are used for any group, including
`package_holidays` and `accommodation`. No robust pre-established holiday
specification was available. Moving-holiday contamination and travel-component
instability remain limitations, to be exposed through diagnostics and the parent's
endpoint check rather than addressed by outcome-dependent tuning.

Primary references: the installed Census manual
`C:/Users/luis_/x13as/x13as/docs/docX13AS.pdf`, X11 final argument (printed page
225, PDF page 234), spectrum diagnostics, and
[Census seasonal adjustment questions and answers](https://www.census.gov/data/software/x13as/seasonal-adjustment-questions-answers.html).
The public [reference manual](https://www2.census.gov/software/x-13arima-seats/x13as/unix-linux/documentation/docx13as.pdf)
also defines the X11 final argument and spectrum output.

## Diagnostics and archive

The JSON-safe diagnostic schema is `momentum_r35_x13/v1`. Principal keys:

- `status`: `ok` or `unavailable`; this is execution/data validity, not a claim
  that economic seasonality has been fully removed.
- `method`: `X13 log-autoARIMA AO/LS/TC X11 D11`.
- `quality_flags`: list of machine-readable warning strings.
- `quality_status`: `flagged`, `unavailable`, or
  `not_flagged_by_available_diagnostics`; never “validated.”
- `residual_seasonality`: QS statistics/p-values for original, residual, D11 and
  extreme-value-adjusted series where present; full/recent sample definitions;
  nonparametric D11 test indications; spectral results and interpretation.
- `effective_model`, `x11_quality_statistics`: archived model, outlier counts,
  filters, and raw X11 quality-statistic values. The raw `d11.f` fields retain
  X13's own units (including significance percentages), not converted p-values.
- `warnings`: source filename and complete warning/note blocks.
- `settings`, `binary_path`, `binary_sha256`, `binary_sha256_after`,
  `process_returncode`, `input` (n/start/end), `output_dir`, `command`.
- `reason` and `failure_stage` for unavailable results.

D11 QS p-values below 0.01 flag residual seasonality, whether in the full sample
(`qssadj`) or the last up to 96 observations (`qsssadj`). Significant D11 spectral
peaks and positive nonparametric D11 indications also flag it. The spectrum uses
unmodified D11 (`robustsa=no`) so retained shocks can affect diagnostics.
Missing/malformed QS evidence is explicitly flagged rather than treated as passing.
QS and spectral tests can disagree; both results are retained. Multiple tests are
descriptive diagnostics, not independent confirmations or calibrated probabilities.

Every successfully initialized run directory retains all X13 files, including
specification, output/error/log reports, user-defined diagnostics, D10/D11/D12/D13
when produced, and stdout/stderr. It also retains `input.csv`, `settings.json`,
`diagnostics.json`, and `manifest.json`. Invalid inputs cannot generate an X13
specification, but still receive settings and failure diagnostics.
`archive_files` hashes the files present before diagnostics were written;
`manifest.json.files` hashes **every file except the manifest itself**, including
diagnostics. The manifest is rehearsal evidence with `delivery_seal=false`.
The binary hash is checked again after the process returns.

Exit code zero alone is insufficient: this binary can print fatal errors and
return zero. The wrapper checks fatal report markers, convergence, D11 header,
each data row, exact dates/length/uniqueness, finiteness, and positivity.

## Verification and limitations

The focused suite has 35 checks, including actual installed-binary runs, failure
injection at the subprocess boundary, bad inputs/output, warning propagation,
directory immutability, and complete archive hashes. It was written before the
wrapper; the absent implementation was observed failing before implementation.

The deterministic synthetic series uses 180 months through August 2026:
`100 * exp(0.002*t + 0.08*sin(2*pi*t/12) + irregular)`, with fixed seed 173 and
normal irregular standard deviation 0.0005. Acceptance thresholds were fixed before
implementation: residual calendar-month amplitude below 2% of the original,
estimated log-trend slope within 0.00001 of 0.002, and retention of a 25% injected
shock within 0.002 in the adjusted shock/no-shock ratio.

A constant-growth trend with the same small irregular component checks M3/M6 mean
annualized rates within 0.05 pp of the known compounded annual rate and endpoint
rates within 0.25 pp. Exactly deterministic exponential growth, with or without a
perfectly repeating seasonal factor, makes this fixed autoARIMA/outlier procedure
fail with zero residual variance on installed X13 1.1 build 62. Tests explicitly
require unavailable results for those degenerate cases. No jitter is added to
production inputs and no alternate specification is tried. The synthetic tests
therefore support behavior on nondegenerate data; they do not establish universal
exactness or validate all 37 real CPI groups.

Synthetic QS can be nonsignificant while X13 reports a residual spectral peak;
the implementation deliberately retains that warning. Production group diagnostics,
coverage and endpoint sensitivity must be assessed by the parent rehearsal.
There is no model promotion claim and no connection to the preserved forecasts.

Run from the repository with the declared Python environment:

```text
python -B -m pytest tools/momentum_r35/test_seasonal.py -q -p no:cacheprovider \
  --basetemp=work/momentum_r35_sa_probe_tests_NEW
```

Choose a new test directory for each run. Initial raw runtime probes are under
`work/momentum_r35_sa_probe1` (fatal zero-variance cases) and
`work/momentum_r35_sa_probe2` (nondegenerate trend/seasonal/shock cases).
No canonical analysis or final export is created by this module.
