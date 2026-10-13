"""Progreso: peso, calorías, gasto estimado y composición corporal, con filtro de fechas."""
from __future__ import annotations

from datetime import date, timedelta

import pandas as pd
import streamlit as st

from macro_tracker import services
from macro_tracker.config import ADAPT_WINDOW_DAYS
from macro_tracker.ui import charts
from macro_tracker.ui import components as ui
from macro_tracker.ui.state import get_repo

repo = get_repo()
mode = ui.current_mode()
today = date.today()

st.title("Progreso")

# ---- un solo filtro de fechas arriba, que gobierna todos los gráficos
first_dates = [d.index.min() for d in (repo.body_df(), repo.daily_totals()) if not d.empty]
earliest = min(first_dates).date() if first_dates else today - timedelta(days=30)
presets = {"Últimos 30 días": 30, "Últimos 90 días": 90, "Últimos 6 meses": 182, "Todo": None, "Personalizado": "custom"}
f1, f2 = st.columns([1, 2])
preset = f1.selectbox("Rango", list(presets), index=1)
if presets[preset] == "custom":
    picked = f2.date_input("Fechas", value=(max(earliest, today - timedelta(days=90)), today),
                           min_value=date(2000, 1, 1), max_value=today, format="DD/MM/YYYY")
    if not isinstance(picked, (tuple, list)) or len(picked) != 2:
        st.info("Elige la fecha final del rango.")
        st.stop()
    start, end = picked
elif presets[preset] is None:
    start, end = earliest, today
else:
    start, end = today - timedelta(days=presets[preset]), today
if start > end:
    st.error("La fecha inicial es posterior a la final.")
    st.stop()

frame = services.daily_frame(repo, start, end)
if frame["weight_kg"].notna().sum() == 0 and frame["kcal"].notna().sum() == 0:
    st.info("No hay registros en este rango. Empieza por «Hoy» para registrar tu peso y tus comidas.")
    st.stop()

# ---- indicadores
ma = frame["weight_ma7"].dropna()
valid_days = int(frame["food_valid"].sum())
k1, k2, k3, k4 = st.columns(4)
k1.metric("Peso (prom. 7 días)", f"{ma.iloc[-1]:.1f} kg" if len(ma) else "—")
k2.metric("Cambio en el rango", f"{ma.iloc[-1] - ma.iloc[0]:+.1f} kg" if len(ma) > 1 else "—")
k3.metric("Calorías prom. (días válidos)", ui.fmt_kcal(frame["kcal_valid"].mean()) if valid_days else "—")
k4.metric("Días con comida válida", f"{valid_days} de {len(frame)}")
st.caption("Los días sin pesar o sin registrar quedan en blanco: no se rellenan con ceros ni se inventan datos.")

# ---- peso
st.subheader("Peso")
fig = charts.weight_fig(frame, mode)
if fig:
    st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})
    st.caption("Puntos: peso de cada día. Línea: promedio móvil de 7 días (necesita ≥ 3 pesajes en la ventana).")
else:
    st.info("Sin pesajes en este rango.")
ui.table_view(frame[["weight_kg", "weight_ma7"]].dropna(how="all").rename(
    columns={"weight_kg": "Peso (kg)", "weight_ma7": "Promedio móvil 7 d (kg)"}).round(2))

# ---- calorías por semana
st.subheader("Calorías por semana")
weekly = services.weekly_summary(frame)
fig = charts.weekly_calories_fig(weekly, mode)
if fig:
    st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})
    st.caption("Promedio diario de cada semana usando solo días válidos. Las barras claras son semanas con menos "
               "de 4 días registrados: menos fiables.")
else:
    st.info("Sin días de comida válidos en este rango.")
ui.table_view(weekly.assign(week_start=weekly["week_start"].dt.date).rename(columns={
    "week_start": "Semana", "mean_kcal": "kcal/día", "valid_days": "Días válidos", "target_kcal": "Meta"}).round(0)
    if not weekly.empty else weekly, hide_index=True)

# ---- gasto estimado
st.subheader("Gasto estimado: datos vs fórmula")
window = st.select_slider("Ventana de la estimación por datos (días)", options=[14, 21, 28, 42], value=ADAPT_WINDOW_DAYS,
                          key="tdee_window")
timeline = services.tdee_timeline(repo, start, end, window_days=window)
fig = charts.tdee_fig(timeline, mode)
if fig:
    st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})
    if timeline["data_tdee"].notna().sum() == 0:
        st.caption("Aún no hay estimación por datos en este rango: se necesitan al menos 14 días con 10 de comida "
                   "válida y suficientes pesajes. Se muestra solo la fórmula.")
    else:
        st.caption("La banda es el intervalo de confianza al 95 % de la estimación por datos. Si es ancha, la "
                   "estimación es poco precisa: no la trates como un número exacto.")
elif repo.get_profile() is None:
    st.info("Guarda tu perfil en «Perfil y metas» para ver el gasto por fórmula.")
else:
    st.info("Sin datos suficientes en este rango.")
if not timeline.empty:
    ui.table_view(timeline[["formula_tdee", "data_tdee", "ci_low", "ci_high", "confidence"]].dropna(how="all").rename(
        columns={"formula_tdee": "Fórmula", "data_tdee": "Por datos", "ci_low": "IC 95 % inf.",
                 "ci_high": "IC 95 % sup.", "confidence": "Confianza"}).round(0))

# ---- composición corporal
st.subheader("Composición corporal")
fig = charts.body_comp_fig(frame, mode)
if fig:
    st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})
    st.caption("Masa magra = peso suavizado × (1 − % de grasa), con el % interpolado entre mediciones. "
               "Si tus % son estimaciones tuyas, la masa magra hereda ese error.")
else:
    st.info("Registra un % de grasa (o medidas de cuello y cintura) para ver la composición corporal.")
bc = frame[["body_fat_pct", "lean_mass_kg"]].dropna(how="all")
ui.table_view(bc.rename(columns={"body_fat_pct": "% de grasa", "lean_mass_kg": "Masa magra (kg)"}).round(1))
