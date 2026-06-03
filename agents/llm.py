"""
Provider-agnostic LLM wrapper.
Swap LLM_PROVIDER in .env to switch between Groq, Anthropic, OpenAI, or Gemini.
Default: Groq (free tier).
"""
import json
from typing import Optional
import config


def call_llm(system: str, user: str, temperature: float = 0.3) -> str:
    provider = config.LLM_PROVIDER.lower()

    if provider == "groq":
        return _call_groq(system, user, temperature)
    elif provider == "anthropic":
        return _call_anthropic(system, user, temperature)
    elif provider == "openai":
        return _call_openai(system, user, temperature)
    elif provider == "gemini":
        return _call_gemini(system, user, temperature)
    else:
        raise ValueError(f"Unknown LLM_PROVIDER: {provider}. Use 'groq', 'anthropic', 'openai', or 'gemini'.")


def _call_groq(system: str, user: str, temperature: float) -> str:
    from groq import Groq
    client = Groq(api_key=config.GROQ_API_KEY)
    response = client.chat.completions.create(
        model=config.GROQ_MODEL,
        temperature=temperature,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    )
    return response.choices[0].message.content.strip()


def _call_anthropic(system: str, user: str, temperature: float) -> str:
    import anthropic
    client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
    message = client.messages.create(
        model=config.ANTHROPIC_MODEL,
        max_tokens=1024,
        temperature=temperature,
        system=system,
        messages=[{"role": "user", "content": user}],
    )
    return message.content[0].text.strip()


def _call_openai(system: str, user: str, temperature: float) -> str:
    from openai import OpenAI
    client = OpenAI(api_key=config.OPENAI_API_KEY)
    response = client.chat.completions.create(
        model=config.OPENAI_MODEL,
        temperature=temperature,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    )
    return response.choices[0].message.content.strip()


def _call_gemini(system: str, user: str, temperature: float) -> str:
    import google.generativeai as genai
    genai.configure(api_key=config.GEMINI_API_KEY)
    model = genai.GenerativeModel("gemini-1.5-flash", system_instruction=system)
    response = model.generate_content(user, generation_config={"temperature": temperature})
    return response.text.strip()


def call_llm_json(system: str, user: str) -> dict:
    """Call LLM and parse JSON response."""
    raw = call_llm(system, user + "\n\nRespond ONLY with valid JSON, no markdown.", temperature=0.1)
    # Strip markdown code fences if present
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    return json.loads(raw.strip())
