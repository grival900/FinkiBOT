"""Two interchangeable chat-completion backends behind one interface, so `/chat` can
fall back from one to the other on a quota/rate-limit error without knowing which
provider is actually active.

Gemini (`stream_gemini`) uses google-genai's own automatic function calling: pass it
plain Python callables and its SDK derives tool schemas and runs the whole
call-execute-continue loop itself. Groq's SDK has no equivalent — it's the standard
OpenAI-compatible shape (JSON tool schemas you build yourself, a tool_calls list you
execute and feed back by hand) — so `stream_groq` hand-rolls that same loop against
the *same* tool callables (`chat_tools.build_chat_tools` needs no provider-specific
version; both readers only need a function's name/signature/docstring).

Simplification worth knowing: Groq responses stream token-by-token only once the
model stops calling tools — intermediate tool-resolving rounds are fetched whole
(`stream=False`) since a round destined to be entirely tool calls has no user-visible
text to stream anyway, and only the final answer is meaningful to send incrementally.
Given the final round is also fetched as one complete response (accumulating partial
tool-call-argument deltas across a streamed round reliably is real extra complexity
this pragmatic fallback path doesn't need), the practical effect is that a Groq
answer arrives as a single chunk rather than gradually the way Gemini's does — an
accepted UX difference for what is explicitly a testing fallback, not the primary
path.
"""

import inspect
import json
import logging
import typing
from collections.abc import Callable, Iterator
from typing import Any

import httpx
from google.genai import errors as genai_errors
from google.genai import types
from groq import APIConnectionError as GroqAPIConnectionError
from groq import APIStatusError as GroqAPIStatusError
from groq import AuthenticationError as GroqAuthenticationError

from backend.core.config import get_settings
from backend.core.llm import get_client, get_groq_client

logger = logging.getLogger(__name__)

PROVIDERS = ("gemini", "groq")
# Bounds the tool-calling loop for both providers (google-genai's own AFC default is
# also 10) — generous enough for a multi-hop compound question
# (find_courses_taught_by, then one search call per course found) without an
# unbounded worst case on latency/cost if a model gets stuck re-querying.
MAX_TOOL_CALLS = 8
_MAX_TOOL_CALLS_EXCEEDED_MESSAGE = (
    "Извинете, прашањето бараше премногу чекори за да го обработам целосно - "
    "обидете се да го поедноставите или поставете го повторно."
)
_BOTH_PROVIDERS_UNAVAILABLE_MESSAGE = (
    "Извинете, моментално не можам да одговорам - и двата модели (Gemini и Groq) се "
    "недостапни во моментов. Обидете се повторно наскоро."
)

# HTTP status codes that mean "try again / try elsewhere", not "this request is
# broken" — 429 (rate limit/quota exhausted), 503 (model overloaded), and 413.
# 413 is Groq-specific and confirmed live: their free tier's tokens-per-minute cap
# (8000 TPM) is tight enough that this app's system prompt + retrieved context + tool
# schemas + a growing conversation history can exceed it on an ordinary multi-turn
# chat, and Groq reports that as `413 Payload Too Large` with
# `{"type": "tokens", "code": "rate_limit_exceeded"}` in the body - a rate-limit
# error wearing an unusual status code, not a genuinely malformed/oversized request.
# Any other status is a real error (bad request, not-found, etc.) and should surface
# as-is rather than silently triggering a fallback that will just fail the same way.
_RETRYABLE_STATUS_CODES = {429, 503, 413}


class QuotaExceededError(Exception):
    """Raised by a provider adapter when the underlying API signals rate-limit/quota
    exhaustion or that the model is overloaded. The caller (`/chat`) catches this one
    exception type to decide whether to fall back to the other provider, rather than
    needing to know each SDK's own exception hierarchy and status-code conventions."""


def _fallback_provider(preferred: str) -> str:
    return "groq" if preferred == "gemini" else "gemini"


