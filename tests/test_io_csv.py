import io
import zipfile

import pandas as pd
import pytest

from macro_tracker import io_csv
from macro_tracker.db.connection import connect
from macro_tracker.db.repository import Repository
from macro_tracker.foods.recipes import save_recipe
from macro_tracker.io_csv import ImportErrors


def populate(repo, profile):
    repo.save_profile(**profile)
    repo.upsert_body("2026-03-01", weight_kg=80.4)
    repo.upsert_body("2026-03-03", weight_kg=80.0, body_fat_pct=18.5, body_fat_source="measured",
                     waist_cm=82.0, neck_cm=38.0, note="en ayunas, con ñ y, coma")
    tortilla = repo.add_food("Tortilla de maíz", 218, 5.7, 44.6, 2.8, serving_g=30, serving_label="1 tortilla")
    off = repo.add_food("Producto OFF", 400, 10, 60, 12, brand="Marca", source="off", barcode="7501000000001",
                        data_flag="kcal_mismatch")
    recipe = save_recipe(repo, "Tacos", [(tortilla, 90), (off, 20)], total_yield_g=100, servings=3)
    repo.add_log("2026-03-02", "lunch", tortilla, 90)
    repo.add_log("2026-03-02", "dinner", recipe, 120)
    repo.set_day_status("2026-03-01", False)
    repo.set_target("2026-03-01", 2300, 160, 260, 75, "formula", "mifflin_st_jeor", "inicial")


def snapshot(repo):
    """Contenido comparable entre bases (sin ids autoincrementales)."""
    c = repo.conn
    return {
        "profile": [dict(r) for r in c.execute("SELECT * FROM profile")],
        "body": [dict(r) for r in c.execute("SELECT * FROM body_log ORDER BY date")],
        "foods": [dict(r) for r in c.execute(
            "SELECT uid, name, brand, name_norm, source, barcode, kcal_100g, protein_100g, carbs_100g, fat_100g,"
            " serving_g, serving_label, data_flag, archived FROM foods ORDER BY uid")],
        "recipes": [dict(r) for r in c.execute(
            "SELECT f.uid, r.total_yield_g, r.servings FROM recipes r JOIN foods f ON f.id = r.food_id")],
        "items": sorted(tuple(r) for r in c.execute(
            "SELECT rf.uid, inf.uid, ri.grams FROM recipe_items ri JOIN foods rf ON rf.id = ri.recipe_food_id "
            "JOIN foods inf ON inf.id = ri.ingredient_food_id")),
        "log": [dict(r) for r in c.execute(
            "SELECT l.uid, l.date, l.meal, f.uid AS food_uid, l.grams, l.kcal, l.protein_g, l.carbs_g, l.fat_g "
            "FROM food_log l JOIN foods f ON f.id = l.food_id ORDER BY l.uid")],
        "status": [dict(r) for r in c.execute("SELECT * FROM day_status")],
        "targets": [dict(r) for r in c.execute("SELECT * FROM targets")],
    }


def fresh():
    return Repository(connect(":memory:"))


def test_zip_roundtrip_restores_everything_exactly(repo, sample_profile):
    populate(repo, sample_profile)
    blob = io_csv.export_zip(repo)
    with zipfile.ZipFile(io.BytesIO(blob)) as zf:
        assert set(zf.namelist()) == {"manifest.json", *[f"{t}.csv" for t in io_csv.TABLES]}
    target = fresh()
    report = io_csv.import_zip(target, blob, mode="replace")
    assert report.counts["food_log"] == 2 and report.counts["foods"] == 3
    assert snapshot(target) == snapshot(repo)
    # los cálculos dependientes dan lo mismo
    assert target.daily_totals().equals(repo.daily_totals())
    assert target.body_df().equals(repo.body_df())


def test_individual_csv_has_bom_and_header(repo, sample_profile):
    populate(repo, sample_profile)
    data = io_csv.export_table_csv(repo, "body_log")
    assert data.startswith(b"\xef\xbb\xbf")
    first = data.decode("utf-8-sig").splitlines()[0]
    assert first == "date,weight_kg,body_fat_pct,body_fat_source,waist_cm,neck_cm,hip_cm,note"
    df = pd.read_csv(io.BytesIO(data))        # legible desde pandas / Excel
    assert df.loc[1, "note"] == "en ayunas, con ñ y, coma"
    assert pd.isna(df.loc[0, "body_fat_pct"])  # faltante = vacío, no 0


def test_merge_is_idempotent_and_does_not_duplicate(repo, sample_profile):
    populate(repo, sample_profile)
    blob = io_csv.export_zip(repo)
    before = snapshot(repo)
    io_csv.import_zip(repo, blob, mode="merge")
    io_csv.import_zip(repo, blob, mode="merge")
    assert snapshot(repo) == before


def test_merge_combines_two_databases_and_imported_wins(repo, sample_profile):
    populate(repo, sample_profile)
    other = fresh()
    other.save_profile(**sample_profile)
    other.upsert_body("2026-03-01", weight_kg=79.0)           # mismo día, otro valor
    other.upsert_body("2026-03-09", weight_kg=78.0)           # día nuevo
    f = other.add_food("Frijoles", 132, 8.9, 23.7, 0.5)
    other.add_log("2026-03-09", "lunch", f, 200)
    io_csv.import_zip(repo, io_csv.export_zip(other), mode="merge")
    body = repo.body_df()
    assert body.loc["2026-03-01", "weight_kg"] == 79.0         # ganó lo importado
    assert body.loc["2026-03-09", "weight_kg"] == 78.0
    assert pd.Timestamp("2026-03-03") in body.index            # lo previo se conserva
    assert len(repo.log_for_date("2026-03-09")) == 1
    assert len(repo.log_for_date("2026-03-02")) == 2           # el diario previo sigue intacto


