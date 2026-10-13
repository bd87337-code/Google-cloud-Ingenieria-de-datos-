"""Exportar e importar todos los datos como CSV.

- Exportación: un ZIP con un CSV por tabla (+ manifest.json), o un CSV suelto por tabla.
- Los alimentos y el diario se enlazan por `uid` (no por id autoincremental), así que
  se pueden combinar bases de dos computadoras sin colisiones.
- Importación: validada y atómica (todo o nada). Modos:
    * merge   – inserta lo nuevo y actualiza lo existente (gana lo importado).
    * replace – borra primero (ZIP: todas las tablas; CSV suelto: solo esa tabla).
- Los CSV usan UTF-8 con BOM (acentos correctos en Excel) y se leen con o sin BOM;
  se acepta coma decimal ("1,5") por si Excel regional reescribió el archivo.
"""
from __future__ import annotations

import csv
import io
import json
import re
import sqlite3
import zipfile
from dataclasses import dataclass, field
from datetime import date, datetime, timezone

from macro_tracker.config import BF_SOURCES, GOALS, MEALS, ACTIVITY_FACTORS
from macro_tracker.db.connection import LATEST_VERSION
from macro_tracker.db.repository import Repository
from macro_tracker.textutil import normalize_text

TABLES = ("profile", "body_log", "foods", "recipes", "recipe_items", "food_log", "day_status", "targets")
MAX_ERRORS_SHOWN = 15

EXPORT_QUERIES = {
    "profile": (
        ["sex", "birth_date", "height_cm", "activity_level", "goal", "rate_kg_week", "protein_g_kg_min",
         "protein_g_kg_max", "fat_g_kg_min", "fat_pct_kcal", "bmr_method_pref", "min_valid_day_kcal",
         "updated_at"],
        "SELECT {cols} FROM profile",
    ),
    "body_log": (
        ["date", "weight_kg", "body_fat_pct", "body_fat_source", "waist_cm", "neck_cm", "hip_cm", "note"],
        "SELECT {cols} FROM body_log ORDER BY date",
    ),
    "foods": (
        ["uid", "name", "brand", "source", "barcode", "kcal_100g", "protein_100g", "carbs_100g", "fat_100g",
         "serving_g", "serving_label", "data_flag", "archived", "off_fetched_at", "created_at"],
        "SELECT {cols} FROM foods ORDER BY id",
    ),
    "recipes": (
        ["food_uid", "total_yield_g", "servings"],
        "SELECT f.uid AS food_uid, r.total_yield_g, r.servings FROM recipes r JOIN foods f ON f.id = r.food_id "
        "ORDER BY f.id",
    ),
    "recipe_items": (
        ["recipe_uid", "ingredient_uid", "grams"],
        "SELECT rf.uid AS recipe_uid, inf.uid AS ingredient_uid, ri.grams FROM recipe_items ri "
        "JOIN foods rf ON rf.id = ri.recipe_food_id JOIN foods inf ON inf.id = ri.ingredient_food_id "
        "ORDER BY ri.id",
    ),
    "food_log": (
        ["uid", "date", "meal", "food_uid", "grams", "kcal", "protein_g", "carbs_g", "fat_g", "created_at"],
        "SELECT l.uid, l.date, l.meal, f.uid AS food_uid, l.grams, l.kcal, l.protein_g, l.carbs_g, l.fat_g, "
        "l.created_at FROM food_log l JOIN foods f ON f.id = l.food_id ORDER BY l.date, l.id",
    ),
    "day_status": (
        ["date", "food_complete"],
        "SELECT {cols} FROM day_status ORDER BY date",
    ),
    "targets": (
        ["effective_from", "kcal", "protein_g", "carbs_g", "fat_g", "tdee_source", "bmr_method", "note"],
        "SELECT {cols} FROM targets ORDER BY effective_from",
    ),
}


class ImportErrors(ValueError):
    """La importación se canceló; `errors` lista los problemas (con tabla y número de fila)."""

    def __init__(self, errors: list[str]):
        self.errors = errors
        shown = errors[:MAX_ERRORS_SHOWN]
        extra = f"\n… y {len(errors) - len(shown)} más" if len(errors) > len(shown) else ""
        super().__init__("Importación cancelada, no se guardó nada:\n- " + "\n- ".join(shown) + extra)


