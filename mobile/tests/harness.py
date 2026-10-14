"""Utilidades para probar mobile/macro-tracker.html en Chromium con la simulación de claude."""
import json
from pathlib import Path
from playwright.sync_api import sync_playwright

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
CDN = HERE / ".cdn"          # copia local de las librerías para probar sin depender de la red (gitignored)
LIBS = {"chart.umd.min.js": "https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.min.js",
        "jszip.min.js": "https://cdnjs.cloudflare.com/ajax/libs/jszip/3.10.1/jszip.min.js"}

def ensure_cdn():
    import urllib.request
    CDN.mkdir(exist_ok=True)
    for name, url in LIBS.items():
        if not (CDN / name).exists():
            (CDN / name).write_bytes(urllib.request.urlopen(url, timeout=60).read())

def wrapped_html(body_html: str) -> str:
    """Envuelve el contenido como lo hace la publicación (doctype, viewport, reset mínimo)."""
    return ("<!doctype html><html><head><meta charset=utf8><meta name=viewport content=\"width=device-width,initial-scale=1,viewport-fit=cover\">"
            "<style>:root{color-scheme:light;padding-block:env(safe-area-inset-top,0px) env(safe-area-inset-bottom,0px)}body{margin:0;font:14px system-ui}[hidden]{display:none!important}</style>"
            "</head><body>" + body_html + "</body></html>")

class Session:
    def __init__(self, scheme="light", width=390, height=844, seed=None):
        self.scheme, self.width, self.height, self.seed = scheme, width, height, seed
        self.errors, self.logs = [], []
    def __enter__(self):
        ensure_cdn()
        self.pw = sync_playwright().start()
        self.browser = self.pw.chromium.launch(executable_path="/opt/pw-browsers/chromium", args=["--no-sandbox"])
        self.ctx = self.browser.new_context(viewport={"width": self.width, "height": self.height}, color_scheme=self.scheme, accept_downloads=True)
        if self.seed is not None:   # la semilla debe existir ANTES de que la simulación lea el almacenamiento
            self.ctx.add_init_script(script=f"if(!localStorage.getItem('__mockdb')) localStorage.setItem('__mockdb', {json.dumps(json.dumps(self.seed))});")
        self.ctx.add_init_script(path=str(HERE / "mock_claude.js"))
        def route(r):
            url = r.request.url
            if "chart.umd" in url: return r.fulfill(path=str(CDN / "chart.umd.min.js"), content_type="application/javascript")
            if "jszip" in url: return r.fulfill(path=str(CDN / "jszip.min.js"), content_type="application/javascript")
            return r.abort()   # fuentes y todo lo demás: bloqueado, como en el visor real
        self.ctx.route("**/*", lambda r: route(r) if r.request.url.startswith("http") else r.continue_())
        self.page = self.ctx.new_page()
        self.page.on("pageerror", lambda e: self.errors.append("pageerror: " + str(e)))
        self.page.on("console", lambda m: self.errors.append("console.error: " + m.text) if m.type == "error" and "ERR_FAILED" not in m.text and "Failed to load resource" not in m.text else None)
        html = wrapped_html((ROOT / "macro-tracker.html").read_text(encoding="utf-8"))
        self.page.route("http://app.local/**", lambda r: r.fulfill(body=html, content_type="text/html; charset=utf-8"))
        return self
    def open(self):
        self.page.goto("http://app.local/index.html", wait_until="load"); self.page.wait_for_timeout(500); return self.page
    def __exit__(self, *a):
        self.browser.close(); self.pw.stop()
