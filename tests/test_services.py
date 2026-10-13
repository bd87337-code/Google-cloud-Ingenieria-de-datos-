from datetime import date, timedelta

import numpy as np
import pandas as pd
import pytest

from macro_tracker import services


def seed_basic(repo, profile, weight=80.0):
    repo.save_profile(**profile)
    repo.upsert_body("2026-03-01", weight_kg=weight)


def test_build_plan_none_without_profile_or_weight(repo, sample_profile):
    assert services.build_plan(repo) is None
    repo.save_profile(**sample_profile)
    assert services.build_plan(repo) is None          # perfil sin ningún peso
    repo.upsert_body("2026-03-01", weight_kg=80)
    assert services.build_plan(repo, date(2026, 3, 2)) is not None


def test_plan_uses_mifflin_without_body_fat(repo, sample_profile):
    seed_basic(repo, sample_profile)
    plan = services.build_plan(repo, date(2026, 3, 2))
    # edad 29 (nace 1996-05-20): 800 + 1125 - 145 + 5 = 1785
    assert plan.age == 29
    assert plan.bmr.method == "mifflin_st_jeor" and plan.bmr.kcal == pytest.approx(1785)
    assert plan.tdee_kcal == pytest.approx(1785 * 1.55)
    assert plan.calories.kcal == pytest.approx(1785 * 1.55 - 550)   # perder 0.5 kg/sem
    assert plan.protein_reference_kg == 80


def test_plan_uses_katch_with_body_fat_and_notes_source(repo, sample_profile):
    repo.save_profile(**sample_profile)
    repo.upsert_body("2026-03-01", weight_kg=80, body_fat_pct=20, body_fat_source="self_estimate")
    plan = services.build_plan(repo, date(2026, 3, 2))
    assert plan.bmr.method == "katch_mcardle"
    assert plan.bmr.kcal == pytest.approx(370 + 21.6 * 64)
    assert services.NOTE_BF_SELF_ESTIMATE in plan.notes


def test_forcing_mifflin_ignores_body_fat_everywhere(repo, sample_profile):
    repo.save_profile(**{**sample_profile, "bmr_method_pref": "mifflin"})
    repo.upsert_body("2026-03-01", weight_kg=100, body_fat_pct=40, body_fat_source="measured")
    plan = services.build_plan(repo, date(2026, 3, 2))
    assert plan.bmr.method == "mifflin_st_jeor"
    assert plan.protein_reference_kg == 100            # sin reducir por % de grasa
    assert services.NOTE_BF_IGNORED in plan.notes


def test_high_body_fat_reduces_protein_reference(repo, sample_profile):
    repo.save_profile(**sample_profile)
    repo.upsert_body("2026-03-01", weight_kg=100, body_fat_pct=40, body_fat_source="measured")
    plan = services.build_plan(repo, date(2026, 3, 2))
    assert plan.protein_reference_kg == pytest.approx(75)
    assert plan.macros.protein_g == pytest.approx(2.2 * 75)  # objetivo "perder": extremo alto


def test_plan_warns_when_weight_or_body_fat_is_stale(repo, sample_profile):
    repo.save_profile(**sample_profile)
    repo.upsert_body("2026-01-01", weight_kg=80, body_fat_pct=20, body_fat_source="measured")
    plan = services.build_plan(repo, date(2026, 6, 1))
    assert services.NOTE_NO_RECENT_WEIGHT in plan.notes and services.NOTE_BF_STALE in plan.notes


def test_plan_weight_is_mean_of_last_week_of_weighings(repo, sample_profile):
    repo.save_profile(**sample_profile)
    for day, w in (("2026-03-01", 90.0), ("2026-03-08", 80.0), ("2026-03-09", 82.0), ("2026-03-10", 81.0)):
        repo.upsert_body(day, weight_kg=w)
    body = services.current_body_state(repo)
    assert body.weight_kg == pytest.approx(81.0)       # ignora el pesaje de hace 9 días
    assert body.weight_date == date(2026, 3, 10)


def test_plan_floor_warning(repo, sample_profile):
    repo.save_profile(**{**sample_profile, "rate_kg_week": 1.5, "activity_level": "sedentary"})
    repo.upsert_body("2026-03-01", weight_kg=80)
    plan = services.build_plan(repo, date(2026, 3, 2))
    assert plan.calories.floor_applied and services.NOTE_FLOOR_APPLIED in plan.notes
    assert plan.calories.kcal == pytest.approx(plan.bmr.kcal)


def test_save_target_stores_macros_and_effective_date(repo, sample_profile):
    seed_basic(repo, sample_profile)
    plan = services.build_plan(repo, date(2026, 3, 2))
    services.save_target(repo, plan, 2300, source="data", effective_from=date(2026, 3, 5), note="x")
    t = repo.target_on("2026-03-06")
    assert t["kcal"] == 2300 and t["tdee_source"] == "data"
    assert 4 * t["protein_g"] + 4 * t["carbs_g"] + 9 * t["fat_g"] == pytest.approx(2300)


def test_daily_frame_keeps_gaps_as_nan_not_zero(repo, sample_profile):
    repo.save_profile(**sample_profile)
    a = repo.add_food("A", 100, 10, 10, 1)
    repo.upsert_body("2026-03-01", weight_kg=80)
    repo.upsert_body("2026-03-04", weight_kg=79)
    repo.add_log("2026-03-02", "lunch", a, 2000)     # 2000 kcal
    repo.add_log("2026-03-03", "lunch", a, 300)      # 300 kcal: día incompleto
    f = services.daily_frame(repo, "2026-03-01", "2026-03-05", today=date(2026, 3, 20))
    assert f["weight_kg"].isna().tolist() == [False, True, True, False, True]
    assert f["kcal"].isna().tolist() == [True, False, False, True, True]
    assert f["food_valid"].tolist() == [False, True, False, False, False]
    assert f["kcal_valid"].tolist()[1] == 2000 and np.isnan(f["kcal_valid"].tolist()[2])


