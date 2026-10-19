"""Pantalla «Hoy»: comidas con su «+», repetir una comida, deshacer, hueco para los botones de la app y botón de foto."""
import sys, tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent)); sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from harness import Session

SP = sys.argv[1] if len(sys.argv) > 1 else tempfile.mkdtemp(prefix="mt-shots-")
fails = 0
def check(c, m):
    global fails; print(("  ✔ " if c else "  ✘ ") + m); fails += (not c)

with Session() as s:
    p = s.open()
    txt = lambda: p.locator("#view").inner_text()
    print("1) Estructura")
    check(all(m in txt() for m in ("Desayuno", "Comida", "Cena", "Colación")), "las cuatro comidas siempre están a la vista")
    check(p.get_by_role("button", name="Agregar a Cena").is_visible(), "cada comida tiene su «+»")
    check(p.locator("#fab").count() == 0 and p.locator("#tabs #fab-photo").is_visible(), "la cámara vive en la barra inferior; no hay botones flotantes sobre el contenido")
    top = p.evaluate("document.querySelector('.top .brand').getBoundingClientRect().top")
    check(top >= 48, f"el encabezado queda debajo de los botones ✕/⋯ de la app (y={top:.0f}px)")
    fab = p.locator("#fab-photo").bounding_box()
    bar = p.locator("#tabs").bounding_box()
    check(fab["y"] + fab["height"] <= bar["y"] + bar["height"] + 0.5 and fab["x"] > 100 and fab["x"] + fab["width"] < 290, f"el botón de foto queda al centro de la barra (x={fab['x']:.0f}, y={fab['y']:.0f})")
    p.locator('.tab[data-tab="goals"]').click(); p.wait_for_timeout(200)
    check(p.locator("#fab-photo").is_visible(), "la cámara sigue disponible en las demás pestañas")
    p.locator('.tab[data-tab="today"]').click(); p.wait_for_timeout(200)

    print("2) «+» de una comida preselecciona esa comida")
    p.get_by_role("button", name="Agregar a Cena").click(); sh = p.locator(".sheet")
    sh.get_by_placeholder("Buscar: tortilla, frijoles, pechuga…").fill("huevo"); p.wait_for_timeout(120)
    sh.locator(".list .row").first.click(); p.wait_for_timeout(100)
    check(sh.get_by_label("Comida").input_value() == "dinner", "la lista de comidas ya trae «Cena»")
    sh.get_by_role("button", name="Agregar", exact=True).click(); p.wait_for_timeout(300)
    meals = p.evaluate("(S.days[S.date].entries||[]).map(e => e.meal)")
    check(meals == ["dinner"], f"se guardó en la cena: {meals}")

    print("3) Repetir una comida (ayer → hoy) y deshacer")
    yday = p.evaluate("addDays(S.date, -1)")
    p.evaluate("""(y) => saveDay(y, d => { d.entries = [
      {id:'a1', meal:'breakfast', foodId:'usda-175036', name:'Tortilla de maíz', brand:null, grams:72, kcal:157, p:4, c:32, f:2, at:1},
      {id:'a2', meal:'breakfast', foodId:'nope', name:'Estimado IA', brand:null, grams:100, kcal:200, p:10, c:20, f:8, at:2, est:true}]; })""", yday)
    p.wait_for_timeout(400)
    btn = p.get_by_role("button", name="Repetir el de ayer")
    check(btn.count() == 1 and "kcal" in btn.inner_text(), f"el desayuno vacío ofrece repetir el de ayer: «{btn.first.inner_text() if btn.count() else ''}»")
    check(p.get_by_role("button", name=__import__("re").compile("^Repetir")).count() == 1, "solo las comidas vacías con antecedente lo ofrecen")
    btn.click(); p.wait_for_timeout(400)
    es = p.evaluate("S.days[S.date].entries.filter(e => e.meal === 'breakfast')")
    check(len(es) == 2 and len({e['id'] for e in es}) == 2 and all(e['id'] not in ('a1', 'a2') for e in es), "copia con ids nuevos")
    check(any(e.get("est") for e in es), "lo estimado por IA conserva su marca «estimado»")
    check(p.get_by_role("button", name="Deshacer").is_visible(), "ofrece «Deshacer»")
    p.get_by_role("button", name="Deshacer").click(); p.wait_for_timeout(400)
    check(p.evaluate("S.days[S.date].entries.filter(e => e.meal === 'breakfast').length") == 0, "«Deshacer» quita lo repetido")
    check(p.evaluate("S.days[S.date].entries.length") == 1, "…y no toca el resto del día")

    print("4) Borrar una entrada y deshacer")
    p.get_by_role("button", name="Huevo", exact=False).first.click(); p.wait_for_timeout(150)
    p.locator(".sheet").get_by_role("button", name="Borrar", exact=True).click(); p.wait_for_timeout(300)
    check(p.evaluate("(S.days[S.date]||{}).entries?.length || 0") == 0, "se borró")
    p.get_by_role("button", name="Deshacer").click(); p.wait_for_timeout(300)
    check(p.evaluate("S.days[S.date].entries.length") == 1, "«Deshacer» la devuelve")

    print("5) Agua compacta")
    r = p.evaluate("""[...document.querySelectorAll('.btn-row.tight .btn')].map(b => b.getBoundingClientRect().top)""")
    check(len(r) >= 3 and max(r) - min(r) < 2, "los botones de agua caben en una sola fila")
    p.screenshot(path=f"{SP}/m_hoy_nuevo.png", full_page=True)
    check(not s.errors, f"sin errores de consola: {s.errors}")
print("RESULTADO:", "OK" if not fails else f"{fails} fallo(s)"); sys.exit(1 if fails else 0)
