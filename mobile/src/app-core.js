/* ===== APP-CORE: estado, ayudantes de interfaz, plan de metas ===== */
const MEALS = ['breakfast', 'lunch', 'dinner', 'snack'];
const MEAL_LABEL = { breakfast: 'Desayuno', lunch: 'Comida', dinner: 'Cena', snack: 'Colación' };
const ACTIVITY_LABEL = {
  sedentary: 'Sedentario (poco o nada de ejercicio)', light: 'Ligero (1–3 días/semana)', moderate: 'Moderado (3–5 días/semana)',
  active: 'Activo (6–7 días/semana)', very_active: 'Muy activo (entrenamiento intenso o trabajo físico)',
};
const GOAL_LABEL = { maintain: 'Mantener', gain: 'Ganar masa', lose: 'Perder grasa' };
const BF_LABEL = { measured: 'medido', self_estimate: 'estimado por ti', navy: 'fórmula Navy (medidas)' };
const METHOD_LABEL = { katch_mcardle: 'Katch-McArdle', mifflin_st_jeor: 'Mifflin-St Jeor' };
const CONF_LABEL = { high: 'alta', medium: 'media', low: 'baja' };
const MACROS = [['protein', 'Proteína', 's1', 'p'], ['carbs', 'Carbohidratos', 's2', 'c'], ['fat', 'Grasa', 's3', 'f']];
const STALE_WEIGHT_DAYS = 14, STALE_BF_DAYS = 90;

const S = {
  backend: null, mode: 'local', pending: 0, profile: null, days: {}, foods: {}, targets: [],
  loaded: { profile: false, days: false, foods: false, targets: false },
  tab: 'today', date: todayIso(), caps: { sample: null, downloads: null },
  range: { preset: '90', start: null, end: null }, tdeeWindow: 14, showArchived: false, foodFilter: 'all',
};

/* ---------- utilidades ---------- */
const $ = (sel, root = document) => root.querySelector(sel);
const norm = (t) => (t || '').normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase().replace(/\s+/g, ' ').trim();
const uid = () => {
  if (window.crypto && crypto.randomUUID) return crypto.randomUUID().replace(/-/g, '');
  // Respaldo (contextos no seguros): 32 caracteres hex de Math.random, sin prefijo de hora que se repita.
  return Array.from({ length: 4 }, () => Math.floor(Math.random() * 0x100000000).toString(16).padStart(8, '0')).join('');
};
let _fieldSeq = 0;
const clone = (o) => JSON.parse(JSON.stringify(o));
const mean = (a) => (a.length ? a.reduce((x, y) => x + y, 0) / a.length : NaN);
const num = (v) => { if (v === '' || v == null) return null; const n = Number(String(v).replace(',', '.')); return Number.isFinite(n) ? n : null; };
const fmt0 = (n) => (isNum(n) ? Math.round(n).toLocaleString('es-MX') : '—');
const fmt1 = (n) => (isNum(n) ? n.toLocaleString('es-MX', { minimumFractionDigits: 1, maximumFractionDigits: 1 }) : '—');
const fmtDM = (iso) => iso.slice(8, 10) + '/' + iso.slice(5, 7);
const fmtDMY = (iso) => iso.slice(8, 10) + '/' + iso.slice(5, 7) + '/' + iso.slice(0, 4);
const longDate = (iso) => new Date(dayNum(iso) * DAY_MS).toLocaleDateString('es-MX', { weekday: 'long', day: 'numeric', month: 'long', timeZone: 'UTC' });
const cssVar = (n) => getComputedStyle(document.documentElement).getPropertyValue(n).trim();
const rgba = (hex, a) => { const c = hex.replace('#', ''); const v = [0, 2, 4].map((i) => parseInt(c.slice(i, i + 2), 16)); return `rgba(${v[0]},${v[1]},${v[2]},${a})`; };
const mealByHour = () => { const hr = new Date().getHours(); return hr < 11 ? 'breakfast' : hr < 17 ? 'lunch' : hr < 21 ? 'dinner' : 'snack'; };
const foodList = () => Object.values(S.foods);
const sortedTargets = () => S.targets.slice().sort((a, b) => (a.from < b.from ? -1 : 1));
const targetOn = (iso) => { let t = null; for (const x of sortedTargets()) if (x.from <= iso) t = x; return t; };

/* append/replaceChildren toleran null/false y listas (como h()): evita que el DOM escriba «null» en pantalla. */
(function () {
  const clean = (kids) => kids.flat(Infinity).filter((k) => k != null && k !== false);
  const ap = Element.prototype.append, rc = Element.prototype.replaceChildren;
  Element.prototype.append = function (...kids) { return ap.apply(this, clean(kids)); };
  Element.prototype.replaceChildren = function (...kids) { return rc.apply(this, clean(kids)); };
})();

