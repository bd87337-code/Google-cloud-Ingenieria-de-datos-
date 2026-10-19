/* ===== VISTA HOY ===== */
const sumEntries = (entries) => entries.reduce((t, e) => ({ kcal: t.kcal + e.kcal, p: t.p + e.p, c: t.c + e.c, f: t.f + e.f }), { kcal: 0, p: 0, c: 0, f: 0 });
const per = (food, grams) => ({ kcal: (food.kcal * grams) / 100, p: (food.p * grams) / 100, c: (food.c * grams) / 100, f: (food.f * grams) / 100 });
function validateFood(f) {
  const errs = [];
  if (!f.name || !f.name.trim()) errs.push('El alimento necesita un nombre.');
  for (const [k, l] of [['kcal', 'Las calorías'], ['p', 'La proteína'], ['c', 'Los carbohidratos'], ['f', 'La grasa']]) if (!isNum(f[k]) || f[k] < 0) errs.push(l + ' deben ser un número igual o mayor que 0.');
  if (isNum(f.kcal) && f.kcal > 900) errs.push('Más de 900 kcal por 100 g no es posible (la grasa pura tiene ≈ 900).');
  if (isNum(f.p) && isNum(f.c) && isNum(f.f) && f.p + f.c + f.f > 100.5) errs.push('Proteína + carbohidratos + grasa suman más de 100 g por cada 100 g.');
  if (f.servingG != null && !(f.servingG > 0)) errs.push('La porción debe ser mayor que 0.');
  return errs;
}
function foodLabel(f) { return h('span', null, f.name, f.brand ? ' (' + f.brand + ')' : '', SOURCE_TAG[f.source] ? h('span', { class: 'tag' + (f.source === 'ai' ? ' warn' : '') }, SOURCE_TAG[f.source]) : null); }
function recentFoods(limit = 12) {
  const seen = new Set(), out = [];
  for (const k of Object.keys(S.days).sort().reverse()) {
    for (const e of (S.days[k].entries || []).slice().reverse()) {
      if (seen.has(e.foodId)) continue; seen.add(e.foodId);
      const f = S.foods[e.foodId]; if (f && !f.archived) out.push(f);
      if (out.length >= limit) return out;
    }
  }
  return out;
}
function searchFoods(query, { exclude, limit = 40 } = {}) {
  const tokens = norm(query).split(' ').filter(Boolean);
  if (!tokens.length) return [];
  const first = norm(query);
  return foodList().filter((f) => !f.archived && f.id !== exclude && tokens.every((t) => norm(f.name + ' ' + (f.brand || '')).includes(t)))
    .sort((a, b) => (norm(b.name).startsWith(first) - norm(a.name).startsWith(first)) || a.name.length - b.name.length || (a.name < b.name ? -1 : 1)).slice(0, limit);
}

