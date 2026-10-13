"""Gráficos Plotly.

Reglas de diseño aplicadas (guía de visualización de datos):
- Color por entidad y en orden fijo: proteína = azul, carbohidratos = naranja, grasa = aguamarina,
  en todos los gráficos. Paleta validada (CVD y contraste) en modo claro y oscuro.
- Un solo eje por gráfico: nunca ejes duales (composición corporal = dos paneles).
- Marcas finas, rejilla solo con líneas finas y sólidas, leyenda cuando hay ≥ 2 series,
  etiquetas directas selectivas (nunca un número en cada punto).
- Cada gráfico tiene su vista de tabla en la interfaz (el color no es el único canal).

Robustez de tema: los fondos, la leyenda y la mayor parte del texto no llevan color fijo (los hereda
el tema activo de Streamlit) y rejilla, ejes, marcas y pistas usan grises neutros que se leen sobre
fondo claro y oscuro. Dependen del modo detectado (`st.context.theme.type`) solo las series y la
"tinta" de los valores clave (etiquetas de barras, porcentajes y total de la dona): en tema claro
Streamlit pinta el texto de Plotly con un gris de 3.7:1, por debajo de AA. La detección es fiable
con los dos temas de `.streamlit/config.toml`; un `[theme]` plano en la config global del usuario la
desincronizaría y solo degradaría esas etiquetas.
"""
from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from macro_tracker.config import KCAL_PER_G

TOKENS = {
    "light": dict(
        surface="#fcfcfb", ink="#0b0b0b", ink2="#52514e",
        series=["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948"],
    ),
    "dark": dict(
        surface="#1a1a19", ink="#f0efec", ink2="#c3c2b7",
        series=["#3987e5", "#d95926", "#199e70", "#c98500", "#d55181", "#008300", "#9085e9", "#e66767"],
    ),
}
FONT = "system-ui, -apple-system, 'Segoe UI', sans-serif"
MUTED = "#767676"                       # neutro: 4.5:1 sobre blanco y 4.2:1 sobre #0e1117
GRID = "rgba(128, 128, 128, 0.20)"      # hairline neutro, recesivo en claro y oscuro
AXIS = "rgba(128, 128, 128, 0.45)"
TRACK = "rgba(128, 128, 128, 0.18)"     # pista de las barras de progreso
MAX_MARKED_POINTS = 120   # más puntos que esto y los marcadores se vuelven ruido

MACRO_LABELS = {"protein": "Proteína", "carbs": "Carbohidratos", "fat": "Grasa"}
MACRO_SLOT = {"protein": 0, "carbs": 1, "fat": 2}   # el color sigue a la entidad


def _t(mode: str) -> dict:
    return TOKENS["dark" if mode == "dark" else "light"]


def macro_color(macro: str, mode: str) -> str:
    return _t(mode)["series"][MACRO_SLOT[macro]]


def _rgba(hex_color: str, alpha: float) -> str:
    """Color de serie con transparencia (funciona sobre cualquier fondo, sin conocer la superficie)."""
    r, g, b = (int(hex_color[i:i + 2], 16) for i in (1, 3, 5))
    return f"rgba({r}, {g}, {b}, {alpha})"


def _layout(fig: go.Figure, mode: str, *, height: int, legend: bool, title: str | None = None,
            y_title: str | None = None) -> go.Figure:
    fig.update_layout(
        title=dict(text=title, x=0, xanchor="left", font=dict(size=15)) if title else None,
        height=height,
        margin=dict(l=8, r=16, t=48 if title else 16, b=8),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family=FONT, size=12),
        showlegend=legend,
        legend=dict(orientation="h", yanchor="bottom", y=1.0, xanchor="left", x=0, bgcolor="rgba(0,0,0,0)"),
        hovermode="x unified",
        hoverlabel=dict(font=dict(family=FONT, size=12)),
    )
    fig.update_xaxes(showgrid=False, linecolor=AXIS, linewidth=1, ticks="", tickfont=dict(color=MUTED),
                     zeroline=False)
    fig.update_yaxes(showgrid=True, gridcolor=GRID, gridwidth=1, zeroline=False, ticks="",
                     tickfont=dict(color=MUTED), title=dict(text=y_title, font=dict(color=MUTED)))
    return fig


