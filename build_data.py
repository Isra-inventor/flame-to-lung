import hashlib, sys, time, urllib.parse
from pathlib import Path
import pandas as pd
import requests

RAW = Path(__file__).parent / "data" / "raw"
OUT = Path(__file__).parent / "data" / "processed"

FILES = [
    ("PSI-101", "PSI-101_Analyzed Data_SAME, SAME-R_Results.xlsx"),
    ("PSI-69", "PSI-69_Experimental table_FLEX.csv"),
    ("PSI-25", "PSI-25_Experimental table_BASS-II.csv"),
    ("PSI-26", "PSI-26_Science Documents_As Run_Test Matrix.xlsx"),
    ("PSI-98", "PSI-98_Experimental table_SAFFIRE-1.csv"),
    ("PSI-99", "PSI-99_Experimental table_SAFFIRE-2.csv"),
    ("PSI-100", "PSI-100_Experimental table_SAFFIRE-3.csv"),
    ("PSI-107", "PSI-107_Raw Data_SmokePointReview-0g-3.xlsx"),
]


# ==================== DOWNLOAD ====================
def download():
    RAW.mkdir(parents=True, exist_ok=True)
    rows = []
    for psi_id, name in FILES:
        path = RAW / name
        if not path.exists():
            url = f"https://psi.nasa.gov/geode-py/ws/studies/{psi_id}/download?file={urllib.parse.quote(name)}"
            path.write_bytes(requests.get(url, timeout=120).content)
        sha = hashlib.sha256(path.read_bytes()).hexdigest()
        rows.append({"psi_id": psi_id, "source_file": name, "sha256": sha,
                     "checked_utc": time.strftime("%Y-%m-%d %H:%M")})
    pd.DataFrame(rows).to_csv(OUT / "sources.csv", index=False)


# ==================== HELPERS ====================
def to_number(df, cols, flags):
    for c in cols:
        clean = pd.to_numeric(df[c], errors="coerce")
        bad = clean.isna() & df[c].notna()
        flags[bad] += f"{c}_not_numeric;"
        df[c] = clean


def finish(df, flags, psi_id, source_file, name):
    df["quality_flags"] = flags.str.rstrip(";")
    df["psi_id"] = psi_id
    df["source_file"] = source_file
    df.to_csv(OUT / f"{name}.csv", index=False)
    return df


# ==================== SAME (smoke particles) ====================
def build_same():
    src = FILES[0][1]
    raw = pd.read_excel(RAW / src, sheet_name="Reduced data sheet", header=None).iloc[2:]
    df = raw[[0, 1, 2, 3, 4, 5, 6, 7, 8, 11, 12, 13, 15, 16, 18, 19]].copy()
    df.columns = ["flight", "material", "same_run", "description", "inlet_velocity_cm_s", "rt_r0",
                  "net_aging_s", "number_conc_per_cm3", "m1_mm_per_cm3", "dusttrak_mass_mg_m3",
                  "count_mean_diameter_um", "diam_avg_mass_um", "gsd", "gmd_um",
                  "sample_temp_c", "mass_loss_mg"]
    df = df.reset_index(drop=True)
    flags = pd.Series("", index=df.index)
    to_number(df, df.columns[4:], flags)

    df["flight"] = df["flight"].map({1: "SAME", 2: "SAME-R"})
    df["same_run"] = df["same_run"].astype(str)
    df["is_aged"] = df["same_run"].str.endswith("a")

    liquid = df["material"] == "DBP"
    flags[liquid] += "liquid_aerosol_moments_not_reduced;"
    cold = df["sample_temp_c"] == 0
    df.loc[cold, "sample_temp_c"] = None
    flags[cold] += "sample_temp_zero_set_nan;"

    size_cols = ["number_conc_per_cm3", "gmd_um", "gsd"]
    df["usable_for_size"] = (df[size_cols] > 0).all(axis=1)
    flags[~df["usable_for_size"] & ~liquid] += "size_fit_missing;"
    df[size_cols] = df[size_cols].where(df[size_cols] > 0)

    df["value_type"] = "derived-by-NASA"
    return finish(df, flags, "PSI-101", src, "same")


# ==================== FLEX (burning droplets) ====================
def build_flex():
    src = FILES[1][1]
    df = pd.read_csv(RAW / src, encoding="latin-1")
    df.columns = ["flex_test", "flex_id", "test_date", "test_gmt", "fuel", "pressure_mmhg",
                  "o2_frac", "n2_frac", "co2_frac", "he_frac", "d0_mm", "extinction_d_mm",
                  "burning_rate_mm2_s", "burn_time_s", "test_end"]
    flags = pd.Series("", index=df.index)
    approx = df["burn_time_s"].astype(str).str.startswith("~")
    df["burn_time_s"] = df["burn_time_s"].astype(str).str.lstrip("~")
    flags[approx] += "burn_time_approximate;"
    for c in ["d0_mm", "extinction_d_mm", "burn_time_s"]:
        df[c] = df[c].replace(["\x96", "nan"], None)
    to_number(df, ["d0_mm", "extinction_d_mm", "burning_rate_mm2_s", "burn_time_s"], flags)
    df["value_type"] = "observed"
    return finish(df, flags, "PSI-69", src, "flex")


# ==================== BASS-II (flame spread test log) ====================
def build_bass2():
    src = FILES[2][1]
    df = pd.read_csv(RAW / src, encoding="utf-8-sig")
    df = df.iloc[:, [0, 1, 2, 4, 5, 6, 7, 8, 11, 12]].copy()
    df.columns = ["pi", "test", "date", "sample", "material", "flow_restrictor", "fan_display",
                  "air_display", "o2_initial_pct", "o2_final_pct"]
    flags = pd.Series("", index=df.index)
    to_number(df, ["o2_initial_pct", "o2_final_pct"], flags)
    df["value_type"] = "observed"
    return finish(df, flags, "PSI-25", src, "bass2")


