"""Speed-prediction equations from NCHRP Report 672 / NCHRP Report 1043.

Two families of equations are implemented:

1. The theoretical-maximum-speed regression used for roundabout fastest-path
   checks (NCHRP 1043 Eq. 9.3 / 9.4, originally Rodegerdts et al., NCHRP 672).
   These are power curves fit through the AASHTO speed-radius relationship
   (point-mass model with speed-dependent side friction) for the two standard
   cross-slope assumptions, valid for R <= 400 ft (120 m):

       e = +0.02 :  V = 3.4415 * R^0.3861     (US: V mph, R ft)
       e = -0.02 :  V = 3.4614 * R^0.3673
       e = +0.02 :  V = 8.7602 * R^0.3861     (SI: V km/h, R m)
       e = -0.02 :  V = 8.6169 * R^0.3673

2. The underlying point-mass relationship (NCHRP 672 Eq. 6-1):

       V = sqrt(127 * R * (e + f))            (SI)
       V = sqrt( 15 * R * (e + f))            (US customary)

   used as a fall-back above the regression's valid range, with side-friction
   factors from the AASHTO low-speed (intersection) curve.
"""

from __future__ import annotations

import math
from typing import Literal

Units = Literal["us", "si"]

# Standard cross-slope assumptions (NCHRP 672 Sec. 6.2.1.4):
#   +0.02 for entry and exit curves, -0.02 for curves around the central island.
SUPER_ENTRY = 0.02
SUPER_CIRCULATING = -0.02

# Regression coefficients: units -> superelevation sign -> (a, b) in V = a * R^b
_REGRESSION = {
    "us": {
        "pos": (3.4415, 0.3861),  # e = +0.02, R ft, V mph
        "neg": (3.4614, 0.3673),  # e = -0.02
    },
    "si": {
        "pos": (8.7602, 0.3861),  # e = +0.02, R m, V km/h
        "neg": (8.6169, 0.3673),  # e = -0.02
    },
}

# Upper bound of the regression's stated validity.
REGRESSION_MAX_R = {"us": 400.0, "si": 120.0}

# AASHTO side-friction factor vs. speed for low-speed / intersection curves
# (NCHRP 672 Exhibits 6-8 / 6-9).  Linearly interpolated / end-clamped.
_SIDE_FRICTION = {
    "us": [  # (speed mph, f)
        (15.0, 0.32),
        (20.0, 0.27),
        (25.0, 0.23),
        (30.0, 0.20),
        (35.0, 0.18),
        (40.0, 0.16),
    ],
    "si": [  # (speed km/h, f)
        (20.0, 0.35),
        (30.0, 0.28),
        (40.0, 0.23),
        (50.0, 0.19),
        (60.0, 0.17),
    ],
}

_POINT_MASS_K = {"us": 15.0, "si": 127.0}


def _interp(table, x: float) -> float:
    """Linear interpolation with flat extrapolation past the table ends."""
    if x <= table[0][0]:
        return table[0][1]
    if x >= table[-1][0]:
        return table[-1][1]
    for (x0, y0), (x1, y1) in zip(table, table[1:]):
        if x0 <= x <= x1:
            t = (x - x0) / (x1 - x0)
            return y0 + t * (y1 - y0)
    return table[-1][1]  # pragma: no cover


def side_friction_factor(speed: float, units: Units = "us") -> float:
    """AASHTO low-speed side-friction factor for the given speed."""
    return _interp(_SIDE_FRICTION[units], speed)


def point_mass_speed(radius: float, superelevation: float, units: Units = "us") -> float:
    """Solve the point-mass equation V = sqrt(k * R * (e + f(V))) for V.

    ``f`` depends on ``V``, so the equation is solved by fixed-point iteration.
    """
    k = _POINT_MASS_K[units]
    v = 20.0 if units == "us" else 30.0  # seed
    for _ in range(100):
        f = side_friction_factor(v, units)
        nxt = math.sqrt(max(k * radius * (superelevation + f), 0.0))
        if abs(nxt - v) < 1e-6:
            v = nxt
            break
        v = nxt
    return v


def predict_speed(
    radius: float,
    superelevation: float = SUPER_ENTRY,
    units: Units = "us",
    method: Literal["regression", "point-mass", "auto"] = "auto",
) -> float:
    """Predict the theoretical fastest-path speed for one path radius.

    Parameters
    ----------
    radius:
        Fastest-path radius (ft for ``units="us"``, m for ``units="si"``).
    superelevation:
        Cross slope as a decimal.  The regression only distinguishes the sign
        (``>= 0`` uses the +0.02 curve, ``< 0`` uses the -0.02 curve); the
        point-mass method uses the value directly.
    units:
        ``"us"`` (mph, ft) or ``"si"`` (km/h, m).
    method:
        ``"regression"`` forces NCHRP 1043 Eq. 9.3/9.4.
        ``"point-mass"`` forces NCHRP 672 Eq. 6-1.
        ``"auto"`` (default) uses the regression within its valid range and the
        point-mass model above it.

    Returns
    -------
    Predicted speed (mph or km/h).
    """
    if radius <= 0:
        raise ValueError("radius must be positive")

    if method == "auto":
        method = "regression" if radius <= REGRESSION_MAX_R[units] else "point-mass"

    if method == "point-mass":
        return point_mass_speed(radius, superelevation, units)

    a, b = _REGRESSION[units]["pos" if superelevation >= 0 else "neg"]
    return a * radius ** b


def radius_for_speed(
    speed: float,
    superelevation: float = SUPER_ENTRY,
    units: Units = "us",
) -> float:
    """Inverse of the regression: radius that yields ``speed``."""
    if speed <= 0:
        raise ValueError("speed must be positive")
    a, b = _REGRESSION[units]["pos" if superelevation >= 0 else "neg"]
    return (speed / a) ** (1.0 / b)


# Acceleration between the midpoint of the R2 path and the exit point of
# interest (NCHRP 1043 Eq. 9.7).
_EXIT_ACCEL = {"us": 6.9, "si": 2.1}  # ft/s^2, m/s^2
_SPEED_TO_BASE = {"us": 1.0 / 1.46667, "si": 1.0 / 3.6}  # mph->ft/s, km/h->m/s


def exit_speed_accel_limited(
    v2: float,
    distance: float,
    units: Units = "us",
) -> float:
    """Exit speed limited by acceleration away from the circulating path.

    NCHRP 1043 Eq. 9.7::

        V3 = (1 / c) * sqrt( (c * V2)^2 + 2 * a23 * d23 )

    where ``c`` converts the reported speed unit to ft/s (or m/s), ``a23`` is
    6.9 ft/s^2 (2.1 m/s^2) and ``d23`` is the path distance from the middle of
    the R2 path to the exit point of interest.
    """
    if distance < 0:
        raise ValueError("distance must be non-negative")
    c = _SPEED_TO_BASE[units]
    a23 = _EXIT_ACCEL[units]
    base = math.sqrt((c * v2) ** 2 + 2.0 * a23 * distance)
    return base / c


def exit_speed(
    v3_path: float,
    v2: float | None = None,
    distance: float | None = None,
    units: Units = "us",
) -> float:
    """Governing exit speed: the lesser of the path-radius prediction and the
    acceleration-limited speed (NCHRP 1043 Eq. 9.7).  If ``distance`` is not
    supplied, only the path-radius prediction is returned.
    """
    if v2 is None or distance is None:
        return v3_path
    return min(v3_path, exit_speed_accel_limited(v2, distance, units))
