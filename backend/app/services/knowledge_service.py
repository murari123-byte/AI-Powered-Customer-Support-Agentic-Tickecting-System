"""Knowledge base: store documents, embed their chunks, and search them by meaning.

Search by meaning ("semantic search"): the question and every chunk are turned into embeddings
(lists of 768 numbers). Texts with similar meaning get similar numbers, so the chunks whose
embeddings are closest to the question's embedding are the most relevant, even if they use
different words ("refund" vs "money back").
"""

import logging
import uuid
from dataclasses import dataclass
from pathlib import PurePath

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.ai.errors import AIUnavailableError
from app.ai.service import AIService
from app.core.config import get_settings
from app.models import DocumentStatus, KnowledgeChunk, KnowledgeDocument, User
from app.services.document_processing import InvalidDocumentError, clean_text, extract_text, split_into_chunks

logger = logging.getLogger(__name__)

# nomic-embed-text was trained with these task prefixes: documents and questions are embedded
# slightly differently, which makes search noticeably better.
DOCUMENT_PREFIX = "search_document: "
QUERY_PREFIX = "search_query: "
EMBED_BATCH_SIZE = 16


class DocumentNotFoundError(Exception):
    pass


@dataclass(frozen=True)
class SearchHit:
    chunk_id: uuid.UUID
    document_id: uuid.UUID
    title: str
    chunk_index: int
    content: str
    similarity: float  # 1.0 = same meaning, 0 = unrelated


# ---------- Upload and processing ----------


def create_document(
    db: Session, *, filename: str, data: bytes, title: str | None, uploaded_by: User | None
) -> KnowledgeDocument:
    """Check the file, extract and clean its text, and save it as PROCESSING. Fast: no AI here."""
    max_bytes = get_settings().knowledge_max_upload_mb * 1024 * 1024
    if len(data) > max_bytes:
        raise InvalidDocumentError(f"The file is larger than {get_settings().knowledge_max_upload_mb} MB")
    text = clean_text(extract_text(filename, data))
    if len(text) < 20:
        raise InvalidDocumentError("The document has almost no text")

    document = KnowledgeDocument(
        title=(title or _title_from(text, filename))[:200],
        filename=PurePath(filename).name[:255],
        content=text,
        uploaded_by_id=uploaded_by.id if uploaded_by else None,
    )
    db.add(document)
    db.commit()
    db.refresh(document)
    return document


def _title_from(text: str, filename: str) -> str:
    """The first Markdown heading ("# Refund policy"), or else a title made from the file name."""
    first_line = text.split("\n", 1)[0]
    if first_line.startswith("# "):
        return first_line[2:].strip()
    return PurePath(filename).stem.replace("-", " ").replace("_", " ").capitalize()


def process_document(db: Session, ai: AIService, document_id: uuid.UUID) -> KnowledgeDocument | None:
    """Chunk and embed a document, then mark it READY. Slow (AI), so it runs as a background job.

    Raises AIUnavailableError so the job can retry. Any other problem marks the document FAILED.
    """
    document = db.get(KnowledgeDocument, document_id)
    if document is None:
        return None
    settings = get_settings()
    try:
        pieces = split_into_chunks(document.content, settings.rag_chunk_size, settings.rag_chunk_overlap)
        # The title is added to each chunk's embedding text, so a chunk keeps its context
        # (e.g. "Refund policy" + "within 14 days").
        texts = [f"{DOCUMENT_PREFIX}{document.title}\n{piece}" for piece in pieces]
        vectors: list[list[float]] = []
        for start in range(0, len(texts), EMBED_BATCH_SIZE):
            vectors += ai.embed(texts[start : start + EMBED_BATCH_SIZE])

        db.execute(delete(KnowledgeChunk).where(KnowledgeChunk.document_id == document.id))  # re-processing
        db.add_all(
            KnowledgeChunk(document_id=document.id, chunk_index=i, content=piece, embedding=vector)
            for i, (piece, vector) in enumerate(zip(pieces, vectors, strict=True))
        )
        document.status = DocumentStatus.READY
        document.chunk_count = len(pieces)
        document.error = None
        # Write now, inside the try: a bad row (e.g. a wrong-sized vector) must fail HERE and be
        # caught, not later at commit() where it would crash the worker and leave the document stuck.
        db.flush()
    except AIUnavailableError:
        db.rollback()
        raise
    except Exception as exc:  # noqa: BLE001  (a broken document must not crash the worker)
        db.rollback()
        document = db.get(KnowledgeDocument, document_id)
        document.status = DocumentStatus.FAILED
        document.error = f"{exc.__class__.__name__}: {exc}"[:1000]
        logger.exception("Processing document %s failed", document_id)
    db.commit()
    db.refresh(document)
    return document


def list_documents(db: Session) -> list[KnowledgeDocument]:
    return list(db.execute(select(KnowledgeDocument).order_by(KnowledgeDocument.created_at.desc())).scalars())


def delete_document(db: Session, document_id: uuid.UUID) -> None:
    document = db.get(KnowledgeDocument, document_id)
    if document is None:
        raise DocumentNotFoundError()
    db.delete(document)  # its chunks go too (ON DELETE CASCADE)
    db.commit()


# ---------- Search ----------


def search(
    db: Session, ai: AIService, query: str, *, top_k: int | None = None, min_similarity: float | None = None
) -> list[SearchHit]:
    """The chunks closest in meaning to `query`, best first, from READY documents only.

    Chunks below `min_similarity` are dropped: a weak match is worse than no match, because the LLM
    would try to answer from it.
    """
    settings = get_settings()
    top_k = top_k or settings.rag_top_k
    min_similarity = settings.rag_min_similarity if min_similarity is None else min_similarity

    query_vector = ai.embed([f"{QUERY_PREFIX}{query}"])[0]
    distance = KnowledgeChunk.embedding.cosine_distance(query_vector)  # 0 = identical, 2 = opposite
    rows = db.execute(
        select(KnowledgeChunk, KnowledgeDocument.title, distance.label("distance"))
        .join(KnowledgeDocument)
        .where(KnowledgeDocument.status == DocumentStatus.READY)
        .order_by(distance)
        .limit(top_k)
    ).all()

    hits = [
        SearchHit(
            chunk_id=chunk.id,
            document_id=chunk.document_id,
            title=title,
            chunk_index=chunk.chunk_index,
            content=chunk.content,
            similarity=round(1 - distance, 4),
        )
        for chunk, title, distance in rows
    ]
    return [hit for hit in hits if hit.similarity >= min_similarity]
