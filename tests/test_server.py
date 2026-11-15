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


def test_aging_route():
    series = client.post("/api/aging", json={"material": "Silicone", "dilution": 1}).json["series"]
    assert len(series) == 31
    assert series[30]["gmd_um"] > series[0]["gmd_um"]
