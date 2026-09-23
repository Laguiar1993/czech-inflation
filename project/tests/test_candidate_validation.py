"""Verdict rules used to validate Bloomberg candidates against official series."""
import numpy as np
import pandas as pd

from tools.paper_replication import validate_candidates as val


def _series(values, start="2018-01"):
    return pd.Series(values, index=pd.period_range(start, periods=len(values), freq="M"), dtype=float)


def _matrix(candidate, officials):
    rows = []
    for code, official in officials.items():
        stats = val.compare(candidate, official)
        stats.update(official_code=code, official_sa=code.split(".")[4].endswith("S"))
        rows.append(stats)
    return pd.DataFrame(rows)


def _walk(seed, n=100):
    return _series(np.round(np.cumsum(np.random.default_rng(seed).normal(size=n)), 1))


def test_compare_reports_identity_and_overlap():
    a = _walk(0)
    stats = val.compare(a, a.copy())
    assert stats["n"] == 100 and stats["mae"] == 0 and stats["share_identical"] == 1
    shifted = val.compare(a, a.iloc[10:] + 1.0)
    assert shifted["n"] == 90 and shifted["mae"] == 1.0 and shifted["share_identical"] == 0


def test_adjusted_series_wins_a_tie_with_identical_unadjusted_values():
    x = _walk(1)
    matrix = _matrix(x, {"SERV.CZ.TOT.2.B.M": x, "SERV.CZ.TOT.2.BS.M": x, "SERV.CZ.TOT.3.BS.M": x + 3})
    verdict, best = val.bcs_verdict(matrix, "SERV.CZ.TOT.2.BS.M")
    assert verdict == "identical_SA" and best["official_code"] == "SERV.CZ.TOT.2.BS.M"


def test_unadjusted_mirror_is_labelled_as_such():
    x = _walk(2)
    seasonal = _series(np.round(3 * np.sin(2 * np.pi * np.arange(100) / 12), 1))
    matrix = _matrix(x, {"RETA.CZ.TOT.3.B.M": x, "RETA.CZ.TOT.3.BS.M": x + seasonal})
    assert val.bcs_verdict(matrix, "RETA.CZ.TOT.3.BS.M")[0] == "identical_NSA"


def test_a_mnemonic_for_another_question_is_detected():
    x, other = _walk(3), _walk(4)
    matrix = _matrix(x, {"CONS.CZ.TOT.2.BS.M": other, "CONS.CZ.TOT.4.BS.M": x})
    verdict, best = val.bcs_verdict(matrix, "CONS.CZ.TOT.2.BS.M")
    assert verdict == "matches_other_official_series" and best["official_code"] == "CONS.CZ.TOT.4.BS.M"


def test_unrelated_series_is_a_mismatch_and_short_overlap_is_not_scored():
    x = _series(np.random.default_rng(5).normal(scale=10, size=100))
    unrelated = _series(np.random.default_rng(6).normal(scale=10, size=100))
    assert val.bcs_verdict(_matrix(x, {"INDU.CZ.TOT.1.BS.M": unrelated}), "INDU.CZ.TOT.1.BS.M")[0] == "mismatch"
    short = _matrix(x.iloc[:30], {"INDU.CZ.TOT.1.BS.M": x.iloc[:30]})
    assert val.bcs_verdict(short, "INDU.CZ.TOT.1.BS.M")[0] == "insufficient_overlap"


def test_ticker_geography():
    assert val.ticker_geo("EUA8EMU Index") == "EA"
    assert val.ticker_geo("EUCODE Index") == "DE"
    assert val.ticker_geo("EURTPL Index") == "PL"
    assert val.ticker_geo("EUR3CZ Index") == "CZ"
