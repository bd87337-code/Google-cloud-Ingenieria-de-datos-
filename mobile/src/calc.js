/* ===== CALC: cálculos puros (sin DOM ni almacenamiento). Port fiel de macro_tracker/calc y services.py ===== */
const KCAL_PER_KG = 7700;
const ACTIVITY_FACTORS = { sedentary: 1.2, light: 1.375, moderate: 1.55, active: 1.725, very_active: 1.9 };
const CFG = {
  windowDays: 14, minFoodDays: 10, minWeighings: 8, minPerHalf: 3,
  maxStepKcal: 250, noiseFloorKcal: 100, ciHigh: 250, ciMedium: 450,
  maDays: 7, defaultMinValidKcal: 1000, proteinRefBf: 0.20,
};

/* ---------- fechas (ISO AAAA-MM-DD, sin zona horaria) ---------- */
const DAY_MS = 86400000;
function dayNum(iso) { const [y, m, d] = iso.split('-').map(Number); return Date.UTC(y, m - 1, d) / DAY_MS; }
function isoOf(n) { return new Date(n * DAY_MS).toISOString().slice(0, 10); }
function addDays(iso, n) { return isoOf(dayNum(iso) + n); }
function todayIso() {
  const d = new Date();
  return d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0') + '-' + String(d.getDate()).padStart(2, '0');
}
function dateRange(startIso, endIso) {
  const out = [];
  for (let n = dayNum(startIso); n <= dayNum(endIso); n++) out.push(isoOf(n));
  return out;
}
function ageOn(birthIso, onIso) {
  const [by, bm, bd] = birthIso.split('-').map(Number), [oy, om, od] = onIso.split('-').map(Number);
  let years = oy - by;
  if (om < bm || (om === bm && od < bd)) years -= 1;
  return years;
}
const isNum = (v) => typeof v === 'number' && Number.isFinite(v);

/* ---------- gasto basal ---------- */
function mifflin(weightKg, heightCm, age, sex) {
  if (!(weightKg > 0) || !(heightCm > 0) || !(age > 0)) throw new Error('peso, estatura y edad deben ser positivos');
  if (sex !== 'M' && sex !== 'F') throw new Error("sexo debe ser 'M' o 'F'");
  return 10 * weightKg + 6.25 * heightCm - 5 * age + (sex === 'M' ? 5 : -161);
}
function checkBf(bf) { if (!(bf >= 3 && bf <= 60)) throw new Error('% de grasa fuera de rango [3, 60]'); }
function katch(weightKg, bf) {
  if (!(weightKg > 0)) throw new Error('peso debe ser positivo');
  checkBf(bf);
  return 370 + 21.6 * weightKg * (1 - bf / 100);
}
function estimateBmr(weightKg, heightCm, age, sex, bf = null, prefer = 'auto') {
  if (bf != null && prefer === 'auto') return { kcal: katch(weightKg, bf), method: 'katch_mcardle' };
  return { kcal: mifflin(weightKg, heightCm, age, sex), method: 'mifflin_st_jeor' };
}

/* ---------- composición corporal ---------- */
function proteinRefWeight(weightKg, bf = null) {
  if (bf == null) return weightKg;
  checkBf(bf);
  return Math.min(weightKg, (weightKg * (1 - bf / 100)) / (1 - CFG.proteinRefBf));
}
function navyBodyFat(sex, heightCm, neckCm, waistCm, hipCm = null) {
  if (sex !== 'M' && sex !== 'F') throw new Error("sexo debe ser 'M' o 'F'");
  if (!(heightCm > 0) || !(neckCm > 0) || !(waistCm > 0)) throw new Error('estatura, cuello y cintura deben ser positivos');
  let density;
  if (sex === 'M') {
    const spread = waistCm - neckCm;
    if (spread <= 0) throw new Error('la cintura debe ser mayor que el cuello');
    density = 1.0324 - 0.19077 * Math.log10(spread) + 0.15456 * Math.log10(heightCm);
  } else {
    if (!(hipCm > 0)) throw new Error('las mujeres requieren la medida de cadera');
    const spread = waistCm + hipCm - neckCm;
    if (spread <= 0) throw new Error('cintura + cadera debe ser mayor que el cuello');
    density = 1.29579 - 0.35004 * Math.log10(spread) + 0.221 * Math.log10(heightCm);
  }
  return 495 / density - 450;
}

