import json
from pathlib import Path
import numpy as np
import pandas as pd
from flask import Flask, jsonify, render_template, request
import assistant, engine

app = Flask(__name__)
ROOT = Path(__file__).parent
STAGES = ["overheating", "spread", "soot", "extinction", "crew exposure"]


def clean(x):
    return json.loads(json.dumps(x, default=float))


# ==================== PAGE ====================
@app.get("/")
def index():
    counts = {t: len(pd.read_csv(ROOT / "data" / "processed" / f"{t}.csv")) for t in assistant.TABLES}
    return render_template("index.html", counts=counts, stages=STAGES, questions=assistant.DEMO_QUESTIONS,
                           materials=list(engine.SMOKE_NAME), aging=engine.AGING,
                           ml=engine.FLAMMABILITY["metrics"])


# ==================== DATA ====================
@app.get("/api/cards")
def cards():
    return jsonify(assistant.CARDS)


@app.get("/api/matrix")
def matrix():
    return jsonify(clean(engine.hazard_matrix()))


@app.get("/api/flame-science")
def flame_science():
    return jsonify(clean(engine.flame_science()))


# ==================== MODELS ====================
@app.post("/api/exposure")
def exposure():
    a = request.json
    out = engine.exposure(a["material"], float(a["dilution"]), float(a["minutes"]), a["activity"], a["gravity"])
    grid = engine.GRID[(engine.GRID >= 0.005) & (engine.GRID <= 20)][::3]
    curves = engine.deposition_at_gravity(grid, engine.GRAVITY[a["gravity"]])
    smoke = out["aged_smoke"]
    shape = np.exp(-0.5 * (np.log(grid / smoke["gmd_um"]) / np.log(smoke["gsd"])) ** 2)
    curves = {k: v.tolist() for k, v in ({"dp_um": grid, "smoke_by_count": shape} | curves).items()}
    return jsonify(clean(out | {"curves": curves}))


@app.post("/api/flammability")
def flammability():
    a = request.json
    args = [a["fuel"], float(a["o2_pct"]) / 100, float(a["co2_pct"]) / 100, float(a["he_pct"]) / 100, float(a["pressure_mmhg"]), float(a["d0_mm"])]
    out = engine.flammability(*args)
    out["advice"] = engine.advise(*args)
    out["oxygen_sweep"] = []
    for o2 in range(12, 35):
        e = engine.flammability(args[0], o2 / 100, *args[2:])
        out["oxygen_sweep"].append({"o2_pct": o2, "p_out": e["probability_flame_goes_out_early"],
                                    "rate": e["burning_rate_mm2_s"], "band": e["burning_rate_band_10_90"],
                                    "fuel_left": e["fuel_left_when_hot_flame_goes_out"]})
    return jsonify(clean(out))


# ==================== ASSISTANT ====================
@app.post("/api/chat")
def chat():
    try:
        history = [{"role": m["role"], "content": str(m["content"])} for m in request.json.get("history", [])
                   if m.get("role") in ("user", "assistant")][-8:]
        return jsonify(clean(assistant.ask(request.json["question"], history)))
    except Exception as error:
        return jsonify({"answer": f"The language model could not be reached: {error}", "tool_calls": []}), 502


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
