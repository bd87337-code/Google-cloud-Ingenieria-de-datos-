/* ===== VISTA DATOS: exportar/importar CSV (mismo formato que la versión de escritorio) ===== */
const CSV_TABLES = ['profile', 'body_log', 'foods', 'recipes', 'recipe_items', 'food_log', 'day_status', 'targets'];
const csvEsc = (v) => { if (v == null) return ''; const s = String(v); return /[",\n\r]/.test(s) ? '"' + s.replace(/"/g, '""') + '"' : s; };
const toCsv = (cols, rows) => '﻿' + [cols.join(','), ...rows.map((r) => cols.map((c) => csvEsc(r[c])).join(','))].join('\n') + '\n';
const isoTs = (ms) => (ms ? new Date(ms).toISOString().replace(/\.\d+Z$/, '+00:00') : '');

function parseCsv(text) {
  if (text.charCodeAt(0) === 0xfeff) text = text.slice(1);
  const rows = []; let row = [], cur = '', q = false;
  for (let i = 0; i < text.length; i++) {
    const ch = text[i];
    if (q) { if (ch === '"') { if (text[i + 1] === '"') { cur += '"'; i++; } else q = false; } else cur += ch; }
    else if (ch === '"') q = true;
    else if (ch === ',') { row.push(cur); cur = ''; }
    else if (ch === '\n' || ch === '\r') { if (ch === '\r' && text[i + 1] === '\n') i++; row.push(cur); cur = ''; if (row.some((c) => c !== '')) rows.push(row); row = []; }
    else cur += ch;
  }
  if (cur !== '' || row.length) { row.push(cur); if (row.some((c) => c !== '')) rows.push(row); }
  if (!rows.length) return { cols: [], rows: [] };
  const cols = rows[0].map((c) => c.trim());
  return { cols, rows: rows.slice(1).map((r) => Object.fromEntries(cols.map((c, i) => [c, (r[i] ?? '').trim()]))) };
}

function exportTables() {
  const out = {}, p = S.profile, dayKeys = Object.keys(S.days).sort();
  out.profile = toCsv(['sex', 'birth_date', 'height_cm', 'activity_level', 'goal', 'rate_kg_week', 'protein_g_kg_min', 'protein_g_kg_max', 'fat_g_kg_min', 'fat_pct_kcal', 'bmr_method_pref', 'min_valid_day_kcal', 'updated_at'],
    p ? [{ sex: p.sex, birth_date: p.birth, height_cm: p.heightCm, activity_level: p.activity, goal: p.goal, rate_kg_week: p.rate, protein_g_kg_min: p.pMin, protein_g_kg_max: p.pMax, fat_g_kg_min: p.fatMin, fat_pct_kcal: p.fatPct, bmr_method_pref: p.mifflinOnly ? 'mifflin' : 'auto', min_valid_day_kcal: p.minValidKcal, updated_at: new Date().toISOString() }] : []);
  out.body_log = toCsv(['date', 'weight_kg', 'body_fat_pct', 'body_fat_source', 'waist_cm', 'neck_cm', 'hip_cm', 'note'],
    dayKeys.filter((k) => { const d = S.days[k]; return isNum(d.weight) || isNum(d.bf) || isNum(d.waist) || isNum(d.neck) || isNum(d.hip) || d.note; })
      .map((k) => { const d = S.days[k]; return { date: k, weight_kg: d.weight, body_fat_pct: d.bf, body_fat_source: d.bfSource, waist_cm: d.waist, neck_cm: d.neck, hip_cm: d.hip, note: d.note }; }));
  const foods = foodList().sort((a, b) => (a.createdAt || 0) - (b.createdAt || 0));
  out.foods = toCsv(['uid', 'name', 'brand', 'source', 'barcode', 'kcal_100g', 'protein_100g', 'carbs_100g', 'fat_100g', 'serving_g', 'serving_label', 'data_flag', 'archived', 'off_fetched_at', 'created_at'],
    foods.map((f) => ({ uid: f.id, name: f.name, brand: f.brand, source: f.source === 'ai' ? 'custom' : f.source, barcode: f.barcode, kcal_100g: f.kcal, protein_100g: f.p, carbs_100g: f.c, fat_100g: f.f,
      serving_g: f.servingG, serving_label: f.servingLabel, data_flag: f.source === 'ai' ? 'ai_estimate' : null, archived: f.archived ? 1 : 0, off_fetched_at: null, created_at: isoTs(f.createdAt) })));
  const recipes = foods.filter((f) => f.recipe);
  out.recipes = toCsv(['food_uid', 'total_yield_g', 'servings'], recipes.map((f) => ({ food_uid: f.id, total_yield_g: f.recipe.yieldG, servings: f.recipe.servings })));
  out.recipe_items = toCsv(['recipe_uid', 'ingredient_uid', 'grams'], recipes.flatMap((f) => f.recipe.items.map((i) => ({ recipe_uid: f.id, ingredient_uid: i.foodId, grams: i.grams }))));
  out.food_log = toCsv(['uid', 'date', 'meal', 'food_uid', 'grams', 'kcal', 'protein_g', 'carbs_g', 'fat_g', 'created_at'],
    dayKeys.flatMap((k) => (S.days[k].entries || []).map((e) => ({ uid: e.id, date: k, meal: e.meal, food_uid: e.foodId, grams: e.grams, kcal: e.kcal, protein_g: e.p, carbs_g: e.c, fat_g: e.f, created_at: isoTs(e.at) }))));
  out.day_status = toCsv(['date', 'food_complete'], dayKeys.filter((k) => typeof S.days[k].forced === 'boolean').map((k) => ({ date: k, food_complete: S.days[k].forced ? 1 : 0 })));
  out.targets = toCsv(['effective_from', 'kcal', 'protein_g', 'carbs_g', 'fat_g', 'tdee_source', 'bmr_method', 'note'],
    sortedTargets().map((t) => ({ effective_from: t.from, kcal: t.kcal, protein_g: t.p, carbs_g: t.c, fat_g: t.f, tdee_source: t.source, bmr_method: t.bmrMethod, note: t.note })));
  return out;
}

/* Valida TODO antes de escribir. Devuelve { errors, plan } con plan = {profile, foods, days(parches), targets}. */
function planImport(files) {
  const errors = [], plan = { profile: null, foods: {}, dayPatches: {}, targets: [] };
  const T = {}; // tablas parseadas
  for (const [name, text] of Object.entries(files)) { try { T[name] = parseCsv(text); } catch (e) { errors.push(`${name}.csv: no se pudo leer (${e.message})`); } }
  const need = (name, cols) => { if (!T[name]) return false; const miss = cols.filter((c) => !T[name].cols.includes(c)); if (miss.length) { errors.push(`${name}.csv: faltan columnas ${miss.join(', ')}`); return false; } return true; };
  const rowCtx = (name, i) => {
    const where = `${name}.csv fila ${i + 2}`;
    return {
      txt: (c, req) => { const v = T[name].rows[i][c] ?? ''; if (req && !v) errors.push(`${where}, columna '${c}': es obligatoria`); return v || null; },
      n: (c, o = {}) => { let v = (T[name].rows[i][c] ?? ''); if (v === '') { if (o.req) errors.push(`${where}, columna '${c}': es obligatoria`); return null; }
        if (/^-?\d+,\d+$/.test(v)) v = v.replace(',', '.'); const x = Number(v);
        if (!Number.isFinite(x)) { errors.push(`${where}, columna '${c}': '${v}' no es un número`); return null; }
        if (o.min != null && (x < o.min || (o.exMin && x === o.min))) { errors.push(`${where}, columna '${c}': ${x} fuera de rango`); return null; }
        if (o.max != null && x > o.max) { errors.push(`${where}, columna '${c}': ${x} fuera de rango`); return null; } return x; },
      date: (c) => { const v = T[name].rows[i][c] ?? ''; if (!/^\d{4}-\d{2}-\d{2}$/.test(v) || isNaN(Date.parse(v))) { errors.push(`${where}, columna '${c}': '${v}' no es una fecha AAAA-MM-DD`); return null; } return v; },
      pick: (c, opts, req = true) => { const v = T[name].rows[i][c] ?? ''; if (!v) { if (req) errors.push(`${where}, columna '${c}': es obligatoria`); return null; } if (!opts.includes(v)) { errors.push(`${where}, columna '${c}': '${v}' no es válido (${opts.join(', ')})`); return null; } return v; },
    };
  };
  if (need('profile', ['sex', 'birth_date', 'height_cm', 'activity_level', 'goal']) && T.profile.rows.length) {
    const r = rowCtx('profile', 0);
    const o = { sex: r.pick('sex', ['M', 'F']), birth: r.date('birth_date'), heightCm: r.n('height_cm', { req: true, min: 0, exMin: true, max: 260 }), activity: r.pick('activity_level', Object.keys(ACTIVITY_FACTORS)), goal: r.pick('goal', ['maintain', 'gain', 'lose']),
      rate: r.n('rate_kg_week', { min: 0 }) ?? 0, pMin: r.n('protein_g_kg_min', { min: 0, exMin: true }) ?? 1.6, pMax: r.n('protein_g_kg_max', { min: 0, exMin: true }) ?? 2.2, fatMin: r.n('fat_g_kg_min', { min: 0 }) ?? 0.6,
      fatPct: r.n('fat_pct_kcal', { min: 0, max: 0.99 }) ?? 0.25, mifflinOnly: r.txt('bmr_method_pref') === 'mifflin', minValidKcal: r.n('min_valid_day_kcal', { min: 0 }) ?? 1000 };
    if (o.pMax < o.pMin) errors.push("profile.csv fila 2, columna 'protein_g_kg_max': debe ser ≥ protein_g_kg_min");
    plan.profile = o;
  }
  const patch = (iso) => (plan.dayPatches[iso] = plan.dayPatches[iso] || { entries: [] });
  if (need('body_log', ['date'])) T.body_log.rows.forEach((_, i) => {
    const r = rowCtx('body_log', i), d = r.date('date'), w = r.n('weight_kg', { min: 0, exMin: true, max: 500 }), bf = r.n('body_fat_pct', { min: 3, max: 60 });
    const src = r.pick('body_fat_source', ['measured', 'self_estimate', 'navy'], false), wa = r.n('waist_cm', { min: 0, exMin: true, max: 300 }), nk = r.n('neck_cm', { min: 0, exMin: true, max: 300 }), hp = r.n('hip_cm', { min: 0, exMin: true, max: 300 });
    if (bf != null && !src) errors.push(`body_log.csv fila ${i + 2}, columna 'body_fat_source': es obligatoria cuando hay body_fat_pct`);
    if (d) Object.assign(patch(d), { body: { weight: w, bf, bfSource: bf != null ? src : null, waist: wa, neck: nk, hip: hp, note: r.txt('note') } });
  });
  if (need('foods', ['uid', 'name', 'kcal_100g', 'protein_100g', 'carbs_100g', 'fat_100g'])) T.foods.rows.forEach((_, i) => {
    const r = rowCtx('foods', i), id = r.txt('uid', true), name = r.txt('name', true), srcRaw = r.pick('source', ['custom', 'off', 'recipe'], false) || 'custom';
    const food = { id, name, brand: r.txt('brand'), kcal: r.n('kcal_100g', { req: true, min: 0, max: 900 }), p: r.n('protein_100g', { req: true, min: 0, max: 100 }), c: r.n('carbs_100g', { req: true, min: 0, max: 100 }), f: r.n('fat_100g', { req: true, min: 0, max: 100 }),
      servingG: r.n('serving_g', { min: 0, exMin: true }), servingLabel: r.txt('serving_label'), source: srcRaw === 'custom' && r.txt('data_flag') === 'ai_estimate' ? 'ai' : srcRaw, archived: ['1', 'true', 'True'].includes(T.foods.rows[i].archived), createdAt: Date.parse(r.txt('created_at') || '') || Date.now() };
    if (id && name && isNum(food.p) && isNum(food.c) && isNum(food.f) && food.p + food.c + food.f > 100.5) errors.push(`foods.csv fila ${i + 2}: proteína + carbohidratos + grasa suman más de 100 g por 100 g`);
    if (id) plan.foods[id] = food;
  });
  const foodOf = (id) => plan.foods[id] || S.foods[id];
  if (need('recipes', ['food_uid', 'total_yield_g'])) T.recipes.rows.forEach((_, i) => {
    const r = rowCtx('recipes', i), id = r.txt('food_uid', true), y = r.n('total_yield_g', { req: true, min: 0, exMin: true }), sv = r.n('servings', { min: 0, exMin: true }) ?? 1;
    if (!id) return; const f = foodOf(id); if (!f) { errors.push(`recipes.csv fila ${i + 2}, columna 'food_uid': el alimento '${id}' no existe`); return; }
    plan.foods[id] = { ...(plan.foods[id] || f), source: 'recipe', recipe: { items: [], yieldG: y, servings: sv } };
  });
  if (need('recipe_items', ['recipe_uid', 'ingredient_uid', 'grams'])) T.recipe_items.rows.forEach((_, i) => {
    const r = rowCtx('recipe_items', i), rid = r.txt('recipe_uid', true), iid = r.txt('ingredient_uid', true), g = r.n('grams', { req: true, min: 0, exMin: true });
    if (!rid || !iid) return; const rec = plan.foods[rid];
    if (!rec || !rec.recipe) { errors.push(`recipe_items.csv fila ${i + 2}, columna 'recipe_uid': la receta '${rid}' no está en recipes.csv`); return; }
    if (!foodOf(iid)) { errors.push(`recipe_items.csv fila ${i + 2}, columna 'ingredient_uid': el ingrediente '${iid}' no existe`); return; }
    rec.recipe.items.push({ foodId: iid, grams: g });
  });
  if (need('food_log', ['uid', 'date', 'meal', 'food_uid', 'grams', 'kcal', 'protein_g', 'carbs_g', 'fat_g'])) T.food_log.rows.forEach((_, i) => {
    const r = rowCtx('food_log', i), id = r.txt('uid', true), d = r.date('date'), meal = r.pick('meal', MEALS), fid = r.txt('food_uid', true), g = r.n('grams', { req: true, min: 0, exMin: true });
    const m = ['kcal', 'protein_g', 'carbs_g', 'fat_g'].map((c) => r.n(c, { req: true, min: 0 }));
    if (fid && !foodOf(fid)) errors.push(`food_log.csv fila ${i + 2}, columna 'food_uid': el alimento '${fid}' no existe`);
    if (id && d && meal && fid && foodOf(fid) && g && m.every(isNum)) { const f = foodOf(fid); patch(d).entries.push({ id, meal, foodId: fid, name: f.name, brand: f.brand || null, grams: g, kcal: m[0], p: m[1], c: m[2], f: m[3], at: Date.parse(r.txt('created_at') || '') || Date.now() }); }
  });
  if (need('day_status', ['date', 'food_complete'])) T.day_status.rows.forEach((_, i) => { const r = rowCtx('day_status', i), d = r.date('date'), v = r.pick('food_complete', ['0', '1'], false); if (d) patch(d).forced = v == null ? null : v === '1'; });
  if (need('targets', ['effective_from', 'kcal', 'protein_g', 'carbs_g', 'fat_g', 'tdee_source'])) T.targets.rows.forEach((_, i) => {
    const r = rowCtx('targets', i), d = r.date('effective_from'), k = r.n('kcal', { req: true, min: 0, exMin: true }), m = ['protein_g', 'carbs_g', 'fat_g'].map((c) => r.n(c, { req: true, min: 0 })), s = r.pick('tdee_source', ['formula', 'data', 'manual']);
    if (d && k && s && m.every(isNum)) plan.targets.push({ from: d, kcal: k, p: m[0], c: m[1], f: m[2], source: s, bmrMethod: r.txt('bmr_method'), note: r.txt('note') });
  });
  return { errors, plan };
}

async function applyImport(plan, mode, onProgress) {
  const ops = [];
  if (mode === 'replace') {
    Object.keys(S.days).forEach((k) => ops.push(() => S.backend.remove('days', k)));
    foodList().forEach((f) => ops.push(() => S.backend.remove('foods', f.id)));
    S.targets.forEach((t) => ops.push(() => S.backend.remove('targets', t.from)));
    if (S.profile) ops.push(() => S.backend.remove('profile', 'main'));
  }
  const base = mode === 'replace' ? {} : S.days;
  Object.values(plan.foods).forEach((f) => ops.push(() => S.backend.put('foods', f.id, f)));
  for (const [iso, pt] of Object.entries(plan.dayPatches)) {
    const doc = clone(base[iso] || { date: iso });
    if (pt.body) for (const [k, v] of Object.entries(pt.body)) { if (v == null) delete doc[k]; else doc[k] = v; }
    if (!isNum(doc.bf)) delete doc.bfSource;
    if (pt.entries.length) { const map = new Map((doc.entries || []).map((e) => [e.id, e])); pt.entries.forEach((e) => map.set(e.id, e)); doc.entries = [...map.values()]; }
    if ('forced' in pt) { if (pt.forced == null) delete doc.forced; else doc.forced = pt.forced; }
    if (!isEmptyDay(doc)) ops.push(() => S.backend.put('days', iso, doc));
  }
  plan.targets.forEach((t) => ops.push(() => S.backend.put('targets', t.from, t)));
  if (plan.profile) ops.push(() => S.backend.put('profile', 'main', plan.profile));
  for (let i = 0; i < ops.length; i++) { await ops[i](); onProgress(i + 1, ops.length); if (i % 15 === 14) await new Promise((r) => setTimeout(r, 60)); }
  return ops.length;
}

async function readUploads(fileList) {
  const files = {};
  for (const f of fileList) {
    if (/\.zip$/i.test(f.name)) {
      if (typeof JSZip === 'undefined') throw new Error('No se pudo cargar el lector de ZIP.');
      const zip = await JSZip.loadAsync(await f.arrayBuffer());
      for (const name of Object.keys(zip.files)) { const m = name.split('/').pop().match(/^(.+)\.csv$/i); if (m && CSV_TABLES.includes(m[1])) files[m[1]] = await zip.files[name].async('string'); }
    } else { const m = f.name.match(/^(.+)\.csv$/i); if (m && CSV_TABLES.includes(m[1])) files[m[1]] = await f.text(); else throw new Error(`«${f.name}» no se reconoce: el nombre debe ser una de estas tablas .csv: ${CSV_TABLES.join(', ')}.`); }
  }
  return files;
}

function viewData() {
  const root = h('div', { style: 'display:flex;flex-direction:column;gap:14px' });
  const ndays = Object.keys(S.days).length, nentries = Object.values(S.days).reduce((s, d) => s + (d.entries || []).length, 0);
  root.append(h('div', null, h('h2', null, 'Datos'), h('p', { class: 'sub' }, S.mode === 'cloud' ? 'Tus datos están en tu cuenta de Claude, privados para ti, y se sincronizan entre tus dispositivos.' : 'Tus datos están solo en este navegador. Si lo borras o cambias de dispositivo, se pierden: exporta un respaldo.')),
    h('div', { class: 'kpis' }, h('div', { class: 'kpi' }, h('div', { class: 'l' }, 'Días con registro'), h('div', { class: 'v num' }, String(ndays))), h('div', { class: 'kpi' }, h('div', { class: 'l' }, 'Entradas de comida'), h('div', { class: 'v num' }, String(nentries)))));

  const exMsg = h('div');
  root.append(h('section', { class: 'card' }, h('h3', null, 'Exportar'), h('p', { class: 'sub' }, 'Un ZIP con un CSV por tabla, con el mismo formato que la versión de escritorio. Sirve de respaldo y para abrirlo en Excel, R o Python.'), exMsg,
    h('button', { class: 'btn primary block', type: 'button', onclick: async (e) => {
      const btn = e.currentTarget; btn.disabled = true;
      try {
        if (typeof JSZip === 'undefined') throw new Error('zip');
        const zip = new JSZip(); const t = exportTables();
        zip.file('manifest.json', JSON.stringify({ app: 'macro_tracker', schema_version: 1, exported_at: new Date().toISOString(), tables: CSV_TABLES, source: 'mobile' }, null, 2));
        CSV_TABLES.forEach((n) => zip.file(n + '.csv', t[n]));
        const blob = await zip.generateAsync({ type: 'blob', compression: 'DEFLATE' });
        const dl = S.caps.downloads;
        if (!dl) { exMsg.replaceChildren(notice('warn', 'Esta vista no permite descargar archivos. Ábrela desde la app de Claude o desde claude.ai.')); return; }
        await dl.save({ filename: `macro_tracker_${todayIso().replace(/-/g, '')}.zip`, data: blob });
        exMsg.replaceChildren(notice('good', 'Respaldo guardado.'));
      } catch (err) {
        exMsg.replaceChildren(err && err.code === 'declined' ? notice('info', 'Cancelaste la descarga.') : notice('bad', 'No se pudo generar el archivo.'));
      } finally { btn.disabled = false; }
    } }, 'Descargar respaldo (ZIP)')));

  const up = h('input', { type: 'file', accept: '.zip,.csv', multiple: true, id: 'upload' }), imMsg = h('div'), prog = h('div', { class: 'sub' });
  // El mensaje se guarda en el estado: al importar cambian los datos, la pantalla se redibuja y de otro modo se perdería.
  const showImport = (kind, text, list, more) => { S.importMsg = { kind, text, list, more }; paintImport(); };
  const paintImport = () => { imMsg.replaceChildren(); const m = S.importMsg; if (!m) return; imMsg.append(notice(m.kind, m.text), m.list ? h('ul', { style: 'margin:8px 0 0;padding-left:20px;font-size:14px' }, m.list.map((x) => h('li', null, x))) : null, m.more ? h('p', { class: 'sub' }, m.more) : null); };
  paintImport();
  let mode = 'merge'; const confirmBox = h('input', { type: 'checkbox', id: 'confirm-replace' });
  const confirmRow = h('label', { class: 'check', for: 'confirm-replace', hidden: true }, confirmBox, h('span', null, 'Entiendo que esto borra todo lo que tengo ahora y lo reemplaza por el archivo.'));
  root.append(h('section', { class: 'card' }, h('h3', null, 'Importar'),
    h('p', { class: 'sub' }, 'Acepta el ZIP de esta app (o de la versión de escritorio) o archivos CSV sueltos con el nombre de cada tabla. La importación es todo o nada: si una fila tiene un error, no se guarda nada y te digo dónde está.'),
    field('Archivo', up), segmented([['merge', 'Combinar'], ['replace', 'Reemplazar todo']], mode, (v) => { mode = v; confirmRow.hidden = v !== 'replace'; }), confirmRow, imMsg, prog,
    h('button', { class: 'btn block', type: 'button', onclick: async (e) => {
      const btn = e.currentTarget; S.importMsg = null; paintImport(); prog.textContent = '';
      if (!up.files.length) { showImport('warn', 'Elige primero un archivo.'); return; }
      if (mode === 'replace' && !confirmBox.checked) { showImport('warn', 'Marca la casilla para confirmar el reemplazo.'); return; }
      btn.disabled = true;
      try {
        const files = await readUploads(up.files);
        if (!Object.keys(files).length) throw new Error('No encontré ninguna tabla reconocible en los archivos.');
        const { errors, plan } = planImport(files);
        if (errors.length) { showImport('bad', 'Importación cancelada; no se guardó nada.', errors.slice(0, 15), errors.length > 15 ? `… y ${errors.length - 15} errores más.` : null); return; }
        const n = await write(() => applyImport(plan, mode, (i, tot) => { prog.textContent = `Guardando ${i} de ${tot}…`; }));
        prog.textContent = ''; if (n) { showImport('good', 'Importación completada.'); toast('Importación completada'); } else showImport('bad', 'La importación se interrumpió; puede haber quedado a medias. Vuelve a importar en modo «Combinar» para completarla.');
      } catch (err) { showImport('bad', err.message || 'No se pudo leer el archivo.'); } finally { btn.disabled = false; }
    } }, 'Importar')));

  const wipeBox = h('div');
  root.append(h('section', { class: 'card' }, h('h3', null, 'Borrar todo'), h('p', { class: 'sub' }, 'Elimina tu perfil, registros, alimentos y metas. Exporta un respaldo antes.'), wipeBox,
    h('button', { class: 'btn danger block', type: 'button', onclick: () => {
      wipeBox.replaceChildren(notice('bad', 'Esto no se puede deshacer.'), h('div', { class: 'btn-row' }, h('button', { class: 'btn', type: 'button', onclick: () => wipeBox.replaceChildren() }, 'Cancelar'),
        h('button', { class: 'btn danger', type: 'button', onclick: async () => {
          const ok = await write(async () => { for (const k of Object.keys(S.days)) await S.backend.remove('days', k); for (const f of foodList()) await S.backend.remove('foods', f.id); for (const t of S.targets) await S.backend.remove('targets', t.from); if (S.profile) await S.backend.remove('profile', 'main'); });
          wipeBox.replaceChildren(); if (ok) toast('Se borraron todos tus datos.');
        } }, 'Sí, borrar todo')));
    } }, 'Borrar todos mis datos')));
  return root;
}
