/* ===== IA (texto/foto/etiqueta), AGUA y EJERCICIO ===== */
const SOURCE_TAG = { recipe: 'receta', ai: 'estimado por IA', off: 'OFF', usda: 'USDA', label: 'etiqueta' };

function aiErrorNote(e) {
  switch (e && e.code) {
    case 'cancelled': return null;
    case 'not_granted': return 'No diste permiso para que esta página use Claude. Puedes capturar los valores a mano.';
    case 'rate_limited': return 'Demasiadas consultas seguidas o llegaste a tu límite de uso. Intenta más tarde.';
    case 'invalid_json': return 'No pude entender la respuesta. Prueba describiendo con más detalle (cantidades y preparación).';
    case 'image_rejected': return 'No pude usar esa imagen. Prueba con otra foto.';
    case 'images_unavailable': return 'Esta vista no puede enviar fotos.';
    case 'session_expired': return 'Tu sesión expiró; vuelve a abrir la página.';
    default: return 'No pude obtener una estimación ahora. Intenta de nuevo o captura los valores a mano.';
  }
}
/** Pregunta a Claude pidiendo JSON. Cada llamada es deliberada, así que no usa la caché. */
function askAi(prompt, blob, ctl) {
  const o = { modelTier: 'default', cache: false, signal: ctl.signal };
  if (blob) o.images = blob;
  return S.caps.sample.json(prompt, o);
}

/** Selector de foto: cámara o galería, con vista previa. */
function photoPicker() {
  const st = { blob: null, url: null };
  const cam = h('input', { type: 'file', accept: 'image/*', capture: 'environment', hidden: true, 'aria-label': 'Tomar foto' });
  const gal = h('input', { type: 'file', accept: 'image/*', hidden: true, 'aria-label': 'Elegir foto de la galería' });
  const prev = h('div');
  const clear = () => { if (st.url) URL.revokeObjectURL(st.url); st.blob = null; st.url = null; prev.replaceChildren(); cam.value = ''; gal.value = ''; };
  const set = (file) => {
    clear(); if (!file) return;
    st.blob = file; st.url = URL.createObjectURL(file);
    prev.replaceChildren(h('img', { src: st.url, alt: 'Foto seleccionada', style: 'max-width:100%;max-height:220px;border-radius:10px;object-fit:contain;align-self:flex-start' }),
      h('button', { class: 'btn ghost sm', type: 'button', onclick: clear }, 'Quitar foto'));
  };
  cam.addEventListener('change', () => set(cam.files[0])); gal.addEventListener('change', () => set(gal.files[0]));
  const el = h('div', { style: 'display:flex;flex-direction:column;gap:8px' },
    h('div', { class: 'btn-row' }, h('button', { class: 'btn', type: 'button', onclick: () => cam.click() }, 'Tomar foto'), h('button', { class: 'btn', type: 'button', onclick: () => gal.click() }, 'Elegir de la galería')), cam, gal, prev);
  return { el, clear, set, get blob() { return st.blob; } };
}

const AI_MEAL_PROMPT = (text, hasPhoto) => `COMIDA. Eres un asistente de nutrición. Estima las calorías y macros de lo que comió una persona en México${hasPhoto ? ', usando la foto' : ''}${text ? ' y esta descripción: «' + text + '»' : ''}.
Reglas:
- Separa en renglones por alimento o preparación (máximo 12). Incluye aparte aceites, salsas, tortillas, crema y bebidas si se ven o se mencionan.
- "grams" es el peso total del renglón tal como se comió (gramos o mililitros), no por 100 g.
- Si no se indican cantidades, asume porciones típicas realistas y dilo en "note".
- Si ves un objeto de referencia (plato, tortilla, cuchara, lata, mano), úsalo para estimar el tamaño de las porciones.
- No inventes alimentos que no se mencionen ni se vean.
- "kcal" debe ser coherente con 4×proteína + 4×carbohidratos + 9×grasa.
- "confidence": "alta" si el alimento y la cantidad son claros, "media" si hay supuestos, "baja" si es una conjetura.
Responde SOLO con un objeto JSON: {"items":[{"name": string, "grams": number, "kcal": number, "protein": number, "carbs": number, "fat": number, "confidence": "alta"|"media"|"baja", "note": string}]}`;

