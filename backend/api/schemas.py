from datetime import datetime
from typing import Literal

from pydantic import BaseModel, EmailStr


class SearchResultOut(BaseModel):
    document_id: str
    title: str
    url: str
    source: str
    type: str
    published_at: datetime | None
    chunk_text: str
    score: float


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class ChatRequest(BaseModel):
    message: str
    history: list[ChatMessage] = []


class SubscribeRequest(BaseModel):
    email: EmailStr
    keywords: list[str] = []
    course_codes: list[str] = []


class QuizQuestion(BaseModel):
    question: str
    choices: list[str]
    correct_index: int
    explanation: str


class QuizGenerateRequest(BaseModel):
    course_query: str
    num_questions: int = 5


class QuizResponse(BaseModel):
    questions: list[QuizQuestion]
    source_titles: list[str]
