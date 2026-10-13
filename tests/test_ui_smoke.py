"""Pruebas de humo de la interfaz con el framework de pruebas de Streamlit."""
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pytest
from streamlit.testing.v1 import AppTest

from macro_tracker.db.connection import connect
from macro_tracker.db.repository import Repository

ROOT = Path(__file__).resolve().parent.parent
PAGES = {
    "today": "macro_tracker/ui/pages/today.py",
    "progress": "macro_tracker/ui/pages/progress.py",
    "foods": "macro_tracker/ui/pages/foods.py",
    "goals": "macro_tracker/ui/pages/goals.py",
    "data": "macro_tracker/ui/pages/data.py",
}


@pytest.fixture
def db(tmp_path, monkeypatch):
    path = tmp_path / "ui.db"
    monkeypatch.setenv("MACRO_TRACKER_DB", str(path))
    return path


def run_page(name, timeout=30):
    at = AppTest.from_file(str(ROOT / PAGES[name]), default_timeout=timeout)
    at.run()
    return at


def seed(path, days=35):
    repo = Repository(connect(path))
    repo.save_profile(sex="M", birth_date="1998-04-10", height_cm=178, activity_level="moderate",
                      goal="lose", rate_kg_week=0.4)
    arroz = repo.add_food("Arroz cocido", 130, 2.7, 28, 0.3, serving_g=150, serving_label="1 taza")
    pollo = repo.add_food("Pechuga de pollo", 165, 31, 0, 3.6)
    rng = np.random.default_rng(1)
    start = date.today() - timedelta(days=days)
    for i in range(days):
        d = start + timedelta(days=i)
        if i % 5 != 4:                                     # algunos días sin pesar
            repo.upsert_body(d, weight_kg=round(82 - 0.04 * i + rng.normal(0, 0.3), 1),
                             **({"body_fat_pct": 19.0, "body_fat_source": "self_estimate"} if i % 14 == 0 else {}))
        if i % 7 != 6:                                     # algunos días sin comida
            repo.add_log(d, "lunch", arroz, 250)
            repo.add_log(d, "dinner", pollo, 300)
            repo.add_log(d, "snack", arroz, 400)
    repo.set_target(start, 2300, 160, 250, 70, "formula", "katch_mcardle")
    return repo


@pytest.mark.parametrize("page", list(PAGES))
def test_every_page_renders_with_empty_database(db, page):
    at = run_page(page)
    assert not at.exception, [e.value for e in at.exception]


@pytest.mark.parametrize("page", list(PAGES))
def test_every_page_renders_with_data(db, page):
    seed(db)
    at = run_page(page)
    assert not at.exception, [e.value for e in at.exception]


def test_goals_shows_method_in_use_and_withholds_number_without_data(db):
    seed(db, days=6)         # muy pocos días
    at = run_page("goals")
    assert not at.exception, [e.value for e in at.exception]
    text = " ".join(str(el.value) for el in [*at.info, *at.warning, *at.markdown])
    assert "Katch-McArdle" in text                                              # indica qué método usa
    data_metric = next(m for m in at.metric if m.label == "Gasto por datos")
    assert data_metric.value == "Sin datos suficientes"                         # sin número con falsa precisión
    assert "Días con comida registrada" in text                                 # y dice qué falta


def test_goals_with_enough_data_shows_estimate_and_interval(db):
    seed(db, days=35)
    at = run_page("goals")
    assert not at.exception
    labels = {m.label: m.value for m in at.metric}
    assert labels["Gasto por datos"] != "Sin datos suficientes"
    assert "kcal" in labels["Gasto por datos"]
    deltas = [m.delta for m in at.metric if m.label == "Gasto por datos"]
    assert deltas and "IC 95" in deltas[0]


def test_goals_profile_form_creates_profile_and_weight(db):
    at = run_page("goals")
    at.number_input[0].set_value(175.0)             # estatura
    # pesos del formulario: el primer number_input vacío con placeholder es el peso
    weight_input = next(n for n in at.number_input if n.label == "Peso (kg)")
    weight_input.set_value(80.0)
    at.button[0].click()
    at.run()
    assert not at.exception, [e.value for e in at.exception]
    repo = Repository(connect(db))
    assert repo.get_profile()["height_cm"] == 175.0
    assert repo.body_df()["weight_kg"].iloc[-1] == 80.0