function h(tag, props, ...kids) {
  const el = document.createElement(tag);
  let value;
  for (const [k, v] of Object.entries(props || {})) {
    if (v == null || v === false) continue;
    if (k === 'class') el.className = v;
    else if (k === 'text') el.textContent = v;
    else if (k === 'value') value = v;
    else if (k.startsWith('on')) el.addEventListener(k.slice(2), v);
    else if (k === 'checked' || k === 'disabled' || k === 'selected' || k === 'hidden') el[k] = !!v;
    else el.setAttribute(k, v === true ? '' : v);
  }
  for (const kid of kids.flat(Infinity)) { if (kid == null || kid === false) continue; el.append(kid.nodeType ? kid : document.createTextNode(String(kid))); }
  if (value !== undefined) el.value = value;
  return el;
}
const ICONS = {
  today: 'M8 3v4M16 3v4M4 9h16M5 5h14a1 1 0 0 1 1 1v13a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V6a1 1 0 0 1 1-1zM9 15l2 2 4-4',
  progress: 'M4 19V5M4 19h16M8 15l3-4 3 3 5-7',
  foods: 'M12 7c-2-3-7-2-7 3 0 5 3 10 7 10s7-5 7-10c0-5-5-6-7-3zM12 7c0-2 1-3 3-4',
  goals: 'M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18zM12 16a4 4 0 1 0 0-8 4 4 0 0 0 0 8zM12 12h.01',
  data: 'M5 4h11l3 3v13H5zM8 4v5h7V4M8 20v-6h8v6',
};
const icon = (name) => { const s = document.createElementNS('http://www.w3.org/2000/svg', 'svg'); s.setAttribute('viewBox', '0 0 24 24'); s.setAttribute('aria-hidden', 'true');
  const p = document.createElementNS('http://www.w3.org/2000/svg', 'path'); p.setAttribute('d', ICONS[name]); s.append(p); return s; };

function notice(kind, ...kids) { return h('div', { class: 'notice ' + kind, role: kind === 'bad' ? 'alert' : null }, h('span', null, ...kids)); }
function field(label, input, hint) { const id = input.id || (input.id = 'fld' + (++_fieldSeq)); return h('div', { class: 'field' }, h('label', { for: id }, label), input, hint ? h('div', { class: 'hint' }, hint) : null); }
function numInput(value, o = {}) { return h('input', { type: 'number', inputmode: 'decimal', step: o.step || 'any', min: o.min, max: o.max, value: value == null ? '' : value, placeholder: o.placeholder, id: o.id }); }
function select(options, value, id) { return h('select', { id, value }, options.map(([v, l]) => h('option', { value: v, selected: v === value }, l))); }
function segmented(options, value, onPick) {
  const wrap = h('div', { class: 'seg', role: 'group' });
  options.forEach(([v, l]) => wrap.append(h('button', { type: 'button', 'aria-pressed': String(v === value), onclick: (e) => { [...wrap.children].forEach((b) => b.setAttribute('aria-pressed', 'false')); e.currentTarget.setAttribute('aria-pressed', 'true'); onPick(v); } }, l)));
  return wrap;
}
function tableView(headers, rows, label = 'Ver tabla') {
  if (!rows.length) return h('details', null, h('summary', null, label), h('p', { class: 'sub' }, 'Sin datos en este rango.'));
  return h('details', null, h('summary', null, label), h('div', { class: 'tbl-wrap' }, h('table', null,
    h('thead', null, h('tr', null, headers.map((x) => h('th', null, x)))), h('tbody', null, rows.map((r) => h('tr', null, r.map((c) => h('td', null, c))))))));
}

let toastTimer;
function toast(msg, ms = 2600) { const t = $('#toast'); t.textContent = msg; t.hidden = false; clearTimeout(toastTimer); toastTimer = setTimeout(() => { t.hidden = true; }, ms); }

let sheetEl = null;
function openSheet(title, build) {
  closeSheet();
  const body = h('div', { class: 'sheet-body', style: 'display:flex;flex-direction:column;gap:14px' });
  const sheet = h('div', { class: 'sheet', role: 'dialog', 'aria-modal': 'true', 'aria-label': title }, h('div', { class: 'grab' }),
    h('div', { class: 'sheet-head' }, h('h2', null, title), h('button', { class: 'btn ghost sm', type: 'button', onclick: closeSheet }, 'Cerrar')), body);
  const scrim = h('div', { class: 'scrim', onclick: (e) => { if (e.target === scrim) closeSheet(); } }, sheet);
  document.body.append(scrim); sheetEl = scrim;
  build(body, closeSheet);
  return { body, close: closeSheet };
}
function closeSheet() { if (sheetEl) { sheetEl.remove(); sheetEl = null; } flushRender(); }
document.addEventListener('keydown', (e) => { if (e.key === 'Escape') closeSheet(); });

