"""Genera mobile/tests/fixtures.json con resultados de la implementación Python (referencia).
Uso:  .venv/bin/python mobile/tests/gen_fixtures.py
"""
import json, math, sys
from datetime import date, timedelta
from pathlib import Path
import numpy as np, pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from macro_tracker.calc import adaptive, bmr, body_comp, series, targets
from macro_tracker.db.connection import connect
from macro_tracker.db.repository import Repository
from macro_tracker import services

def nn(x):
    if x is None: return None
    if isinstance(x, (float, np.floating)): return None if math.isnan(x) else float(x)
    if isinstance(x, (np.integer,)): return int(x)
    if isinstance(x, (np.bool_,)): return bool(x)
    return x
def arr(s): return [nn(v) for v in s]

out = {}
# --- BMR / navy / referencia de proteína
out["bmr"] = [
    {"args": [80, 180, 30, "M", None, "auto"], "expected": vars(bmr.estimate_bmr(80, 180, 30, "M"))},
    {"args": [60, 165, 25, "F", None, "auto"], "expected": vars(bmr.estimate_bmr(60, 165, 25, "F"))},
    {"args": [70, 175, 30, "M", 15, "auto"], "expected": vars(bmr.estimate_bmr(70, 175, 30, "M", 15))},
    {"args": [70, 175, 30, "M", 15, "mifflin"], "expected": vars(bmr.estimate_bmr(70, 175, 30, "M", 15, "mifflin"))},
]
out["navy"] = [
    {"args": ["M", 180, 38, 85, None], "expected": body_comp.navy_body_fat_pct("M", 180, 38, 85)},
    {"args": ["F", 165, 32, 75, 98], "expected": body_comp.navy_body_fat_pct("F", 165, 32, 75, 98)},
]
out["proteinRef"] = [{"args": [w, b], "expected": body_comp.protein_reference_weight(w, b)} for w, b in [(100, None), (100, 40), (100, 15), (75, 20)]]
out["age"] = [{"args": [b, o], "expected": bmr.age_on(date.fromisoformat(b), date.fromisoformat(o))} for b, o in [("2000-09-14", "2026-09-13"), ("2000-09-14", "2026-09-14"), ("1996-02-29", "2026-02-28")]]
# --- metas
out["calorieTarget"] = []
for tdee, b, goal, rate in [(2700, 1800, "lose", 0.5), (2000, 1800, "lose", 1.0), (2500, 1800, "gain", 0.25), (2500, 1800, "maintain", 0.5)]:
    t = targets.calorie_target(tdee, b, goal, rate)
    out["calorieTarget"].append({"args": [tdee, b, goal, rate], "expected": {"kcal": t.kcal, "adjustment": t.adjustment_kcal, "unfloored": t.unfloored_kcal,
        "floorApplied": t.floor_applied, "effectiveRate": t.effective_rate_kg_week}})
out["macros"] = []
for kcal, w, goal, ref, fp in [(2500, 80, "maintain", None, 0.25), (2200, 80, "lose", None, 0.25), (1500, 90, "maintain", None, 0.25), (1400, 100, "lose", None, 0.25),
                               (1000, 100, "lose", None, 0.25), (2500, 100, "maintain", 75, 0.25), (2800, 70, "gain", None, 0.30)]:
    m = targets.macro_targets(kcal, w, goal, ref, fat_pct_kcal=fp)
    out["macros"].append({"args": [kcal, w, goal, ref, [1.6, 2.2], 0.6, fp], "expected": {"protein": m.protein_g, "carbs": m.carbs_g, "fat": m.fat_g,
        "proteinPerKg": m.protein_g_per_kg, "proteinRange": list(m.protein_range_g), "fatFloor": m.fat_floor_g, "flags": list(m.flags)}})
