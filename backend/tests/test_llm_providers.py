from unittest.mock import MagicMock, patch

import pytest
from google.genai import errors as genai_errors
from groq import InternalServerError as GroqInternalServerError
from groq import RateLimitError as GroqRateLimitError

from backend.core import llm_providers
from backend.core.llm_providers import (
    QuotaExceededError,
    _execute_groq_tool_call,
    _fallback_provider,
    _groq_tool_schema,
    stream_chat_with_failover,
)


def _http_error(status_code: int):
    response = MagicMock()
    response.status_code = status_code
    response.headers = {}
    response.json.return_value = {"error": {"message": "boom"}}
    return response


def test_fallback_provider_swaps_gemini_and_groq():
    assert _fallback_provider("gemini") == "groq"
    assert _fallback_provider("groq") == "gemini"


def test_groq_tool_schema_reflects_signature_and_docstring():
    def search_courses(query: str, limit: int = 5) -> list[dict]:
        """Search FINKI courses by name or topic."""
        return []

    schema = _groq_tool_schema(search_courses)

    assert schema["type"] == "function"
    assert schema["function"]["name"] == "search_courses"
    assert schema["function"]["description"] == "Search FINKI courses by name or topic."
    assert schema["function"]["parameters"]["properties"] == {
        "query": {"type": "string"},
        "limit": {"type": "integer"},
    }
    # only `query` has no default, so only it is required
    assert schema["function"]["parameters"]["required"] == ["query"]


def test_execute_groq_tool_call_invokes_the_matching_function():
    def echo(text: str) -> dict:
        return {"echo": text}

    tool_call = MagicMock()
    tool_call.function.name = "echo"
    tool_call.function.arguments = '{"text": "hi"}'

    result = _execute_groq_tool_call({"echo": echo}, tool_call)

    assert result == {"result": {"echo": "hi"}}


def test_execute_groq_tool_call_reports_an_unknown_tool_without_raising():
    tool_call = MagicMock()
    tool_call.function.name = "does_not_exist"

    result = _execute_groq_tool_call({}, tool_call)

    assert result == {"error": "unknown tool 'does_not_exist'"}


def test_execute_groq_tool_call_wraps_a_failing_tool_as_an_error_not_an_exception():
    def boom(**kwargs):
        raise ValueError("bad args")

    tool_call = MagicMock()
    tool_call.function.name = "boom"
    tool_call.function.arguments = "{}"

    result = _execute_groq_tool_call({"boom": boom}, tool_call)

    assert result == {"error": "bad args"}


def test_stream_chat_with_failover_uses_the_preferred_provider_when_it_succeeds():
    with patch.object(llm_providers, "_STREAMERS", {"gemini": lambda *a: iter(["hi"]), "groq": lambda *a: iter(["nope"])}):
        provider, chunks = stream_chat_with_failover("gemini", [], [], "system")

    assert provider == "gemini"
    assert list(chunks) == ["hi"]


def test_stream_chat_with_failover_falls_back_on_quota_exceeded():
    def failing(*_a):
        raise QuotaExceededError("rate limited")
        yield  # pragma: no cover - makes this a generator function

    with patch.object(llm_providers, "_STREAMERS", {"gemini": failing, "groq": lambda *a: iter(["from groq"])}):
        provider, chunks = stream_chat_with_failover("gemini", [], [], "system")

    assert provider == "groq"
    assert list(chunks) == ["from groq"]


def test_stream_chat_with_failover_returns_an_apology_when_both_providers_fail():
    def failing(*_a):
        raise QuotaExceededError("down")
        yield  # pragma: no cover - makes this a generator function

    with patch.object(llm_providers, "_STREAMERS", {"gemini": failing, "groq": failing}):
        provider, chunks = stream_chat_with_failover("gemini", [], [], "system")

    assert provider == "gemini"
    assert list(chunks) == [llm_providers._BOTH_PROVIDERS_UNAVAILABLE_MESSAGE]


def test_stream_chat_with_failover_unknown_provider_defaults_to_gemini():
    with patch.object(llm_providers, "_STREAMERS", {"gemini": lambda *a: iter(["hi"]), "groq": lambda *a: iter(["nope"])}):
        provider, chunks = stream_chat_with_failover("not-a-real-provider", [], [], "system")

    assert provider == "gemini"
    assert list(chunks) == ["hi"]


def test_stream_gemini_raises_quota_exceeded_on_429():
    client = MagicMock()
    client.models.generate_content_stream.side_effect = genai_errors.ClientError(429, {"error": {"message": "quota"}})

    with patch.object(llm_providers, "get_client", return_value=client):
        stream = llm_providers.stream_gemini([{"role": "user", "content": "hi"}], [], "system")
        with pytest.raises(QuotaExceededError):
            next(stream)


def test_stream_gemini_reraises_a_non_retryable_error():
    client = MagicMock()
    client.models.generate_content_stream.side_effect = genai_errors.ClientError(400, {"error": {"message": "bad"}})

    with patch.object(llm_providers, "get_client", return_value=client):
        stream = llm_providers.stream_gemini([{"role": "user", "content": "hi"}], [], "system")
        with pytest.raises(genai_errors.ClientError):
            next(stream)


