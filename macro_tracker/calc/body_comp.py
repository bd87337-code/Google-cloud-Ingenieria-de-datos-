"""Composición corporal: masa magra, peso de referencia para proteína, fórmula Navy."""
from __future__ import annotations

import math

import pandas as pd

from macro_tracker.calc.bmr import check_body_fat
from macro_tracker.config import PROTEIN_REFERENCE_BF


def lean_mass_kg(weight_kg: float, body_fat_pct: float) -> float:
    check_body_fat(body_fat_pct)
    return weight_kg * (1.0 - body_fat_pct / 100.0)


def fat_mass_kg(weight_kg: float, body_fat_pct: float) -> float:
    check_body_fat(body_fat_pct)
    return weight_kg * body_fat_pct / 100.0


def protein_reference_weight(
    weight_kg: float,
    body_fat_pct: float | None = None,
    reference_bf: float = PROTEIN_REFERENCE_BF,
) -> float:
    """Peso sobre el que se aplican los g/kg de proteína.

    Sin % de grasa: el peso total. Con % de grasa: la masa magra escalada al
    peso que tendría la persona con `reference_bf` de grasa (por defecto 20 %),
    sin superar nunca el peso real. Evita inflar la proteína objetivo cuando
    hay mucha grasa corporal.
    """
    if body_fat_pct is None:
        return weight_kg
    lean = lean_mass_kg(weight_kg, body_fat_pct)
    return min(weight_kg, lean / (1.0 - reference_bf))


def navy_body_fat_pct(
    sex: str,
    height_cm: float,
    neck_cm: float,
    waist_cm: float,
    hip_cm: float | None = None,
) -> float:
    """% de grasa estimado con la fórmula de la Marina de EE. UU. (medidas en cm).

    Error típico de ±3–4 puntos porcentuales; es una estimación, no una medición.
    Mujeres requieren `hip_cm`.
    """
    if sex not in ("M", "F"):
        raise ValueError(f"sexo debe ser 'M' o 'F' (recibido: {sex!r})")
    for name, value in (("estatura", height_cm), ("cuello", neck_cm), ("cintura", waist_cm)):
        if not value or value <= 0:
            raise ValueError(f"{name} debe ser positiva")
    if sex == "M":
        spread = waist_cm - neck_cm
        if spread <= 0:
            raise ValueError("la cintura debe ser mayor que el cuello")
        density = 1.0324 - 0.19077 * math.log10(spread) + 0.15456 * math.log10(height_cm)
    else:
        if not hip_cm or hip_cm <= 0:
            raise ValueError("las mujeres requieren la medida de cadera")
        spread = waist_cm + hip_cm - neck_cm
        if spread <= 0:
            raise ValueError("cintura + cadera debe ser mayor que el cuello")
        density = 1.29579 - 0.35004 * math.log10(spread) + 0.22100 * math.log10(height_cm)
    return 495.0 / density - 450.0


def interpolate_body_fat(bf_pct: pd.Series) -> pd.Series:
    """% de grasa diario a partir de mediciones espaciadas.

    Interpolación lineal entre mediciones; después de la última se mantiene
    constante; antes de la primera queda NaN (no se extrapola hacia atrás).
    """
    if bf_pct.notna().sum() == 0:
        return bf_pct.astype(float)
    out = bf_pct.astype(float).interpolate(method="time", limit_area="inside")
    return out.ffill()


def lean_mass_series(weight_smooth: pd.Series, bf_daily: pd.Series) -> pd.Series:
    """Masa magra diaria = peso suavizado × (1 − % grasa interpolado)."""
    return weight_smooth * (1.0 - bf_daily / 100.0)
