# Macro Tracker para celular

Versión de **una sola página** (`macro-tracker.html`) pensada para el celular. Se publica como *Artifact* de
claude.ai y se abre desde la app de Claude; no hay que instalar nada ni tener la computadora encendida.

- **Datos:** se guardan en la cuenta de Claude de quien la abre, en una zona privada por usuario
  (`data/users/<id>/…`) y se sincronizan entre dispositivos. Si esa API no estuviera disponible, la página
  cae a `localStorage` y avisa («Solo en este navegador»).
- **Qué comparte con la versión de escritorio:** los mismos cálculos (portados a JavaScript y **validados
  contra la implementación Python**, ver abajo) y el mismo formato de CSV/ZIP: se puede exportar en una y
  importar en la otra.
- **Qué no tiene:** Open Food Facts ni escáner de código de barras (una página publicada no puede salir a internet
  ni usar la cámara en vivo). A cambio:
  - **Base inicial** de 97 alimentos básicos (tortilla, frijol, pollo, huevo, queso fresco, frutas, verduras…) de
    **USDA FoodData Central (SR Legacy, dominio público)**, cada uno con su número de registro (`fdc`) para poder
    verificarlo. Se regenera con `mobile/seed/build_seed.py`. Son valores genéricos: marcas y recetas propias pueden diferir.
    Viven **en el código** (no se escriben en la base de datos): están disponibles al abrir y no consumen escrituras.
    Si editas uno se guarda tu versión (que manda sobre el catálogo); «borrar» un alimento incluido lo oculta.
  - **Registro por texto o foto con IA**: Claude estima calorías y macros; el usuario corrige gramos antes de guardar.
    Las entradas quedan marcadas «estimado», se avisa qué % del día es estimado y, si pasa de 30 % de una ventana de
    análisis, se advierte que sesga a la baja el gasto «por datos». Se validan las respuestas (descarta lo imposible
    y fuerza coherencia kcal ↔ macros).
  - **Foto de la etiqueta nutrimental**: lee los números impresos y los convierte a valores por 100 g.
  - **Agua** y **ejercicio** (el ejercicio es solo referencia: no se suma a la meta calórica).
  - **Hoy**: cuatro comidas, cada una con su «+» (preselecciona la comida); si una comida está vacía ofrece
    «↻ Repetir el de ayer» (o el último día, hasta 7 días atrás) y los borrados/repeticiones se pueden deshacer.
    La cámara está en el centro de la barra inferior, no flota sobre el contenido.
  - **Escrituras a la nube**: una sola a la vez y con reintentos de espera creciente cuando la plataforma pide ir más
    despacio (`resource_exhausted`); `tests/e2e_store.py` lo simula.

## Estructura

```
src/calc.js       Cálculos puros (BMR, metas, macros, series con huecos, gasto por datos con IC al 95 %)
src/store.js      Persistencia: db de Claude (nube) con respaldo en localStorage
src/app-core.js   Estado, ayudantes de interfaz, plan de metas
src/view-*.js     Pantallas: Hoy, Alimentos, Metas, Progreso, Datos (CSV/ZIP); view-ai.js: IA, etiqueta, agua, ejercicio
src/seed-foods.js Base inicial (generada)   seed/build_seed.py  Generador desde USDA
src/boot.js       Arranque
src/style.css     Estilos (claro/oscuro)         src/page.html   Plantilla
build.py          Ensambla todo en macro-tracker.html (lo que se publica)
tests/            Pruebas (ver abajo)
```

## Reconstruir y probar

```bash
python3 mobile/build.py                                   # genera macro-tracker.html
.venv/bin/python mobile/tests/gen_fixtures.py             # resultados de referencia de la versión Python
node --test mobile/tests/calc.test.mjs mobile/tests/ai.test.mjs   # el port JS reproduce a Python; validación de IA y base USDA
.venv/bin/pip install playwright                          # una vez; usa el Chromium ya instalado
.venv/bin/python mobile/tests/e2e_flow.py                 # perfil → alimentos y receta → registro → recarga
.venv/bin/python mobile/tests/e2e_history.py              # 10 semanas: gráficos, números vs Python, CSV en ambos sentidos
.venv/bin/python mobile/tests/e2e_features.py             # base USDA, IA por texto/foto, etiqueta, agua, ejercicio, CSV
.venv/bin/python mobile/tests/e2e_today.py                # Hoy: comidas con «+», repetir, deshacer, cámara en la barra
.venv/bin/python mobile/tests/e2e_store.py                # ráfaga de escrituras con rechazos simulados: todas terminan guardadas
.venv/bin/python mobile/tests/layout_check.py             # formularios sin encimarse (peor caso de Safari)
```

Las pruebas de navegador usan `tests/mock_claude.js`, una simulación de `window.claude` (db, user, sample,
downloads) con la misma forma que la API real. **Esa simulación no es la API real**: lo que no se puede probar
fuera de claude.ai es el comportamiento exacto de la `db` real (límites de tasa, reglas de acceso) y de los
permisos que pide Claude al estimar macros o descargar.

## Criterios de diseño aplicados

Revisión de interfaz hecha con criterios de dos guías públicas de diseño, usadas solo como lista de verificación
(no se instalaron ni se copió su contenido): [emilkowalski/skills](https://github.com/emilkowalski/skills) (MIT; en
especial *mobile-native* y los principios de animación) e [Impeccable](https://github.com/pbakaus/impeccable)
(Apache 2.0; modo «Operate» para interfaces de uso diario). Concretamente: sin flash gris al tocar, `:active` con
respuesta inmediata (100–140 ms, ease-out), `touch-action: manipulation`, texto de controles no seleccionable,
iconos dibujados en lugar de glifos, una sola familia tipográfica en cifras y etiquetas, esqueleto de carga en
vez de spinner, hojas con entrada breve (y sin animación con «reducir movimiento»), contraste ≥ 4.5:1 en texto
(el botón primario claro subió de 4.42 a 5.39).
