/* ===== ARRANQUE ===== */
const TABS = [['today', 'Hoy', viewToday], ['progress', 'Progreso', viewProgress], ['foods', 'Alimentos', viewFoods], ['goals', 'Metas', viewGoals], ['data', 'Datos', viewData]];
function setTab(t) { if (t !== S.tab) S.importMsg = null; S.tab = t; window.scrollTo(0, 0); closeSheet(); render(); }
function render() {
  destroyCharts();
  const view = $('#view'), tab = TABS.find((x) => x[0] === S.tab);
  const ready = Object.values(S.loaded).every(Boolean);
  try { view.replaceChildren(ready ? tab[2]() : h('div', { class: 'empty' }, h('span', { class: 'spin' }), h('span', null, 'Cargando tus datos…'))); }
  catch (e) { console.error(e); view.replaceChildren(notice('bad', 'Algo falló al mostrar esta pantalla: ' + (e && e.message ? e.message : e) + '. Prueba con otra pestaña o recarga la página.')); }
  $('#tabs').querySelectorAll('.tab').forEach((b) => b.setAttribute('aria-selected', String(b.dataset.tab === S.tab)));
  postRender.splice(0).forEach((fn) => { try { fn(); } catch (e) { console.error(e); } });
}
function mountChrome() {
  const tabs = $('#tabs');
  TABS.forEach(([id, label]) => tabs.append(h('button', { class: 'tab', type: 'button', role: 'tab', 'data-tab': id, onclick: () => setTab(id) }, icon(id), h('span', null, label))));
  // la cámara va en el centro de la barra (no flota sobre el contenido): un toque abre la cámara desde cualquier pestaña
  const cam = h('button', { class: 'tab-cam', id: 'fab-photo', type: 'button', 'aria-label': 'Estimar una comida con una foto', onclick: () => { if (S.tab !== 'today') setTab('today'); quickPhoto(S.date); } }, icon('camera'));
  tabs.insertBefore(cam, tabs.children[2]);
  window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', () => render());
  new MutationObserver(() => render()).observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] });
}
async function boot() {
  mountChrome(); updateSync(); render();
  S.backend = await openBackend(); S.mode = S.backend.mode; updateSync();
  const fail = (e) => { console.error(e); S.mode = 'error'; $('#sync').dataset.state = 'local'; $('#sync').textContent = 'Sin conexión con tu cuenta'; toast('No pude leer tus datos guardados. Recarga la página; mientras tanto no escribas nada nuevo.', 6000); };
  const got = (kind, fn) => S.backend.subscribe(kind, (docs) => { fn(docs); S.loaded[kind] = true; scheduleRender(); }, fail);
  got('profile', (docs) => { S.profile = docs[0] ? docs[0] : null; });
  got('days', (docs) => { S.days = Object.fromEntries(docs.map((d) => [d.id, d])); });
  got('foods', (docs) => { S.storedFoods = new Set(docs.map((d) => d.id)); S.foods = withBuiltin(Object.fromEntries(docs.map((d) => [d.id, { ...d, id: d.id }]))); });
  got('targets', (docs) => { S.targets = docs.map((d) => ({ ...d, from: d.from || d.id })); });
  if (window.claude && window.claude.use) {
    window.claude.use('sample').then((s) => { S.caps.sample = s; if (s && s.limits) s.limits().then((l) => { S.caps.images = !!(l && l.images); }).catch(() => {}); }).catch(() => {});
    window.claude.use('downloads').then((d) => { S.caps.downloads = d; }).catch(() => {});
  }
}
boot();
