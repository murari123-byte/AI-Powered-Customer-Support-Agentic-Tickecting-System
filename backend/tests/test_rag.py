"""Knowledge base + RAG with a FAKE LLM: upload, process, search, answer, and the API."""

import json
from contextlib import nullcontext

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.ai.errors import AIUnavailableError
from app.ai.rag import NO_ANSWER, answer_question, build_prompt
from app.ai.service import AIService
from app.models import AIInteraction, DocumentStatus, KnowledgeChunk, KnowledgeDocument
from app.services import knowledge_service
from app.services.document_processing import InvalidDocumentError
from app.workers import queue, tasks
from tests.fakes import FakeLLMProvider
from tests.helpers import World, auth

pytestmark = pytest.mark.db

REFUNDS = b"# Refund policy\n\nMonthly plans can be refunded within 14 days of payment. Refunds show up in 5 to 10 business days."
PASSWORDS = b"# Passwords\n\nClick Forgot password on the sign-in page. The reset link is valid for 1 hour."


def fake_ai(*replies) -> tuple[AIService, FakeLLMProvider]:
    provider = FakeLLMProvider(replies)
    return AIService(provider), provider


def rag_reply(answerable=True, answer="Refunds are possible within 14 days [1].", sources=(1,)) -> str:
    return json.dumps({"answerable": answerable, "answer": answer, "sources": list(sources)})


@pytest.fixture
def knowledge(db_session: Session) -> list[KnowledgeDocument]:
    """Two READY documents, embedded with the fake embeddings."""
    ai, _ = fake_ai()
    documents = []
    for name, data in (("refund-policy.md", REFUNDS), ("passwords.md", PASSWORDS)):
        document = knowledge_service.create_document(db_session, filename=name, data=data, title=None, uploaded_by=None)
        documents.append(knowledge_service.process_document(db_session, ai, document.id))
    return documents


@pytest.fixture(autouse=True)
def low_threshold(monkeypatch: pytest.MonkeyPatch) -> None:
    """Fake embeddings give lower similarities than real ones, so tests use a lower cut-off."""
    from app.core.config import get_settings

    monkeypatch.setenv("RAG_MIN_SIMILARITY", "0.1")
    get_settings.cache_clear()


# ---------- Upload and processing ----------


def test_upload_saves_clean_text_as_processing(db_session: Session) -> None:
    document = knowledge_service.create_document(
        db_session, filename="refund-policy.md", data=REFUNDS + b"\r\n\r\n\r\n", title=None, uploaded_by=None
    )

    assert document.status == DocumentStatus.PROCESSING
    assert document.title == "Refund policy"  # taken from the "# Refund policy" heading
    assert not document.content.endswith("\n")


def test_title_falls_back_to_the_file_name(db_session: Session) -> None:
    document = knowledge_service.create_document(
        db_session,
        filename="payment_methods.txt",
        data=b"We accept Visa and PayPal cards.",
        title=None,
        uploaded_by=None,
    )

    assert document.title == "Payment methods"


@pytest.mark.parametrize("data, message", [(b"tiny", "almost no text"), (b"x" * (6 * 1024 * 1024), "larger than")])
def test_upload_rejects_empty_or_huge_files(db_session: Session, data: bytes, message: str) -> None:
    with pytest.raises(InvalidDocumentError, match=message):
        knowledge_service.create_document(db_session, filename="a.txt", data=data, title=None, uploaded_by=None)


def test_processing_makes_embedded_chunks(db_session: Session, knowledge) -> None:
    refunds = knowledge[0]

    assert refunds.status == DocumentStatus.READY and refunds.chunk_count == 1
    chunk = db_session.execute(select(KnowledgeChunk).where(KnowledgeChunk.document_id == refunds.id)).scalar_one()
    assert len(chunk.embedding) == 768
    assert "14 days" in chunk.content


def test_chunks_are_embedded_as_documents_with_their_title(db_session: Session) -> None:
    document = knowledge_service.create_document(
        db_session, filename="refund-policy.md", data=REFUNDS, title=None, uploaded_by=None
    )
    ai, provider = fake_ai()

    knowledge_service.process_document(db_session, ai, document.id)

    assert provider.embed_calls[0][0].startswith("search_document: Refund policy\n")


