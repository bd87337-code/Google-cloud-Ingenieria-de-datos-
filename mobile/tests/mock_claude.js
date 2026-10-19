/* Simulación de window.claude (db, user, sample, downloads) para probar la página fuera de claude.ai.
   Imita la forma de la API real; persiste en localStorage para poder probar recargas. */
(function () {
  const KEY = '__mockdb';
  const store = new Map(Object.entries(JSON.parse(localStorage.getItem(KEY) || '{}')));
  const subs = new Set();
  const persist = () => localStorage.setItem(KEY, JSON.stringify(Object.fromEntries(store)));
  const rand = () => Math.random().toString(16).slice(2, 12);
  const snapDoc = (path) => ({ id: path.split('/').pop(), exists: store.has(path), data: () => (store.has(path) ? JSON.parse(store.get(path)) : undefined), metadata: { fromCache: false, hasPendingWrites: false } });
  const children = (col) => [...store.keys()].filter((k) => k.startsWith(col + '/') && !k.slice(col.length + 1).includes('/')).sort();
  const notify = () => subs.forEach((s) => s());
  const segs = (p) => p.split('/').length;
  const sub = (fire) => { subs.add(fire); setTimeout(fire, 0); return () => subs.delete(fire); };
  const delay = (v) => new Promise((r) => setTimeout(() => r(v), 8));
  window.__mockCalls = { sets: 0 };
  function docRef(path) {
    if (segs(path) % 2 !== 0) throw new TypeError('doc path must have an even number of segments: ' + path);
    return {
      id: path.split('/').pop(), path,
      get: () => delay(snapDoc(path)),
      set: async (d) => { window.__mockCalls.sets++; await delay(); store.set(path, JSON.stringify(d)); persist(); notify(); },
      update: async (d) => { const cur = JSON.parse(store.get(path) || 'null'); if (!cur) throw { code: 'invalid_argument', message: 'missing' }; store.set(path, JSON.stringify({ ...cur, ...d })); persist(); notify(); },
      delete: async () => { await delay(); store.delete(path); persist(); notify(); },
      onSnapshot: (fn) => sub(() => fn(snapDoc(path))),
      collection: (p) => colRef(path + '/' + p),
    };
  }
  function colRef(path) {
    if (segs(path) % 2 !== 1) throw new TypeError('collection path must have an odd number of segments: ' + path);
    const snap = () => { const docs = children(path).map(snapDoc); return { docs, size: docs.length, empty: !docs.length, docChanges: () => [], metadata: {} }; };
    return { path, doc: (id) => docRef(path + '/' + (id || rand())), onSnapshot: (fn) => sub(() => fn(snap())), get: () => delay(snap()) };
  }
  const db = { doc: docRef, collection: colRef };
  const user = { id: async () => 'u_test', me: async () => ({ id: 'u_test' }), isOwner: async () => true, canEdit: async () => true };
  const sampleCalls = (window.__sampleCalls = []);
  const sample = async () => ({ text: '', truncated: false });
  sample.limits = async () => ({ maxPromptBytes: 262144, images: { maxCount: 1, maxInputBytes: 20e6, mediaTypes: ['image/jpeg', 'image/png', 'image/webp', 'image/gif'] } });
  sample.json = async (prompt, opts = {}) => {
    sampleCalls.push({ prompt, hasImage: !!opts.images, cache: opts.cache });
    await delay();
    const mode = localStorage.getItem('__sampleMode') || 'ok';
    if (mode === 'denied') throw { code: 'not_granted', message: 'x' };
    if (prompt.startsWith('ETIQUETA')) {
      if (mode === 'unreadable') return { readable: false };
      return { readable: true, name: 'Galletas María', brand: 'Marca X', basis: 'perServing', servingG: 30, servingLabel: '1 porción (30 g)', kcal: 120, protein: 2, carbs: 22, fat: 2.5, note: '' };
    }
    if (prompt.startsWith('COMIDA')) {
      return { items: [
        { name: 'Taco de pastor', grams: 110, kcal: 230, protein: 12, carbs: 20, fat: 11, confidence: 'media', note: 'con piña' },
        { name: 'Refresco de cola', grams: 355, kcal: 150, protein: 0, carbs: 38, fat: 0, confidence: 'alta', note: '' },
        { name: 'Salsa roja', grams: 30, kcal: 500, protein: 1, carbs: 3, fat: 0, confidence: 'baja', note: 'kcal exageradas' },
        { name: 'Inválido', grams: 0, kcal: 10, protein: 1, carbs: 1, fat: 1 }] };
    }
    return { kcal: 250, protein: 8, carbs: 40, fat: 5, servingG: 50, servingLabel: '1 pieza' };
  };
  const downloads = { save: async ({ filename, data }) => { window.__dl = { filename, data }; return { status: 'saved' }; } };
  window.claude = { use: async (name) => (name === 'sample' && localStorage.getItem('__nosample') ? null : { db, user, sample, downloads }[name] || null) };
})();
