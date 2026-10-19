"""Revisa que la pantalla de Metas no se encime ni dependa de flex/gap dentro de <details> (Safari no lo aplica)."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from harness import Session
SP = sys.argv[1] if len(sys.argv) > 1 else "/tmp"
fails = 0
def check(c, m):
    global fails; print(("  ✔ " if c else "  ✘ ") + m); fails += (not c)
for w in (390, 360):
    with Session(width=w) as s:
        p = s.open(); p.locator('.tab[data-tab="goals"]').click(); p.wait_for_timeout(400)
        # peor caso: Safari sin gap dentro de <details>
        p.add_style_tag(content="details.card { gap: 0 !important; row-gap: 0 !important; }")   # Safari ignora el gap del <details>; el de las rejillas internas sí funciona
        print(f"Ancho {w}px")
        d = p.locator('details.card').first
        kids = d.evaluate("""el => [...el.children].filter(k => getComputedStyle(k).display !== 'none').map(k => { const r = k.getBoundingClientRect(); return {tag: k.tagName + '.' + k.className, top: r.top, bottom: r.bottom}; })""")
        gaps = [kids[i + 1]["top"] - kids[i]["bottom"] for i in range(len(kids) - 1)]
        check(min(gaps) >= 10, f"separación mínima entre bloques del formulario: {min(gaps):.0f}px (≥ 10)")
        birth, height = p.get_by_label("Fecha de nacimiento").bounding_box(), p.get_by_label("Estatura (cm)").bounding_box()
        check(birth["x"] + birth["width"] <= height["x"] + 0.5, f"fecha no se encima con estatura (fecha termina en {birth['x'] + birth['width']:.0f}, estatura empieza en {height['x']:.0f})")
        over = p.evaluate("document.documentElement.scrollWidth > window.innerWidth + 1")
        check(not over, "sin desplazamiento horizontal de la página")
        outside = p.evaluate("""() => [...document.querySelectorAll('#view input, #view select')].filter(e => { const r = e.getBoundingClientRect(); return r.width > 0 && (r.right > window.innerWidth + 1 || r.left < -1); }).length""")
        check(outside == 0, "ningún campo se sale de la pantalla")
        p.screenshot(path=f"{SP}/m_metas_{w}.png")
        check(not s.errors, f"sin errores de consola: {s.errors}")
print("RESULTADO:", "OK" if not fails else f"{fails} fallo(s)"); sys.exit(1 if fails else 0)
