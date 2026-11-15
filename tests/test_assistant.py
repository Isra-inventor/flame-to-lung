import assistant


def test_search_finds_cool_flames():
    assert assistant.search_investigations("fire that seems to be out")[0]["id"] == "flex-cool-flames"


def test_query_table_is_whitelisted():
    assert "error" in assistant.query_table("passwords")
    assert assistant.query_table("same", {"material": "Kapton"})["rows_matched"] == 36


def test_exposure_tool_reports_bad_material():
    assert "error" in assistant.smoke_exposure("PMMA")
    assert assistant.smoke_exposure("Kapton")["label"] == "Modeled"