function viewToday() {
  const iso = S.date, today = todayIso(), day = S.days[iso] || {}, entries = day.entries || [], target = targetOn(iso), tot = sumEntries(entries);
  const root = h('div', { style: 'display:flex;flex-direction:column;gap:14px' });

  const dateInput = h('input', { type: 'date', value: iso, max: today, 'aria-label': 'Elegir fecha', onchange: (e) => { if (e.target.value) { S.date = e.target.value > today ? today : e.target.value; render(); } } });
  root.append(h('div', { class: 'date-bar' },
    h('button', { class: 'btn', type: 'button', 'aria-label': 'Día anterior', onclick: () => { S.date = addDays(iso, -1); render(); } }, '‹'),
    h('div', { class: 'date-label' }, h('span', null, iso === today ? 'Hoy' : longDate(iso).replace(/^./, (c) => c.toUpperCase())), iso === today ? h('span', { class: 'sub', style: 'font-weight:400' }, longDate(iso)) : null, dateInput),
    h('button', { class: 'btn', type: 'button', 'aria-label': 'Día siguiente', disabled: iso >= today, onclick: () => { S.date = addDays(iso, 1); render(); } }, '›')));

  if (!S.profile) root.append(notice('info', 'Para empezar, crea tu perfil y tu meta en la pestaña ', h('b', null, 'Metas'), '. Mientras tanto ya puedes registrar comida.'));
  else if (!target) root.append(notice('warn', 'Aún no tienes una meta vigente. Establécela en la pestaña ', h('b', null, 'Metas'), '.'));

  /* resumen */
  const hero = h('div', { class: 'kcal-hero' }, h('span', { class: 'big num' }, fmt0(tot.kcal)), h('span', { class: 'muted' }, 'kcal', target ? ' de ' + fmt0(target.kcal) : ''));
  const card = h('section', { class: 'card', 'aria-label': 'Resumen del día' }, hero);
  if (target) {
    const pct = tot.kcal / target.kcal, diff = tot.kcal - target.kcal;
    card.append(h('div', { class: 'meter', role: 'progressbar', 'aria-valuenow': Math.round(pct * 100), 'aria-valuemin': 0, 'aria-valuemax': 100 }, h('i', { style: `width:${Math.min(100, pct * 100)}%` })),
      h('div', { class: 'sub' }, diff <= 0 ? `Te faltan ${fmt0(-diff)} kcal para la meta (${Math.round(pct * 100)} %).` : `Superaste la meta por ${fmt0(diff)} kcal.`));
  }
  const estKcal = entries.filter((e) => e.est).reduce((s, e) => s + e.kcal, 0);
  if (estKcal > 0) card.append(h('div', { class: 'sub' }, `${Math.round((estKcal / tot.kcal) * 100)} % de estas calorías son estimadas por IA (menos precisas).`));
  for (const [key, label, color, short] of MACROS) {
    const goal = target ? target[short] : null, got = tot[short];
    card.append(h('div', { class: 'macro' },
      h('span', { class: 'macro-name' }, h('i', { class: 'dot', style: `background:var(--${color})` }), label),
      h('div', { class: 'meter' }, h('i', { style: `width:${goal ? Math.min(100, (got / goal) * 100) : 0}%;background:var(--${color})` })),
      h('b', null, goal ? `${fmt0(got)} / ${fmt0(goal)} g` : `${fmt0(got)} g`)));
  }
  root.append(card);

  /* estado del día para la adaptación */
  if (entries.length) {
    const minK = S.profile ? S.profile.minValidKcal : CFG.defaultMinValidKcal;
    const forced = typeof day.forced === 'boolean' ? day.forced : null, cur = forced === null ? 'auto' : forced ? 'yes' : 'no';
    const autoValid = tot.kcal >= minK && iso !== today;
    root.append(h('details', { class: 'card' }, h('summary', null, '¿Este día cuenta para estimar mi gasto?'),
      segmented([['auto', 'Automático'], ['yes', 'Contar siempre'], ['no', 'No contar']], cur, (v) => saveDay(iso, (d) => { if (v === 'auto') delete d.forced; else d.forced = v === 'yes'; })),
      h('p', { class: 'sub' }, `Automático: cuenta si suma al menos ${fmt0(minK)} kcal${iso === today ? ' y el día ya terminó (hoy casi siempre está incompleto)' : ''}. Ahora mismo: ${autoValid ? 'sí cuenta' : 'no cuenta'}.`)));
  }

  /* registro por comida */
  const log = h('section', { class: 'card', 'aria-label': 'Registro' }, h('h2', null, 'Registro'));
  if (!entries.length) log.append(h('div', { class: 'empty' }, h('span', null, 'Todavía no registras nada este día.'), h('button', { class: 'btn primary', type: 'button', onclick: () => addFoodSheet(iso) }, 'Agregar el primer alimento')));
  for (const meal of MEALS) {
    const es = entries.filter((e) => e.meal === meal); if (!es.length) continue;
    log.append(h('div', { class: 'meal-head', style: 'margin-top:4px' }, h('h3', null, MEAL_LABEL[meal]), h('span', { class: 'sub num' }, fmt0(sumEntries(es).kcal) + ' kcal')),
      h('div', { class: 'list' }, es.map((e) => h('button', { class: 'row', type: 'button', onclick: () => editEntrySheet(iso, e.id) },
        h('div', { class: 'main' }, h('div', { class: 'name' }, e.name + (e.brand ? ' (' + e.brand + ')' : ''), e.est ? h('span', { class: 'tag warn' }, 'estimado') : null), h('div', { class: 'meta num' }, `${fmt0(e.grams)} g · P ${fmt1(e.p)} · C ${fmt1(e.c)} · G ${fmt1(e.f)}`)),
        h('div', { class: 'end' }, fmt0(e.kcal) + ' kcal')))));
  }
  root.append(log);

  root.append(waterCard(iso, day), exerciseCard(iso, day), bodyCard(iso, day));
  return root;
}

