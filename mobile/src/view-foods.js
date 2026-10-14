/* ===== VISTA ALIMENTOS Y RECETAS ===== */
function recipePer100(items, yieldG) {
  let t = { kcal: 0, p: 0, c: 0, f: 0 };
  for (const it of items) { const f = S.foods[it.foodId]; if (!f) continue; const m = per(f, it.grams); t = { kcal: t.kcal + m.kcal, p: t.p + m.p, c: t.c + m.c, f: t.f + m.f }; }
  const k = 100 / yieldG;
  return { kcal: t.kcal * k, p: t.p * k, c: t.c * k, f: t.f * k };
}
function recipeDependsOn(rootId, targetId, seen = new Set()) {
  if (seen.has(rootId)) return false; seen.add(rootId);
  const r = S.foods[rootId]; if (!r || !r.recipe) return false;
  return r.recipe.items.some((i) => i.foodId === targetId || recipeDependsOn(i.foodId, targetId, seen));
}
function recomputeDependents(foodId, seen = new Set()) {
  for (const r of foodList()) {
    if (!r.recipe || seen.has(r.id) || !r.recipe.items.some((i) => i.foodId === foodId)) continue;
    seen.add(r.id);
    const m = recipePer100(r.recipe.items, r.recipe.yieldG), sg = r.recipe.yieldG / r.recipe.servings;
    saveFood({ ...r, kcal: m.kcal, p: m.p, c: m.c, f: m.f, servingG: sg, servingLabel: `1 porción (~${Math.round(sg)} g)` });
    recomputeDependents(r.id, seen);
  }
}