# ------------------------------------------------------------------ macros del día
def macro_progress_fig(consumed: dict[str, float], target: dict[str, float] | None, mode: str) -> go.Figure:
    """Una barra por macro: consumido (color de la entidad) sobre una pista que llega a la meta."""
    t = _t(mode)
    macros = ["protein", "carbs", "fat"]
    labels = [MACRO_LABELS[m] for m in macros]
    fig = go.Figure()
    if target:
        fig.add_bar(
            y=labels, x=[max(target[m], consumed[m]) for m in macros], orientation="h",
            marker=dict(color=TRACK, cornerradius=4), hoverinfo="skip", showlegend=False,
        )
    for m, label in zip(macros, labels):
        goal = target[m] if target else None
        text = f"{consumed[m]:.0f} / {goal:.0f} g" if goal else f"{consumed[m]:.0f} g"
        fig.add_bar(
            y=[label], x=[consumed[m]], orientation="h", name=label,
            marker=dict(color=macro_color(m, mode), cornerradius=4),
            text=[text], textposition="outside", cliponaxis=False,
            textfont=dict(size=12, color=t["ink"]),
            hovertemplate=f"{label}: %{{x:.0f}} g" + (f" de {goal:.0f} g<extra></extra>" if goal else "<extra></extra>"),
            showlegend=False,
        )
    fig.update_layout(barmode="overlay", bargap=0.55)
    _layout(fig, mode, height=170, legend=False)
    fig.update_layout(hovermode="closest", margin=dict(l=8, r=90, t=8, b=8))
    fig.update_xaxes(visible=False)
    fig.update_yaxes(showgrid=False, autorange="reversed", tickfont=dict(size=13, color=t["ink"]))
    return fig


def macro_donut_fig(protein_g: float, carbs_g: float, fat_g: float, mode: str,
                    logged_kcal: float | None = None) -> go.Figure | None:
    """Reparto de las calorías del día entre macros (parte-a-todo, 3 segmentos).

    Los porcentajes se calculan con 4·P + 4·C + 9·G. El centro muestra `logged_kcal` (las kcal
    declaradas de los alimentos) si se da, para que coincida con el resto de la pantalla.
    """
    kcal = {
        "protein": protein_g * KCAL_PER_G["protein"],
        "carbs": carbs_g * KCAL_PER_G["carbs"],
        "fat": fat_g * KCAL_PER_G["fat"],
    }
    total = sum(kcal.values())
    if total <= 0:
        return None
    t = _t(mode)
    macros = list(kcal)
    fig = go.Figure(
        go.Pie(
            labels=[MACRO_LABELS[m] for m in macros], values=[kcal[m] for m in macros], hole=0.62,
            sort=False, direction="clockwise",
            marker=dict(colors=[macro_color(m, mode) for m in macros], line=dict(color=t["surface"], width=2)),
            textinfo="percent", textposition="outside", textfont=dict(size=12, color=t["ink"]),
            hovertemplate="%{label}: %{value:.0f} kcal (%{percent})<extra></extra>",
        )
    )
    center = total if logged_kcal is None else logged_kcal
    fig.add_annotation(text=f"<b>{center:,.0f}</b><br>kcal", x=0.5, y=0.5, showarrow=False,
                       font=dict(size=15, color=t["ink"]))
    _layout(fig, mode, height=250, legend=True)
    fig.update_layout(hovermode="closest", legend=dict(orientation="h", yanchor="top", y=-0.02, x=0.5,
                                                       xanchor="center"))
    return fig


# --------------------------------------------------------------------------- peso
def weight_fig(frame: pd.DataFrame, mode: str) -> go.Figure | None:
    """Peso diario (puntos) y promedio móvil de 7 días (línea). Los días sin pesar quedan en blanco."""
    w = frame["weight_kg"]
    if w.notna().sum() == 0:
        return None
    t = _t(mode)
    blue = t["series"][0]
    dense = int(w.notna().sum()) > MAX_MARKED_POINTS
    fig = go.Figure()
    fig.add_scatter(
        x=frame.index, y=w, name="Peso diario",
        mode="lines" if dense else "markers",
        line=dict(color=MUTED, width=1),
        marker=dict(color=MUTED, size=8, line=dict(color=t["surface"], width=2)),
        connectgaps=False, hovertemplate="%{y:.1f} kg",
    )
    fig.add_scatter(
        x=frame.index, y=frame["weight_ma7"], name="Promedio móvil 7 días", mode="lines",
        line=dict(color=blue, width=2), connectgaps=False, hovertemplate="%{y:.2f} kg",
    )
    _layout(fig, mode, height=320, legend=True, y_title="kg")
    fig.update_yaxes(rangemode="normal")
    fig.update_xaxes(hoverformat="%d/%m/%Y", tickformat="%d/%m")
    return fig


