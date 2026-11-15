import os
from dotenv import load_dotenv
from openai import OpenAI

# ---------- LOAD SETTINGS FROM .env ----------
load_dotenv()
client = OpenAI(base_url=os.environ["LLM_BASE_URL"], api_key=os.environ["LLM_API_KEY"])

# ---------- ONE TEST CALL ----------
reply = client.chat.completions.create(
    model=os.environ["LLM_MODEL"],
    messages=[{"role": "user", "content": "Say hello in five words."}],
)
print(reply.choices[0].message.content)