function openRecipeEditor(existing) {
  const draft = existing ? { id: existing.id, name: existing.name, items: clone(existing.recipe.items), yieldG: existing.recipe.yieldG, servings: existing.recipe.servings }
    : { id: uid(), name: '', items: [], yieldG: null, servings: 1 };
  openSheet(existing ? 'Editar receta' : 'Nueva receta', (body, close) => {
    const nm = h('input', { type: 'text', value: draft.name, placeholder: 'Tacos de frijol con queso', autocomplete: 'off' });
    nm.addEventListener('input', () => { draft.name = nm.value; });
    const q = h('input', { type: 'search', placeholder: 'Buscar ingrediente en tus alimentos…', autocomplete: 'off', 'aria-label': 'Buscar ingrediente' });
    const results = h('div', { class: 'list' }), itemsBox = h('div'), preview = h('div', { class: 'sub num' }), msg = h('div');
    const yieldIn = numInput(draft.yieldG, { step: '5', min: 0 }), servIn = numInput(draft.servings, { step: '0.5', min: 0 });
    let yieldTouched = !!existing;
    yieldIn.addEventListener('input', () => { yieldTouched = true; draw(); }); servIn.addEventListener('input', draw);
    const rawTotal = () => draft.items.reduce((s, i) => s + i.grams, 0);

    function showResults() {
      results.replaceChildren();
      const query = q.value.trim(); if (!query) return;
      const found = searchFoods(query, { exclude: draft.id, limit: 6 }).filter((f) => !(f.recipe && recipeDependsOn(f.id, draft.id)));
      if (!found.length) { results.append(h('div', { class: 'sub', style: 'padding:8px 0' }, 'Sin resultados. Crea el ingrediente en la pestaña Alimentos y vuelve.')); return; }
      found.forEach((f) => results.append(h('button', { class: 'row', type: 'button', onclick: () => choose(f) },
        h('div', { class: 'main' }, h('div', { class: 'name' }, foodLabel(f)), h('div', { class: 'meta num' }, fmt0(f.kcal) + ' kcal por 100 g')), h('div', { class: 'end' }, '+'))));
    }
    function choose(f) {
      results.replaceChildren();
      const g = numInput(100, { step: '5', min: 0 });
      results.append(h('div', { class: 'card', style: 'background:var(--bg)' }, h('b', null, f.name), field('Gramos (peso crudo)', g),
        h('div', { class: 'btn-row' }, h('button', { class: 'btn', type: 'button', onclick: showResults }, 'Atrás'),
          h('button', { class: 'btn primary', type: 'button', onclick: () => { const v = num(g.value); if (!(v > 0)) { toast('Escribe los gramos.'); return; } draft.items.push({ foodId: f.id, grams: v }); q.value = ''; results.replaceChildren(); draw(); } }, 'Agregar'))));
      g.focus();
    }
    q.addEventListener('input', showResults);

    function draw() {
      itemsBox.replaceChildren();
      if (!draft.items.length) itemsBox.append(h('p', { class: 'sub' }, 'Aún no hay ingredientes. Busca arriba y agrégalos con su peso crudo.'));
      draft.items.forEach((it, idx) => {
        const f = S.foods[it.foodId];
        const g = numInput(Math.round(it.grams * 10) / 10, { step: '5', min: 0 }); g.style.maxWidth = '110px'; g.setAttribute('aria-label', 'Gramos de ' + (f ? f.name : 'ingrediente'));
        g.addEventListener('input', () => { const v = num(g.value); if (v > 0) { it.grams = v; refreshPreview(); } });
        itemsBox.append(h('div', { class: 'row', style: 'cursor:default' }, h('div', { class: 'main' }, h('div', { class: 'name' }, f ? f.name : '(alimento eliminado)'), h('div', { class: 'meta' }, f ? fmt0(f.kcal) + ' kcal / 100 g' : '')), g,
          h('button', { class: 'btn ghost sm', type: 'button', 'aria-label': 'Quitar', onclick: () => { draft.items.splice(idx, 1); draw(); } }, 'Quitar')));
      });
      if (!yieldTouched) yieldIn.value = draft.items.length ? Math.round(rawTotal()) : '';
      refreshPreview();
    }
    function refreshPreview() {
      const y = num(yieldIn.value) || rawTotal(), sv = num(servIn.value) || 1;
      if (!draft.items.length || !(y > 0)) { preview.textContent = ''; return; }
      const m = recipePer100(draft.items, y), s = per(m, y / sv);
      preview.textContent = `Por 100 g: ${fmt0(m.kcal)} kcal · P ${fmt1(m.p)} · C ${fmt1(m.c)} · G ${fmt1(m.f)}   |   Por porción (~${fmt0(y / sv)} g): ${fmt0(s.kcal)} kcal · P ${fmt1(s.p)} · C ${fmt1(s.c)} · G ${fmt1(s.f)}`;
    }
    body.append(field('Nombre de la receta', nm), h('h3', null, 'Ingredientes'), q, results, itemsBox,
      h('div', { class: 'grid2' }, field('Peso final del platillo (g)', yieldIn, 'Pésalo ya cocido; si pierde agua, las macros por 100 g suben.'), field('Porciones que rinde', servIn)), preview, msg,
      h('div', { class: 'btn-row' },
        existing ? h('button', { class: 'btn danger', type: 'button', onclick: () => {
          if (foodUsed(existing.id)) { saveFood({ ...existing, archived: true }); toast('Receta archivada: ya está en tu registro.', 3600); } else { removeFood(existing.id); toast('Receta eliminada'); }
          close();
        } }, 'Borrar / archivar') : null,
        h('button', { class: 'btn primary', type: 'button', onclick: () => {
          const y = num(yieldIn.value) || rawTotal(), sv = num(servIn.value);
          const fail = (t) => msg.replaceChildren(notice('bad', t));
          if (!draft.name.trim()) return fail('La receta necesita un nombre.');
          if (!draft.items.length) return fail('Agrega al menos un ingrediente.');
          if (!(y > 0) || !(sv > 0)) return fail('El peso final y las porciones deben ser mayores que 0.');
          const m = recipePer100(draft.items, y), sg = y / sv;
          const food = { id: draft.id, name: draft.name.trim(), brand: null, kcal: m.kcal, p: m.p, c: m.c, f: m.f, servingG: sg, servingLabel: `1 porción (~${Math.round(sg)} g)`,
            source: 'recipe', archived: false, recipe: { items: draft.items, yieldG: y, servings: sv }, createdAt: existing ? existing.createdAt : Date.now() };
          const errs = validateFood(food); if (errs.length) return fail('Los valores de la receta no son plausibles: ' + errs.join(' '));
          saveFood(food); recomputeDependents(food.id); close(); toast('Receta guardada');
        } }, 'Guardar receta')));
    draw();
  });
}

