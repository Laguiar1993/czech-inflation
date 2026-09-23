"""Independent exact-rank audit of the preserved and verified R18 runs."""
import hashlib
import json
import sys
from fractions import Fraction
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from models.nowcast_reliability_r18_verified import weighted_quantile

FIELDS = {"lo90": Fraction(1, 20), "lo80": Fraction(1, 10), "median": Fraction(1, 2),
          "hi80": Fraction(9, 10), "hi90": Fraction(19, 20)}


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path):
    return pd.read_csv(path, float_precision="round_trip")


def exact_quantile(support, weights, probability):
    """Exact rational accumulation of binary64 weights; no cumsum or tolerance.

    For equal positive weights this reduces to exact integer nearest rank.
    Requested quantile probabilities are the declared exact decimal fractions.
    """
    pairs = sorted((float(x), Fraction.from_float(float(w))) for x, w in zip(support, weights) if w > 0)
    target = probability * sum(w for _, w in pairs)
    cumulative = Fraction(0)
    for value, weight in pairs:
        cumulative += weight
        if cumulative >= target:
            return value
    return pairs[-1][0]


def main():
    original = ROOT / "output/research_r18_nowcast"
    verified = ROOT / "output/research_r18_nowcast_verified"
    keys = ["origin", "model", "family"]
    old = read(original / "predictions.csv").set_index(keys)
    new = read(verified / "predictions.csv").set_index(keys)
    pd.testing.assert_index_equal(old.index, new.index)
    allowed = set(FIELDS) | {"cover80", "cover90"}
    preserved_columns = [name for name in old.columns if name not in allowed]
    pd.testing.assert_frame_equal(old[preserved_columns], new[preserved_columns], check_exact=True)
    parity = {}
    for filename in ("laws.json", "alerts.csv", "coverage.csv", "error_history.csv"):
        parity[filename] = digest(original / filename) == digest(verified / filename)
    assert all(parity.values())
    laws = json.loads((verified / "laws.json").read_text())
    mismatches = []
    changed = []
    quantiles_checked = 0
    equal_quantiles = 0
    for law in laws:
        if law["status"] != "estimated":
            continue
        key = (law["origin"], law["model"], law["family"])
        row = new.loc[key]
        x, w = law["support"], law["weights"]
        for field, p in FIELDS.items():
            expected = exact_quantile(x, w, p)
            quantiles_checked += 1
            equal_quantiles += len(set(w)) == 1
            if row[field] != expected:
                mismatches.append({"origin":key[0], "model":key[1], "family":key[2], "field":field,
                                   "saved":float(row[field]), "exact_reference":expected})
            if old.loc[key, field] != row[field]:
                changed.append({"origin":key[0], "model":key[1], "family":key[2], "field":field,
                                "old":float(old.loc[key,field]), "verified":float(row[field]),
                                "difference":float(row[field]-old.loc[key,field]), "n":law["n"]})
        assert row.cover80 == (row.lo80 <= row.actual <= row.hi80)
        assert row.cover90 == (row.lo90 <= row.actual <= row.hi90)
    assert not mismatches, mismatches[:5]
    # A broader exact integer-rank grid includes both endpoints and all run sizes.
    boundary_cases = 0
    outside_run_size_failures = []
    for n in range(1, 257):
        for p in [Fraction(0), *FIELDS.values(), Fraction(1)]:
            # ceil(n*p) is computed on integers, so no binary64 correction is used.
            rank = max(1, (n * p.numerator + p.denominator - 1) // p.denominator)
            actual_rank = weighted_quantile(np.arange(n), np.ones(n), float(p))
            if actual_rank != rank - 1:
                assert n > 60, (n, p)
                outside_run_size_failures.append({"n":n,"p":str(p),"actual":actual_rank,"expected":rank-1})
            boundary_cases += 1
    changed_df = pd.DataFrame(changed)
    changed_df.to_csv(OUT / "verified_quantile_changes.csv", index=False)
    flag_changes = []
    for field in ("cover80", "cover90"):
        for key in old.index[old[field] != new[field]]:
            flag_changes.append({**dict(zip(keys,key)), "field":field, "old":bool(old.loc[key,field]), "verified":bool(new.loc[key,field])})
    pd.DataFrame(flag_changes, columns=keys+["field","old","verified"]).to_csv(OUT / "verified_coverage_changes.csv", index=False)
    old_scores = read(original / "scores.csv").set_index(["model", "family", "frame"])
    new_scores = read(verified / "scores.csv").set_index(["model", "family", "frame"])
    invariant_scores = [name for name in old_scores.columns if name not in ("coverage80", "coverage90", "width80", "width90")]
    pd.testing.assert_frame_equal(old_scores[invariant_scores], new_scores[invariant_scores], check_exact=True)
    score_changes = []
    for key in new_scores.index:
        model, family, frame = key
        z = new.reset_index()
        z = z[(z.model == model) & (z.family == family)]
        masks = {"all": np.ones(len(z),bool), "2024+":z.origin.ge("2024-01"), "flash":z.release_kind.eq("flash"),
                 "january":z.origin.str.endswith("-01"), "ex_january":~z.origin.str.endswith("-01"), "big":z.big}
        a = z.loc[masks[frame]]
        expected = dict(coverage80=a.cover80.mean(), coverage90=a.cover90.mean(),
                        width80=(a.hi80-a.lo80).mean(), width90=(a.hi90-a.lo90).mean())
        for field, value in expected.items():
            assert abs(new_scores.loc[key,field]-value) < 1e-13
            if old_scores.loc[key,field] != new_scores.loc[key,field]:
                score_changes.append({"model":model,"family":family,"frame":frame,"field":field,
                                      "old":float(old_scores.loc[key,field]), "verified":float(new_scores.loc[key,field]),
                                      "difference":float(new_scores.loc[key,field]-old_scores.loc[key,field])})
    pd.DataFrame(score_changes).to_csv(OUT / "verified_score_changes.csv", index=False)
    manifest_checks = {}
    for folder in (original,verified):
        manifest = json.loads((folder/"manifest.json").read_text())
        for name,value in manifest["inputs"].items():
            assert digest(ROOT/name) == value, (folder.name,name)
        for name,value in manifest["outputs"].items():
            assert digest(folder/name) == value, (folder.name,name)
        manifest_checks[folder.name] = {"inputs":len(manifest["inputs"]),"outputs":len(manifest["outputs"]),
                                        "manifest_sha256":digest(folder/"manifest.json")}
    all_frame_coverage = new_scores.loc[(slice(None),slice(None),"all"),["coverage80","coverage90","width80","width90"]].reset_index().to_dict("records")
    receipt = {
        "status": "verified_run_quantiles_and_parity_passed",
        "exact_rational_quantiles_checked":quantiles_checked, "equal_weight_quantiles_checked":int(equal_quantiles),
        "unequal_weight_quantiles_checked":quantiles_checked-int(equal_quantiles), "quantile_mismatches":mismatches,
        "independent_integer_rank_boundary_cases":boundary_cases,
        "boundary_failures_within_run_size_1_to_60":0,
        "outside_run_size_boundary_failures":outside_run_size_failures,
        "byte_identical_original_verified_files":parity, "unchanged_prediction_columns":preserved_columns,
        "changed_quantile_cells":len(changed), "prediction_rows_with_quantile_change":len(changed_df[keys].drop_duplicates()),
        "changed_quantiles_by_field":changed_df.field.value_counts().to_dict(),
        "changed_quantiles_by_family":changed_df.family.value_counts().to_dict(),
        "max_abs_quantile_change_pp":float(changed_df.difference.abs().max()),
        "coverage_flag_changes":flag_changes, "summary_cells_changed":len(score_changes),
        "summary_fields_changed":sorted(set(item["field"] for item in score_changes)),
        "verified_all_frame_interval_scores":all_frame_coverage,
        "manifest_checks":manifest_checks,
        "off_grid_helper_limit":{
            "case":"weighted_quantile([0,1],[1,1e-16],1)",
            "actual":weighted_quantile([0,1],[1,1e-16],1), "exact_expected":1,
            "meaning":"The absolute CDF boundary tolerance can exclude a tiny positive tail at p=1; this is outside the run quantile grid and does not affect any saved output. No source changes made."},
        "prior_audit_correction":"The first audit's floating cumulative-weight oracle repeated the original boundary behavior. This exact-rational/integer-rank audit supersedes its quantile conclusion; earlier law, probability, CRPS and alert findings stand."
    }
    (OUT/"verified_quantile_receipt.json").write_text(json.dumps(receipt,indent=2)+"\n")
    print(json.dumps({key:value for key,value in receipt.items() if key not in ("verified_all_frame_interval_scores","unchanged_prediction_columns")},indent=2))


if __name__ == "__main__": main()
