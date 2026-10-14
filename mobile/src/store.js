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
  const chains = new Map();   // una escritura a la vez por documento
  const enqueue = (path, fn) => {
    const next = (chains.get(path) || Promise.resolve()).catch(() => {}).then(fn);
    chains.set(path, next);
    return next;
  };
  const retry = async (fn) => {
    try { return await fn(); } catch (e) {
      if (e && (e.code === 'unavailable' || e.code === 'resource_exhausted')) {
        await new Promise((r) => setTimeout(r, 400 + Math.random() * 600));
        return fn();
      }
      throw e;
    }
  };
  return {
    mode: 'cloud',
    async init() { return true; },
    subscribe(kind, fn, onError) {
      const src = kind === 'profile' ? base.doc('profile') : app.collection(kind);
      if (kind === 'profile') src.onSnapshot((s) => fn(s.exists ? [{ id: 'main', ...s.data() }] : []), onError);
      else src.onSnapshot((s) => fn(s.docs.map((d) => ({ id: d.id, ...d.data() }))), onError);
    },
    put(kind, id, data) { const r = ref(kind, id); return enqueue(r.path, () => retry(() => r.set(JSON.parse(JSON.stringify(data))))); },
    remove(kind, id) { const r = ref(kind, id); return enqueue(r.path, () => retry(() => r.delete())); },
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
