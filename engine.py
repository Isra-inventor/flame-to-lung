from pathlib import Path
import numpy as np
import pandas as pd

DATA = Path(__file__).parent / "data" / "processed"
GRID = np.logspace(-3, 2, 500)
BREATHING_L_MIN = {"rest": 7.5, "light": 25.0, "heavy": 50.0}
GRAVITY = {"1g": 1.0, "lunar": 1 / 6, "microgravity": 0.0}


# ==================== 1. LUNG DEPOSITION (ICRP 66, Hinds 1999) ====================
def deposition(dp):
    dp = np.asarray(dp, dtype=float)
    ln = np.log(dp)
    inhalable = 1 - 0.5 * (1 - 1 / (1 + 0.00076 * dp**2.8))
    head = inhalable * (1 / (1 + np.exp(6.84 + 1.183 * ln)) + 1 / (1 + np.exp(0.924 - 1.885 * ln)))
    tb = (0.00352 / dp) * (np.exp(-0.234 * (ln + 3.40) ** 2) + 63.9 * np.exp(-0.819 * (ln - 1.61) ** 2))
    al = (0.0155 / dp) * (np.exp(-0.416 * (ln + 2.84) ** 2) + 19.11 * np.exp(-0.482 * (ln - 1.362) ** 2))
    overshoot = np.maximum(head + tb + al, 1.0)
    return {"HA": head / overshoot, "TB": tb / overshoot, "AL": al / overshoot}


# ==================== 2. GRAVITY CORRECTION ====================
# Calibrated so lunar gravity cuts deep-lung (TB+AL) deposition by 25% at 0.5 um
# and 32% at 1 um (Darquenne & Prisk 2008). "low" = half that effect (assumption).
LUNAR_DROP = {0.5: 0.25, 1.0: 0.32}
PLATEAU = 0.40


def _fit_sedimentation_curve():
    share = {d: drop / (1 - GRAVITY["lunar"]) for d, drop in LUNAR_DROP.items()}
    logit = {d: np.log(s / (PLATEAU - s)) for d, s in share.items()}
    slope = (logit[1.0] - logit[0.5]) / np.log(2)
    midpoint = np.exp(-logit[1.0] / slope)
    return slope, midpoint


SLOPE, MIDPOINT = _fit_sedimentation_curve()


def sedimentation_share(dp, band="high"):
    s = PLATEAU / (1 + np.exp(-SLOPE * (np.log(dp) - np.log(MIDPOINT))))
    return s if band == "high" else 0.5 * s


def deposition_at_gravity(dp, g=1.0, band="high"):
    d = deposition(dp)
    factor = 1 - sedimentation_share(np.asarray(dp, dtype=float), band) * (1 - g)
    return {"HA": d["HA"], "TB": d["TB"] * factor, "AL": d["AL"] * factor}


# ==================== 3. POLYDISPERSE SMOKE (lognormal) ====================
def lognormal_weights(median, gsd):
    w = np.exp(-0.5 * (np.log(GRID / median) / np.log(gsd)) ** 2)
    return w / w.sum()


def smoke_deposition(gmd, gsd, g=1.0, band="high"):
    d = deposition_at_gravity(GRID, g, band)
    mass_median = gmd * np.exp(3 * np.log(gsd) ** 2)
    by_count, by_mass = lognormal_weights(gmd, gsd), lognormal_weights(mass_median, gsd)
    return ({k: float((v * by_count).sum()) for k, v in d.items()},
            {k: float((v * by_mass).sum()) for k, v in d.items()})


# ==================== 4. SMOKE AGING (coagulation fitted to SAME) ====================
def same_pairs():
    same = pd.read_csv(DATA / "same.csv")
    same = same[same["usable_for_size"]]
    fresh = same[~same["is_aged"]]
    aged = same[same["is_aged"]].copy()
    aged["same_run"] = aged["same_run"].str.rstrip("a")
    p = aged.merge(fresh, on=["same_run", "material"], suffixes=("", "_fresh"))
    p["dt_s"] = p["net_aging_s"] - p["net_aging_s_fresh"]
    p["K"] = (1 / p["number_conc_per_cm3"] - 1 / p["number_conc_per_cm3_fresh"]) / p["dt_s"]
    p["b"] = (np.log(p["gmd_um"] / p["gmd_um_fresh"])
              / np.log(p["number_conc_per_cm3_fresh"] / p["number_conc_per_cm3"]))
    return p[(p["K"] > 0) & (p["dt_s"] > 0)]


