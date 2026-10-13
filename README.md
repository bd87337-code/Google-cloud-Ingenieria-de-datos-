# Macro Tracker

App **local** para registrar calorías y macros, con gráficos, que ajusta tus metas según tu composición
corporal y según cómo responde tu peso en la práctica. Sin cuentas ni servicios de pago.

- **Stack:** Python 3.11+, Streamlit (interfaz), SQLite (datos), Plotly (gráficos).
- **Todo en tu computadora.** El único acceso a internet es la consulta a Open Food Facts cuando buscas un
  alimento que no tienes guardado.

## Qué hace

| Página | Para qué sirve |
|---|---|
| **Hoy** | Registrar alimentos (gramos o porciones), peso y medidas. Calorías vs. meta (barra de progreso) y macros (barras + dona). |
| **Progreso** | Peso diario con promedio móvil de 7 días, calorías por semana, gasto estimado por datos vs. por fórmula, % de grasa y masa magra. Un filtro de fechas gobierna todos los gráficos; cada gráfico tiene su tabla de datos. |
| **Alimentos y recetas** | Crear alimentos propios y recetas (obligatorio para comida mexicana: la cobertura en bases públicas es pobre), editar, archivar. |
| **Perfil y metas** | Perfil, meta por fórmula (indica qué método usa), y adaptación con tus datos reales. |
| **Datos** | Exportar e importar todo en CSV. |

Búsqueda de alimentos: **tabla local primero**; si no hay resultado, **Open Food Facts** (con filtro opcional de
México); todo lo encontrado se **guarda en caché** local.

## Instalación

Requiere **Python 3.11 o superior**.

```bash
git clone <este-repositorio> && cd <carpeta>
python3 -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

## Ejecución

```bash
streamlit run app.py
```

Se abre en <http://localhost:8501>. La base de datos se crea sola en `data/tracker.db` (está en `.gitignore`).
Para usar otra ubicación: `MACRO_TRACKER_DB=/ruta/mi.db streamlit run app.py`.

### Primer uso recomendado

1. **Perfil y metas** → llena el perfil y tu peso actual → «Guardar perfil» → «Establecer como meta vigente».
2. **Alimentos y recetas** → crea tus alimentos habituales (tortilla, frijoles…) y tus recetas.
3. **Hoy** → registra comida; pésate cuando puedas (no hace falta todos los días).
4. Tras ~2 semanas, **Perfil y metas** → «Adaptación con tus datos».

### Pruebas

```bash
pip install -r requirements-dev.txt
pytest
```

Cubren los cálculos (BMR, metas, macros, series con huecos, gasto por datos y su intervalo de confianza,
incluida una simulación que comprueba la cobertura del IC al 95 %), la base de datos, la caché de Open Food
Facts (con respuestas reales guardadas como fixtures y fallos de red simulados), las recetas, el ciclo
exportar→importar y las páginas de la interfaz.

## Estructura

```
app.py                       Entrada de Streamlit (navegación)
.streamlit/config.toml       Dos temas (claro/oscuro) y telemetría desactivada
macro_tracker/
  config.py                  Constantes y umbrales (7700 kcal/kg, factores de actividad, mínimos de datos…)
  calc/                      Funciones puras, sin SQLite ni Streamlit (lo que se prueba más a fondo)
    bmr.py  targets.py  body_comp.py  series.py  adaptive.py  nutrition.py
  db/                        schema.sql, connection.py (migraciones), repository.py (único SQL de la app)
  foods/                     off_client.py, service.py (local → OFF → caché), recipes.py
  services.py                Pegamento DB → cálculos (series diarias con huecos, plan, adaptación)
  io_csv.py                  Exportar/importar
  ui/                        components.py, charts.py, state.py y pages/