def test_today_is_never_valid_unless_forced(repo, sample_profile):
    repo.save_profile(**sample_profile)
    a = repo.add_food("A", 100, 10, 10, 1)
    repo.add_log("2026-03-02", "lunch", a, 2000)
    repo.add_log("2026-03-03", "lunch", a, 2000)
    f = services.daily_frame(repo, "2026-03-01", "2026-03-03", today=date(2026, 3, 3))
    assert f.loc["2026-03-02", "food_valid"] and not f.loc["2026-03-03", "food_valid"]
    repo.set_day_status("2026-03-03", True)
    f = services.daily_frame(repo, "2026-03-01", "2026-03-03", today=date(2026, 3, 3))
    assert f.loc["2026-03-03", "food_valid"]


def test_daily_frame_uses_history_before_range_for_smoothing(repo, sample_profile):
    repo.save_profile(**sample_profile)
    for i in range(10):
        repo.upsert_body(date(2026, 3, 1) + timedelta(days=i), weight_kg=80 + i * 0.1)
    repo.upsert_body("2026-02-20", weight_kg=70, body_fat_pct=20, body_fat_source="measured")
    f = services.daily_frame(repo, "2026-03-08", "2026-03-10", today=date(2026, 4, 1))
    assert f["weight_ma7"].notna().all()                       # no hay arranque en frío en el borde
    assert f["bf_daily"].notna().all() and (f["bf_daily"] == 20).all()   # medición anterior al rango
    assert f["lean_mass_kg"].iloc[0] == pytest.approx(f["weight_ma7"].iloc[0] * 0.8)


def test_daily_frame_target_series_follow_history(repo, sample_profile):
    repo.save_profile(**sample_profile)
    repo.set_target("2026-03-01", 2200, 150, 250, 70, "formula")
    repo.set_target("2026-03-04", 2400, 160, 290, 75, "data")
    f = services.daily_frame(repo, "2026-03-02", "2026-03-06", today=date(2026, 4, 1))
    assert f["target_kcal"].tolist() == [2200, 2200, 2400, 2400, 2400]


def test_daily_frame_empty_database(repo):
    f = services.daily_frame(repo, "2026-03-01", "2026-03-03", today=date(2026, 4, 1))
    assert len(f) == 3 and f["weight_kg"].isna().all() and f["kcal"].isna().all()
    assert f["target_kcal"].isna().all()


def build_history(repo, profile, days=20, intake=2000.0, true_tdee=2500.0, start=date(2026, 3, 1)):
    """Historia sintética consistente: peso baja según el balance real."""
    repo.save_profile(**profile)
    food = repo.add_food("Comida", 100, 5, 10, 3)
    slope = (intake - true_tdee) / 7700
    for i in range(days):
        day = start + timedelta(days=i)
        repo.upsert_body(day, weight_kg=round(80 + slope * i, 3))
        repo.add_log(day, "lunch", food, intake)     # 100 kcal/100 g
    return start + timedelta(days=days - 1)


def test_adaptive_status_insufficient_with_little_data(repo, sample_profile):
    last = build_history(repo, sample_profile, days=8)
    plan = services.build_plan(repo, last)
    st = services.adaptive_status(repo, plan, end_date=last)
    assert not st.data.ok and st.recommendation.status == "insufficient"
    assert st.data.tdee_kcal is None


def test_adaptive_status_estimates_and_recommends(repo, sample_profile):
    last = build_history(repo, sample_profile, days=20, intake=2000, true_tdee=2500)
    plan = services.build_plan(repo, last)
    st = services.adaptive_status(repo, plan, end_date=last)
    assert st.data.ok
    assert st.data.tdee_kcal == pytest.approx(2500, abs=15)       # redondeo del peso a 3 decimales
    assert st.recommendation.status in ("adjust", "keep")


def test_tdee_timeline_combines_formula_and_data(repo, sample_profile):
    last = build_history(repo, sample_profile, days=20)
    tl = services.tdee_timeline(repo, "2026-03-01", last, window_days=14)
    assert tl["formula_tdee"].notna().sum() >= 18
    assert tl["data_tdee"].notna().sum() == 7                     # días 14..20
    assert tl["data_tdee"].dropna().between(2450, 2550).all()
    assert tl["data_tdee"].first_valid_index() == pd.Timestamp("2026-03-14")


def test_tdee_timeline_without_profile_is_empty(repo):
    assert services.tdee_timeline(repo, "2026-03-01", "2026-03-10").empty


def test_weekly_summary_adds_target_and_counts_only_valid_days(repo, sample_profile):
    repo.save_profile(**sample_profile)
    a = repo.add_food("A", 100, 10, 10, 1)
    repo.set_target("2026-03-01", 2200, 150, 250, 70, "formula")
    repo.add_log("2026-03-02", "lunch", a, 2000)   # lunes 2
    repo.add_log("2026-03-03", "lunch", a, 2400)
    repo.add_log("2026-03-04", "lunch", a, 300)    # incompleto: no cuenta
    f = services.daily_frame(repo, "2026-03-02", "2026-03-08", today=date(2026, 4, 1))
    w = services.weekly_summary(f)
    assert len(w) == 1
    assert w.loc[0, "mean_kcal"] == pytest.approx(2200) and w.loc[0, "valid_days"] == 2
    assert w.loc[0, "target_kcal"] == pytest.approx(2200)


def test_weekly_summary_empty(repo):
    f = services.daily_frame(repo, "2026-03-02", "2026-03-08", today=date(2026, 4, 1))
    assert services.weekly_summary(f).empty