const AI_LABEL_PROMPT = () => `ETIQUETA. La imagen muestra la tabla de información nutrimental de un producto (probablemente en español, de México). Lee los valores IMPRESOS; no estimes ni completes los que no veas.
Responde SOLO con un objeto JSON: {"readable": boolean, "name": string|null, "brand": string|null, "basis": "per100g"|"per100ml"|"perServing", "servingG": number|null, "servingLabel": string|null, "kcal": number, "protein": number, "carbs": number, "fat": number, "note": string}
- "basis" es la base de la columna que lees: por 100 g, por 100 ml o por porción. Prefiere la columna por 100 g/ml si existe.
- "servingG": peso de la porción en gramos (o ml) si está impreso.
- "kcal": contenido energético en kcal (si solo ves kJ, divide entre 4.184). "carbs": hidratos de carbono totales. "fat": grasa total (no solo saturada).
- Si la imagen no es una tabla nutrimental legible, responde {"readable": false} con ceros en los números.`;

/** Reutiliza un alimento «ai» con el mismo nombre y valores parecidos, o crea uno nuevo. */
function findOrCreateAiFood(item) {
  const per100 = { kcal: (item.kcal * 100) / item.grams, p: (item.p * 100) / item.grams, c: (item.c * 100) / item.grams, f: (item.f * 100) / item.grams };
  const key = norm(item.name);
  const same = foodList().find((f) => f.source === 'ai' && norm(f.name) === key && Math.abs(f.kcal - per100.kcal) <= 0.1 * Math.max(per100.kcal, 1));
  if (same) return same;
  const food = { id: uid(), name: item.name, brand: null, kcal: per100.kcal, p: per100.p, c: per100.c, f: per100.f, servingG: Math.round(item.grams), servingLabel: '1 porción estimada', source: 'ai', archived: false, createdAt: Date.now() };
  saveFood(food);
  return food;
}

/* ---------- toma rápida: un toque en «Foto», dispara, y la estimación empieza sola ---------- */
function quickPhoto(iso) {
  if (!S.caps.sample) { addFoodSheet(iso); return; }
  if (!S.caps.images) { aiLogSheet(iso); return; }
  const inp = h('input', { type: 'file', accept: 'image/*', capture: 'environment', hidden: true });
  document.body.append(inp);
  inp.addEventListener('change', () => { const f = inp.files[0]; inp.remove(); if (f) aiLogSheet(iso, { photo: f, auto: true }); });
  inp.addEventListener('cancel', () => inp.remove());
  inp.click();   // dentro del gesto del toque: abre la cámara
}

