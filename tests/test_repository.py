import sqlite3

import pandas as pd
import pytest

from macro_tracker.db.connection import connect, schema_version
from macro_tracker.db.repository import Repository


def test_migrate_creates_schema_and_is_idempotent(tmp_path):
    path = tmp_path / "t.db"
    conn = connect(path)
    assert schema_version(conn) == 1
    conn.close()
    conn = connect(path)  # reabrir no vuelve a crear ni falla
    assert schema_version(conn) == 1
    conn.close()


def test_newer_database_version_is_refused(tmp_path):
    path = tmp_path / "t.db"
    conn = connect(path)
    conn.execute("INSERT INTO schema_version VALUES (99)")
    conn.commit()
    conn.close()
    with pytest.raises(RuntimeError):
        connect(path)


def test_profile_roundtrip_and_update(repo, sample_profile):
    assert repo.get_profile() is None
    repo.save_profile(**sample_profile)
    p = repo.get_profile()
    assert p["height_cm"] == 180 and p["protein_g_kg_min"] == 1.6 and p["bmr_method_pref"] == "auto"
    repo.save_profile(**{**sample_profile, "goal": "gain", "rate_kg_week": 0.25})
    assert repo.get_profile()["goal"] == "gain"
    assert repo.conn.execute("SELECT COUNT(*) FROM profile").fetchone()[0] == 1


def test_profile_rejects_invalid_values(repo, sample_profile):
    with pytest.raises(sqlite3.IntegrityError):
        repo.save_profile(**{**sample_profile, "sex": "X"})
    with pytest.raises(sqlite3.IntegrityError):
        repo.save_profile(**{**sample_profile, "rate_kg_week": -1})


def test_body_log_upsert_partial_rows_and_missing_days(repo):
    repo.upsert_body("2026-03-01", weight_kg=80.5)
    repo.upsert_body("2026-03-03", weight_kg=80.1, body_fat_pct=18.0, body_fat_source="measured")
    repo.upsert_body("2026-03-01", weight_kg=80.7)  # actualiza
    df = repo.body_df()
    assert list(df.index) == [pd.Timestamp("2026-03-01"), pd.Timestamp("2026-03-03")]
    assert df.loc["2026-03-01", "weight_kg"] == 80.7
    assert pd.isna(df.loc["2026-03-01", "body_fat_pct"])
    assert df.loc["2026-03-03", "body_fat_source"] == "measured"
    assert len(repo.body_df(start="2026-03-02")) == 1


def test_body_log_requires_source_for_body_fat_and_empty_row_deletes(repo):
    with pytest.raises(ValueError):
        repo.upsert_body("2026-03-01", body_fat_pct=20.0)
    repo.upsert_body("2026-03-01", weight_kg=80)
    repo.upsert_body("2026-03-01")  # todo vacío -> se elimina la fila
    assert repo.get_body("2026-03-01") is None


def test_body_log_rejects_implausible_values(repo):
    with pytest.raises(sqlite3.IntegrityError):
        repo.upsert_body("2026-03-01", weight_kg=-5)
    with pytest.raises(sqlite3.IntegrityError):
        repo.upsert_body("2026-03-01", body_fat_pct=90, body_fat_source="measured")


def test_add_and_get_food_validates(repo):
    fid = repo.add_food("Tortilla de maíz", 218, 5.7, 44.6, 2.8, serving_g=30, serving_label="1 tortilla")
    food = repo.get_food(fid)
    assert food["source"] == "custom" and food["name_norm"] == "tortilla de maiz"
    with pytest.raises(ValueError):
        repo.add_food("", 100, 1, 1, 1)
    with pytest.raises(ValueError):
        repo.add_food("Imposible", 1200, 1, 1, 1)
    with pytest.raises(ValueError):
        repo.add_food("Imposible 2", 100, 60, 60, 10)  # suma > 100 g por 100 g
    with pytest.raises(ValueError):
        repo.add_food("Mala porción", 100, 1, 1, 1, serving_g=0)


def test_search_is_accent_and_case_insensitive_and_multi_term(repo):
    repo.add_food("Chile jalapeño", 29, 0.9, 6.5, 0.4)
    repo.add_food("Frijoles negros cocidos", 132, 8.9, 23.7, 0.5)
    repo.add_food("Frijoles refritos", 150, 7, 20, 4)
    assert [f["name"] for f in repo.search_foods("JALAPENO")] == ["Chile jalapeño"]
    assert len(repo.search_foods("frijoles")) == 2
    assert [f["name"] for f in repo.search_foods("frijol negro")] == ["Frijoles negros cocidos"]  # subcadenas
    assert repo.search_foods("frijoles blancos") == []                                              # todos los términos
    assert [f["name"] for f in repo.search_foods("frijoles negr")] == ["Frijoles negros cocidos"]
    assert repo.search_foods("   ") == []


def test_search_escapes_like_wildcards(repo):
    repo.add_food("Salsa 100% natural", 20, 1, 3, 0.1)
    repo.add_food("Salsa verde", 20, 1, 3, 0.1)
    assert [f["name"] for f in repo.search_foods("100%")] == ["Salsa 100% natural"]
    assert repo.search_foods("_") == []


def test_search_ranks_custom_before_off_and_prefix_first(repo):
    repo.add_food("Tortilla de harina", 300, 8, 50, 7, source="off", barcode="1")
    repo.add_food("Mi tortilla de maíz", 218, 5.7, 44.6, 2.8)
    repo.add_food("Tortilla de maíz", 218, 5.7, 44.6, 2.8)
    names = [f["name"] for f in repo.search_foods("tortilla")]
    assert names[0] == "Tortilla de maíz"      # propio y empieza con la consulta
    assert names[-1] == "Tortilla de harina"   # OFF al final