function bodyCard(iso, day) {
  const hasAny = isNum(day.weight) || isNum(day.bf) || isNum(day.waist);
  const box = h('details', { class: 'card', open: !hasAny ? true : null }, h('summary', null, 'Peso y medidas del día'));
  const msg = h('div');
  const w = numInput(day.weight, { step: '0.1', min: 30, max: 300, placeholder: 'kg' }), bf = numInput(day.bf, { step: '0.1', min: 3, max: 60, placeholder: '%' });
  const src = select([['measured', 'medido'], ['self_estimate', 'estimado por ti']], day.bfSource === 'measured' ? 'measured' : 'self_estimate');
  const neck = numInput(day.neck, { step: '0.5', placeholder: 'cm' }), waist = numInput(day.waist, { step: '0.5', placeholder: 'cm' }), hip = numInput(day.hip, { step: '0.5', placeholder: 'cm' });
  const navy = h('input', { type: 'checkbox', id: 'navy-' + iso });
  const note = h('input', { type: 'text', value: day.note || '', placeholder: 'opcional' });
  box.append(h('p', { class: 'sub' }, 'Todo es opcional: puedes registrar solo el peso, o nada. Un día sin pesar no rompe ningún cálculo.'),
    h('div', { class: 'grid2' }, field('Peso (kg)', w), field('% de grasa', bf)),
    field('Origen del % de grasa', src, 'Sé honesto con el origen: una estimación a ojo no tiene la precisión de una medición.'),
    h('div', { class: 'grid3' }, field('Cuello (cm)', neck), field('Cintura (cm)', waist), field('Cadera (cm)', hip, 'Solo mujeres')),
    h('label', { class: 'check', for: 'navy-' + iso }, navy, h('span', null, 'Si no escribí un % de grasa, estimarlo con mis medidas (fórmula Navy, error típico ±3–4 puntos).')),
    field('Nota', note), msg,
    h('div', { class: 'btn-row' },
      h('button', { class: 'btn primary', type: 'button', onclick: () => {
        const bfv = num(bf.value), wv = num(w.value), nk = num(neck.value), wa = num(waist.value), hp = num(hip.value);
        let bfFinal = bfv, source = bfv != null ? src.value : null, navyUsed = false;
        const fail = (t) => { msg.replaceChildren(notice('bad', t)); };
        if (wv != null && (wv < 30 || wv > 300)) return fail('El peso debe estar entre 30 y 300 kg.');
        if (bfv != null && (bfv < 3 || bfv > 60)) return fail('El % de grasa debe estar entre 3 y 60.');
        if (bfv == null && navy.checked) {
          if (!S.profile) return fail('Para la fórmula Navy necesito tu perfil (sexo y estatura). Créalo en Metas.');
          if (nk == null || wa == null || (S.profile.sex === 'F' && hp == null)) return fail('La fórmula Navy requiere cuello y cintura (y cadera en mujeres).');
          try { bfFinal = Math.round(navyBodyFat(S.profile.sex, S.profile.heightCm, nk, wa, hp) * 10) / 10; navyUsed = true; } catch (e) { return fail(e.message); }
          if (bfFinal < 3 || bfFinal > 60) return fail('Con esas medidas la fórmula da ' + bfFinal + ' %, fuera de rango. Revisa las medidas.');
        }
        const keepNavy = bfFinal != null && day.bfSource === 'navy' && day.bf === bfFinal;
        saveDay(iso, (d) => { d.weight = wv; d.bf = bfFinal; d.bfSource = navyUsed || keepNavy ? 'navy' : source; d.neck = nk; d.waist = wa; d.hip = hp; d.note = note.value.trim(); });
        toast(navyUsed ? `Guardado. Navy estimó ${fmt1(bfFinal)} % de grasa.` : 'Guardado');
      } }, 'Guardar'),
      hasAny || day.note ? h('button', { class: 'btn danger', type: 'button', onclick: () => saveDay(iso, (d) => { for (const k of ['weight', 'bf', 'bfSource', 'neck', 'waist', 'hip', 'note']) delete d[k]; }) }, 'Borrar registro corporal') : null));
  return box;
}

