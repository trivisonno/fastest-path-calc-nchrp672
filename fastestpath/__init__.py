"""Fastest-path speed prediction for roundabouts (NCHRP 672 / NCHRP 1043).

A Python re-implementation of the "Fastest Path Spreadsheet": given the
controlling fastest-path radii (R1-R5) measured from a roundabout layout,
predict the operating speed of each vehicle movement and run the
speed-consistency performance checks.
"""

from .equations import (
    predict_speed,
    exit_speed_accel_limited,
    point_mass_speed,
    SUPER_ENTRY,
    SUPER_CIRCULATING,
)
from .model import ApproachInput, evaluate_approach

__version__ = "1.0.0"

__all__ = [
    "predict_speed",
    "exit_speed_accel_limited",
    "point_mass_speed",
    "SUPER_ENTRY",
    "SUPER_CIRCULATING",
    "ApproachInput",
    "evaluate_approach",
    "__version__",
]
