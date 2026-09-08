import json

import pytest

from fastestpath.cli import main
from fastestpath.model import ApproachInput, evaluate_approach


def test_evaluate_full_approach_runs_all_checks():
    res = evaluate_approach(
        ApproachInput(r1=130, r2=95, r3=160, r4=90, r5=78, units="us", name="NB")
    )
    assert {r.key for r in res.radii} == {"R1", "R2", "R3", "R4", "R5"}
    assert res.entering_stream_speed is not None
    assert res.circulating_stream_speed is not None
    assert len(res.checks) >= 5


def test_entering_stream_speed_is_average_of_r1_r2():
    res = evaluate_approach(ApproachInput(r1=130, r2=95, units="us"))
    r1 = res.by_key("R1").governing
    r2 = res.by_key("R2").governing
    assert res.entering_stream_speed == pytest.approx((r1 + r2) / 2)


def test_r1_greater_than_r2_fails_progression_check():
    res = evaluate_approach(ApproachInput(r1=200, r2=90, units="us"))
    prog = next(c for c in res.checks if c.name.startswith("R1 <= R2"))
    assert not prog.passed


def test_typical_super_uses_negative_for_circulating():
    res = evaluate_approach(ApproachInput(r2=95, units="us"), super_mode="typical")
    r2 = res.by_key("R2")
    assert r2.governing == pytest.approx(r2.speed_neg)
    assert r2.governing != pytest.approx(r2.speed_pos)


def test_normal_crown_mode_uses_positive_super_everywhere():
    res = evaluate_approach(ApproachInput(r2=95, units="us"), super_mode="normal-crown")
    r2 = res.by_key("R2")
    assert r2.governing == pytest.approx(r2.speed_pos)


def test_exit_distance_can_make_accel_limit_govern():
    # short distance from mid-R2 -> acceleration limit below the R3 prediction
    res = evaluate_approach(
        ApproachInput(r2=95, r3=300, units="us", exit_distance=10)
    )
    assert "acceleration-limited" in res.exit_speed_note
    assert res.exit_speed_governing < res.by_key("R3").governing


def test_at_least_one_radius_required():
    with pytest.raises(ValueError):
        evaluate_approach(ApproachInput(units="us"))


def test_cli_json_output(capsys):
    rc = main(["--units", "us", "--r1", "130", "--r2", "95", "--r3", "160", "--json"])
    out = json.loads(capsys.readouterr().out)
    assert out["speed_unit"] == "mph"
    assert any(r["key"] == "R1" for r in out["radii"])
    assert rc in (0, 1)


def test_cli_text_report(capsys):
    main(["--units", "us", "--r1", "130", "--r2", "95", "--r3", "160"])
    text = capsys.readouterr().out
    assert "fastest-path speed check" in text
    assert "Performance checks" in text


def test_cli_reads_json_file(tmp_path, capsys):
    p = tmp_path / "a.json"
    p.write_text(json.dumps({"name": "X", "units": "si", "r1": 40, "r2": 30}))
    main(["--input", str(p), "--json"])
    out = json.loads(capsys.readouterr().out)
    assert out["speed_unit"] == "km/h"
    assert out["name"] == "X"


def test_cli_requires_input(capsys):
    with pytest.raises(SystemExit):
        main(["--units", "us"])
