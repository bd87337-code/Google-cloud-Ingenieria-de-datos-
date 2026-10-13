"""Hoy: registro de alimentos, peso y medidas, y progreso contra la meta del día."""
from __future__ import annotations

from datetime import date, datetime

import pandas as pd
import streamlit as st

from macro_tracker import services
from macro_tracker.calc.body_comp import navy_body_fat_pct
from macro_tracker.calc.nutrition import Macros, macros_for_grams
from macro_tracker.config import BF_SOURCE_LABELS, MEAL_LABELS, MEALS
from macro_tracker.foods import service as food_service
from macro_tracker.ui import charts
from macro_tracker.ui import components as ui
from macro_tracker.ui.state import get_repo

repo = get_repo()
mode = ui.current_mode()
profile = repo.get_profile()

st.title("Hoy")
day = st.date_input("Fecha", value=date.today(), max_value=date.today(), format="DD/MM/YYYY")
iso_day = day.isoformat()
log = repo.log_for_date(day)
totals = {k: float(log[c].sum()) for k, c in
          (("kcal", "kcal"), ("protein", "protein_g"), ("carbs", "carbs_g"), ("fat", "fat_g"))}
target = repo.target_on(day)

# -------------------------------------------------------------------- resumen
st.header("Resumen del día")
if target is None:
    st.warning("Aún no hay una meta vigente para esta fecha. Créala en **Perfil y metas**.")

c1, c2 = st.columns([3, 2])
with c1:
    if target:
        goal_kcal = float(target["kcal"])
        pct = totals["kcal"] / goal_kcal
        diff = totals["kcal"] - goal_kcal
        st.metric("Calorías", ui.fmt_kcal(totals["kcal"]),
                  delta=f"{diff:+,.0f} kcal respecto a la meta de {goal_kcal:,.0f}", delta_color="off")
        st.progress(min(1.0, pct), text=f"{pct:.0%} de la meta")
        if pct > 1.0:
            st.caption(f"Superaste la meta por {diff:,.0f} kcal.")
    else:
        st.metric("Calorías", ui.fmt_kcal(totals["kcal"]))
    consumed = {"protein": totals["protein"], "carbs": totals["carbs"], "fat": totals["fat"]}
    goals = ({"protein": target["protein_g"], "carbs": target["carbs_g"], "fat": target["fat_g"]}
             if target else None)
    st.plotly_chart(charts.macro_progress_fig(consumed, goals, mode), width="stretch",
                    config={"displayModeBar": False})
with c2:
    donut = charts.macro_donut_fig(totals["protein"], totals["carbs"], totals["fat"], mode,
                                   logged_kcal=totals["kcal"])
    if donut:
        st.plotly_chart(donut, width="stretch", config={"displayModeBar": False})
        st.caption("Reparto de las calorías entre macros (4·P + 4·C + 9·G). El centro es el total registrado, que puede "
                   "diferir un poco porque cada alimento declara sus propias kcal.")
    else:
        st.caption("Registra alimentos para ver el reparto de macros.")

# Estado del día para el análisis de adaptación
min_kcal = profile["min_valid_day_kcal"] if profile else 1000.0
forced = repo.day_status_map(day, day).get(pd.Timestamp(day))
auto_valid = totals["kcal"] >= min_kcal and day != date.today()
choice_labels = {"auto": "Automático", "yes": "Contar siempre", "no": "No contar"}
current = "auto" if forced is None else ("yes" if forced else "no")
with st.expander("¿Este día cuenta para estimar mi gasto?"):
    picked = st.radio("Estado del día", list(choice_labels), index=list(choice_labels).index(current),
                      format_func=choice_labels.get, horizontal=True, key=f"day_status_{iso_day}")
    if day == date.today():
        st.caption("El día en curso no cuenta en la estimación (casi siempre está incompleto), salvo que lo fuerces.")
    st.caption(f"Automático: cuenta si suma al menos {min_kcal:,.0f} kcal → ahora "
               f"{'sí cuenta' if auto_valid else 'no cuenta'}.")
    if picked != current:
        repo.set_day_status(day, None if picked == "auto" else picked == "yes")
        st.rerun()

# ------------------------------------------------------------- diario del día
st.header("Registro")
if log.empty:
    st.caption("Todavía no hay alimentos registrados este día.")