/* ---------- escritura con indicador de guardado ---------- */
async function write(fn) {
  S.pending++; updateSync();
  try { await fn(); return true; } catch (e) {
    console.error(e);
    toast(e && e.code === 'quota_exceeded' ? 'Se llenó el espacio de almacenamiento de la página.' : 'No se pudo guardar. Revisa tu conexión e intenta de nuevo.', 4200);
    return false;
  } finally { S.pending--; updateSync(); }
}
function updateSync() {
  const el = $('#sync'); if (!el) return;
  const st = S.pending > 0 ? 'saving' : S.mode === 'cloud' ? 'cloud' : 'local';
  el.dataset.state = st;
  el.textContent = st === 'saving' ? 'Guardando…' : st === 'cloud' ? 'Guardado en tu cuenta' : 'Solo en este navegador';
}
const isEmptyDay = (d) => !isNum(d.weight) && !isNum(d.bf) && !isNum(d.waist) && !isNum(d.neck) && !isNum(d.hip) && !d.note && !(d.entries && d.entries.length) && typeof d.forced !== 'boolean';
function saveDay(iso, mutate) {
  const doc = clone(S.days[iso] || { date: iso });
  mutate(doc);
  for (const k of ['weight', 'bf', 'waist', 'neck', 'hip', 'note', 'bfSource', 'forced']) if (doc[k] == null || doc[k] === '') delete doc[k];
  if (!isNum(doc.bf)) delete doc.bfSource;
  const empty = isEmptyDay(doc);
  if (empty) delete S.days[iso]; else S.days[iso] = doc;
  scheduleRender();
  return write(() => (empty ? S.backend.remove('days', iso) : S.backend.put('days', iso, doc)));
}
function saveFood(food) { S.foods[food.id] = food; scheduleRender(); return write(() => S.backend.put('foods', food.id, food)); }
function removeFood(id) { delete S.foods[id]; scheduleRender(); return write(() => S.backend.remove('foods', id)); }
function saveProfile(p) { S.profile = p; scheduleRender(); return write(() => S.backend.put('profile', 'main', p)); }

/* ---------- render con protección al escribir ---------- */
let renderQueued = false, deferred = false;
const typing = () => { const a = document.activeElement; return a && /^(INPUT|TEXTAREA|SELECT)$/.test(a.tagName) && $('#view').contains(a); };
function scheduleRender() {
  if (renderQueued) return;
  renderQueued = true;
  requestAnimationFrame(() => { renderQueued = false; if (typing()) { deferred = true; return; } render(); });
}
function flushRender() { if (!sheetEl) { deferred = false; render(); } }
document.addEventListener('focusout', () => { if (deferred) setTimeout(() => { if (!typing() && !sheetEl) { deferred = false; render(); } }, 120); });