def age(n0, gmd0, k, seconds, exponent=1 / 3):
    n = n0 / (1 + k * n0 * seconds)
    return n, gmd0 * (n0 / n) ** exponent


def fit_aging():
    p = same_pairs()
    per_material = {m: float(g["K"].median()) for m, g in p.groupby("material") if len(g) >= 5}
    err_n, err_physics, err_empirical = [], [], []
    for i, row in p.iterrows():
        others = p.drop(i)
        k, b = others["K"].median(), others["b"].median()
        n, gmd = age(row["number_conc_per_cm3_fresh"], row["gmd_um_fresh"], k, row["dt_s"])
        _, gmd_b = age(row["number_conc_per_cm3_fresh"], row["gmd_um_fresh"], k, row["dt_s"], b)
        err_n.append(abs(n - row["number_conc_per_cm3"]) / row["number_conc_per_cm3"])
        err_physics.append(abs(gmd - row["gmd_um"]))
        err_empirical.append(abs(gmd_b - row["gmd_um"]))
    return {"n_pairs": len(p), "K_pooled_cm3_s": float(p["K"].median()),
            "K_by_material": per_material, "b_empirical": float(p["b"].median()),
            "validation": {"number_conc_mean_abs_pct_error": float(np.mean(err_n) * 100),
                           "gmd_mae_um_volume_conserving": float(np.mean(err_physics)),
                           "gmd_mae_um_empirical_exponent": float(np.mean(err_empirical))},
            "note": "K is an effective coefficient: chamber wall losses also lower N.",
            "source": "PSI-101 SAME/SAME-R fresh vs aged pairs"}


AGING = fit_aging()


# ==================== 5. CREW EXPOSURE ====================
def fresh_smoke(material):
    same = pd.read_csv(DATA / "same.csv")
    rows = same[(same["material"] == material) & same["usable_for_size"] & ~same["is_aged"]]
    if rows.empty:
        raise ValueError(f"No SAME size data for {material}")
    cols = ["number_conc_per_cm3", "gmd_um", "gsd", "dusttrak_mass_mg_m3"]
    return rows[cols].median().to_dict() | {"n_runs": len(rows)}


def exposure(material, dilution=0.01, minutes=0, activity="rest", gravity="1g"):
    src = fresh_smoke(material)
    k = AGING["K_by_material"].get(material, AGING["K_pooled_cm3_s"])
    n0 = src["number_conc_per_cm3"] * dilution
    n, gmd = age(n0, src["gmd_um"], k, minutes * 60)
    _, gmd_empirical = age(n0, src["gmd_um"], k, minutes * 60, AGING["b_empirical"])
    mass = src["dusttrak_mass_mg_m3"] * dilution
    air_cm3_min = BREATHING_L_MIN[activity] * 1000
    g = GRAVITY[gravity]

    def dose(band):
        count, by_mass = smoke_deposition(gmd, src["gsd"], g, band)
        return {"fraction_by_count": count, "fraction_by_mass": by_mass,
                "alveolar_particles_per_min": n * air_cm3_min * count["AL"],
                "mass_deposited_ug_per_10min": mass * (air_cm3_min / 1e6) * 10 * sum(by_mass.values()) * 1000}

    result = dose("high")
    result["band_low_gravity_effect"] = dose("low") if g < 1 else None
    result |= {
        "label": "Modeled",
        "inputs": {"material": material, "dilution": dilution, "minutes": minutes,
                   "activity": activity, "gravity": gravity},
        "measured_source_smoke": src,
        "aged_smoke": {"number_conc_per_cm3": n, "gmd_um": gmd, "gmd_um_empirical_exponent": gmd_empirical,
                       "gsd": src["gsd"], "mass_mg_m3": mass, "K_cm3_s": k},
        "sources": ["PSI-101 (SAME smoke, measured)", "ICRP 66 / Hinds 1999 (deposition model)",
                    "Darquenne & Prisk 2008 (gravity calibration)"],
        "limits": "Deposition is not toxicity. Gases (CO, HF) not modelled. Average adult, unit-density spheres.",
    }
    return result


# ==================== 6. HAZARD MATRIX + GAP MAP ====================
SMOKE_NAME = {"Kapton": "Kapton", "Silicone": "Silicone", "Lampwick": "Cotton", "Teflon": "Teflon", "Pyrell": "Pyrell foam"}
FIRE_NAME = {"Cotton/SIBAL": "Cotton", "PMMA": "PMMA", "Nomex": "Nomex", "Ultem": "Ultem", "Wax": "Wax"}


