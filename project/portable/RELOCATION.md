# Sealed archive relocation

`portable.relocation.relocations(root, old_root=ORIGINAL_ROOT)` temporarily
adapts the existing R33/R34/R35 verification loaders to a moved checkout.
It never edits archived bytes, manifests, hashes, snapshots or clocks, and
does not run models or contact the network.

The default original repository is:

```text
C:/Users/luis_/Documents/Codex/2026-09-05/c-users-luis-appdata-local-temp/work/cpi-independent
```

## Contract

- Relative paths resolve under `root`, independently of cwd. Current absolute
  paths must be under `root`. Archived absolute paths must be under `old_root`;
  their identical relative suffix is read under `root`.
- Root matching uses path components, not string prefixes. Windows drive paths
  are recognized on non-Windows test hosts too; Windows root matching is case
  insensitive. Archived metadata strings retain their original spelling.
- `old_root` is lexical and need not exist. It is never probed, and a missing
  copied file never falls back to an original file.
- Reject `..` even within the root, external absolute paths, Windows
  drive-relative/root-relative paths, device paths, alternate data streams,
  reserved names, and ambiguous trailing dots/spaces.
- Symlink/junction targets must remain within the checkout before reads.
  The existing shared manifest validator additionally checks containment
  within each package directory.
- `root` must be an existing directory. The roots may be identical; distinct
  roots must not contain one another.
- The yielded object's `resolve(path)` returns a validated native `Path`.
  Its `mappings` property is a tuple of observed (archived, actual) path pairs.
  Neither operation attests content; original loaders perform hash validation.
  No mapping log files are written.

Use the context only for R33 `workflow.load_run` / `compare_runs`,
R34/R35 `inputs.load_prepared`, and their read helpers. It is not a general
filesystem sandbox. The module-local path facade exposes only the read
operations those loaders need; write-open modes fail. R34's returned `output`
is an `os.PathLike` facade, convertible with `Path(result["output"])`.
Run fresh preparation, recording and models outside the context.

## Exact boundaries

| Module attribute | Temporary behavior | Original checks retained |
| --- | --- | --- |
| R33 `workflow.Path` | Rebases archive reads and early `bundle_evidence(request["bundle"])` reads | Archive, bundle and provenance hashes; clocks; normalized forecast equality |
| R34 `inputs.Path`, `_manifest` | Rebases packages and farm/metadata reads; preserves archived package path metadata | Member hashes, complete source metadata equality, farm hashes, clocks, frames |
| R35 `inputs.Path`, `_manifest` | Rebases prepared/capture/frozen packages; preserves archived package identity | Member and capture/raw hashes, original metadata and loader comparisons |
| R35 `inputs._frozen` | After validation, expresses returned `extractor_path` under `old_root` for an archived package | Original extractor source hash, frozen raw hash, weights and observations |

Only these six module attributes are replaced: three `Path` bindings,
two `_manifest` helpers, one `_frozen` helper. Returned metadata dictionaries
are copied before replacing path identity; every other field comes from the
original validator. Current/relative package calls retain current identities.
No global filesystem functions, module `__file__`, `ROOT`, hash functions,
clocks, or numerical routines are patched.

Restoration happens in `finally`, including errors and failed entry.
Nested/overlapping contexts raise `RuntimeError`. Use a single thread or
dedicated process: other threads must not use these modules during the
context, and the checkout must not be mutated concurrently. Launch Python
from the NEW checkout so imports refer to it; the context does not install
modules from `root`. Use `-B` to suppress Python import bytecode.

## Regression command

With the project runtime installed, from the checkout:

```powershell
python -B -m unittest portable.test_relocation -v
```

On the current development computer:

```powershell
$env:PYTHONPATH = 'C:\Users\luis_\AppData\Local\Temp\cpi-r32-runtime;' + (Resolve-Path '..\pythonlibs').Path
& 'C:\Users\luis_\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -B -m unittest portable.test_relocation -v
```

Tests write disposable fixtures only under the OS temp directory.
R33 verifies an early prospective record copied byte-for-byte from a fixture
seed. R34/R35 use their real loaders, manifests, hashes, metadata comparisons
and clocks with small tables and mocked domain coverage/extraction checks.
Original directories need not exist. Tests include source/provenance/farm
metadata tampering, traversal, restoration, failed imports and nesting.
The symlink test explicitly skips when Windows denies symlink creation.

Local result: **13 tests run; 12 passed; 1 symlink privilege skip**.
The full fresh-checkout canonical audit remains the parent task's responsibility.

## Parent's fresh-checkout verification

After the full copy, run from its root. This verifies successful R33 records
and canonical R34/R35 prepared fixtures using their archived decision clocks.
No preparation, model fitting or clock overrides are invoked.

```powershell
@'
import json
from pathlib import Path
from portable.relocation import relocations
from tools.forecast_updates_r33 import workflow
from tools.current_path_r34 import inputs as r34
from tools.momentum_r35 import inputs as r35

root = Path.cwd().resolve()
with relocations(root) as relocation:
    verified = 0
    for result_path in sorted((root / "output/forecast_updates_r33/runs").glob("*/result.json")):
        if json.loads(result_path.read_bytes()).get("status") == "successful":
            workflow.load_run(result_path.parent)
            verified += 1
    assert verified, "No successful R33 records found"
    for loader, relative in (
        (r34.load_prepared, "output/current_path_r34_inputs/prepared_20260922_v2"),
        (r35.load_prepared, "output/momentum_r35_inputs/prepared_20260922_v1"),
    ):
        prepared = root / relative
        provenance = json.loads((prepared / "provenance.json").read_bytes())
        loader(prepared, as_of=provenance["as_of"])
    print({"successful_r33_records": verified, "r34": "verified", "r35": "verified",
           "relocated_paths": len(relocation.mappings)})
'@ | python -B -
```

This fixture command complements the parent's complete archive inventory and
canonical audit; keep the same context around audit calls to these loaders.
Investigate hash failures; never reseal or rewrite archived provenance to
make relocation pass.

