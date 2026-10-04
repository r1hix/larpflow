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

FALLBACK_MODELS = [
    "gemini-3.8-flash",
    "gemini-3.7-flash",
    "gemini-3.6-flash",
    "gemini-3.5-flash",
    "gemini-flash-latest",
]


def chat(system, user, json_mode=False, temperature=0.7):
    client = _client()
    models_to_try = [config.LLM_MODEL] + [m for m in FALLBACK_MODELS if m != config.LLM_MODEL]
    last_err: Exception | None = None

    for model in models_to_try:
        args = dict(
            model=model,
            temperature=temperature,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        )
        for attempt in range(2):
            try:
                if json_mode:
                    try:
                        resp = client.chat.completions.create(response_format={"type": "json_object"}, **args)
                    except Exception as inner_e:
                        err_s = str(inner_e)
                        # Do not burn an attempt with non-json if it is an infrastructure / quota / auth error
                        if any(s in err_s for s in ["503", "429", "401", "403", "RESOURCE_EXHAUSTED", "Quota exceeded"]) or "timeout" in err_s.lower():
                            raise
                        resp = client.chat.completions.create(**args)
                else:
                    resp = client.chat.completions.create(**args)
                return resp.choices[0].message.content or ""
            except Exception as e:
                last_err = e
                err_str = str(e)
                # If model is not found (404) or daily quota is exhausted (RESOURCE_EXHAUSTED), fail over to next model immediately
                if "404" in err_str or "RESOURCE_EXHAUSTED" in err_str or "Quota exceeded" in err_str:
                    break
                # If 503 (high demand) or transient 429, pause briefly and retry once
                if ("503" in err_str or "429" in err_str) and attempt < 1:
                    time.sleep(1.5)
                    continue
                break  # try next model on other errors or after retry

    if last_err is not None:
        raise last_err
    raise RuntimeError("All LLM attempts failed without an exception.")



def parse_json(raw):
    """Finds the JSON object in the answer, even if the model wrapped it in ``` fences."""
    raw = re.sub(r"^```(?:json)?|```$", "", raw.strip(), flags=re.MULTILINE).strip()
    start, end = raw.find("{"), raw.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("no JSON object found in the model answer")
    return json.loads(raw[start : end + 1])