def hazard_matrix():
    rows = {}
    for same_name, name in SMOKE_NAME.items():
        e = exposure(same_name, dilution=1, minutes=0, activity="rest", gravity="1g")
        rows[name] = {"smoke": {"gmd_um": e["measured_source_smoke"]["gmd_um"],
                                "mass_mg_m3": e["measured_source_smoke"]["dusttrak_mass_mg_m3"],
                                "alveolar_fraction_by_count": e["fraction_by_count"]["AL"],
                                "mass_deposited_ug_per_10min": e["mass_deposited_ug_per_10min"],
                                "n_runs": e["measured_source_smoke"]["n_runs"], "source": "PSI-101"}}

    bass = pd.read_csv(DATA / "bass.csv")
    for family, name in FIRE_NAME.items():
        counts = bass[bass["material_family"] == family]["outcome"].value_counts().to_dict()
        rows.setdefault(name, {})["fire"] = {"bass_tests": counts, "source": "PSI-26"}

    saffire = pd.read_csv(DATA / "saffire.csv")
    for key, name in [("Silicone", "Silicone"), ("SIBAL", "Cotton"), ("PMMA", "PMMA"), ("Nomex", "Nomex")]:
        s = saffire[saffire["material"].str.contains(key)]
        fire = rows.setdefault(name, {}).setdefault("fire", {"source": ""})
        fire["saffire_samples"] = len(s)
        fire["saffire_ug_burn_length"] = s["ug_burn_length"].dropna().tolist()
        fire["source"] = (fire["source"] + ", PSI-98/99/100").strip(", ")

    gaps = []
    for name, r in rows.items():
        if "fire" not in r:
            gaps.append(f"No microgravity flammability data for {name} in these datasets.")
        if "smoke" not in r:
            gaps.append(f"No smoke particle data for {name} in these datasets.")
    has_smoke = {n: r["smoke"] for n, r in rows.items() if "smoke" in r}
    return {"materials": rows, "gaps": gaps,
            "rank_alveolar_fraction": sorted(has_smoke, key=lambda n: -has_smoke[n]["alveolar_fraction_by_count"]),
            "rank_mass_dose": sorted(has_smoke, key=lambda n: -has_smoke[n]["mass_deposited_ug_per_10min"])}


# ==================== 7. FLAMMABILITY MODEL (machine learning on FLEX) ====================
FLEX_FEATURES = ["heptane", "o2_frac", "co2_frac", "he_frac", "pressure_mmhg", "d0_mm"]


def fit_flammability():
    from sklearn.ensemble import RandomForestRegressor
    from sklearn.linear_model import LogisticRegression
    from sklearn.metrics import mean_absolute_error, r2_score, roc_auc_score
    from sklearn.model_selection import GroupKFold, cross_val_predict
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler

    flex = pd.read_csv(DATA / "flex.csv")
    flex = flex[flex["pressure_mmhg"] > 100].copy()
    flex["heptane"] = (flex["fuel"] == "Heptane").astype(int)
    flex["series"] = flex["flex_id"].str[:3]

    ended = flex[flex["test_end"].isin(["Extinction", "Completion"])].dropna(subset=FLEX_FEATURES)
    went_out = (ended["test_end"] == "Extinction").astype(int)
    classifier = make_pipeline(StandardScaler(), LogisticRegression(max_iter=1000))
    held_out = cross_val_predict(classifier, ended[FLEX_FEATURES], went_out, cv=GroupKFold(5),
                                 groups=ended["series"], method="predict_proba")[:, 1]
    classifier.fit(ended[FLEX_FEATURES], went_out)

    rated = flex.dropna(subset=FLEX_FEATURES + ["burning_rate_mm2_s"])
    regressor = RandomForestRegressor(200, min_samples_leaf=2, random_state=0)
    held_out_rate = cross_val_predict(regressor, rated[FLEX_FEATURES], rated["burning_rate_mm2_s"],
                                      cv=GroupKFold(5), groups=rated["series"])
    regressor.fit(rated[FLEX_FEATURES], rated["burning_rate_mm2_s"])

    left = ended[ended["test_end"] == "Extinction"].dropna(subset=["extinction_d_mm"]).copy()
    left["fuel_left"] = ((left["extinction_d_mm"] / left["d0_mm"]) ** 3).clip(0, 1)
    leftover = RandomForestRegressor(200, min_samples_leaf=2, random_state=0)
    held_out_left = cross_val_predict(leftover, left[FLEX_FEATURES], left["fuel_left"], cv=GroupKFold(5), groups=left["series"])
    leftover.fit(left[FLEX_FEATURES], left["fuel_left"])

    return {"classifier": classifier, "regressor": regressor, "leftover": leftover,
            "ranges": {c: [float(rated[c].min()), float(rated[c].max())] for c in FLEX_FEATURES[1:]},
            "metrics": {"extinction_tests": len(ended), "share_that_went_out": float(went_out.mean()),
                        "extinction_auc": float(roc_auc_score(went_out, held_out)),
                        "rate_tests": len(rated), "rate_r2": float(r2_score(rated["burning_rate_mm2_s"], held_out_rate)),
                        "rate_mae_mm2_s": float(mean_absolute_error(rated["burning_rate_mm2_s"], held_out_rate)),
                        "fuel_left_tests": len(left), "fuel_left_r2": float(r2_score(left["fuel_left"], held_out_left)),
                        "fuel_left_mae": float(mean_absolute_error(left["fuel_left"], held_out_left)),
                        "validation": "5-fold, whole test series held out together"}}