/* ---------- hoja: estimar la comida por foto o texto ---------- */
function aiLogSheet(iso, opts = {}) {
  openSheet('Estimar comida', (body, close) => {
    if (!S.caps.sample) { body.append(notice('warn', 'Esta función necesita Claude y no está disponible en esta vista. Ábrela desde la app de Claude, o agrega el alimento a mano.')); return; }
    const txt = h('textarea', { placeholder: 'Opcional: agrega un detalle. Ej.: con 2 cucharadas de aceite, sin tortilla…', rows: 2 });
    const photo = S.caps.images ? photoPicker() : null;
    const out = h('div', { style: 'display:flex;flex-direction:column;gap:12px' }), msg = h('div');
    let items = [], ctl = null;
    const estBtn = h('button', { class: 'btn block', type: 'button' }, 'Estimar');
    const meal = select(MEALS.map((m) => [m, MEAL_LABEL[m]]), opts.meal || mealByHour());
    const totEl = h('div', { class: 'big-total num' }), macEl = h('div', { class: 'sub num' });
    const upd = () => { const t = sumEntries(items.map((x) => ({ kcal: x.kcal, p: x.p, c: x.c, f: x.f }))); totEl.textContent = '≈ ' + fmt0(t.kcal) + ' kcal'; macEl.textContent = `Proteína ${fmt0(t.p)} g · Carbohidratos ${fmt0(t.c)} g · Grasa ${fmt0(t.f)} g`; };

    const draw = () => {
      out.replaceChildren(); if (!items.length) return;
      upd();
      out.append(h('div', { class: 'card', style: 'background:var(--bg)' }, totEl, macEl,
        h('div', { class: 'grid2', style: 'align-items:end' }, field('Comida', meal),
          h('button', { class: 'btn primary', type: 'button', onclick: () => {
            if (!items.length) return;
            const entries = items.map((it) => { const f = findOrCreateAiFood({ name: it.name, grams: it.grams, kcal: it.kcal, p: it.p, c: it.c, f: it.f });
              return { id: uid(), meal: meal.value, foodId: f.id, name: f.name, brand: null, grams: it.grams, kcal: it.kcal, p: it.p, c: it.c, f: it.f, at: Date.now(), est: true }; });
            saveDay(iso, (d) => { d.entries = (d.entries || []).concat(entries); });
            photo && photo.clear(); close(); toast(`Guardado: ≈ ${fmt0(entries.reduce((s, e) => s + e.kcal, 0))} kcal estimadas`);
          } }, 'Guardar'))),
        notice('warn', 'Es una estimación de IA. Lo que más falla son las porciones y lo que no se ve (aceite, azúcar, salsas), y suele quedarse corta. Si algo no cuadra con lo que comiste, corrige los gramos.'));
      items.forEach((it, idx) => {
        const g = numInput(Math.round(it.grams * 10) / 10, { step: '5', min: 0 }); g.style.maxWidth = '110px'; g.setAttribute('aria-label', 'Gramos de ' + it.name);
        const kc = h('div', { class: 'end num' }, fmt0(it.kcal) + ' kcal');
        g.addEventListener('input', () => { const v = num(g.value); if (v > 0) { const k = v / it.base.grams; Object.assign(it, { grams: v, kcal: it.base.kcal * k, p: it.base.p * k, c: it.base.c * k, f: it.base.f * k }); kc.textContent = fmt0(it.kcal) + ' kcal'; upd(); } });
        out.append(h('div', { class: 'card', style: 'background:var(--bg);gap:8px' },
          h('div', { style: 'display:flex;justify-content:space-between;gap:8px;align-items:flex-start' }, h('div', { class: 'name', style: 'font-weight:600;overflow-wrap:anywhere' }, it.name, h('span', { class: 'tag' + (it.confidence === 'baja' ? ' warn' : '') }, 'confianza ' + it.confidence)),
            h('button', { class: 'btn ghost sm', type: 'button', 'aria-label': 'Quitar ' + it.name, onclick: () => { items.splice(idx, 1); draw(); } }, 'Quitar')),
          it.note ? h('div', { class: 'sub' }, it.note) : null, it.adjusted ? h('div', { class: 'sub' }, 'Ajusté las calorías para que cuadren con los macros.') : null,
          h('div', { style: 'display:flex;gap:12px;align-items:center;justify-content:space-between' }, h('div', { style: 'display:flex;gap:6px;align-items:center' }, g, h('span', { class: 'muted' }, 'g')), kc),
          h('div', { class: 'sub num' }, `P ${fmt1(it.p)} · C ${fmt1(it.c)} · G ${fmt1(it.f)} g`)));
      });
    };

    const run = async () => {
      const text = txt.value.trim(), blob = photo ? photo.blob : null;
      msg.replaceChildren();
      if (!text && !blob) { msg.append(notice('warn', 'Toma una foto o escribe lo que comiste.')); return; }
      ctl = new AbortController(); estBtn.disabled = true; items = []; draw();
      estBtn.replaceChildren(h('span', { class: 'spin' }), ' Estimando…');
      msg.append(h('div', { style: 'display:flex;align-items:center;gap:10px' }, h('span', { class: 'spin' }), h('span', null, blob ? 'Analizando tu foto…' : 'Estimando…'), h('button', { class: 'btn ghost sm', type: 'button', onclick: () => ctl.abort() }, 'Cancelar')));
      try {
        const raw = await askAi(AI_MEAL_PROMPT(text, !!blob), blob, ctl);
        items = normalizeAiItems(raw).map((x) => ({ ...x, base: { grams: x.grams, kcal: x.kcal, p: x.p, c: x.c, f: x.f } }));
        msg.replaceChildren(); if (!items.length) msg.append(notice('warn', 'No pude sacar alimentos de eso. Prueba con una foto más clara o describe lo que comiste.'));
        draw(); if (items.length) estBtn.replaceChildren('Estimar de nuevo');
      } catch (e) { msg.replaceChildren(); const t = aiErrorNote(e); if (t) msg.append(notice('bad', t)); estBtn.replaceChildren('Estimar'); }
      finally { estBtn.disabled = false; }
    };
    estBtn.onclick = run;
    body.append(out, msg, photo ? photo.el : null, field('Detalle (opcional)', txt, 'También puedes dictarlo con el micrófono del teclado.'), estBtn);
    if (opts.photo && photo) photo.set(opts.photo);
    if (opts.auto) setTimeout(run, 0); else setTimeout(() => (photo ? null : txt.focus()), 60);
  });
}

