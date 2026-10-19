/* ===== VISTA METAS: perfil, meta por fórmula y adaptación ===== */
function viewGoals() {
  const p = S.profile, body = bodyState(), today = todayIso(), root = h('div', { style: 'display:flex;flex-direction:column;gap:14px' });
  root.append(h('div', null, h('h2', null, 'Perfil y metas'), h('p', { class: 'sub' }, 'Las fórmulas son solo el punto de partida; con tus datos reales la app estima tu gasto verdadero.')));
  if (!p) root.append(notice('info', 'Empieza aquí: llena tu perfil y tu peso. Con eso calculo tu meta inicial.'));

  /* formulario de perfil */
  const sexV = { v: p ? p.sex : 'M' };
  const birth = h('input', { type: 'date', value: p ? p.birth : '', max: today });
  const height = numInput(p ? p.heightCm : '', { step: '0.5', min: 120, max: 230, placeholder: 'cm' });
  const activity = select(Object.entries(ACTIVITY_LABEL), p ? p.activity : 'light');
  const goalSel = select(Object.entries(GOAL_LABEL), p ? p.goal : 'maintain');
  const rate = numInput(p ? p.rate : 0.25, { step: '0.05', min: 0, max: 1.5 });
  const weight = numInput('', { step: '0.1', min: 30, max: 300, placeholder: body.weight ? 'último: ' + fmt1(body.weight) : 'obligatorio la 1.ª vez' });
  const bf = numInput('', { step: '0.1', min: 3, max: 60, placeholder: body.bf ? 'último: ' + fmt1(body.bf) : 'si no lo conoces, déjalo vacío' });
  const bfSrc = select([['self_estimate', 'estimado por ti'], ['measured', 'medido (báscula, plicómetro, DEXA…)']], 'self_estimate');
  const pMin = numInput(p ? p.pMin : 1.6, { step: '0.1', min: 0.5, max: 4 }), pMax = numInput(p ? p.pMax : 2.2, { step: '0.1', min: 0.5, max: 4 });
  const fatMin = numInput(p ? p.fatMin : 0.6, { step: '0.1', min: 0, max: 2 }), fatPct = numInput(p ? Math.round(p.fatPct * 100) : 25, { step: '1', min: 0, max: 60 });
  const minK = numInput(p ? p.minValidKcal : CFG.defaultMinValidKcal, { step: '50', min: 0 });
  const waterIn = numInput(p && isNum(p.waterMl) ? p.waterMl : 2000, { step: '250', min: 500, max: 6000 });
  const mif = h('input', { type: 'checkbox', id: 'mif', checked: !!(p && p.mifflinOnly) });
  const msg = h('div');
  const form = h('details', { class: 'card', open: !p ? true : null }, h('summary', null, p ? 'Editar mi perfil' : 'Mi perfil'),
    h('div', { class: 'field' }, h('span', { class: 'lbl' }, 'Sexo'), segmented([['M', 'Hombre'], ['F', 'Mujer']], sexV.v, (v) => { sexV.v = v; })),
    h('div', { class: 'grid2' }, field('Fecha de nacimiento', birth), field('Estatura (cm)', height)),
    field('Nivel de actividad', activity), h('div', { class: 'grid2' }, field('Objetivo', goalSel), field('Ritmo (kg/semana)', rate, 'Se ignora al mantener. Razonable: 0.25–0.5 al perder; 0.1–0.25 al ganar masa.')),
    h('p', { class: 'lbl', style: 'margin-top:2px' }, 'Peso y composición actuales (se guardan como el registro de hoy)'),
    h('div', { class: 'grid2' }, field('Peso (kg)', weight), field('% de grasa (opcional)', bf)), field('Origen del % de grasa', bfSrc, 'Sé honesto con el origen: una estimación a ojo no tiene la precisión de una medición.'),
    h('details', null, h('summary', null, 'Opciones avanzadas'),
      h('div', { style: 'display:flex;flex-direction:column;gap:12px;padding-top:6px' },
        h('div', { class: 'grid2' }, field('Proteína mín. (g/kg)', pMin), field('Proteína máx. (g/kg)', pMax)),
        h('div', { class: 'grid2' }, field('Grasa mínima (g/kg)', fatMin), field('Grasa objetivo (% de las kcal)', fatPct, 'La grasa será el mayor entre este % y el mínimo por kg; el resto son carbohidratos.')),
        field('Meta de agua (ml/día)', waterIn, 'Solo una referencia tuya para la barra de agua.'),
        field('Calorías mínimas para contar un día', minK, 'Un día con menos calorías registradas se considera incompleto y no entra al promedio que estima tu gasto.'),
        h('label', { class: 'check', for: 'mif' }, mif, h('span', null, 'Usar siempre Mifflin-St Jeor (ignorar mi % de grasa en el cálculo). Útil si ese % es solo una estimación.')))),
    msg, h('button', { class: 'btn primary block', type: 'button', onclick: () => {
      const fail = (t) => msg.replaceChildren(notice('bad', t));
      const ht = num(height.value), wv = num(weight.value), bfv = num(bf.value), rt = num(rate.value) ?? 0, lo = num(pMin.value), hi = num(pMax.value), fm = num(fatMin.value), fp = num(fatPct.value), mk = num(minK.value), wm = num(waterIn.value);
      if (!birth.value) return fail('Falta tu fecha de nacimiento.');
      const age = ageOn(birth.value, today); if (age < 14 || age > 100) return fail('Revisa la fecha de nacimiento (la edad debe estar entre 14 y 100 años).');
      if (!(ht >= 120 && ht <= 230)) return fail('La estatura debe estar entre 120 y 230 cm.');
      if (wv == null && body.weight == null) return fail('Necesito al menos un peso para calcular tus metas.');
      if (wv != null && !(wv >= 30 && wv <= 300)) return fail('El peso debe estar entre 30 y 300 kg.');
      if (bfv != null && !(bfv >= 3 && bfv <= 60)) return fail('El % de grasa debe estar entre 3 y 60.');
      if (!(rt >= 0 && rt <= 1.5)) return fail('El ritmo debe estar entre 0 y 1.5 kg/semana.');
      if (!(lo > 0 && hi >= lo)) return fail('La proteína máxima no puede ser menor que la mínima.');
      if (fm == null || fm < 0 || fp == null || fp < 0 || fp >= 100 || mk == null || mk < 0) return fail('Revisa las opciones avanzadas: hay valores vacíos o fuera de rango.');
      const hadTarget = S.targets.length > 0;
      saveProfile({ sex: sexV.v, birth: birth.value, heightCm: ht, activity: activity.value, goal: goalSel.value, rate: goalSel.value === 'maintain' ? 0 : rt, pMin: lo, pMax: hi, fatMin: fm, fatPct: fp / 100, minValidKcal: mk, mifflinOnly: mif.checked, waterMl: wm >= 500 && wm <= 6000 ? wm : 2000 });
      if (wv != null || bfv != null) saveDay(today, (d) => { if (wv != null) d.weight = wv; if (bfv != null) { d.bf = bfv; d.bfSource = bfSrc.value; } });
      if (!hadTarget) { const pl = buildPlan(); if (pl) { saveTarget(pl, pl.calories.kcal, 'formula', 'Meta inicial por fórmula'); toast('Perfil guardado y meta inicial creada.'); return; } }
      toast('Perfil guardado.');
    } }, p ? 'Guardar cambios' : 'Guardar perfil'));
  root.append(form);

  const plan = buildPlan(today);
  if (!plan) { if (p) root.append(notice('info', 'Falta un peso para calcular tus metas. Regístralo en «Hoy» o en el perfil.')); return root; }

  /* meta por fórmula */
  const card = h('section', { class: 'card' }, h('h2', null, 'Meta por fórmula'));
  card.append(plan.bmr.method === 'katch_mcardle'
    ? notice('info', 'Gasto basal calculado con ', h('b', null, 'Katch-McArdle'), ', porque hay un % de grasa registrado (', fmt1(plan.body.bf), ' %).')
    : notice('info', 'Gasto basal calculado con ', h('b', null, 'Mifflin-St Jeor'), plan.profile.mifflinOnly ? ' (lo forzaste).' : ' (no hay % de grasa registrado).'));
  card.append(h('div', { class: 'kpis' },
    h('div', { class: 'kpi' }, h('div', { class: 'l' }, 'Gasto basal'), h('div', { class: 'v num' }, fmt0(plan.bmr.kcal) + ' kcal')),
    h('div', { class: 'kpi' }, h('div', { class: 'l' }, 'Gasto total estimado'), h('div', { class: 'v num' }, fmt0(plan.tdee) + ' kcal')),
    h('div', { class: 'kpi', style: 'grid-column:1/-1' }, h('div', { class: 'l' }, 'Meta calórica'), h('div', { class: 'v num' }, fmt0(plan.calories.kcal) + ' kcal'),
      h('div', { class: 'sub num' }, `${plan.calories.adjustment >= 0 ? '+' : '−'}${fmt0(Math.abs(plan.calories.adjustment))} kcal respecto al gasto`))));
  plan.notes.forEach((c) => card.append(notice(c === 'floor_applied' || c === 'no_recent_weight' ? 'warn' : 'info', PLAN_NOTES[c](plan))));
  plan.macros.flags.forEach((fl) => card.append(notice('warn', MACRO_FLAG_TEXT[fl])));
  const m = plan.macros;
  card.append(h('div', { class: 'list' },
    ...[['Proteína', m.protein, `rango ${fmt0(m.proteinRange[0])}–${fmt0(m.proteinRange[1])} g (${plan.profile.pMin}–${plan.profile.pMax} g/kg sobre ${fmt1(plan.ref)} kg)`],
      ['Grasa', m.fat, `mínimo ${fmt0(m.fatFloor)} g (${plan.profile.fatMin} g/kg)`], ['Carbohidratos', m.carbs, 'el resto de las calorías']]
      .map(([l, v, d]) => h('div', { class: 'row', style: 'cursor:default' }, h('div', { class: 'main' }, h('div', { class: 'name' }, l), h('div', { class: 'meta' }, d)), h('div', { class: 'end' }, fmt0(v) + ' g')))));
  if (plan.ref < plan.body.weight - 0.05) card.append(h('p', { class: 'sub' }, 'La proteína se calcula sobre un peso de referencia menor que tu peso real porque tu % de grasa es alto, para que el rango en g/kg no se infle por la grasa corporal.'));
  const active = targetOn(today);
  const srcL = { formula: 'fórmula', data: 'ajuste por datos', manual: 'manual' };
  card.append(active ? h('p', { class: 'sub' }, `Meta vigente desde ${fmtDMY(active.from)}: `, h('b', null, fmt0(active.kcal) + ' kcal'), ` (P ${fmt0(active.p)} · C ${fmt0(active.c)} · G ${fmt0(active.f)} g; origen: ${srcL[active.source]}).`)
    : notice('warn', 'Todavía no tienes una meta vigente. Establece la calculada para registrar contra ella.'));
  card.append(h('button', { class: active ? 'btn block' : 'btn primary block', type: 'button', onclick: () => { saveTarget(plan, plan.calories.kcal, 'formula', 'Calculada por fórmula'); toast('Meta vigente actualizada.'); } }, 'Establecer esta meta como vigente'));
  const man = numInput(Math.round(plan.calories.kcal / 10) * 10, { step: '10', min: 800, max: 6000 });
  const manMsg = h('div');
  card.append(h('details', null, h('summary', null, 'Fijar una meta calórica manualmente'), h('div', { style: 'display:flex;flex-direction:column;gap:10px;padding-top:6px' }, field('Calorías por día', man), manMsg,
    h('button', { class: 'btn block', type: 'button', onclick: () => {
      const v = num(man.value); if (!(v >= 800 && v <= 6000)) { manMsg.replaceChildren(notice('bad', 'Escribe un valor entre 800 y 6,000 kcal.')); return; }
      if (v < plan.bmr.kcal) toast(`Ojo: está por debajo de tu gasto basal estimado (${fmt0(plan.bmr.kcal)} kcal).`, 4200);
      saveTarget(plan, v, 'manual', 'Fijada manualmente'); toast('Meta manual guardada.');
    } }, 'Guardar meta manual'))));
  root.append(card);

  /* adaptación */
  const ad = h('section', { class: 'card' }, h('h2', null, 'Adaptación con tus datos'));
  ad.append(h('div', { class: 'field' }, h('span', { class: 'lbl' }, 'Ventana de análisis (días)'),
    h('div', { class: 'chips' }, [14, 21, 28, 42].map((w) => h('button', { class: 'chip', type: 'button', 'aria-pressed': String(S.tdeeWindow === w), onclick: () => { S.tdeeWindow = w; render(); } }, String(w)))),
    h('div', { class: 'hint' }, 'Ventanas largas dan más precisión pero menos actualidad. El día en curso no cuenta porque suele estar incompleto.')));
  const st = adaptiveStatus(plan, S.tdeeWindow), d = st.data;
  const share = estimatedShare(S.days, st.windowStart, st.windowEnd);
  if (share > 0.3) ad.append(notice('warn', `${Math.round(share * 100)} % de las calorías de esta ventana son estimaciones de IA. Esas entradas suelen quedarse cortas, y eso hace que el gasto «por datos» salga más bajo que el real. Interpreta el resultado con cuidado.`));
  else if (share > 0) ad.append(h('p', { class: 'sub' }, `${Math.round(share * 100)} % de las calorías de esta ventana son estimaciones de IA.`));
  ad.append(h('div', { class: 'kpis' },
    h('div', { class: 'kpi' }, h('div', { class: 'l' }, 'Gasto por fórmula'), h('div', { class: 'v num' }, fmt0(plan.tdee) + ' kcal')),
    h('div', { class: 'kpi' }, h('div', { class: 'l' }, 'Gasto por datos'), h('div', { class: 'v num' }, d.ok ? fmt0(d.tdee) + ' kcal' : 'Sin datos'),
      d.ok ? h('div', { class: 'sub num' }, `± ${fmt0(d.ciHalf)} (IC 95 %) · confianza ${CONF_LABEL[d.confidence]}`) : h('div', { class: 'sub' }, 'insuficientes'))));
  if (!d.ok) {
    ad.append(notice('warn', 'Todavía no hay suficientes registros para estimar tu gasto real, así que no muestro ningún número (con pocos datos sería falsa precisión). Qué falta:'));
    ad.append(h('ul', { style: 'margin:0;padding-left:20px;display:flex;flex-direction:column;gap:4px' }, d.reasons.map((r) => h('li', null, REASON_TEXT[r](d)))));
    const bar = (v, mx, label) => h('div', { style: 'display:flex;flex-direction:column;gap:4px' }, h('div', { class: 'sub' }, label), h('div', { class: 'meter' }, h('i', { style: `width:${Math.min(100, (v / mx) * 100)}%` })));
    ad.append(bar(d.nFood, CFG.minFoodDays, `Días con comida: ${d.nFood}/${CFG.minFoodDays}`), bar(d.nWeighings, CFG.minWeighings, `Pesajes: ${d.nWeighings}/${CFG.minWeighings}`),
      h('p', { class: 'sub' }, `Ventana evaluada: ${fmtDMY(st.windowStart)} – ${fmtDMY(st.windowEnd)}.`));
  } else {
    ad.append(h('p', { class: 'sub' }, `Ventana ${fmtDMY(st.windowStart)} – ${fmtDMY(st.windowEnd)} · ${d.nFood} días de comida · ${d.nWeighings} pesajes · ingesta promedio ${fmt0(d.avgIntake)} kcal · tendencia de peso ${d.slope * 7 >= 0 ? '+' : '−'}${Math.abs(d.slope * 7).toFixed(2)} kg/semana.`));
    if (d.confidence === 'low') ad.append(notice('warn', `Confianza baja: el intervalo (±${fmt0(d.ciHalf)} kcal) es amplio, típico de ventanas cortas o de peso muy variable. Tómalo como una pista, no como una medición; se afina con más semanas de registro.`));
    const rec = st.rec;
    if (rec.status === 'keep') {
      ad.append(d.confidence === 'high'
        ? notice('good', `Tu meta vigente (${fmt0(st.current)} kcal) es coherente con tu gasto real estimado (diferencia menor a 100 kcal). No hace falta ajustar.`)
        : notice('info', `Sin cambios por ahora: tu gasto estimado por datos difiere en menos de 100 kcal del que asume tu meta (${fmt0(st.current)} kcal). Con el margen de error actual (±${fmt0(d.ciHalf)} kcal) esto significa «no hay evidencia para cambiarla», no «está confirmada».`));
    } else {
      ad.append(h('h3', null, 'Recomendación'), h('p', null, `Tu meta vigente (${fmt0(st.current)} kcal) asume un gasto de ≈ ${fmt0(rec.implied)} kcal; tus datos sugieren ≈ ${fmt0(d.tdee)} kcal. Meta ideal: `, h('b', null, fmt0(rec.ideal) + ' kcal'), '. Propuesta: ', h('b', null, fmt0(rec.recommended) + ' kcal'), ` (${rec.delta >= 0 ? '+' : '−'}${fmt0(Math.abs(rec.delta))}).`));
      if (rec.limitedByStep) ad.append(h('p', { class: 'sub' }, 'El cambio se limita a ±250 kcal por revisión para no sobrerreaccionar a una estimación ruidosa; si la tendencia se confirma, se repetirá en la siguiente.'));
      if (rec.limitedByFloor) ad.append(h('p', { class: 'sub' }, 'La meta ideal quedaría por debajo de tu gasto basal estimado, así que se respeta ese piso.'));
      if (rec.withinNoise) ad.append(notice('warn', 'La diferencia con el gasto que asume tu meta actual es menor que el margen de error de la estimación: puede ser ruido. Considera esperar a tener más datos antes de aplicarla.'));
      ad.append(h('button', { class: 'btn primary block', type: 'button', onclick: () => { saveTarget(plan, rec.recommended, 'data', `Ajuste por datos: gasto estimado ${Math.round(d.tdee)} ± ${Math.round(d.ciHalf)} kcal`); toast('Meta actualizada.'); } }, 'Aplicar como meta vigente desde hoy'));
    }
  }
  ad.append(h('p', { class: 'sub' }, 'La evolución en el tiempo está en la pestaña Progreso.'));
  root.append(ad);
  return root;
}
