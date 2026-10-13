import pandas as pd
import pytest

from macro_tracker.calc.series import (
    daily_index,
    moving_average,
    valid_food_day_mask,
    weekly_intake,
)


def test_daily_index_inclusive():
    idx = daily_index("2026-01-01", "2026-01-05")
    assert len(idx) == 5 and idx[-1] == pd.Timestamp("2026-01-05")


def test_moving_average_ignores_missing_days():
    idx = daily_index("2026-01-01", "2026-01-10")
    s = pd.Series(float("nan"), index=idx)
    s.loc["2026-01-01"] = 80.0
    s.loc["2026-01-02"] = 81.0
    s.loc["2026-01-04"] = 82.0
    ma = moving_average(s, window_days=7, min_periods=3)
    assert pd.isna(ma.loc["2026-01-03"])               # solo 2 datos
    assert ma.loc["2026-01-04"] == pytest.approx(81.0)  # (80+81+82)/3, el hueco no cuenta como 0


def test_moving_average_window_is_7_calendar_days():
    idx = daily_index("2026-01-01", "2026-01-10")
    s = pd.Series(range(10), index=idx, dtype=float)
    ma = moving_average(s, window_days=7, min_periods=1)
    assert ma.loc["2026-01-08"] == pytest.approx(sum(range(1, 8)) / 7)  # días 2..8


def test_moving_average_short_series_returns_nan_not_error():
    s = pd.Series([80.0], index=pd.DatetimeIndex(["2026-01-01"]))
    assert moving_average(s).isna().all()
    assert moving_average(pd.Series(dtype=float)).empty


def test_valid_food_day_mask_threshold_and_missing():
    idx = daily_index("2026-01-01", "2026-01-04")
    kcal = pd.Series([2200.0, 400.0, float("nan"), 1000.0], index=idx)
    mask = valid_food_day_mask(kcal, min_kcal=1000)
    assert mask.tolist() == [True, False, False, True]


def test_valid_food_day_mask_overrides():
    idx = daily_index("2026-01-01", "2026-01-04")
    kcal = pd.Series([2200.0, 400.0, float("nan"), 1200.0], index=idx)
    overrides = {
        pd.Timestamp("2026-01-01"): False,  # el usuario descarta un día completo
        pd.Timestamp("2026-01-02"): True,   # acepta uno corto
        pd.Timestamp("2026-01-03"): True,   # no hay datos: no puede ser válido
    }
    mask = valid_food_day_mask(kcal, 1000, overrides)
    assert mask.tolist() == [False, True, False, True]


def test_weekly_intake_uses_only_valid_days_and_counts_them():
    idx = daily_index("2026-01-05", "2026-01-18")  # lunes 5 -> domingo 18: dos semanas
    kcal = pd.Series(float("nan"), index=idx)
    kcal.loc["2026-01-05"] = 2000.0
    kcal.loc["2026-01-06"] = 3000.0
    kcal.loc["2026-01-12"] = 2500.0
    out = weekly_intake(kcal)
    assert out["week_start"].tolist() == [pd.Timestamp("2026-01-05"), pd.Timestamp("2026-01-12")]
    assert out["mean_kcal"].tolist() == [2500.0, 2500.0]
    assert out["valid_days"].tolist() == [2, 1]


def test_weekly_intake_skips_weeks_without_data_and_empty():
    idx = daily_index("2026-01-05", "2026-01-25")
    kcal = pd.Series(float("nan"), index=idx)
    kcal.loc["2026-01-05"] = 2000.0
    kcal.loc["2026-01-20"] = 1800.0
    out = weekly_intake(kcal)
    assert len(out) == 2  # la semana intermedia sin datos no aparece
    assert weekly_intake(pd.Series(dtype=float)).empty
