/* ===== STORE: persistencia. Nube (db de Claude, privado por usuario) con respaldo en localStorage ===== */
const KINDS = ['profile', 'days', 'foods', 'targets'];

function makeLocalBackend() {
  const KEY = 'macro-tracker:v1';
  let mem = { profile: {}, days: {}, foods: {}, targets: {} };
  try { const raw = localStorage.getItem(KEY); if (raw) mem = { ...mem, ...JSON.parse(raw) }; } catch (e) { /* sin almacenamiento: solo memoria */ }
  const listeners = {};
  const persist = () => { try { localStorage.setItem(KEY, JSON.stringify(mem)); } catch (e) { /* ignorar */ } };
  const emit = (kind) => (listeners[kind] || []).forEach((fn) => fn(Object.entries(mem[kind]).map(([id, d]) => ({ id, ...d }))));
  return {
    mode: 'local',
    async init() { return true; },
    subscribe(kind, fn) { (listeners[kind] = listeners[kind] || []).push(fn); setTimeout(() => emit(kind), 0); },
    async put(kind, id, data) { mem[kind][id] = JSON.parse(JSON.stringify(data)); persist(); emit(kind); },
    async remove(kind, id) { delete mem[kind][id]; persist(); emit(kind); },
  };
}

function makeCloudBackend(db, uid) {
  const base = db.collection('data/users/' + uid);
  const app = base.doc('app');
  const ref = (kind, id) => (kind === 'profile' ? base.doc('profile') : app.collection(kind).doc(id));
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  // Una sola escritura a la vez, en orden. La plataforma limita las llamadas por segundo; en paralelo
  // (o en ráfagas largas, como una importación) algunas se rechazaban y quedaba el trabajo a medias.
  let tail = Promise.resolve(), gap = 0;
  const enqueue = (fn) => { const next = tail.catch(() => {}).then(() => attempt(fn)); tail = next; return next; };
  async function attempt(fn) {
    for (let n = 0; ; n++) {
      if (gap) await sleep(gap);
      try { const r = await fn(); gap = Math.floor(gap * 0.7); return r; } catch (e) {
        const code = e && e.code;
        if (!((code === 'resource_exhausted' && n < 6) || (code === 'unavailable' && n < 2))) throw e;
        if (code === 'resource_exhausted') gap = Math.min(1500, gap ? gap * 2 : 200);   // ir más despacio, también para lo que sigue
        await sleep(Math.round(300 * 2 ** n * (0.6 + Math.random() * 0.8)));
      }
    }
  }
  return {
    mode: 'cloud',
    async init() { return true; },
    subscribe(kind, fn, onError) {
      const src = kind === 'profile' ? base.doc('profile') : app.collection(kind);
      if (kind === 'profile') src.onSnapshot((s) => fn(s.exists ? [{ id: 'main', ...s.data() }] : []), onError);
      else src.onSnapshot((s) => fn(s.docs.map((d) => ({ id: d.id, ...d.data() }))), onError);
    },
    put(kind, id, data) { const r = ref(kind, id); const body = JSON.parse(JSON.stringify(data)); return enqueue(() => r.set(body)); },
    remove(kind, id) { const r = ref(kind, id); return enqueue(() => r.delete()); },
  };
}

/** Intenta la nube; si no hay db o identidad, usa el navegador. Devuelve el backend elegido. */
async function openBackend() {
  try {
    if (window.claude && window.claude.use) {
      const [db, user] = await Promise.all([window.claude.use('db'), window.claude.use('user')]);
      const uid = user ? await user.id() : null;
      if (db && uid) return makeCloudBackend(db, uid);
    }
  } catch (e) { /* cae al respaldo local */ }
  return makeLocalBackend();
}

if (typeof module !== 'undefined') module.exports = { openBackend, makeLocalBackend, makeCloudBackend, KINDS };