/* ---------- hoja: agregar alimento ---------- */
function addFoodSheet(iso, preset) {
  openSheet('Agregar alimento', (body, close) => {
    const q = h('input', { type: 'search', placeholder: 'Buscar: tortilla, frijoles, pechuga…', autocomplete: 'off', 'aria-label': 'Buscar alimento' });
    const results = h('div', { class: 'list' });
    const aiBtn = S.caps.sample ? h('button', { class: 'btn block', type: 'button', onclick: () => { close(); aiLogSheet(iso); } }, 'Describir o fotografiar la comida (IA)') : null;
    const step1 = h('div', { style: 'display:flex;flex-direction:column;gap:12px' }, aiBtn, q, results);
    const step2 = h('div', { style: 'display:flex;flex-direction:column;gap:14px' });
    body.append(step1, step2); step2.hidden = true;

    const renderResults = () => {
      const query = q.value.trim(), foods = query ? searchFoods(query) : recentFoods();
      results.replaceChildren();
      if (!query && foods.length) results.append(h('div', { class: 'sub', style: 'padding:4px 0' }, 'Recientes'));
      if (!foods.length) {
        results.append(h('div', { class: 'empty' },
          h('span', null, query ? `No tienes «${query}» guardado.` : 'Aún no tienes alimentos. Crea el primero y quedará guardado.'),
          h('button', { class: 'btn primary', type: 'button', onclick: () => { close(); openFoodForm(null, { name: query, onSaved: (f) => addFoodSheet(iso, f) }); } }, query ? `Crear «${query}»` : 'Crear un alimento')));
        return;
      }
      foods.forEach((f) => results.append(h('button', { class: 'row', type: 'button', onclick: () => pick(f) },
        h('div', { class: 'main' }, h('div', { class: 'name' }, foodLabel(f)), h('div', { class: 'meta num' }, `${fmt0(f.kcal)} kcal por 100 g${f.servingG ? ' · porción ' + fmt0(f.servingG) + ' g' : ''}`)),
        h('div', { class: 'end' }, '›'))));
      if (query) results.append(h('button', { class: 'btn ghost block', type: 'button', onclick: () => { close(); openFoodForm(null, { name: query, onSaved: (f) => addFoodSheet(iso, f) }); } }, `+ Crear «${query}» como alimento nuevo`));
    };
    q.addEventListener('input', renderResults); renderResults();

    function pick(food) {
      step1.hidden = true; step2.hidden = false; step2.replaceChildren();
      let unit = 'g';
      const qty = numInput(food.servingG ? food.servingG : 100, { step: 'any', min: 0 });
      const meal = select(MEALS.map((m) => [m, MEAL_LABEL[m]]), mealByHour());
      const prev = h('div', { class: 'sub num' });
      const grams = () => { const v = num(qty.value); return v == null ? NaN : unit === 'g' ? v : v * food.servingG; };
      const upd = () => { const g = grams(); prev.textContent = g > 0 ? (() => { const m = per(food, g); return `${fmt0(g)} g → ${fmt0(m.kcal)} kcal · P ${fmt1(m.p)} g · C ${fmt1(m.c)} g · G ${fmt1(m.f)} g`; })() : 'Escribe una cantidad mayor que 0.'; };
      qty.addEventListener('input', upd);
      const qtyField = field('Cantidad (g)', qty);
      const unitSeg = food.servingG ? segmented([['g', 'Gramos'], ['serv', 'Porciones']], 'g', (v) => { unit = v; qty.value = v === 'g' ? food.servingG : 1; qtyField.querySelector('label').textContent = v === 'g' ? 'Cantidad (g)' : 'Porciones'; upd(); }) : null;
      step2.append(h('div', null, h('h3', null, foodLabel(food)), h('div', { class: 'sub' }, `${fmt0(food.kcal)} kcal por 100 g${food.servingG ? ' · ' + (food.servingLabel || 'porción de ' + fmt0(food.servingG) + ' g') : ''}`)),
        food.source === 'ai' ? notice('warn', 'Estos valores los estimó una IA; no son de una etiqueta. Verifícalos cuando puedas.') : null,
        unitSeg, qtyField, field('Comida', meal), prev,
        h('div', { class: 'btn-row' }, h('button', { class: 'btn', type: 'button', onclick: () => { step2.hidden = true; step1.hidden = false; } }, 'Atrás'),
          h('button', { class: 'btn primary', type: 'button', onclick: () => {
            const g = grams(); if (!(g > 0)) { toast('Escribe una cantidad mayor que 0.'); return; }
            const m = per(food, g);
            const entry = { id: uid(), meal: meal.value, foodId: food.id, name: food.name, brand: food.brand || null, grams: g, kcal: m.kcal, p: m.p, c: m.c, f: m.f, at: Date.now() };
            saveDay(iso, (d) => { d.entries = (d.entries || []).concat(entry); });
            close(); toast(`Agregado: ${food.name}`);
          } }, 'Agregar')));
      upd(); qty.focus();
    }
    if (preset) pick(preset); else setTimeout(() => q.focus(), 50);
  });
}

