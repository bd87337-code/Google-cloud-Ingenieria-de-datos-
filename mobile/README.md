# Macro Tracker para celular

Versión de **una sola página** (`macro-tracker.html`) pensada para el celular. Se publica como *Artifact* de
claude.ai y se abre desde la app de Claude; no hay que instalar nada ni tener la computadora encendida.

- **Datos:** se guardan en la cuenta de Claude de quien la abre, en una zona privada por usuario
  (`data/users/<id>/…`) y se sincronizan entre dispositivos. Si esa API no estuviera disponible, la página
  cae a `localStorage` y avisa («Solo en este navegador»).
- **Qué comparte con la versión de escritorio:** los mismos cálculos (portados a JavaScript y **validados
  contra la implementación Python**, ver abajo) y el mismo formato de CSV/ZIP: se puede exportar en una y
  importar en la otra.
- **Qué no tiene:** Open Food Facts (una página publicada no puede salir a internet). A cambio, al crear un
  alimento se puede pedir a Claude una estimación de macros, que queda marcada como «estimado por IA».

## Estructura

```
src/calc.js       Cálculos puros (BMR, metas, macros, series con huecos, gasto por datos con IC al 95 %)
src/store.js      Persistencia: db de Claude (nube) con respaldo en localStorage
src/app-core.js   Estado, ayudantes de interfaz, plan de metas
src/view-*.js     Pantallas: Hoy, Alimentos, Metas, Progreso, Datos (CSV/ZIP)
src/boot.js       Arranque
src/style.css     Estilos (claro/oscuro)         src/page.html   Plantilla
build.py          Ensambla todo en macro-tracker.html (lo que se publica)
tests/            Pruebas (ver abajo)
```

## Reconstruir y probar

```bash
python3 mobile/build.py                                   # genera macro-tracker.html
.venv/bin/python mobile/tests/gen_fixtures.py             # resultados de referencia de la versión Python
node --test mobile/tests/calc.test.mjs                    # el port JS reproduce a Python número por número
.venv/bin/pip install playwright                          # una vez; usa el Chromium ya instalado
.venv/bin/python mobile/tests/e2e_flow.py                 # perfil → alimentos y receta → registro → recarga
.venv/bin/python mobile/tests/e2e_history.py              # 10 semanas: gráficos, números vs Python, CSV en ambos sentidos
```

Las pruebas de navegador usan `tests/mock_claude.js`, una simulación de `window.claude` (db, user, sample,
downloads) con la misma forma que la API real. **Esa simulación no es la API real**: lo que no se puede probar
fuera de claude.ai es el comportamiento exacto de la `db` real (límites de tasa, reglas de acceso) y de los
permisos que pide Claude al estimar macros o descargar.