tests/                       Pruebas unitarias y de interfaz
```

## Datos, respaldo y privacidad

- Todo vive en un único archivo SQLite. Para respaldarlo, usa **Datos → Descargar todo (ZIP)** o copia el archivo.
- La telemetría de Streamlit está desactivada en `.streamlit/config.toml`.
- Las únicas peticiones de red van a `world.openfoodfacts.org`, con el texto que buscas y sin ningún dato personal.
  Open Food Facts limita la tasa de peticiones (las búsquedas por texto son las más restringidas) y a veces
  responde vacío o tarda; la app busca solo al pulsar «Buscar», nunca mientras escribes, y si la consulta falla
  te lo dice y sigue funcionando con tu base local.
- Open Food Facts es colaborativo y tiene errores. La app descarta productos con datos incompletos o imposibles y
  marca con ⚠ los que declaran calorías que no cuadran con sus macros (4·P + 4·C + 9·G, tolerancia 15 %).

### Formato CSV

«Descargar todo» entrega un ZIP con un CSV por tabla (`profile`, `body_log`, `foods`, `recipes`, `recipe_items`,
`food_log`, `day_status`, `targets`) más `manifest.json`. UTF-8 con BOM (acentos correctos en Excel); los valores
faltantes son celdas vacías, nunca 0. Los alimentos y el diario se enlazan por un `uid` estable, no por el id
numérico, de modo que puedes **combinar** respaldos de dos computadoras sin colisiones.

La importación es **todo o nada**: valida cada fila (fechas, rangos, valores permitidos, referencias) y, si hay
cualquier error, no guarda nada y te dice la tabla, la fila y la columna. Modos: *combinar* (agrega lo nuevo y
actualiza lo existente; gana lo importado) o *reemplazar*. Acepta coma decimal por si Excel regional reescribió
el archivo.

---

## Fórmulas y limitaciones

Esta sección importa más que el resto: la app produce números con aspecto preciso a partir de supuestos que no lo
son. Aquí se dice cuáles.

### 1. Gasto basal (BMR)

- **Mifflin-St Jeor** (si no hay % de grasa):
  `BMR = 10·peso(kg) + 6.25·estatura(cm) − 5·edad + 5` (hombres) o `− 161` (mujeres).
- **Katch-McArdle** (si hay % de grasa): `BMR = 370 + 21.6 · masa magra(kg)`, con
  `masa magra = peso · (1 − %grasa/100)`.

La interfaz indica siempre cuál se está usando.

**Limitaciones.** Ambas son regresiones sobre poblaciones; el error individual típico es de ±10 % o más.
Katch-McArdle *parece* más preciso porque usa composición corporal, pero toma tu % de grasa como un hecho: si ese
dato es una estimación a ojo, el cálculo hereda su error (cada punto porcentual mueve el basal ≈ 0.2 kcal por cada
kg de peso, p. ej. ≈ 17–19 kcal para 80–88 kg). Por eso cada % de grasa lleva su **origen** (medido, estimado por
ti, o fórmula Navy), la app avisa cuando es una estimación tuya, y existe la opción «Usar siempre Mifflin-St Jeor».

### 2. Gasto total y meta calórica

- `Gasto total estimado = BMR × factor de actividad` (1.2 sedentario · 1.375 ligero · 1.55 moderado · 1.725 activo ·
  1.9 muy activo).
- `Meta = gasto total + ajuste`, con `ajuste = ± ritmo(kg/sem) × 7700 / 7` (perder: negativo; ganar: positivo;
  mantener: 0).
- **Piso:** la meta nunca baja del BMR estimado. Si el ritmo elegido lo exigiría, la app muestra una advertencia
  con el ritmo que realmente se logra con ese piso.

**Limitaciones.** El factor de actividad es el supuesto más débil de toda la cadena: las categorías son subjetivas
y el gasto real por actividad varía enormemente entre personas con el mismo nivel declarado. Es la razón de ser de
la sección de adaptación. El piso en el BMR es una **heurística**, no un límite clínico ni una recomendación médica.

### 3. Macros

- **Proteína:** rango configurable de 1.6–2.2 g/kg (valores de la literatura de entrenamiento de fuerza). El objetivo
  puntual es el extremo alto al perder grasa (protege masa magra) y el punto medio en otro caso.
  - Con % de grasa registrado, los g/kg se aplican a un **peso de referencia** =
    `min(peso, masa magra / 0.80)` (el peso equivalente a un 20 % de grasa). Así el rango no se infla en personas
    con mucha grasa corporal. Sin % de grasa, se usa el peso total.
- **Grasa:** el mayor entre el mínimo (0.6 g/kg, sobre el peso total) y un porcentaje de las calorías (25 % por
  defecto, configurable).
- **Carbohidratos:** el resto de las calorías (4 kcal/g para proteína y carbohidratos, 9 kcal/g para grasa).
- Si con una meta calórica baja el resto sale negativo, se recorta primero la grasa sobre su mínimo, luego la
  proteína sobre su mínimo; si aun así no cabe, carbohidratos = 0 y se avisa.

**Limitaciones.** Se ignoran fibra, alcohol y polialcoholes (las kcal declaradas de un alimento pueden diferir de
4P+4C+9G sin que haya error). La regla del peso de referencia es una **decisión de diseño** de esta app, no un
estándar publicado.

### 4. Adaptación: gasto real estimado por datos

Es el balance energético:

```
gasto = calorías promedio ingeridas − (pendiente de peso en kg/día) × 7700
```

**Cómo se calcula aquí, y por qué no exactamente como suele describirse.** La pendiente sale de una **regresión
lineal sobre los pesos diarios de la ventana**, no de la diferencia entre dos promedios móviles de 7 días. Con dos
promedios de 7 días dentro de una ventana de 14, sus centros están separados por **7 días, no 14**; dividir esa
diferencia entre 14 reduce a la mitad el efecto del peso y sesga el gasto hacia lo que comiste (en una simulación
con un déficit de 500 kcal da un error de ≈ 250 kcal). La regresión tolera días sin pesar y entrega un error
estándar. El promedio móvil de 7 días se usa solo para graficar.

**Cuándo hay estimación.** Solo si, en la ventana (14 días por defecto; 21, 28 o 42 opcionales; el día en curso
no cuenta):
- hay al menos **10 días con comida válida**,
- al menos **8 pesajes**, y al menos **3 en cada mitad** de la ventana.

Antes de eso la app **no muestra ningún número** y dice qué falta (con contadores), en vez de aparentar precisión.

**Día de comida «válido».** Suma al menos 1000 kcal (configurable), o lo fuerzas tú desde «Hoy» (*contar siempre* /
*no contar*). Sin este filtro, un día en que solo anotaste el desayuno parece un día de 400 kcal y hunde el promedio.
El promedio de calorías usa **solo** los días válidos.

**Incertidumbre: el punto que más conviene entender.** El mínimo de 14 días es el piso para *empezar*, no una
garantía de precisión. Con ruido diario de peso de ±0.4–0.7 kg (supuesto razonable por agua, sal y contenido
intestinal), una ventana de 14 días con pesaje diario da un intervalo de confianza al 95 % de aproximadamente
**±450–780 kcal/día**; con 28 días baja a ≈ ±190 kcal para ruido de 0.5 kg. Por eso la app siempre muestra el
intervalo y etiqueta la **confianza** (alta ≤ ±250, media ≤ ±450, baja el resto). Con confianza baja, trata el
número como una pista. Una prueba de simulación verifica que ese intervalo contiene el valor real en ≈ 95 % de los
casos.

**Recomendación.** Meta ideal = gasto por datos + ajuste del objetivo (nunca bajo el BMR). Diferencias menores a
100 kcal se descartan como ruido; cada ajuste se limita a **±250 kcal** para no sobrerreaccionar. **No se aplica
sola**: tú pulsas el botón. Si la diferencia con el gasto que asume tu meta actual es menor que el margen de
error, la app lo advierte.

**Limitaciones.**
- **7700 kcal/kg** es la densidad energética de la *grasa*. Es mala aproximación cuando el peso cambia por agua o
  glucógeno (domina las primeras 1–2 semanas de una dieta nueva, o tras un cambio brusco de carbohidratos o sodio) y
  cuando se gana masa magra (el tejido magro es bastante menos denso en energía que la grasa por su contenido de
  agua y proteína; la cifra exacta es incierta). Un cambio de dieta reciente contamina la ventana.
- **El sub-registro sesga el resultado.** Si registras menos de lo que comes (lo habitual), la ingesta promedio
  queda baja y el gasto estimado sale *más bajo que el real*. La estimación es tan buena como tu registro.
- El método supone ingesta y gasto aproximadamente estables dentro de la ventana y que los días sin registro se
  parecen a los registrados.
- No es una medición del metabolismo: es un balance con un peso ruidoso y una ingesta autorreportada.

### 5. Composición corporal

- **Masa magra** = peso suavizado (promedio móvil de 7 días) × (1 − % de grasa interpolado). El % de grasa se
  interpola linealmente entre mediciones, se mantiene constante después de la última y no se extrapola antes de la
  primera.
- **Fórmula Navy** (opcional, con medidas de cuello y cintura; cadera en mujeres): estima el % de grasa con un error
  típico de **±3–4 puntos**. Queda marcada como «estimada con medidas» y nunca se mezcla en silencio con un % medido.

**Limitaciones.** Los cambios de masa magra que muestra el gráfico dependen casi por completo de la trayectoria
*supuesta* del % de grasa entre mediciones. Si tus % son estimaciones tuyas, los cambios de masa magra no son
observaciones: son consecuencia de ese supuesto.

### 6. Datos faltantes

Un día sin pesar o sin registrar queda como dato faltante (nunca 0): las gráficas dejan huecos, los promedios solo
cuentan días con datos y el promedio móvil exige al menos 3 pesajes en su ventana de 7 días.

### 7. Alcance

Esta herramienta es de análisis personal, **no es consejo médico ni nutricional**. No sustituye a un profesional,
en particular si tienes una condición de salud, estás embarazada o tienes antecedentes de trastornos de la
conducta alimentaria.

## Notas técnicas

- **Tema:** `.streamlit/config.toml` define `[theme.light]` y `[theme.dark]` para que la app siga la preferencia del
  sistema. Evita un `[theme]` plano: Streamlit se queda en claro aunque el sistema esté en oscuro, y los gráficos
  (que adaptan sus colores al modo detectado) podrían quedar desincronizados con la interfaz.
- **Gráficos:** paleta categórica en orden fijo (proteína azul, carbohidratos naranja, grasa aguamarina, siempre),
  (las tres series que se usan, validadas para daltonismo y contraste con el script de la guía de visualización);
  nunca ejes duales; cada gráfico tiene su tabla de datos equivalente.
- **Esquema de la base:** versionado en `macro_tracker/db/schema.sql` (tabla `schema_version`); `connection.py` migra
  al abrir y rechaza bases de una versión más nueva que la app.
- **Unidades:** solo métricas (kg, cm). Interfaz en español.
