"""Series de tiempo diarias con datos faltantes.

Convención: toda serie es un `pd.Series` con `DatetimeIndex` diario (sin hora).
Un dato faltante es NaN, nunca 0: un día sin registrar no es un día de 0 kcal.
"""
from __future__ import annotations

from datetime import date
from typing import Mapping

import pandas as pd

from macro_tracker.config import MOVING_AVERAGE_DAYS


def daily_index(start: date | str | pd.Timestamp, end: date | str | pd.Timestamp) -> pd.DatetimeIndex:
    return pd.date_range(pd.Timestamp(start).normalize(), pd.Timestamp(end).normalize(), freq="D")


def moving_average(
    series: pd.Series,
    window_days: int = MOVING_AVERAGE_DAYS,
    min_periods: int = 3,
) -> pd.Series:
    """Promedio móvil por días calendario (ventana terminada en cada día).

    Los NaN no cuentan: si en la ventana hay menos de `min_periods` datos reales,
    el resultado es NaN en vez de un promedio de una sola medición.
    """
    if series.empty:
        return series.astype(float)
    s = series.astype(float).sort_index()
    return s.rolling(f"{window_days}D", min_periods=min_periods).mean()


def valid_food_day_mask(
    kcal: pd.Series,
    min_kcal: float,
    overrides: Mapping[pd.Timestamp, bool] | None = None,
) -> pd.Series:
    """Marca los días con comida registrada de forma utilizable.

    Un día es válido si suma al menos `min_kcal`. Un `override` manual tiene
    prioridad sobre la regla: False descarta el día; True lo acepta aunque no
    llegue al umbral, pero solo si tiene alguna comida registrada (un día en NaN
    nunca es válido).
    """
    mask = kcal.fillna(0.0) >= min_kcal
    if overrides:
        for day, forced in overrides.items():
            ts = pd.Timestamp(day).normalize()
            if ts in mask.index:
                mask.loc[ts] = bool(forced) and pd.notna(kcal.loc[ts])
    return mask


def weekly_intake(kcal_valid: pd.Series) -> pd.DataFrame:
    """Promedio de calorías por semana (lunes–domingo) usando solo días válidos."""
    if kcal_valid.empty:
        return pd.DataFrame(columns=["week_start", "mean_kcal", "valid_days"])
    grouped = kcal_valid.groupby(kcal_valid.index.to_period("W-SUN"))
    out = pd.DataFrame(
        {
            "mean_kcal": grouped.mean(),
            "valid_days": grouped.count(),
        }
    )
    out = out[out["valid_days"] > 0]
    out["week_start"] = [p.start_time.normalize() for p in out.index]
    return out.reset_index(drop=True)[["week_start", "mean_kcal", "valid_days"]]
