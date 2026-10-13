"""Alimentos y recetas: crear los tuyos (obligatorio para comida mexicana), editar y combinar."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from macro_tracker.calc.nutrition import Macros, kcal_from_macros, kcal_mismatch
from macro_tracker.foods.recipes import recipe_per_100g, recompute_dependents, save_recipe
from macro_tracker.ui.state import get_repo

repo = get_repo()
st.title("Alimentos y recetas")
st.caption("Los datos nutricionales van **por 100 g**. Lo que crees aquí se busca primero que cualquier base pública.")

tab_new, tab_recipe, tab_base = st.tabs(["Crear alimento", "Recetas", "Mi base de alimentos"])


def _check_kcal(kcal: float, p: float, c: float, f: float) -> None:
    if kcal_mismatch(kcal, p, c, f):
        st.warning(f"Las calorías ({kcal:.0f}) no cuadran con los macros: 4·P + 4·C + 9·G = "
                   f"{kcal_from_macros(p, c, f):.0f}. Puede ser fibra o alcohol, o un dato mal capturado.")


# ------------------------------------------------------------------ crear alimento
with tab_new:
    with st.form("new_food", clear_on_submit=True):
        n1, n2 = st.columns([2, 1])
        name = n1.text_input("Nombre", placeholder="Tortilla de maíz (tortillería)")
        brand = n2.text_input("Marca (opcional)")
        k1, k2, k3, k4 = st.columns(4)
        kcal = k1.number_input("kcal / 100 g", 0.0, 900.0, 0.0, 1.0)
        protein = k2.number_input("Proteína (g)", 0.0, 100.0, 0.0, 0.1)
        carbs = k3.number_input("Carbohidratos (g)", 0.0, 100.0, 0.0, 0.1)
        fat = k4.number_input("Grasa (g)", 0.0, 100.0, 0.0, 0.1)
        derive = st.checkbox("Calcular las calorías a partir de los macros (4·P + 4·C + 9·G)",
                             help="Útil si solo conoces los macros.")
        s1, s2 = st.columns(2)
        serving_g = s1.number_input("Porción habitual (g, opcional)", 0.0, 2000.0, 0.0, 1.0)
        serving_label = s2.text_input("Descripción de la porción", placeholder="1 tortilla chica")
        created = st.form_submit_button("Guardar alimento", type="primary")
    if created:
        final_kcal = kcal_from_macros(protein, carbs, fat) if derive else kcal
        try:
            repo.add_food(name, final_kcal, protein, carbs, fat, brand=brand or None,
                          serving_g=serving_g or None, serving_label=serving_label or None)
        except ValueError as exc:
            st.error(str(exc))
        else:
            st.success(f"«{name}» guardado. Ya puedes registrarlo desde «Hoy».")
            if not derive:
                _check_kcal(final_kcal, protein, carbs, fat)

# ---------------------------------------------------------------------- recetas
with tab_recipe:
    recipes = repo.list_foods(source="recipe")
    options = [None] + [r["id"] for r in recipes]
    names = {r["id"]: r["name"] for r in recipes}
    chosen = st.selectbox("Receta", options, format_func=lambda i: "➕ Nueva receta" if i is None else names[i])

    draft = st.session_state.get("recipe_draft")
    if draft is None or draft["loaded_for"] != chosen:
        if chosen is None:
            draft = dict(loaded_for=None, id=None, name="", items=[], yield_g=None, servings=1.0)
        else:
            rec = repo.get_recipe(chosen)
            draft = dict(loaded_for=chosen, id=chosen, name=names[chosen],
                         items=[(i["ingredient_food_id"], i["grams"]) for i in rec["items"]],
                         yield_g=rec["total_yield_g"], servings=rec["servings"])
        st.session_state["recipe_draft"] = draft

    draft["name"] = st.text_input("Nombre de la receta", value=draft["name"], placeholder="Tacos de frijol con queso")

    st.markdown("**Ingredientes**")
    q = st.text_input("Buscar ingrediente en tu base", key="ing_query")
    candidates = repo.search_foods(q, limit=30) if q.strip() else []
    if q.strip() and not candidates:
        st.caption("Sin resultados. Crea el ingrediente en la pestaña «Crear alimento» (o búscalo en «Hoy» para "
                   "traerlo de Open Food Facts).")
    if candidates:
        by_id = {f["id"]: f for f in candidates}
        a, b, c = st.columns([3, 1, 1])
        ing = a.selectbox("Ingrediente", list(by_id), format_func=lambda i: f"{by_id[i]['name']} — {by_id[i]['kcal_100g']:.0f} kcal/100 g")
        grams = b.number_input("Gramos (crudo)", 1.0, 5000.0, 100.0, 5.0)
        if c.button("Agregar ingrediente", width="stretch"):
            if ing == draft["id"]:
                st.error("Una receta no puede contenerse a sí misma.")
            else:
                draft["items"].append((ing, grams))
                st.rerun()

    if draft["items"]:
        foods = {i: repo.get_food(i) for i, _ in draft["items"]}
        table = pd.DataFrame({
            "Ingrediente": [foods[i]["name"] for i, _ in draft["items"]],
            "Gramos": [g for _, g in draft["items"]],
            "Quitar": False,
        })
        edited = st.data_editor(table, hide_index=True, width="stretch", key=f"ing_editor_{chosen}",
                                column_config={"Gramos": st.column_config.NumberColumn(min_value=1, step=5)},
                                disabled=["Ingrediente"])
        draft["items"] = [(i, float(row["Gramos"])) for (i, _), (_, row) in zip(draft["items"], edited.iterrows())
                          if not row["Quitar"]]
        raw_total = sum(g for _, g in draft["items"])
        if draft["items"]:
            y1, y2 = st.columns(2)
            yield_g = y1.number_input(
                "Peso final del platillo (g)", 1.0, 20000.0, float(draft["yield_g"] or raw_total), 5.0,
                help="Pésalo ya cocido. Si pierde agua, es menor que la suma de los crudos y las macros por 100 g suben.")
            servings = y2.number_input("Porciones que rinde", 0.5, 100.0, float(draft["servings"]), 0.5)
            per100 = recipe_per_100g([(Macros(foods[i]["kcal_100g"], foods[i]["protein_100g"],
                                              foods[i]["carbs_100g"], foods[i]["fat_100g"]), g)
                                      for i, g in draft["items"]], yield_g)
            per_serv = per100.scaled(yield_g / servings / 100)
            st.caption(f"Por 100 g: {per100.kcal:.0f} kcal · P {per100.protein_g:.1f} · C {per100.carbs_g:.1f} · "
                       f"G {per100.fat_g:.1f}   |   Por porción (~{yield_g / servings:.0f} g): {per_serv.kcal:.0f} kcal · "
                       f"P {per_serv.protein_g:.1f} · C {per_serv.carbs_g:.1f} · G {per_serv.fat_g:.1f}")
            s1, s2 = st.columns([1, 1])
            if s1.button("Guardar receta", type="primary", width="stretch"):
                try:
                    rid = save_recipe(repo, draft["name"], draft["items"], total_yield_g=yield_g, servings=servings,
                                      recipe_id=draft["id"])
                except (ValueError, KeyError) as exc:
                    st.error(str(exc))
                else:
                    st.session_state.pop("recipe_draft", None)
                    st.success(f"Receta «{draft['name']}» guardada (id {rid}).")
                    st.rerun()
            if draft["id"] and s2.button("Eliminar receta", width="stretch"):
                outcome = repo.delete_food(draft["id"])
                st.session_state.pop("recipe_draft", None)
                st.toast("Receta archivada (ya estaba en tu registro)" if outcome == "archived" else "Receta eliminada")
                st.rerun()
        else:
            st.caption("Agrega al menos un ingrediente.")

# ----------------------------------------------------------------- mi base
with tab_base:
    include_archived = st.checkbox("Mostrar archivados")
    foods_all = repo.list_foods(include_archived=include_archived)
    if not foods_all:
        st.caption("Aún no tienes alimentos guardados.")
    else:
        origin = {"custom": "propio", "off": "Open Food Facts", "recipe": "receta"}
        df = pd.DataFrame([{
            "Alimento": f["name"], "Marca": f["brand"] or "", "Origen": origin[f["source"]],
            "kcal/100g": round(f["kcal_100g"], 1), "P": round(f["protein_100g"], 1), "C": round(f["carbs_100g"], 1),
            "G": round(f["fat_100g"], 1), "Porción (g)": f["serving_g"],
            "Aviso": "kcal ≠ macros" if f["data_flag"] else "", "Archivado": bool(f["archived"]),
        } for f in foods_all])
        st.dataframe(df, hide_index=True, width="stretch")

        by_id = {f["id"]: f for f in foods_all}
        fid = st.selectbox("Editar o borrar un alimento", list(by_id), format_func=lambda i: by_id[i]["name"])
        food = by_id[fid]
        if food["source"] == "recipe":
            st.info("Las recetas se editan en la pestaña «Recetas».")
        else:
            with st.form(f"edit_food_{fid}"):
                e1, e2 = st.columns([2, 1])
                ename = e1.text_input("Nombre", food["name"])
                ebrand = e2.text_input("Marca", food["brand"] or "")
                f1, f2, f3, f4 = st.columns(4)
                ekcal = f1.number_input("kcal / 100 g", 0.0, 900.0, float(food["kcal_100g"]), 1.0)
                eprot = f2.number_input("Proteína (g)", 0.0, 100.0, float(food["protein_100g"]), 0.1)
                ecarb = f3.number_input("Carbohidratos (g)", 0.0, 100.0, float(food["carbs_100g"]), 0.1)
                efat = f4.number_input("Grasa (g)", 0.0, 100.0, float(food["fat_100g"]), 0.1)
                g1, g2 = st.columns(2)
                eserv = g1.number_input("Porción (g)", 0.0, 2000.0, float(food["serving_g"] or 0.0), 1.0)
                elabel = g2.text_input("Descripción de la porción", food["serving_label"] or "")
                restore = st.checkbox("Restaurar (quitar de archivados)", value=False) if food["archived"] else False
                b1, b2 = st.columns(2)
                update = b1.form_submit_button("Guardar cambios", type="primary")
                delete = b2.form_submit_button("Borrar / archivar")
            if update:
                try:
                    repo.update_food(fid, name=ename, brand=ebrand or None, kcal_100g=ekcal, protein_100g=eprot,
                                     carbs_100g=ecarb, fat_100g=efat, serving_g=eserv or None,
                                     serving_label=elabel or None, archived=0 if restore else food["archived"])
                    recompute_dependents(repo, fid)
                except ValueError as exc:
                    st.error(str(exc))
                else:
                    st.success("Alimento actualizado. Tus registros pasados conservan los valores con los que "
                               "los capturaste; las recetas que lo usan se recalcularon.")
                    _check_kcal(ekcal, eprot, ecarb, efat)
            if delete:
                outcome = repo.delete_food(fid)
                st.toast("Archivado: ya aparece en tu registro o en una receta, así que se conserva oculto."
                         if outcome == "archived" else "Alimento eliminado")
                st.rerun()
