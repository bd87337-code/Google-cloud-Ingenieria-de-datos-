"""Recetas: un alimento compuesto cuyas macros por 100 g salen de sus ingredientes."""
from __future__ import annotations

from macro_tracker.calc.nutrition import ZERO, Macros, macros_for_grams
from macro_tracker.db.repository import Repository


def recipe_per_100g(ingredients: list[tuple[Macros, float]], total_yield_g: float) -> Macros:
    """Macros por 100 g del platillo terminado.

    `ingredients`: (macros por 100 g, gramos crudos usados) de cada ingrediente.
    `total_yield_g`: peso final del platillo (cocido); puede ser menor que la suma
    de los crudos por la pérdida de agua, lo que concentra las macros por 100 g.
    """
    if total_yield_g <= 0:
        raise ValueError("el rendimiento total debe ser positivo")
    if not ingredients:
        raise ValueError("la receta necesita al menos un ingrediente")
    total = ZERO
    for per_100g, grams in ingredients:
        total = total + macros_for_grams(per_100g, grams)
    return total.scaled(100.0 / total_yield_g)


def _per_100g_of(food: dict) -> Macros:
    return Macros(food["kcal_100g"], food["protein_100g"], food["carbs_100g"], food["fat_100g"])


def _depends_on(repo: Repository, root_id: int, target_id: int, seen: set[int] | None = None) -> bool:
    """¿La receta `root_id` contiene (directa o indirectamente) a `target_id`?"""
    seen = seen or set()
    if root_id in seen:
        return False
    seen.add(root_id)
    recipe = repo.get_recipe(root_id)
    if not recipe:
        return False
    for item in recipe["items"]:
        ing = item["ingredient_food_id"]
        if ing == target_id or _depends_on(repo, ing, target_id, seen):
            return True
    return False


def save_recipe(
    repo: Repository,
    name: str,
    items: list[tuple[int, float]],
    *,
    total_yield_g: float | None = None,
    servings: float = 1.0,
    recipe_id: int | None = None,
) -> int:
    """Crea o actualiza una receta y su ficha de alimento (source = 'recipe').

    `items`: (id del alimento ingrediente, gramos). Si no se indica rendimiento se
    usa la suma de gramos crudos. Devuelve el id del alimento-receta.
    """
    if not items:
        raise ValueError("la receta necesita al menos un ingrediente")
    ingredient_foods = []
    for ing_id, grams in items:
        food = repo.get_food(ing_id)
        if food is None:
            raise KeyError(f"ingrediente {ing_id} no existe")
        if grams <= 0:
            raise ValueError("los gramos de cada ingrediente deben ser positivos")
        if recipe_id is not None and (ing_id == recipe_id or _depends_on(repo, ing_id, recipe_id)):
            raise ValueError(f"'{food['name']}' contiene a esta receta: sería una dependencia circular")
        ingredient_foods.append(food)

    raw_total = sum(g for _, g in items)
    yield_g = total_yield_g if total_yield_g else raw_total
    per_100 = recipe_per_100g([(_per_100g_of(f), g) for f, (_, g) in zip(ingredient_foods, items)], yield_g)
    serving_g = yield_g / servings

    fields = dict(
        kcal_100g=per_100.kcal, protein_100g=per_100.protein_g, carbs_100g=per_100.carbs_g,
        fat_100g=per_100.fat_g, serving_g=serving_g,
        serving_label=f"1 porción (~{serving_g:.0f} g)",
    )
    if recipe_id is None:
        recipe_id = repo.add_food(
            name, fields["kcal_100g"], fields["protein_100g"], fields["carbs_100g"],
            fields["fat_100g"], source="recipe", serving_g=serving_g,
            serving_label=fields["serving_label"],
        )
    else:
        repo.update_food(recipe_id, name=name, **fields)
    repo.set_recipe(recipe_id, yield_g, servings, items)
    recompute_dependents(repo, recipe_id)
    return recipe_id


def recompute_recipe(repo: Repository, recipe_id: int) -> None:
    recipe = repo.get_recipe(recipe_id)
    if recipe is None:
        return
    items = [(i["ingredient_food_id"], i["grams"]) for i in recipe["items"]]
    food = repo.get_food(recipe_id)
    save_recipe(repo, food["name"], items, total_yield_g=recipe["total_yield_g"],
                servings=recipe["servings"], recipe_id=recipe_id)


def recompute_dependents(repo: Repository, food_id: int, _seen: set[int] | None = None) -> None:
    """Recalcula las recetas que usan `food_id` (p. ej. tras editar un ingrediente).

    Los registros ya guardados en el diario no cambian: tienen su propio snapshot.
    """
    seen = _seen or set()
    for rid in repo.recipes_using(food_id):
        if rid in seen:
            continue
        seen.add(rid)
        recipe = repo.get_recipe(rid)
        items = [(i["ingredient_food_id"], i["grams"]) for i in recipe["items"]]
        food = repo.get_food(rid)
        per_100 = recipe_per_100g(
            [(_per_100g_of(repo.get_food(i)), g) for i, g in items], recipe["total_yield_g"]
        )
        serving_g = recipe["total_yield_g"] / recipe["servings"]
        repo.update_food(
            rid, name=food["name"], kcal_100g=per_100.kcal, protein_100g=per_100.protein_g,
            carbs_100g=per_100.carbs_g, fat_100g=per_100.fat_g, serving_g=serving_g,
            serving_label=f"1 porción (~{serving_g:.0f} g)",
        )
        recompute_dependents(repo, rid, seen)
