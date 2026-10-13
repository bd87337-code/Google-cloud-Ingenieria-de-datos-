"""Gasto real estimado a partir de datos (balance energético).

    gasto = calorías promedio − pendiente de peso (kg/día) × 7700

La pendiente se obtiene por regresión lineal sobre los pesos diarios de la
ventana (no como diferencia de dos promedios móviles: con dos promedios de 7 días
dentro de 14 días solo hay 7 días de separación, no 14). La regresión tolera
días sin pesar y entrega un error estándar, que se traduce en un intervalo de
confianza para el gasto. El promedio móvil de 7 días se usa solo para graficar.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date

import numpy as np
import pandas as pd

from macro_tracker.calc.targets import goal_adjustment_kcal
from macro_tracker.config import (
    ADAPT_MAX_STEP_KCAL,
    ADAPT_MIN_FOOD_DAYS,
    ADAPT_MIN_WEIGHINGS,
    ADAPT_MIN_WEIGHINGS_PER_HALF,
    ADAPT_NOISE_FLOOR_KCAL,
    ADAPT_WINDOW_DAYS,
    CI_HALF_WIDTH_HIGH,
    CI_HALF_WIDTH_MEDIUM,
    KCAL_PER_KG,
)

# Códigos de insuficiencia (la interfaz los traduce a texto).
REASON_FOOD_DAYS = "food_days"
REASON_WEIGHINGS = "weighings"
REASON_WEIGHINGS_HALVES = "weighings_halves"
REASON_NO_VARIATION = "no_variation"

# t de Student, dos colas al 95 %, por grados de libertad.
_T95 = {
    1: 12.706, 2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571, 6: 2.447, 7: 2.365, 8: 2.306,
    9: 2.262, 10: 2.228, 11: 2.201, 12: 2.179, 13: 2.160, 14: 2.145, 15: 2.131,
    16: 2.120, 17: 2.110, 18: 2.101, 19: 2.093, 20: 2.086, 21: 2.080, 22: 2.074,
    23: 2.069, 24: 2.064, 25: 2.060, 26: 2.056, 27: 2.052, 28: 2.048, 29: 2.045,
    30: 2.042,
}


def t95(df: int) -> float:
    if df < 1:
        raise ValueError("grados de libertad deben ser ≥ 1")
    return _T95.get(df, 1.96)


@dataclass(frozen=True)
class DataTdeeResult:
    ok: bool
    reasons: tuple[str, ...]
    window_start: date
    window_end: date
    window_days: int
    n_food_days: int
    n_weighings: int
    n_weighings_first_half: int
    n_weighings_second_half: int
    avg_intake_kcal: float | None
    slope_kg_per_day: float | None = None
    slope_se: float | None = None
    tdee_kcal: float | None = None
    ci_half_width_kcal: float | None = None  # IC 95 %
    confidence: str | None = None  # 'high' | 'medium' | 'low'

    @property
    def ci(self) -> tuple[float, float] | None:
        if self.tdee_kcal is None or self.ci_half_width_kcal is None:
            return None
        return (self.tdee_kcal - self.ci_half_width_kcal, self.tdee_kcal + self.ci_half_width_kcal)


def confidence_label(ci_half_width_kcal: float) -> str:
    if ci_half_width_kcal <= CI_HALF_WIDTH_HIGH:
        return "high"
    if ci_half_width_kcal <= CI_HALF_WIDTH_MEDIUM:
        return "medium"
    return "low"


def _linear_fit(x: np.ndarray, y: np.ndarray) -> tuple[float, float] | None:
    """Pendiente y su error estándar (None si no hay variación en x o n < 3)."""
    n = len(x)
    if n < 3:
        return None
    xm, ym = x.mean(), y.mean()
    sxx = float(((x - xm) ** 2).sum())
    if sxx == 0:
        return None
    slope = float(((x - xm) * (y - ym)).sum() / sxx)
    resid = y - (ym + slope * (x - xm))
    s2 = float((resid**2).sum() / (n - 2))
    return slope, math.sqrt(s2 / sxx)


def estimate_tdee_from_data(
    weight_kg: pd.Series,
    intake_kcal_valid: pd.Series,
    end_date: date | str | pd.Timestamp,
    window_days: int = ADAPT_WINDOW_DAYS,
    min_food_days: int = ADAPT_MIN_FOOD_DAYS,
    min_weighings: int = ADAPT_MIN_WEIGHINGS,
    min_weighings_per_half: int = ADAPT_MIN_WEIGHINGS_PER_HALF,
) -> DataTdeeResult:
    """Gasto estimado por datos en la ventana de `window_days` que termina en `end_date`.

    `weight_kg`: peso diario (NaN = sin pesar).
    `intake_kcal_valid`: calorías diarias solo de días válidos (NaN = día no utilizable).
    Si no se cumplen los mínimos devuelve `ok=False` con los motivos y SIN número de gasto.
    """
    end = pd.Timestamp(end_date).normalize()
    idx = pd.date_range(end - pd.Timedelta(days=window_days - 1), end, freq="D")
    w = weight_kg.reindex(idx)
    k = intake_kcal_valid.reindex(idx)

    half = window_days // 2
    w_first, w_second = w.iloc[:half], w.iloc[half:]
    n_food = int(k.notna().sum())
    n_w = int(w.notna().sum())
    n_w1, n_w2 = int(w_first.notna().sum()), int(w_second.notna().sum())
    avg_intake = float(k.mean()) if n_food else None

    reasons: list[str] = []
    if n_food < min_food_days:
        reasons.append(REASON_FOOD_DAYS)
    if n_w < min_weighings:
        reasons.append(REASON_WEIGHINGS)
    elif n_w1 < min_weighings_per_half or n_w2 < min_weighings_per_half:
        reasons.append(REASON_WEIGHINGS_HALVES)

    base = dict(
        window_start=idx[0].date(),
        window_end=idx[-1].date(),
        window_days=window_days,
        n_food_days=n_food,
        n_weighings=n_w,
        n_weighings_first_half=n_w1,
        n_weighings_second_half=n_w2,
        avg_intake_kcal=avg_intake,
    )
    if reasons:
        return DataTdeeResult(ok=False, reasons=tuple(reasons), **base)

    valid = w.notna().to_numpy()
    x = np.arange(window_days, dtype=float)[valid]
    y = w.to_numpy(dtype=float)[valid]
    fit = _linear_fit(x, y)
    if fit is None:
        return DataTdeeResult(ok=False, reasons=(REASON_NO_VARIATION,), **base)
    slope, se = fit
    tdee = avg_intake - slope * KCAL_PER_KG
    half_width = t95(n_w - 2) * se * KCAL_PER_KG
    return DataTdeeResult(
        ok=True,
        reasons=(),
        slope_kg_per_day=slope,
        slope_se=se,
        tdee_kcal=tdee,
        ci_half_width_kcal=half_width,
        confidence=confidence_label(half_width),
        **base,
    )


def rolling_tdee_from_data(
    weight_kg: pd.Series,
    intake_kcal_valid: pd.Series,
    window_days: int = ADAPT_WINDOW_DAYS,
    **kwargs,
) -> pd.DataFrame:
    """Estimación por datos para cada día final posible; solo filas que cumplen los mínimos."""
    idx = weight_kg.index.union(intake_kcal_valid.index)
    if len(idx) < window_days:
        return pd.DataFrame(columns=["tdee", "ci_low", "ci_high", "confidence", "avg_intake"])
    full = pd.date_range(idx.min(), idx.max(), freq="D")
    w = weight_kg.reindex(full)
    k = intake_kcal_valid.reindex(full)
    rows = []
    for end in full[window_days - 1 :]:
        res = estimate_tdee_from_data(w, k, end, window_days=window_days, **kwargs)
        if res.ok:
            rows.append(
                {
                    "date": end,
                    "tdee": res.tdee_kcal,
                    "ci_low": res.tdee_kcal - res.ci_half_width_kcal,
                    "ci_high": res.tdee_kcal + res.ci_half_width_kcal,
                    "confidence": res.confidence,
                    "avg_intake": res.avg_intake_kcal,
                }
            )
    if not rows:
        return pd.DataFrame(columns=["tdee", "ci_low", "ci_high", "confidence", "avg_intake"])
    return pd.DataFrame(rows).set_index("date")


STATUS_INSUFFICIENT = "insufficient"
STATUS_KEEP = "keep"
STATUS_ADJUST = "adjust"


@dataclass(frozen=True)
class Recommendation:
    status: str
    ideal_kcal: float | None = None  # data_tdee + ajuste del objetivo, con piso en el basal
    recommended_kcal: float | None = None  # ideal con el paso limitado
    delta_kcal: float | None = None  # recommended − meta vigente
    implied_tdee_kcal: float | None = None  # gasto que asume la meta vigente
    within_noise: bool = False  # diferencia de gasto menor que el margen de error
    limited_by_step: bool = False
    limited_by_floor: bool = False
    notes: tuple[str, ...] = field(default_factory=tuple)


def recommend_target(
    data: DataTdeeResult,
    current_target_kcal: float,
    goal: str,
    rate_kg_week: float,
    bmr_kcal: float,
    max_step_kcal: float = ADAPT_MAX_STEP_KCAL,
    noise_floor_kcal: float = ADAPT_NOISE_FLOOR_KCAL,
) -> Recommendation:
    """Recomienda una meta nueva solo si hay datos suficientes.

    - La meta ideal es gasto por datos + ajuste del objetivo, sin bajar del basal.
    - Cambios menores a `noise_floor_kcal` se descartan (ruido).
    - Cada ajuste se limita a ±`max_step_kcal` para no sobrerreaccionar a una
      estimación ruidosa; si falta camino, se repite en la siguiente revisión.
    """
    if not data.ok or data.tdee_kcal is None:
        return Recommendation(status=STATUS_INSUFFICIENT)

    adjustment = goal_adjustment_kcal(goal, rate_kg_week)
    implied_tdee = current_target_kcal - adjustment
    within_noise = abs(data.tdee_kcal - implied_tdee) < (data.ci_half_width_kcal or 0.0)

    ideal_raw = data.tdee_kcal + adjustment
    ideal = max(ideal_raw, bmr_kcal)
    limited_by_floor = ideal_raw < bmr_kcal
    diff = ideal - current_target_kcal

    if abs(diff) < noise_floor_kcal:
        return Recommendation(
            status=STATUS_KEEP,
            ideal_kcal=ideal,
            recommended_kcal=current_target_kcal,
            delta_kcal=0.0,
            implied_tdee_kcal=implied_tdee,
            within_noise=within_noise,
            limited_by_floor=limited_by_floor,
        )

    step = max(-max_step_kcal, min(max_step_kcal, diff))
    recommended = max(current_target_kcal + step, bmr_kcal)
    return Recommendation(
        status=STATUS_ADJUST,
        ideal_kcal=ideal,
        recommended_kcal=recommended,
        delta_kcal=recommended - current_target_kcal,
        implied_tdee_kcal=implied_tdee,
        within_noise=within_noise,
        limited_by_step=abs(diff) > max_step_kcal,
        limited_by_floor=limited_by_floor,
    )
