"""Command-line interface for the NCHRP 672 fastest-path speed calculator."""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from . import __version__
from .equations import REGRESSION_MAX_R
from .model import (
    LENGTH_UNIT,
    SPEED_UNIT,
    ApproachInput,
    ApproachResult,
    evaluate_approach,
)


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="fastest-path",
        description=(
            "Predict roundabout fastest-path operating speeds from the "
            "controlling radii R1-R5 and run the NCHRP 672 speed-consistency "
            "performance checks."
        ),
        epilog=(
            "Radii are entry (R1), circulatory (R2), exit (R3), left-turn (R4) "
            "and right-turn (R5) fastest-path radii, measured from the layout. "
            "Units: ft/mph for --units us, m/km/h for --units si."
        ),
    )
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")

    src = p.add_argument_group("radius input (either flags or --input)")
    for r, desc in [
        ("r1", "entry path radius"),
        ("r2", "circulatory path radius"),
        ("r3", "exit path radius"),
        ("r4", "left-turn path radius"),
        ("r5", "right-turn path radius"),
    ]:
        src.add_argument(f"--{r}", type=float, metavar="R", help=f"{desc}")
    src.add_argument(
        "--input",
        metavar="FILE",
        help="JSON file with one approach object or a list of them "
        "(keys: r1..r5, name, units, exit_distance, method). Use '-' for stdin.",
    )

    opt = p.add_argument_group("options")
    opt.add_argument(
        "--units",
        choices=["us", "si"],
        default="us",
        help="us = feet / mph (default), si = metres / km/h",
    )
    opt.add_argument(
        "--name", default="Approach", help="label for the approach in the report"
    )
    opt.add_argument(
        "--exit-distance",
        type=float,
        metavar="D",
        help="path distance from the middle of the R2 path to the exit point "
        "of interest; enables the acceleration-limited exit-speed check (Eq. 9.7)",
    )
    opt.add_argument(
        "--super-mode",
        choices=["typical", "normal-crown", "both"],
        default="typical",
        help="cross slope used for the governing speed: 'typical' (+0.02 entry/"
        "exit/right, -0.02 circulating/left; default), 'normal-crown' (+0.02 "
        "everywhere, conservative concept-level default) or 'both' (uses the "
        "higher bound)",
    )
    opt.add_argument(
        "--method",
        choices=["auto", "regression", "point-mass"],
        default="auto",
        help="speed equation: 'regression' = NCHRP 1043 Eq. 9.3/9.4, "
        "'point-mass' = NCHRP 672 Eq. 6-1, 'auto' = regression within its valid "
        f"range ({REGRESSION_MAX_R['us']:g} ft / {REGRESSION_MAX_R['si']:g} m) "
        "then point-mass (default)",
    )
    opt.add_argument(
        "--json",
        action="store_true",
        dest="as_json",
        help="emit results as JSON instead of a formatted report",
    )
    return p


def _inputs_from_args(args: argparse.Namespace) -> list[ApproachInput]:
    if args.input:
        raw = sys.stdin.read() if args.input == "-" else open(args.input).read()
        payload = json.loads(raw)
        objs = payload if isinstance(payload, list) else [payload]
        out = []
        for o in objs:
            out.append(
                ApproachInput(
                    r1=o.get("r1"),
                    r2=o.get("r2"),
                    r3=o.get("r3"),
                    r4=o.get("r4"),
                    r5=o.get("r5"),
                    units=o.get("units", args.units),
                    name=o.get("name", args.name),
                    exit_distance=o.get("exit_distance", args.exit_distance),
                    method=o.get("method", args.method),
                )
            )
        return out

    if all(getattr(args, r) is None for r in ("r1", "r2", "r3", "r4", "r5")):
        raise SystemExit(
            "error: provide at least one of --r1..--r5, or --input FILE"
        )
    return [
        ApproachInput(
            r1=args.r1,
            r2=args.r2,
            r3=args.r3,
            r4=args.r4,
            r5=args.r5,
            units=args.units,
            name=args.name,
            exit_distance=args.exit_distance,
            method=args.method,
        )
    ]


