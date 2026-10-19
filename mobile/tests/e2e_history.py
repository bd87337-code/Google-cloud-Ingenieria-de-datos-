"""Historial de 10 semanas: gráficos, coincidencia numérica con la versión Python y exportar/importar cruzado."""
import io, json, re, sys, tempfile, zipfile
from datetime import date, timedelta
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path(__file__).parent)); sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from harness import Session
from macro_tracker import io_csv, services
from macro_tracker.db.connection import connect
from macro_tracker.db.repository import Repository

SP = sys.argv[1] if len(sys.argv) > 1 else __import__('tempfile').mkdtemp(prefix='mt-shots-')
failures = 0
def check(c, m):
    global failures; print(("  ✔ " if c else "  ✘ ") + m); failures += (not c)

# ---------- semilla común: documentos para la página + base Python equivalente ----------
rng = np.random.default_rng(11)
today = date.today(); days_n = 70; start = today - timedelta(days=days_n)
repo = Repository(connect(":memory:"))
repo.save_profile(sex="M", birth_date="1998-04-10", height_cm=180, activity_level="moderate", goal="lose", rate_kg_week=0.4)
food = repo.add_food("Comida base", 100, 10, 20, 5, uid="f1")                   # 100 kcal/100 g: gramos == kcal
P = "data/users/u_test/"
docs = {P + "profile": dict(sex="M", birth="1998-04-10", heightCm=180, activity="moderate", goal="lose", rate=0.4, pMin=1.6, pMax=2.2, fatMin=0.6, fatPct=0.25, minValidKcal=1000, mifflinOnly=False),
        P + "app/foods/f1": dict(id="f1", name="Comida base", brand=None, kcal=100, p=10, c=20, f=5, servingG=None, servingLabel=None, source="custom", archived=False, createdAt=1)}
for i in range(days_n):
    d = start + timedelta(days=i); doc = {"date": d.isoformat()}
    if rng.random() > 0.15:
        w = round(84.0 - 0.052 * i + rng.normal(0, 0.35), 1); doc["weight"] = w
        bf = {}
        if i % 21 == 0: bf = {"bf": round(20 - i * 0.02, 1), "bfSource": "self_estimate"}; doc.update(bf)
        repo.upsert_body(d, weight_kg=w, **({"body_fat_pct": bf["bf"], "body_fat_source": "self_estimate"} if bf else {}))
    if rng.random() > 0.10:
        total = 2250 + rng.normal(0, 120); parts = [0.3, 0.4, 0.3]; ents = []
        for j, (meal, share) in enumerate(zip(["breakfast", "lunch", "dinner"], parts)):
            g = round(total * share, 1); eid = f"e{i}_{j}"
            ents.append(dict(id=eid, meal=meal, foodId="f1", name="Comida base", brand=None, grams=g, kcal=g, p=g * 0.1, c=g * 0.2, f=g * 0.05, at=1000 + i))
            repo.add_log(d, meal, food, g, uid=eid)
        doc["entries"] = ents
    docs[P + f"app/days/{d.isoformat()}"] = doc
repo.set_target(start, 2250, 176, 230, 70, "formula", "mifflin_st_jeor")
docs[P + f"app/targets/{start.isoformat()}"] = dict(from_=None)
docs[P + f"app/targets/{start.isoformat()}"] = {"from": start.isoformat(), "kcal": 2250, "p": 176, "c": 230, "f": 70, "source": "formula", "bmrMethod": "mifflin_st_jeor", "note": None}
seed = {k: json.dumps(v) for k, v in docs.items()}

plan = services.build_plan(repo); st = services.adaptive_status(repo, plan)
print("Referencia Python → basal %.0f · gasto total %.0f · meta %.0f · por datos %s ± %s (%s)" % (plan.bmr.kcal, plan.tdee_kcal, plan.calories.kcal,
      round(st.data.tdee_kcal) if st.data.ok else None, round(st.data.ci_half_width_kcal) if st.data.ok else None, st.data.confidence))
num = lambda t: float(re.sub(r"[^\d.]", "", t.replace(",", "")))

