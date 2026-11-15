# Demo answers
Model: `nvidia/nemotron-3.5-super-vl:free` (via OpenRouter)

## A Kapton-insulated wire is overheating. How dangerous is the smoke for the crew?
Kapton smoke particles are tiny (median 0.0842 µm) and concentrated: 8.51 mg/m³ mass, 1.83 million particles/cm³, 17 runs [Measured, PSI-101]. Modeled at rest in microgravity: ~20% of particles by count reach the alveoli; ~2.8 billion alveolar particles/min; ~101 µg deposited per 10 min [Modeled, PSI-101, ICRP 66, Darquenne & Prisk 2008]. Kapton ranks highest for alveolar fraction by count but lowest for deposited mass dose among tested materials [Measured, PSI-101]. No microgravity flammability data exist for Kapton [gap]. Limits: deposition is not toxicity; CO/HF gases are not modelled. Recommendation: treat Kapton smoke as a deep-lung irritant hazard—ventilate, mask, and monitor crew; low mass dose does not mean safe.

*Tools called: material_evidence({}), smoke_exposure({"material": "Kapton", "dilution": 1, "minutes": 0, "activity": "rest", "gravity": "microgravity"})*

## Which materials have we tested for both flammability and smoke in microgravity?
Two materials have both flammability and smoke evidence in microgravity datasets:

- **Silicone** — smoke data (PSI-101) [Measured]; flammability data (PSI-98/99/100, SAFFIRE) [Measured].
- **Cotton** — smoke data (PSI-101) [Measured]; flammability data (BASS, PSI-26, PSI-98/99/100, SAFFIRE) [Measured].

Kapton, Teflon, and Pyrell foam have smoke data but no microgravity flammability data here. PMMA, Nomex, Ultem, and Wax have flammability data but no smoke data.

Limits: deposition is not toxicity; toxic gases are not modelled.

*Tools called: material_evidence({})*

## Does smoke get more or less dangerous as it drifts through the cabin for 15 minutes?
Assuming cabin smoke is diluted to 10% of source (dilution 0.1) in microgravity at rest:

- Source number concentration: 1,830,000 particles/cm³ [Measured, PSI-101 SAME smoke].
- After 15 minutes aging: 157,000 particles/cm³ [Modeled].
- Particle size grows slightly: 0.0842 → 0.0885 µm [Modeled].
- Alveolar particle deposition rate drops: 276 million → 227 million particles/min [Modeled].
- Mass concentration stays at 0.851 mg/m³; mass deposited per 10 min is about the same (10.1 vs 10.4 µg) [Modeled].

So smoke is somewhat less dangerous by particle count after 15 minutes, but mass-based lung dose is roughly unchanged. Deposition is not toxicity; gases like CO and HF are not modelled [Limits].

*Tools called: material_evidence({}), smoke_exposure({"material": "Kapton", "dilution": 0.1, "minutes": 0, "activity": "rest", "gravity": "microgravity"}), smoke_exposure({"material": "Kapton", "dilution": 0.1, "minutes": 15, "activity": "rest", "gravity": "microgravity"})*

## How does lunar gravity change where smoke deposits in the lungs?
Lunar gravity shifts smoke deposition only slightly versus Earth gravity. Modeled Kapton smoke at rest: alveolar mass fraction falls from 0.0835 at 1g to 0.0708 at lunar gravity; total mass deposited drops from 112 to 103 µg per 10 min. Tracheobronchial mass fraction is 0.01 vs 0.0118 at 1g; head-airway fraction stays 0.08. Particle-count fractions are essentially unchanged. Lunar gravity lies closer to microgravity (alveolar 0.0683, 101 µg/10 min) than to 1g. [Modeled — physics engine; sources PSI-101 SAME smoke, ICRP 66/Hinds 1999, Darquenne & Prisk 2008 gravity calibration.] Limits: deposition is not toxicity; gases (CO, HF) not modeled; average adult, unit-density spheres. [Recommendation: treat lunar and microgravity lung deposition as similar for fire-safety planning.]

*Tools called: smoke_exposure({"material": "Kapton", "dilution": 1, "minutes": 0, "activity": "rest", "gravity": "lunar"}), smoke_exposure({"material": "Kapton", "dilution": 1, "minutes": 0, "activity": "rest", "gravity": "1g"}), smoke_exposure({"material": "Kapton", "dilution": 1, "minutes": 0, "activity": "rest", "gravity": "microgravity"})*

## What did FLEX teach us about fires that seem to be out?
FLEX showed that a fire that looks out can still be burning. In ISS droplet tests, some heptane droplets kept shrinking after the visible flame disappeared — an invisible low-temperature "cool flame" continued reacting, and fuel remained at visible extinction [Measured, NASA PSI-69; Nayagam et al., Combustion and Flame 159 (2012) 3583].

Recommendation: treat "no visible flame" as not proof the fire is out. Keep monitoring for heat and combustion products after a fire appears extinguished [Recommendation].

Limits: deposition is not toxicity; toxic gases are not modelled.

*Tools called: search_investigations({"query": "FLEX Flame Extinguishment Experiment fires that appear extinguished microgravity"})*