def test_editing_off_food_turns_it_custom_and_clears_flag(repo):
    fid = repo.add_food("Producto X", 250, 5, 50, 3, source="off", barcode="123", data_flag="kcal_mismatch")
    repo.update_food(fid, kcal_100g=240)
    food = repo.get_food(fid)
    assert food["source"] == "custom" and food["data_flag"] is None
    # un cambio que no toca datos nutricionales no cambia el origen
    fid2 = repo.add_food("Producto Y", 250, 5, 50, 3, source="off", barcode="124")
    repo.update_food(fid2, serving_g=40)
    assert repo.get_food(fid2)["source"] == "off"


def test_update_food_rejects_unknown_fields_and_missing_food(repo):
    fid = repo.add_food("A", 100, 1, 1, 1)
    with pytest.raises(ValueError):
        repo.update_food(fid, source="off")
    with pytest.raises(KeyError):
        repo.update_food(999, name="x")


def test_log_snapshot_survives_food_edits_and_grams_update_rescales(repo):
    fid = repo.add_food("Arroz cocido", 130, 2.7, 28, 0.3)
    lid = repo.add_log("2026-03-01", "lunch", fid, 200)
    row = repo.log_for_date("2026-03-01").iloc[0]
    assert row["kcal"] == pytest.approx(260) and row["carbs_g"] == pytest.approx(56)
    repo.update_food(fid, kcal_100g=999 / 10)  # cambia la ficha después
    assert repo.log_for_date("2026-03-01").iloc[0]["kcal"] == pytest.approx(260)  # historial intacto
    repo.update_log_grams(lid, 100)
    assert repo.log_for_date("2026-03-01").iloc[0]["kcal"] == pytest.approx(130)
    with pytest.raises(ValueError):
        repo.add_log("2026-03-01", "lunch", fid, 0)


def test_daily_totals_only_include_days_with_entries(repo):
    a = repo.add_food("A", 100, 10, 10, 1)
    repo.add_log("2026-03-01", "breakfast", a, 100)
    repo.add_log("2026-03-01", "lunch", a, 300)
    repo.add_log("2026-03-03", "lunch", a, 100)
    t = repo.daily_totals("2026-03-01", "2026-03-31")
    assert list(t.index) == [pd.Timestamp("2026-03-01"), pd.Timestamp("2026-03-03")]
    assert t.loc["2026-03-01", "kcal"] == pytest.approx(400)
    assert t.loc["2026-03-01", "n_entries"] == 2
    assert repo.daily_totals("2027-01-01", "2027-01-31").empty


def test_delete_food_archives_when_used_and_deletes_when_not(repo):
    used = repo.add_food("Usado", 100, 1, 1, 1)
    free = repo.add_food("Libre", 100, 1, 1, 1)
    repo.add_log("2026-03-01", "snack", used, 50)
    assert repo.delete_food(used) == "archived"
    assert repo.delete_food(free) == "deleted"
    assert repo.get_food(free) is None
    assert repo.search_foods("usado") == []                       # archivado: no sale en búsquedas
    assert len(repo.search_foods("usado", include_archived=True)) == 1
    assert len(repo.log_for_date("2026-03-01")) == 1              # el historial se conserva


def test_foreign_keys_are_enforced(repo):
    with pytest.raises(KeyError):
        repo.add_log("2026-03-01", "lunch", 12345, 100)
    with pytest.raises(sqlite3.IntegrityError):
        repo.conn.execute(
            "INSERT INTO food_log (uid, date, meal, food_id, grams, kcal, protein_g, carbs_g, fat_g, created_at)"
            " VALUES ('u', '2026-03-01', 'lunch', 999, 1, 1, 1, 1, 1, 'x')"
        )


def test_day_status_and_target_history(repo):
    repo.set_day_status("2026-03-01", False)
    repo.set_day_status("2026-03-02", True)
    assert repo.day_status_map() == {pd.Timestamp("2026-03-01"): False, pd.Timestamp("2026-03-02"): True}
    repo.set_day_status("2026-03-01", None)
    assert pd.Timestamp("2026-03-01") not in repo.day_status_map()

    repo.set_target("2026-03-01", 2200, 150, 250, 70, "formula", "mifflin_st_jeor")
    repo.set_target("2026-03-15", 2400, 160, 290, 75, "data", "mifflin_st_jeor", "ajuste")
    assert repo.target_on("2026-02-28") is None
    assert repo.target_on("2026-03-10")["kcal"] == 2200
    assert repo.target_on("2026-03-15")["kcal"] == 2400   # vigente desde ese mismo día
    assert repo.target_on("2026-06-01")["tdee_source"] == "data"
    repo.set_target("2026-03-15", 2450, 160, 290, 75, "manual")  # misma fecha: reemplaza
    assert repo.target_on("2026-03-20")["kcal"] == 2450
    assert len(repo.targets_df()) == 2


def test_recent_foods_orders_by_last_use(repo):
    a = repo.add_food("A", 100, 1, 1, 1)
    b = repo.add_food("B", 100, 1, 1, 1)
    repo.add_log("2026-03-01", "snack", a, 10)
    repo.add_log("2026-03-01", "snack", b, 10)
    repo.add_log("2026-03-02", "snack", a, 10)
    assert [f["name"] for f in repo.recent_foods()] == ["A", "B"]