def _result_to_dict(res: ApproachResult) -> dict[str, Any]:
    return {
        "name": res.name,
        "units": res.units,
        "speed_unit": SPEED_UNIT[res.units],
        "length_unit": LENGTH_UNIT[res.units],
        "radii": [
            {
                "key": r.key,
                "label": r.label,
                "radius": r.radius,
                "speed_e_pos_0_02": round(r.speed_pos, 2),
                "speed_e_neg_0_02": round(r.speed_neg, 2),
                "speed_typical": round(r.speed_typical, 2),
                "governing_speed": round(r.governing, 2),
            }
            for r in res.radii
        ],
        "entering_stream_speed": _round(res.entering_stream_speed),
        "circulating_stream_speed": _round(res.circulating_stream_speed),
        "exit_speed_governing": _round(res.exit_speed_governing),
        "exit_speed_note": res.exit_speed_note,
        "checks": [
            {"name": c.name, "passed": c.passed, "detail": c.detail}
            for c in res.checks
        ],
        "all_checks_passed": all(c.passed for c in res.checks),
    }


def _round(v: float | None) -> float | None:
    return None if v is None else round(v, 2)


def _format_report(res: ApproachResult) -> str:
    su = SPEED_UNIT[res.units]
    lu = LENGTH_UNIT[res.units]
    lines: list[str] = []
    lines.append("=" * 66)
    lines.append(f" {res.name}  --  NCHRP 672 fastest-path speed check ({res.units})")
    lines.append("=" * 66)
    lines.append("")
    lines.append(
        f" {'Path':<18}{'R (' + lu + ')':>10}{'e=+2% ':>10}{'e=-2% ':>10}"
        f"{'govern':>10}"
    )
    lines.append(f" {'-' * 18}{'-' * 10:>10}{'-' * 10:>10}{'-' * 10:>10}{'-' * 10:>10}")
    for r in res.radii:
        lines.append(
            f" {r.key + ' ' + r.label:<18}{r.radius:>10.1f}"
            f"{r.speed_pos:>10.1f}{r.speed_neg:>10.1f}{r.governing:>10.1f}"
        )
    lines.append("")
    lines.append(f" Speeds in {su}. 'govern' per --super-mode.")
    lines.append("")

    if res.entering_stream_speed is not None:
        lines.append(
            f" Entering-stream speed   (avg V(R1),V(R2)) : "
            f"{res.entering_stream_speed:.1f} {su}"
        )
    if res.circulating_stream_speed is not None:
        lines.append(
            f" Circulating-stream speed (V(R4))          : "
            f"{res.circulating_stream_speed:.1f} {su}"
        )
    if res.exit_speed_governing is not None:
        lines.append(
            f" Governing exit speed                      : "
            f"{res.exit_speed_governing:.1f} {su}  [{res.exit_speed_note}]"
        )
    lines.append("")
    lines.append(" Performance checks")
    lines.append(" " + "-" * 64)
    if not res.checks:
        lines.append("   (not enough radii supplied to run any checks)")
    for c in res.checks:
        mark = "PASS" if c.passed else "FAIL"
        lines.append(f"   [{mark}] {c.name}")
        lines.append(f"          {c.detail}")
    lines.append("")
    overall = "ALL CHECKS PASS" if all(c.passed for c in res.checks) else "REVIEW REQUIRED"
    lines.append(f" => {overall}")
    lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    try:
        inputs = _inputs_from_args(args)
        results = [evaluate_approach(i, args.super_mode) for i in inputs]
    except (ValueError, OSError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if args.as_json:
        out = [_result_to_dict(r) for r in results]
        print(json.dumps(out if len(out) > 1 else out[0], indent=2))
    else:
        print("\n".join(_format_report(r) for r in results))

    return 0 if all(c.passed for r in results for c in r.checks) else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