else:
    view = pd.DataFrame({
        "id": log["id"],
        "Comida": log["meal"].map(MEAL_LABELS),
        "Alimento": [f"{n} ({b})" if b else n for n, b in zip(log["name"], log["brand"])],
        "Cantidad (g)": log["grams"].round(1),
        "kcal": log["kcal"].round(0),
        "Prot (g)": log["protein_g"].round(1),
        "Carb (g)": log["carbs_g"].round(1),
        "Grasa (g)": log["fat_g"].round(1),
        "Borrar": False,
    })
    edited = st.data_editor(
        view, hide_index=True, width="stretch", key=f"log_editor_{iso_day}",
        column_config={"id": None, "Cantidad (g)": st.column_config.NumberColumn(min_value=1, step=1),
                       "Borrar": st.column_config.CheckboxColumn()},
        disabled=["Comida", "Alimento", "kcal", "Prot (g)", "Carb (g)", "Grasa (g)"],
    )
    if st.button("Guardar cambios del registro"):
        for (_, before), (_, after) in zip(view.iterrows(), edited.iterrows()):
            if after["Borrar"]:
                repo.delete_log(int(before["id"]))
            elif abs(after["Cantidad (g)"] - before["Cantidad (g)"]) > 1e-9:
                repo.update_log_grams(int(before["id"]), float(after["Cantidad (g)"]))
        st.rerun()

# ------------------------------------------------------------ agregar alimento
st.header("Agregar alimento")


def food_label(f: dict) -> str:
    tag = {"off": " · OFF", "recipe": " · receta", "custom": ""}[f["source"]]
    warn = " · ⚠ datos dudosos" if f.get("data_flag") else ""
    brand = f" ({f['brand']})" if f.get("brand") else ""
    return f"{f['name']}{brand} — {f['kcal_100g']:.0f} kcal/100 g{tag}{warn}"


def default_meal() -> str:
    hour = datetime.now().hour
    return "breakfast" if hour < 11 else "lunch" if hour < 17 else "dinner" if hour < 21 else "snack"


def add_form(foods: list[dict], key: str) -> None:
    if not foods:
        return
    by_id = {f["id"]: f for f in foods}
    fid = st.selectbox("Alimento", list(by_id), format_func=lambda i: food_label(by_id[i]), key=f"{key}_food")
    food = by_id[fid]
    if food.get("data_flag"):
        st.warning("Las calorías declaradas de este producto no cuadran con sus macros (4·P + 4·C + 9·G). "
                   "Los datos de Open Food Facts son colaborativos; revísalos y corrígelos en "
                   "«Alimentos y recetas» si hace falta.")
    a, b, c = st.columns([1, 1, 1])
    unit_options = ["gramos"] + (["porciones"] if food.get("serving_g") else [])
    unit = a.radio("Unidad", unit_options, horizontal=True, key=f"{key}_unit")
    if unit == "porciones":
        servings = b.number_input("Porciones", 0.25, 50.0, 1.0, 0.25, key=f"{key}_servings")
        grams = servings * food["serving_g"]
        b.caption(f"= {grams:,.0f} g ({food.get('serving_label') or 'porción'})")
    else:
        grams = b.number_input("Gramos", 1.0, 5000.0, float(food.get("serving_g") or 100.0), 5.0, key=f"{key}_grams")
    meal = c.selectbox("Comida", MEALS, index=MEALS.index(default_meal()), format_func=MEAL_LABELS.get,
                       key=f"{key}_meal")
    m = macros_for_grams(Macros(food["kcal_100g"], food["protein_100g"], food["carbs_100g"], food["fat_100g"]), grams)
    st.caption(f"{m.kcal:,.0f} kcal · P {m.protein_g:.1f} g · C {m.carbs_g:.1f} g · G {m.fat_g:.1f} g")
    if st.button("Agregar al registro", type="primary", key=f"{key}_add"):
        repo.add_log(day, meal, fid, grams)
        st.rerun()


