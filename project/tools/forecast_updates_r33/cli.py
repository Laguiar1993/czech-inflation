"""Explicit local refresh/readiness and revision CLI; stdout is always JSON."""
import argparse
from pathlib import Path

from . import workflow as w


class Parser(argparse.ArgumentParser):
    def error(self, message):
        raise ValueError(message)


def main(argv=None):
    p = Parser(description=__doc__)
    sub = p.add_subparsers(dest="command", required=True)
    for command in ("run", "readiness"):
        s = sub.add_parser(command)
        s.add_argument("--bundle", required=True, type=Path)
        s.add_argument("--target", required=True)
        s.add_argument("--as-of", required=True)
        s.add_argument("--mode", required=True, choices=("replay", "prospective"))
        s.add_argument("--live-calendar", type=Path)
        s.add_argument("--path", type=Path, dest="path_file")
        s.add_argument("--timeout", type=float, default=120)
        s.add_argument("--store", type=Path, default=w.OUTPUT)
    s = sub.add_parser("compare")
    s.add_argument("--old", type=Path, required=True)
    s.add_argument("--new", type=Path, required=True)
    s.add_argument("--output", type=Path, help="New comparison JSON under output/forecast_updates_r33")
    try:
        args = p.parse_args(argv)
        if args.command == "compare":
            report = w.compare_runs(args.old, args.new)
            if args.output:
                dest = w.owned(args.output, output_only=True)
                dest.parent.mkdir(parents=True, exist_ok=True)
                w.write_new(dest, report)
            code = 0 if report["status"] == "ok" else 2
        else:
            w.owned(args.store, output_only=True)
            report = w.record(args.bundle, args.target, args.as_of, args.mode, store=args.store,
                              command=args.command, live_calendar=args.live_calendar,
                              path_file=args.path_file, timeout=args.timeout)
            code = 0 if report["status"] in ("successful", "ready") and report["publication"]["status"] != "failed" else 2
    except (OSError, TypeError, ValueError, KeyError) as exc:
        report, code = {"status": "blocked", "reason": f"{type(exc).__name__}: {exc}"}, 2
    print(w.encoded(report).decode("utf-8"), end="")
    return code
