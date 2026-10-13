"""Gasto total, meta calórica y reparto de macros."""
from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from macro_tracker.calc.bmr import age_on, estimate_bmr
from macro_tracker.config import (
    ACTIVITY_FACTORS,
    DEFAULT_FAT_G_KG_MIN,
    DEFAULT_FAT_PCT_KCAL,
    DEFAULT_PROTEIN_G_KG,
    GOALS,
    KCAL_PER_G,
    KCAL_PER_KG,
)


def activity_factor(level: str) -> float:
    try:
        return ACTIVITY_FACTORS[level]
    except KeyError:
        raise ValueError(f"nivel de actividad desconocido: {level!r}") from None


def total_daily_energy(bmr_kcal: float, level: str) -> float:
    """Gasto total estimado por fórmula = basal × factor de actividad."""
    return bmr_kcal * activity_factor(level)


def goal_adjustment_kcal(goal: str, rate_kg_week: float) -> float:
    """Ajuste diario (kcal) para lograr `rate_kg_week` (≥ 0; el signo lo da el objetivo)."""
    if goal not in GOALS:
        raise ValueError(f"objetivo desconocido: {goal!r}")
    if rate_kg_week < 0:
        raise ValueError("el ritmo se expresa como valor positivo (kg/semana)")
    if goal == "maintain":
        return 0.0
    daily = rate_kg_week * KCAL_PER_KG / 7.0
    return -daily if goal == "lose" else daily


@dataclass(frozen=True)
class CalorieTarget:
    kcal: float
    tdee_kcal: float
    adjustment_kcal: float
    unfloored_kcal: float
    floor_kcal: float
    floor_applied: bool
    effective_rate_kg_week: float  # ritmo realmente logrado con `kcal` (signo: + gana, − pierde)


def calorie_target(tdee_kcal: float, bmr_kcal: float, goal: str, rate_kg_week: float) -> CalorieTarget:
    """Meta calórica = gasto total + ajuste, nunca por debajo del basal estimado."""
    adjustment = goal_adjustment_kcal(goal, rate_kg_week)
    unfloored = tdee_kcal + adjustment
    kcal = max(unfloored, bmr_kcal)
    return CalorieTarget(
        kcal=kcal,
        tdee_kcal=tdee_kcal,
        adjustment_kcal=adjustment,
        unfloored_kcal=unfloored,
        floor_kcal=bmr_kcal,
        floor_applied=unfloored < bmr_kcal,
        effective_rate_kg_week=(kcal - tdee_kcal) * 7.0 / KCAL_PER_KG,
    )


@dataclass(frozen=True)
class MacroTargets:
    kcal: float
    protein_g: float
    carbs_g: float
    fat_g: float
    protein_g_per_kg: float
    protein_range_g: tuple[float, float]
    fat_floor_g: float
    flags: tuple[str, ...] = field(default_factory=tuple)

    @property
    def kcal_from_macros(self) -> float:
        return (
            KCAL_PER_G["protein"] * self.protein_g
            + KCAL_PER_G["carbs"] * self.carbs_g
            + KCAL_PER_G["fat"] * self.fat_g
        )


FLAG_REDUCED_TO_FIT = "reduced_to_fit"
FLAG_MINIMUMS_EXCEED_KCAL = "minimums_exceed_kcal"


def pick_protein_g_per_kg(goal: str, protein_g_kg_range: tuple[float, float]) -> float:
    """Extremo alto del rango al perder grasa (protege masa magra); punto medio en otro caso."""
    lo, hi = protein_g_kg_range
    return hi if goal == "lose" else (lo + hi) / 2.0


def macro_targets(
    kcal: float,
    weight_kg: float,
    goal: str,
    protein_reference_kg: float | None = None,
    protein_g_kg_range: tuple[float, float] = DEFAULT_PROTEIN_G_KG,
    fat_g_kg_min: float = DEFAULT_FAT_G_KG_MIN,
    fat_pct_kcal: float = DEFAULT_FAT_PCT_KCAL,
) -> MacroTargets:
    """Reparte `kcal` en proteína, grasa y carbohidratos.

    - Proteína: g/kg según objetivo, sobre `protein_reference_kg` (peso total si es None).
    - Grasa: el mayor entre el mínimo (`fat_g_kg_min` × peso) y `fat_pct_kcal` de las kcal.
    - Carbohidratos: el resto. Si el resto fuera negativo se recorta primero la grasa
      sobre su mínimo, luego la proteína sobre su mínimo; si aun así no cabe, carbohidratos = 0
      y se marca `minimums_exceed_kcal`.
    """
    lo, hi = protein_g_kg_range
    if not 0 < lo <= hi:
        raise ValueError("rango de proteína inválido")
    ref = weight_kg if protein_reference_kg is None else protein_reference_kg
    per_kg = pick_protein_g_per_kg(goal, protein_g_kg_range)

    protein = per_kg * ref
    protein_min = lo * ref
    fat_floor = fat_g_kg_min * weight_kg
    fat = max(fat_floor, fat_pct_kcal * kcal / KCAL_PER_G["fat"])
    flags: list[str] = []

    def carbs_for(p: float, f: float) -> float:
        return (kcal - KCAL_PER_G["protein"] * p - KCAL_PER_G["fat"] * f) / KCAL_PER_G["carbs"]

    carbs = carbs_for(protein, fat)
    if carbs < 0:
        flags.append(FLAG_REDUCED_TO_FIT)
        fat = max(fat_floor, (kcal - KCAL_PER_G["protein"] * protein) / KCAL_PER_G["fat"])
        carbs = carbs_for(protein, fat)
        if carbs < 0:
            protein = max(protein_min, (kcal - KCAL_PER_G["fat"] * fat) / KCAL_PER_G["protein"])
            carbs = carbs_for(protein, fat)
        if carbs < 0:
            carbs = 0.0
            flags.append(FLAG_MINIMUMS_EXCEED_KCAL)

    return MacroTargets(
        kcal=kcal,
        protein_g=protein,
        carbs_g=carbs,
        fat_g=fat,
        protein_g_per_kg=protein / ref if ref else 0.0,
        protein_range_g=(lo * ref, hi * ref),
        fat_floor_g=fat_floor,
        flags=tuple(flags),
    )


def formula_tdee_series(
    weight_smooth: pd.Series,
    bf_daily: pd.Series | None,
    sex: str,
    height_cm: float,
    birth_date,
    activity_level: str,
    prefer: str = "auto",
) -> pd.DataFrame:
    """Gasto por fórmula día a día (columnas bmr, tdee, method).

    Usa el peso suavizado de cada día (y el % de grasa interpolado si existe);
    los días sin peso suavizado se omiten.
    """
    factor = activity_factor(activity_level)
    rows = []
    for day, weight in weight_smooth.dropna().items():
        bf = None
        if bf_daily is not None and day in bf_daily.index and pd.notna(bf_daily.loc[day]):
            bf = float(bf_daily.loc[day])
        res = estimate_bmr(
            float(weight), height_cm, age_on(birth_date, day.date()), sex, bf, prefer
        )
        rows.append({"date": day, "bmr": res.kcal, "tdee": res.kcal * factor, "method": res.method})
    if not rows:
        return pd.DataFrame(columns=["bmr", "tdee", "method"], index=pd.DatetimeIndex([], name="date"))
    return pd.DataFrame(rows).set_index("date")
