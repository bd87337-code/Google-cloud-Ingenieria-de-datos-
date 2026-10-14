"""Ensambla mobile/src en un solo archivo: mobile/macro-tracker.html (el que se publica como Artifact)."""
from pathlib import Path
src = Path(__file__).parent / "src"
order = ["calc.js", "store.js", "app-core.js", "view-today.js", "view-foods.js", "view-goals.js", "view-progress.js", "view-data.js", "boot.js"]
js = "\n".join((src / f).read_text(encoding="utf-8") for f in order)
assert "</script" not in js.lower(), "el JS no puede contener </script"
page = (src / "page.html").read_text(encoding="utf-8").replace("/*__CSS__*/", (src / "style.css").read_text(encoding="utf-8")).replace("/*__JS__*/", js)
out = Path(__file__).parent / "macro-tracker.html"
out.write_text(page, encoding="utf-8")
print(f"{out.name}: {len(page.encode()) / 1024:.0f} KB")
