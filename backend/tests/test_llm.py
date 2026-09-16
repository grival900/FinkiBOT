from backend.core.llm import get_groq_client


def test_groq_client_disables_the_sdks_own_retries():
    """Confirmed live: the SDK's default (2) retries a 429 with its own growing
    backoff - 12s, then 52s, then 3s in one observed case - entirely inside a single
    `stream_groq` tool-calling round, while `/chat` blocks synchronously waiting for
    the first output. `llm_providers.stream_chat_with_failover` already exists to
    fall back to the other provider when one is out of quota; letting Groq's own
    single-provider retry loop run first just delays reaching that failover by up to
    a minute instead of within a couple seconds."""
    assert get_groq_client().max_retries == 0
