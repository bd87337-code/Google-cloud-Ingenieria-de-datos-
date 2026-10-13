"""Piezas reutilizables de la interfaz: formato, mensajes en español y tablas de apoyo."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from macro_tracker import services
from macro_tracker.calc import adaptive
from macro_tracker.calc.bmr import METHOD_LABELS
from macro_tracker.calc.targets import FLAG_MINIMUMS_EXCEED_KCAL, FLAG_REDUCED_TO_FIT
from macro_tracker.config import ADAPT_MIN_FOOD_DAYS, ADAPT_MIN_WEIGHINGS, ADAPT_MIN_WEIGHINGS_PER_HALF


def current_mode() -> str:
    """'dark' o 'light' según el tema activo del navegador/app."""
    try:
        return "dark" if st.context.theme.type == "dark" else "light"
    except Exception:  # versiones antiguas o ejecución sin contexto
        return "light"


def fmt_kcal(value: float | None) -> str:
    return "—" if value is None or pd.isna(value) else f"{value:,.0f} kcal"


def fmt_g(value: float | None) -> str:
    return "—" if value is None or pd.isna(value) else f"{value:,.0f} g"


def bmr_method_label(method: str) -> str:
    return METHOD_LABELS[method]


def plan_note_text(code: str, plan: services.Plan) -> str:
    w = plan.body.weight_kg or 0
    texts = {
        services.NOTE_NO_RECENT_WEIGHT: (
            "Tu último peso registrado tiene más de "
            f"{services.STALE_WEIGHT_DAYS} días: las metas usan ese valor. Registra un peso reciente."
        ),
        services.NOTE_BF_SELF_ESTIMATE: (
            "El % de grasa que se está usando es una estimación tuya, no una medición. Katch-McArdle "
            f"lo toma tal cual: cada punto de error mueve el gasto basal ≈ {21.6 * w / 100:.0f} kcal. "
            "Si no confías en ese dato, activa «Usar siempre Mifflin-St Jeor» en opciones avanzadas."
        ),
        services.NOTE_BF_NAVY: (
            "El % de grasa viene de la fórmula Navy (medidas): su error típico es de ±3–4 puntos."
        ),
        services.NOTE_BF_STALE: (
            f"Tu último % de grasa tiene más de {services.STALE_BODY_FAT_DAYS} días; puede estar desactualizado."
        ),
        services.NOTE_BF_IGNORED: (
            "Tienes un % de grasa registrado, pero estás forzando Mifflin-St Jeor: se ignora en el gasto "
            "basal y en la proteína (sí se grafica la masa magra)."
        ),
        services.NOTE_FLOOR_APPLIED: (
            f"El ritmo elegido ({plan.profile['rate_kg_week']:.2f} kg/semana) exigiría ≈ "
            f"{plan.calories.unfloored_kcal:,.0f} kcal/día, por debajo de tu gasto basal estimado "
            f"({plan.calories.floor_kcal:,.0f} kcal). La meta se fijó en el basal, así que el ritmo real "
            f"sería ≈ {abs(plan.calories.effective_rate_kg_week):.2f} kg/semana. Elige un ritmo más lento."
        ),
    }
    return texts[code]


def macro_flag_text(code: str) -> str:
    return {
        FLAG_REDUCED_TO_FIT: (
            "Con esta meta calórica se redujeron grasa y/o proteína respecto a lo ideal para que cuadren "
            "los carbohidratos (siguen sobre sus mínimos)."
        ),
        FLAG_MINIMUMS_EXCEED_KCAL: (
            "Los mínimos de proteína y grasa no caben en esta meta calórica: carbohidratos = 0. "
            "Revisa el ritmo o el rango de proteína."
        ),
    }[code]


def reason_text(code: str, d: adaptive.DataTdeeResult) -> str:
    texts = {
        adaptive.REASON_FOOD_DAYS: (
            f"Días con comida registrada: {d.n_food_days} de {ADAPT_MIN_FOOD_DAYS} necesarios "
            f"(en los últimos {d.window_days} días)."
        ),
        adaptive.REASON_WEIGHINGS: (
            f"Pesajes: {d.n_weighings} de {ADAPT_MIN_WEIGHINGS} necesarios en la ventana."
        ),
        adaptive.REASON_WEIGHINGS_HALVES: (
            f"Los pesajes deben cubrir ambas mitades de la ventana (mínimo {ADAPT_MIN_WEIGHINGS_PER_HALF} en "
            f"cada una); tienes {d.n_weighings_first_half} y {d.n_weighings_second_half}."
        ),
        adaptive.REASON_NO_VARIATION: "No hay variación suficiente en las fechas de pesaje para estimar una tendencia.",
    }
    return texts[code]


CONFIDENCE_LABELS = {"high": "alta", "medium": "media", "low": "baja"}


def table_view(df: pd.DataFrame, label: str = "Ver datos (tabla)", **kwargs) -> None:
    """Equivalente en tabla de un gráfico (el color nunca es el único canal)."""
    with st.expander(label):
        if df is None or df.empty:
            st.caption("Sin datos en este rango.")
        else:
            st.dataframe(df, width="stretch", **kwargs)
