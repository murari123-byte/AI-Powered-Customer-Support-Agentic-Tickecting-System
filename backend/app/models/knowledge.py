import uuid
from datetime import datetime
from enum import StrEnum

from pgvector.sqlalchemy import Vector
from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, enum_column, one_of

# nomic-embed-text produces 768 numbers per text. Changing the embedding model to one with a
# different size needs a migration AND re-embedding every document.
EMBEDDING_DIM = 768


class DocumentStatus(StrEnum):
    PROCESSING = "PROCESSING"  # uploaded; chunks and embeddings are being made in the background
    READY = "READY"  # searchable
    FAILED = "FAILED"  # see `error`


class KnowledgeDocument(Base):
    """One uploaded help document (the text is kept, the original file is not)."""

    __tablename__ = "knowledge_documents"
    __table_args__ = (one_of("status", DocumentStatus),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    title: Mapped[str] = mapped_column(String(200))
    filename: Mapped[str] = mapped_column(String(255))
    content: Mapped[str] = mapped_column(Text)  # the cleaned text
    status: Mapped[DocumentStatus] = mapped_column(
        enum_column(DocumentStatus), default=DocumentStatus.PROCESSING, server_default=DocumentStatus.PROCESSING.value
    )
    error: Mapped[str | None] = mapped_column(Text)
    chunk_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    uploaded_by_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    chunks: Mapped[list["KnowledgeChunk"]] = relationship(
        back_populates="document", cascade="all, delete-orphan", order_by="KnowledgeChunk.chunk_index"
    )


class KnowledgeChunk(Base):
    """A small piece of a document, with its embedding (a list of 768 numbers describing its meaning)."""

    __tablename__ = "knowledge_chunks"
    __table_args__ = (
        # HNSW index: finds the nearest vectors fast without comparing against every row.
        # vector_cosine_ops = the index is for cosine distance, the same measure the search uses.
        Index(
            "ix_knowledge_chunks_embedding",
            "embedding",
            postgresql_using="hnsw",
            postgresql_with={"m": 16, "ef_construction": 64},
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("knowledge_documents.id", ondelete="CASCADE"), index=True)
    chunk_index: Mapped[int] = mapped_column(Integer)  # 0, 1, 2 ... position in the document
    content: Mapped[str] = mapped_column(Text)
    embedding: Mapped[list[float]] = mapped_column(Vector(EMBEDDING_DIM))

    document: Mapped[KnowledgeDocument] = relationship(back_populates="chunks")
