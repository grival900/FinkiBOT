from functools import lru_cache

from google import genai
from groq import Groq

from backend.core.config import get_settings


@lru_cache
def get_client() -> genai.Client:
    return genai.Client(api_key=get_settings().gemini_api_key)


@lru_cache
def get_groq_client() -> Groq:
    # max_retries=0: the SDK's default (2) retries a 429 with its own growing backoff
    # (confirmed live: 12s, then 52s, then 3s - over a minute total) *inside* one
    # `stream_groq` tool-calling round, while our own request blocks waiting for the
    # very first output. Our cross-provider failover in `llm_providers.py` already
    # exists to handle "this provider is out of quota right now" - letting Groq's own
    # single-provider retry loop run first just delays reaching that failover by up to
    # a minute instead of falling back to Gemini within a couple seconds.
    return Groq(api_key=get_settings().groq_api_key, max_retries=0)
