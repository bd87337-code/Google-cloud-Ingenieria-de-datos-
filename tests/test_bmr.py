from datetime import date

import pytest

from macro_tracker.calc.bmr import (
    METHOD_KATCH,
    METHOD_MIFFLIN,
    age_on,
    estimate_bmr,
    katch_mcardle,
    mifflin_st_jeor,
)


def test_mifflin_male_hand_computed():
    # 10*80 + 6.25*180 - 5*30 + 5 = 800 + 1125 - 150 + 5
    assert mifflin_st_jeor(80, 180, 30, "M") == pytest.approx(1780.0)


def test_mifflin_female_hand_computed():
    # 10*60 + 6.25*165 - 5*25 - 161 = 600 + 1031.25 - 125 - 161
    assert mifflin_st_jeor(60, 165, 25, "F") == pytest.approx(1345.25)


def test_katch_mcardle_hand_computed():
    # masa magra = 70 * 0.85 = 59.5 ; 370 + 21.6 * 59.5
    assert katch_mcardle(70, 15) == pytest.approx(1655.2)


def test_estimate_uses_katch_when_body_fat_given():
    res = estimate_bmr(70, 175, 30, "M", body_fat_pct=15)
    assert res.method == METHOD_KATCH
    assert res.kcal == pytest.approx(1655.2)


def test_estimate_falls_back_to_mifflin_without_body_fat():
    res = estimate_bmr(80, 180, 30, "M")
    assert res.method == METHOD_MIFFLIN
    assert res.kcal == pytest.approx(1780.0)


def test_prefer_mifflin_overrides_katch():
    res = estimate_bmr(80, 180, 30, "M", body_fat_pct=20, prefer="mifflin")
    assert res.method == METHOD_MIFFLIN


@pytest.mark.parametrize(
    "kwargs",
    [
        dict(weight_kg=0, height_cm=180, age_years=30, sex="M"),
        dict(weight_kg=80, height_cm=-1, age_years=30, sex="M"),
        dict(weight_kg=80, height_cm=180, age_years=0, sex="M"),
        dict(weight_kg=80, height_cm=180, age_years=30, sex="X"),
    ],
)
def test_mifflin_rejects_invalid_input(kwargs):
    with pytest.raises(ValueError):
        mifflin_st_jeor(**kwargs)


@pytest.mark.parametrize("bf", [0, 2.9, 61, -5])
def test_katch_rejects_implausible_body_fat(bf):
    with pytest.raises(ValueError):
        katch_mcardle(80, bf)


def test_invalid_prefer_rejected():
    with pytest.raises(ValueError):
        estimate_bmr(80, 180, 30, "M", prefer="otro")


def test_age_on_birthday_boundaries():
    birth = date(2000, 9, 14)
    assert age_on(birth, date(2026, 9, 13)) == 25
    assert age_on(birth, date(2026, 9, 14)) == 26
    assert age_on(birth, date(2026, 12, 31)) == 26