with Session(seed=seed) as s:
    p = s.open()
    print("1) Metas: números vs versión Python")
    p.locator('.tab[data-tab="goals"]').click(); p.wait_for_timeout(500)
    kp = {k.locator(".l").inner_text(): k for k in p.locator(".kpi").all()}
    check(abs(num(kp["Gasto basal"].locator(".v").inner_text()) - plan.bmr.kcal) < 1, "gasto basal igual al de Python")
    check(abs(num(kp["Gasto total estimado"].locator(".v").inner_text()) - plan.tdee_kcal) < 1, "gasto total igual al de Python")
    check(abs(num(kp["Meta calórica"].locator(".v").inner_text()) - plan.calories.kcal) < 1, "meta calórica igual a la de Python")
    dv = kp["Gasto por datos"].locator(".v").inner_text(); ds = kp["Gasto por datos"].locator(".sub").inner_text()
    check(st.data.ok and abs(num(dv) - st.data.tdee_kcal) < 1, f"gasto por datos igual al de Python ({dv} vs {st.data.tdee_kcal:.0f})")
    check(abs(num(re.search(r"± ([\d,]+)", ds).group(1)) - st.data.ci_half_width_kcal) < 1, f"intervalo de confianza igual al de Python ({ds})")
    check(f"confianza {dict(high='alta', medium='media', low='baja')[st.data.confidence]}" in ds, "misma etiqueta de confianza")
    p.screenshot(path=f"{SP}/m_metas_datos.png", full_page=True)

    print("2) Progreso: gráficos")
    p.locator('.tab[data-tab="progress"]').click(); p.wait_for_timeout(900)
    check(p.locator("canvas").count() == 5, f"5 gráficos dibujados (peso, calorías, gasto, masa magra, % grasa): {p.locator('canvas').count()}")
    drawn = p.evaluate("""() => [...document.querySelectorAll('canvas')].map(c => { const x = c.getContext('2d').getImageData(0, 0, c.width, c.height).data; let n = 0; for (let i = 3; i < x.length; i += 4) if (x[i] > 0) n++; return n; })""")
    check(all(n > 500 for n in drawn), f"todos los lienzos tienen contenido: {drawn}")
    check(p.locator("details summary", has_text="Ver tabla").count() == 4, "cada gráfico tiene su vista de tabla")
    p.screenshot(path=f"{SP}/m_progreso.png", full_page=True)
    p.locator(".chip", has_text="30 días").click(); p.wait_for_timeout(500)
    check(p.locator("canvas").count() >= 4, "el filtro de rango redibuja los gráficos")

    print("3) Exportar -> importar en la versión Python")
    p.locator('.tab[data-tab="data"]').click(); p.wait_for_timeout(300)
    p.get_by_role("button", name="Descargar respaldo (ZIP)").click(); p.wait_for_timeout(1200)
    blob = bytes(p.evaluate("async () => Array.from(new Uint8Array(await window.__dl.data.arrayBuffer()))"))
    names = zipfile.ZipFile(io.BytesIO(blob)).namelist()
    check(set(names) == {"manifest.json", *[f"{t}.csv" for t in io_csv.TABLES], "water_log.csv", "exercise_log.csv"}, "el ZIP trae las 8 tablas compatibles con escritorio + agua y ejercicio + manifest")
    other = Repository(connect(":memory:")); rep = io_csv.import_zip(other, blob, "replace")
    check(rep.counts["food_log"] == repo.conn.execute("select count(*) from food_log").fetchone()[0], f"entradas de comida importadas en Python: {rep.counts['food_log']}")
    a, b = repo.daily_totals()["kcal"], other.daily_totals()["kcal"]
    check(len(a) == len(b) and np.allclose(a.to_numpy(), b.to_numpy(), atol=1e-6), "totales diarios idénticos tras el viaje JS → CSV → Python")
    wa, wb = repo.body_df()["weight_kg"].dropna(), other.body_df()["weight_kg"].dropna()
    check(len(wa) == len(wb) and np.allclose(wa.to_numpy(), wb.to_numpy()), "pesos idénticos")
    check(other.get_profile()["height_cm"] == 180 and len(other.targets_df()) == 1, "perfil y metas importados")

with Session() as s2:   # base vacía: importar lo que exporta la versión Python
    p = s2.open(); print("4) Exportar desde Python -> importar en la página")
    z = io_csv.export_zip(repo); f = Path(tempfile.mkdtemp()) / "respaldo.zip"; f.write_bytes(z)
    p.locator('.tab[data-tab="data"]').click(); p.wait_for_timeout(300)
    p.set_input_files("#upload", str(f))
    p.get_by_role("button", name="Reemplazar todo").click(); p.locator("#confirm-replace").check()
    p.get_by_role("button", name="Importar", exact=True).click(); p.wait_for_timeout(4000)
    txt = p.locator("#view").inner_text()
    check("Importación completada" in txt, "importación del ZIP de Python completada")
    got = p.evaluate("({days: Object.keys(S.days).length, entries: Object.values(S.days).reduce((s,d)=>s+(d.entries||[]).length,0), foods: Object.keys(S.foods).length, targets: S.targets.length, prof: !!S.profile, sync: document.getElementById('sync').textContent})")
    exp_days = len({k for k in docs if "/days/" in k and ("weight" in docs[k] or "entries" in docs[k])})
    check(got["entries"] == repo.conn.execute("select count(*) from food_log").fetchone()[0], f"entradas de comida en la página: {got['entries']}")
    check(got["days"] == exp_days and got["foods"] == 1 and got["targets"] == 1 and got["prof"], f"días={got['days']} (esperados {exp_days}), alimentos, meta y perfil: {got}")
    tot = p.evaluate("(() => { const k = Object.keys(S.days).sort()[10]; return [k, (S.days[k].entries||[]).reduce((s,e)=>s+e.kcal,0)]; })()")
    pyt = repo.daily_totals().loc[tot[0], "kcal"]
    check(abs(tot[1] - pyt) < 1e-6, f"total del día {tot[0]} igual: {tot[1]:.1f} vs {pyt:.1f}")
    print("5) Importación inválida: todo o nada")
    bad = Path(tempfile.mkdtemp()) / "body_log.csv"; bad.write_text("date,weight_kg\n2026-01-01,80\nno-es-fecha,80\n2026-01-03,-5\n")
    before = p.evaluate("Object.keys(S.days).length")
    p.set_input_files("#upload", str(bad)); p.get_by_role("button", name="Combinar").click()
    p.get_by_role("button", name="Importar", exact=True).click(); p.wait_for_timeout(800)
    txt = p.locator("#view").inner_text()
    check("cancelada" in txt and "fila 3" in txt and "fila 4" in txt, "reporta tabla, fila y columna de cada error")
    check(p.evaluate("Object.keys(S.days).length") == before, "no se escribió nada")
    check(not s2.errors, f"sin errores de consola: {s2.errors}")
print("\nRESULTADO:", "OK" if not failures else f"{failures} fallo(s)")
sys.exit(1 if failures else 0)