@dataclass
class ImportReport:
    mode: str
    counts: dict[str, int] = field(default_factory=dict)


# --------------------------------------------------------------------- exportar
def _fmt(value) -> str:
    if value is None:
        return ""
    if isinstance(value, float):
        return repr(value)
    return str(value)


def export_table_csv(repo: Repository, table: str) -> bytes:
    """CSV (UTF-8 con BOM) de una tabla."""
    if table not in EXPORT_QUERIES:
        raise ValueError(f"tabla desconocida: {table}")
    columns, sql = EXPORT_QUERIES[table]
    rows = repo.conn.execute(sql.format(cols=", ".join(columns))).fetchall()
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(columns)
    for row in rows:
        writer.writerow([_fmt(row[c]) for c in columns])
    return buf.getvalue().encode("utf-8-sig")


def export_zip(repo: Repository) -> bytes:
    manifest = {
        "app": "macro_tracker",
        "schema_version": LATEST_VERSION,
        "exported_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "tables": list(TABLES),
    }
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("manifest.json", json.dumps(manifest, indent=2))
        for table in TABLES:
            zf.writestr(f"{table}.csv", export_table_csv(repo, table))
    return buf.getvalue()


# --------------------------------------------------------------------- importar
_DECIMAL_COMMA = re.compile(r"^-?\d+,\d+$")


def _read_rows(data: bytes) -> tuple[list[str], list[dict[str, str]]]:
    try:
        text = data.decode("utf-8-sig")
        reader = csv.DictReader(io.StringIO(text))
        rows = list(reader)
    except (UnicodeDecodeError, csv.Error) as exc:
        raise ImportErrors([f"no se pudo leer el CSV (¿está en UTF-8?): {exc}"]) from exc
    return list(reader.fieldnames or []), rows


class _Row:
    """Acceso tipado a una fila CSV que acumula errores en vez de lanzar."""

    def __init__(self, table: str, number: int, raw: dict[str, str], errors: list[str]):
        self.table, self.number, self.raw, self.errors = table, number, raw, errors
        self.ok = True

    def _fail(self, column: str, message: str) -> None:
        self.ok = False
        self.errors.append(f"{self.table}.csv fila {self.number}, columna '{column}': {message}")

    def text(self, column: str, required: bool = False) -> str | None:
        value = (self.raw.get(column) or "").strip()
        if not value:
            if required:
                self._fail(column, "es obligatoria")
            return None
        return value

    def number_(self, column: str, required: bool = False, minimum: float | None = None,
                maximum: float | None = None, exclusive_min: bool = False) -> float | None:
        value = self.text(column, required)
        if value is None:
            return None
        if _DECIMAL_COMMA.match(value):
            value = value.replace(",", ".")
        try:
            number = float(value)
        except ValueError:
            self._fail(column, f"'{value}' no es un número")
            return None
        if number != number or number in (float("inf"), float("-inf")):
            self._fail(column, "valor no finito")
            return None
        if minimum is not None and (number < minimum or (exclusive_min and number == minimum)):
            self._fail(column, f"{number} debe ser {'>' if exclusive_min else '≥'} {minimum}")
            return None
        if maximum is not None and number > maximum:
            self._fail(column, f"{number} debe ser ≤ {maximum}")
            return None
        return number

    def day(self, column: str, required: bool = True) -> str | None:
        value = self.text(column, required)
        if value is None:
            return None
        try:
            return date.fromisoformat(value).isoformat()
        except ValueError:
            self._fail(column, f"'{value}' no es una fecha AAAA-MM-DD")
            return None

    def choice(self, column: str, options, required: bool = True) -> str | None:
        value = self.text(column, required)
        if value is None:
            return None
        if value not in options:
            self._fail(column, f"'{value}' no es válido (opciones: {', '.join(options)})")
            return None
        return value


