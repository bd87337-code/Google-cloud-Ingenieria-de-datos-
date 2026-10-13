"""Gasto basal: Mifflin-St Jeor y Katch-McArdle."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

METHOD_MIFFLIN = "mifflin_st_jeor"
METHOD_KATCH = "katch_mcardle"
METHOD_LABELS = {
    METHOD_MIFFLIN: "Mifflin-St Jeor",
    METHOD_KATCH: "Katch-McArdle",
}

BF_MIN_PCT = 3.0
BF_MAX_PCT = 60.0


@dataclass(frozen=True)
class BmrResult:
    kcal: float
    method: str

    @property
    def label(self) -> str:
        return METHOD_LABELS[self.method]


def _positive(name: str, value: float) -> None:
    if value is None or not value > 0:
        raise ValueError(f"{name} debe ser positivo (recibido: {value!r})")


def check_body_fat(body_fat_pct: float) -> None:
    if not BF_MIN_PCT <= body_fat_pct <= BF_MAX_PCT:
        raise ValueError(
            f"% de grasa fuera de rango [{BF_MIN_PCT}, {BF_MAX_PCT}]: {body_fat_pct!r}"
        )


def age_on(birth_date: date, on_date: date) -> int:
    """Edad cumplida (años enteros) en `on_date`."""
    years = on_date.year - birth_date.year
    if (on_date.month, on_date.day) < (birth_date.month, birth_date.day):
        years -= 1
    return years


def mifflin_st_jeor(weight_kg: float, height_cm: float, age_years: float, sex: str) -> float:
    """BMR = 10·peso + 6.25·estatura − 5·edad + 5 (hombre) / −161 (mujer)."""
    _positive("peso", weight_kg)
    _positive("estatura", height_cm)
    _positive("edad", age_years)
    if sex not in ("M", "F"):
        raise ValueError(f"sexo debe ser 'M' o 'F' (recibido: {sex!r})")
    base = 10.0 * weight_kg + 6.25 * height_cm - 5.0 * age_years
    return base + (5.0 if sex == "M" else -161.0)


def katch_mcardle(weight_kg: float, body_fat_pct: float) -> float:
    """BMR = 370 + 21.6 · masa magra (kg)."""
    _positive("peso", weight_kg)
    check_body_fat(body_fat_pct)
    lean_mass = weight_kg * (1.0 - body_fat_pct / 100.0)
    return 370.0 + 21.6 * lean_mass


def estimate_bmr(
    weight_kg: float,
    height_cm: float,
    age_years: float,
    sex: str,
    body_fat_pct: float | None = None,
    prefer: str = "auto",
) -> BmrResult:
    """Katch-McArdle si hay % de grasa (y `prefer == "auto"`); Mifflin si no.

    `prefer="mifflin"` fuerza Mifflin-St Jeor aunque haya % de grasa; sirve
    cuando ese % es una estimación poco fiable.
    """
    if prefer not in ("auto", "mifflin"):
        raise ValueError(f"prefer debe ser 'auto' o 'mifflin' (recibido: {prefer!r})")
    if body_fat_pct is not None and prefer == "auto":
        return BmrResult(katch_mcardle(weight_kg, body_fat_pct), METHOD_KATCH)
    return BmrResult(mifflin_st_jeor(weight_kg, height_cm, age_years, sex), METHOD_MIFFLIN)
