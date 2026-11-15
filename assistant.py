import json, os
from pathlib import Path
import pandas as pd
from dotenv import load_dotenv
from openai import OpenAI
from rank_bm25 import BM25Okapi
import engine

ROOT = Path(__file__).parent
CARDS = json.loads((ROOT / "data" / "cards.json").read_text())
TABLES = ["same", "flex", "bass", "bass2", "saffire"]

SYSTEM_PROMPT = """You are a spacecraft fire-safety briefing assistant built on NASA microgravity combustion data.

Rules:
1. Always call tools first. Never state a number that did not come from a tool result in this conversation.
2. Label every claim [Measured] (NASA data), [Modeled] (our physics engine) or [Recommendation] (your advice).
   Only "measured_source_smoke" and query_table values are [Measured]. Everything else from smoke_exposure,
   including aged smoke, deposition fractions and doses, is [Modeled].
3. State the dilution scenario you assumed. Cite the PSI IDs or papers given in the tool results.
4. If the tools do not have it, say "not in the data". Do not guess.
5. Mention limits when relevant: deposition is not toxicity; toxic gases are not modelled.
6. Answer in at most 150 words, plain crew-briefing style."""


# ==================== TOOL 1: SEARCH THE INVESTIGATION CARDS ====================
def _words(text):
    return "".join(c.lower() if c.isalnum() else " " for c in text).split()


CARD_TEXT = [" ".join([c["title"], c["what"], c["safety_meaning"], c["stage"]] + c["findings"]) for c in CARDS]
INDEX = BM25Okapi([_words(t) for t in CARD_TEXT])


def search_investigations(query):
    scores = INDEX.get_scores(_words(query))
    best = sorted(range(len(CARDS)), key=lambda i: -scores[i])[:3]
    return [CARDS[i] for i in best if scores[i] > 0]


# ==================== TOOL 2: QUERY A NASA TABLE ====================
def query_table(dataset, filters=None, columns=None):
    if dataset not in TABLES:
        return {"error": f"dataset must be one of {TABLES}"}
    df = pd.read_csv(ROOT / "data" / "processed" / f"{dataset}.csv")
    for col, value in (filters or {}).items():
        if col not in df.columns:
            return {"error": f"unknown column {col}", "columns": list(df.columns)}
        df = df[df[col].astype(str).str.lower().str.contains(str(value).lower(), regex=False)]
    numbers = df.select_dtypes("number")
    keep = [c for c in (columns or df.columns) if c in df.columns]
    return {"label": "Measured", "psi_id": sorted(df["psi_id"].unique().tolist()), "rows_matched": len(df),
            "medians": numbers.median().round(4).dropna().to_dict(),
            "first_rows": json.loads(df[keep].head(8).to_json(orient="records", double_precision=4)),
            "all_columns": list(df.columns)}


# ==================== TOOL 3: CREW SMOKE EXPOSURE ====================
def smoke_exposure(material, dilution=0.01, minutes=0, activity="rest", gravity="1g"):
    try:
        return _round(engine.exposure(material, float(dilution), float(minutes), activity, gravity))
    except (ValueError, KeyError) as error:
        return {"error": str(error), "materials": list(engine.SMOKE_NAME),
                "activity": list(engine.BREATHING_L_MIN), "gravity": list(engine.GRAVITY)}


# ==================== TOOL 4: MATERIAL EVIDENCE MATRIX ====================
def material_evidence():
    return _round(engine.hazard_matrix() | {"aging_model": engine.AGING})


def _round(x):
    if isinstance(x, float):
        return float(f"{x:.3g}")
    if isinstance(x, dict):
        return {k: _round(v) for k, v in x.items()}
    if isinstance(x, list):
        return [_round(v) for v in x]
    return x


# ==================== TOOL DESCRIPTIONS FOR THE LLM ====================
def _schema(name, description, properties, required=()):
    return {"type": "function", "function": {"name": name, "description": description,
            "parameters": {"type": "object", "properties": properties, "required": list(required)}}}