/* ---------- metas ---------- */
function activityFactor(level) {
  if (!(level in ACTIVITY_FACTORS)) throw new Error('nivel de actividad desconocido: ' + level);
  return ACTIVITY_FACTORS[level];
}
function goalAdjustment(goal, rate) {
  if (!['maintain', 'gain', 'lose'].includes(goal)) throw new Error('objetivo desconocido: ' + goal);
  if (rate < 0) throw new Error('el ritmo se expresa como valor positivo (kg/semana)');
  if (goal === 'maintain') return 0;
  const daily = (rate * KCAL_PER_KG) / 7;
  return goal === 'lose' ? -daily : daily;
}
function calorieTarget(tdee, bmr, goal, rate) {
  const adjustment = goalAdjustment(goal, rate);
  const unfloored = tdee + adjustment;
  const kcal = Math.max(unfloored, bmr);
  return { kcal, tdee, adjustment, unfloored, floor: bmr, floorApplied: unfloored < bmr,
    effectiveRate: ((kcal - tdee) * 7) / KCAL_PER_KG };
}
function pickProteinPerKg(goal, range) { return goal === 'lose' ? range[1] : (range[0] + range[1]) / 2; }
function macroTargets(kcal, weightKg, goal, refKg = null, range = [1.6, 2.2], fatMin = 0.6, fatPct = 0.25) {
  const [lo, hi] = range;
  if (!(lo > 0 && lo <= hi)) throw new Error('rango de proteína inválido');
  const ref = refKg == null ? weightKg : refKg;
  const perKg = pickProteinPerKg(goal, range);
  let protein = perKg * ref;
  const proteinMin = lo * ref;
  const fatFloor = fatMin * weightKg;
  let fat = Math.max(fatFloor, (fatPct * kcal) / 9);
  const flags = [];
  const carbsFor = (p, f) => (kcal - 4 * p - 9 * f) / 4;
  let carbs = carbsFor(protein, fat);
  if (carbs < 0) {
    flags.push('reduced_to_fit');
    fat = Math.max(fatFloor, (kcal - 4 * protein) / 9);
    carbs = carbsFor(protein, fat);
    if (carbs < 0) { protein = Math.max(proteinMin, (kcal - 9 * fat) / 4); carbs = carbsFor(protein, fat); }
    if (carbs < 0) { carbs = 0; flags.push('minimums_exceed_kcal'); }
  }
  return { kcal, protein, carbs, fat, proteinPerKg: ref ? protein / ref : 0,
    proteinRange: [lo * ref, hi * ref], fatFloor, flags };
}

/* ---------- series con huecos (NaN = dato faltante, nunca 0) ---------- */
function movingAverage(values, windowDays = CFG.maDays, minPeriods = 3) {
  return values.map((_, i) => {
    let sum = 0, n = 0;
    for (let j = Math.max(0, i - windowDays + 1); j <= i; j++) if (isNum(values[j])) { sum += values[j]; n++; }
    return n >= minPeriods ? sum / n : NaN;
  });
}
function interpolateBf(values) {
  const out = values.map(() => NaN);
  const idx = []; values.forEach((v, i) => { if (isNum(v)) idx.push(i); });
  if (!idx.length) return out;
  for (let k = 0; k < idx.length; k++) {
    const i = idx[k]; out[i] = values[i];
    const next = idx[k + 1];
    if (next !== undefined) for (let j = i + 1; j < next; j++) out[j] = values[i] + ((values[next] - values[i]) * (j - i)) / (next - i);
  }
  for (let j = idx[idx.length - 1] + 1; j < values.length; j++) out[j] = values[idx[idx.length - 1]];
  return out;
}
/** overrides[i]: null (auto) | true | false. Hoy nunca es válido salvo que se fuerce. */
function validFoodDays(kcal, minKcal, overrides, todayIdx = -1) {
  return kcal.map((k, i) => {
    const ov = overrides ? overrides[i] : null;
    if (ov === true) return isNum(k);
    if (ov === false) return false;
    if (i === todayIdx) return false;
    return isNum(k) && k >= minKcal;
  });
}
function weeklyIntake(dates, kcalValid) {
  const weeks = new Map();
  dates.forEach((d, i) => {
    if (!isNum(kcalValid[i])) return;
    const n = dayNum(d), monday = n - ((n + 3) % 7);   // 1970-01-01 fue jueves
    const w = weeks.get(monday) || { sum: 0, count: 0 };
    w.sum += kcalValid[i]; w.count++; weeks.set(monday, w);
  });
  return [...weeks.entries()].sort((a, b) => a[0] - b[0])
    .map(([monday, w]) => ({ weekStart: isoOf(monday), meanKcal: w.sum / w.count, validDays: w.count }));
}

