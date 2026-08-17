from collections.abc import Iterator

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from google.genai import types
from sqlalchemy.orm import Session

from backend.api.schemas import ChatRequest
from backend.core.config import get_settings
from backend.core.llm import get_client
from backend.core.retrieval import SearchResult, search
from backend.db import get_db

router = APIRouter(prefix="/chat", tags=["chat"])
settings = get_settings()

SYSTEM_PROMPT = (
    "You are FinkiBOT, an assistant for students at FINKI (Faculty of Computer Science "
    "and Engineering, Skopje). Answer using ONLY the provided context snippets from "
    "finki.ukim.mk and finki-hub.com. If the context doesn't contain the answer, say so "
    "plainly instead of guessing. Always cite sources by including their URLs. Respond "
    "in the same language the student asked in (usually Macedonian).\n\n"
    "Some context entries have type=schedule: these are reference links (e.g. to an exam "
    "session schedule spreadsheet), not documents with the actual dates in their text — "
    "we don't have the file contents, only the link. When a schedule entry's title matches "
    "what the student is asking about (e.g. they ask about the June exam session and a "
    "schedule entry is titled 'јунска испитна сесија'), say you don't have the exact dates "
    "but give them that specific link — don't substitute a less relevant schedule link just "
    "because it's also present in the context."
)


def build_context(results: list[SearchResult]) -> str:
    if not results:
        return "(no matching context found)"
    blocks = []
    for r in results:
        date = r.published_at.date().isoformat() if r.published_at else "n/a"
        blocks.append(f"[{r.title}] (type: {r.type}, url: {r.url}, date: {date})\n{r.chunk_text}")
    return "\n\n---\n\n".join(blocks)


def _gemini_role(role: str) -> str:
    """Gemini uses "model" where Anthropic/OpenAI-style APIs use "assistant"."""
    return "model" if role == "assistant" else "user"


@router.post("")
def chat(payload: ChatRequest, db: Session = Depends(get_db)) -> StreamingResponse:
    results = search(db, payload.message, k=6)
    context = build_context(results)

    contents = [
        types.Content(role=_gemini_role(m.role), parts=[types.Part.from_text(text=m.content)])
        for m in payload.history
    ]
    contents.append(
        types.Content(
            role="user",
            parts=[types.Part.from_text(text=f"Context:\n{context}\n\nQuestion: {payload.message}")],
        )
    )

    client = get_client()

    def event_stream() -> Iterator[str]:
        stream = client.models.generate_content_stream(
            model=settings.llm_model,
            contents=contents,
            config=types.GenerateContentConfig(system_instruction=SYSTEM_PROMPT, max_output_tokens=1024),
        )
        for chunk in stream:
            if chunk.text:
                yield chunk.text

    return StreamingResponse(event_stream(), media_type="text/plain")