def _require_columns(table: str, present: list[str], needed: list[str], errors: list[str]) -> bool:
    missing = [c for c in needed if c not in present]
    if missing:
        errors.append(f"{table}.csv: faltan columnas {missing}")
        return False
    return True


def _rows(table: str, data: bytes, required_cols: list[str], errors: list[str]):
    fieldnames, raw_rows = _read_rows(data)
    if not _require_columns(table, fieldnames, required_cols, errors):
        return []
    return [_Row(table, i, r, errors) for i, r in enumerate(raw_rows, start=2)]


def import_tables(repo: Repository, files: dict[str, bytes], mode: str = "merge") -> ImportReport:
    """Importa `files` ({tabla: contenido CSV}) en una sola transacción."""
    if mode not in ("merge", "replace"):
        raise ValueError("modo debe ser 'merge' o 'replace'")
    unknown = set(files) - set(TABLES)
    if unknown:
        raise ValueError(f"tablas desconocidas: {sorted(unknown)}")
    if not files:
        raise ValueError("no hay archivos para importar")

    conn = repo.conn
    errors: list[str] = []
    report = ImportReport(mode)
    conn.execute("SAVEPOINT import_csv")
    try:
        if mode == "replace":
            _wipe(conn, files)
        uid_to_id: dict[str, int] = {}

        if "profile" in files:
            report.counts["profile"] = _import_profile(conn, files["profile"], errors)
        if "body_log" in files:
            report.counts["body_log"] = _import_body(conn, files["body_log"], errors)
        if "foods" in files:
            report.counts["foods"] = _import_foods(conn, files["foods"], errors, uid_to_id)
        if "recipes" in files:
            report.counts["recipes"] = _import_recipes(conn, files["recipes"], errors, uid_to_id)
        if "recipe_items" in files:
            report.counts["recipe_items"] = _import_recipe_items(conn, files["recipe_items"], errors, uid_to_id)
        if "food_log" in files:
            report.counts["food_log"] = _import_food_log(conn, files["food_log"], errors, uid_to_id)
        if "day_status" in files:
            report.counts["day_status"] = _import_day_status(conn, files["day_status"], errors)
        if "targets" in files:
            report.counts["targets"] = _import_targets(conn, files["targets"], errors)

        if errors:
            raise ImportErrors(errors)
        conn.execute("RELEASE SAVEPOINT import_csv")
        conn.commit()
    except Exception as exc:
        conn.execute("ROLLBACK TO SAVEPOINT import_csv")
        conn.execute("RELEASE SAVEPOINT import_csv")
        if isinstance(exc, ImportErrors):
            raise
        if isinstance(exc, sqlite3.IntegrityError):
            raise ImportErrors([f"restricción de la base de datos: {exc}"]) from exc
        raise
    return report


def _wipe(conn, files: dict[str, bytes]) -> None:
    tables = ["food_log", "recipe_items", "recipes", "foods", "day_status", "targets", "body_log", "profile"]
    # Con un ZIP completo se borra todo; con CSV sueltos, solo las tablas importadas.
    full = set(files) == set(TABLES)
    for table in tables:
        if full or table in files:
            conn.execute(f"DELETE FROM {table}")


def import_zip(repo: Repository, data: bytes, mode: str = "merge") -> ImportReport:
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as exc:
        raise ImportErrors(["el archivo no es un ZIP válido"]) from exc
    names = {n.rsplit("/", 1)[-1]: n for n in zf.namelist()}
    if "manifest.json" in names:
        manifest = json.loads(zf.read(names["manifest.json"]))
        if int(manifest.get("schema_version", 0)) > LATEST_VERSION:
            raise ImportErrors(["el respaldo viene de una versión más nueva de la app"])
    files = {t: zf.read(names[f"{t}.csv"]) for t in TABLES if f"{t}.csv" in names}
    if not files:
        raise ImportErrors(["el ZIP no contiene ningún CSV reconocido"])
    return import_tables(repo, files, mode)


def import_csv(repo: Repository, table: str, data: bytes, mode: str = "merge") -> ImportReport:
    return import_tables(repo, {table: data}, mode)


