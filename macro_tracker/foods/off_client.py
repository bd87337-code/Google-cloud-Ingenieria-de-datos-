"""Cliente mínimo de Open Food Facts (sin cuenta ni clave).

Solo hace peticiones cuando el usuario busca algo que no está en la tabla local.
Los datos de OFF son colaborativos: se validan antes de usarse.
"""
from __future__ import annotations

from dataclasses import dataclass

import requests

from macro_tracker.calc.nutrition import Macros, kcal_mismatch, validate_per_100g
from macro_tracker.config import OFF_PRODUCT_URL, OFF_SEARCH_URL, OFF_TIMEOUT_S, OFF_USER_AGENT

KJ_PER_KCAL = 4.184
FLAG_KCAL_MISMATCH = "kcal_mismatch"


class OffError(RuntimeError):
    """No se pudo consultar Open Food Facts (sin red, tiempo agotado, respuesta inválida)."""


@dataclass(frozen=True)
class OffProduct:
    barcode: str
    name: str
    brand: str | None
    macros: Macros
    serving_g: float | None
    serving_label: str | None
    data_flag: str | None


def _num(value) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def parse_product(raw: dict) -> OffProduct | None:
    """Convierte un producto de OFF en una ficha por 100 g, o None si no es utilizable.

    Se descartan productos sin código, sin nombre, sin proteína/carbohidratos/grasa
    o con valores imposibles. Si las kcal no cuadran con 4P+4C+9F se conserva el
    producto pero marcado con `data_flag = 'kcal_mismatch'`.
    """
    code = str(raw.get("code") or "").strip()
    name = (raw.get("product_name_es") or raw.get("product_name") or raw.get("generic_name") or "").strip()
    if not code or not name:
        return None
    n = raw.get("nutriments") or {}
    kcal = _num(n.get("energy-kcal_100g"))
    if kcal is None:
        kj = _num(n.get("energy-kj_100g"))
        if kj is None:
            kj = _num(n.get("energy_100g"))
        kcal = kj / KJ_PER_KCAL if kj is not None else None
    protein, carbs, fat = (_num(n.get(k)) for k in ("proteins_100g", "carbohydrates_100g", "fat_100g"))
    if None in (kcal, protein, carbs, fat):
        return None
    macros = Macros(kcal, protein, carbs, fat)
    if validate_per_100g(macros):
        return None

    brand = (raw.get("brands") or "").split(",")[0].strip() or None
    serving_g = _num(raw.get("serving_quantity"))
    if serving_g is not None and serving_g <= 0:
        serving_g = None
    serving_label = (raw.get("serving_size") or "").strip() or None if serving_g else None
    flag = FLAG_KCAL_MISMATCH if kcal_mismatch(kcal, protein, carbs, fat) else None
    return OffProduct(code, name, brand, macros, serving_g, serving_label, flag)


def _get(url: str, params: dict | None, timeout: float, session: requests.Session | None) -> dict:
    http = session or requests
    try:
        resp = http.get(url, params=params, headers={"User-Agent": OFF_USER_AGENT}, timeout=timeout)
        resp.raise_for_status()
        return resp.json()
    except (requests.RequestException, ValueError) as exc:
        raise OffError(str(exc)) from exc


def search(
    query: str,
    *,
    page_size: int = 20,
    mexico_only: bool = False,
    timeout: float = OFF_TIMEOUT_S,
    session: requests.Session | None = None,
) -> tuple[list[OffProduct], int]:
    """Busca por texto. Devuelve (productos utilizables, cantidad descartada por datos incompletos)."""
    params = {
        "search_terms": query,
        "search_simple": 1,
        "action": "process",
        "json": 1,
        "page_size": page_size,
    }
    if mexico_only:
        params.update({"tagtype_0": "countries", "tag_contains_0": "contains", "tag_0": "mexico"})
    data = _get(OFF_SEARCH_URL, params, timeout, session)
    raw_products = data.get("products") or []
    parsed = [parse_product(p) for p in raw_products]
    products = [p for p in parsed if p is not None]
    return products, len(raw_products) - len(products)


def get_by_barcode(
    barcode: str,
    *,
    timeout: float = OFF_TIMEOUT_S,
    session: requests.Session | None = None,
) -> OffProduct | None:
    data = _get(OFF_PRODUCT_URL.format(barcode=barcode), None, timeout, session)
    if data.get("status") == 0 or not data.get("product"):
        return None
    return parse_product({**data["product"], "code": data["product"].get("code") or barcode})