/* ---------- gasto real por datos ---------- */
const T95 = [NaN, 12.706, 4.303, 3.182, 2.776, 2.571, 2.447, 2.365, 2.306, 2.262, 2.228, 2.201, 2.179, 2.16, 2.145, 2.131,
  2.12, 2.11, 2.101, 2.093, 2.086, 2.08, 2.074, 2.069, 2.064, 2.06, 2.056, 2.052, 2.048, 2.045, 2.042];
function t95(df) { if (df < 1) throw new Error('grados de libertad deben ser ≥ 1'); return df <= 30 ? T95[df] : 1.96; }
function linearFit(x, y) {
  const n = x.length;
  if (n < 3) return null;
  const xm = x.reduce((a, b) => a + b, 0) / n, ym = y.reduce((a, b) => a + b, 0) / n;
  let sxx = 0, sxy = 0;
  for (let i = 0; i < n; i++) { sxx += (x[i] - xm) ** 2; sxy += (x[i] - xm) * (y[i] - ym); }
  if (sxx === 0) return null;
  const slope = sxy / sxx;
  let sse = 0;
  for (let i = 0; i < n; i++) sse += (y[i] - (ym + slope * (x[i] - xm))) ** 2;
  return { slope, se: Math.sqrt(sse / (n - 2) / sxx) };
}
function confidenceLabel(half) { return half <= CFG.ciHigh ? 'high' : half <= CFG.ciMedium ? 'medium' : 'low'; }

/** weights/kcalValid: arrays alineados por día (NaN = faltante). La ventana termina en endIdx. */
function estimateTdee(weights, kcalValid, endIdx, windowDays = CFG.windowDays, o = {}) {
  const minFood = o.minFoodDays ?? CFG.minFoodDays, minW = o.minWeighings ?? CFG.minWeighings, minHalf = o.minPerHalf ?? CFG.minPerHalf;
  const at = (arr, i) => (i >= 0 && i < arr.length ? arr[i] : NaN);
  const start = endIdx - windowDays + 1;
  const w = [], k = [];
  for (let i = start; i <= endIdx; i++) { w.push(at(weights, i)); k.push(at(kcalValid, i)); }
  const half = Math.floor(windowDays / 2);
  const cnt = (a) => a.filter(isNum).length;
  const nFood = cnt(k), nW = cnt(w), nW1 = cnt(w.slice(0, half)), nW2 = cnt(w.slice(half));
  const avgIntake = nFood ? k.filter(isNum).reduce((a, b) => a + b, 0) / nFood : null;
  const reasons = [];
  if (nFood < minFood) reasons.push('food_days');
  if (nW < minW) reasons.push('weighings');
  else if (nW1 < minHalf || nW2 < minHalf) reasons.push('weighings_halves');
  const base = { ok: false, reasons, startIdx: start, endIdx, windowDays, nFood, nWeighings: nW, nWeighings1: nW1, nWeighings2: nW2,
    avgIntake, slope: null, slopeSe: null, tdee: null, ciHalf: null, confidence: null };
  if (reasons.length) return base;
  const xs = [], ys = [];
  w.forEach((v, i) => { if (isNum(v)) { xs.push(i); ys.push(v); } });
  const fit = linearFit(xs, ys);
  if (!fit) return { ...base, reasons: ['no_variation'] };
  const ciHalf = t95(nW - 2) * fit.se * KCAL_PER_KG;
  return { ...base, ok: true, reasons: [], slope: fit.slope, slopeSe: fit.se, tdee: avgIntake - fit.slope * KCAL_PER_KG,
    ciHalf, confidence: confidenceLabel(ciHalf) };
}
function rollingTdee(weights, kcalValid, windowDays = CFG.windowDays, o = {}) {
  const out = weights.map(() => null);
  for (let end = windowDays - 1; end < weights.length; end++) {
    const r = estimateTdee(weights, kcalValid, end, windowDays, o);
    if (r.ok) out[end] = { tdee: r.tdee, lo: r.tdee - r.ciHalf, hi: r.tdee + r.ciHalf, confidence: r.confidence, avgIntake: r.avgIntake };
  }
  return out;
}
function recommendTarget(data, currentKcal, goal, rate, bmr, o = {}) {
  const maxStep = o.maxStepKcal ?? CFG.maxStepKcal, noise = o.noiseFloorKcal ?? CFG.noiseFloorKcal;
  if (!data.ok || data.tdee == null) return { status: 'insufficient' };
  const adjustment = goalAdjustment(goal, rate);
  const implied = currentKcal - adjustment;
  const withinNoise = Math.abs(data.tdee - implied) < (data.ciHalf || 0);
  const idealRaw = data.tdee + adjustment, ideal = Math.max(idealRaw, bmr), limitedByFloor = idealRaw < bmr;
  const diff = ideal - currentKcal;
  if (Math.abs(diff) < noise) return { status: 'keep', ideal, recommended: currentKcal, delta: 0, implied, withinNoise, limitedByStep: false, limitedByFloor };
  const step = Math.max(-maxStep, Math.min(maxStep, diff));
  const recommended = Math.max(currentKcal + step, bmr);
  return { status: 'adjust', ideal, recommended, delta: recommended - currentKcal, implied, withinNoise,
    limitedByStep: Math.abs(diff) > maxStep, limitedByFloor };
}