/* ---------- foto de etiqueta nutrimental (dentro del formulario de alimento) ---------- */
function labelReader(fields, setSource, msg) {
  const photo = photoPicker();
  const btn = h('button', { class: 'btn block', type: 'button' }, 'Leer la etiqueta de la foto');
  btn.onclick = async () => {
    if (!photo.blob) { msg.replaceChildren(notice('warn', 'Primero toma o elige una foto de la tabla nutrimental.')); return; }
    const ctl = new AbortController(); btn.disabled = true; btn.replaceChildren(h('span', { class: 'spin' }), ' Leyendo…'); msg.replaceChildren();
    try {
      const raw = await askAi(AI_LABEL_PROMPT(), photo.blob, ctl);
      if (!raw || raw.readable === false) { msg.replaceChildren(notice('warn', 'No pude leer una tabla nutrimental en esa foto. Acércate, evita reflejos y que salga completa.')); return; }
      const r = labelToPer100(raw);
      if (!r.ok) { msg.replaceChildren(notice('bad', r.reason === 'no_serving' ? 'La tabla está por porción y no pude leer cuántos gramos tiene la porción. Escribe los valores a mano.' : r.reason === 'implausible' ? 'Los valores que leí no son plausibles (probablemente leí mal). Captura los valores a mano o toma otra foto.' : 'No pude leer los valores. Toma otra foto o captura a mano.')); return; }
      const rd = (v) => Math.round(v * 10) / 10;
      fields.k.value = rd(r.kcal); fields.p.value = rd(r.p); fields.c.value = rd(r.c); fields.f.value = rd(r.f);
      if (r.servingG && !fields.sg.value) { fields.sg.value = Math.round(r.servingG * 10) / 10; if (r.servingLabel && !fields.sl.value) fields.sl.value = r.servingLabel; }
      if (raw.name && !fields.nm.value.trim()) fields.nm.value = String(raw.name).slice(0, 80);
      if (raw.brand && !fields.br.value.trim()) fields.br.value = String(raw.brand).slice(0, 60);
      setSource('label');
      msg.replaceChildren(notice(r.mismatch ? 'warn' : 'info', r.mismatch ? 'Leí estos valores, pero las calorías no cuadran con los macros: probablemente leí mal algún número. Compáralos con la etiqueta.' : 'Leí estos valores de la foto. Compáralos con la etiqueta antes de guardar: una lectura puede fallar.',
        r.perMl ? ' Ojo: la tabla estaba por 100 ml; los trato como por 100 g (aproximado en líquidos).' : ''));
    } catch (e) { const t = aiErrorNote(e); msg.replaceChildren(t ? notice('bad', t) : null); }
    finally { btn.disabled = false; btn.replaceChildren('Leer la etiqueta de la foto'); }
  };
  return h('div', { class: 'card', style: 'background:var(--bg)' }, h('h3', null, 'Desde la etiqueta'), h('p', { class: 'sub' }, 'Toma una foto de la tabla nutrimental. Lee los números impresos, así que es mucho más exacto que estimar un platillo.'), photo.el, btn);
}

/* ---------- agua ---------- */
const fmtWater = (ml) => (ml >= 1000 ? (ml / 1000).toLocaleString('es-MX', { maximumFractionDigits: 2 }) + ' L' : Math.round(ml) + ' ml');
function waterCard(iso, day) {
  const ml = isNum(day.water) ? day.water : 0, goal = S.profile && isNum(S.profile.waterMl) ? S.profile.waterMl : 2000;
  const add = (d) => saveDay(iso, (x) => { x.water = Math.max(0, (isNum(x.water) ? x.water : 0) + d); });
  return h('section', { class: 'card', 'aria-label': 'Agua' }, h('div', { class: 'card-title' }, h('h2', null, 'Agua'), h('span', { class: 'sub num' }, `${fmtWater(ml)} de ${fmtWater(goal)}`)),
    h('div', { class: 'meter', role: 'progressbar', 'aria-valuenow': Math.round(Math.min(1, ml / goal) * 100), 'aria-valuemin': 0, 'aria-valuemax': 100 }, h('i', { style: `width:${Math.min(100, (ml / goal) * 100)}%` })),
    h('div', { class: 'btn-row tight' }, [[250, '+250 ml'], [500, '+500 ml'], [1000, '+1 L']].map(([v, l]) => h('button', { class: 'btn sm', type: 'button', onclick: () => add(v) }, l)),
      ml > 0 ? h('button', { class: 'btn ghost sm', type: 'button', 'aria-label': 'Quitar 250 ml', onclick: () => add(-250) }, '−250') : null));
}

