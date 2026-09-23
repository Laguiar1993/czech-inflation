"""Bounded R32 subprocess recording and validated component revision export.

The archive is append-only by this API; hashes attest local integrity, not an
external signature. Only the per-identity successful pointer is replaceable.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys
import uuid
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / "output/forecast_updates_r33"
SCHEMA = "forecast_updates_r33/run-v1"
MODEL = "HARD_BASE"
UNITS = "mm_pct"
TOL = 1e-9
MAX_PROSPECTIVE_AGE_SECONDS = 300
SOURCE_FILES = ("forecast_independent.py", "cz_struct.py",
                "tools/live_bundle_r32/adapter.py", "tools/live_bundle_r32/runner.py",
                "tools/live_bundle_r32/cli.py")


def utcnow():
    return datetime.now(timezone.utc)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def encoded(value):
    return (json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n").encode("utf-8")


def read_json(path):
    def reject(value):
        raise ValueError("nonfinite JSON number: " + value)
    value = json.loads(Path(path).read_bytes(), parse_constant=reject)
    if not isinstance(value, dict):
        raise ValueError("JSON document must be an object")
    return value


def write_new(path, value):
    raw = encoded(value)
    with Path(path).open("xb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())


def owned(path, output_only=False):
    path = Path(path).resolve()
    roots = (OUTPUT.resolve(),) if output_only else (
        OUTPUT.resolve(), (ROOT / "tools/forecast_updates_r33").resolve())
    if not any(path.is_relative_to(root) for root in roots):
        raise ValueError("writes must stay in the new R33 owned directories")
    return path


def clock(value):
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if dt.tzinfo is None or dt.utcoffset() is None:
            raise ValueError()
        return dt.astimezone(timezone.utc)
    except (ValueError, TypeError, AttributeError) as exc:
        raise ValueError("timestamp must have an explicit timezone") from exc


def month(value):
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", value):
        raise ValueError("target must be YYYY-MM")
    datetime.strptime(value, "%Y-%m")
    return value


def number(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError("point/contribution must be finite numeric")
    return float(value)


def validate_clocks(request, recorded, completed):
    as_of, start, end = clock(request["as_of"]), clock(recorded), clock(completed)
    month(request["target"])
    if request["mode"] not in ("replay", "prospective"):
        raise ValueError("mode must be replay or prospective")
    if request["command"] not in ("run", "readiness"):
        raise ValueError("command must be run or readiness")
    if as_of > start:
        raise ValueError("future as-of timestamp is not allowed")
    if end < start:
        raise ValueError("recording clock moved backwards")
    if request["mode"] == "prospective" and (start - as_of).total_seconds() > MAX_PROSPECTIVE_AGE_SECONDS:
        raise ValueError("stale as-of: prospective recording must start within 300 seconds; use replay")
    return as_of, start, end


def release_clock(value):
    # R32 reports Prague wall time without its timezone. This conversion restores
    # its documented zone; ambiguous/nonexistent local times fail closed.
    if not value:
        raise ValueError("missing sourced first release")
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is not None:
        return dt.astimezone(timezone.utc)
    zone = ZoneInfo("Europe/Prague")
    a, b = dt.replace(tzinfo=zone, fold=0), dt.replace(tzinfo=zone, fold=1)
    if a.utcoffset() != b.utcoffset() or a.astimezone(timezone.utc).astimezone(zone).replace(tzinfo=None) != dt:
        raise ValueError("ambiguous or nonexistent first release timezone")
    return a.astimezone(timezone.utc)


def path_points(payload, request):
    if payload is None:
        return None
    for key, expected in (("target", request["target"]), ("model", MODEL), ("units", UNITS)):
        if payload.get(key) != expected:
            raise ValueError("external path identity mismatch: " + key)
    if clock(payload.get("as_of")) != clock(request["as_of"]):
        raise ValueError("external path clock mismatch")
    if not isinstance(payload.get("source"), str) or not payload["source"].strip():
        raise ValueError("external path requires source provenance")
    points = payload.get("points")
    if not isinstance(points, list) or not points:
        raise ValueError("external path requires calendar target-month points")
    result = {}
    for row in points:
        target = month(row["target_month"])
        if target < request["target"] or target in result:
            raise ValueError("duplicate or pre-origin external path target month")
        result[target] = number(row["point"])
    return result


def validate_adapter(request, report, recorded, completed, inputs, path=None):
    as_of, start, end = validate_clocks(request, recorded, completed)
    if report.get("schema_version") != "live_bundle_r32/v1":
        raise ValueError("unsupported adapter report")
    for key, expected in (("target", request["target"]), ("variant", "R31C_C123"), ("main_model", MODEL), ("command", request["command"])):
        if report.get(key) != expected:
            raise ValueError("adapter identity mismatch: " + key)
    if clock(report.get("as_of")) != as_of:
        raise ValueError("adapter as-of mismatch")
    if report.get("status") not in ("calculated", "ready_for_calculation") or report.get("reasons"):
        raise ValueError("adapter blocked: " + json.dumps(report.get("reasons", [])))
    if report.get("ready_for_calculation") is not True or report.get("runtime", {}).get("ready") is not True:
        raise ValueError("adapter runtime/calculation not ready")
    data = report.get("readiness", {})
    if data.get("data_ready") is not True or data.get("before_first_release") is not True or data.get("reasons"):
        raise ValueError("adapter data not ready")
    first = release_clock(data.get("first_release"))
    if as_of >= first or (request["mode"] == "prospective" and end >= first):
        raise ValueError("first release already reached at decision or actual recording time")
    if report.get("provenance", {}).get("bundle_manifest_sha256") != inputs["bundle_manifest_sha256"]:
        raise ValueError("adapter bundle manifest changed or mismatched")
    expected_calendar = inputs.get("live_calendar_sha256")
    if report.get("calendar", {}).get("live_sha256") != expected_calendar:
        raise ValueError("adapter live calendar changed or mismatched")
    path = path_points(path, request)
    if request["command"] == "readiness":
        return None, path
    if (report.get("status") != "calculated" or report.get("forecast_available") is not True
            or report.get("ready_for_first_release") is not True):
        raise ValueError("no successful calculated forecast")
    f = report.get("forecast", {})
    if f.get("target") != request["target"] or clock(f.get("as_of")) != as_of or f.get("main_model") != MODEL:
        raise ValueError("forecast identity mismatch")
    if f.get("ready_for_first_release") is not True or f.get("before_first_release") is not True:
        raise ValueError("forecast not ready for first release")
    if f.get("food_diagnostics", {}).get("method") != "x13":
        raise ValueError("food fallback is not a validated forecast")
    if f.get("diagnostics", {}).get("hard", {}).get("residual_forest", {}).get("fallback_used") is not False:
        raise ValueError("residual forest fallback/diagnostics missing")
    point = number(f["points_mm_pct"][MODEL])
    values = f["main_contributions_pp"]
    if not isinstance(values, dict) or not values or any(not isinstance(k, str) or not k.strip() for k in values):
        raise ValueError("named contributions required")
    components = {k: number(v) for k, v in sorted(values.items())}
    residual = point - math.fsum(components.values())
    if abs(residual) > TOL:
        raise ValueError("component contributions do not reconcile to point")
    if not isinstance(f.get("version"), str) or not f["version"]:
        raise ValueError("missing forecast model version")
    identity = sha(encoded({"model": MODEL, "variant": report["variant"], "version": f["version"],
                            "source_hashes": inputs["source_hashes"]}))
    return {"point": point, "components": components, "residual": residual,
            "model_identity": identity, "first_release": first.isoformat()}, path


def bounded_run(command, *, timeout, cwd, env, stdout, stderr):
    """Wait once; terminate the owned process tree on timeout (including X13)."""
    options = {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {"start_new_session": True}
    proc = subprocess.Popen(command, cwd=cwd, env=env, stdout=stdout, stderr=stderr, **options)
    try:
        return subprocess.CompletedProcess(command, proc.wait(timeout=timeout))
    except (subprocess.TimeoutExpired, KeyboardInterrupt):
        if proc.poll() is None:
            if os.name == "nt":
                try:
                    subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"],
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                   timeout=5, check=False, creationflags=subprocess.CREATE_NO_WINDOW)
                except (OSError, subprocess.TimeoutExpired):
                    pass
            else:
                import signal
                try:
                    os.killpg(proc.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            if proc.poll() is None:
                proc.kill()
            proc.wait(timeout=5)
        raise


def invoke_r32(request, directory):
    command = [sys.executable, "-B", "-m", "tools.live_bundle_r32", request["command"],
               "--bundle", request["bundle"], "--target", request["target"], "--as-of", request["as_of"]]
    if request["live_calendar"]:
        command.extend(["--live-calendar", str(directory / "live_calendar.csv")])
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    scratch = directory / "scratch"
    scratch.mkdir()
    env.update(TMP=str(scratch), TEMP=str(scratch), TMPDIR=str(scratch))
    with (directory / "adapter.stdout").open("xb") as out, (directory / "adapter.stderr").open("xb") as err:
        result = bounded_run(command, cwd=ROOT, env=env, stdout=out, stderr=err,
                             timeout=request["timeout_seconds"])
    report = read_json(directory / "adapter.stdout")
    if result.returncode not in (0, 2):
        raise ValueError(f"adapter exit {result.returncode}; see adapter.stderr")
    if result.returncode != 0 and report.get("status") != "blocked":
        raise ValueError("adapter exit/status mismatch")
    return report


def source_hashes():
    names = set(SOURCE_FILES) | {"config.py", "independent_nowcast_experiment.py"}
    for folder in ("models", "data"):
        names.update(p.relative_to(ROOT).as_posix() for p in (ROOT / folder).glob("*.py"))
    return {name: sha((ROOT / name).read_bytes()) for name in sorted(names)}


def seal(directory):
    files = {p.relative_to(directory).as_posix(): sha(p.read_bytes())
             for p in sorted(directory.rglob("*")) if p.is_file() and p.name != "MANIFEST.json"}
    write_new(directory / "MANIFEST.json", {"schema_version": SCHEMA, "files": files})


def publish(store, directory, record):
    if record["mode"] == "prospective" and utcnow() >= clock(record["forecast"]["first_release"]):
        raise ValueError("first release already reached before publication")
    pointer = store / "latest_successful.json"
    current = read_json(pointer) if pointer.exists() else {"schema_version": SCHEMA, "entries": {}}
    key = "|".join(record[k] for k in ("mode", "target", "model", "units", "model_identity"))
    prior = current["entries"].get(key)
    if prior:
        previous = load_run(store / prior["run_directory"])
        if sha((store / prior["run_directory"] / "MANIFEST.json").read_bytes()) != prior["manifest_sha256"]:
            raise ValueError("prior pointer manifest hash mismatch")
        if clock(previous["as_of"]) >= clock(record["as_of"]):
            return {"status": "retained", "reason": "existing successful as-of is at least as new"}
    current["entries"][key] = {"run_directory": directory.relative_to(store).as_posix(),
                               "manifest_sha256": sha((directory / "MANIFEST.json").read_bytes()),
                               "as_of": record["as_of"], "recorded_at": record["recorded_at"]}
    pending = store / ("pointer-" + uuid.uuid4().hex + ".tmp")
    try:
        write_new(pending, current)
        os.replace(pending, pointer)
    finally:
        if pending.exists():
            pending.unlink()
    return {"status": "published"}


def bundle_evidence(bundle, expected_hash, *, manifest_raw=None, provenance_raw=None):
    """Bind availability metadata to the exact input manifest, including legacy runs."""
    folder = Path(bundle)
    raw = manifest_raw if manifest_raw is not None else (folder / "MANIFEST.json").read_bytes()
    if sha(raw) != expected_hash:
        raise ValueError("bundle manifest hash mismatch while checking availability")
    manifest = json.loads(raw)
    files = manifest.get("files", {})
    digest = files.get("provenance.json")
    if isinstance(digest, dict):
        digest = digest.get("sha256")
    if digest is None:
        # Existing test transports/static schemas have no dated preparation.
        # The real adapter still validates its required portable-bundle files.
        return raw, None, None
    prov_raw = provenance_raw if provenance_raw is not None else (folder / "provenance.json").read_bytes()
    if sha(prov_raw) != digest:
        raise ValueError("bundle provenance hash mismatch while checking availability")
    return raw, prov_raw, json.loads(prov_raw)


def check_bundle_availability(request, provenance):
    if request["mode"] != "prospective" or provenance is None:
        return
    # Preparation timestamp itself may follow the as-of: source availability,
    # rather than computation time, determines whether an input was known.
    prepared = "feature_function" in provenance or "manual_rows" in provenance
    snapshot = provenance.get("snapshot")
    if prepared and (not isinstance(snapshot, dict) or not snapshot.get("completed_at")):
        raise ValueError("prepared bundle is missing snapshot completion evidence")
    if isinstance(snapshot, dict) and snapshot.get("completed_at"):
        if clock(snapshot["completed_at"]) > clock(request["as_of"]):
            raise ValueError("snapshot completion is later than the run as-of")
    rows = provenance.get("manual_rows", [])
    if not isinstance(rows, list):
        raise ValueError("manual availability evidence must be a list")
    for row in rows:
        if not isinstance(row, dict) or not row.get("available_from"):
            raise ValueError("manual availability evidence is missing")
        if clock(row["available_from"]) > clock(request["as_of"]):
            raise ValueError("manual availability is later than the run as-of")


def record(bundle, target, as_of, mode, *, store=OUTPUT, command="run",
           live_calendar=None, path_file=None, timeout=120, invoke=invoke_r32):
    store = owned(store)
    store.mkdir(parents=True, exist_ok=True)
    recorded = utcnow().isoformat()
    directory = store / "runs" / (utcnow().strftime("%Y%m%dT%H%M%S%fZ") + "_" + uuid.uuid4().hex[:12])
    directory.mkdir(parents=True, exist_ok=False)
    request = {"command": command, "bundle": str(Path(bundle).resolve()), "target": target, "as_of": as_of,
               "mode": mode, "live_calendar": str(Path(live_calendar).resolve()) if live_calendar else None,
               "path_file": str(Path(path_file).resolve()) if path_file else None, "timeout_seconds": timeout}
    write_new(directory / "request.json", dict(request, recorded_at=recorded))
    result = {"schema_version": SCHEMA, "status": "blocked", "command": command, "target": target, "as_of": as_of, "mode": mode,
              "model": MODEL, "units": UNITS, "model_identity": None, "recorded_at": recorded,
              "completed_at": None, "forecast": None, "path": None, "reason": "",
              "run_directory": str(directory)}
    lock = store / ".refresh.lock"
    lock_fd = None
    try:
        lock_fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.write(lock_fd, str(directory).encode("utf-8"))
        validate_clocks(request, recorded, utcnow().isoformat())
        if not isinstance(timeout, (int, float)) or isinstance(timeout, bool) or not 0 < timeout <= 300:
            raise ValueError("timeout must be in (0, 300] seconds")
        inputs = {"bundle_manifest_sha256": sha((Path(bundle) / "MANIFEST.json").read_bytes()),
                  "source_hashes": source_hashes(), "live_calendar_sha256": None}
        bundle_raw, provenance_raw, provenance = bundle_evidence(bundle, inputs["bundle_manifest_sha256"])
        check_bundle_availability(request, provenance)
        (directory / "bundle_manifest.json").write_bytes(bundle_raw)
        if provenance_raw is not None:
            (directory / "bundle_provenance.json").write_bytes(provenance_raw)
        inputs["bundle_evidence_version"] = 1
        if live_calendar:
            raw = Path(live_calendar).read_bytes()
            (directory / "live_calendar.csv").write_bytes(raw)
            inputs["live_calendar_sha256"] = sha(raw)
        path = read_json(path_file) if path_file else None
        if path is not None:
            write_new(directory / "path_input.json", path)
        write_new(directory / "inputs.json", inputs)
        report = invoke(request, directory)
        write_new(directory / "adapter.json", report)
        result["completed_at"] = utcnow().isoformat()
        forecast, path = validate_adapter(request, report, recorded, result["completed_at"], inputs, path)
        if source_hashes() != inputs["source_hashes"]:
            raise ValueError("model implementation changed during refresh")
        result.update(status="successful" if forecast else "ready", forecast=forecast, path=path,
                      model_identity=forecast["model_identity"] if forecast else None,
                      reason=(("Validated component accounting; not causal news attribution. " if forecast
                               else "Input/runtime preflight passed; no forecast calculated. ")
                              + ("Historical/latest-vintage replay." if mode == "replay"
                                 else "Recorded before first release; latest-vintage/static-input limitations remain.")))
    except Exception as exc:
        result.update(status="blocked", forecast=None, path=None, reason=f"{type(exc).__name__}: {exc}")
    finally:
        result["completed_at"] = result["completed_at"] or utcnow().isoformat()
        try:
            write_new(directory / "result.json", result)
            seal(directory)
            publication = {"status": "not_applicable"}
            if result["status"] == "successful":
                try:
                    load_run(directory)
                    publication = publish(store, directory, result)
                except Exception as exc:
                    publication = {"status": "failed", "reason": f"{type(exc).__name__}: {exc}"}
            write_new(directory / "publication.json", publication)
        finally:
            if lock_fd is not None:
                os.close(lock_fd)
                lock.unlink()
    return dict(result, publication=publication)


def load_run(directory):
    directory = Path(directory).resolve()
    if directory.name == "result.json":
        directory = directory.parent
    manifest = read_json(directory / "MANIFEST.json")
    if manifest.get("schema_version") != SCHEMA:
        raise ValueError("unsupported archive schema")
    files = manifest["files"]
    if not {"request.json", "result.json"} <= set(files):
        raise ValueError("incomplete archive manifest")
    for name, digest in files.items():
        path = (directory / name).resolve()
        if not path.is_relative_to(directory) or path == directory:
            raise ValueError("unsafe archive path")
        if sha(path.read_bytes()) != digest:
            raise ValueError("archive hash mismatch: " + name)
    result = read_json(directory / "result.json")
    if result.get("schema_version") != SCHEMA or result.get("status") != "successful":
        raise ValueError("run is not a validated successful calculation")
    if not {"adapter.json", "inputs.json"} <= set(files):
        raise ValueError("successful run lacks validated inputs/adapter")
    request = read_json(directory / "request.json")
    if result["recorded_at"] != request["recorded_at"]:
        raise ValueError("recording timestamp mismatch")
    if clock(result["completed_at"]) > utcnow():
        raise ValueError("future actual recording timestamp")
    for k in ("target", "as_of", "mode", "command"):
        if result[k] != request[k]:
            raise ValueError("request/result mismatch: " + k)
    inputs = read_json(directory / "inputs.json")
    if inputs.get("bundle_evidence_version") == 1:
        if "bundle_manifest.json" not in files:
            raise ValueError("archive lacks sealed bundle manifest evidence")
        raw = (directory / "bundle_manifest.json").read_bytes()
        source_manifest = json.loads(raw)
        needs_provenance = "provenance.json" in source_manifest.get("files", {})
        if needs_provenance and "bundle_provenance.json" not in files:
            raise ValueError("archive lacks sealed bundle provenance evidence")
        prov_raw = (directory / "bundle_provenance.json").read_bytes() if needs_provenance else None
        _, _, provenance = bundle_evidence(request["bundle"], inputs["bundle_manifest_sha256"],
                                           manifest_raw=raw, provenance_raw=prov_raw)
        check_bundle_availability(request, provenance)
    elif request["mode"] == "prospective":
        # Earlier records retain their immutable, hash-pinned prepared bundle.
        # Revalidate it without changing any archived bytes.
        _, _, provenance = bundle_evidence(request["bundle"], inputs["bundle_manifest_sha256"])
        check_bundle_availability(request, provenance)
    if request["live_calendar"] and ("live_calendar.csv" not in files or
            sha((directory / "live_calendar.csv").read_bytes()) != inputs["live_calendar_sha256"]):
        raise ValueError("missing or mismatched calendar evidence")
    if request["path_file"] and "path_input.json" not in files:
        raise ValueError("missing external path evidence")
    external = read_json(directory / "path_input.json") if "path_input.json" in files else None
    forecast, path = validate_adapter(request, read_json(directory / "adapter.json"),
                                      result["recorded_at"], result["completed_at"], inputs, external)
    if forecast is None or result["forecast"] != forecast or result["path"] != path:
        raise ValueError("stored normalized forecast/path does not match adapter evidence")
    if result["model"] != MODEL or result["units"] != UNITS or result["model_identity"] != forecast["model_identity"]:
        raise ValueError("stored model/units mismatch")
    return result


def unavailable(reason):
    return {"status": "blocked", "kind": "unavailable", "target": None, "model": None,
            "old_as_of": None, "new_as_of": None, "old_point": None, "new_point": None,
            "delta": None, "components": [], "residual": None, "path_changes": [], "reason": reason}


def compare_records(old, new):
    """Internal accounting helper. Public callers should use compare_runs."""
    try:
        for record in (old, new):
            if record["status"] != "successful":
                raise ValueError("two successful runs are required")
            validate_clocks(record, record["recorded_at"], record["completed_at"])
            if clock(record["completed_at"]) > utcnow():
                raise ValueError("future actual recording timestamp")
        for key in ("target", "model", "model_identity", "units", "mode"):
            if old[key] != new[key]:
                raise ValueError("not comparable: different " + key)
        if clock(new["as_of"]) <= clock(old["as_of"]):
            raise ValueError("new as-of must be strictly newer than old")
        a, b = old["forecast"], new["forecast"]
        if set(a["components"]) != set(b["components"]):
            raise ValueError("not comparable: different component definitions")
        for value in (a, b):
            if abs(number(value["point"]) - math.fsum(number(x) for x in value["components"].values())) > TOL:
                raise ValueError("components do not reconcile to point")
        components = [{"name": name, "old": a["components"][name], "new": b["components"][name],
                       "delta": b["components"][name] - a["components"][name]} for name in sorted(a["components"])]
        delta = b["point"] - a["point"]
        residual = delta - math.fsum(c["delta"] for c in components)
        if abs(residual) > 2 * TOL:
            raise ValueError("revision components fail total-delta reconciliation")
        paths = []
        # Optional paths are compared only when BOTH runs supplied a path.
        if old["path"] is not None and new["path"] is not None:
            for target in sorted(set(old["path"]) | set(new["path"])):
                x, y = old["path"].get(target), new["path"].get(target)
                paths.append({"target_month": target, "old": x, "new": y,
                              "delta": y - x if x is not None and y is not None else None})
        return {"status": "ok", "kind": "replay_revision" if old["mode"] == "replay" else "forecast_revision",
                "target": old["target"], "model": old["model"], "old_as_of": old["as_of"], "new_as_of": new["as_of"],
                "old_point": a["point"], "new_point": b["point"], "delta": delta, "components": components,
                "residual": residual, "path_changes": paths,
                "reason": ("Same-target/model m/m component accounting in percentage points; not causal news attribution. "
                           "Residual is unexplained numerical reconciliation. "
                           + ("Historical/latest-vintage replay, not prospective evidence. " if old["mode"] == "replay" else "")
                           + ("Path changes use externally supplied, calendar-aligned points." if paths else "No comparable optional paths."))}
    except (KeyError, TypeError, ValueError) as exc:
        return unavailable(str(exc))


def compare_runs(old, new):
    try:
        a, b = load_run(old), load_run(new)
        return compare_records(a, b)
    except (OSError, KeyError, TypeError, ValueError, AttributeError, OverflowError) as exc:
        return unavailable(f"{type(exc).__name__}: {exc}")