TOOLS = {"search_investigations": search_investigations, "query_table": query_table,
         "smoke_exposure": smoke_exposure, "material_evidence": material_evidence}

SCHEMAS = [
    _schema("search_investigations", "Find NASA investigation summaries (SAME, FLEX, cool flames, BASS, BASS-II, Saffire, SPICE, lung model).",
            {"query": {"type": "string"}}, ["query"]),
    _schema("query_table", "Read rows and medians from a cleaned NASA table. Filters match text inside a column.",
            {"dataset": {"type": "string", "enum": TABLES},
             "filters": {"type": "object", "description": "column name -> text to match, e.g. {\"material\": \"Kapton\"}"},
             "columns": {"type": "array", "items": {"type": "string"}}}, ["dataset"]),
    _schema("smoke_exposure", "Model where smoke from an overheated material deposits in a crew member's lungs.",
            {"material": {"type": "string", "enum": list(engine.SMOKE_NAME)},
             "dilution": {"type": "number", "description": "cabin concentration / measured source concentration, e.g. 1, 0.1, 0.01, 0.001"},
             "minutes": {"type": "number", "description": "minutes the smoke has aged in the cabin"},
             "activity": {"type": "string", "enum": list(engine.BREATHING_L_MIN)},
             "gravity": {"type": "string", "enum": list(engine.GRAVITY)}}, ["material"]),
    _schema("material_evidence", "Which materials have flammability evidence, smoke evidence, or gaps; inhalation rankings; smoke aging fit.", {}),
]


# ==================== THE AGENT LOOP ====================
def ask(question, history=None):
    load_dotenv()
    client = OpenAI(base_url=os.environ["LLM_BASE_URL"], api_key=os.environ["LLM_API_KEY"])
    messages = [{"role": "system", "content": SYSTEM_PROMPT}] + (history or []) + [{"role": "user", "content": question}]
    calls = []
    for _ in range(6):
        reply = client.chat.completions.create(model=os.environ["LLM_MODEL"], messages=messages,
                                               tools=SCHEMAS, temperature=0.2).choices[0].message
        if not reply.tool_calls:
            return {"answer": reply.content, "tool_calls": calls}
        messages.append({"role": "assistant", "content": reply.content or "",
                         "tool_calls": [c.model_dump() for c in reply.tool_calls]})
        for call in reply.tool_calls:
            try:
                args = json.loads(call.function.arguments or "{}")
                result = TOOLS[call.function.name](**args)
            except Exception as error:
                args, result = call.function.arguments, {"error": str(error)}
            calls.append({"tool": call.function.name, "args": args, "result": result})
            messages.append({"role": "tool", "tool_call_id": call.id, "content": json.dumps(result, default=str)})
    return {"answer": "I could not finish within the tool-call limit.", "tool_calls": calls}


DEMO_QUESTIONS = [
    "A Kapton-insulated wire is overheating. How dangerous is the smoke for the crew?",
    "Which materials have we tested for both flammability and smoke in microgravity?",
    "Does smoke get more or less dangerous as it drifts through the cabin for 15 minutes?",
    "How does lunar gravity change where smoke deposits in the lungs?",
    "What did FLEX teach us about fires that seem to be out?",
]

if __name__ == "__main__":
    load_dotenv()
    lines = ["# Demo answers", f"Model: `{os.environ['LLM_MODEL']}`", ""]
    for q in DEMO_QUESTIONS:
        out = ask(q)
        used = ", ".join(f"{c['tool']}({json.dumps(c['args'])})" for c in out["tool_calls"])
        lines += [f"## {q}", out["answer"] or "", "", f"*Tools called: {used or 'none'}*", ""]
        print(lines[-5], lines[-4], lines[-2], sep="\n", end="\n\n")
    (ROOT / "docs").mkdir(exist_ok=True)
    (ROOT / "docs" / "demo_answers.md").write_text("\n".join(lines))