/* ---------- hoja: editar o borrar una entrada ---------- */
function editEntrySheet(iso, entryId) {
  const entry = ((S.days[iso] || {}).entries || []).find((e) => e.id === entryId);
  if (!entry) return;
  openSheet(entry.name, (body, close) => {
    const qty = numInput(Math.round(entry.grams * 10) / 10, { step: 'any', min: 0 });
    const prev = h('div', { class: 'sub num' });
    const upd = () => { const g = num(qty.value); prev.textContent = g > 0 ? `${fmt0(g)} g → ${fmt0((entry.kcal * g) / entry.grams)} kcal` : ''; };
    qty.addEventListener('input', upd); upd();
    body.append(field('Cantidad (g)', qty), prev, h('div', { class: 'btn-row' },
      h('button', { class: 'btn danger', type: 'button', onclick: () => { saveDay(iso, (d) => { d.entries = d.entries.filter((e) => e.id !== entryId); }); close(); toast('Entrada borrada'); } }, 'Borrar'),
      h('button', { class: 'btn primary', type: 'button', onclick: () => {
        const g = num(qty.value); if (!(g > 0)) { toast('La cantidad debe ser mayor que 0.'); return; }
        const k = g / entry.grams;
        saveDay(iso, (d) => { d.entries = d.entries.map((e) => (e.id === entryId ? { ...e, grams: g, kcal: e.kcal * k, p: e.p * k, c: e.c * k, f: e.f * k } : e)); });
        close();
      } }, 'Guardar')));
  });
}

