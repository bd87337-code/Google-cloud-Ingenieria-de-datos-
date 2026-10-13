import pandas as pd
import pytest

from macro_tracker.calc.body_comp import (
    fat_mass_kg,
    interpolate_body_fat,
    lean_mass_kg,
    lean_mass_series,
    navy_body_fat_pct,
    protein_reference_weight,
)


def test_lean_and_fat_mass():
    assert lean_mass_kg(100, 25) == pytest.approx(75)
    assert fat_mass_kg(100, 25) == pytest.approx(25)


def test_protein_reference_without_body_fat_is_total_weight():
    assert protein_reference_weight(90) == 90


def test_protein_reference_high_body_fat_is_reduced():
    # masa magra 60 kg -> peso equivalente a 20 % de grasa = 60 / 0.8 = 75
    assert protein_reference_weight(100, 40) == pytest.approx(75)


def test_protein_reference_never_exceeds_weight():
    # masa magra 85 -> 85 / 0.8 = 106.25 > 100 -> se limita al peso real
    assert protein_reference_weight(100, 15) == 100


def test_protein_reference_at_20_percent_equals_weight():
    assert protein_reference_weight(75, 20) == pytest.approx(75)


def test_navy_male_matches_hand_computation():
    assert navy_body_fat_pct("M", 180, 38, 85) == pytest.approx(16.11, abs=0.05)


def test_navy_female_matches_hand_computation():
    assert navy_body_fat_pct("F", 165, 32, 75, hip_cm=98) == pytest.approx(28.94, abs=0.05)


def test_navy_female_requires_hip():
    with pytest.raises(ValueError):
        navy_body_fat_pct("F", 165, 32, 75)


def test_navy_rejects_waist_not_greater_than_neck():
    with pytest.raises(ValueError):
        navy_body_fat_pct("M", 180, 40, 40)


def test_interpolate_body_fat_between_points_and_hold_after():
    idx = pd.date_range("2026-01-01", periods=11, freq="D")
    s = pd.Series(float("nan"), index=idx)
    s.iloc[2] = 20.0
    s.iloc[6] = 18.0
    out = interpolate_body_fat(s)
    assert out.iloc[:2].isna().all()  # antes de la primera medición: sin extrapolar
    assert out.iloc[2] == 20.0
    assert out.iloc[4] == pytest.approx(19.0)
    assert out.iloc[6] == 18.0
    assert (out.iloc[7:] == 18.0).all()  # se mantiene después de la última


def test_interpolate_body_fat_all_missing_stays_missing():
    s = pd.Series(float("nan"), index=pd.date_range("2026-01-01", periods=3))
    assert interpolate_body_fat(s).isna().all()


def test_lean_mass_series_propagates_nan():
    idx = pd.date_range("2026-01-01", periods=3)
    weight = pd.Series([80.0, float("nan"), 78.0], index=idx)
    bf = pd.Series([20.0, 20.0, 10.0], index=idx)
    out = lean_mass_series(weight, bf)
    assert out.iloc[0] == pytest.approx(64.0)
    assert pd.isna(out.iloc[1])
    assert out.iloc[2] == pytest.approx(70.2)
