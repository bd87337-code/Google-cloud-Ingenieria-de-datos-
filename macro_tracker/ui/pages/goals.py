"""Perfil y metas: fórmulas de partida y adaptación con tus datos reales."""
from __future__ import annotations

from datetime import date

import streamlit as st

from macro_tracker import services
from macro_tracker.calc import adaptive
from macro_tracker.config import (
    ACTIVITY_LABELS,
    ADAPT_MIN_FOOD_DAYS,
    ADAPT_MIN_WEIGHINGS,
    BF_SOURCE_LABELS,
    DEFAULT_FAT_G_KG_MIN,
    DEFAULT_FAT_PCT_KCAL,
    DEFAULT_MIN_VALID_DAY_KCAL,
    DEFAULT_PROTEIN_G_KG,
    GOAL_LABELS,
)
from macro_tracker.ui import components as ui
from macro_tracker.ui.state import get_repo

repo = get_repo()
today = date.today()
profile = repo.get_profile()
body = services.current_body_state(repo)

st.title("Perfil y metas")
st.caption("Las fórmulas son solo el punto de partida; con tus datos reales la app estima tu gasto verdadero.")

# ------------------------------------------------------------------ formulario
with st.form("profile_form"):
    c1, c2, c3 = st.columns(3)
    sex = c1.selectbox(
        "Sexo", ["M", "F"], index=0 if not profile or profile["sex"] == "M" else 1,
        format_func={"M": "Hombre", "F": "Mujer"}.get,
    )
    birth = c2.date_input(
        "Fecha de nacimiento",
        value=date.fromisoformat(profile["birth_date"]) if profile else date(2000, 1, 1),
        min_value=date(1920, 1, 1), max_value=today, format="DD/MM/YYYY",
    )
    height = c3.number_input("Estatura (cm)", 120.0, 230.0, float(profile["height_cm"]) if profile else 170.0, 0.5)

    c4, c5, c6 = st.columns(3)
    levels = list(ACTIVITY_LABELS)
    activity = c4.selectbox(
        "Nivel de actividad", levels, index=levels.index(profile["activity_level"]) if profile else 1,
        format_func=ACTIVITY_LABELS.get,
    )
    goals = list(GOAL_LABELS)
    goal = c5.selectbox(
        "Objetivo", goals, index=goals.index(profile["goal"]) if profile else 0, format_func=GOAL_LABELS.get,
    )
    rate = c6.number_input(
        "Ritmo deseado (kg/semana)", 0.0, 1.5, float(profile["rate_kg_week"]) if profile else 0.25, 0.05,
        help="Se ignora si el objetivo es mantener. Ritmos razonables: 0.25–0.5 kg/sem al perder; "
             "0.1–0.25 kg/sem al ganar masa.",
    )

    st.markdown("**Peso y composición actuales** (se guardan como el registro de hoy)")
    c7, c8, c9 = st.columns(3)
    weight_in = c7.number_input(
        "Peso (kg)", 30.0, 300.0, None, 0.1, format="%.1f",
        placeholder=f"último: {body.weight_kg:.1f}" if body.weight_kg else "obligatorio la primera vez",
    )
    bf_in = c8.number_input(
        "% de grasa (opcional)", 3.0, 60.0, None, 0.1, format="%.1f",
        placeholder=f"último: {body.body_fat_pct:.1f}" if body.body_fat_pct else "si no lo conoces, déjalo vacío",
    )
    sources = list(BF_SOURCE_LABELS)
    bf_source = c9.selectbox(
        "Origen del % de grasa", sources, index=1, format_func=BF_SOURCE_LABELS.get,
        help="Sé honesto con el origen: una estimación a ojo no tiene la precisión de una medición.",
    )

    with st.expander("Opciones avanzadas"):
        a1, a2, a3 = st.columns(3)
        p_lo = a1.number_input("Proteína mínima (g/kg)", 0.5, 4.0,
                               float(profile["protein_g_kg_min"]) if profile else DEFAULT_PROTEIN_G_KG[0], 0.1)
        p_hi = a2.number_input("Proteína máxima (g/kg)", 0.5, 4.0,
                               float(profile["protein_g_kg_max"]) if profile else DEFAULT_PROTEIN_G_KG[1], 0.1)
        fat_min = a3.number_input("Grasa mínima (g/kg)", 0.0, 2.0,
                                  float(profile["fat_g_kg_min"]) if profile else DEFAULT_FAT_G_KG_MIN, 0.1)
        a4, a5 = st.columns(2)
        fat_pct = a4.number_input(
            "Grasa objetivo (% de las calorías)", 0.0, 60.0,
            (profile["fat_pct_kcal"] if profile else DEFAULT_FAT_PCT_KCAL) * 100, 1.0,
            help="La grasa será el mayor entre este porcentaje y el mínimo por kg. El resto son carbohidratos.",
        )
        min_valid = a5.number_input(
            "Calorías mínimas para contar un día", 0.0, 3000.0,
            float(profile["min_valid_day_kcal"]) if profile else DEFAULT_MIN_VALID_DAY_KCAL, 50.0,
            help="Un día con menos calorías registradas se considera incompleto y no entra en el promedio "
                 "que estima tu gasto. Puedes forzar un día concreto desde «Hoy».",
        )
        force_mifflin = st.checkbox(
            "Usar siempre Mifflin-St Jeor (ignorar mi % de grasa en el cálculo)",
            value=bool(profile and profile["bmr_method_pref"] == "mifflin"),
            help="Útil si tu % de grasa es solo una estimación.",
        )
    saved = st.form_submit_button("Guardar perfil", type="primary")

