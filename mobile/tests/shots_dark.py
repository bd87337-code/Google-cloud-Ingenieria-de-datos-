import sys, json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
SP = sys.argv[1] if len(sys.argv) > 1 else __import__('tempfile').mkdtemp(prefix='mt-shots-')
# reutiliza la semilla de e2e_history ejecutándolo como módulo parcial
src = (Path(__file__).parent / "e2e_history.py").read_text().split("plan = services.build_plan")[0]
ns = {"__file__": __file__, "sys": sys}; sys.argv = [sys.argv[0], SP]
exec(compile(src, "seed", "exec"), ns)
from harness import Session
for scheme in ("light", "dark"):
    with Session(scheme=scheme, seed=ns["seed"]) as s:
        p = s.open()
        for tab in ("today", "progress", "goals"):
            p.locator(f'.tab[data-tab="{tab}"]').click(); p.wait_for_timeout(800)
            p.screenshot(path=f"{SP}/m_{scheme}_{tab}.png", full_page=True)
        p.locator('.tab[data-tab="today"]').click(); p.locator("#fab").click(); p.wait_for_timeout(300)
        p.screenshot(path=f"{SP}/m_{scheme}_sheet.png")
        print(scheme, "errores:", s.errors)
