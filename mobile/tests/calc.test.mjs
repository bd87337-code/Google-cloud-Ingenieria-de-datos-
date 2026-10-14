// Valida el port JS contra los resultados de la implementación Python (fixtures.json).
import test from 'node:test';
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import { readFileSync } from 'node:fs';
const require = createRequire(import.meta.url);
const C = require('../src/calc.js');
const F = JSON.parse(readFileSync(new URL('./fixtures.json', import.meta.url)));
const nan = (a) => a.map((v) => (v === null ? NaN : v));
const near = (a, b, msg, tol = 1e-9) => {
  if (b === null || b === undefined) return assert.ok(a === null || a === undefined || Number.isNaN(a), `${msg}: esperado vacío, obtuve ${a}`);
  assert.ok(Math.abs(a - b) <= tol * Math.max(1, Math.abs(b)), `${msg}: ${a} ≠ ${b}`);
};
const nearArr = (a, b, msg, tol) => { assert.equal(a.length, b.length, msg + ' longitud'); b.forEach((v, i) => near(a[i], v, `${msg}[${i}]`, tol)); };

test('BMR', () => F.bmr.forEach((c) => { const r = C.estimateBmr(...c.args); near(r.kcal, c.expected.kcal, 'kcal'); assert.equal(r.method, c.expected.method); }));
test('Navy', () => F.navy.forEach((c) => near(C.navyBodyFat(...c.args), c.expected, 'navy')));
test('referencia de proteína', () => F.proteinRef.forEach((c) => near(C.proteinRefWeight(...c.args), c.expected, 'ref')));
test('edad', () => F.age.forEach((c) => assert.equal(C.ageOn(...c.args), c.expected)));
test('meta calórica y piso', () => F.calorieTarget.forEach((c) => {
  const t = C.calorieTarget(...c.args);
  near(t.kcal, c.expected.kcal, 'kcal'); near(t.adjustment, c.expected.adjustment, 'adj'); near(t.unfloored, c.expected.unfloored, 'unfloored');
  assert.equal(t.floorApplied, c.expected.floorApplied); near(t.effectiveRate, c.expected.effectiveRate, 'rate');
}));
test('macros (incluye recorte y mínimos que no caben)', () => F.macros.forEach((c) => {
  const m = C.macroTargets(...c.args), e = c.expected;
  near(m.protein, e.protein, 'protein'); near(m.carbs, e.carbs, 'carbs'); near(m.fat, e.fat, 'fat'); near(m.proteinPerKg, e.proteinPerKg, 'g/kg');
  nearArr(m.proteinRange, e.proteinRange, 'rango'); near(m.fatFloor, e.fatFloor, 'fatFloor'); assert.deepEqual(m.flags, e.flags);
}));
test('promedio móvil con huecos', () => nearArr(C.movingAverage(nan(F.ma.values)), F.ma.expected, 'ma'));
test('interpolación de % de grasa', () => nearArr(C.interpolateBf(nan(F.interp.values)), F.interp.expected, 'bf'));
test('días válidos con overrides', () => assert.deepEqual(C.validFoodDays(nan(F.valid.kcal), 1000, F.valid.overrides), F.valid.expected));
test('calorías por semana', () => {
  const w = C.weeklyIntake(F.weekly.dates, nan(F.weekly.kcalValid));
  assert.equal(w.length, F.weekly.expected.length);
  w.forEach((r, i) => { assert.equal(r.weekStart, F.weekly.expected[i].weekStart); near(r.meanKcal, F.weekly.expected[i].meanKcal, 'mean'); assert.equal(r.validDays, F.weekly.expected[i].validDays); });
});
test('gasto por datos: todos los escenarios', () => F.adaptive.forEach((c) => {
  const r = C.estimateTdee(nan(c.weights), nan(c.kcalValid), c.endIdx, c.window), e = c.expected;
  assert.equal(r.ok, e.ok, c.name + ' ok'); assert.deepEqual(r.reasons, e.reasons, c.name + ' motivos');
  assert.equal(r.nFood, e.nFood, c.name + ' nFood'); assert.equal(r.nWeighings, e.nWeighings, c.name + ' nW');
  assert.equal(r.nWeighings1, e.n1); assert.equal(r.nWeighings2, e.n2);
  near(r.avgIntake, e.avgIntake, c.name + ' avg'); near(r.slope, e.slope, c.name + ' slope'); near(r.tdee, e.tdee, c.name + ' tdee');
  near(r.ciHalf, e.ciHalf, c.name + ' ci'); assert.equal(r.confidence, e.confidence, c.name + ' confianza');
}));
test('gasto por datos rodante', () => {
  const r = C.rollingTdee(nan(F.rolling.weights), nan(F.rolling.kcalValid), F.rolling.window);
  F.rolling.expected.forEach((e, i) => {
    if (e === null) return assert.equal(r[i], null, `día ${i} debería estar vacío`);
    assert.notEqual(r[i], null, `día ${i} debería tener estimación`);
    near(r[i].tdee, e.tdee, `tdee[${i}]`); near(r[i].lo, e.lo, `lo[${i}]`); near(r[i].hi, e.hi, `hi[${i}]`);
  });
});
test('recomendación', () => F.recommend.forEach((c) => {
  const r = C.recommendTarget(c.data, ...c.args), e = c.expected;
  assert.equal(r.status, e.status); near(r.ideal, e.ideal, 'ideal'); near(r.recommended, e.recommended, 'rec'); near(r.delta, e.delta, 'delta');
  near(r.implied, e.implied, 'implied'); assert.equal(r.withinNoise, e.withinNoise); assert.equal(r.limitedByStep, e.limitedByStep); assert.equal(r.limitedByFloor, e.limitedByFloor);
}));
test('tabla diaria integrada vs services.daily_frame / tdee_timeline', () => {
  const f = F.frame, fr = C.buildFrame({ days: f.days, targets: f.targets, profile: f.profile }, f.start, f.end, f.today), e = f.expected;
  assert.deepEqual(fr.dates, e.dates);
  nearArr(fr.ma7, e.ma7, 'ma7'); nearArr(fr.bfDaily, e.bfDaily, 'bfDaily'); nearArr(fr.lean, e.lean, 'lean'); nearArr(fr.kcal, e.kcal, 'kcal');
  assert.deepEqual(fr.valid, e.valid); nearArr(fr.kcalValid, e.kcalValid, 'kcalValid'); nearArr(fr.targetKcal, e.targetKcal, 'target');
  const fs = C.formulaSeries(fr._full, f.profile);
  const full = fr._full, cutF = fs.slice(full.from).map((x) => (x ? x.tdee : null));
  nearArr(cutF, e.formulaTdee, 'fórmula');
  const roll = C.rollingTdee(full.weight, full.kcalValid, 14).slice(full.from).map((x) => (x ? x.tdee : null));
  nearArr(roll, e.dataTdee, 'por datos');
  const lo = C.rollingTdee(full.weight, full.kcalValid, 14).slice(full.from).map((x) => (x ? x.lo : null));
  nearArr(lo, e.ciLow, 'IC inf');
});
test('errores de entrada', () => {
  assert.throws(() => C.mifflin(0, 180, 30, 'M')); assert.throws(() => C.katch(80, 2)); assert.throws(() => C.navyBodyFat('F', 165, 32, 75));
  assert.throws(() => C.goalAdjustment('lose', -1)); assert.throws(() => C.t95(0));
});
