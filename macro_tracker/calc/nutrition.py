"""Utilidades de macros por alimento."""
from __future__ import annotations

from dataclasses import dataclass

from macro_tracker.config import KCAL_PER_G


@dataclass(frozen=True)
class Macros:
    kcal: float
    protein_g: float
    carbs_g: float
    fat_g: float

    def scaled(self, factor: float) -> "Macros":
        return Macros(
            self.kcal * factor,
            self.protein_g * factor,
            self.carbs_g * factor,
            self.fat_g * factor,
        )

    def __add__(self, other: "Macros") -> "Macros":
        return Macros(
            self.kcal + other.kcal,
            self.protein_g + other.protein_g,
            self.carbs_g + other.carbs_g,
            self.fat_g + other.fat_g,
        )


ZERO = Macros(0.0, 0.0, 0.0, 0.0)


def macros_for_grams(per_100g: Macros, grams: float) -> Macros:
    """Macros de `grams` de un alimento cuya ficha está por 100 g."""
    if grams < 0:
        raise ValueError("los gramos no pueden ser negativos")
    return per_100g.scaled(grams / 100.0)


def kcal_from_macros(protein_g: float, carbs_g: float, fat_g: float) -> float:
    return (
        KCAL_PER_G["protein"] * protein_g
        + KCAL_PER_G["carbs"] * carbs_g
        + KCAL_PER_G["fat"] * fat_g
    )


def kcal_mismatch(
    kcal: float,
    protein_g: float,
    carbs_g: float,
    fat_g: float,
    rel_tol: float = 0.15,
    abs_tol: float = 20.0,
) -> bool:
    """True si las kcal declaradas no cuadran con 4P + 4C + 9F.

    Se toleran `rel_tol` (fibra, alcohol y polialcoholes explican diferencias
    legítimas) o `abs_tol` kcal por cada 100 g, lo que sea mayor.
    """
    expected = kcal_from_macros(protein_g, carbs_g, fat_g)
    return abs(kcal - expected) > max(rel_tol * max(kcal, expected), abs_tol)


def validate_per_100g(m: Macros) -> list[str]:
    """Errores de plausibilidad para una ficha por 100 g (lista vacía = válida)."""
    errors: list[str] = []
    for name, value in (
        ("kcal", m.kcal),
        ("proteína", m.protein_g),
        ("carbohidratos", m.carbs_g),
        ("grasa", m.fat_g),
    ):
        if value < 0:
            errors.append(f"{name} no puede ser negativa")
    if m.kcal > 900:
        errors.append("más de 900 kcal por 100 g no es posible (la grasa pura tiene ~900)")
    if m.protein_g + m.carbs_g + m.fat_g > 100.5:
        errors.append("proteína + carbohidratos + grasa suman más de 100 g por 100 g")
    return errors
