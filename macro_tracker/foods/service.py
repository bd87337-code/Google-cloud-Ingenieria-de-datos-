"""Búsqueda de alimentos: primero la tabla local; si no hay resultados, Open Food Facts.

Todo lo que se encuentra en OFF se guarda en la tabla local (caché), así la
segunda búsqueda no necesita red.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from macro_tracker.db.repository import Repository
from macro_tracker.foods import off_client


@dataclass
class SearchResult:
    foods: list[dict]
    origin: str                 # 'local' | 'off' | 'none'
    off_error: str | None = None
    off_skipped: int = 0        # productos de OFF descartados por datos incompletos
    notes: list[str] = field(default_factory=list)


def cache_off_products(repo: Repository, products: list[off_client.OffProduct]) -> list[dict]:
    ids = [
        repo.upsert_off_food(
            barcode=p.barcode, name=p.name, brand=p.brand, macros=p.macros,
            serving_g=p.serving_g, serving_label=p.serving_label, data_flag=p.data_flag,
        )
        for p in products
    ]
    return [f for f in (repo.get_food(i) for i in ids) if f is not None]


def search_off(repo: Repository, query: str, *, mexico_only: bool = False, session=None) -> SearchResult:
    """Consulta OFF explícitamente y cachea el resultado. Nunca lanza por fallas de red."""
    try:
        products, skipped = off_client.search(query, mexico_only=mexico_only, session=session)
    except off_client.OffError as exc:
        return SearchResult([], "none", off_error=str(exc))
    foods = cache_off_products(repo, products)
    return SearchResult(foods, "off" if foods else "none", off_skipped=skipped)


def search(repo: Repository, query: str, *, use_off: bool = True, mexico_only: bool = False,
           session=None) -> SearchResult:
    """Local primero; solo si no hay nada local se consulta OFF."""
    local = repo.search_foods(query)
    if local:
        return SearchResult(local, "local")
    if not use_off or not query.strip():
        return SearchResult([], "none")
    return search_off(repo, query, mexico_only=mexico_only, session=session)


def lookup_barcode(repo: Repository, barcode: str, *, session=None) -> SearchResult:
    barcode = barcode.strip()
    cached = repo.get_food_by_barcode(barcode)
    if cached:
        return SearchResult([cached], "local")
    try:
        product = off_client.get_by_barcode(barcode, session=session)
    except off_client.OffError as exc:
        return SearchResult([], "none", off_error=str(exc))
    if product is None:
        return SearchResult([], "none", notes=["Código no encontrado o con datos incompletos en OFF."])
    return SearchResult(cache_off_products(repo, [product]), "off")