if saved:
    if p_hi < p_lo:
        st.error("La proteína máxima no puede ser menor que la mínima.")
    elif weight_in is None and body.weight_kg is None:
        st.error("Necesito al menos un peso para calcular tus metas.")
    else:
        repo.save_profile(
            sex=sex, birth_date=birth, height_cm=height, activity_level=activity, goal=goal,
            rate_kg_week=0.0 if goal == "maintain" else rate, protein_g_kg_min=p_lo, protein_g_kg_max=p_hi,
            fat_g_kg_min=fat_min, fat_pct_kcal=fat_pct / 100, bmr_method_pref="mifflin" if force_mifflin else "auto",
            min_valid_day_kcal=min_valid,
        )
        if weight_in is not None or bf_in is not None:
            existing = repo.get_body(today) or {}
            repo.upsert_body(
                today,
                weight_kg=weight_in if weight_in is not None else existing.get("weight_kg"),
                body_fat_pct=bf_in if bf_in is not None else existing.get("body_fat_pct"),
                body_fat_source=bf_source if bf_in is not None else existing.get("body_fat_source"),
                waist_cm=existing.get("waist_cm"), neck_cm=existing.get("neck_cm"),
                hip_cm=existing.get("hip_cm"), note=existing.get("note"),
            )
        st.success("Perfil guardado.")
        st.rerun()

plan = services.build_plan(repo, today)
if plan is None:
    st.info("Completa y guarda el perfil (con un peso) para calcular tus metas.")
    st.stop()

# ---------------------------------------------------------------- meta por fórmula
st.header("Meta por fórmula")
method_label = ui.bmr_method_label(plan.bmr.method)
if plan.bmr.method == "katch_mcardle":
    st.info(f"Gasto basal calculado con **{method_label}**, porque hay un % de grasa registrado "
            f"({plan.body.body_fat_pct:.1f} %).")
else:
    why = "forzaste este método" if plan.profile["bmr_method_pref"] == "mifflin" else "no hay % de grasa registrado"
    st.info(f"Gasto basal calculado con **{method_label}** ({why}).")

m1, m2, m3 = st.columns(3)
m1.metric("Gasto basal", ui.fmt_kcal(plan.bmr.kcal), help=f"Método: {method_label}")
m2.metric("Gasto total estimado", ui.fmt_kcal(plan.tdee_kcal),
          help="Gasto basal × factor de actividad. Es una estimación: el factor de actividad es el supuesto más débil.")