# --- series
rng = np.random.default_rng(42)
idx = series.daily_index("2026-01-01", "2026-02-12")  # 43 días (6 semanas + 1)
w = pd.Series(80 - 0.05 * np.arange(len(idx)) + rng.normal(0, 0.4, len(idx)), index=idx)
w.iloc[[3, 4, 9, 17, 18, 19, 30]] = np.nan
out["ma"] = {"values": arr(w), "expected": arr(series.moving_average(w))}
bf = pd.Series(np.nan, index=idx); bf.iloc[5] = 20.0; bf.iloc[20] = 18.5; bf.iloc[33] = 18.0
out["interp"] = {"values": arr(bf), "expected": arr(body_comp.interpolate_body_fat(bf))}
kcal = pd.Series(2000 + rng.normal(0, 150, len(idx)), index=idx); kcal.iloc[[2, 3, 11, 12, 25]] = np.nan; kcal.iloc[7] = 400; kcal.iloc[8] = 1200
ov = {idx[7]: True, idx[8]: False, idx[0]: True, idx[2]: True}
valid = series.valid_food_day_mask(kcal, 1000, ov)
out["valid"] = {"kcal": arr(kcal), "overrides": [None if d not in ov else bool(ov[d]) for d in idx], "expected": [bool(v) for v in valid]}
kv = kcal.where(valid)
wk = series.weekly_intake(kv)
out["weekly"] = {"dates": [d.date().isoformat() for d in idx], "kcalValid": arr(kv),
                 "expected": [{"weekStart": r.week_start.date().isoformat(), "meanKcal": float(r.mean_kcal), "validDays": int(r.valid_days)} for r in wk.itertuples()]}
# --- adaptación: varios escenarios
def scenario(name, w_series, k_series, end_idx, window=14):
    wi = pd.Series(w_series, index=idx[: len(w_series)]); ki = pd.Series(k_series, index=idx[: len(k_series)])
    r = adaptive.estimate_tdee_from_data(wi, ki, idx[end_idx], window_days=window)
    return {"name": name, "weights": arr(wi), "kcalValid": arr(ki), "endIdx": end_idx, "window": window,
            "expected": {"ok": r.ok, "reasons": list(r.reasons), "nFood": r.n_food_days, "nWeighings": r.n_weighings, "n1": r.n_weighings_first_half,
                         "n2": r.n_weighings_second_half, "avgIntake": nn(r.avg_intake_kcal), "slope": nn(r.slope_kg_per_day), "tdee": nn(r.tdee_kcal),
                         "ciHalf": nn(r.ci_half_width_kcal), "confidence": r.confidence}}
n = len(idx)
kv_full = kcal.where(series.valid_food_day_mask(kcal, 1000)).to_numpy()
cases = [scenario("ruido+huecos 14d", w.to_numpy(), kv_full, 20), scenario("ventana 28d", w.to_numpy(), kv_full, 40, 28)]
w2 = w.copy(); w2.iloc[:22] = np.nan
cases.append(scenario("pesajes solo en una mitad", w2.to_numpy(), kv_full, 28))
k2 = pd.Series(kv_full).copy(); k2.iloc[10:25] = np.nan
cases.append(scenario("pocos días de comida", w.to_numpy(), k2.to_numpy(), 24))
cases.append(scenario("ventana antes del inicio", w.to_numpy()[:10], kv_full[:10], 9))
out["adaptive"] = cases
# rolling
r = adaptive.rolling_tdee_from_data(w, kv, window_days=14)
out["rolling"] = {"weights": arr(w), "kcalValid": arr(kv), "window": 14,
                  "expected": [None if d not in r.index else {"tdee": float(r.loc[d, "tdee"]), "lo": float(r.loc[d, "ci_low"]), "hi": float(r.loc[d, "ci_high"])} for d in idx]}
