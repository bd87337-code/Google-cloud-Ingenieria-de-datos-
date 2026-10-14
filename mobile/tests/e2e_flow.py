"""Flujo completo de uso: perfil -> alimentos y receta propios -> registro -> edición -> recarga."""
import sys, json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from harness import Session
SP = sys.argv[1] if len(sys.argv) > 1 else __import__('tempfile').mkdtemp(prefix='mt-shots-')
ok = lambda c, m: (print(("  ✔ " if c else "  ✘ ") + m), c)[1]
failures = 0
def check(c, m):
    global failures
    if not ok(c, m): failures += 1

def sheet_save(p, name="Guardar"):
    p.locator(".sheet").get_by_role("button", name=name, exact=True).click(); p.wait_for_timeout(250)

with Session() as s:
  p = s.open()
  try:
      print("1) Perfil")
      p.locator('.tab[data-tab="goals"]').click(); p.wait_for_timeout(200)
      p.get_by_label("Fecha de nacimiento").fill("2000-01-15"); p.get_by_label("Estatura (cm)").fill("180")
      p.get_by_label("Nivel de actividad").select_option("moderate"); p.get_by_label("Objetivo", exact=True).select_option("lose"); p.get_by_label("Ritmo (kg/semana)").fill("0.4")
      p.get_by_label("Peso (kg)", exact=True).fill("80"); p.get_by_label("% de grasa (opcional)").fill("18")
      p.get_by_role("button", name="Guardar perfil").click(); p.wait_for_timeout(500)
      txt = p.locator("#view").inner_text()
      check("Katch-McArdle" in txt, "indica el método usado (Katch-McArdle por haber % de grasa)")
      check("estimación tuya" in txt, "avisa que el % de grasa es una estimación propia")
      check("Sin datos" in txt and "Días con comida registrada" in txt, "adaptación: no muestra número y dice qué falta")
      keys = p.evaluate("Object.keys(JSON.parse(localStorage.getItem('__mockdb')))")
      check(any("/app/targets/" in k for k in keys), "se creó la meta inicial automáticamente")
      check(any(k.endswith("/profile") for k in keys), "perfil guardado en la ruta privada del usuario (data/users/<id>/profile)")
      p.screenshot(path=f"{SP}/m_metas.png", full_page=True)

      print("2) Alimentos y receta propios")
      p.locator('.tab[data-tab="foods"]').click(); p.wait_for_timeout(200)
      for name, k, pr, c, f, sg, sl in [("Tortilla de maíz", 218, 5.7, 44.6, 2.8, 30, "1 tortilla"), ("Frijoles de la olla", 100, 6.5, 17, 0.8, None, None), ("Queso Oaxaca", 300, 22, 2, 23, None, None)]:
          p.get_by_role("button", name="+ Alimento").click(); p.wait_for_timeout(150)
          sh = p.locator(".sheet")
          sh.get_by_label("Nombre", exact=True).fill(name); sh.get_by_label("Calorías (kcal)").fill(str(k)); sh.get_by_label("Proteína (g)").fill(str(pr)); sh.get_by_label("Carbohidratos (g)").fill(str(c)); sh.get_by_label("Grasa (g)").fill(str(f))
          if sg: sh.get_by_label("Porción habitual (g)").fill(str(sg)); sh.get_by_label("Descripción de la porción").fill(sl)
          sheet_save(p)
      check("Tortilla de maíz" in p.locator("#view").inner_text() and "Queso Oaxaca" in p.locator("#view").inner_text(), "los 3 alimentos aparecen en la lista")
      p.get_by_role("button", name="+ Alimento").click(); sh = p.locator(".sheet")
      sh.get_by_label("Nombre", exact=True).fill("Raro"); sh.get_by_label("Calorías (kcal)").fill("1200"); sheet_save(p)
      check("900" in p.locator(".sheet").inner_text(), "rechaza un alimento imposible (>900 kcal por 100 g)")
      p.locator(".sheet").get_by_role("button", name="Cerrar").click()
      p.get_by_role("button", name="+ Receta").click(); sh = p.locator(".sheet"); sh.get_by_label("Nombre de la receta").fill("Tacos de frijol")
      for q, g in [("tortilla", "90"), ("frijoles", "80"), ("oaxaca", "30")]:
          sh.get_by_label("Buscar ingrediente").fill(q); p.wait_for_timeout(100); sh.locator(".list .row").first.click(); sh.get_by_label("Gramos (peso crudo)").fill(g)
          sh.get_by_role("button", name="Agregar", exact=True).click(); p.wait_for_timeout(100)
      sh.get_by_label("Porciones que rinde").fill("2")
      prev = sh.locator(".sub.num").inner_text()
      exp_kcal = (218*.9 + 100*.8 + 300*.3) / 200 * 100
      check(f"{round(exp_kcal)} kcal" in prev, f"vista previa de la receta por 100 g = {round(exp_kcal)} kcal (a mano): «{prev[:60]}…»")
      p.screenshot(path=f"{SP}/m_receta.png")
      sheet_save(p, "Guardar receta")
      check("Tacos de frijol" in p.locator("#view").inner_text(), "la receta aparece como alimento")

      print("3) Registro")
      p.locator('.tab[data-tab="today"]').click(); p.wait_for_timeout(200)
      p.locator("#fab").click(); p.wait_for_timeout(150)
      sh = p.locator(".sheet"); sh.get_by_label("Buscar alimento").fill("TORTILLA"); p.wait_for_timeout(100)
      check(sh.locator(".list .row").count() >= 1, "búsqueda sin distinguir mayúsculas")
      sh.locator(".list .row").first.click(); p.wait_for_timeout(100)
      sh.get_by_role("button", name="Porciones").click(); sh.get_by_label("Porciones").fill("3")
      check("196" in sh.locator(".sub.num").inner_text(), "3 porciones de 30 g = 90 g → 196 kcal")
      sh.get_by_role("button", name="Agregar", exact=True).click(); p.wait_for_timeout(300)
      p.locator("#fab").click(); sh = p.locator(".sheet"); sh.get_by_label("Buscar alimento").fill("tacos"); p.wait_for_timeout(100); sh.locator(".list .row").first.click()
      sh.get_by_role("button", name="Agregar", exact=True).click(); p.wait_for_timeout(300)
      v = p.locator("#view").inner_text()
      check("Tortilla de maíz" in v and "Tacos de frijol" in v, "ambas entradas aparecen en el registro")
      check("%" in v and "Te faltan" in v, "barra de progreso y calorías restantes contra la meta")
      p.screenshot(path=f"{SP}/m_hoy_con_datos.png", full_page=True)
      p.get_by_role("button", name=__import__("re").compile("Tortilla de maíz")).first.click(); p.wait_for_timeout(150)
      p.locator(".sheet").get_by_label("Cantidad (g)").fill("120"); sheet_save(p); 
      check("120 g" in p.locator("#view").inner_text(), "editar la cantidad de una entrada")

      print("4) Persistencia: recargar la página")
      p.reload(wait_until="load"); p.wait_for_timeout(600)
      v = p.locator("#view").inner_text()
      check("Tortilla de maíz" in v and "120 g" in v, "los datos siguen ahí tras recargar")
      check(p.locator("#sync").inner_text() == "Guardado en tu cuenta", "indicador de guardado")
      print("errores de consola/JS:", s.errors or "ninguno")
      check(not s.errors, "sin errores de consola ni excepciones")
  except Exception as e:
    print('\n!! EXCEPCIÓN:', str(e).splitlines()[0])
    print('hoja abierta:', p.locator('.sheet').first.inner_text().replace('\n',' | ')[:500] if p.locator('.sheet').count() else '(ninguna)')
    print('vista:', p.locator('#view').inner_text().replace('\n',' | ')[:400])
    p.screenshot(path=SP + '/m_fallo.png'); failures += 1
print("\nRESULTADO:", "OK" if not failures else f"{failures} fallo(s)")
sys.exit(1 if failures else 0)
