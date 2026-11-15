import numpy as np
import pytest
import engine

ANCHORS = {0.01: (0.199, 0.251, 0.424), 0.1: (0.021, 0.027, 0.142), 0.3: (0.044, 0.005, 0.058),
           1.0: (0.285, 0.027, 0.122), 10: (0.811, 0.015, 0.019)}


# ==================== LUNG ====================
@pytest.mark.parametrize("dp", ANCHORS)
def test_lung_anchors(dp):
    d = engine.deposition(dp)
    assert (d["HA"], d["TB"], d["AL"]) == pytest.approx(ANCHORS[dp], abs=0.005)


def test_fractions_are_valid():
    d = engine.deposition(engine.GRID)
    total = d["HA"] + d["TB"] + d["AL"]
    assert all((v >= 0).all() for v in d.values())
    assert (total <= 1).all()


def test_least_deposition_near_0_3_um():
    d = engine.deposition(engine.GRID)
    total = d["HA"] + d["TB"] + d["AL"]
    assert 0.2 < engine.GRID[np.argmin(total)] < 0.5


# ==================== GRAVITY ====================
@pytest.mark.parametrize("dp,drop", [(0.5, 0.25), (1.0, 0.32)])
def test_lunar_calibration(dp, drop):
    earth, moon = engine.deposition(dp), engine.deposition_at_gravity(dp, 1 / 6)
    assert 1 - (moon["TB"] + moon["AL"]) / (earth["TB"] + earth["AL"]) == pytest.approx(drop, abs=0.005)


def test_gravity_barely_matters_for_tiny_particles():
    earth, space = engine.deposition(0.05), engine.deposition_at_gravity(0.05, 0)
    assert space["AL"] == pytest.approx(earth["AL"], rel=0.01)


# ==================== AGING ====================
def test_aging_fit_is_textbook_sized():
    assert engine.AGING["n_pairs"] >= 30
    assert 1e-10 < engine.AGING["K_pooled_cm3_s"] < 1e-8


def test_aging_grows_particles_and_cuts_count():
    n, gmd = engine.age(1e6, 0.1, 1e-9, 600)
    assert n < 1e6 and gmd > 0.1


# ==================== EXPOSURE + MATRIX ====================
def test_dose_scales_with_dilution_and_breathing():
    a = engine.exposure("Kapton", 0.01, 0, "rest")
    b = engine.exposure("Kapton", 0.001, 0, "rest")
    c = engine.exposure("Kapton", 0.01, 0, "heavy")
    assert a["alveolar_particles_per_min"] == pytest.approx(10 * b["alveolar_particles_per_min"])
    assert c["alveolar_particles_per_min"] > a["alveolar_particles_per_min"]


def test_microgravity_gives_a_band():
    e = engine.exposure("Silicone", 1, 15, "rest", "microgravity")
    assert e["band_low_gravity_effect"]["fraction_by_count"]["AL"] >= e["fraction_by_count"]["AL"]


def test_matrix_finds_the_gaps():
    m = engine.hazard_matrix()
    assert m["rank_alveolar_fraction"][0] == "Kapton"
    assert any("Kapton" in g for g in m["gaps"])