def test_data_page_import_roundtrip_via_function_not_widget(db):
    # El cargador de archivos no es controlable en AppTest; la lógica de importación ya se prueba en test_io_csv.
    at = run_page("data")
    assert any("Descargar" in str(getattr(b, "label", "")) for b in at.get("download_button"))


def test_goals_does_not_claim_confirmation_when_confidence_is_low(db):
    seed(db, days=35)
    at = run_page("goals")
    assert not at.exception
    text = " ".join(str(el.value) for el in [*at.success, *at.info, *at.warning])
    data_delta = next(m.delta for m in at.metric if m.label == "Gasto por datos")
    if "confianza baja" in data_delta or "confianza media" in data_delta:
        assert "es coherente con tu gasto real" not in text     # sin el aval verde si la confianza no es alta


def _button(at, label):
    return next(b for b in at.button if b.label == label)


def test_create_custom_food_then_build_recipe_and_log_it(db):
    repo = Repository(connect(db))
    repo.save_profile(sex="M", birth_date="1998-04-10", height_cm=178, activity_level="moderate",
                      goal="maintain", rate_kg_week=0)
    repo.upsert_body(date.today(), weight_kg=80)
    repo.set_target(date.today() - timedelta(days=1), 2400, 150, 280, 70, "formula")

    # 1) crear dos alimentos propios desde el formulario
    for name, kcal, p, c, f in (("Tortilla de maíz casera", 218, 5.7, 44.6, 2.8), ("Queso Oaxaca", 300, 22, 2, 23)):
        at = run_page("foods")
        labels = {}
        for n in at.number_input:                   # el formulario de editar repite etiquetas: gana el primero (crear)
            labels.setdefault(n.label, n)
        at.text_input[0].set_value(name)
        labels["kcal / 100 g"].set_value(kcal)
        labels["Proteína (g)"].set_value(p)
        labels["Carbohidratos (g)"].set_value(c)
        labels["Grasa (g)"].set_value(f)
        at.button[0].click()
        at.run()
        assert not at.exception, [e.value for e in at.exception]
    assert {f["name"] for f in repo.list_foods()} == {"Tortilla de maíz casera", "Queso Oaxaca"}

    # 2) receta: buscar ingredientes por texto (sin acentos), agregarlos y guardar
    at = run_page("foods")
    for query, grams in (("tortilla", 90), ("oaxaca", 40)):
        at.text_input(key="ing_query").set_value(query).run()
        next(n for n in at.number_input if n.label == "Gramos (crudo)").set_value(grams)
        _button(at, "Agregar ingrediente").click()
        at.run()
        assert not at.exception, [e.value for e in at.exception]
    next(i for i in at.text_input if i.label == "Nombre de la receta").set_value("Quesadilla")
    at.run()
    next(n for n in at.number_input if n.label == "Porciones que rinde").set_value(2)
    _button(at, "Guardar receta").click()
    at.run()
    assert not at.exception, [e.value for e in at.exception]
    recipes = repo.list_foods(source="recipe")
    assert [r["name"] for r in recipes] == ["Quesadilla"]
    expected_kcal = (218 * 0.9 + 300 * 0.4) / 130 * 100       # rendimiento = suma de crudos (130 g)
    assert recipes[0]["kcal_100g"] == pytest.approx(expected_kcal)
    assert recipes[0]["serving_g"] == pytest.approx(65)

    # 3) la receta se puede registrar y aparece en el resumen de «Hoy»
    repo.add_log(date.today(), "lunch", recipes[0]["id"], 130)
    at = run_page("today")
    assert not at.exception, [e.value for e in at.exception]
    kcal_metric = next(m for m in at.metric if m.label == "Calorías")
    assert kcal_metric.value.replace(",", "").startswith(str(round(expected_kcal * 1.3)))