def test_merge_reuses_same_off_barcode_under_different_uid(repo):
    repo.add_food("Producto", 100, 1, 1, 1, source="off", barcode="123")
    other = fresh()
    of = other.add_food("Producto", 100, 1, 1, 1, source="off", barcode="123")
    other.add_log("2026-03-01", "snack", of, 100)
    io_csv.import_zip(repo, io_csv.export_zip(other), mode="merge")
    assert len(repo.list_foods()) == 1                          # no se duplicó por el código de barras
    assert len(repo.log_for_date("2026-03-01")) == 1            # y la entrada apunta al alimento local


def test_replace_wipes_previous_data(repo, sample_profile):
    populate(repo, sample_profile)
    other = fresh()
    other.upsert_body("2026-05-01", weight_kg=70)
    # un ZIP parcial (solo body_log) reemplaza únicamente esa tabla
    io_csv.import_tables(repo, {"body_log": io_csv.export_table_csv(other, "body_log")}, mode="replace")
    assert list(repo.body_df().index) == [pd.Timestamp("2026-05-01")]
    assert len(repo.log_for_date("2026-03-02")) == 2           # el resto quedó intacto


def test_invalid_rows_cancel_everything_and_report_locations(repo, sample_profile):
    populate(repo, sample_profile)
    before = snapshot(repo)
    bad_body = (
        "date,weight_kg,body_fat_pct,body_fat_source\n"
        "2026-04-01,80,,\n"
        "no-es-fecha,80,,\n"
        "2026-04-03,-5,,\n"
        "2026-04-04,80,20,\n"             # % de grasa sin origen
    ).encode()
    with pytest.raises(ImportErrors) as exc:
        io_csv.import_csv(repo, "body_log", bad_body)
    msg = str(exc.value)
    assert "fila 3" in msg and "fecha" in msg
    assert "fila 4" in msg and "weight_kg" in msg
    assert "fila 5" in msg and "body_fat_source" in msg
    assert len(exc.value.errors) == 3
    assert snapshot(repo) == before          # nada se escribió, ni siquiera la fila 2 válida


def test_error_in_later_table_rolls_back_earlier_tables(repo, sample_profile):
    populate(repo, sample_profile)
    before = snapshot(repo)
    files = {
        "body_log": b"date,weight_kg\n2026-06-01,75\n",
        "food_log": b"uid,date,meal,food_uid,grams,kcal,protein_g,carbs_g,fat_g\n"
                    b"x1,2026-06-01,brunch,no-existe,100,100,1,1,1\n",
    }
    with pytest.raises(ImportErrors) as exc:
        io_csv.import_tables(repo, files)
    assert any("meal" in e for e in exc.value.errors) and any("food_uid" in e for e in exc.value.errors)
    assert snapshot(repo) == before


def test_missing_required_columns_and_bad_inputs(repo):
    with pytest.raises(ImportErrors) as exc:
        io_csv.import_csv(repo, "body_log", b"fecha,peso\n2026-01-01,80\n")
    assert "faltan columnas" in str(exc.value)
    with pytest.raises(ImportErrors):
        io_csv.import_zip(repo, b"esto no es un zip")
    with pytest.raises(ImportErrors):
        io_csv.import_csv(repo, "body_log", "date,weight_kg\n2026-01-01,80\n".encode("utf-16"))
    with pytest.raises(ValueError):
        io_csv.import_tables(repo, {"otra_tabla": b""})
    with pytest.raises(ValueError):
        io_csv.import_csv(repo, "body_log", b"date\n", mode="mezclar")


def test_accepts_excel_style_bom_and_decimal_comma(repo):
    data = "﻿date,weight_kg,waist_cm\n2026-02-01,\"80,5\",\"82,25\"\n".encode("utf-8")
    io_csv.import_csv(repo, "body_log", data)
    row = repo.get_body("2026-02-01")
    assert row["weight_kg"] == 80.5 and row["waist_cm"] == 82.25


def test_newer_schema_zip_is_refused(repo, sample_profile):
    blob = io_csv.export_zip(repo)
    buf = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(blob)) as src, zipfile.ZipFile(buf, "w") as dst:
        for name in src.namelist():
            data = src.read(name)
            if name == "manifest.json":
                data = b'{"schema_version": 99}'
            dst.writestr(name, data)
    with pytest.raises(ImportErrors):
        io_csv.import_zip(repo, buf.getvalue())


def test_food_validations_on_import(repo):
    data = (
        "uid,name,kcal_100g,protein_100g,carbs_100g,fat_100g\n"
        "a,Imposible,1500,1,1,1\n"
        "b,Suma mal,100,60,60,10\n"
    ).encode()
    with pytest.raises(ImportErrors) as exc:
        io_csv.import_csv(repo, "foods", data)
    assert len(exc.value.errors) == 2


def test_profile_import_validates_and_upserts(repo, sample_profile):
    repo.save_profile(**sample_profile)
    csv_text = (
        "sex,birth_date,height_cm,activity_level,goal,rate_kg_week\n"
        "F,1999-01-02,165,light,gain,0.25\n"
    ).encode()
    io_csv.import_csv(repo, "profile", csv_text)
    p = repo.get_profile()
    assert p["sex"] == "F" and p["goal"] == "gain" and p["protein_g_kg_min"] == 1.6
    with pytest.raises(ImportErrors):
        io_csv.import_csv(repo, "profile", b"sex,birth_date,height_cm,activity_level,goal\nX,2000-01-01,170,light,gain\n")
