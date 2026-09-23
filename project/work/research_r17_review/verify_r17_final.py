"""Read-only checks of final R17 evidence; write only a new completion receipt."""
from datetime import datetime, timezone
import csv
import hashlib
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[2]
REVIEW = ROOT / "work/research_r17_review"


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
    checks = {"manifests": {}, "documents": {}}
    names = [
        "research_r15/manifest.json", "research_r15/evaluation/input_manifest.json",
        "research_r16/manifest.json", "research_r16/evaluation/input_manifest.json",
        "research_r16/attribution/manifest.json", "research_r16/interpretation/manifest.json",
        "research_r17_core/manifest.json", "research_r17_food/manifest.json",
        "research_r17_monthly/manifest.json", "research_r17_energy/manifest.json",
        "research_r17/path/manifest.json", "research_r17/path/evaluation/input_manifest.json",
        "research_r17/attribution/manifest.json", "research_r17/primary_uncertainty/manifest.json",
    ]
    for name in names:
        path = ROOT / "output" / name
        manifest = read(path)
        base = path.parent.parent if name.endswith("interpretation/manifest.json") else ROOT
        result = dict(inputs=verify_map(manifest["inputs"], base),
                      outputs=verify_map(manifest["outputs"], path.parent),
                      sha256=sha(path))
        if "evaluator_sha256" in manifest:
            verify_map({manifest["evaluator"]: manifest["evaluator_sha256"]}, ROOT)
        if "shared_r15_evaluator_sha256" in manifest:
            verify_map({"tools/review/evaluate_r15.py": manifest["shared_r15_evaluator_sha256"]}, ROOT)
        if name.endswith("interpretation/manifest.json"):
            verify_map({"tools/review/r16_drivers.py": manifest["source_sha256"],
                        "tools/review/r15_drivers.py": manifest["helper_sha256"]}, ROOT)
        checks["manifests"][name] = result

    for name in ["R17_RESULTS_2026-09-14.md",
                 "work/research_r17_review/R17_VERIFICATION_2026-09-14.md",
                 "README.md", "docs/MODELS.md"]:
        path = ROOT / name
        content = path.read_text(encoding="utf-8")
        if name == "README.md":
            content = content.split("**Previous path research (R16", 1)[0]
        if name == "docs/MODELS.md":
            content = content.split("## R16 path research", 1)[0]
        links = re.findall(r"\]\(([^)]+)\)", content)
        for link in links:
            if link.startswith(("https://", "http://", "#")):
                continue
            if not (path.parent / link.split("#", 1)[0]).is_file():
                raise ValueError(f"Broken report link: {name}: {link}")
        checks["documents"][name] = dict(local_links_verified=len(links), sha256=sha(path))

    receipts = ["FINAL_REVIEW_RECEIPT.json", "ENERGY_FULL_REVIEW_RECEIPT.json",
                "COMBINATION_FINAL_REVIEW_RECEIPT.json"]
    checks["review_receipts"] = {}
    for name in receipts:
        receipt = read(REVIEW / name)
        if "sha256" in receipt and isinstance(receipt["sha256"], dict):
            verify_map(receipt["sha256"], ROOT)
        checks["review_receipts"][name] = sha(REVIEW / name)

    behavior = read(REVIEW / "replay_behavior_receipt.json")
    verify_map({behavior["artifact"]: behavior["sha256"]}, ROOT)
    previous = read(ROOT / "work/research_r16_review/replay_behavior_receipt.json")
    verify_map({previous["artifact"]: previous["sha256"]}, ROOT)
    checks["artifact"] = behavior
    checks["artifact"]["checker_sha256"] = sha(ROOT / "work/research_r16_review/check_replay_behavior.cjs")

    checks["tests"] = {}
    for name, count in [("tests_new_final.log", 69), ("tests_regression.log", 278)]:
        text = (REVIEW / name).read_text(encoding="utf-8-sig")
        if not re.search(rf"\b{count} passed\b", text) or re.search(r"\b\d+ failed\b", text):
            raise ValueError(f"Unexpected test summary: {name}")
        checks["tests"][name] = dict(passed=count, sha256=sha(REVIEW / name))

    # Check the exact matched support and report rounding, without refitting.
    with (ROOT / "output/research_r17/path/evaluation/primary_scoreboard.csv").open(newline="") as f:
        scores = list(csv.DictReader(f))
    expected = {
        "STATE_FAST_R15": (4.8695, .8580),
        "STABLE_LOCAL_CORE_R14B": (5.3972, .7077),
        "DAMPED_P95_Q001_R16": (4.8101, .7159),
        "CORE_ROBUST_R17": (4.8290, .7153),
        "CORE_NEWS_R17": (4.7705, .8425),
        "FUEL_ANNUAL_R17": (4.9133, .7639),
        "COMBO_ALL_R17": (5.0209, .7941),
        "PATH_POOL_R17": (4.9568, .7904),
        "PATH_FAST_CURRENT_HALF_R17": (5.1140, .7670),
    }
    checks["headline_table"] = {}
    for model, pair in expected.items():
        checks["headline_table"][model] = {}
        for sample, count, value in zip(["full", "origins_2024plus"], [75, 19], pair):
            rows = [r for r in scores if r["model"] == model and r["sample"] == sample
                    and r["h"] == "12" and r["metric"] == "headline_yy"]
            assert len(rows) == 1, (model, sample, len(rows))
            row = rows[0]
            assert int(row["n"]) == count and int(row["n_missing_forecasts"]) == 0, row
            assert abs(float(row["rmse"]) - value) <= .00005, row
            checks["headline_table"][model][sample] = dict(n=count, rmse=float(row["rmse"]))

    checks["verified_at_utc"] = datetime.now(timezone.utc).isoformat()
    checks["verifier_sha256"] = sha(Path(__file__))
    checks["status"] = "pass"
    (REVIEW / "final_integrity.json").write_text(json.dumps(checks, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": "pass", "manifests": len(checks["manifests"]),
                      "hash_entries": sum(v["inputs"] + v["outputs"] for v in checks["manifests"].values()),
                      "tests_passed": sum(v["passed"] for v in checks["tests"].values()),
                      "report_rows": len(expected), "receipt": str(REVIEW / "final_integrity.json")}, indent=2))


if __name__ == "__main__":
    main()
