import json
import os
import time
import requests


def ask_llm(system, user, temperature=0.5, max_tokens=700):
    key = os.getenv("LLM_API_KEY")
    url = os.getenv("LLM_BASE_URL", "https://api.groq.com/openai/v1")
    model = os.getenv("LLM_MODEL", "llama-3.3-70b-versatile")
    if not key:
        raise Exception("Set LLM_API_KEY in the .env file")
    body = {
        "model": model,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    for attempt in range(3):
        r = requests.post(url + "/chat/completions", headers={"Authorization": "Bearer " + key}, json=body, timeout=60)
        if r.status_code == 429:
            time.sleep(4 * (attempt + 1))
            continue
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"].strip()
    raise Exception("LLM rate limit reached, try again in a minute")


def ask_llm_json(system, user):
    text = ask_llm(system + " Reply with JSON only, nothing else.", user, temperature=0)
    start = text.find("{")
    end = text.rfind("}")
    try:
        return json.loads(text[start:end + 1])
    except Exception:
        return {}
