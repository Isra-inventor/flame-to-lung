import server

client = server.app.test_client()


def test_page_and_data_routes():
    assert client.get("/").status_code == 200
    assert len(client.get("/api/cards").json) >= 8
    assert client.get("/api/matrix").json["gaps"]


def test_exposure_route():
    body = {"material": "Kapton", "dilution": 0.01, "minutes": 5, "activity": "rest", "gravity": "lunar"}
    out = client.post("/api/exposure", json=body).json
    assert out["label"] == "Modeled"
    assert len(out["curves"]["dp_um"]) == len(out["curves"]["AL"])


def test_flammability_route():
    body = {"fuel": "Heptane", "o2_pct": 30, "co2_pct": 0, "he_pct": 0, "pressure_mmhg": 527, "d0_mm": 3}
    out = client.post("/api/flammability", json=body).json
    assert 0 <= out["probability_flame_goes_out_early"] <= 1
    assert len(out["oxygen_sweep"]) == 23
    assert out["advice"]["verdict"]["level"] in ("sustained", "hidden", "out")


def test_flame_science_route():
    out = client.get("/api/flame-science").json
    assert set(out["fuels"]) == {"Heptane", "Methanol"}
    assert out["soot"][0]["fuel"].startswith("Propylene")


def test_findings_are_ranked():
    out = client.get("/api/findings").json["findings"]
    assert [f["rank"] for f in out] == list(range(1, len(out) + 1))
    assert all(out[i]["total"] >= out[i + 1]["total"] for i in range(len(out) - 1))
    assert all(f["scores"]["evidence"] == (3 if f["tests"] >= 100 else 2 if f["tests"] >= 30 else 1) for f in out)