FLAMMABILITY = fit_flammability()


def flammability(fuel="Heptane", o2_frac=0.21, co2_frac=0.0, he_frac=0.0, pressure_mmhg=760.0, d0_mm=3.0):
    row = pd.DataFrame([[int(fuel == "Heptane"), o2_frac, co2_frac, he_frac, pressure_mmhg, d0_mm]], columns=FLEX_FEATURES)
    trees = np.array([t.predict(row.values)[0] for t in FLAMMABILITY["regressor"].estimators_])
    left = np.array([t.predict(row.values)[0] for t in FLAMMABILITY["leftover"].estimators_])
    outside = [c for c, (lo, hi) in FLAMMABILITY["ranges"].items() if not lo <= row[c][0] <= hi]
    if o2_frac + co2_frac + he_frac > 1:
        outside.append("gas fractions add up to more than 1")
    return {"label": "Modeled (machine learning)",
            "inputs": {"fuel": fuel, "o2_frac": o2_frac, "co2_frac": co2_frac, "he_frac": he_frac,
                       "pressure_mmhg": pressure_mmhg, "d0_mm": d0_mm},
            "probability_flame_goes_out_early": float(FLAMMABILITY["classifier"].predict_proba(row)[0, 1]),
            "burning_rate_mm2_s": float(trees.mean()),
            "burning_rate_band_10_90": [float(np.percentile(trees, 10)), float(np.percentile(trees, 90))],
            "fuel_left_when_hot_flame_goes_out": float(left.mean()),
            "fuel_left_band_10_90": [float(np.percentile(left, 10)), float(np.percentile(left, 90))],
            "outside_tested_range": outside,
            "metrics": FLAMMABILITY["metrics"], "tested_ranges": FLAMMABILITY["ranges"],
            "source": "PSI-69 (FLEX droplet tests)",
            "limits": "Trained on single fuel droplets only. It interpolates inside the tested conditions and says nothing about solid materials."}


# ==================== 8. SAFETY ADVISOR (what would make this flame safer?) ====================
def verdict(f):
    p_out, left, fuel = f["probability_flame_goes_out_early"], f["fuel_left_when_hot_flame_goes_out"], f["inputs"]["fuel"]
    if p_out < 0.5:
        return {"level": "sustained", "text": "The flame most likely keeps burning until the fuel is gone."}
    if left >= 0.3:
        extra = (" Heptane is a fuel NASA saw burn on as an invisible cool flame after the hot flame went out, so treat this as possibly still burning."
                 if fuel == "Heptane" else " Unburned fuel can re-ignite if oxygen or heat returns.")
        return {"level": "hidden", "text": f"The visible flame likely goes out, but about {left:.0%} of the fuel is still there." + extra}
    return {"level": "out", "text": "The flame likely goes out with little fuel left behind."}