/* ---------- hoja: crear o editar un alimento ---------- */
function openFoodForm(existing, { name, onSaved } = {}) {
  const f0 = existing || { id: uid(), name: name || '', brand: '', kcal: null, p: null, c: null, f: null, servingG: null, servingLabel: '', source: 'custom', archived: false, createdAt: Date.now() };
  openSheet(existing ? 'Editar alimento' : 'Nuevo alimento', (body, close) => {
    let source = ['ai', 'off', 'usda', 'label'].includes(f0.source) ? f0.source : 'custom';
    const nm = h('input', { type: 'text', value: f0.name, placeholder: 'Tortilla de maíz (tortillería)', autocomplete: 'off' });
    const br = h('input', { type: 'text', value: f0.brand || '', placeholder: 'opcional' });
    const k = numInput(f0.kcal, { step: '0.1', min: 0, max: 900 }), p = numInput(f0.p, { step: '0.1', min: 0, max: 100 }), c = numInput(f0.c, { step: '0.1', min: 0, max: 100 }), f = numInput(f0.f, { step: '0.1', min: 0, max: 100 });
    const derive = h('input', { type: 'checkbox', id: 'derive' });
    const sg = numInput(f0.servingG, { step: '1', min: 0, placeholder: 'g (opcional)' }), sl = h('input', { type: 'text', value: f0.servingLabel || '', placeholder: '1 tortilla chica' });
    const msg = h('div'), aiBox = h('div');
    const touched = () => { if (['ai', 'usda', 'off'].includes(source)) { source = 'custom'; aiBox.replaceChildren(); } };
    [k, p, c, f].forEach((el) => el.addEventListener('input', touched));
    body.append(field('Nombre', nm), field('Marca', br),
      h('p', { class: 'sub' }, 'Valores por cada 100 g (como vienen en la etiqueta).'),
      h('div', { class: 'grid2' }, field('Calorías (kcal)', k), field('Proteína (g)', p)), h('div', { class: 'grid2' }, field('Carbohidratos (g)', c), field('Grasa (g)', f)),
      h('label', { class: 'check', for: 'derive' }, derive, h('span', null, 'Calcular las calorías a partir de los macros (4·P + 4·C + 9·G).')),
      h('div', { class: 'grid2' }, field('Porción habitual (g)', sg), field('Descripción de la porción', sl)), aiBox);
    if (S.caps.sample && S.caps.images) body.append(labelReader({ nm, br, k, p, c, f, sg, sl }, (s) => { source = s; }, msg));
    if (S.caps.sample) {
      const btn = h('button', { class: 'btn block', type: 'button' }, 'Estimar los macros con Claude');
      btn.onclick = async () => {
        const n = nm.value.trim(); if (!n) { msg.replaceChildren(notice('bad', 'Escribe primero el nombre del alimento.')); return; }
        btn.disabled = true; btn.replaceChildren(h('span', { class: 'spin' }), ' Estimando…'); msg.replaceChildren();
        try {
          const r = await S.caps.sample.json(`Estima los valores nutricionales por 100 g de este alimento tal como se consume habitualmente en México: «${n}»${br.value.trim() ? ' (marca: ' + br.value.trim() + ')' : ''}. Responde SOLO un objeto JSON con números: {"kcal": number, "protein": number, "carbs": number, "fat": number, "servingG": number|null, "servingLabel": string|null}. Usa valores típicos realistas; kcal debe ser coherente con 4·proteína + 4·carbohidratos + 9·grasa.`, { modelTier: 'quick' });
          const fk = ['kcal', 'protein', 'carbs', 'fat'].every((x) => isNum(Number(r[x])));
          if (!fk) throw { code: 'invalid_json' };
          k.value = Math.round(r.kcal * 10) / 10; p.value = Math.round(r.protein * 10) / 10; c.value = Math.round(r.carbs * 10) / 10; f.value = Math.round(r.fat * 10) / 10;
          if (isNum(Number(r.servingG)) && r.servingG > 0 && !sg.value) { sg.value = Math.round(r.servingG); if (r.servingLabel && !sl.value) sl.value = String(r.servingLabel); }
          source = 'ai';
          aiBox.replaceChildren(notice('warn', 'Estimación de una IA con valores típicos, no de una etiqueta ni de una base de datos. Revísala; si la editas, se guarda como valor tuyo.'));
        } catch (e) {
          msg.replaceChildren(notice('bad', e && e.code === 'not_granted' ? 'No diste permiso para usar Claude en esta página.' : e && e.code === 'rate_limited' ? 'Demasiadas consultas seguidas; intenta en un rato.' : 'No pude obtener una estimación. Captura los valores a mano.'));
        } finally { btn.disabled = false; btn.replaceChildren('Estimar los macros con Claude'); }
      };
      body.append(btn);
    }
    body.append(msg, h('div', { class: 'btn-row' },
      existing ? h('button', { class: 'btn danger', type: 'button', onclick: () => {
        if (foodUsed(existing.id)) { saveFood({ ...existing, archived: true }); toast('Archivado: ya está en tu registro o en una receta, así que se conserva oculto.', 4000); }
        else { removeFood(existing.id); toast('Alimento eliminado'); }
        close();
      } }, 'Borrar / archivar') : null,
      h('button', { class: 'btn primary', type: 'button', onclick: () => {
        const pv = num(p.value), cv = num(c.value), fv = num(f.value);
        const kv = derive.checked && pv != null && cv != null && fv != null ? Math.round(kcalFromMacros(pv, cv, fv) * 10) / 10 : num(k.value);
        const food = { ...f0, name: nm.value.trim(), brand: br.value.trim() || null, kcal: kv, p: pv, c: cv, f: fv, servingG: num(sg.value) || null, servingLabel: sl.value.trim() || null, source: existing && existing.source === 'recipe' ? 'recipe' : source, fdc: f0.fdc || null };
        const errs = validateFood(food);
        if (errs.length) { msg.replaceChildren(notice('bad', errs.join(' '))); return; }
        const warn = kcalMismatch(food.kcal, food.p, food.c, food.f);
        saveFood(food); if (existing) recomputeDependents(food.id);
        close(); toast(warn ? `Guardado, pero las kcal (${fmt0(food.kcal)}) no cuadran con los macros (${fmt0(kcalFromMacros(food.p, food.c, food.f))}).` : 'Alimento guardado', warn ? 4500 : 2600);
        if (onSaved) onSaved(food);
      } }, 'Guardar')));
    setTimeout(() => nm.focus(), 50);
  });
}
function foodUsed(id) {
  for (const d of Object.values(S.days)) if ((d.entries || []).some((e) => e.foodId === id)) return true;
  return foodList().some((f) => f.recipe && f.recipe.items.some((i) => i.foodId === id));
}
