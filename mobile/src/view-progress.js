/* ===== VISTA PROGRESO ===== */
let CHARTS = [];
const postRender = [];
function destroyCharts() { CHARTS.forEach((c) => c.destroy()); CHARTS = []; postRender.length = 0; }
function chartTheme() { return { ink2: cssVar('--ink2'), muted: cssVar('--muted'), grid: cssVar('--line'), s1: cssVar('--s1'), s2: cssVar('--s2'), s3: cssVar('--s3'), surface: cssVar('--surface') }; }
function baseOpts(t, o = {}) {
  return { responsive: true, maintainAspectRatio: false, animation: false, interaction: { mode: 'index', intersect: false },
    plugins: { legend: { display: !!o.legend, position: 'top', align: 'start', labels: { color: t.ink2, usePointStyle: true, boxWidth: 8, boxHeight: 8, filter: (i) => !i.text.startsWith('__') } },
      tooltip: { callbacks: { title: o.title || undefined, label: o.label || undefined, filter: (i) => !i.dataset.label.startsWith('__') } } },
    scales: { x: { grid: { display: false }, border: { color: t.grid }, ticks: { color: t.muted, maxTicksLimit: 6, autoSkip: true, maxRotation: 0 } },
      y: { grid: { color: t.grid }, border: { display: false }, ticks: { color: t.muted }, title: { display: !!o.yTitle, text: o.yTitle, color: t.muted }, beginAtZero: !!o.zero } } };
}
const orNull = (a) => a.map((v) => (isNum(v) ? v : null));
function chartBox(title, sub, tall) {
  const canvas = h('canvas', { role: 'img', 'aria-label': title });
  return { canvas, box: h('div', { class: 'chart-box' + (tall ? ' tall' : '') }, canvas), head: h('div', null, h('h3', null, title), h('p', { class: 'sub' }, sub)) };
}
function addChart(canvas, cfg) { postRender.push(() => { if (typeof Chart === 'undefined') return; CHARTS.push(new Chart(canvas, cfg)); }); }

function rangeBounds() {
  const today = todayIso(), r = S.range;
  const keys = Object.keys(S.days).sort();
  const earliest = keys.length ? keys[0] : addDays(today, -30);
  if (r.preset === 'all') return [earliest, today];
  if (r.preset === 'custom' && r.start && r.end && r.start <= r.end) return [r.start, r.end > today ? today : r.end];
  const n = { 30: 30, 90: 90, 180: 182 }[r.preset] || 90;
  return [addDays(today, -n), today];
}

