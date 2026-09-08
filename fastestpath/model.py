"""Assemble the five fastest-path radii into a full approach evaluation.

This mirrors what the "Fastest Path Spreadsheet" does: take the controlling
fastest-path radii for the entry, circulatory, exit, left-turn and right-turn
paths, predict the operating speed of each, derive the conflicting-stream
speeds, and run the NCHRP 672 speed-consistency performance checks.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from .equations import (
    SUPER_CIRCULATING,
    SUPER_ENTRY,
    Units,
    exit_speed_accel_limited,
    predict_speed,
)

# Speed differential that NCHRP 672 (Sec. 6.2.1.5) says should not be exceeded
# between consecutive geometric elements / conflicting streams.
MAX_SPEED_DIFFERENTIAL = {"us": 12.0, "si": 20.0}  # mph, km/h

# Target band for (entry speed - left-turn speed), i.e. the entering vs.
# circulating conflict (City of Cleveland / Columbus performance-check aids,
# consistent with NCHRP 672).
ENTRY_MINUS_LEFT_TARGET = {"us": (10.0, 12.0), "si": (16.0, 20.0)}

SPEED_UNIT = {"us": "mph", "si": "km/h"}
LENGTH_UNIT = {"us": "ft", "si": "m"}

SuperMode = Literal["typical", "normal-crown", "both"]

# Typical cross slope seen by each movement (NCHRP 672 Sec. 6.2.1.4).
_TYPICAL_SUPER = {
    "R1": SUPER_ENTRY,
    "R2": SUPER_CIRCULATING,
    "R3": SUPER_ENTRY,
    "R4": SUPER_CIRCULATING,
    "R5": SUPER_ENTRY,
}

_LABELS = {
    "R1": "Entry path",
    "R2": "Circulating path",
    "R3": "Exit path",
    "R4": "Left-turn path",
    "R5": "Right-turn path",
}


@dataclass
class ApproachInput:
    """Fastest-path radii for one approach (ft for ``us``, m for ``si``)."""

    r1: float | None = None
    r2: float | None = None
    r3: float | None = None
    r4: float | None = None
    r5: float | None = None
    units: Units = "us"
    name: str = "Approach"
    # Optional: path distance from the middle of the R2 path to the exit point
    # of interest, enabling the acceleration-limited exit-speed check (Eq. 9.7).
    exit_distance: float | None = None
    method: Literal["regression", "point-mass", "auto"] = "auto"

    def radii(self) -> dict[str, float]:
        out = {}
        for key in ("r1", "r2", "r3", "r4", "r5"):
            val = getattr(self, key)
            if val is not None:
                if val <= 0:
                    raise ValueError(f"{key} must be positive")
                out[key.upper()] = float(val)
        if not out:
            raise ValueError("at least one radius (r1..r5) is required")
        return out


@dataclass
class RadiusResult:
    key: str
    label: str
    radius: float
    speed_pos: float          # e = +0.02 regression
    speed_neg: float          # e = -0.02 regression
    speed_typical: float      # using the movement's typical cross slope
    governing: float          # value used in the checks (see SuperMode)


@dataclass
class Check:
    name: str
    passed: bool
    detail: str


@dataclass
class ApproachResult:
    name: str
    units: Units
    radii: list[RadiusResult]
    entering_stream_speed: float | None
    circulating_stream_speed: float | None
    exit_speed_governing: float | None
    exit_speed_note: str
    checks: list[Check] = field(default_factory=list)

    def by_key(self, key: str) -> RadiusResult | None:
        for r in self.radii:
            if r.key == key:
                return r
        return None


def _governing_speed(res: RadiusResult, mode: SuperMode) -> float:
    if mode == "normal-crown":
        return res.speed_pos
    if mode == "both":
        # Conservative: the higher of the two bounds drives the speed checks.
        return max(res.speed_pos, res.speed_neg)
    return res.speed_typical


def evaluate_approach(
    data: ApproachInput,
    super_mode: SuperMode = "typical",
) -> ApproachResult:
    units = data.units
    su = SPEED_UNIT[units]
    radii = data.radii()

    results: list[RadiusResult] = []
    for key, radius in radii.items():
        s_pos = predict_speed(radius, SUPER_ENTRY, units, data.method)
        s_neg = predict_speed(radius, SUPER_CIRCULATING, units, data.method)
        s_typ = predict_speed(radius, _TYPICAL_SUPER[key], units, data.method)
        rr = RadiusResult(
            key=key,
            label=_LABELS[key],
            radius=radius,
            speed_pos=s_pos,
            speed_neg=s_neg,
            speed_typical=s_typ,
            governing=0.0,
        )
        rr.governing = _governing_speed(rr, super_mode)
        results.append(rr)

    res = ApproachResult(
        name=data.name,
        units=units,
        radii=results,
        entering_stream_speed=None,
        circulating_stream_speed=None,
        exit_speed_governing=None,
        exit_speed_note="",
    )

    r1 = res.by_key("R1")
    r2 = res.by_key("R2")
    r3 = res.by_key("R3")
    r4 = res.by_key("R4")

    # Conflicting-stream speeds (NCHRP 672 Sec. 6.5 / Eq. 6-2):
    #   entering stream  ~ average of entry-path and circulating-path speeds
    #   circulating stream ~ left-turn-path speed
    if r1 and r2:
        res.entering_stream_speed = (r1.governing + r2.governing) / 2.0
    if r4:
        res.circulating_stream_speed = r4.governing

    # Governing exit speed (Eq. 9.7): lesser of the R3 prediction and the
    # acceleration-limited speed away from the middle of the R2 path.
    if r3:
        res.exit_speed_governing = r3.governing
        res.exit_speed_note = "R3 path-radius prediction"
        if r2 and data.exit_distance is not None:
            accel = exit_speed_accel_limited(r2.governing, data.exit_distance, units)
            if accel < r3.governing:
                res.exit_speed_governing = accel
                res.exit_speed_note = (
                    f"acceleration-limited from mid-R2 over "
                    f"{data.exit_distance:g} {LENGTH_UNIT[units]} (Eq. 9.7)"
                )

    res.checks = _run_checks(res, super_mode)
    return res


def _run_checks(res: ApproachResult, super_mode: SuperMode) -> list[Check]:
    units = res.units
    su = SPEED_UNIT[units]
    lu = LENGTH_UNIT[units]
    max_diff = MAX_SPEED_DIFFERENTIAL[units]
    checks: list[Check] = []

    r1 = res.by_key("R1")
    r2 = res.by_key("R2")
    r3 = res.by_key("R3")
    r4 = res.by_key("R4")
    r5 = res.by_key("R5")

    # 1. Radius progression R1 <= R2 <= R3 (NCHRP 672 Sec. 6.2.1.5).
    if r1 and r2:
        ok = r1.radius <= r2.radius
        checks.append(
            Check(
                "R1 <= R2 (entry radius not larger than circulating radius)",
                ok,
                f"R1 = {r1.radius:g} {lu}, R2 = {r2.radius:g} {lu}"
                + ("" if ok else "  -- tighten the entry or enlarge the central island"),
            )
        )
    if r2 and r3:
        ok = r3.radius >= r2.radius
        checks.append(
            Check(
                "R3 >= R2 (exit radius not smaller than circulating radius)",
                ok,
                f"R2 = {r2.radius:g} {lu}, R3 = {r3.radius:g} {lu}",
            )
        )

    # 2. Entry -> circulating speed differential.
    if r1 and r2:
        diff = abs(r1.governing - r2.governing)
        ok = diff <= max_diff
        checks.append(
            Check(
                f"|V(R1) - V(R2)| <= {max_diff:g} {su}",
                ok,
                f"V(R1) = {r1.governing:.1f} {su}, V(R2) = {r2.governing:.1f} {su}, "
                f"differential = {diff:.1f} {su}",
            )
        )

    # 3. Entering vs. circulating conflict: V(R1) - V(R4) in target band.
    if r1 and r4:
        diff = r1.governing - r4.governing
        lo, hi = ENTRY_MINUS_LEFT_TARGET[units]
        ok = lo <= diff <= hi
        checks.append(
            Check(
                f"V(R1) - V(R4) within {lo:g}-{hi:g} {su} target band",
                ok,
                f"V(R1) = {r1.governing:.1f} {su}, V(R4) = {r4.governing:.1f} {su}, "
                f"difference = {diff:.1f} {su}",
            )
        )

    # 4. Conflicting-stream speed differential (entering vs. circulating).
    if res.entering_stream_speed is not None and res.circulating_stream_speed is not None:
        diff = abs(res.entering_stream_speed - res.circulating_stream_speed)
        ok = diff <= max_diff
        checks.append(
            Check(
                f"|entering stream - circulating stream| <= {max_diff:g} {su}",
                ok,
                f"entering = {res.entering_stream_speed:.1f} {su}, "
                f"circulating = {res.circulating_stream_speed:.1f} {su}, "
                f"differential = {diff:.1f} {su}",
            )
        )

    # 5. Right-turn vs. through: R5 should not govern a higher speed than R1.
    if r1 and r5:
        ok = r5.governing <= r1.governing + 1e-6
        checks.append(
            Check(
                "V(R5) <= V(R1) (right turn not faster than the through entry)",
                ok,
                f"V(R1) = {r1.governing:.1f} {su}, V(R5) = {r5.governing:.1f} {su}",
            )
        )

    return checks