# ==================== BASS (did it burn?) ====================
def material_family(text):
    t = str(text).lower()
    for key, family in [("sibal", "Cotton/SIBAL"), ("nomex", "Nomex"), ("ultem", "Ultem"),
                        ("wax", "Wax"), ("candle", "Wax"), ("pmma", "PMMA"), ("sphere", "PMMA")]:
        if key in t:
            return family
    return None


def outcome(text):
    t = str(text).lower()
    if "no ignition" in t or "did not ignite" in t or "not ignite" in t:
        return "no_ignition"
    if "brief" in t:
        return "brief"
    if "burn" in t or "flame" in t or "ignit" in t:
        return "burned"
    return "unknown"


def build_bass():
    src = FILES[3][1]
    df = pd.read_excel(RAW / src, sheet_name="as run matrix", header=2)
    df = df.iloc[:, [0, 2, 4, 5, 9, 10, 26, 27, 29]].copy()
    df.columns = ["date", "as_run_test", "sample", "material", "fan_display", "air_display",
                  "o2_frac", "pressure_atm", "observations"]
    df = df[pd.to_numeric(df["as_run_test"], errors="coerce").notna()].reset_index(drop=True)
    flags = pd.Series("", index=df.index)
    to_number(df, ["o2_frac", "pressure_atm"], flags)

    df["material_family"] = df["material"].map(material_family)
    sphere_only = df["material"].str.lower().str.contains("sphere") & ~df["material"].str.lower().str.contains("pmma")
    flags[sphere_only.fillna(False)] += "pmma_inferred_from_sphere;"
    df["outcome"] = df["observations"].map(outcome)
    flags += "outcome_is_keyword_guess_from_notes;"
    df["value_type"] = "observed (outcome + material_family derived-by-us)"
    return finish(df, flags, "PSI-26", src, "bass")


# ==================== SAFFIRE (large fires) ====================
def build_saffire():
    names = {"sample": "sample", "material": "material", "thickness": "thickness", "length": "length",
             "width": "width", "air flow": "air_flow", "percent o2": "o2_pct", "burn time": "burn_time",
             "direction": "flow_direction", "g burn length": "ug_burn_length",
             "g spread length": "ug_spread_rate", "1-g burn": "g1_burn_length", "1-g spread": "g1_spread_rate"}
    parts = []
    for (psi_id, src), mission in zip(FILES[4:], ["Saffire-I", "Saffire-II", "Saffire-III"]):
        raw = pd.read_csv(RAW / src, encoding="latin-1")
        df = pd.DataFrame()
        for col in raw.columns:
            unit = col[col.find("("):] if "(cm" in col or "(s)" in col else ""
            for key in sorted(names, key=len, reverse=True):
                if key in col.lower() and names[key] not in df:
                    values = raw[col].astype(str).replace("nan", None)
                    is_bare_number = pd.to_numeric(values, errors="coerce").notna()
                    df[names[key]] = values.where(~is_bare_number, values + " " + unit[1:-1]) if unit else values
                    break
        df["mission"], df["psi_id"], df["source_file"] = mission, psi_id, src
        parts.append(df[df["flow_direction"].notna()])
    df = pd.concat(parts, ignore_index=True)
    flags = pd.Series("", index=df.index)
    blank = df["material"].isna()
    df["material"] = df["material"].ffill()
    flags[blank] += "material_filled_from_row_above;"
    df["quality_flags"] = flags.str.rstrip(";")
    df["value_type"] = "observed"
    df.to_csv(OUT / "saffire.csv", index=False)
    return df


# ==================== SPICE (soot: smoke point of gas flames) ====================
def build_spice():
    src = FILES[7][1]
    raw = pd.read_excel(RAW / src, sheet_name="Smoke Point Datasheet", header=None).iloc[4:]
    df = raw[[5, 6, 11, 7, 18, 29, 30]].copy()
    df.columns = ["test", "fuel_as_written", "fuel_mole_frac", "nozzle_mm", "smoke_point_mm", "air_velocity_cm_s", "fuel_velocity_cm_s"]
    df = df[df["fuel_as_written"].astype(str).str.contains("Ethylene|Propane|Propylene") & ~df["fuel_as_written"].astype(str).str.contains("Avg")]
    df = df.reset_index(drop=True)
    flags = pd.Series("", index=df.index)
    to_number(df, df.columns[2:], flags)
    keep = (df["smoke_point_mm"] > 0) & df["test"].notna() & df["fuel_mole_frac"].notna()
    df, flags = df[keep].reset_index(drop=True), flags[keep].reset_index(drop=True)
    df["fuel"] = df["fuel_as_written"].str.extract("(Ethylene|Propane|Propylene)")[0]
    df["value_type"] = "derived-by-NASA"
    return finish(df, flags, "PSI-107", src, "spice")


# ==================== RUN ====================
if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    download()
    same, flex, bass2, bass, saffire, spice = build_same(), build_flex(), build_bass2(), build_bass(), build_saffire(), build_spice()
    print(f"SAME    {len(same)} rows, {same['usable_for_size'].sum()} usable for size")
    print(f"FLEX    {len(flex)} rows  {flex['fuel'].value_counts().to_dict()}  {flex['test_end'].value_counts().to_dict()}")
    print(f"BASS-II {len(bass2)} rows")
    print(f"BASS    {len(bass)} rows  {bass['outcome'].value_counts().to_dict()}")
    print(f"SAFFIRE {len(saffire)} samples")
    print(f"SPICE   {len(spice)} smoke points  {spice['fuel'].value_counts().to_dict()}")
