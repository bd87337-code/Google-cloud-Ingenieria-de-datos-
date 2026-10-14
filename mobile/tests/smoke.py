import sys
sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent))
from harness import Session
SP = sys.argv[1] if len(sys.argv) > 1 else __import__('tempfile').mkdtemp(prefix='mt-shots-')
with Session() as s:
    p = s.open()
    print("sync chip:", p.locator("#sync").inner_text())
    print("tabs:", p.locator(".tab span").all_inner_texts())
    print("vista:", p.locator("#view").inner_text()[:200].replace("\n", " | "))
    p.screenshot(path=f"{SP}/m_hoy_vacio.png")
    print("errores:", s.errors)