/* ---------- tabla diaria a partir de los datos guardados ---------- */
const dayKcal = (day) => (day && day.entries && day.entries.length ? day.entries.reduce((s, e) => s + e.kcal, 0) : NaN);
/** data = { days: {iso: doc}, targets: [{from,...}] ordenados, profile }. Devuelve arrays alineados entre start y end. */
function buildFrame(data, startIso, endIso, today) {
  const keys = Object.keys(data.days).filter((k) => {
    const d = data.days[k];
    return d && (isNum(d.weight) || isNum(d.bf) || (d.entries && d.entries.length));
  }).sort();
  const fullStart = keys.length && keys[0] < startIso ? keys[0] : startIso;
  const dates = dateRange(fullStart, endIso);
  const profile = data.profile;
  const minKcal = profile && isNum(profile.minValidKcal) ? profile.minValidKcal : CFG.defaultMinValidKcal;
  const col = (f) => dates.map((d) => (data.days[d] && isNum(data.days[d][f]) ? data.days[d][f] : NaN));
  const weight = col('weight'), bf = col('bf');
  const kcal = dates.map((d) => dayKcal(data.days[d]));
  const sumF = (f) => dates.map((d) => (data.days[d] && data.days[d].entries && data.days[d].entries.length
    ? data.days[d].entries.reduce((s, e) => s + e[f], 0) : NaN));
  const overrides = dates.map((d) => (data.days[d] && typeof data.days[d].forced === 'boolean' ? data.days[d].forced : null));
  const todayIdx = dates.indexOf(today);
  const valid = validFoodDays(kcal, minKcal, overrides, todayIdx);
  const kcalValid = kcal.map((k, i) => (valid[i] ? k : NaN));
  const ma7 = movingAverage(weight);
  const bfDaily = interpolateBf(bf);
  const lean = ma7.map((w, i) => w * (1 - bfDaily[i] / 100));
  const tg = data.targets || [];
  const target = dates.map((d) => { let t = null; for (const x of tg) if (x.from <= d) t = x; return t; });
  const from = dates.indexOf(startIso) >= 0 ? dates.indexOf(startIso) : 0;
  const cut = (a) => a.slice(from);
  return { dates: cut(dates), weight: cut(weight), ma7: cut(ma7), bf: cut(bf), bfDaily: cut(bfDaily), lean: cut(lean), kcal: cut(kcal),
    protein: cut(sumF('p')), carbs: cut(sumF('c')), fat: cut(sumF('f')), valid: cut(valid), kcalValid: cut(kcalValid),
    targetKcal: cut(target).map((t) => (t ? t.kcal : NaN)),
    _full: { dates, weight, kcalValid, bfDaily, ma7, from } };
}
function formulaSeries(full, profile) {
  return full.dates.map((d, i) => {
    if (!isNum(full.ma7[i])) return null;
    const bf = profile.mifflinOnly || !isNum(full.bfDaily[i]) ? null : full.bfDaily[i];
    const r = estimateBmr(full.ma7[i], profile.heightCm, ageOn(profile.birth, d), profile.sex, bf, profile.mifflinOnly ? 'mifflin' : 'auto');
    return { bmr: r.kcal, tdee: r.kcal * activityFactor(profile.activity), method: r.method };
  });
}

if (typeof module !== 'undefined') {
  module.exports = { KCAL_PER_KG, ACTIVITY_FACTORS, CFG, dayNum, isoOf, addDays, todayIso, dateRange, ageOn, mifflin, katch, estimateBmr,
    proteinRefWeight, navyBodyFat, activityFactor, goalAdjustment, calorieTarget, macroTargets, movingAverage, interpolateBf,
    validFoodDays, weeklyIntake, t95, linearFit, estimateTdee, rollingTdee, recommendTarget, buildFrame, formulaSeries, dayKcal };
}
