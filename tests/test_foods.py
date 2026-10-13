import json
from pathlib import Path

import pytest
import requests

from macro_tracker.calc.nutrition import Macros, kcal_mismatch
from macro_tracker.foods import off_client, service
from macro_tracker.foods.recipes import recipe_per_100g, save_recipe

FIXTURES = Path(__file__).parent / "fixtures"


def load(name):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


class FakeResponse:
    def __init__(self, payload=None, status=200, bad_json=False):
        self.payload, self.status, self.bad_json = payload, status, bad_json

    def raise_for_status(self):
        if self.status >= 400:
            raise requests.HTTPError(f"HTTP {self.status}")

    def json(self):
        if self.bad_json:
            raise ValueError("not json")
        return self.payload


class FakeSession:
    def __init__(self, response=None, error=None):
        self.response, self.error, self.calls = response, error, []

    def get(self, url, params=None, headers=None, timeout=None):
        self.calls.append({"url": url, "params": params, "headers": headers, "timeout": timeout})
        if self.error:
            raise self.error
        return self.response


# ---------------------------------------------------------------- parseo de OFF
def test_parse_real_products_from_fixture():
    raw = load("off_search_tortilla.json")["products"]
    parsed = [off_client.parse_product(p) for p in raw]
    good = [p for p in parsed if p]
    assert len(good) >= 8 and len(good) < len(raw) + 1
    takis = next(p for p in good if "Takis" in p.name)
    assert takis.barcode and takis.macros.kcal > 400 and takis.brand == "Barcel"


def test_parse_product_converts_kj_when_kcal_missing():
    p = off_client.parse_product({
        "code": "1", "product_name": "X",
        "nutriments": {"energy-kj_100g": 418.4, "proteins_100g": 10, "carbohydrates_100g": 10, "fat_100g": 2},
    })
    assert p.macros.kcal == pytest.approx(100.0)


def test_parse_product_discards_incomplete_or_impossible():
    ok = {"proteins_100g": 1, "carbohydrates_100g": 1, "fat_100g": 1, "energy-kcal_100g": 17}
    assert off_client.parse_product({"code": "1", "product_name": "A", "nutriments": ok}) is not None
    assert off_client.parse_product({"code": "", "product_name": "A", "nutriments": ok}) is None
    assert off_client.parse_product({"code": "1", "product_name": "", "nutriments": ok}) is None
    no_fat = {k: v for k, v in ok.items() if k != "fat_100g"}
    assert off_client.parse_product({"code": "1", "product_name": "A", "nutriments": no_fat}) is None
    impossible = {**ok, "proteins_100g": 70, "carbohydrates_100g": 70}
    assert off_client.parse_product({"code": "1", "product_name": "A", "nutriments": impossible}) is None
    assert off_client.parse_product({"code": "1", "product_name": "A", "nutriments": {**ok, "energy-kcal_100g": "n/a"}}) is None


def test_parse_product_flags_kcal_inconsistency_but_keeps_it():
    # 4*10 + 4*10 + 9*2 = 98 kcal esperadas; declara 300
    p = off_client.parse_product({
        "code": "1", "product_name": "Dudoso",
        "nutriments": {"energy-kcal_100g": 300, "proteins_100g": 10, "carbohydrates_100g": 10, "fat_100g": 2},
    })
    assert p.data_flag == off_client.FLAG_KCAL_MISMATCH


def test_kcal_mismatch_tolerates_fiber_sized_gaps():
    assert not kcal_mismatch(200, 5, 40, 2.8)       # 203 esperadas
    assert not kcal_mismatch(0, 0, 0.1, 0)           # agua / sal: dentro de la tolerancia absoluta
    assert kcal_mismatch(500, 5, 40, 2.8)


def test_search_sends_user_agent_and_mexico_filter():
    sess = FakeSession(FakeResponse({"products": []}))
    off_client.search("tortilla", mexico_only=True, session=sess)
    call = sess.calls[0]
    assert "MacroTracker" in call["headers"]["User-Agent"]
    assert call["params"]["tag_0"] == "mexico" and call["params"]["search_terms"] == "tortilla"
    assert call["timeout"] > 0


@pytest.mark.parametrize(
    "session",
    [
        FakeSession(error=requests.ConnectionError("sin red")),
        FakeSession(error=requests.Timeout("lento")),
        FakeSession(FakeResponse(status=503)),
        FakeSession(FakeResponse(bad_json=True)),
    ],
)
def test_network_failures_become_offerror(session):
    with pytest.raises(off_client.OffError):
        off_client.search("x", session=session)


def test_get_by_barcode_found_and_not_found():
    found = FakeSession(FakeResponse(load("off_product_nutella.json")))
    p = off_client.get_by_barcode("3017620422003", session=found)
    assert p.macros.kcal == 539 and "Nutella" in (p.brand or "") + p.name
    missing = FakeSession(FakeResponse({"status": 0, "status_verbose": "product not found"}))
    assert off_client.get_by_barcode("0", session=missing) is None


# ------------------------------------------------------------- servicio / caché
def test_search_prefers_local_and_does_not_hit_network(repo):
    repo.add_food("Tortilla de maíz casera", 218, 5.7, 44.6, 2.8)
    sess = FakeSession(FakeResponse({"products": []}))
    res = service.search(repo, "tortilla", session=sess)
    assert res.origin == "local" and len(res.foods) == 1
    assert sess.calls == []


