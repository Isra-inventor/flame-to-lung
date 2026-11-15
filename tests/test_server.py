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
