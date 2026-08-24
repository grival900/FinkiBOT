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


class McpToolParam(BaseModel):
    name: str
    type: str
    required: bool
    default: str | int | None = None


class McpToolOut(BaseModel):
    server: str
    name: str
    description: str
    params: list[McpToolParam]


class McpCallRequest(BaseModel):
    server: str
    tool: str
    query: str
    limit: int = 5


class DocumentOut(BaseModel):
    id: str
    source: str
    type: str
    title: str
    url: str
    published_at: datetime | None
    content: str
    doc_metadata: dict


class DocTypeCount(BaseModel):
    source: str
    type: str
    count: int


class MonthCount(BaseModel):
    month: str
    count: int


class TagCount(BaseModel):
    tag: str
    count: int


class SemesterCount(BaseModel):
    semester: str
    count: int


class InsightsOut(BaseModel):
    documents_by_type: list[DocTypeCount]
    announcements_by_month: list[MonthCount]
    course_tags: list[TagCount]
    course_semester_distribution: list[SemesterCount]


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


class QuizResponse(BaseModel):
    questions: list[QuizQuestion]
    source_titles: list[str]