m3.metric("Meta calórica", ui.fmt_kcal(plan.calories.kcal), delta=f"{plan.calories.adjustment_kcal:+,.0f} kcal vs gasto",
          delta_color="off")

for code in plan.notes:
    (st.warning if code in (services.NOTE_FLOOR_APPLIED, services.NOTE_NO_RECENT_WEIGHT) else st.info)(
        ui.plan_note_text(code, plan)
    )
for code in plan.macros.flags:
    st.warning(ui.macro_flag_text(code))

lo_g, hi_g = plan.macros.protein_range_g
st.markdown(
    f"""
| Macro | Meta | Detalle |
|---|---|---|
| Proteína | **{plan.macros.protein_g:,.0f} g** | rango {lo_g:,.0f}–{hi_g:,.0f} g ({plan.profile['protein_g_kg_min']:.1f}–{plan.profile['protein_g_kg_max']:.1f} g/kg sobre {plan.protein_reference_kg:,.1f} kg de referencia) |
| Grasa | **{plan.macros.fat_g:,.0f} g** | mínimo {plan.macros.fat_floor_g:,.0f} g ({plan.profile['fat_g_kg_min']:.1f} g/kg) |
| Carbohidratos | **{plan.macros.carbs_g:,.0f} g** | el resto de las calorías |
"""
)
if plan.protein_reference_kg < (plan.body.weight_kg or 0) - 0.05:
    st.caption(
        "La proteína se calcula sobre un peso de referencia menor que tu peso real porque tu % de grasa "
        "es alto: así el rango en g/kg no se infla por la grasa corporal."
    )

active = repo.target_on(today)
cA, cB = st.columns([2, 1])
if active:
    src = {"formula": "fórmula", "data": "ajuste por datos", "manual": "manual"}[active["tdee_source"]]
    cA.caption(f"Meta vigente desde {active['effective_from']}: **{active['kcal']:,.0f} kcal** "
               f"(P {active['protein_g']:.0f} · C {active['carbs_g']:.0f} · G {active['fat_g']:.0f} g; origen: {src}).")
else:
    cA.warning("Todavía no tienes una meta vigente. Establece la calculada para empezar a registrar contra ella.")
if cB.button("Establecer como meta vigente", type="primary" if not active else "secondary", width="stretch"):
    services.save_target(repo, plan, plan.calories.kcal, source="formula", note="Calculada por fórmula")
    st.success("Meta vigente actualizada.")
    st.rerun()

with st.expander("Fijar una meta calórica manualmente"):
    manual = st.number_input("Calorías por día", 800.0, 6000.0, float(round(plan.calories.kcal, -1)), 10.0)
    if manual < plan.bmr.kcal:
        st.warning(f"Esa meta está por debajo de tu gasto basal estimado ({plan.bmr.kcal:,.0f} kcal).")
    if st.button("Guardar meta manual"):
        services.save_target(repo, plan, manual, source="manual", note="Fijada manualmente")
        st.rerun()

# -------------------------------------------------------------------- adaptación
st.header("Adaptación con tus datos")
window = st.select_slider("Ventana de análisis (días)", options=[14, 21, 28, 42], value=14,
                          help="Ventanas más largas dan estimaciones más precisas pero menos recientes. "
                               "El día en curso no cuenta porque suele estar incompleto.")
status = services.adaptive_status(repo, plan, window_days=window)
data = status.data

colF, colD = st.columns(2)
colF.metric("Gasto por fórmula", ui.fmt_kcal(plan.tdee_kcal))
if data.ok:
    colD.metric(
        "Gasto por datos", ui.fmt_kcal(data.tdee_kcal),
        delta=f"± {data.ci_half_width_kcal:,.0f} kcal (IC 95 %) · confianza {ui.CONFIDENCE_LABELS[data.confidence]}",
        delta_color="off",
    )
else:
    colD.metric("Gasto por datos", "Sin datos suficientes")