# ------------------------------------------------------------------------ calorías
def weekly_calories_fig(weekly: pd.DataFrame, mode: str, min_days_solid: int = 4) -> go.Figure | None:
    """Calorías promedio por semana (solo días válidos). Semanas con pocos días se atenúan."""
    if weekly.empty:
        return None
    t = _t(mode)
    blue = t["series"][0]
    solid = weekly["valid_days"] >= min_days_solid
    fig = go.Figure()
    fig.add_bar(
        x=weekly["week_start"], y=weekly["mean_kcal"], name="Calorías promedio",
        marker=dict(color=[blue if s else _rgba(blue, 0.40) for s in solid], cornerradius=4),
        customdata=weekly[["valid_days"]].to_numpy(),
        hovertemplate="%{y:,.0f} kcal/día<br>%{customdata[0]} días con registro<extra></extra>",
    )
    has_target = bool("target_kcal" in weekly and weekly["target_kcal"].notna().any())
    if has_target:
        fig.add_scatter(
            x=weekly["week_start"], y=weekly["target_kcal"], name="Meta", mode="lines",
            line=dict(color=MUTED, width=2, shape="hv"), hovertemplate="%{y:,.0f} kcal",
        )
    fig.update_layout(bargap=0.45)
    _layout(fig, mode, height=300, legend=has_target, y_title="kcal/día")
    fig.update_xaxes(hoverformat="Semana del %d/%m/%Y", tickformat="%d/%m")
    return fig


# --------------------------------------------------------------------------- gasto
def tdee_fig(timeline: pd.DataFrame, mode: str) -> go.Figure | None:
    """Gasto estimado por datos (con intervalo 95 %) vs por fórmula."""
    if timeline is None or timeline.empty:
        return None
    has_formula = bool(timeline["formula_tdee"].notna().any())
    has_data = bool(timeline["data_tdee"].notna().any())
    if not (has_formula or has_data):
        return None
    t = _t(mode)
    blue, orange = t["series"][0], t["series"][1]
    fig = go.Figure()
    if has_data:
        band = timeline.dropna(subset=["data_tdee"])
        fig.add_scatter(x=band.index, y=band["ci_high"], mode="lines", line=dict(width=0),
                        hoverinfo="skip", showlegend=False)
        fig.add_scatter(x=band.index, y=band["ci_low"], mode="lines", line=dict(width=0),
                        fill="tonexty", fillcolor=_rgba(blue, 0.18),
                        name="Intervalo 95 %", hoverinfo="skip")
        fig.add_scatter(x=timeline.index, y=timeline["data_tdee"], mode="lines", name="Por datos",
                        line=dict(color=blue, width=2), connectgaps=False,
                        customdata=timeline[["ci_low", "ci_high"]].to_numpy(),
                        hovertemplate="%{y:,.0f} kcal (IC 95 %: %{customdata[0]:,.0f}–%{customdata[1]:,.0f})")
    if has_formula:
        fig.add_scatter(x=timeline.index, y=timeline["formula_tdee"], mode="lines", name="Por fórmula",
                        line=dict(color=orange, width=2), connectgaps=False, hovertemplate="%{y:,.0f} kcal")
    _layout(fig, mode, height=320, legend=True, y_title="kcal/día")
    fig.update_xaxes(hoverformat="%d/%m/%Y", tickformat="%d/%m")
    return fig


# ------------------------------------------------------------------ composición
def body_comp_fig(frame: pd.DataFrame, mode: str) -> go.Figure | None:
    """% de grasa (mediciones) y masa magra estimada, en dos paneles (nunca eje doble)."""
    bf = frame["body_fat_pct"].dropna()
    lean = frame["lean_mass_kg"].dropna()
    if bf.empty and lean.empty:
        return None
    t = _t(mode)
    blue, orange = t["series"][0], t["series"][1]
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.14,
                        subplot_titles=("Masa magra estimada (kg)", "% de grasa registrado"))
    if not lean.empty:
        fig.add_scatter(x=lean.index, y=lean, mode="lines", name="Masa magra (kg)",
                        line=dict(color=blue, width=2), hovertemplate="%{y:.1f} kg", row=1, col=1)
    if not bf.empty:
        fig.add_scatter(x=bf.index, y=bf, mode="lines+markers", name="% de grasa",
                        line=dict(color=orange, width=2),
                        marker=dict(color=orange, size=8, line=dict(color=t["surface"], width=2)),
                        hovertemplate="%{y:.1f} %", row=2, col=1)
    # Una serie por panel y cada panel lleva su título: no hace falta leyenda.
    _layout(fig, mode, height=420, legend=False)
    for ann in fig.layout.annotations:
        ann.update(x=0, xanchor="left", font=dict(size=12))
    fig.update_xaxes(hoverformat="%d/%m/%Y", tickformat="%d/%m")
    return fig
