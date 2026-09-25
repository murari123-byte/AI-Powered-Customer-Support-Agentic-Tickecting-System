import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models import DocumentStatus


class DocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    filename: str
    status: DocumentStatus
    chunk_count: int
    error: str | None
    created_at: datetime


class QuestionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    question: str = Field(min_length=3, max_length=1000)


class SourceOut(BaseModel):
    document_id: uuid.UUID
    title: str
    chunk_index: int
    similarity: float
    excerpt: str  # the chunk text, so staff can check the answer themselves


class AnswerOut(BaseModel):
    answerable: bool
    answer: str
    sources: list[SourceOut]
    reason: str
    latency_ms: int | None


class SearchOut(BaseModel):
    results: list[SourceOut]