/* ---------- estado corporal y plan de metas (equivale a services.build_plan) ---------- */
function bodyState() {
  const keys = Object.keys(S.days).sort();
  let wKey = null, bKey = null;
  for (let i = keys.length - 1; i >= 0; i--) {
    const d = S.days[keys[i]];
    if (wKey == null && isNum(d.weight)) wKey = keys[i];
    if (bKey == null && isNum(d.bf)) bKey = keys[i];
    if (wKey && bKey) break;
  }
  let weight = null;
  if (wKey) {
    const vals = [];
    for (let n = dayNum(wKey) - 6; n <= dayNum(wKey); n++) { const d = S.days[isoOf(n)]; if (d && isNum(d.weight)) vals.push(d.weight); }
    weight = mean(vals);
  }
  return { weight, weightDate: wKey, bf: bKey ? S.days[bKey].bf : null, bfSource: bKey ? S.days[bKey].bfSource : null, bfDate: bKey };
}
function buildPlan(on = todayIso()) {
  const p = S.profile, body = bodyState();
  if (!p || body.weight == null) return null;
  const notes = [];
  const useBf = body.bf != null && !p.mifflinOnly;
  if (body.bf != null && !useBf) notes.push('bf_ignored');
  if (useBf) {
    if (body.bfSource === 'self_estimate') notes.push('bf_self_estimate'); else if (body.bfSource === 'navy') notes.push('bf_navy');
    if (dayNum(on) - dayNum(body.bfDate) > STALE_BF_DAYS) notes.push('bf_stale');
  }
  if (dayNum(on) - dayNum(body.weightDate) > STALE_WEIGHT_DAYS) notes.push('no_recent_weight');
  const age = ageOn(p.birth, on);
  const bmr = estimateBmr(body.weight, p.heightCm, age, p.sex, useBf ? body.bf : null, p.mifflinOnly ? 'mifflin' : 'auto');
  const tdee = bmr.kcal * activityFactor(p.activity);
  const calories = calorieTarget(tdee, bmr.kcal, p.goal, p.rate);
  if (calories.floorApplied) notes.push('floor_applied');
  const ref = proteinRefWeight(body.weight, useBf ? body.bf : null);
  const macros = macrosFor(p, body.weight, ref, calories.kcal);
  return { profile: p, age, body, bmr, tdee, calories, ref, macros, notes };
}
const macrosFor = (p, weight, ref, kcal) => macroTargets(kcal, weight, p.goal, ref, [p.pMin, p.pMax], p.fatMin, p.fatPct);
function saveTarget(plan, kcal, source, note) {
  const m = macrosFor(plan.profile, plan.body.weight, plan.ref, kcal);
  const t = { from: todayIso(), kcal, p: m.protein, c: m.carbs, f: m.fat, source, bmrMethod: plan.bmr.method, note: note || null };
  S.targets = S.targets.filter((x) => x.from !== t.from).concat(t); scheduleRender();
  return write(() => S.backend.put('targets', t.from, t));
}
function dataFor() { return { days: S.days, targets: sortedTargets(), profile: S.profile }; }
function adaptiveStatus(plan, windowDays) {
  const end = addDays(todayIso(), -1), start = addDays(end, -(windowDays - 1));
  const fr = buildFrame(dataFor(), start, end, todayIso());
  const data = estimateTdee(fr.weight, fr.kcalValid, fr.dates.length - 1, windowDays);
  const active = targetOn(todayIso());
  const current = active ? active.kcal : plan.calories.kcal;
  const rec = recommendTarget(data, current, plan.profile.goal, plan.profile.rate, plan.bmr.kcal);
  return { data, rec, current, windowStart: start, windowEnd: end };
}
const PLAN_NOTES = {
  no_recent_weight: (pl) => `Tu último peso registrado tiene más de ${STALE_WEIGHT_DAYS} días y las metas usan ese valor. Registra un peso reciente.`,
  bf_self_estimate: (pl) => `El % de grasa que se usa es una estimación tuya, no una medición. Katch-McArdle lo toma tal cual: cada punto de error mueve el gasto basal ≈ ${Math.round(21.6 * pl.body.weight / 100)} kcal. Si no confías en ese dato, activa «Usar siempre Mifflin-St Jeor» en opciones avanzadas.`,
  bf_navy: () => 'El % de grasa viene de la fórmula Navy con tus medidas; su error típico es de ±3–4 puntos.',
  bf_stale: () => `Tu último % de grasa tiene más de ${STALE_BF_DAYS} días y puede estar desactualizado.`,
  bf_ignored: () => 'Tienes un % de grasa registrado, pero fuerzas Mifflin-St Jeor: se ignora en el gasto basal y en la proteína (sí se grafica la masa magra).',
  floor_applied: (pl) => `El ritmo elegido (${pl.profile.rate.toFixed(2)} kg/semana) exigiría ≈ ${fmt0(pl.calories.unfloored)} kcal/día, por debajo de tu gasto basal estimado (${fmt0(pl.calories.floor)} kcal). La meta se fijó en el basal, así que el ritmo real sería ≈ ${Math.abs(pl.calories.effectiveRate).toFixed(2)} kg/semana. Elige un ritmo más lento.`,
};
const REASON_TEXT = {
  food_days: (d) => `Días con comida registrada: ${d.nFood} de ${CFG.minFoodDays} necesarios (en los últimos ${d.windowDays} días).`,
  weighings: (d) => `Pesajes: ${d.nWeighings} de ${CFG.minWeighings} necesarios en la ventana.`,
  weighings_halves: (d) => `Los pesajes deben cubrir ambas mitades de la ventana (mínimo ${CFG.minPerHalf} en cada una); tienes ${d.nWeighings1} y ${d.nWeighings2}.`,
  no_variation: () => 'No hay variación suficiente en las fechas de pesaje para estimar una tendencia.',
};
const MACRO_FLAG_TEXT = {
  reduced_to_fit: 'Con esta meta calórica se redujeron grasa y/o proteína respecto a lo ideal para que cuadren los carbohidratos (siguen sobre sus mínimos).',
  minimums_exceed_kcal: 'Los mínimos de proteína y grasa no caben en esta meta calórica: carbohidratos = 0. Revisa el ritmo o el rango de proteína.',
};