/* ---------- ejercicio (solo registro: no se suma a la meta) ---------- */
function exerciseCard(iso, day) {
  const list = day.exercise || [], totalMin = list.reduce((s, e) => s + e.min, 0);
  return h('details', { class: 'card', open: list.length ? true : null }, h('summary', null, 'Ejercicio' + (list.length ? ' · ' + totalMin + ' min' : '')),
    list.length ? h('div', { class: 'list' }, list.map((e) => h('button', { class: 'row', type: 'button', onclick: () => exerciseSheet(iso, e.id) },
      h('div', { class: 'main' }, h('div', { class: 'name' }, e.name), h('div', { class: 'meta num' }, `${e.min} min${isNum(e.kcal) ? ' · ' + fmt0(e.kcal) + ' kcal (tu cálculo)' : ''}`)), h('div', { class: 'end chev' }, icon('chevR')))))
      : h('p', { class: 'sub' }, 'Sin ejercicio registrado este día.'),
    h('button', { class: 'btn block', type: 'button', onclick: () => exerciseSheet(iso, null) }, '+ Registrar ejercicio'),
    h('p', { class: 'sub' }, 'Se guarda como referencia y no se suma a tu meta de calorías: las calorías que dicen los relojes y las apps varían mucho, y «comérselas» de vuelta suele borrar el déficit.'));
}
function exerciseSheet(iso, id) {
  const ex = id ? ((S.days[iso] || {}).exercise || []).find((e) => e.id === id) : null;
  openSheet(ex ? 'Editar ejercicio' : 'Registrar ejercicio', (body, close) => {
    const dl = h('datalist', { id: 'ex-names' }, ['Caminata', 'Correr', 'Pesas', 'Bicicleta', 'Natación', 'Fútbol', 'Yoga', 'Baile'].map((n) => h('option', { value: n })));
    const nm = h('input', { type: 'text', value: ex ? ex.name : '', list: 'ex-names', placeholder: 'Caminata, pesas…', autocomplete: 'off' });
    const mn = numInput(ex ? ex.min : '', { step: '5', min: 1, max: 600, placeholder: 'minutos' }), kc = numInput(ex && isNum(ex.kcal) ? ex.kcal : '', { step: '10', min: 0, max: 3000, placeholder: 'opcional' });
    const msg = h('div');
    body.append(field('Actividad', nm), dl, h('div', { class: 'grid2' }, field('Duración (min)', mn), field('Calorías (opcional)', kc)), msg,
      h('div', { class: 'btn-row' }, ex ? h('button', { class: 'btn danger', type: 'button', onclick: () => { saveDay(iso, (d) => { d.exercise = (d.exercise || []).filter((e) => e.id !== id); }); close(); } }, 'Borrar') : null,
        h('button', { class: 'btn primary', type: 'button', onclick: () => {
          const name = nm.value.trim(), m = num(mn.value), k = num(kc.value);
          if (!name) return msg.replaceChildren(notice('bad', 'Escribe qué hiciste.'));
          if (!(m >= 1 && m <= 600)) return msg.replaceChildren(notice('bad', 'La duración debe estar entre 1 y 600 minutos.'));
          if (k != null && !(k >= 0 && k <= 3000)) return msg.replaceChildren(notice('bad', 'Las calorías deben estar entre 0 y 3,000.'));
          const rec = { id: ex ? ex.id : uid(), name, min: m, kcal: k };
          saveDay(iso, (d) => { d.exercise = ex ? d.exercise.map((e) => (e.id === id ? rec : e)) : (d.exercise || []).concat(rec); });
          close(); toast('Ejercicio guardado');
        } }, 'Guardar')));
    setTimeout(() => nm.focus(), 60);
  });
}
