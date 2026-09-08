import math

import pytest

from fastestpath.equations import (
    exit_speed_accel_limited,
    point_mass_speed,
    predict_speed,
    radius_for_speed,
    side_friction_factor,
)


def test_regression_us_positive_super_matches_nchrp_example():
    # NCHRP 1043 worked example: R1 = 125 ft, e = +0.02.  The guide prints
    # "~23 mph" but that figure comes from a transcription slip in its own
    # example (exponent shown as 0.3891); the stated equation V = 3.4415 R^0.3861
    # gives 22.2 mph, which is what we reproduce.
    assert predict_speed(125, 0.02, "us", "regression") == pytest.approx(22.2, abs=0.2)


def test_regression_us_negative_super_matches_nchrp_example():
    # Same example: R1 = 125 ft, e = -0.02 -> 20.4 mph (guide prints ~21).
    assert predict_speed(125, -0.02, "us", "regression") == pytest.approx(20.4, abs=0.2)


def test_regression_coefficients_us():
    assert predict_speed(1, 0.02, "us", "regression") == pytest.approx(3.4415)
    assert predict_speed(1, -0.02, "us", "regression") == pytest.approx(3.4614)


def test_regression_coefficients_si():
    assert predict_speed(1, 0.02, "si", "regression") == pytest.approx(8.7602)
    assert predict_speed(1, -0.02, "si", "regression") == pytest.approx(8.6169)


def test_si_and_us_regression_are_consistent_within_one_percent():
    # 40 m ~ 131.2 ft
    v_si = predict_speed(40, 0.02, "si", "regression")          # km/h
    v_us = predict_speed(40 / 0.3048, 0.02, "us", "regression")  # mph
    assert v_si == pytest.approx(v_us * 1.609344, rel=0.01)


def test_auto_switches_to_point_mass_above_valid_range():
    r = 500  # ft, beyond the 400 ft regression limit
    assert predict_speed(r, 0.02, "us", "auto") == pytest.approx(
        point_mass_speed(r, 0.02, "us")
    )


def test_point_mass_is_self_consistent():
    v = point_mass_speed(150, 0.02, "us")
    f = side_friction_factor(v, "us")
    assert v == pytest.approx(math.sqrt(15 * 150 * (0.02 + f)), rel=1e-4)


def test_radius_for_speed_is_inverse_of_predict():
    r = radius_for_speed(25, 0.02, "us")
    assert predict_speed(r, 0.02, "us", "regression") == pytest.approx(25)


def test_speed_increases_with_radius():
    speeds = [predict_speed(r, 0.02, "us", "regression") for r in (80, 120, 200, 350)]
    assert speeds == sorted(speeds)


def test_positive_super_faster_than_negative():
    assert predict_speed(150, 0.02, "us") > predict_speed(150, -0.02, "us")


def test_exit_speed_accel_limited_reduces_to_v2_at_zero_distance():
    assert exit_speed_accel_limited(20, 0, "us") == pytest.approx(20)


def test_exit_speed_accel_limited_grows_with_distance():
    assert exit_speed_accel_limited(20, 150, "us") > 20


def test_invalid_radius_raises():
    with pytest.raises(ValueError):
        predict_speed(0, 0.02, "us")
