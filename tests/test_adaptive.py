import numpy as np
import pandas as pd
import pytest

from macro_tracker.calc.adaptive import (
    REASON_FOOD_DAYS,
    REASON_NO_VARIATION,
    REASON_WEIGHINGS,
    REASON_WEIGHINGS_HALVES,
    STATUS_ADJUST,
    STATUS_INSUFFICIENT,
    STATUS_KEEP,
    confidence_label,
    estimate_tdee_from_data,
    recommend_target,
    rolling_tdee_from_data,
    t95,
)
from macro_tracker.calc.series import daily_index

TRUE_TDEE = 2500.0
INTAKE = 2000.0
SLOPE = (INTAKE - TRUE_TDEE) / 7700.0  # kg/día: balance de -500 kcal


def synthetic(days=28, noise=0.0, seed=0, start="2026-01-01", intake=INTAKE, w0=80.0):
    idx = daily_index(start, pd.Timestamp(start) + pd.Timedelta(days=days - 1))
    rng = np.random.default_rng(seed)
    t = np.arange(days)
    weight = pd.Series(w0 + SLOPE * t + rng.normal(0, noise, days), index=idx)
    kcal = pd.Series(float(intake), index=idx)
    return weight, kcal


def test_recovers_true_tdee_without_noise():
    w, k = synthetic(days=14)
    res = estimate_tdee_from_data(w, k, w.index[-1])
    assert res.ok
    assert res.tdee_kcal == pytest.approx(TRUE_TDEE, abs=1e-6)
    assert res.slope_kg_per_day == pytest.approx(SLOPE)
    assert res.ci_half_width_kcal == pytest.approx(0.0, abs=1e-6)
    assert res.confidence == "high"


def test_weight_gain_means_expenditure_below_intake():
    # come 3000 y sube peso: el gasto debe quedar por debajo de 3000
    idx = daily_index("2026-01-01", "2026-01-14")
    w = pd.Series(80 + 0.05 * np.arange(14), index=idx)
    k = pd.Series(3000.0, index=idx)
    res = estimate_tdee_from_data(w, k, idx[-1])
    assert res.tdee_kcal == pytest.approx(3000 - 0.05 * 7700)


def test_division_is_by_14_not_7_days_regression_check():
    """Con una pérdida lineal, la diferencia de MA7 / 14 días daría la mitad del efecto.
    La regresión sobre la ventana completa no cae en ese error."""
    w, k = synthetic(days=14)
    res = estimate_tdee_from_data(w, k, w.index[-1])
    naive = INTAKE - ((w.iloc[7:].mean() - w.iloc[:7].mean()) * 7700 / 14)
    assert abs(naive - TRUE_TDEE) > 200      # el enfoque ingenuo está sesgado (~ -250 kcal)
    assert abs(res.tdee_kcal - TRUE_TDEE) < 1


def test_insufficient_before_enough_days_returns_no_number():
    w, k = synthetic(days=14)
    res = estimate_tdee_from_data(w.iloc[:8], k.iloc[:8], w.index[7])
    assert not res.ok
    assert res.tdee_kcal is None and res.ci_half_width_kcal is None
    assert REASON_FOOD_DAYS in res.reasons


def test_needs_10_food_days_of_14():
    w, k = synthetic(days=14)
    k.iloc[:5] = float("nan")  # 9 días válidos
    res = estimate_tdee_from_data(w, k, w.index[-1])
    assert res.n_food_days == 9 and not res.ok
    assert res.reasons == (REASON_FOOD_DAYS,)
    k.iloc[4] = INTAKE  # 10 días válidos
    assert estimate_tdee_from_data(w, k, w.index[-1]).ok


def test_needs_enough_weighings():
    w, k = synthetic(days=14)
    w.iloc[[0, 2, 4, 6, 8, 10]] = float("nan")  # quedan 8 -> pasa; quito uno más
    assert estimate_tdee_from_data(w, k, w.index[-1]).ok
    w.iloc[12] = float("nan")
    res = estimate_tdee_from_data(w, k, w.index[-1])
    assert not res.ok and REASON_WEIGHINGS in res.reasons


def test_weighings_must_cover_both_halves():
    w, k = synthetic(days=14)
    w.iloc[:5] = float("nan")  # primera mitad con 2 pesajes, segunda con 7 -> 9 en total
    res = estimate_tdee_from_data(w, k, w.index[-1])
    assert not res.ok
    assert res.reasons == (REASON_WEIGHINGS_HALVES,)
    assert (res.n_weighings_first_half, res.n_weighings_second_half) == (2, 7)


def test_constant_dates_cannot_happen_but_flat_weights_are_valid():
    idx = daily_index("2026-01-01", "2026-01-14")
    w = pd.Series(80.0, index=idx)
    k = pd.Series(2500.0, index=idx)
    res = estimate_tdee_from_data(w, k, idx[-1])
    assert res.ok and res.tdee_kcal == pytest.approx(2500.0)


