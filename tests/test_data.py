from pathlib import Path
import pandas as pd

P = Path(__file__).parent.parent / "data" / "processed"


def load(name):
    return pd.read_csv(P / f"{name}.csv")


def test_row_counts():
    assert len(load("same")) == 154
    assert len(load("flex")) == 274
    assert len(load("bass")) == 121
    assert len(load("saffire")) == 13


def test_flex_breakdown():
    flex = load("flex")
    assert flex["fuel"].value_counts().to_dict() == {"Methanol": 157, "Heptane": 117}
    assert flex["test_end"].value_counts().to_dict() == {"Extinction": 186, "Disruption": 61, "Completion": 27}


def test_same_sizes_are_physical():
    same = load("same")
    good = same[same["usable_for_size"]]
    assert len(good) > 100
    assert good["gmd_um"].between(0.01, 2).all()
    assert good["gsd"].between(1, 4).all()
    assert not (same["material"].eq("DBP") & same["usable_for_size"]).any()


def test_every_table_keeps_its_source():
    for name in ["same", "flex", "bass", "bass2", "saffire"]:
        df = load(name)
        for col in ["psi_id", "source_file", "value_type", "quality_flags"]:
            assert col in df.columns