def _to_gemini_contents(messages: list[dict[str, str]]) -> list[types.Content]:
    return [
        types.Content(
            role=("model" if m["role"] == "assistant" else "user"),
            parts=[types.Part.from_text(text=m["content"])],
        )
        for m in messages
    ]


def stream_gemini(messages: list[dict[str, str]], tools: list[Callable], system_prompt: str) -> Iterator[str]:
    settings = get_settings()
    client = get_client()
    try:
        stream = client.models.generate_content_stream(
            model=settings.llm_model,
            contents=_to_gemini_contents(messages),
            config=types.GenerateContentConfig(
                system_instruction=system_prompt,
                max_output_tokens=4096,
                temperature=0.2,
                tools=tools,
                automatic_function_calling=types.AutomaticFunctionCallingConfig(maximum_remote_calls=MAX_TOOL_CALLS),
                # Thinking budget -1 (dynamic): the model has to decide *whether* a
                # question needs a tool call at all and how to chain them, so it
                # should spend thinking budget only when that reasoning is actually
                # needed rather than paying (or not paying) a fixed cost regardless.
                thinking_config=types.ThinkingConfig(thinking_budget=-1),
            ),
        )
        for chunk in stream:
            if chunk.text:
                yield chunk.text
    except genai_errors.APIError as e:
        if e.code in _RETRYABLE_STATUS_CODES:
            raise QuotaExceededError(str(e)) from e
        raise
    except httpx.TransportError as e:
        # Network-level failure (DNS, connection refused, timeout) never reaches the
        # point of getting an HTTP status at all — genuinely "this provider isn't
        # reachable right now", the same "try the other one" situation a 429/503 is.
        raise QuotaExceededError(str(e)) from e


def _python_type_to_json_type(py_type: type) -> str:
    return {str: "string", int: "integer", float: "number", bool: "boolean"}.get(py_type, "string")


def _groq_tool_schema(fn: Callable) -> dict[str, Any]:
    """Builds an OpenAI-style tool schema from a plain Python callable's signature and
    docstring — the hand-rolled equivalent of what google-genai's AFC derives
    automatically for Gemini. Only covers the simple `str`/`int`/`float`/`bool`
    parameter types every tool in `chat_tools.py` actually uses."""
    sig = inspect.signature(fn)
    hints = typing.get_type_hints(fn)
    properties: dict[str, dict[str, str]] = {}
    required: list[str] = []
    for name, param in sig.parameters.items():
        properties[name] = {"type": _python_type_to_json_type(hints.get(name, str))}
        if param.default is inspect.Parameter.empty:
            required.append(name)
    return {
        "type": "function",
        "function": {
            "name": fn.__name__,
            "description": (fn.__doc__ or "").strip(),
            "parameters": {"type": "object", "properties": properties, "required": required},
        },
    }


def _execute_groq_tool_call(function_map: dict[str, Callable], tool_call: Any) -> dict[str, Any]:
    fn = function_map.get(tool_call.function.name)
    if fn is None:
        return {"error": f"unknown tool {tool_call.function.name!r}"}
    try:
        kwargs = json.loads(tool_call.function.arguments or "{}")
        return {"result": fn(**kwargs)}
    except Exception as e:
        logger.warning("Groq tool call %s failed: %s", tool_call.function.name, e)
        return {"error": str(e)}


