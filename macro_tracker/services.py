"""Pegamento entre la base de datos y los cálculos (sin Streamlit).

Aquí se arman las series diarias con huecos, el plan de metas vigente y el estado
de la adaptación. La interfaz solo llama a estas funciones.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta

import pandas as pd

from macro_tracker.calc import adaptive
from macro_tracker.calc.bmr import BmrResult, age_on, estimate_bmr
from macro_tracker.calc.body_comp import (
    interpolate_body_fat,
    lean_mass_series,
    protein_reference_weight,
)
from macro_tracker.calc.series import daily_index, moving_average, valid_food_day_mask, weekly_intake
from macro_tracker.calc.targets import (
    CalorieTarget,
    MacroTargets,
    calorie_target,
    formula_tdee_series,
    macro_targets,
    total_daily_energy,
)
from macro_tracker.config import (
    ADAPT_WINDOW_DAYS,
    DEFAULT_MIN_VALID_DAY_KCAL,
    MOVING_AVERAGE_DAYS,
)
from macro_tracker.db.repository import Repository

STALE_WEIGHT_DAYS = 14
STALE_BODY_FAT_DAYS = 90

NOTE_NO_RECENT_WEIGHT = "no_recent_weight"
NOTE_BF_SELF_ESTIMATE = "bf_self_estimate"
NOTE_BF_NAVY = "bf_navy"
NOTE_BF_STALE = "bf_stale"
NOTE_BF_IGNORED = "bf_ignored"
NOTE_FLOOR_APPLIED = "floor_applied"


@dataclass(frozen=True)
class BodyState:
    weight_kg: float | None = None        # promedio de los pesajes de los 7 días previos al último
    weight_date: date | None = None
    body_fat_pct: float | None = None     # último valor registrado
    body_fat_source: str | None = None
    body_fat_date: date | None = None


def current_body_state(repo: Repository) -> BodyState:
    body = repo.body_df()
    if body.empty:
        return BodyState()
    weights = body["weight_kg"].dropna()
    weight = weight_date = None
    if not weights.empty:
        last = weights.index[-1]
        weight = float(weights[last - pd.Timedelta(days=MOVING_AVERAGE_DAYS - 1): last].mean())
        weight_date = last.date()
    bf = body["body_fat_pct"].dropna()
    bf_val = bf_src = bf_date = None
    if not bf.empty:
        last_bf = bf.index[-1]
        bf_val = float(bf.iloc[-1])
        bf_src = body.loc[last_bf, "body_fat_source"]
        bf_date = last_bf.date()
    return BodyState(weight, weight_date, bf_val, bf_src, bf_date)


@dataclass(frozen=True)
class Plan:
    profile: dict
    age: int
    body: BodyState
    bmr: BmrResult
    tdee_kcal: float
    calories: CalorieTarget
    protein_reference_kg: float
    macros: MacroTargets
    notes: tuple[str, ...] = field(default_factory=tuple)


def build_plan(repo: Repository, on_date: date | None = None) -> Plan | None:
    """Meta calculada por fórmula con el perfil y el último estado corporal.

    Devuelve None si faltan el perfil o al menos un peso registrado.
    """
    on_date = on_date or date.today()
    profile = repo.get_profile()
    body = current_body_state(repo)
    if profile is None or body.weight_kg is None:
        return None

    notes: list[str] = []
    use_bf = body.body_fat_pct is not None and profile["bmr_method_pref"] == "auto"
    if body.body_fat_pct is not None and not use_bf:
        notes.append(NOTE_BF_IGNORED)
    bf = body.body_fat_pct if use_bf else None
    if use_bf:
        if body.body_fat_source == "self_estimate":
            notes.append(NOTE_BF_SELF_ESTIMATE)
        elif body.body_fat_source == "navy":
            notes.append(NOTE_BF_NAVY)
        if body.body_fat_date and (on_date - body.body_fat_date).days > STALE_BODY_FAT_DAYS:
            notes.append(NOTE_BF_STALE)
    if body.weight_date and (on_date - body.weight_date).days > STALE_WEIGHT_DAYS:
        notes.append(NOTE_NO_RECENT_WEIGHT)

    age = age_on(date.fromisoformat(profile["birth_date"]), on_date)
    bmr = estimate_bmr(body.weight_kg, profile["height_cm"], age, profile["sex"], bf,
                       profile["bmr_method_pref"])
    tdee = total_daily_energy(bmr.kcal, profile["activity_level"])
    calories = calorie_target(tdee, bmr.kcal, profile["goal"], profile["rate_kg_week"])
    if calories.floor_applied:
        notes.append(NOTE_FLOOR_APPLIED)
    ref = protein_reference_weight(body.weight_kg, bf)
    macros = _macros_for(profile, body.weight_kg, ref, calories.kcal)
    return Plan(profile, age, body, bmr, tdee, calories, ref, macros, tuple(notes))


def _macros_for(profile: dict, weight_kg: float, ref_kg: float, kcal: float) -> MacroTargets:
    return macro_targets(
        kcal, weight_kg, profile["goal"], ref_kg,
        (profile["protein_g_kg_min"], profile["protein_g_kg_max"]),
        profile["fat_g_kg_min"], profile["fat_pct_kcal"],
    )


def save_target(repo: Repository, plan: Plan, kcal: float, *, source: str,
                effective_from: date | None = None, note: str | None = None) -> MacroTargets:
    """Guarda como meta vigente `kcal` con el reparto de macros del plan."""
    macros = _macros_for(plan.profile, plan.body.weight_kg, plan.protein_reference_kg, kcal)
    repo.set_target(
        effective_from or date.today(), kcal, macros.protein_g, macros.carbs_g, macros.fat_g,
        source, plan.bmr.method, note,
    )
    return macros


def daily_frame(
    repo: Repository,
    start: date | str | pd.Timestamp,
    end: date | str | pd.Timestamp,
    *,
    today: date | None = None,
) -> pd.DataFrame:
    """Tabla diaria entre `start` y `end` con huecos como NaN (nunca 0).

    Los suavizados (promedio móvil, % de grasa interpolado) se calculan con todo
    el historial anterior para que el borde izquierdo del rango no distorsione.
    El día en curso nunca cuenta como "día de comida válido" salvo que el usuario
    lo fuerce: casi siempre está incompleto y bajaría el promedio de calorías.
    """
    start, end = pd.Timestamp(start).normalize(), pd.Timestamp(end).normalize()
    today_ts = pd.Timestamp(today or date.today()).normalize()
    body_all = repo.body_df(end=end)
    totals_all = repo.daily_totals(end=end)
    first_dates = [d.index.min() for d in (body_all, totals_all) if not d.empty]
    full_start = min([start, *first_dates])
    idx = daily_index(full_start, end)

    profile = repo.get_profile()
    min_kcal = profile["min_valid_day_kcal"] if profile else DEFAULT_MIN_VALID_DAY_KCAL

    body = body_all.reindex(idx)
    totals = totals_all.reindex(idx)
    frame = pd.DataFrame(index=idx)
    frame["weight_kg"] = body["weight_kg"].astype(float)
    frame["weight_ma7"] = moving_average(frame["weight_kg"])
    frame["body_fat_pct"] = body["body_fat_pct"].astype(float)
    frame["bf_daily"] = interpolate_body_fat(frame["body_fat_pct"])
    frame["lean_mass_kg"] = lean_mass_series(frame["weight_ma7"], frame["bf_daily"])
    for col in ("kcal", "protein_g", "carbs_g", "fat_g"):
        frame[col] = totals[col].astype(float)

    overrides = repo.day_status_map(end=end)
    valid = valid_food_day_mask(frame["kcal"], min_kcal, overrides)
    if today_ts in valid.index and today_ts not in overrides:
        valid.loc[today_ts] = False
    frame["food_valid"] = valid
    frame["kcal_valid"] = frame["kcal"].where(valid)

    targets = repo.targets_df()
    if targets.empty:
        for col in ("kcal", "protein_g", "carbs_g", "fat_g"):
            frame[f"target_{col}"] = float("nan")
    else:
        numeric = targets[["kcal", "protein_g", "carbs_g", "fat_g"]].astype(float)
        spread = numeric.reindex(numeric.index.union(idx)).ffill().reindex(idx)
        for col in ("kcal", "protein_g", "carbs_g", "fat_g"):
            frame[f"target_{col}"] = spread[col]
    return frame.loc[start:end]


@dataclass(frozen=True)
class AdaptiveStatus:
    data: adaptive.DataTdeeResult
    recommendation: adaptive.Recommendation
    current_target_kcal: float


def adaptive_status(
    repo: Repository,
    plan: Plan,
    *,
    end_date: date | None = None,
    window_days: int = ADAPT_WINDOW_DAYS,
) -> AdaptiveStatus:
    """Gasto por datos y recomendación. La ventana termina ayer por defecto."""
    end = end_date or (date.today() - timedelta(days=1))
    start = pd.Timestamp(end) - pd.Timedelta(days=window_days - 1)
    frame = daily_frame(repo, start, end)
    data = adaptive.estimate_tdee_from_data(
        frame["weight_kg"], frame["kcal_valid"], end, window_days=window_days
    )
    active = repo.target_on(date.today())
    current = float(active["kcal"]) if active else plan.calories.kcal
    rec = adaptive.recommend_target(
        data, current, plan.profile["goal"], plan.profile["rate_kg_week"], plan.bmr.kcal
    )
    return AdaptiveStatus(data, rec, current)


def tdee_timeline(
    repo: Repository,
    start: date | str | pd.Timestamp,
    end: date | str | pd.Timestamp,
    *,
    window_days: int = ADAPT_WINDOW_DAYS,
) -> pd.DataFrame:
    """Gasto por fórmula y por datos día a día (columnas: formula_tdee, formula_method,
    data_tdee, ci_low, ci_high, confidence). Los días sin estimación quedan en NaN."""
    profile = repo.get_profile()
    if profile is None:
        return pd.DataFrame()
    start, end = pd.Timestamp(start).normalize(), pd.Timestamp(end).normalize()
    full = daily_frame(repo, _history_start(repo, start), end)
    bf = full["bf_daily"] if profile["bmr_method_pref"] == "auto" else None
    formula = formula_tdee_series(
        full["weight_ma7"], bf, profile["sex"], profile["height_cm"],
        date.fromisoformat(profile["birth_date"]), profile["activity_level"], profile["bmr_method_pref"],
    )
    rolling = adaptive.rolling_tdee_from_data(full["weight_kg"], full["kcal_valid"], window_days=window_days)

    out = pd.DataFrame(index=full.index)
    out["formula_tdee"] = formula["tdee"] if not formula.empty else float("nan")
    out["formula_method"] = formula["method"] if not formula.empty else None
    for col, name in (("tdee", "data_tdee"), ("ci_low", "ci_low"), ("ci_high", "ci_high"), ("confidence", "confidence")):
        out[name] = rolling[col] if not rolling.empty else (float("nan") if col != "confidence" else None)
    return out.loc[start:end]


def _history_start(repo: Repository, fallback: pd.Timestamp) -> pd.Timestamp:
    dates = []
    body, totals = repo.body_df(), repo.daily_totals()
    for d in (body, totals):
        if not d.empty:
            dates.append(d.index.min())
    return min([fallback, *dates])


def weekly_summary(frame: pd.DataFrame) -> pd.DataFrame:
    """Calorías promedio por semana (solo días válidos) con la meta promedio de esa semana."""
    weekly = weekly_intake(frame["kcal_valid"])
    if weekly.empty:
        return weekly.assign(target_kcal=pd.Series(dtype=float))
    target = frame["target_kcal"].groupby(frame.index.to_period("W-SUN")).mean()
    weekly["target_kcal"] = [target.get(pd.Period(ws, freq="W-SUN"), float("nan")) for ws in weekly["week_start"]]
    return weekly
