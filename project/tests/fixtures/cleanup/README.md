# Frozen cleanup replay fixture

Eleven input CSVs (about 190 KB), copied/derived from the closed v1.6.1 audit
package, the frozen alcohol/tobacco series and the v2.3 weekly fuel snapshot.
Core frames remove wage, restore the compound lagged state and apply R4's
documented July-2026 import_l2=0.70 repair plus its interaction. No live source
was consulted. Their content hashes are in MANIFEST.json.

The production functions perform all forecast fitting, weight solving,
recombination, X13, warm/cold forests, direct horizons and bands. The source
loaders are replaced with these fixed frames solely for the refactor replay.
This is not a new real-time vintage dataset. Calendar and warm-error files
are read from the unchanged repository data/ folder.

expected_backtest.csv is the isolated unmodified R4 replay, 90 rows x 42
columns. SHA256 d0c2ce6584347c29449923ea1c66dd3a033d3f1dae045890b81545461f7c93d8.
It differs from supplied R4 BASE_RIDGE and PAST_FULL by at most 4.14e-8 pp
(frozen CSV representation); the cleaned replay matches this fixture byte
for byte. RUNTIME.json records the numerical libraries. X13 is external.

This is not an exact reproduction of every supplied R4 research column:
legacy residual QRF differs by up to 0.00859 pp, cold past-error forecasts
by 0.02996 pp and legacy bands by 0.01019 pp. These baseline-versus-supplied
differences precede the cleanup; their cause is unresolved. The before/after
cleanup check is exact for all columns.