def advise(fuel, o2_frac, co2_frac, he_frac, pressure_mmhg, d0_mm):
    base = flammability(fuel, o2_frac, co2_frac, he_frac, pressure_mmhg, d0_mm)
    room = 1 - o2_frac - co2_frac - he_frac
    changes = {"Lower oxygen by 3 points": (o2_frac - 0.03, co2_frac, he_frac, pressure_mmhg),
               "Replace 10 points of nitrogen with CO2": (o2_frac, co2_frac + 0.10, he_frac, pressure_mmhg) if room >= 0.10 else None,
               "Replace 10 points of nitrogen with helium": (o2_frac, co2_frac, he_frac + 0.10, pressure_mmhg) if room >= 0.10 else None,
               "Lower pressure by 100 mmHg": (o2_frac, co2_frac, he_frac, pressure_mmhg - 100),
               "Raise pressure by 100 mmHg": (o2_frac, co2_frac, he_frac, pressure_mmhg + 100)}
    options = []
    for name, args in changes.items():
        if args is None:
            continue
        f = flammability(fuel, *args, d0_mm)
        if f["outside_tested_range"]:
            continue
        options.append({"change": name,
                        "goes_out_early": f["probability_flame_goes_out_early"],
                        "goes_out_early_change": f["probability_flame_goes_out_early"] - base["probability_flame_goes_out_early"],
                        "burning_rate_change": f["burning_rate_mm2_s"] - base["burning_rate_mm2_s"],
                        "fuel_left_change": f["fuel_left_when_hot_flame_goes_out"] - base["fuel_left_when_hot_flame_goes_out"],
                        "verdict": verdict(f)["level"]})
    options.sort(key=lambda o: -o["goes_out_early_change"])
    best = options[0] if options and options[0]["goes_out_early_change"] > 0.02 else None
    return {"label": "Recommendation built from the Modeled values", "verdict": verdict(base), "options": options,
            "best_single_change": best["change"] if best else None,
            "trade_off": "Putting a flame out early leaves fuel behind. More fuel left means more to feed a cool flame or a re-ignition, so keep monitoring after the visible flame is gone."}


# ==================== 9. FLAME SCIENCE (measured comparisons) ====================
def flame_science():
    flex = pd.read_csv(DATA / "flex.csv")
    flex = flex[flex["pressure_mmhg"] > 100].copy()
    flex["diluent"] = np.where(flex["he_frac"] > 0, "Helium", np.where(flex["co2_frac"] > 0, "CO2", "Nitrogen only"))
    went_out = flex["test_end"] == "Extinction"
    flex["fuel_left"] = ((flex["extinction_d_mm"] / flex["d0_mm"]) ** 3).where(went_out).clip(0, 1)

    groups = []
    for (fuel, diluent), g in flex.groupby(["fuel", "diluent"]):
        groups.append({"fuel": fuel, "diluent": diluent, "tests": len(g), "outcomes": g["test_end"].value_counts().to_dict(),
                       "median_burning_rate_mm2_s": float(g["burning_rate_mm2_s"].median()),
                       "median_fuel_left": float(g["fuel_left"].median())})
    fuels = {fuel: {"tests": len(g), "share_went_out_early": float((g["test_end"] == "Extinction").mean()),
                    "median_burning_rate_mm2_s": float(g["burning_rate_mm2_s"].median()),
                    "median_fuel_left": float(g["fuel_left"].median())} for fuel, g in flex.groupby("fuel")}
    points = flex.dropna(subset=["fuel_left", "d0_mm"])[["fuel", "diluent", "o2_frac", "d0_mm", "fuel_left"]]

    spice = pd.read_csv(DATA / "spice.csv")
    soot = [{"fuel": fuel if frac == 1 else f"{fuel} diluted to {frac:.0%}", "tests": len(g),
             "median_smoke_point_mm": float(g["smoke_point_mm"].median()),
             "range_mm": [float(g["smoke_point_mm"].min()), float(g["smoke_point_mm"].max())]}
            for (fuel, frac), g in spice.groupby(["fuel", "fuel_mole_frac"])]
    return {"label": "Measured", "fuels": fuels, "groups": groups, "extinction_points": points.to_dict("records"),
            "soot": sorted(soot, key=lambda r: r["median_smoke_point_mm"]),
            "notes": {"fuel_left": "Share of the droplet's volume still unburned when the visible flame went out: (extinction diameter / initial diameter) cubed. Derived by us from PSI-69.",
                      "smoke_point": "Flame length at which a gas flame starts to release soot. A shorter smoke point means a sootier fuel. PSI-107 (SPICE), ISS tests only.",
                      "not_in_data": "Xenon diluent, cool-flame temperatures and cool-flame durations are not in these tables."}}


if __name__ == "__main__":
    import json
    print(json.dumps(AGING, indent=1))
    print(json.dumps(flammability(), indent=1))
    print(json.dumps(flammability("Heptane", 0.30, 0, 0, 527, 3), indent=1))
