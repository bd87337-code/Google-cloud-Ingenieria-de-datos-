import pandas as pd
import pytest

from datetime import date

from macro_tracker.calc.targets import (
    FLAG_MINIMUMS_EXCEED_KCAL,
    FLAG_REDUCED_TO_FIT,
    calorie_target,
    formula_tdee_series,
    goal_adjustment_kcal,
    macro_targets,
    total_daily_energy,
)


def test_total_daily_energy():
    assert total_daily_energy(1780, "moderate") == pytest.approx(1780 * 1.55)


def test_total_daily_energy_unknown_level():
    with pytest.raises(ValueError):
        total_daily_energy(1780, "astronaut")


@pytest.mark.parametrize(
    "goal,rate,expected",
    [
        ("lose", 0.5, -550.0),   # 0.5 * 7700 / 7
        ("gain", 0.25, 275.0),
        ("maintain", 0.5, 0.0),  # mantener ignora el ritmo
        ("lose", 0.0, 0.0),
    ],
)
def test_goal_adjustment(goal, rate, expected):
    assert goal_adjustment_kcal(goal, rate) == pytest.approx(expected)


def test_goal_adjustment_rejects_negative_rate_and_unknown_goal():
    with pytest.raises(ValueError):
        goal_adjustment_kcal("lose", -0.5)
    with pytest.raises(ValueError):
        goal_adjustment_kcal("bulk", 0.5)


def test_calorie_target_without_floor():
    t = calorie_target(tdee_kcal=2700, bmr_kcal=1800, goal="lose", rate_kg_week=0.5)
    assert t.kcal == pytest.approx(2150)
    assert not t.floor_applied
    assert t.effective_rate_kg_week == pytest.approx(-0.5)


def test_calorie_target_never_below_bmr():
    t = calorie_target(tdee_kcal=2000, bmr_kcal=1800, goal="lose", rate_kg_week=1.0)
    assert t.unfloored_kcal == pytest.approx(900)
    assert t.kcal == 1800
    assert t.floor_applied
    # solo se logra (1800 - 2000) * 7 / 7700 kg/semana
    assert t.effective_rate_kg_week == pytest.approx(-200 * 7 / 7700)


def test_calorie_target_gain_is_above_tdee():
    t = calorie_target(2500, 1800, "gain", 0.25)
    assert t.kcal == pytest.approx(2775)
    assert not t.floor_applied


def test_macro_targets_maintain_hand_computed():
    m = macro_targets(kcal=2500, weight_kg=80, goal="maintain")
    assert m.protein_g == pytest.approx(152.0)       # 1.9 g/kg (punto medio) * 80
    assert m.fat_g == pytest.approx(0.25 * 2500 / 9)  # 25 % de kcal > mínimo 48 g
    assert m.carbs_g == pytest.approx((2500 - 4 * 152 - 9 * (0.25 * 2500 / 9)) / 4)
    assert m.kcal_from_macros == pytest.approx(2500)
    assert m.flags == ()
    assert m.protein_range_g == pytest.approx((128.0, 176.0))


def test_macro_targets_lose_uses_upper_protein():
    m = macro_targets(kcal=2200, weight_kg=80, goal="lose")
    assert m.protein_g_per_kg == pytest.approx(2.2)
    assert m.protein_g == pytest.approx(176.0)


def test_macro_targets_fat_floor_binds_at_low_kcal():
    # 25 % de 1500 kcal = 41.7 g < mínimo 0.6 * 90 = 54 g
    m = macro_targets(kcal=1500, weight_kg=90, goal="maintain")
    assert m.fat_g == pytest.approx(54.0)
    assert m.fat_floor_g == pytest.approx(54.0)


def test_macro_targets_shrinks_to_fit_before_flagging():
    m = macro_targets(kcal=1400, weight_kg=100, goal="lose")
    assert FLAG_REDUCED_TO_FIT in m.flags
    assert FLAG_MINIMUMS_EXCEED_KCAL not in m.flags
    assert m.fat_g == pytest.approx(60.0)             # en su mínimo
    assert m.protein_g == pytest.approx(215.0)        # recortada, sobre su mínimo (160)
    assert m.carbs_g == pytest.approx(0.0)
    assert m.kcal_from_macros == pytest.approx(1400)


def test_macro_targets_flags_when_minimums_do_not_fit():
    m = macro_targets(kcal=1000, weight_kg=100, goal="lose")
    assert FLAG_MINIMUMS_EXCEED_KCAL in m.flags
    assert m.carbs_g == 0.0
    assert m.protein_g == pytest.approx(160.0)  # mínimo del rango
    assert m.fat_g == pytest.approx(60.0)


def test_macro_targets_use_protein_reference_weight():
    m = macro_targets(kcal=2500, weight_kg=100, goal="maintain", protein_reference_kg=75)
    assert m.protein_g == pytest.approx(1.9 * 75)
    # la grasa mínima sigue usando el peso total
    assert m.fat_floor_g == pytest.approx(60.0)


def test_formula_tdee_series_uses_katch_only_when_bf_present():
    idx = pd.date_range("2026-03-01", periods=3)
    weight = pd.Series([80.0, float("nan"), 79.0], index=idx)
    bf = pd.Series([float("nan"), 20.0, 20.0], index=idx)
    out = formula_tdee_series(weight, bf, "M", 180, date(1996, 1, 1), "moderate")
    assert list(out.index) == [idx[0], idx[2]]  # el día sin peso se omite
    assert out.loc[idx[0], "method"] == "mifflin_st_jeor"
    assert out.loc[idx[2], "method"] == "katch_mcardle"
    # edad 30 el 2026-03-01: 800 + 1125 - 150 + 5 = 1780
    assert out.loc[idx[0], "bmr"] == pytest.approx(1780.0)
    assert out.loc[idx[0], "tdee"] == pytest.approx(1780.0 * 1.55)
    # Katch: 370 + 21.6 * (79 * 0.8)
    assert out.loc[idx[2], "bmr"] == pytest.approx(370 + 21.6 * 79 * 0.8)


def test_formula_tdee_series_empty():
    idx = pd.date_range("2026-03-01", periods=2)
    out = formula_tdee_series(pd.Series([float("nan")] * 2, index=idx), None, "M", 180, date(1996, 1, 1), "light")
    assert out.empty
