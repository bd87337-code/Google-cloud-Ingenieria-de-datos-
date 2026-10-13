"""Acceso a datos. Único módulo con SQL (junto con la importación de CSV)."""
from __future__ import annotations

import sqlite3
import uuid
from datetime import date, datetime, timezone

import pandas as pd

from macro_tracker.calc.nutrition import Macros, macros_for_grams, validate_per_100g
from macro_tracker.textutil import normalize_text

DateLike = date | str | pd.Timestamp


def iso(day: DateLike) -> str:
    if isinstance(day, str):
        return date.fromisoformat(day).isoformat()
    if isinstance(day, datetime):  # incluye pd.Timestamp
        return day.date().isoformat()
    return day.isoformat()


def _like_escape(text: str) -> str:
    """Escapa comodines de LIKE (se usa con ESCAPE '\\')."""
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _row(row: sqlite3.Row | None) -> dict | None:
    return dict(row) if row is not None else None


FOOD_EDITABLE = (
    "name", "brand", "kcal_100g", "protein_100g", "carbs_100g", "fat_100g",
    "serving_g", "serving_label", "barcode", "data_flag", "archived",
)


class Repository:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    # ------------------------------------------------------------------ perfil
    def get_profile(self) -> dict | None:
        return _row(self.conn.execute("SELECT * FROM profile WHERE id = 1").fetchone())

    def save_profile(
        self,
        *,
        sex: str,
        birth_date: DateLike,
        height_cm: float,
        activity_level: str,
        goal: str,
        rate_kg_week: float,
        protein_g_kg_min: float = 1.6,
        protein_g_kg_max: float = 2.2,
        fat_g_kg_min: float = 0.6,
        fat_pct_kcal: float = 0.25,
        bmr_method_pref: str = "auto",
        min_valid_day_kcal: float = 1000.0,
    ) -> None:
        with self.conn:
            self.conn.execute(
                """
                INSERT INTO profile (id, sex, birth_date, height_cm, activity_level, goal,
                    rate_kg_week, protein_g_kg_min, protein_g_kg_max, fat_g_kg_min,
                    fat_pct_kcal, bmr_method_pref, min_valid_day_kcal, updated_at)
                VALUES (1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    sex = excluded.sex, birth_date = excluded.birth_date,
                    height_cm = excluded.height_cm, activity_level = excluded.activity_level,
                    goal = excluded.goal, rate_kg_week = excluded.rate_kg_week,
                    protein_g_kg_min = excluded.protein_g_kg_min,
                    protein_g_kg_max = excluded.protein_g_kg_max,
                    fat_g_kg_min = excluded.fat_g_kg_min, fat_pct_kcal = excluded.fat_pct_kcal,
                    bmr_method_pref = excluded.bmr_method_pref,
                    min_valid_day_kcal = excluded.min_valid_day_kcal,
                    updated_at = excluded.updated_at
                """,
                (
                    sex, iso(birth_date), height_cm, activity_level, goal, rate_kg_week,
                    protein_g_kg_min, protein_g_kg_max, fat_g_kg_min, fat_pct_kcal,
                    bmr_method_pref, min_valid_day_kcal, _now(),
                ),
            )

    # --------------------------------------------------------- peso y medidas
    def upsert_body(
        self,
        day: DateLike,
        *,
        weight_kg: float | None = None,
        body_fat_pct: float | None = None,
        body_fat_source: str | None = None,
        waist_cm: float | None = None,
        neck_cm: float | None = None,
        hip_cm: float | None = None,
        note: str | None = None,
    ) -> None:
        """Guarda la fila completa del día; si todo viene vacío, borra la fila."""
        if body_fat_pct is not None and body_fat_source is None:
            raise ValueError("indica el origen del % de grasa (medido, estimado o Navy)")
        if all(v is None for v in (weight_kg, body_fat_pct, waist_cm, neck_cm, hip_cm)) and not note:
            self.delete_body(day)
            return
        with self.conn:
            self.conn.execute(
                """
                INSERT INTO body_log (date, weight_kg, body_fat_pct, body_fat_source,
                    waist_cm, neck_cm, hip_cm, note)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(date) DO UPDATE SET
                    weight_kg = excluded.weight_kg, body_fat_pct = excluded.body_fat_pct,
                    body_fat_source = excluded.body_fat_source, waist_cm = excluded.waist_cm,
                    neck_cm = excluded.neck_cm, hip_cm = excluded.hip_cm, note = excluded.note
                """,
                (
                    iso(day), weight_kg, body_fat_pct,
                    body_fat_source if body_fat_pct is not None else None,
                    waist_cm, neck_cm, hip_cm, note or None,
                ),
            )

    def get_body(self, day: DateLike) -> dict | None:
        return _row(self.conn.execute("SELECT * FROM body_log WHERE date = ?", (iso(day),)).fetchone())

    def delete_body(self, day: DateLike) -> None:
        with self.conn:
            self.conn.execute("DELETE FROM body_log WHERE date = ?", (iso(day),))

    def body_df(self, start: DateLike | None = None, end: DateLike | None = None) -> pd.DataFrame:
        sql, params = "SELECT * FROM body_log", []
        clauses = []
        if start is not None:
            clauses.append("date >= ?")
            params.append(iso(start))
        if end is not None:
            clauses.append("date <= ?")
            params.append(iso(end))
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        df = pd.read_sql_query(sql + " ORDER BY date", self.conn, params=params)
        df["date"] = pd.to_datetime(df["date"])
        return df.set_index("date")

    # -------------------------------------------------------------- alimentos
    @staticmethod
    def _check_food_fields(name: str, macros: Macros, serving_g: float | None) -> None:
        if not name or not name.strip():
            raise ValueError("el alimento necesita un nombre")
        errors = validate_per_100g(macros)
        if serving_g is not None and serving_g <= 0:
            errors.append("la porción debe ser mayor que 0")
        if errors:
            raise ValueError("; ".join(errors))

    def add_food(
        self,
        name: str,
        kcal_100g: float,
        protein_100g: float,
        carbs_100g: float,
        fat_100g: float,
        *,
        brand: str | None = None,
        source: str = "custom",
        barcode: str | None = None,
        serving_g: float | None = None,
        serving_label: str | None = None,
        data_flag: str | None = None,
        off_fetched_at: str | None = None,
        uid: str | None = None,
    ) -> int:
        self._check_food_fields(name, Macros(kcal_100g, protein_100g, carbs_100g, fat_100g), serving_g)
        with self.conn:
            cur = self.conn.execute(
                """
                INSERT INTO foods (uid, name, brand, name_norm, source, barcode, kcal_100g,
                    protein_100g, carbs_100g, fat_100g, serving_g, serving_label, data_flag,
                    off_fetched_at, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    uid or uuid.uuid4().hex, name.strip(), (brand or "").strip() or None,
                    normalize_text(f"{name} {brand or ''}"), source, barcode or None,
                    kcal_100g, protein_100g, carbs_100g, fat_100g, serving_g,
                    serving_label or None, data_flag, off_fetched_at, _now(),
                ),
            )
        return int(cur.lastrowid)

    def get_food(self, food_id: int) -> dict | None:
        return _row(self.conn.execute("SELECT * FROM foods WHERE id = ?", (food_id,)).fetchone())

    def get_food_by_barcode(self, barcode: str) -> dict | None:
        return _row(self.conn.execute("SELECT * FROM foods WHERE barcode = ?", (barcode,)).fetchone())

    def get_food_by_uid(self, uid: str) -> dict | None:
        return _row(self.conn.execute("SELECT * FROM foods WHERE uid = ?", (uid,)).fetchone())

    def update_food(self, food_id: int, **fields) -> None:
        """Edita campos de un alimento. Editar un alimento de OFF lo convierte en propio.

        Los registros pasados no cambian: guardan su propio snapshot de macros.
        """
        unknown = set(fields) - set(FOOD_EDITABLE)
        if unknown:
            raise ValueError(f"campos no editables: {sorted(unknown)}")
        current = self.get_food(food_id)
        if current is None:
            raise KeyError(f"alimento {food_id} no existe")
        merged = {**current, **fields}
        self._check_food_fields(
            merged["name"],
            Macros(merged["kcal_100g"], merged["protein_100g"], merged["carbs_100g"], merged["fat_100g"]),
            merged["serving_g"],
        )
        changed = any(
            fields.get(k, current[k]) != current[k]
            for k in ("name", "brand", "kcal_100g", "protein_100g", "carbs_100g", "fat_100g")
        )
        merged["name_norm"] = normalize_text(f"{merged['name']} {merged['brand'] or ''}")
        source = current["source"]
        if source == "off" and changed:
            # El usuario corrigió datos de OFF: pasa a ser un alimento propio y se
            # retira la advertencia de coherencia (ya los validó él).
            source = "custom"
            if "data_flag" not in fields:
                merged["data_flag"] = None
        with self.conn:
            self.conn.execute(
                """
                UPDATE foods SET name = ?, brand = ?, name_norm = ?, source = ?, barcode = ?,
                    kcal_100g = ?, protein_100g = ?, carbs_100g = ?, fat_100g = ?,
                    serving_g = ?, serving_label = ?, data_flag = ?, archived = ?
                WHERE id = ?
                """,
                (
                    merged["name"].strip(), (merged["brand"] or "").strip() or None,
                    merged["name_norm"], source, merged["barcode"] or None,
                    merged["kcal_100g"], merged["protein_100g"], merged["carbs_100g"],
                    merged["fat_100g"], merged["serving_g"], merged["serving_label"] or None,
                    merged["data_flag"], int(merged["archived"]), food_id,
                ),
            )

    def search_foods(self, query: str, limit: int = 25, include_archived: bool = False) -> list[dict]:
        """Búsqueda por todos los términos (AND) sin acentos ni mayúsculas.

        Orden: alimentos propios y recetas primero, luego los que empiezan con la
        consulta, luego los de nombre más corto.
        """
        tokens = normalize_text(query).split()
        if not tokens:
            return []
        where = " AND ".join("name_norm LIKE ? ESCAPE '\\'" for _ in tokens)
        params: list = [f"%{_like_escape(t)}%" for t in tokens]
        if not include_archived:
            where += " AND archived = 0"
        prefix = _like_escape(normalize_text(query)) + "%"
        rows = self.conn.execute(
            f"""
            SELECT * FROM foods WHERE {where}
            ORDER BY (source = 'off') ASC,
                     (name_norm LIKE ? ESCAPE '\\') DESC,
                     LENGTH(name) ASC, name ASC
            LIMIT ?
            """,
            [*params, prefix, limit],
        ).fetchall()
        return [dict(r) for r in rows]

    def list_foods(self, source: str | None = None, include_archived: bool = False) -> list[dict]:
        clauses, params = [], []
        if source:
            clauses.append("source = ?")
            params.append(source)
        if not include_archived:
            clauses.append("archived = 0")
        sql = "SELECT * FROM foods" + (" WHERE " + " AND ".join(clauses) if clauses else "")
        return [dict(r) for r in self.conn.execute(sql + " ORDER BY name_norm", params).fetchall()]

    def food_is_used(self, food_id: int) -> bool:
        in_log = self.conn.execute("SELECT 1 FROM food_log WHERE food_id = ? LIMIT 1", (food_id,)).fetchone()
        in_recipe = self.conn.execute(
            "SELECT 1 FROM recipe_items WHERE ingredient_food_id = ? LIMIT 1", (food_id,)
        ).fetchone()
        return bool(in_log or in_recipe)

    def delete_food(self, food_id: int) -> str:
        """Borra el alimento si no se usa; si ya está en el diario o en recetas lo archiva."""
        if self.food_is_used(food_id):
            with self.conn:
                self.conn.execute("UPDATE foods SET archived = 1 WHERE id = ?", (food_id,))
            return "archived"
        with self.conn:
            self.conn.execute("DELETE FROM foods WHERE id = ?", (food_id,))
        return "deleted"

    def upsert_off_food(self, *, barcode: str, name: str, brand: str | None, macros: Macros,
                        serving_g: float | None, serving_label: str | None,
                        data_flag: str | None) -> int:
        """Guarda un producto de OFF en la caché. Si el código ya existe y el usuario lo
        editó (source = 'custom'), no se sobrescribe."""
        existing = self.get_food_by_barcode(barcode)
        if existing is None:
            return self.add_food(
                name, macros.kcal, macros.protein_g, macros.carbs_g, macros.fat_g,
                brand=brand, source="off", barcode=barcode, serving_g=serving_g,
                serving_label=serving_label, data_flag=data_flag, off_fetched_at=_now(),
            )
        if existing["source"] == "off":
            with self.conn:
                self.conn.execute(
                    """
                    UPDATE foods SET name = ?, brand = ?, name_norm = ?, kcal_100g = ?,
                        protein_100g = ?, carbs_100g = ?, fat_100g = ?, serving_g = ?,
                        serving_label = ?, data_flag = ?, off_fetched_at = ?
                    WHERE id = ?
                    """,
                    (
                        name.strip(), (brand or "").strip() or None,
                        normalize_text(f"{name} {brand or ''}"), macros.kcal, macros.protein_g,
                        macros.carbs_g, macros.fat_g, serving_g, serving_label, data_flag,
                        _now(), existing["id"],
                    ),
                )
        return int(existing["id"])

    # ----------------------------------------------------------------- recetas
    def set_recipe(self, food_id: int, total_yield_g: float, servings: float,
                   items: list[tuple[int, float]]) -> None:
        """Define (reemplazando) el rendimiento y los ingredientes de una receta."""
        if total_yield_g <= 0 or servings <= 0:
            raise ValueError("el rendimiento y las porciones deben ser positivos")
        if not items:
            raise ValueError("la receta necesita al menos un ingrediente")
        if any(grams <= 0 for _, grams in items):
            raise ValueError("los gramos de cada ingrediente deben ser positivos")
        if any(ing == food_id for ing, _ in items):
            raise ValueError("una receta no puede contenerse a sí misma")
        with self.conn:
            self.conn.execute(
                """
                INSERT INTO recipes (food_id, total_yield_g, servings) VALUES (?, ?, ?)
                ON CONFLICT(food_id) DO UPDATE SET
                    total_yield_g = excluded.total_yield_g, servings = excluded.servings
                """,
                (food_id, total_yield_g, servings),
            )
            self.conn.execute("DELETE FROM recipe_items WHERE recipe_food_id = ?", (food_id,))
            self.conn.executemany(
                "INSERT INTO recipe_items (recipe_food_id, ingredient_food_id, grams) VALUES (?, ?, ?)",
                [(food_id, ing, grams) for ing, grams in items],
            )

    def get_recipe(self, food_id: int) -> dict | None:
        head = self.conn.execute("SELECT * FROM recipes WHERE food_id = ?", (food_id,)).fetchone()
        if head is None:
            return None
        items = self.conn.execute(
            """
            SELECT ri.id, ri.ingredient_food_id, ri.grams, f.name, f.kcal_100g, f.protein_100g,
                   f.carbs_100g, f.fat_100g
            FROM recipe_items ri JOIN foods f ON f.id = ri.ingredient_food_id
            WHERE ri.recipe_food_id = ? ORDER BY ri.id
            """,
            (food_id,),
        ).fetchall()
        return {**dict(head), "items": [dict(i) for i in items]}

    def recipes_using(self, ingredient_food_id: int) -> list[int]:
        rows = self.conn.execute(
            "SELECT DISTINCT recipe_food_id FROM recipe_items WHERE ingredient_food_id = ?",
            (ingredient_food_id,),
        ).fetchall()
        return [int(r["recipe_food_id"]) for r in rows]

    # ------------------------------------------------------------------ diario
    def add_log(self, day: DateLike, meal: str, food_id: int, grams: float, *,
                uid: str | None = None) -> int:
        food = self.get_food(food_id)
        if food is None:
            raise KeyError(f"alimento {food_id} no existe")
        if grams <= 0:
            raise ValueError("la cantidad debe ser mayor que 0")
        m = macros_for_grams(
            Macros(food["kcal_100g"], food["protein_100g"], food["carbs_100g"], food["fat_100g"]), grams
        )
        with self.conn:
            cur = self.conn.execute(
                """
                INSERT INTO food_log (uid, date, meal, food_id, grams, kcal, protein_g, carbs_g,
                    fat_g, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (uid or uuid.uuid4().hex, iso(day), meal, food_id, grams, m.kcal, m.protein_g,
                 m.carbs_g, m.fat_g, _now()),
            )
        return int(cur.lastrowid)

    def update_log_grams(self, log_id: int, grams: float) -> None:
        """Cambia la cantidad de una entrada reescalando su propio snapshot."""
        if grams <= 0:
            raise ValueError("la cantidad debe ser mayor que 0")
        row = self.conn.execute("SELECT grams FROM food_log WHERE id = ?", (log_id,)).fetchone()
        if row is None:
            raise KeyError(f"entrada {log_id} no existe")
        factor = grams / row["grams"]
        with self.conn:
            self.conn.execute(
                """
                UPDATE food_log SET grams = ?, kcal = kcal * ?, protein_g = protein_g * ?,
                    carbs_g = carbs_g * ?, fat_g = fat_g * ? WHERE id = ?
                """,
                (grams, factor, factor, factor, factor, log_id),
            )

    def delete_log(self, log_id: int) -> None:
        with self.conn:
            self.conn.execute("DELETE FROM food_log WHERE id = ?", (log_id,))

    def log_for_date(self, day: DateLike) -> pd.DataFrame:
        return pd.read_sql_query(
            """
            SELECT l.id, l.meal, l.food_id, f.name, f.brand, l.grams, l.kcal, l.protein_g,
                   l.carbs_g, l.fat_g
            FROM food_log l JOIN foods f ON f.id = l.food_id
            WHERE l.date = ? ORDER BY l.created_at, l.id
            """,
            self.conn,
            params=[iso(day)],
        )

    def daily_totals(self, start: DateLike | None = None, end: DateLike | None = None) -> pd.DataFrame:
        sql = ("SELECT date, SUM(kcal) AS kcal, SUM(protein_g) AS protein_g, SUM(carbs_g) AS carbs_g, "
               "SUM(fat_g) AS fat_g, COUNT(*) AS n_entries FROM food_log")
        clauses, params = [], []
        if start is not None:
            clauses.append("date >= ?")
            params.append(iso(start))
        if end is not None:
            clauses.append("date <= ?")
            params.append(iso(end))
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        df = pd.read_sql_query(sql + " GROUP BY date ORDER BY date", self.conn, params=params)
        df["date"] = pd.to_datetime(df["date"])
        return df.set_index("date")

    def recent_foods(self, limit: int = 12) -> list[dict]:
        rows = self.conn.execute(
            """
            SELECT f.*, MAX(l.created_at) AS last_used FROM food_log l
            JOIN foods f ON f.id = l.food_id WHERE f.archived = 0
            GROUP BY f.id ORDER BY last_used DESC, MAX(l.id) DESC LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]

    # ---------------------------------------------------------- estado del día
    def set_day_status(self, day: DateLike, complete: bool | None) -> None:
        """True/False fuerza el día como válido/no válido; None vuelve a la regla automática."""
        with self.conn:
            if complete is None:
                self.conn.execute("DELETE FROM day_status WHERE date = ?", (iso(day),))
            else:
                self.conn.execute(
                    """
                    INSERT INTO day_status (date, food_complete) VALUES (?, ?)
                    ON CONFLICT(date) DO UPDATE SET food_complete = excluded.food_complete
                    """,
                    (iso(day), int(complete)),
                )

    def day_status_map(self, start: DateLike | None = None, end: DateLike | None = None) -> dict[pd.Timestamp, bool]:
        sql, params, clauses = "SELECT date, food_complete FROM day_status", [], []
        if start is not None:
            clauses.append("date >= ?")
            params.append(iso(start))
        if end is not None:
            clauses.append("date <= ?")
            params.append(iso(end))
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        return {
            pd.Timestamp(r["date"]): bool(r["food_complete"])
            for r in self.conn.execute(sql, params).fetchall()
            if r["food_complete"] is not None
        }

    # ------------------------------------------------------------------ metas
    def set_target(self, effective_from: DateLike, kcal: float, protein_g: float, carbs_g: float,
                   fat_g: float, tdee_source: str, bmr_method: str | None = None,
                   note: str | None = None) -> None:
        with self.conn:
            self.conn.execute(
                """
                INSERT INTO targets (effective_from, kcal, protein_g, carbs_g, fat_g, tdee_source,
                    bmr_method, note) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(effective_from) DO UPDATE SET
                    kcal = excluded.kcal, protein_g = excluded.protein_g, carbs_g = excluded.carbs_g,
                    fat_g = excluded.fat_g, tdee_source = excluded.tdee_source,
                    bmr_method = excluded.bmr_method, note = excluded.note
                """,
                (iso(effective_from), kcal, protein_g, carbs_g, fat_g, tdee_source, bmr_method, note),
            )

    def target_on(self, day: DateLike) -> dict | None:
        """Meta vigente en `day` (la más reciente con effective_from ≤ day)."""
        return _row(
            self.conn.execute(
                "SELECT * FROM targets WHERE effective_from <= ? ORDER BY effective_from DESC LIMIT 1",
                (iso(day),),
            ).fetchone()
        )

    def targets_df(self) -> pd.DataFrame:
        df = pd.read_sql_query("SELECT * FROM targets ORDER BY effective_from", self.conn)
        df["effective_from"] = pd.to_datetime(df["effective_from"])
        return df.set_index("effective_from")

    def delete_target(self, effective_from: DateLike) -> None:
        with self.conn:
            self.conn.execute("DELETE FROM targets WHERE effective_from = ?", (iso(effective_from),))