def stream_groq(messages: list[dict[str, str]], tools: list[Callable], system_prompt: str) -> Iterator[str]:
    settings = get_settings()
    client = get_groq_client()
    function_map = {fn.__name__: fn for fn in tools}
    tool_schemas = [_groq_tool_schema(fn) for fn in tools]
    convo: list[dict[str, Any]] = [{"role": "system", "content": system_prompt}, *messages]

    try:
        for _ in range(MAX_TOOL_CALLS):
            response = client.chat.completions.create(
                model=settings.groq_model, messages=convo, tools=tool_schemas, tool_choice="auto"
            )
            message = response.choices[0].message
            tool_calls = message.tool_calls or []
            if not tool_calls:
                yield message.content or ""
                return

            convo.append(
                {
                    "role": "assistant",
                    "content": message.content,
                    "tool_calls": [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                        }
                        for tc in tool_calls
                    ],
                }
            )
            for tc in tool_calls:
                result = _execute_groq_tool_call(function_map, tc)
                convo.append({"role": "tool", "tool_call_id": tc.id, "content": json.dumps(result, ensure_ascii=False)})
        yield _MAX_TOOL_CALLS_EXCEEDED_MESSAGE
    except (GroqAPIConnectionError, GroqAuthenticationError) as e:
        # APIConnectionError (network-level - never even got an HTTP status) and
        # AuthenticationError (401, e.g. no/invalid GROQ_API_KEY configured yet) both
        # mean "this provider isn't usable right now", not "the request itself is
        # malformed" - same "try elsewhere" bucket as the status-code check below,
        # just not expressible as one since neither carries a status this app should
        # treat as generically retryable (a stray 401 elsewhere likely *is* a bug).
        raise QuotaExceededError(str(e)) from e
    except GroqAPIStatusError as e:
        # Catches RateLimitError(429)/InternalServerError(5xx) and everything else
        # Groq's SDK maps to APIStatusError uniformly by status code - confirmed live
        # this needs to be status-code-driven rather than exception-subclass-driven,
        # since Groq reports a token-rate-limit condition as 413, not 429 (see
        # `_RETRYABLE_STATUS_CODES`). Every other status (400/403/404/409/422) is a
        # real bug and propagates uncaught instead.
        if e.status_code in _RETRYABLE_STATUS_CODES:
            raise QuotaExceededError(str(e)) from e
        raise


_STREAMERS: dict[str, Callable[[list[dict[str, str]], list[Callable], str], Iterator[str]]] = {
    "gemini": stream_gemini,
    "groq": stream_groq,
}


def stream_chat_with_failover(
    preferred: str, messages: list[dict[str, str]], tools: list[Callable], system_prompt: str
) -> tuple[str, Iterator[str]]:
    """Tries `preferred` first; if it raises `QuotaExceededError` before producing any
    output, retries once against the other provider. Returns `(provider_used, chunks)`
    — `provider_used` is known synchronously (the caller needs it to set a response
    header before the streaming body starts), which is why this forces the first
    chunk out of the chosen provider right here rather than leaving that to whoever
    iterates the returned generator.

    A failure *after* output has already started (e.g. quota runs out mid-answer,
    between tool-calling rounds) can't be recovered from here — the client already has
    partial text, so there's nothing to retry cleanly. This only guards the common
    case: a request that never got going at all.

    If the fallback *also* fails before producing anything (both providers down/
    exhausted/unconfigured at once), returns a plain apology instead of propagating —
    an unhandled exception here would otherwise surface as a raw 500 to the client
    mid-request, with no graceful message."""
    provider = preferred if preferred in PROVIDERS else "gemini"
    fallback = _fallback_provider(provider)

    try:
        stream = _STREAMERS[provider](messages, tools, system_prompt)
        first = next(stream, "")
        return provider, _prepend(first, stream)
    except QuotaExceededError:
        logger.warning("%s is unavailable (quota/rate-limit/connection), falling back to %s", provider, fallback)

    try:
        stream = _STREAMERS[fallback](messages, tools, system_prompt)
        first = next(stream, "")
        return fallback, _prepend(first, stream)
    except QuotaExceededError:
        logger.error("%s is also unavailable - no provider could serve this request", fallback)
        return provider, iter([_BOTH_PROVIDERS_UNAVAILABLE_MESSAGE])


def _prepend(first: str, rest: Iterator[str]) -> Iterator[str]:
    if first:
        yield first
    yield from rest
