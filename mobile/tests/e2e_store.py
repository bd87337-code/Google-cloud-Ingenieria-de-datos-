"""La nube limita las escrituras por segundo: una ráfaga larga no debe quedar a medias (reintentos con espera creciente)."""
import sys, tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from harness import Session
fails = 0
def check(c, m):
    global fails; print(("  ✔ " if c else "  ✘ ") + m); fails += (not c)
with Session() as s:
    p = s.open()
    p.evaluate("window.__failRate = 0.35")
    r = p.evaluate("""async () => {
      const t0 = Date.now();
      const ids = Array.from({ length: 25 }, (_, i) => 'burst' + i);
      await Promise.all(ids.map((id, i) => S.backend.put('foods', id, { id, name: 'X' + i, kcal: 1, p: 0, c: 0, f: 0, source: 'custom', archived: false, createdAt: i })));
      window.__failRate = 0;
      await new Promise((r) => setTimeout(r, 200));
      return { ms: Date.now() - t0, stored: Object.keys(JSON.parse(localStorage.getItem('__mockdb'))).filter((k) => k.includes('/foods/burst')).length, rejected: window.__mockCalls.rejected };
    }""")
    check(r["rejected"] > 0, f"la simulación sí rechazó escrituras ({r['rejected']})")
    check(r["stored"] == 25, f"las 25 escrituras terminaron guardadas pese a los rechazos: {r['stored']}")
    print(f"  ({r['ms']/1000:.1f} s)")
    # un error que no es de ritmo (p. ej. argumento inválido) no se reintenta
    r2 = p.evaluate("""async () => {
      window.__mockCalls.rejected = 0;
      let code = null, t0 = Date.now();
      try { await S.backend.put('foods', 'bad/id', { id: 'x' }); } catch (e) { code = e && e.code || String(e); }
      return { code, ms: Date.now() - t0 };
    }""")
    print("  error inmediato:", r2)
    check(not s.errors, f"sin errores de consola: {s.errors}")
print("RESULTADO:", "OK" if not fails else f"{fails} fallo(s)"); sys.exit(1 if fails else 0)
