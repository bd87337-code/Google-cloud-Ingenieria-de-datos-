// Pruebas de la validación de estimaciones de IA, la conversión de etiquetas y la base inicial de alimentos.
import test from 'node:test';
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import { readFileSync } from 'node:fs';
const require = createRequire(import.meta.url);
const C = require('../src/calc.js');
const seed = JSON.parse(readFileSync(new URL('../src/seed-foods.js', import.meta.url), 'utf8').replace(/^[\s\S]*?const SEED_FOODS = /, '').replace(/;\s*$/, ''));

test('IA: acepta un renglón coherente y lo deja tal cual', () => {
  const [it] = C.normalizeAiItems({ items: [{ name: 'Taco de pastor', grams: 110, kcal: 230, protein: 12, carbs: 20, fat: 11, confidence: 'media', note: 'con piña' }] });
  assert.equal(it.name, 'Taco de pastor'); assert.equal(it.kcal, 230); assert.equal(it.adjusted, false); assert.equal(it.confidence, 'media');
});
test('IA: si las kcal no cuadran con los macros (>15 %) las recalcula y lo marca', () => {
  const [it] = C.normalizeAiItems([{ name: 'X', grams: 100, kcal: 500, protein: 10, carbs: 20, fat: 5 }]);   // macros → 165 kcal
  assert.equal(it.kcal, 4 * 10 + 4 * 20 + 9 * 5); assert.equal(it.adjusted, true);
});
test('IA: descarta lo imposible o inválido, sin tirar los renglones buenos', () => {
  const raw = [
    { name: 'Bueno', grams: 100, kcal: 100, protein: 5, carbs: 15, fat: 2 },
    { name: '', grams: 100, kcal: 100, protein: 5, carbs: 15, fat: 2 },                         // sin nombre
    { name: 'Gramos 0', grams: 0, kcal: 100, protein: 5, carbs: 15, fat: 2 },
    { name: 'Negativo', grams: 100, kcal: 100, protein: -5, carbs: 15, fat: 2 },
    { name: 'Macros >100 g', grams: 50, kcal: 400, protein: 40, carbs: 40, fat: 10 },           // 90 g de macros en 50 g
    { name: 'Texto', grams: 'mucho', kcal: 100, protein: 5, carbs: 15, fat: 2 },
    { name: 'Gigante', grams: 5000, kcal: 100, protein: 5, carbs: 15, fat: 2 }, null, 'basura'];
  const out = C.normalizeAiItems(raw);
  assert.deepEqual(out.map((x) => x.name), ['Bueno']);
});
test('IA: tolera formas inesperadas de la respuesta', () => {
  assert.deepEqual(C.normalizeAiItems(null), []); assert.deepEqual(C.normalizeAiItems({}), []); assert.deepEqual(C.normalizeAiItems('hola'), []);
  assert.equal(C.normalizeAiItems({ items: Array.from({ length: 40 }, (_, i) => ({ name: 'i' + i, grams: 50, kcal: 80, protein: 3, carbs: 12, fat: 2 })) }).length, 15);  // tope de 15
  assert.equal(C.normalizeAiItems([{ name: 'a', grams: 50, kcal: 80, protein: 3, carbs: 12, fat: 2, confidence: 'excelente' }])[0].confidence, 'media');
});
test('IA: aceita p/c/f como alias y nunca devuelve NaN', () => {
  const [it] = C.normalizeAiItems([{ name: 'Alias', grams: 100, p: 10, c: 20, f: 5 }]);   // sin kcal
  assert.equal(it.kcal, 165); assert.ok(Object.values(it).every((v) => typeof v !== 'number' || Number.isFinite(v)));
});

test('etiqueta: por 100 g pasa directo', () => {
  const r = C.labelToPer100({ basis: 'per100g', kcal: 250, protein: 8, carbs: 40, fat: 6 });
  assert.equal(r.ok, true); assert.equal(r.kcal, 250); assert.equal(r.mismatch, false);
});
test('etiqueta: por porción se convierte a 100 g con el peso de la porción', () => {
  // porción de 30 g con 120 kcal, 3 P, 22 C, 2.5 F  →  por 100 g: ×(100/30)
  const r = C.labelToPer100({ basis: 'perServing', servingG: 30, servingLabel: '1 galleta', kcal: 120, protein: 3, carbs: 22, fat: 2.5 });
  assert.equal(r.ok, true); assert.ok(Math.abs(r.kcal - 400) < 1e-9 && Math.abs(r.p - 10) < 1e-9 && Math.abs(r.c - 73.3333333) < 1e-6);
  assert.equal(r.servingG, 30); assert.equal(r.servingLabel, '1 galleta');
});
test('etiqueta: por porción sin peso de la porción no se inventa', () => {
  assert.deepEqual(C.labelToPer100({ basis: 'perServing', kcal: 120, protein: 3, carbs: 22, fat: 2.5 }), { ok: false, reason: 'no_serving' });
});
test('etiqueta: lectura imposible o ilegible se rechaza', () => {
  assert.equal(C.labelToPer100({ basis: 'per100g', kcal: 250, protein: 60, carbs: 60, fat: 6 }).reason, 'implausible');
  assert.equal(C.labelToPer100({ basis: 'per100g', kcal: 'n/a', protein: 8, carbs: 40, fat: 6 }).reason, 'unreadable');
  assert.equal(C.labelToPer100({ basis: 'otra', kcal: 1, protein: 1, carbs: 1, fat: 1 }).reason, 'unreadable');
  assert.equal(C.labelToPer100(null).reason, 'unreadable');
});
test('etiqueta: avisa si las kcal leídas no cuadran con los macros (posible error de lectura)', () => {
  assert.equal(C.labelToPer100({ basis: 'per100g', kcal: 480, protein: 8, carbs: 40, fat: 6 }).mismatch, true);
});
test('porcentaje estimado del día', () => {
  const days = { '2026-03-01': { entries: [{ kcal: 600, est: true }, { kcal: 400 }] }, '2026-03-02': { entries: [{ kcal: 1000 }] }, '2026-03-09': { entries: [{ kcal: 999, est: true }] } };
  assert.equal(C.estimatedShare(days, '2026-03-01', '2026-03-02'), 600 / 2000);
  assert.equal(C.estimatedShare({}, '2026-03-01', '2026-03-02'), 0);
});

test('base inicial: ids únicos, valores plausibles y calorías coherentes con los macros', () => {
  assert.ok(seed.length >= 90);
  assert.equal(new Set(seed.map((x) => x.id)).size, seed.length);
  for (const x of seed) {
    assert.ok(x.name && x.fdc, x.name);
    assert.ok(x.kcal >= 0 && x.kcal <= 900, x.name + ' kcal');
    assert.ok(x.p + x.c + x.f <= 100.5, x.name + ' macros');
    assert.ok(!C.kcalMismatch(x.kcal, x.p, x.c, x.f), `${x.name}: ${x.kcal} vs ${C.kcalFromMacros(x.p, x.c, x.f)}`);
    if (x.servingG != null) assert.ok(x.servingG > 0 && x.servingLabel, x.name + ' porción');
  }
  const tort = seed.find((x) => x.name === 'Tortilla de maíz');
  assert.deepEqual([tort.kcal, tort.p, tort.c, tort.f, tort.servingG], [218, 5.7, 44.6, 2.9, 24]);     // valor de USDA verificado arriba
  assert.ok(seed.some((x) => /queso fresco/i.test(x.name)) && seed.some((x) => /frijol negro/i.test(x.name)));
});