if not data.ok:
    st.warning(
        "Todavía no hay suficientes registros para estimar tu gasto real, así que no se muestra ningún número "
        "(un valor con pocos datos sería falsa precisión). Qué falta:"
    )
    for code in data.reasons:
        st.write("• " + ui.reason_text(code, data))
    p1, p2 = st.columns(2)
    p1.progress(min(1.0, data.n_food_days / ADAPT_MIN_FOOD_DAYS), text=f"Días con comida: {data.n_food_days}/{ADAPT_MIN_FOOD_DAYS}")
    p2.progress(min(1.0, data.n_weighings / ADAPT_MIN_WEIGHINGS), text=f"Pesajes: {data.n_weighings}/{ADAPT_MIN_WEIGHINGS}")
    st.caption(f"Ventana evaluada: {data.window_start:%d/%m/%Y} – {data.window_end:%d/%m/%Y}.")
else:
    st.caption(
        f"Ventana: {data.window_start:%d/%m/%Y} – {data.window_end:%d/%m/%Y} · {data.n_food_days} días de comida · "
        f"{data.n_weighings} pesajes · ingesta promedio {data.avg_intake_kcal:,.0f} kcal · tendencia de peso "
        f"{data.slope_kg_per_day * 7:+.2f} kg/semana."
    )
    if data.confidence == "low":
        st.warning(
            f"Confianza **baja**: el intervalo (±{data.ci_half_width_kcal:,.0f} kcal) es amplio, típico de "
            "ventanas cortas o de peso muy variable. Trátalo como una pista, no como una medición; se afina "
            "con más semanas de registro."
        )
    rec = status.recommendation
    if rec.status == adaptive.STATUS_KEEP:
        if data.confidence == "high":
            st.success(f"Tu meta vigente ({status.current_target_kcal:,.0f} kcal) es coherente con tu gasto real "
                       "estimado (diferencia menor a 100 kcal). No hace falta ajustar.")
        else:
            st.info(
                f"Sin cambios por ahora: tu gasto estimado por datos difiere en menos de 100 kcal del que asume tu "
                f"meta ({status.current_target_kcal:,.0f} kcal). Con el margen de error actual "
                f"(±{data.ci_half_width_kcal:,.0f} kcal) esto significa «no hay evidencia para cambiarla», "
                "no «está confirmada»."
            )
    else:
        st.subheader("Recomendación")
        st.write(
            f"Tu meta vigente ({status.current_target_kcal:,.0f} kcal) asume un gasto de "
            f"≈ {rec.implied_tdee_kcal:,.0f} kcal; tus datos sugieren ≈ {data.tdee_kcal:,.0f} kcal. "
            f"Meta ideal: **{rec.ideal_kcal:,.0f} kcal**. Propuesta: **{rec.recommended_kcal:,.0f} kcal** "
            f"({rec.delta_kcal:+,.0f})."
        )
        if rec.limited_by_step:
            st.caption("El cambio se limita a ±250 kcal por revisión para no sobrerreaccionar a una estimación "
                       "ruidosa; si la tendencia se confirma, se repetirá en la siguiente.")
        if rec.limited_by_floor:
            st.caption("La meta ideal quedaría por debajo de tu gasto basal estimado, así que se respeta ese piso.")
        if rec.within_noise:
            st.warning("La diferencia con el gasto que asume tu meta actual es menor que el margen de error de la "
                       "estimación: puede ser ruido. Considera esperar a tener más datos antes de aplicarla.")
        if st.button("Aplicar recomendación como meta vigente desde hoy", type="primary"):
            services.save_target(
                repo, plan, rec.recommended_kcal, source="data",
                note=f"Ajuste por datos: gasto estimado {data.tdee_kcal:.0f} ± {data.ci_half_width_kcal:.0f} kcal",
            )
            st.success("Meta actualizada.")
            st.rerun()
st.caption("Cómo se calcula y sus límites: ver «Fórmulas y limitaciones» en el README. "
           "La evolución en el tiempo está en la página Progreso.")