function viewProgress() {
  const today = todayIso(), [start, end] = rangeBounds(), fr = buildFrame(dataFor(), start, end, today), root = h('div', { style: 'display:flex;flex-direction:column;gap:14px' });
  const chip = (v, l) => h('button', { class: 'chip', type: 'button', 'aria-pressed': String(S.range.preset === v), onclick: () => { S.range.preset = v; render(); } }, l);
  root.append(h('h2', null, 'Progreso'), h('div', { class: 'chips', role: 'group', 'aria-label': 'Rango de fechas' }, chip('30', '30 días'), chip('90', '90 días'), chip('180', '6 meses'), chip('all', 'Todo'), chip('custom', 'Otro')));
  if (S.range.preset === 'custom') {
    const a = h('input', { type: 'date', value: S.range.start || start, max: today }), b = h('input', { type: 'date', value: S.range.end || end, max: today });
    const apply = () => { S.range.start = a.value; S.range.end = b.value; render(); };
    a.addEventListener('change', apply); b.addEventListener('change', apply);
    root.append(h('div', { class: 'grid2' }, field('Desde', a), field('Hasta', b)));
  }
  const anyW = fr.weight.some(isNum), anyK = fr.kcal.some(isNum);
  if (!anyW && !anyK) { root.append(h('section', { class: 'card' }, h('div', { class: 'empty' }, h('span', null, 'No hay registros en este rango. Empieza por «Hoy»: registra tu peso y tus comidas y aquí verás tu evolución.'), h('button', { class: 'btn primary', type: 'button', onclick: () => setTab('today') }, 'Ir a Hoy')))); return root; }

  const ma = fr.ma7.filter(isNum), validDays = fr.valid.filter(Boolean).length, t = chartTheme();
  root.append(h('div', { class: 'kpis' },
    h('div', { class: 'kpi' }, h('div', { class: 'l' }, 'Peso (prom. 7 días)'), h('div', { class: 'v num' }, ma.length ? fmt1(ma[ma.length - 1]) + ' kg' : '—')),
    h('div', { class: 'kpi' }, h('div', { class: 'l' }, 'Cambio en el rango'), h('div', { class: 'v num' }, ma.length > 1 ? (ma[ma.length - 1] - ma[0] >= 0 ? '+' : '−') + fmt1(Math.abs(ma[ma.length - 1] - ma[0])) + ' kg' : '—')),
    h('div', { class: 'kpi' }, h('div', { class: 'l' }, 'Calorías prom. (días válidos)'), h('div', { class: 'v num' }, validDays ? fmt0(mean(fr.kcalValid.filter(isNum))) : '—')),
    h('div', { class: 'kpi' }, h('div', { class: 'l' }, 'Días con comida válida'), h('div', { class: 'v num' }, `${validDays} de ${fr.dates.length}`))));
  root.append(h('p', { class: 'sub' }, 'Los días sin pesar o sin registrar quedan en blanco: no se rellenan con ceros ni se inventan datos.'));
  const labels = fr.dates.map(fmtDM), fullDate = (items) => fmtDMY(fr.dates[items[0].dataIndex]);

  /* peso */
  const wc = chartBox('Peso', 'Puntos: cada día. Línea: promedio móvil de 7 días (necesita ≥ 3 pesajes en la ventana).');
  if (anyW) {
    const dense = fr.weight.filter(isNum).length > 120;
    addChart(wc.canvas, { type: 'line', data: { labels, datasets: [
      { label: 'Peso diario', data: orNull(fr.weight), borderColor: t.muted, backgroundColor: t.muted, pointBackgroundColor: t.muted, pointBorderColor: t.surface, pointBorderWidth: 1.5, pointRadius: dense ? 0 : 3.5, showLine: dense, borderWidth: 1, spanGaps: false },
      { label: 'Promedio móvil 7 días', data: orNull(fr.ma7), borderColor: t.s1, backgroundColor: t.s1, borderWidth: 2.5, pointRadius: 0, spanGaps: false }] },
      options: baseOpts(t, { legend: true, yTitle: 'kg', title: fullDate, label: (c) => `${c.dataset.label}: ${fmt1(c.parsed.y)} kg` }) });
  }
  root.append(h('section', { class: 'card' }, wc.head, anyW ? wc.box : h('p', { class: 'sub' }, 'Sin pesajes en este rango.'),
    tableView(['Fecha', 'Peso (kg)', 'Prom. 7 d'], fr.dates.map((d, i) => [fmtDMY(d), fmt1(fr.weight[i]), fmt1(fr.ma7[i])]).filter((_, i) => isNum(fr.weight[i]) || isNum(fr.ma7[i])))));

  /* calorías por semana */
  const weekly = weeklyIntake(fr.dates, fr.kcalValid).map((w) => { const i = fr.dates.indexOf(w.weekStart); const idx = i >= 0 ? i : 0; return { ...w, target: isNum(fr.targetKcal[idx]) ? fr.targetKcal[idx] : null }; });
  const kc = chartBox('Calorías por semana', 'Promedio diario de cada semana usando solo días válidos. Las barras claras tienen menos de 4 días registrados: son menos fiables.');
  if (weekly.length) {
    const hasT = weekly.some((w) => w.target != null);
    addChart(kc.canvas, { type: 'bar', data: { labels: weekly.map((w) => fmtDM(w.weekStart)), datasets: [
      { type: 'bar', label: 'Calorías promedio', data: weekly.map((w) => w.meanKcal), backgroundColor: weekly.map((w) => (w.validDays >= 4 ? t.s1 : rgba(t.s1, 0.4))), borderRadius: 4, maxBarThickness: 30 },
      ...(hasT ? [{ type: 'line', label: 'Meta', data: weekly.map((w) => w.target), borderColor: t.ink2, backgroundColor: t.ink2, borderWidth: 2, pointRadius: 0, stepped: 'before' }] : [])] },
      options: { ...baseOpts(t, { legend: hasT, yTitle: 'kcal/día', zero: true, title: (items) => 'Semana del ' + fmtDMY(weekly[items[0].dataIndex].weekStart), label: (c) => c.dataset.type === 'line' ? `Meta: ${fmt0(c.parsed.y)} kcal` : `${fmt0(c.parsed.y)} kcal/día · ${weekly[c.dataIndex].validDays} días con registro` }) } });
  }
  root.append(h('section', { class: 'card' }, kc.head, weekly.length ? kc.box : h('p', { class: 'sub' }, 'Sin días de comida válidos en este rango.'),
    tableView(['Semana', 'kcal/día', 'Días', 'Meta'], weekly.map((w) => [fmtDMY(w.weekStart), fmt0(w.meanKcal), String(w.validDays), w.target != null ? fmt0(w.target) : '—']))));

  /* gasto por datos vs fórmula */
  const keys = Object.keys(S.days).sort(), earliest = keys.length ? keys[0] : start;
  const full = buildFrame(dataFor(), earliest < start ? earliest : start, end, today), F = full._full;
  const form = S.profile ? formulaSeries(F, S.profile) : F.dates.map(() => null);
  const roll = rollingTdee(F.weight, F.kcalValid, S.tdeeWindow);
  const from = Math.max(0, F.dates.indexOf(start)), dts = F.dates.slice(from), pick = (a, f) => a.slice(from).map((x) => (x ? f(x) : null));
  const hasData = roll.some(Boolean), hasForm = form.some(Boolean);
  const tc = chartBox('Gasto estimado: datos vs fórmula', 'La banda es el intervalo de confianza al 95 % de la estimación por datos. Si es ancha, la estimación es poco precisa: no la trates como un número exacto.');
  if (hasData || hasForm) {
    addChart(tc.canvas, { type: 'line', data: { labels: dts.map(fmtDM), datasets: [
      { label: '__hi', data: pick(roll, (x) => x.hi), borderWidth: 0, pointRadius: 0, fill: false },
      { label: 'Intervalo 95 %', data: pick(roll, (x) => x.lo), borderWidth: 0, pointRadius: 0, backgroundColor: rgba(t.s1, 0.18), fill: '-1' },
      { label: 'Por datos', data: pick(roll, (x) => x.tdee), borderColor: t.s1, backgroundColor: t.s1, borderWidth: 2.5, pointRadius: 0, spanGaps: false },
      { label: 'Por fórmula', data: pick(form, (x) => x.tdee), borderColor: t.s2, backgroundColor: t.s2, borderWidth: 2.5, pointRadius: 0, spanGaps: false }] },
      options: baseOpts(t, { legend: true, yTitle: 'kcal/día', title: (items) => fmtDMY(dts[items[0].dataIndex]), label: (c) => (c.dataset.label === 'Intervalo 95 %' ? `IC 95 %: ${fmt0(c.parsed.y)} – ${fmt0(c.chart.data.datasets[0].data[c.dataIndex])}` : `${c.dataset.label}: ${fmt0(c.parsed.y)} kcal`) }) });
  }
  root.append(h('section', { class: 'card' }, h('div', { class: 'card-title' }, h('div', null, tc.head.firstChild), h('div', { class: 'chips' }, [14, 21, 28, 42].map((w) => h('button', { class: 'chip', type: 'button', 'aria-pressed': String(S.tdeeWindow === w), onclick: () => { S.tdeeWindow = w; render(); } }, w + ' d')))),
    tc.head.lastChild, hasData || hasForm ? tc.box : h('p', { class: 'sub' }, S.profile ? 'Sin datos suficientes en este rango.' : 'Guarda tu perfil en «Metas» para ver el gasto por fórmula.'),
    hasForm && !hasData ? h('p', { class: 'sub' }, 'Aún no hay estimación por datos en este rango: se necesitan ≥ 14 días con 10 de comida válida y suficientes pesajes. Se muestra solo la fórmula.') : null,
    tableView(['Fecha', 'Fórmula', 'Por datos', 'IC inf.', 'IC sup.'], dts.map((d, i) => [fmtDMY(d), form[from + i] ? fmt0(form[from + i].tdee) : '—', roll[from + i] ? fmt0(roll[from + i].tdee) : '—', roll[from + i] ? fmt0(roll[from + i].lo) : '—', roll[from + i] ? fmt0(roll[from + i].hi) : '—']).filter((r) => r[1] !== '—' || r[2] !== '—'))));

  /* composición corporal (dos paneles: nunca eje doble) */
  const anyL = fr.lean.some(isNum), anyBf = fr.bf.some(isNum);
  const bcL = chartBox('Masa magra estimada', 'Peso suavizado × (1 − % de grasa interpolado entre mediciones). Si tus % son estimaciones, la masa magra hereda ese error.');
  const bcB = chartBox('% de grasa registrado', 'Solo las mediciones que registraste.');
  if (anyL) addChart(bcL.canvas, { type: 'line', data: { labels, datasets: [{ label: 'Masa magra', data: orNull(fr.lean), borderColor: t.s1, backgroundColor: t.s1, borderWidth: 2.5, pointRadius: 0, spanGaps: false }] }, options: (() => { const o = baseOpts(t, { yTitle: 'kg', title: fullDate, label: (c) => `${fmt1(c.parsed.y)} kg` }); o.scales.y.ticks.maxTicksLimit = 5; o.scales.y.ticks.callback = (v) => fmt1(v); return o; })() });
  if (anyBf) addChart(bcB.canvas, { type: 'line', data: { labels, datasets: [{ label: '% de grasa', data: orNull(fr.bf), borderColor: t.s2, backgroundColor: t.s2, pointBackgroundColor: t.s2, pointBorderColor: t.surface, pointBorderWidth: 1.5, borderWidth: 2, pointRadius: 4, spanGaps: true }] }, options: (() => { const o = baseOpts(t, { yTitle: '%', title: fullDate, label: (c) => `${fmt1(c.parsed.y)} %` }); o.scales.y.ticks.maxTicksLimit = 5; o.scales.y.ticks.callback = (v) => fmt1(v); return o; })() });
  root.append(h('section', { class: 'card' }, h('h2', null, 'Composición corporal'),
    anyL ? [bcL.head, bcL.box] : null, anyBf ? [bcB.head, bcB.box] : null,
    !anyL && !anyBf ? h('p', { class: 'sub' }, 'Registra un % de grasa (o medidas de cuello y cintura) en «Hoy» para ver la composición corporal.') : null,
    tableView(['Fecha', '% grasa', 'Masa magra (kg)'], fr.dates.map((d, i) => [fmtDMY(d), fmt1(fr.bf[i]), fmt1(fr.lean[i])]).filter((_, i) => isNum(fr.bf[i]) || isNum(fr.lean[i])))));
  return root;
}
