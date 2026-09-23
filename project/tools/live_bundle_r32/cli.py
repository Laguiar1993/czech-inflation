"""Standalone R31C bundle inspection/readiness and explicit forecast execution."""
import argparse
from contextlib import redirect_stdout
import json
import math
from pathlib import Path
import sys

import pandas as pd

from .adapter import ROOT, load_bundle, load_calendar, target_month, decision_clock, prepare_frames, readiness
from .runner import runtime_readiness, calculate


class Parser(argparse.ArgumentParser):
    def error(self, message):
        raise ValueError(message)


def json_safe(value):
    if isinstance(value, dict):
        return {str(k): json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(v) for v in value]
    if hasattr(value, 'tolist'):
        return json_safe(value.tolist())
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if hasattr(value, 'isoformat'):
        return value.isoformat()
    return value


def main(argv=None):
    parser = Parser(description=__doc__)
    parser.add_argument('command', choices=['inspect', 'readiness', 'run'])
    parser.add_argument('--bundle', type=Path, required=True)
    parser.add_argument('--target', required=True, help='YYYY-MM; never inferred or extended')
    parser.add_argument('--as-of', required=True, help='ISO timestamp with timezone/offset')
    parser.add_argument('--live-calendar', type=Path, help='Separate sourced append-only release calendar CSV')
    parser.add_argument('--output', type=Path, help='New JSON file under output/live_bundle_r32; default stdout only')
    output = None
    phase = 'invalid_arguments'
    try:
        args = parser.parse_args(argv)
        target, clock = target_month(args.target), decision_clock(args.as_of)
        if args.output:
            output = args.output.resolve()
            if not output.is_relative_to((ROOT / 'output/live_bundle_r32').resolve()):
                raise ValueError('--output must be under output/live_bundle_r32')
            if output.exists():
                raise ValueError('--output already exists; choose a new report path')
        phase = 'invalid_input'
        loaded = load_bundle(args.bundle, ROOT)
        calendar, calendar_info = load_calendar(ROOT / 'data/release_calendar_cz_cpi.csv', args.live_calendar, clock)
        frames, fx = prepare_frames(loaded, target, clock, calendar)
        data = readiness(frames, target, clock, calendar, fx=fx)
        runtime = runtime_readiness()
        ready = data['data_ready'] and runtime['ready']
        report = {'schema_version': 'live_bundle_r32/v1', 'command': args.command, 'target': str(target),
                  'as_of': args.as_of, 'decision_time_prague': pd.Timestamp(args.as_of).tz_convert('Europe/Prague').isoformat(),
                  'status': 'ready_for_calculation' if ready else 'blocked', 'ready_for_calculation': ready,
                  'forecast_available': False, 'ready_for_first_release': False, 'main_model': 'HARD_BASE',
                  'variant': 'R31C_C123', 'readiness': data, 'runtime': runtime, 'calendar': calendar_info,
                  'fx': fx, 'provenance': loaded.provenance,
                  'reasons': data['reasons'] + runtime['reasons'],
                  'limitations': ['Latest-vintage Bloomberg data with publication rules; historical clocks are reconstructed replay, not a prospective archive.',
                                  'Readiness never extrapolates missing monthly observations or invents release dates.',
                                  'Farm prices, documented energy announcements, basket weights and X13 remain external/static requirements.',
                                  'This entry point calculates h0 only; it does not refresh sources or extend the monthly path.']}
        if args.command == 'run' and ready:
            phase = 'model_execution_failed'
            with redirect_stdout(sys.stderr):
                result = calculate(frames, target, args.as_of, calendar)
            failures = []
            if not result.get('ready_for_first_release'):
                failures.append({'code': 'model_not_ready', 'missing_inputs': result.get('missing_inputs', [])})
            if result.get('food_diagnostics', {}).get('method') != 'x13':
                failures.append({'code': 'food_model_fallback', 'diagnostics': result.get('food_diagnostics')})
            for policy, details in result.get('diagnostics', {}).items():
                if policy == 'hard' and details.get('residual_forest', {}).get('fallback_used'):
                    failures.append({'code': 'residual_model_fallback', 'diagnostics': details['residual_forest']})
            points = result.get('points_mm_pct', {})
            if any(not math.isfinite(points.get(k, float('nan'))) for k in ('HARD_BASE', 'HARD_HALF', 'HARD_FULL')):
                failures.append({'code': 'nonfinite_forecast'})
            if failures:
                report.update(status='blocked', reasons=report['reasons'] + failures, ready_for_calculation=False)
            else:
                # Expose only the independent HARD roster. The existing calculate
                # also computes sentiment comparators internally for parity.
                result['points_mm_pct'] = {k: points[k] for k in ('HARD_BASE', 'HARD_HALF', 'HARD_FULL')}
                report.update(status='calculated', forecast_available=True, ready_for_first_release=True, forecast=result)
        code = 0 if report['status'] in ('ready_for_calculation', 'calculated') else 2
    except (ValueError, OSError, KeyError, TypeError, ImportError, RuntimeError) as exc:
        report = {'schema_version': 'live_bundle_r32/v1', 'status': 'blocked', 'forecast_available': False,
                  'ready_for_calculation': False, 'ready_for_first_release': False,
                  'reasons': [{'code': phase, 'error_type': type(exc).__name__, 'message': str(exc)}]}
        code = 2
        output = None
    text = json.dumps(json_safe(report), indent=2, allow_nan=False)
    if output:
        try:
            output.parent.mkdir(parents=True, exist_ok=True)
            with output.open('x', encoding='utf-8', newline='\n') as f:
                f.write(text + '\n')
        except OSError as exc:
            report = {'status': 'blocked', 'forecast_available': False, 'reasons': [{'code': 'output_error', 'message': str(exc)}]}
            text = json.dumps(report, indent=2); code = 2
    print(text)
    return code