def test_stream_gemini_raises_quota_exceeded_on_a_network_failure():
    """A DNS/connection failure never gets far enough to have an HTTP status at all -
    still means "this provider isn't reachable right now", same as a 429/503."""
    import httpx

    client = MagicMock()
    client.models.generate_content_stream.side_effect = httpx.ConnectError("connection refused")

    with patch.object(llm_providers, "get_client", return_value=client):
        stream = llm_providers.stream_gemini([{"role": "user", "content": "hi"}], [], "system")
        with pytest.raises(QuotaExceededError):
            next(stream)


def test_stream_groq_raises_quota_exceeded_on_missing_or_invalid_api_key():
    from groq import AuthenticationError as GroqAuthenticationError

    client = MagicMock()
    client.chat.completions.create.side_effect = GroqAuthenticationError(
        message="invalid api key", response=_http_error(401), body=None
    )

    with patch.object(llm_providers, "get_groq_client", return_value=client):
        stream = llm_providers.stream_groq([{"role": "user", "content": "hi"}], [], "system")
        with pytest.raises(QuotaExceededError):
            next(stream)


def test_stream_groq_raises_quota_exceeded_on_rate_limit():
    client = MagicMock()
    client.chat.completions.create.side_effect = GroqRateLimitError(
        message="rate limited", response=_http_error(429), body=None
    )

    with patch.object(llm_providers, "get_groq_client", return_value=client):
        stream = llm_providers.stream_groq([{"role": "user", "content": "hi"}], [], "system")
        with pytest.raises(QuotaExceededError):
            next(stream)


def test_stream_groq_raises_quota_exceeded_on_internal_server_error():
    client = MagicMock()
    client.chat.completions.create.side_effect = GroqInternalServerError(
        message="overloaded", response=_http_error(503), body=None
    )

    with patch.object(llm_providers, "get_groq_client", return_value=client):
        stream = llm_providers.stream_groq([{"role": "user", "content": "hi"}], [], "system")
        with pytest.raises(QuotaExceededError):
            next(stream)


def test_stream_groq_raises_quota_exceeded_on_413_token_rate_limit():
    """Confirmed live: Groq reports its free-tier tokens-per-minute limit being
    exceeded as `413 Payload Too Large` (body: {"type": "tokens", "code":
    "rate_limit_exceeded"}), not 429 - a rate-limit condition wearing an unusual
    status code. Without this, a large-context request (long system prompt + tool
    schemas + conversation history - easy to hit on an ordinary multi-turn chat)
    crashed instead of falling back to the other provider."""
    from groq import APIStatusError as GroqAPIStatusError

    client = MagicMock()
    client.chat.completions.create.side_effect = GroqAPIStatusError(
        message="Request too large", response=_http_error(413), body=None
    )

    with patch.object(llm_providers, "get_groq_client", return_value=client):
        stream = llm_providers.stream_groq([{"role": "user", "content": "hi"}], [], "system")
        with pytest.raises(QuotaExceededError):
            next(stream)


def test_stream_groq_reraises_a_non_retryable_status_error():
    from groq import APIStatusError as GroqAPIStatusError

    client = MagicMock()
    client.chat.completions.create.side_effect = GroqAPIStatusError(
        message="bad request", response=_http_error(400), body=None
    )

    with patch.object(llm_providers, "get_groq_client", return_value=client):
        stream = llm_providers.stream_groq([{"role": "user", "content": "hi"}], [], "system")
        with pytest.raises(GroqAPIStatusError):
            next(stream)


def test_stream_groq_yields_the_final_answer_once_no_tool_calls_remain():
    client = MagicMock()
    final_response = MagicMock()
    final_response.choices[0].message.tool_calls = None
    final_response.choices[0].message.content = "the answer"
    client.chat.completions.create.return_value = final_response

    with patch.object(llm_providers, "get_groq_client", return_value=client):
        chunks = list(llm_providers.stream_groq([{"role": "user", "content": "hi"}], [], "system"))

    assert chunks == ["the answer"]


def test_stream_groq_executes_a_tool_call_then_answers():
    def get_thing(name: str) -> dict:
        return {"name": name}

    client = MagicMock()

    tool_call = MagicMock()
    tool_call.id = "call_1"
    tool_call.function.name = "get_thing"
    tool_call.function.arguments = '{"name": "x"}'

    round_1 = MagicMock()
    round_1.choices[0].message.tool_calls = [tool_call]
    round_1.choices[0].message.content = None

    round_2 = MagicMock()
    round_2.choices[0].message.tool_calls = None
    round_2.choices[0].message.content = "resolved: x"

    client.chat.completions.create.side_effect = [round_1, round_2]

    with patch.object(llm_providers, "get_groq_client", return_value=client):
        chunks = list(llm_providers.stream_groq([{"role": "user", "content": "hi"}], [get_thing], "system"))

    assert chunks == ["resolved: x"]
    assert client.chat.completions.create.call_count == 2
    # the tool result must have been fed back into the second round's messages
    second_call_messages = client.chat.completions.create.call_args_list[1].kwargs["messages"]
    tool_messages = [m for m in second_call_messages if m["role"] == "tool"]
    assert len(tool_messages) == 1
    assert "x" in tool_messages[0]["content"]
