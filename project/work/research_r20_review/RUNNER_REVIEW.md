# R20 runner review — 15 September 2026

Assessment: no remaining material finding in the reviewed runner and recording boundary after the fixes below. This review supports the historical integration and replay result. It does not certify refreshed live sources or establish a new September forecast.

## Scope

Reviewed `tools/current_path/run.py` against `docs/implementation/R20_CURRENT_PATH_PLAN_2026-09-15.md`, including its use of `forecast_independent.py` snapshot, runtime and source checks. Also reviewed the new `tools/current_path/record.py` handoff and clock validation. Shared model arithmetic and 90-origin parity were assigned to a separate reviewer and are outside this review.

The reviewer added only `tests/test_r20_runner_review.py` and this report. Implementation corrections were made by the parent agent.

## Findings and resolution

1. **Important — readiness accepted a level whose monthly rate was unavailable.** The original `input_freshness` checked the latest finite, released level. A July-origin capture on 4 August reported food ready with a June level even when the May level or May publication timestamp was missing. The food model consumes differences, so the June rate was unavailable. Two regression cases failed on the original implementation. The corrected code at `tools/current_path/run.py:98` requires consecutive finite, released level endpoints and reports both the level and rate edges. Both regression cases now pass.

2. **Important — input hashes did not identify the parsed bytes under concurrent replacement.** The original loader hashed all input files, then reopened each file for parsing. Replacing the level file immediately before its first parse returned `agri4=999` with the manifest digest for the original `agri4=10`. The regression failed on the original implementation. The corrected loader at `tools/current_path/run.py:64` reads each file into bytes once, verifies those bytes, and parses those same bytes through `BytesIO`. The mutation regression now returns the verified original value and passes.

3. **Important — recording timestamps needed explicit validation.** The initial handoff used raw `pd.Timestamp` comparisons and a time-difference freshness check. A `NaT` completion defeats both checks; capture/decision ordering was also unchecked. The corrected boundary at `tools/current_path/record.py:47` requires valid timezone-aware completion, capture and decision timestamps, checks chronology, and requires live decision time to equal capture time. Seven cases cover missing/naive timestamps, future or premature completion, and mismatched live decision time. Two controls verify valid prospective and historical handoffs through the validation boundary. The underlying archive-writing calls are stubbed in these clock tests, so these controls do not constitute prospective issuance.

## Verification evidence

- Original runner suite: **7 passed**.
- Initial independent regression suite: **3 failed, 3 passed**. The three failures were the two missing food endpoints and input hash/parse replacement described above; the passing cases checked immutable snapshot directories, runtime mismatch rejection, and frame-byte mutation rejection.
- Final command: `python -m pytest -q -p no:cacheprovider --basetemp work/research_r20_review/pytest_final_01 tests/test_r20_runner_review.py tests/test_current_path_runner.py`.
- Final result: **22 passed in 1.72 seconds**; no remaining failing review cases.
- Python runtime: `C:/Users/luis_/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe` with `PYTHONPATH=work/audit_fixes_20260914/runtime_deps;../pythonlibs`. Initial sandbox execution could not read a local dependency or use the default pytest temporary directory; the successful offline runs used approved local access and a dedicated review temporary directory.
- Independently replayed `output/research_r20/runs_final/20260915T082214Z_e1d40da2` with `requests.sessions.Session.request` and `socket.create_connection` patched to reject network access. The replay returned **replay_matched**, **39 path rows**, **6 nowcast points**, and **1e-10 tolerance**. No source files or captured outputs were changed by the replay.

## Strengths and practical limits

Live input loading requires the explicit file, unit and hash contract. Unsupported future calendar targets fail closed. Capture uses a unique directory, snapshots numerical frames, retains source bytes, and checks code/static-input and runtime identity before and after calculation. Replay checks receipt hashes, forecast/path values, path diagnostics and readiness. Recording checks the model/horizon roster, h0 agreement, contributions, and path decision clocks.

The existing release calendar still ends at the August 2026 target. The reviewed final output remains a historical July 2026 fixture, captured on 15 September; no prospective September issuance was tested or claimed. Availability still follows the declared reconstructed publication rules, and refreshed upstream histories remain an operational responsibility.
