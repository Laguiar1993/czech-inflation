"""Table A6 transcription and its consistency with the paper-replication runner."""
from tools.paper_replication.a6_catalog import BY_NUMBER, PAPER_TRANSFORMS, ROWS, ecfin_nsa_code

# Transform codes read from the rendered Table A6 pages (PDF pages 36-39) and
# the PDF text layer, 12 September 2026.
PRINTED = {
    **{n: 0 for n in (1, 2, 11, 12, 13, 14, 15, 16, 17, 18, 24, 27, 28, 32, 43, 44,
                      53, 54, 55, 60, 65, 66, 69, 70, 71, 72)},
    **{n: 2 for n in (22, 23, 25, 26, 45, 46, 47, 48, 49, 50, 51, 52, 56, 57, 58, 59,
                      61, 62, 63, 64)},
    **{n: 3 for n in (3, 4, 5, 6, 7, 8, 9, 10, 19, 20, 21, 29, 30, 31, 33, 34, 35, 36,
                      37, 38, 39, 40, 41, 42, 67, 68)},
}


def test_catalog_has_72_rows_in_table_order():
    assert [row.number for row in ROWS] == list(range(1, 73))
    assert set(PRINTED) == set(range(1, 73))


def test_catalog_transforms_match_the_printed_table():
    assert PAPER_TRANSFORMS == PRINTED


def test_runner_uses_the_printed_transforms():
    from paper_replication_experiment import A6

    assert {row.number: row.transform for row in A6} == PAPER_TRANSFORMS


def test_construction_confidence_is_differenced():
    # The earlier transcription used a level for row 38; the table prints 3.
    assert BY_NUMBER[38].transform == 3


def test_survey_rows_carry_official_codes_for_their_geography():
    for row in ROWS:
        if row.eurostat:
            assert row.ecfin, row.number
            assert row.ecfin.split(".")[1] == row.geo, row.number
            assert row.ecfin.split(".")[4] in ("BS", "F4S", "F5S", "F7S"), row.number
    assert {r.number for r in ROWS if r.kind == "survey"} <= {r.number for r in ROWS if r.eurostat}


def test_euro_area_rows_are_printed_and_czech_price_balances_are_interpretations():
    assert BY_NUMBER[27].geo == BY_NUMBER[28].geo == "EA"
    assert BY_NUMBER[27].geo_basis == "printed"
    assert BY_NUMBER[71].geo == BY_NUMBER[72].geo == "CZ"
    assert BY_NUMBER[71].geo_basis == BY_NUMBER[72].geo_basis == "interpretation"


def test_unadjusted_ecfin_code():
    assert ecfin_nsa_code("INDU.CZ.TOT.1.BS.M") == "INDU.CZ.TOT.1.B.M"
    assert ecfin_nsa_code("BUIL.CZ.TOT.2.F7S.M") == "BUIL.CZ.TOT.2.F7.M"
    assert ecfin_nsa_code(None) is None