# ---- tablas individuales ---------------------------------------------------------
def _import_profile(conn, data, errors) -> int:
    n = 0
    for r in _rows("profile", data, ["sex", "birth_date", "height_cm", "activity_level", "goal"], errors):
        vals = (
            r.choice("sex", ("M", "F")), r.day("birth_date"),
            r.number_("height_cm", True, 0, 260, exclusive_min=True),
            r.choice("activity_level", tuple(ACTIVITY_FACTORS)), r.choice("goal", GOALS),
            r.number_("rate_kg_week", minimum=0) or 0.0,
            r.number_("protein_g_kg_min", minimum=0, exclusive_min=True) or 1.6,
            r.number_("protein_g_kg_max", minimum=0, exclusive_min=True) or 2.2,
            r.number_("fat_g_kg_min", minimum=0) if r.text("fat_g_kg_min") else 0.6,
            r.number_("fat_pct_kcal", minimum=0, maximum=0.99) if r.text("fat_pct_kcal") else 0.25,
            r.choice("bmr_method_pref", ("auto", "mifflin"), required=False) or "auto",
            r.number_("min_valid_day_kcal", minimum=0) if r.text("min_valid_day_kcal") else 1000.0,
            r.text("updated_at") or datetime.now(timezone.utc).isoformat(timespec="seconds"),
        )
        if r.ok and vals[7] < vals[6]:
            r._fail("protein_g_kg_max", "debe ser ≥ protein_g_kg_min")
        if not r.ok:
            continue
        conn.execute(
            """
            INSERT INTO profile (id, sex, birth_date, height_cm, activity_level, goal, rate_kg_week,
                protein_g_kg_min, protein_g_kg_max, fat_g_kg_min, fat_pct_kcal, bmr_method_pref,
                min_valid_day_kcal, updated_at)
            VALUES (1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET sex = excluded.sex, birth_date = excluded.birth_date,
                height_cm = excluded.height_cm, activity_level = excluded.activity_level,
                goal = excluded.goal, rate_kg_week = excluded.rate_kg_week,
                protein_g_kg_min = excluded.protein_g_kg_min, protein_g_kg_max = excluded.protein_g_kg_max,
                fat_g_kg_min = excluded.fat_g_kg_min, fat_pct_kcal = excluded.fat_pct_kcal,
                bmr_method_pref = excluded.bmr_method_pref,
                min_valid_day_kcal = excluded.min_valid_day_kcal, updated_at = excluded.updated_at
            """,
            vals,
        )
        n += 1
        break  # el perfil es una sola fila
    return n


def _import_body(conn, data, errors) -> int:
    n = 0
    for r in _rows("body_log", data, ["date"], errors):
        day = r.day("date")
        weight = r.number_("weight_kg", minimum=0, exclusive_min=True, maximum=500)
        bf = r.number_("body_fat_pct", minimum=3, maximum=60)
        source = r.choice("body_fat_source", BF_SOURCES, required=False)
        waist, neck, hip = (r.number_(c, minimum=0, exclusive_min=True, maximum=300)
                            for c in ("waist_cm", "neck_cm", "hip_cm"))
        if bf is not None and source is None and r.ok:
            r._fail("body_fat_source", "es obligatoria cuando hay body_fat_pct")
        if not r.ok:
            continue
        conn.execute(
            """
            INSERT INTO body_log (date, weight_kg, body_fat_pct, body_fat_source, waist_cm, neck_cm, hip_cm, note)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(date) DO UPDATE SET weight_kg = excluded.weight_kg, body_fat_pct = excluded.body_fat_pct,
                body_fat_source = excluded.body_fat_source, waist_cm = excluded.waist_cm,
                neck_cm = excluded.neck_cm, hip_cm = excluded.hip_cm, note = excluded.note
            """,
            (day, weight, bf, source if bf is not None else None, waist, neck, hip, r.text("note")),
        )
        n += 1
    return n