# recomendación
recs = []
for tdee, half, cur, goal, rate, b in [(2800, 150, 2200, "maintain", 0, 1700), (2250, 150, 2200, "maintain", 0, 1700), (2600, 150, 2200, "lose", 0.5, 1700),
                                       (1900, 150, 1850, "lose", 0.5, 1800), (2400, 400, 2200, "maintain", 0, 1700)]:
    base = adaptive.estimate_tdee_from_data(w, kv, idx[20])
    from dataclasses import replace
    fake = replace(base, ok=True, reasons=(), tdee_kcal=tdee, ci_half_width_kcal=half, confidence="medium")
    rc = adaptive.recommend_target(fake, cur, goal, rate, b)
    recs.append({"data": {"ok": True, "tdee": tdee, "ciHalf": half}, "args": [cur, goal, rate, b],
                 "expected": {"status": rc.status, "ideal": nn(rc.ideal_kcal), "recommended": nn(rc.recommended_kcal), "delta": nn(rc.delta_kcal),
                              "implied": nn(rc.implied_tdee_kcal), "withinNoise": rc.within_noise, "limitedByStep": rc.limited_by_step, "limitedByFloor": rc.limited_by_floor}})
out["recommend"] = recs
# --- tabla diaria integrada (services.daily_frame) con una base real en memoria
repo = Repository(connect(":memory:"))
repo.save_profile(sex="M", birth_date="1996-05-20", height_cm=180, activity_level="moderate", goal="lose", rate_kg_week=0.5, min_valid_day_kcal=1000)
food = repo.add_food("Comida", 100, 10, 20, 5)   # 100 kcal/100 g -> grams == kcal
today = date(2026, 2, 12)
days = {}
for i, d in enumerate(idx):
    day = d.date()
    doc = {}
    if not np.isnan(w.iloc[i]): doc["weight"] = float(w.iloc[i]); repo.upsert_body(day, weight_kg=float(w.iloc[i]), **({"body_fat_pct": float(bf.iloc[i]), "body_fat_source": "measured"} if not np.isnan(bf.iloc[i]) else {}))
    elif not np.isnan(bf.iloc[i]): repo.upsert_body(day, body_fat_pct=float(bf.iloc[i]), body_fat_source="measured")
    if not np.isnan(bf.iloc[i]): doc["bf"] = float(bf.iloc[i])
    if not np.isnan(kcal.iloc[i]):
        g = float(kcal.iloc[i]); repo.add_log(day, "lunch", food, g)
        doc["entries"] = [{"kcal": g, "p": g * 0.1, "c": g * 0.2, "f": g * 0.05}]
    if d in ov: repo.set_day_status(day, bool(ov[d])); doc["forced"] = bool(ov[d])
    if doc: days[day.isoformat()] = doc
repo.set_target("2026-01-01", 2200, 150, 250, 70, "formula"); repo.set_target("2026-01-20", 2400, 160, 290, 75, "data")
frame = services.daily_frame(repo, "2026-01-05", "2026-02-12", today=today)
import unittest.mock as _mock
class _FixedDate(date):          # tdee_timeline usa date.today(); se fija al "hoy" del fixture
    @classmethod
    def today(cls): return date(2026, 2, 12)
with _mock.patch.object(services, "date", _FixedDate):
    tl = services.tdee_timeline(repo, "2026-01-05", "2026-02-12", window_days=14)
out["frame"] = {
    "days": days, "profile": {"sex": "M", "birth": "1996-05-20", "heightCm": 180, "activity": "moderate", "minValidKcal": 1000, "mifflinOnly": False},
    "targets": [{"from": "2026-01-01", "kcal": 2200}, {"from": "2026-01-20", "kcal": 2400}], "start": "2026-01-05", "end": "2026-02-12", "today": "2026-02-12",
    "expected": {"dates": [d.date().isoformat() for d in frame.index], "ma7": arr(frame["weight_ma7"]), "bfDaily": arr(frame["bf_daily"]), "lean": arr(frame["lean_mass_kg"]),
                 "kcal": arr(frame["kcal"]), "valid": [bool(v) for v in frame["food_valid"]], "kcalValid": arr(frame["kcal_valid"]), "targetKcal": arr(frame["target_kcal"]),
                 "formulaTdee": arr(tl["formula_tdee"]), "dataTdee": arr(tl["data_tdee"]), "ciLow": arr(tl["ci_low"])}}
(ROOT / "mobile/tests/fixtures.json").write_text(json.dumps(out, indent=1))
print("fixtures OK:", {k: (len(v) if isinstance(v, list) else "·") for k, v in out.items()})
