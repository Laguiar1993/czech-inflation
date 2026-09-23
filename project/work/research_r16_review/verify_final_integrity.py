"""Verify frozen research files, final report links and replay behavior receipt."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[2]


def read(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_map(mapping, base):
    for name, digest in mapping.items():
        path = base / name
        if sha(path) != digest:
            raise ValueError(f"Hash changed: {path}")
    return len(mapping)


def main():
    checks = {}
    for version in ("r15", "r16"):
        directory = ROOT / "output" / ("research_" + version)
        manifest = read(directory / "manifest.json")
        checks[version] = dict(inputs=verify_map(manifest["inputs"], ROOT),
                               outputs=verify_map(manifest["outputs"], directory))
        output = directory / "evaluation"
        manifest = read(output / "input_manifest.json")
        checks[version + "_evaluation"] = dict(inputs=verify_map(manifest["inputs"], ROOT),
                                                outputs=verify_map(manifest["outputs"], output))

    directory = ROOT / "output/research_r16"
    manifest = read(directory / "interpretation/manifest.json")
    checks["interpretation"] = dict(inputs=verify_map(manifest["inputs"], directory),
        outputs=verify_map(manifest["outputs"], directory / "interpretation"))
    if sha(ROOT / "tools/review/r16_drivers.py") != manifest["source_sha256"]:
        raise ValueError("Driver source changed")
    if sha(ROOT / "tools/review/r15_drivers.py") != manifest["helper_sha256"]:
        raise ValueError("Driver helper changed")
    checks["interpretation"]["sources"] = 2

    manifest = read(directory / "attribution/manifest.json")
    checks["attribution"] = dict(inputs=verify_map(manifest["inputs"], ROOT),
        outputs=verify_map(manifest["outputs"], directory / "attribution"))
    for name in ("R16_RESULTS_2026-09-14.md", "work/research_r16_review/VERIFICATION_2026-09-14.md"):
        path = ROOT / name
        links = re.findall(r"\]\(([^)]+)\)", path.read_text(encoding="utf-8"))
        for link in links:
            if not (path.parent / link).exists():
                raise ValueError(f"Broken report link: {name}: {link}")
        checks[name] = dict(links_verified=len(links), sha256=sha(path))

    behavior = read(ROOT / "work/research_r16_review/replay_behavior_receipt.json")
    if sha(ROOT / behavior["artifact"]) != behavior["sha256"]:
        raise ValueError("HTML changed after Node behavior check")
    checks["replay_behavior"] = dict(sha256=behavior["sha256"],
        script_sha256=sha(ROOT / "work/research_r16_review/check_replay_behavior.cjs"),
        checks=behavior["checks"], limitation=behavior["limitation"])
    checks["verified_at_utc"] = datetime.now(timezone.utc).isoformat()
    target = ROOT / "work/research_r16_review/final_integrity.json"
    target.write_text(json.dumps(checks, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(checks, indent=2))


if __name__ == "__main__":
    main()