def test_ai_down_keeps_document_processing_and_raises(db_session: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    document = knowledge_service.create_document(
        db_session, filename="a.md", data=REFUNDS, title=None, uploaded_by=None
    )
    ai, provider = fake_ai()
    monkeypatch.setattr(provider, "embed", lambda texts: (_ for _ in ()).throw(AIUnavailableError("down")))

    with pytest.raises(AIUnavailableError):
        knowledge_service.process_document(db_session, ai, document.id)

    db_session.refresh(document)
    assert document.status == DocumentStatus.PROCESSING  # the job will retry


def test_other_errors_mark_the_document_failed(db_session: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    document = knowledge_service.create_document(
        db_session, filename="a.md", data=REFUNDS, title=None, uploaded_by=None
    )
    ai, provider = fake_ai()
    monkeypatch.setattr(provider, "embed", lambda texts: [[0.1, 0.2]])  # wrong size for vector(768)

    result = knowledge_service.process_document(db_session, ai, document.id)

    assert result.status == DocumentStatus.FAILED and result.error


def test_deleting_a_document_deletes_its_chunks(db_session: Session, knowledge) -> None:
    knowledge_service.delete_document(db_session, knowledge[0].id)

    assert db_session.execute(select(func.count()).select_from(KnowledgeChunk)).scalar_one() == 1


# ---------- Search ----------


def test_search_finds_the_right_document_first(db_session: Session, knowledge) -> None:
    hits = knowledge_service.search(db_session, fake_ai()[0], "How many days to get a refund on monthly plans?")

    assert hits[0].title == "Refund policy"
    assert hits == sorted(hits, key=lambda h: h.similarity, reverse=True)


def test_search_drops_weak_matches(db_session: Session, knowledge) -> None:
    hits = knowledge_service.search(db_session, fake_ai()[0], "zebra giraffe elephant", min_similarity=0.3)

    assert hits == []


def test_search_ignores_documents_that_are_not_ready(db_session: Session, knowledge) -> None:
    knowledge[0].status = DocumentStatus.PROCESSING
    db_session.commit()

    hits = knowledge_service.search(db_session, fake_ai()[0], "refund monthly plans days", min_similarity=0.0)

    assert all(hit.title != "Refund policy" for hit in hits)


# ---------- Answering (the anti-hallucination rules) ----------


def test_no_sources_means_no_llm_call(db_session: Session) -> None:
    ai, provider = fake_ai()

    result = answer_question(ai, "What is the meaning of life?", [])

    assert not result.answerable and result.answer == NO_ANSWER
    assert not result.used_llm and provider.chat_calls == []


def test_answer_with_valid_citation(db_session: Session, knowledge) -> None:
    hits = knowledge_service.search(db_session, fake_ai()[0], "refund monthly plans days")
    ai, provider = fake_ai(rag_reply())

    result = answer_question(ai, "Can I get a refund?", hits)

    assert result.answerable and "14 days" in result.answer
    assert [s.title for s in result.sources] == ["Refund policy"]
    prompt = provider.chat_calls[0]["messages"][1].content
    assert "[1] (from: Refund policy)" in prompt and "QUESTION:" in prompt


@pytest.mark.parametrize(
    "reply, reason",
    [
        (rag_reply(answerable=False, answer="Not in the sources", sources=()), "don't answer"),
        (rag_reply(sources=()), "cited no source"),
        (rag_reply(sources=(1, 7)), "wasn't given"),  # source 7 doesn't exist: made up
    ],
)
def test_untrustworthy_answers_become_i_dont_know(db_session: Session, knowledge, reply: str, reason: str) -> None:
    hits = knowledge_service.search(db_session, fake_ai()[0], "refund monthly plans days")

    result = answer_question(fake_ai(reply)[0], "Can I get a refund?", hits)

    assert not result.answerable and result.answer == NO_ANSWER
    assert reason in result.reason


def test_prompt_numbers_every_source(db_session: Session, knowledge) -> None:
    hits = knowledge_service.search(db_session, fake_ai()[0], "refund password days link", min_similarity=0.0)

    prompt = build_prompt("q", hits)

    assert "[1]" in prompt and "[2]" in prompt


# ---------- API ----------


def test_admin_uploads_and_the_job_is_queued(api: TestClient, world: World, monkeypatch: pytest.MonkeyPatch) -> None:
    queued = []
    monkeypatch.setattr(tasks.process_document, "apply_async", lambda args, retry: queued.append(args[0]))
    files = {"file": ("refund-policy.md", REFUNDS, "text/markdown")}

    response = api.post("/api/v1/knowledge", files=files, headers=auth(world.admin))

    assert response.status_code == 202
    assert response.json()["status"] == "PROCESSING"
    assert queued == [response.json()["id"]]


def test_upload_rules(api: TestClient, world: World, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(queue, "enqueue_document", lambda document_id: True)
    good = {"file": ("a.md", REFUNDS, "text/markdown")}

    assert api.post("/api/v1/knowledge", files=good, headers=auth(world.manager)).status_code == 403
    bad = {"file": ("evil.exe", b"MZ....", "application/octet-stream")}
    response = api.post("/api/v1/knowledge", files=bad, headers=auth(world.admin))
    assert response.status_code == 400 and "Only" in response.json()["detail"]


def test_huge_upload_is_refused_without_reading_it_all(
    api: TestClient, world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("KNOWLEDGE_MAX_UPLOAD_MB", "1")
    from app.core.config import get_settings

    get_settings.cache_clear()
    files = {"file": ("big.txt", b"x" * (3 * 1024 * 1024), "text/plain")}

    response = api.post("/api/v1/knowledge", files=files, headers=auth(world.admin))

    assert response.status_code == 413


def test_ask_endpoint(api: TestClient, world: World, knowledge, monkeypatch: pytest.MonkeyPatch) -> None:
    from app.ai.dependencies import get_ai_service

    api.app.dependency_overrides[get_ai_service] = lambda: fake_ai(rag_reply())[0]

    response = api.post(
        "/api/v1/knowledge/ask", json={"question": "refund monthly plans days?"}, headers=auth(world.billing_agent)
    )

    assert response.status_code == 200
    body = response.json()
    assert body["answerable"] is True
    assert body["sources"][0]["title"] == "Refund policy" and "14 days" in body["sources"][0]["excerpt"]
    assert (
        api.post("/api/v1/knowledge/ask", json={"question": "refund?"}, headers=auth(world.customer)).status_code == 403
    )


def test_ask_when_ai_is_down_is_503_with_a_safe_message(api: TestClient, world: World, knowledge) -> None:
    from app.ai.dependencies import get_ai_service

    api.app.dependency_overrides[get_ai_service] = lambda: fake_ai(
        AIUnavailableError("internal host 10.0.0.5 refused")
    )[0]

    response = api.post(
        "/api/v1/knowledge/ask", json={"question": "refund monthly plans days?"}, headers=auth(world.manager)
    )

    assert response.status_code == 503
    assert "10.0.0.5" not in response.text  # internal details never leak


def test_suggest_reply_for_a_ticket_is_saved_but_not_sent(
    api: TestClient, db_session: Session, world: World, knowledge
) -> None:
    from app.ai.dependencies import get_ai_service

    api.app.dependency_overrides[get_ai_service] = lambda: fake_ai(rag_reply())[0]
    ticket = world.new_ticket(db_session, "Refund for monthly plan within days?")

    response = api.post(f"/api/v1/tickets/{ticket.id}/suggest-reply", headers=auth(world.manager))

    assert response.status_code == 200 and response.json()["answerable"] is True
    record = db_session.execute(select(AIInteraction).where(AIInteraction.kind == "reply_suggestion")).scalar_one()
    assert "not sent to the customer" in record.decision
    messages = api.get(f"/api/v1/tickets/{ticket.id}/messages", headers=auth(world.customer)).json()
    assert len(messages) == 1  # only the customer's own first message: nothing was sent


def test_process_task_runs_the_service(db_session: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    document = knowledge_service.create_document(
        db_session, filename="a.md", data=REFUNDS, title=None, uploaded_by=None
    )
    monkeypatch.setattr(tasks, "session_factory", lambda: lambda: nullcontext(db_session))
    monkeypatch.setattr(tasks, "get_ai_service", lambda: fake_ai()[0])

    assert tasks.process_document(str(document.id)) == "READY: 1 chunks"
