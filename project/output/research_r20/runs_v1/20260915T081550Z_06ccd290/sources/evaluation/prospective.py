"""Conservative classification of the existing shadow log.

This checks necessary conditions only. An archive flag is not an integrity
verification, and an explicit release stage is not a verified event identity.
Until completion timestamps, source vintages, archive hashes and the matching
survey receipt are validated, even timely rows remain unverified evidence.
"""
import pandas as pd


def classify_shadow_row(row) -> str:
    stage = row.get('release_stage')
    if stage == 'pre_final':
        return 'FINAL_RELEASE_ONLY'
    if stage not in ('pre_flash', 'pre_release'):
        return 'UNVERIFIED_STAGE'
    spec = str(row.get('spec', ''))
    if spec.startswith(('v2.0', 'v2.1', 'v2.2', 'v2.3')):
        return 'INELIGIBLE_CONSTRUCTION'
    # Parse literal booleans explicitly: bool('False') and bool(NaN) are True.
    if str(row.get('archive_ok', '')).lower() not in ('true', '1', '1.0'):
        return 'INELIGIBLE_ARCHIVE'
    n = pd.to_numeric(row.get('n_imputed'), errors='coerce')
    if pd.isna(n) or n != 0:
        return 'INCOMPLETE_INPUTS'
    try:
        run = pd.Timestamp(row.get('run_ts'))
        release = pd.Timestamp(row.get('release_ts'))
    except (ValueError, TypeError):
        return 'UNVERIFIED_CLOCK'
    if pd.isna(release):
        return 'PENDING_RELEASE'
    # Do not assign the machine's local zone retrospectively to a naive log.
    if pd.isna(run) or run.tzinfo is None or release.tzinfo is None:
        return 'UNVERIFIED_CLOCK'
    if run >= release:
        return 'RETROSPECTIVE'
    return 'TIMELY_UNVERIFIED'
