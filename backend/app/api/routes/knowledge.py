"""Knowledge base: upload help documents (admin), then search them and ask questions (staff)."""

import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.ai.dependencies import get_ai_service
from app.ai.rag import RagResult, answer_question
from app.ai.service import AIService
from app.api.deps import require_roles
from app.core.config import get_settings
from app.core.roles import STAFF, Role
from app.db.session import get_db
from app.models import KnowledgeDocument, User
from app.schemas.knowledge import AnswerOut, DocumentOut, QuestionRequest, SearchOut, SourceOut
from app.services import knowledge_service
from app.services.document_processing import InvalidDocumentError
from app.services.knowledge_service import DocumentNotFoundError, SearchHit
from app.workers.queue import enqueue_document

router = APIRouter(prefix="/knowledge", tags=["knowledge base"])


def source_out(hit: SearchHit) -> SourceOut:
    return SourceOut(
        document_id=hit.document_id,
        title=hit.title,
        chunk_index=hit.chunk_index,
        similarity=hit.similarity,
        excerpt=hit.content,
    )


def answer_out(result: RagResult) -> AnswerOut:
    return AnswerOut(
        answerable=result.answerable,
        answer=result.answer,
        sources=[source_out(hit) for hit in result.sources],
        reason=result.reason,
        latency_ms=result.latency_ms,
    )


def _read_limited(file: UploadFile) -> bytes:
    """Read the upload in 1 MB pieces and stop as soon as it's over the limit, so a huge file
    can't fill the server's memory."""
    max_mb = get_settings().knowledge_max_upload_mb
    data = bytearray()
    while piece := file.file.read(1024 * 1024):
        data += piece
        if len(data) > max_mb * 1024 * 1024:
            raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, f"The file is larger than {max_mb} MB")
    return bytes(data)


@router.post("", response_model=DocumentOut, status_code=status.HTTP_202_ACCEPTED)
def upload_document(
    file: UploadFile = File(...),
    title: str | None = Form(default=None, max_length=200),
    admin: User = Depends(require_roles(Role.ADMIN)),
    db: Session = Depends(get_db),
) -> KnowledgeDocument:
    """Upload a .md, .txt or .pdf file. 202 = accepted; chunks and embeddings are made in the background.

    A plain `def` (not async): FastAPI runs it in a worker thread, so the blocking database calls
    don't stop the server from handling other requests meanwhile.
    """
    data = _read_limited(file)
    try:
        document = knowledge_service.create_document(
            db, filename=file.filename or "document.txt", data=data, title=title, uploaded_by=admin
        )
    except InvalidDocumentError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from None
    enqueue_document(document.id)
    return document


@router.get("", response_model=list[DocumentOut])
def list_documents(_: User = Depends(require_roles(*STAFF)), db: Session = Depends(get_db)) -> list[KnowledgeDocument]:
    return knowledge_service.list_documents(db)


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_document(
    document_id: uuid.UUID, _: User = Depends(require_roles(Role.ADMIN)), db: Session = Depends(get_db)
) -> None:
    try:
        knowledge_service.delete_document(db, document_id)
    except DocumentNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Document not found") from None


@router.post("/search", response_model=SearchOut)
def search(
    body: QuestionRequest,
    _: User = Depends(require_roles(*STAFF)),
    db: Session = Depends(get_db),
    ai: AIService = Depends(get_ai_service),
) -> SearchOut:
    """Just the search step: which chunks match, and how closely. Useful to see WHY an answer was given."""
    hits = knowledge_service.search(db, ai, body.question)
    return SearchOut(results=[source_out(hit) for hit in hits])


@router.post("/ask", response_model=AnswerOut)
def ask(
    body: QuestionRequest,
    _: User = Depends(require_roles(*STAFF)),
    db: Session = Depends(get_db),
    ai: AIService = Depends(get_ai_service),
) -> AnswerOut:
    """Answer a question from the knowledge base, with sources. Takes a few seconds (the LLM runs now)."""
    hits = knowledge_service.search(db, ai, body.question)
    return answer_out(answer_question(ai, body.question, hits))