def test_missing_days_do_not_break_calculation():
    w, k = synthetic(days=14)
    w.iloc[[1, 3, 8]] = float("nan")
    k.iloc[[0, 5]] = float("nan")
    res = estimate_tdee_from_data(w, k, w.index[-1])
    assert res.ok
    assert res.n_weighings == 11 and res.n_food_days == 12
    assert res.tdee_kcal == pytest.approx(TRUE_TDEE, abs=1e-6)  # datos lineales: faltantes no sesgan


def test_window_uses_only_recent_days():
    # 14 días a 80 kg estables, luego 14 días bajando: la ventana final solo ve la bajada
    idx = daily_index("2026-01-01", "2026-01-28")
    w = pd.Series(80.0, index=idx)
    w.iloc[14:] = 80 + SLOPE * np.arange(14)
    k = pd.Series(INTAKE, index=idx)
    res = estimate_tdee_from_data(w, k, idx[-1], window_days=14)
    assert res.tdee_kcal == pytest.approx(TRUE_TDEE, abs=1e-6)


def test_confidence_interval_coverage_with_noise():
    """El IC al 95 % debe contener el gasto real en ~95 % de las simulaciones."""
    hits = 0
    runs = 300
    for seed in range(runs):
        w, k = synthetic(days=14, noise=0.5, seed=seed)
        res = estimate_tdee_from_data(w, k, w.index[-1])
        lo, hi = res.ci
        hits += lo <= TRUE_TDEE <= hi
    assert 0.90 <= hits / runs <= 0.99


def test_noise_makes_14_day_estimate_low_confidence_and_longer_window_better():
    w14, k14 = synthetic(days=14, noise=0.5, seed=3)
    w28, k28 = synthetic(days=28, noise=0.5, seed=3)
    r14 = estimate_tdee_from_data(w14, k14, w14.index[-1], window_days=14)
    r28 = estimate_tdee_from_data(w28, k28, w28.index[-1], window_days=28)
    assert r14.confidence == "low"
    assert r28.ci_half_width_kcal < r14.ci_half_width_kcal


def test_rolling_only_emits_rows_that_meet_the_minimums():
    w, k = synthetic(days=20)
    out = rolling_tdee_from_data(w, k, window_days=14)
    assert out.index[0] == w.index[13]          # primera ventana completa
    assert len(out) == 7
    assert out["tdee"].between(TRUE_TDEE - 1, TRUE_TDEE + 1).all()
    assert (out["ci_low"] <= out["tdee"]).all() and (out["tdee"] <= out["ci_high"]).all()


def test_rolling_with_too_little_data_is_empty():
    w, k = synthetic(days=10)
    assert rolling_tdee_from_data(w, k, window_days=14).empty


def test_t95_and_confidence_labels():
    assert t95(12) == pytest.approx(2.179)
    assert t95(500) == pytest.approx(1.96)
    with pytest.raises(ValueError):
        t95(0)
    assert confidence_label(100) == "high"
    assert confidence_label(300) == "medium"
    assert confidence_label(900) == "low"


def _ok_result(tdee, half_width=150.0):
    w, k = synthetic(days=14)
    base = estimate_tdee_from_data(w, k, w.index[-1])
    from dataclasses import replace
    return replace(base, tdee_kcal=tdee, ci_half_width_kcal=half_width, confidence="medium")


def test_recommend_insufficient_when_not_ok():
    w, k = synthetic(days=5)
    bad = estimate_tdee_from_data(w, k, w.index[-1])
    rec = recommend_target(bad, 2200, "maintain", 0.0, 1700)
    assert rec.status == STATUS_INSUFFICIENT and rec.recommended_kcal is None


def test_recommend_keep_when_close():
    rec = recommend_target(_ok_result(2250), 2200, "maintain", 0.0, 1700)
    assert rec.status == STATUS_KEEP
    assert rec.recommended_kcal == 2200 and rec.delta_kcal == 0


def test_recommend_limits_step():
    rec = recommend_target(_ok_result(2800), 2200, "maintain", 0.0, 1700)
    assert rec.status == STATUS_ADJUST
    assert rec.ideal_kcal == pytest.approx(2800)
    assert rec.recommended_kcal == pytest.approx(2450)   # +250 máximo
    assert rec.limited_by_step


def test_recommend_includes_goal_adjustment():
    # pierde 0.5 kg/sem = -550 kcal; gasto real 2600 -> meta ideal 2050
    rec = recommend_target(_ok_result(2600), 2200, "lose", 0.5, 1700)
    assert rec.ideal_kcal == pytest.approx(2050)
    assert rec.recommended_kcal == pytest.approx(2050)   # -150, dentro del paso
    assert rec.implied_tdee_kcal == pytest.approx(2750)  # la meta vigente asumía 2750


def test_recommend_never_below_bmr():
    rec = recommend_target(_ok_result(1900), 1850, "lose", 0.5, 1800)
    assert rec.ideal_kcal == 1800 and rec.limited_by_floor
    assert rec.recommended_kcal >= 1800


def test_recommend_flags_difference_within_noise():
    rec = recommend_target(_ok_result(2400, half_width=400), 2200, "maintain", 0.0, 1700)
    assert rec.status == STATUS_ADJUST
    assert rec.within_noise  # |2400 - 2200| = 200 < 400