def test_search_falls_back_to_off_and_caches(repo):
    sess = FakeSession(FakeResponse(load("off_search_tortilla.json")))
    res = service.search(repo, "tortilla de maiz", session=sess)
    assert res.origin == "off" and res.foods and len(sess.calls) == 1
    assert all(f["source"] == "off" and f["barcode"] for f in res.foods)
    # segunda búsqueda: sale de la caché local, sin red
    sess2 = FakeSession(error=requests.ConnectionError("sin red"))
    res2 = service.search(repo, "tortilla", session=sess2)
    assert res2.origin == "local" and sess2.calls == []


def test_off_failure_returns_message_not_exception(repo):
    res = service.search(repo, "algo raro", session=FakeSession(error=requests.ConnectionError("sin red")))
    assert res.foods == [] and res.origin == "none" and "sin red" in res.off_error


def test_search_without_off_flag_never_calls_network(repo):
    sess = FakeSession(FakeResponse({"products": []}))
    assert service.search(repo, "nada", use_off=False, session=sess).origin == "none"
    assert sess.calls == []


def test_recaching_does_not_duplicate_or_overwrite_user_edits(repo):
    payload = load("off_search_tortilla.json")
    service.search_off(repo, "tortilla", session=FakeSession(FakeResponse(payload)))
    n = len(repo.list_foods())
    first = repo.list_foods()[0]
    repo.update_food(first["id"], kcal_100g=first["kcal_100g"] + 10)   # el usuario lo corrige
    corrected = repo.get_food(first["id"])["kcal_100g"]
    service.search_off(repo, "tortilla", session=FakeSession(FakeResponse(payload)))
    assert len(repo.list_foods()) == n
    assert repo.get_food(first["id"])["kcal_100g"] == corrected


def test_lookup_barcode_uses_cache_then_network(repo):
    sess = FakeSession(FakeResponse(load("off_product_nutella.json")))
    r1 = service.lookup_barcode(repo, "3017620422003", session=sess)
    assert r1.origin == "off" and len(sess.calls) == 1
    r2 = service.lookup_barcode(repo, "3017620422003", session=sess)
    assert r2.origin == "local" and len(sess.calls) == 1


# ------------------------------------------------------------------- recetas
def test_recipe_per_100g_hand_computed():
    # 200 g de A (100 kcal/100g) + 100 g de B (300 kcal/100g) = 500 kcal; rendimiento 250 g
    a = Macros(100, 10, 10, 1)
    b = Macros(300, 5, 20, 20)
    out = recipe_per_100g([(a, 200), (b, 100)], total_yield_g=250)
    assert out.kcal == pytest.approx(500 / 250 * 100)
    assert out.protein_g == pytest.approx((20 + 5) / 250 * 100)
    assert out.fat_g == pytest.approx((2 + 20) / 250 * 100)


def test_recipe_cooked_yield_concentrates_macros():
    a = Macros(100, 10, 10, 1)
    raw = recipe_per_100g([(a, 200)], total_yield_g=200)
    cooked = recipe_per_100g([(a, 200)], total_yield_g=100)  # pierde la mitad del peso
    assert cooked.kcal == pytest.approx(raw.kcal * 2)


def test_recipe_rejects_empty_or_zero_yield():
    with pytest.raises(ValueError):
        recipe_per_100g([], 100)
    with pytest.raises(ValueError):
        recipe_per_100g([(Macros(1, 0, 0, 0), 10)], 0)


def test_save_recipe_creates_logable_food(repo):
    arroz = repo.add_food("Arroz cocido", 130, 2.7, 28, 0.3)
    pollo = repo.add_food("Pollo cocido", 165, 31, 0, 3.6)
    rid = save_recipe(repo, "Arroz con pollo", [(arroz, 200), (pollo, 150)], total_yield_g=350, servings=2)
    food = repo.get_food(rid)
    assert food["source"] == "recipe" and food["serving_g"] == pytest.approx(175)
    expected_kcal = (130 * 2 + 165 * 1.5) / 350 * 100
    assert food["kcal_100g"] == pytest.approx(expected_kcal)
    lid = repo.add_log("2026-03-01", "lunch", rid, 175)   # una porción
    assert lid and repo.log_for_date("2026-03-01").iloc[0]["kcal"] == pytest.approx(expected_kcal * 1.75)


def test_editing_ingredient_recomputes_recipe_but_not_history(repo):
    from macro_tracker.foods.recipes import recompute_dependents
    arroz = repo.add_food("Arroz cocido", 100, 2, 20, 0.5)
    rid = save_recipe(repo, "Plato", [(arroz, 100)])
    repo.add_log("2026-03-01", "lunch", rid, 100)
    before = repo.log_for_date("2026-03-01").iloc[0]["kcal"]
    repo.update_food(arroz, kcal_100g=150, carbs_100g=33)
    recompute_dependents(repo, arroz)
    assert repo.get_food(rid)["kcal_100g"] == pytest.approx(150)
    assert repo.log_for_date("2026-03-01").iloc[0]["kcal"] == before


def test_recipe_can_use_another_recipe_but_not_create_a_cycle(repo):
    a = repo.add_food("Tortilla", 218, 5.7, 44.6, 2.8)
    salsa = save_recipe(repo, "Salsa", [(a, 10)])
    plato = save_recipe(repo, "Plato con salsa", [(a, 100), (salsa, 50)])
    assert repo.get_recipe(plato)["items"]
    with pytest.raises(ValueError):   # salsa no puede contener a plato (que ya contiene a salsa)
        save_recipe(repo, "Salsa", [(plato, 10)], recipe_id=salsa)


def test_recipe_validations(repo):
    a = repo.add_food("A", 100, 1, 1, 1)
    with pytest.raises(ValueError):
        save_recipe(repo, "Vacía", [])
    with pytest.raises(ValueError):
        save_recipe(repo, "Negativa", [(a, -5)])
    with pytest.raises(KeyError):
        save_recipe(repo, "Fantasma", [(999, 5)])
