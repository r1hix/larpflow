"""Tiny wrapper around an OpenAI-compatible API (OpenAI, Gemini, and so on)."""
import json
import re

from openai import OpenAI

from . import config


def _client():
    if not config.LLM_API_KEY:
        raise RuntimeError("LLM_API_KEY is empty. Put it in .env first.")
    kwargs = {"api_key": config.LLM_API_KEY}
    if config.LLM_BASE_URL:
        kwargs["base_url"] = config.LLM_BASE_URL
    return OpenAI(**kwargs)


import time

FALLBACK_MODELS = ["gemini-3.8-flash", "gemini-2.5-flash", "gemini-2.0-flash", "gemini-1.5-flash"]


def chat(system, user, json_mode=False, temperature=0.7):
    client = _client()
    models_to_try = [config.LLM_MODEL] + [m for m in FALLBACK_MODELS if m != config.LLM_MODEL]
    last_err = None

    for model in models_to_try:
        args = dict(
            model=model,
            temperature=temperature,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        )
        for attempt in range(3):
            try:
                if json_mode:
                    try:
                        resp = client.chat.completions.create(response_format={"type": "json_object"}, **args)
                    except Exception:
                        resp = client.chat.completions.create(**args)
                else:
                    resp = client.chat.completions.create(**args)
                return resp.choices[0].message.content or ""
            except Exception as e:
                last_err = e
                # If 503 (high demand) or 429 (rate limit), pause briefly before retry
                err_str = str(e)
                if "503" in err_str or "429" in err_str:
                    time.sleep(2 * (attempt + 1))
                    continue
                break  # try next model if 404 or other error

    raise last_err



def parse_json(raw):
    """Finds the JSON object in the answer, even if the model wrapped it in ``` fences."""
    raw = re.sub(r"^```(?:json)?|```$", "", raw.strip(), flags=re.MULTILINE).strip()
    start, end = raw.find("{"), raw.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("no JSON object found in the model answer")
    return json.loads(raw[start : end + 1])