function viewFoods() {
  const root = h('div', { style: 'display:flex;flex-direction:column;gap:14px' });
  root.append(h('div', { class: 'card-title' }, h('h2', null, 'Mis alimentos'), h('span', { class: 'sub' }, foodList().filter((f) => !f.archived).length + ' guardados')),
    h('div', { class: 'btn-row' },
      h('button', { class: 'btn primary', type: 'button', onclick: () => openFoodForm(null) }, '+ Alimento'),
      h('button', { class: 'btn', type: 'button', onclick: () => openRecipeEditor(null) }, '+ Receta')));
  const q = h('input', { type: 'search', placeholder: 'Buscar entre tus alimentos…', autocomplete: 'off', 'aria-label': 'Buscar', value: S.foodQuery || '' });
  const chips = h('div', { class: 'chips', role: 'group' }, [['all', 'Todos'], ['custom', 'Míos'], ['recipe', 'Recetas'], ['ai', 'Estimados por IA']].map(([v, l]) =>
    h('button', { class: 'chip', type: 'button', 'aria-pressed': String(S.foodFilter === v), onclick: () => { S.foodFilter = v; render(); } }, l)));
  const list = h('div', { class: 'list' });
  const draw = () => {
    S.foodQuery = q.value;
    const tokens = norm(q.value).split(' ').filter(Boolean);
    const items = foodList().filter((f) => (S.showArchived || !f.archived) && (S.foodFilter === 'all' || f.source === S.foodFilter) && tokens.every((t) => norm(f.name + ' ' + (f.brand || '')).includes(t)))
      .sort((a, b) => norm(a.name).localeCompare(norm(b.name)));
    list.replaceChildren();
    if (!items.length) list.append(h('div', { class: 'empty' }, h('span', null, foodList().length ? 'Nada coincide con tu búsqueda.' : 'Aquí vivirán tus alimentos y recetas. Crea el primero con «+ Alimento».')));
    items.forEach((f) => list.append(h('button', { class: 'row', type: 'button', onclick: () => (f.recipe ? openRecipeEditor(f) : openFoodForm(f)) },
      h('div', { class: 'main' }, h('div', { class: 'name' }, foodLabel(f), f.archived ? h('span', { class: 'tag' }, 'archivado') : null),
        h('div', { class: 'meta num' }, `P ${fmt1(f.p)} · C ${fmt1(f.c)} · G ${fmt1(f.f)} por 100 g${f.servingG ? ' · porción ' + fmt0(f.servingG) + ' g' : ''}`)),
      h('div', { class: 'end' }, fmt0(f.kcal) + ' kcal'))));
  };
  q.addEventListener('input', draw);
  root.append(q, chips, h('section', { class: 'card' }, list));
  draw();
  root.append(h('label', { class: 'check' }, h('input', { type: 'checkbox', checked: S.showArchived, onchange: (e) => { S.showArchived = e.target.checked; render(); } }), h('span', null, 'Mostrar archivados')),
    notice('info', 'En esta versión no hay búsqueda en Open Food Facts (la página no puede salir a internet). Tus alimentos se guardan aquí, y al crear uno puedes pedirle a Claude una estimación de macros, que queda marcada como estimada.'));
  return root;
}
