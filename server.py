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
                           materials=list(engine.SMOKE_NAME), aging=engine.AGING)


# ==================== DATA ====================
@app.get("/api/cards")
def cards():
    return jsonify(assistant.CARDS)


@app.get("/api/matrix")
def matrix():
    return jsonify(clean(engine.hazard_matrix()))


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


@app.post("/api/aging")
def aging():
    a = request.json
    series = []
    for minute in range(0, 31):
        e = engine.exposure(a["material"], float(a["dilution"]), minute, "rest", "1g")
        series.append({"minute": minute, "number_conc_per_cm3": e["aged_smoke"]["number_conc_per_cm3"],
                       "gmd_um": e["aged_smoke"]["gmd_um"], "gmd_um_empirical": e["aged_smoke"]["gmd_um_empirical_exponent"],
                       "alveolar_fraction_by_count": e["fraction_by_count"]["AL"]})
    return jsonify(clean({"series": series, "fit": engine.AGING}))


# ==================== ASSISTANT ====================
@app.post("/api/chat")
def chat():
    try:
        return jsonify(clean(assistant.ask(request.json["question"])))
    except Exception as error:
        return jsonify({"answer": f"The language model could not be reached: {error}", "tool_calls": []}), 502


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