def _import_foods(conn, data, errors, uid_to_id) -> int:
    n = 0
    needed = ["uid", "name", "kcal_100g", "protein_100g", "carbs_100g", "fat_100g"]
    for r in _rows("foods", data, needed, errors):
        uid = r.text("uid", True)
        name = r.text("name", True)
        brand = r.text("brand")
        source = r.choice("source", ("custom", "off", "recipe"), required=False) or "custom"
        barcode = r.text("barcode")
        kcal = r.number_("kcal_100g", True, 0, 900)
        p, c, f = (r.number_(col, True, 0, 100) for col in ("protein_100g", "carbs_100g", "fat_100g"))
        serving = r.number_("serving_g", minimum=0, exclusive_min=True)
        if r.ok and p + c + f > 100.5:
            r._fail("protein_100g", "proteína + carbohidratos + grasa suman más de 100 g por 100 g")
        if not r.ok:
            continue
        existing = conn.execute("SELECT id, uid FROM foods WHERE uid = ?", (uid,)).fetchone()
        if existing is None and barcode:
            clash = conn.execute("SELECT id FROM foods WHERE barcode = ?", (barcode,)).fetchone()
            if clash:   # el mismo producto ya existe localmente con otro uid: se reutiliza
                uid_to_id[uid] = int(clash["id"])
                continue
        values = (
            name, brand, normalize_text(f"{name} {brand or ''}"), source, barcode, kcal, p, c, f, serving,
            r.text("serving_label"), r.text("data_flag"), 1 if r.text("archived") in ("1", "true", "True") else 0,
            r.text("off_fetched_at"), r.text("created_at") or datetime.now(timezone.utc).isoformat(timespec="seconds"),
        )
        if existing:
            conn.execute(
                """
                UPDATE foods SET name = ?, brand = ?, name_norm = ?, source = ?, barcode = ?, kcal_100g = ?,
                    protein_100g = ?, carbs_100g = ?, fat_100g = ?, serving_g = ?, serving_label = ?,
                    data_flag = ?, archived = ?, off_fetched_at = ?, created_at = ? WHERE id = ?
                """,
                (*values, existing["id"]),
            )
            uid_to_id[uid] = int(existing["id"])
        else:
            cur = conn.execute(
                """
                INSERT INTO foods (name, brand, name_norm, source, barcode, kcal_100g, protein_100g, carbs_100g,
                    fat_100g, serving_g, serving_label, data_flag, archived, off_fetched_at, created_at, uid)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (*values, uid),
            )
            uid_to_id[uid] = int(cur.lastrowid)
        n += 1
    return n


def _food_id(conn, uid: str | None, uid_to_id: dict[str, int]) -> int | None:
    if uid is None:
        return None
    if uid in uid_to_id:
        return uid_to_id[uid]
    row = conn.execute("SELECT id FROM foods WHERE uid = ?", (uid,)).fetchone()
    return int(row["id"]) if row else None


def _import_recipes(conn, data, errors, uid_to_id) -> int:
    n = 0
    for r in _rows("recipes", data, ["food_uid", "total_yield_g"], errors):
        uid = r.text("food_uid", True)
        yield_g = r.number_("total_yield_g", True, 0, exclusive_min=True)
        servings = r.number_("servings", minimum=0, exclusive_min=True) or 1.0
        food_id = _food_id(conn, uid, uid_to_id)
        if uid and food_id is None:
            r._fail("food_uid", f"el alimento '{uid}' no existe (importa foods.csv primero)")
        if not r.ok:
            continue
        conn.execute(
            """
            INSERT INTO recipes (food_id, total_yield_g, servings) VALUES (?, ?, ?)
            ON CONFLICT(food_id) DO UPDATE SET total_yield_g = excluded.total_yield_g,
                servings = excluded.servings
            """,
            (food_id, yield_g, servings),
        )
        n += 1
    return n


def _import_recipe_items(conn, data, errors, uid_to_id) -> int:
    n = 0
    cleared: set[int] = set()
    for r in _rows("recipe_items", data, ["recipe_uid", "ingredient_uid", "grams"], errors):
        recipe_uid, ing_uid = r.text("recipe_uid", True), r.text("ingredient_uid", True)
        grams = r.number_("grams", True, 0, exclusive_min=True)
        recipe_id, ing_id = _food_id(conn, recipe_uid, uid_to_id), _food_id(conn, ing_uid, uid_to_id)
        if recipe_uid and conn.execute("SELECT 1 FROM recipes WHERE food_id = ?", (recipe_id,)).fetchone() is None:
            r._fail("recipe_uid", f"la receta '{recipe_uid}' no está en recipes.csv ni en la base")
        if ing_uid and ing_id is None:
            r._fail("ingredient_uid", f"el ingrediente '{ing_uid}' no existe")
        if not r.ok:
            continue
        if recipe_id not in cleared:   # los ingredientes importados reemplazan los existentes de esa receta
            conn.execute("DELETE FROM recipe_items WHERE recipe_food_id = ?", (recipe_id,))
            cleared.add(recipe_id)
        conn.execute(
            "INSERT INTO recipe_items (recipe_food_id, ingredient_food_id, grams) VALUES (?, ?, ?)",
            (recipe_id, ing_id, grams),
        )
        n += 1
    return n


def _import_food_log(conn, data, errors, uid_to_id) -> int:
    n = 0
    needed = ["uid", "date", "meal", "food_uid", "grams", "kcal", "protein_g", "carbs_g", "fat_g"]
    for r in _rows("food_log", data, needed, errors):
        uid, day = r.text("uid", True), r.day("date")
        meal = r.choice("meal", MEALS)
        food_uid = r.text("food_uid", True)
        grams = r.number_("grams", True, 0, exclusive_min=True)
        kcal, p, c, f = (r.number_(col, True, 0) for col in ("kcal", "protein_g", "carbs_g", "fat_g"))
        food_id = _food_id(conn, food_uid, uid_to_id)
        if food_uid and food_id is None:
            r._fail("food_uid", f"el alimento '{food_uid}' no existe (importa foods.csv primero)")
        if not r.ok:
            continue
        conn.execute(
            """
            INSERT INTO food_log (uid, date, meal, food_id, grams, kcal, protein_g, carbs_g, fat_g, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(uid) DO UPDATE SET date = excluded.date, meal = excluded.meal,
                food_id = excluded.food_id, grams = excluded.grams, kcal = excluded.kcal,
                protein_g = excluded.protein_g, carbs_g = excluded.carbs_g, fat_g = excluded.fat_g
            """,
            (uid, day, meal, food_id, grams, kcal, p, c, f,
             r.text("created_at") or datetime.now(timezone.utc).isoformat(timespec="seconds")),
        )
        n += 1
    return n


def _import_day_status(conn, data, errors) -> int:
    n = 0
    for r in _rows("day_status", data, ["date", "food_complete"], errors):
        day = r.day("date")
        flag = r.choice("food_complete", ("0", "1"), required=False)
        if not r.ok:
            continue
        if flag is None:
            conn.execute("DELETE FROM day_status WHERE date = ?", (day,))
        else:
            conn.execute(
                "INSERT INTO day_status (date, food_complete) VALUES (?, ?) "
                "ON CONFLICT(date) DO UPDATE SET food_complete = excluded.food_complete",
                (day, int(flag)),
            )
        n += 1
    return n


def _import_targets(conn, data, errors) -> int:
    n = 0
    needed = ["effective_from", "kcal", "protein_g", "carbs_g", "fat_g", "tdee_source"]
    for r in _rows("targets", data, needed, errors):
        day = r.day("effective_from")
        kcal = r.number_("kcal", True, 0, exclusive_min=True)
        p, c, f = (r.number_(col, True, 0) for col in ("protein_g", "carbs_g", "fat_g"))
        source = r.choice("tdee_source", ("formula", "data", "manual"))
        if not r.ok:
            continue
        conn.execute(
            """
            INSERT INTO targets (effective_from, kcal, protein_g, carbs_g, fat_g, tdee_source, bmr_method, note)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(effective_from) DO UPDATE SET kcal = excluded.kcal, protein_g = excluded.protein_g,
                carbs_g = excluded.carbs_g, fat_g = excluded.fat_g, tdee_source = excluded.tdee_source,
                bmr_method = excluded.bmr_method, note = excluded.note
            """,
            (day, kcal, p, c, f, source, r.text("bmr_method"), r.text("note")),
        )
        n += 1
    return n
