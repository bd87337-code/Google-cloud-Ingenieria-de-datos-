"""Constantes y umbrales de la aplicación. Ningún cálculo vive aquí."""
from __future__ import annotations

import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# --- Energía -----------------------------------------------------------------
# Densidad energética asumida para el cambio de peso. Es una aproximación para
# tejido graso; ver README ("Limitaciones").
KCAL_PER_KG = 7700.0
KCAL_PER_G = {"protein": 4.0, "carbs": 4.0, "fat": 9.0}

ACTIVITY_FACTORS = {
    "sedentary": 1.2,
    "light": 1.375,
    "moderate": 1.55,
    "active": 1.725,
    "very_active": 1.9,
}
ACTIVITY_LABELS = {
    "sedentary": "Sedentario (poco o nada de ejercicio)",
    "light": "Ligero (ejercicio 1–3 días/semana)",
    "moderate": "Moderado (ejercicio 3–5 días/semana)",
    "active": "Activo (ejercicio 6–7 días/semana)",
    "very_active": "Muy activo (entrenamiento intenso o trabajo físico)",
}

GOALS = ("maintain", "gain", "lose")
GOAL_LABELS = {
    "maintain": "Mantener",
    "gain": "Ganar masa",
    "lose": "Perder grasa",
}

MEALS = ("breakfast", "lunch", "dinner", "snack")
MEAL_LABELS = {
    "breakfast": "Desayuno",
    "lunch": "Comida",
    "dinner": "Cena",
    "snack": "Colación",
}

BF_SOURCES = ("measured", "self_estimate", "navy")
BF_SOURCE_LABELS = {
    "measured": "medido (báscula, plicómetro, DEXA…)",
    "self_estimate": "estimado por ti",
    "navy": "estimado con medidas (fórmula Navy)",
}

# --- Macros ------------------------------------------------------------------
DEFAULT_PROTEIN_G_KG = (1.6, 2.2)
DEFAULT_FAT_G_KG_MIN = 0.6
DEFAULT_FAT_PCT_KCAL = 0.25
# Peso al que se "normaliza" la masa magra para fijar la proteína (20 % de grasa).
PROTEIN_REFERENCE_BF = 0.20

# --- Adaptación (gasto real por datos) -----------------------------------------
ADAPT_WINDOW_DAYS = 14
ADAPT_MIN_FOOD_DAYS = 10
ADAPT_MIN_WEIGHINGS = 8
ADAPT_MIN_WEIGHINGS_PER_HALF = 3
ADAPT_MAX_STEP_KCAL = 250.0
ADAPT_NOISE_FLOOR_KCAL = 100.0
# Semiancho del intervalo de confianza al 95 % (kcal/día) para etiquetar la confianza.
CI_HALF_WIDTH_HIGH = 250.0
CI_HALF_WIDTH_MEDIUM = 450.0

DEFAULT_MIN_VALID_DAY_KCAL = 1000.0
MOVING_AVERAGE_DAYS = 7

# --- Open Food Facts -----------------------------------------------------------
OFF_SEARCH_URL = "https://world.openfoodfacts.org/cgi/search.pl"
OFF_PRODUCT_URL = "https://world.openfoodfacts.org/api/v2/product/{barcode}.json"
OFF_USER_AGENT = "MacroTrackerLocal/0.1 (personal local app)"
OFF_TIMEOUT_S = 8.0


def db_path() -> Path:
    """Ruta de la base de datos. Se puede cambiar con MACRO_TRACKER_DB."""
    override = os.environ.get("MACRO_TRACKER_DB")
    if override:
        return Path(override).expanduser()
    return PROJECT_ROOT / "data" / "tracker.db"