tab_search, tab_recent = st.tabs(["Buscar", "Recientes"])
with tab_search:
    with st.form("search_form"):
        query = st.text_input("Buscar alimento", placeholder="p. ej. tortilla de maíz, frijoles, pechuga…")
        mexico = st.checkbox("Si consulto Open Food Facts, solo productos vendidos en México", value=True)
        searched = st.form_submit_button("Buscar")
    if searched and query.strip():
        res = food_service.search(repo, query, mexico_only=mexico)
        st.session_state["search"] = dict(query=query, mexico=mexico, ids=[f["id"] for f in res.foods],
                                          origin=res.origin, error=res.off_error, skipped=res.off_skipped)
    state = st.session_state.get("search")
    if state:
        foods = [f for f in (repo.get_food(i) for i in state["ids"]) if f]
        if state["origin"] == "local":
            st.caption(f"{len(foods)} resultado(s) en tu base local.")
            if st.button("Buscar también en Open Food Facts"):
                extra = food_service.search_off(repo, state["query"], mexico_only=state["mexico"])
                merged = {f["id"]: f for f in foods}
                merged.update({f["id"]: f for f in extra.foods})
                st.session_state["search"].update(ids=list(merged), error=extra.off_error, skipped=extra.off_skipped,
                                                  origin="local")
                st.rerun()
        elif state["origin"] == "off":
            st.caption(f"{len(foods)} resultado(s) de Open Food Facts (guardados en tu base local para la próxima vez).")
        if state["error"]:
            st.error(f"No pude consultar Open Food Facts ({state['error']}). Puedes trabajar con tu base local o "
                     "crear el alimento a mano en «Alimentos y recetas».")
        elif not foods:
            st.info("No encontré nada. La cobertura de comida mexicana en bases públicas es limitada: crea el "
                    "alimento o la receta en **Alimentos y recetas** y quedará guardado.")
        if state.get("skipped"):
            st.caption(f"{state['skipped']} producto(s) de OFF se descartaron por datos nutricionales incompletos.")
        add_form(foods, "search")
with tab_recent:
    recent = repo.recent_foods()
    if recent:
        add_form(recent, "recent")
    else:
        st.caption("Aquí aparecerán los alimentos que más has usado.")

# ------------------------------------------------------------ peso y medidas
st.header("Peso y medidas")
body = repo.get_body(day) or {}
with st.expander("Registrar o editar el peso y las medidas de este día", expanded=not body):
    st.caption("Todo es opcional: puedes registrar solo el peso, o ningún dato. Un día sin pesar no rompe nada.")
    with st.form(f"body_form_{iso_day}"):
        b1, b2, b3 = st.columns(3)
        weight = b1.number_input("Peso (kg)", 30.0, 300.0, body.get("weight_kg"), 0.1, format="%.1f")
        bf = b2.number_input("% de grasa", 3.0, 60.0, body.get("body_fat_pct"), 0.1, format="%.1f")
        sources = list(BF_SOURCE_LABELS)
        src_default = sources.index(body["body_fat_source"]) if body.get("body_fat_source") in sources else 1
        bf_source = b3.selectbox("Origen del % de grasa", sources[:2], index=min(src_default, 1),
                                 format_func=BF_SOURCE_LABELS.get)
        d1, d2, d3 = st.columns(3)
        neck = d1.number_input("Cuello (cm)", 20.0, 80.0, body.get("neck_cm"), 0.5)
        waist = d2.number_input("Cintura (cm)", 40.0, 200.0, body.get("waist_cm"), 0.5)
        hip = d3.number_input("Cadera (cm, solo mujeres)", 50.0, 200.0, body.get("hip_cm"), 0.5)
        use_navy = st.checkbox(
            "Si no escribí un % de grasa, estimarlo con mis medidas (fórmula Navy, error típico ±3–4 puntos)")
        note = st.text_input("Nota", value=body.get("note") or "")
        save = st.form_submit_button("Guardar", type="primary")
    if save:
        problem = None
        navy_used = False
        if bf is None and use_navy:
            if profile is None:
                problem = "Para la fórmula Navy necesito tu perfil (sexo y estatura)."
            elif neck is None or waist is None or (profile["sex"] == "F" and hip is None):
                problem = "La fórmula Navy requiere cuello y cintura (y cadera en mujeres)."
            else:
                try:
                    bf = round(navy_body_fat_pct(profile["sex"], profile["height_cm"], neck, waist, hip), 1)
                    navy_used = True
                except ValueError as exc:
                    problem = str(exc)
        if problem:
            st.error(problem)
        else:
            unchanged_navy = (bf is not None and body.get("body_fat_source") == "navy"
                              and abs(bf - body.get("body_fat_pct", -1)) < 1e-9)
            source = "navy" if (navy_used or unchanged_navy) else (bf_source if bf is not None else None)
            repo.upsert_body(day, weight_kg=weight, body_fat_pct=bf, body_fat_source=source,
                             waist_cm=waist, neck_cm=neck, hip_cm=hip, note=note)
            st.rerun()
    if body and st.button("Borrar el registro corporal de este día"):
        repo.delete_body(day)
        st.rerun()
