"""Measure the RAG pipeline with the REAL embedding model and LLM.

    cd backend
    .venv/bin/python -m evals.run_rag

The knowledge base (../knowledge-base/*.md) is loaded into the TEST database inside a transaction
that is rolled back at the end, so this never touches your real data. Needs Ollama and
`docker compose up -d`. Reports go to evals/results/.

What it measures, and why:
- Retrieval hit rate: did search find the right document? (If not, the LLM can't answer well.)
- Correct answers: answered, contains the key facts, and cites the right document.
- Correct refusals: for questions the documents DON'T cover, did it say "I don't know"?
- Hallucination rate: how often it answered a question it should have refused (the worst failure).
- Similarity of the best match, for answerable vs unanswerable questions: shows whether the
  RAG_MIN_SIMILARITY cut-off is in a sensible place.
"""

import json
import statistics
import time
from datetime import UTC, datetime
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.ai.dependencies import build_provider
from app.ai.errors import AIError
from app.ai.rag import PROMPT_VERSION, answer_question
from app.ai.service import AIService
from app.core.config import get_settings
from app.services import knowledge_service
from evals.run_classification import p95, percent

HERE = Path(__file__).parent
BACKEND = HERE.parent
KNOWLEDGE_BASE = BACKEND.parent / "knowledge-base"
DATASET = HERE / "rag_dataset.jsonl"
RESULTS = HERE / "results"


def contains_facts(answer: str, must_include: list) -> bool:
    """Each item must appear in the answer. An item can be a list of alternatives ("1 hour" or "one hour")."""
    text = answer.lower()
    for item in must_include:
        options = item if isinstance(item, list) else [item]
        if not any(option.lower() in text for option in options):
            return False
    return True


def load_knowledge(db: Session, ai: AIService) -> int:
    count = 0
    for path in sorted(KNOWLEDGE_BASE.glob("*.md")):
        document = knowledge_service.create_document(
            db, filename=path.name, data=path.read_bytes(), title=None, uploaded_by=None
        )
        knowledge_service.process_document(db, ai, document.id)
        count += 1
    return count


def evaluate(db: Session, ai: AIService, rows: list[dict]) -> list[dict]:
    outcomes = []
    for index, row in enumerate(rows, start=1):
        started = time.perf_counter()
        best = knowledge_service.search(db, ai, row["question"], top_k=1, min_similarity=0.0)
        hits = knowledge_service.search(db, ai, row["question"])  # with the real top-k and cut-off
        try:
            result = answer_question(ai, row["question"], hits)
            error = None
        except AIError as exc:
            result, error = None, f"{exc.__class__.__name__}: {exc}"

        answered = bool(result and result.answerable)
        cited = [s.title for s in result.sources] if result else []
        outcome = {
            "id": row["id"],
            "question": row["question"],
            "should_answer": row["answerable"],
            "answered": answered,
            "answer": result.answer if result else None,
            "reason": result.reason if result else error,
            "used_llm": bool(result and result.used_llm),
            "cited": cited,
            "retrieved": [h.title for h in hits],
            "best_similarity": best[0].similarity if best else None,
            "best_document": best[0].title if best else None,
            "error": error,
            "seconds": round(time.perf_counter() - started, 2),
        }
        if row["answerable"]:
            outcome["expected_doc"] = row["expected_doc"]
            outcome["retrieval_hit"] = row["expected_doc"] in outcome["retrieved"]
            outcome["correct"] = (
                answered and row["expected_doc"] in cited and contains_facts(result.answer, row["must_include"])
            )
        else:
            outcome["correct"] = not answered
        mark = "ok " if outcome["correct"] else "BAD"
        print(
            f"[{index:2}/{len(rows)}] {mark} {row['id']:11} best sim {outcome['best_similarity']:.3f} "
            f"{'answered' if answered else 'refused '} ({outcome['seconds']}s) {outcome['reason']}"
        )
        outcomes.append(outcome)
    return outcomes


def summarise(outcomes: list[dict]) -> dict:
    answerable = [o for o in outcomes if o["should_answer"]]
    unanswerable = [o for o in outcomes if not o["should_answer"]]
    sims_yes = [o["best_similarity"] for o in answerable if o["best_similarity"] is not None]
    sims_no = [o["best_similarity"] for o in unanswerable if o["best_similarity"] is not None]
    seconds = [o["seconds"] for o in outcomes]
    return {
        "questions": len(outcomes),
        "answerable_questions": len(answerable),
        "unanswerable_questions": len(unanswerable),
        "retrieval_hit_rate": percent(sum(o["retrieval_hit"] for o in answerable), len(answerable)),
        "correct_answers": percent(sum(o["correct"] for o in answerable), len(answerable)),
        "wrongly_refused": percent(sum(not o["answered"] for o in answerable), len(answerable)),
        "correct_refusals": percent(sum(o["correct"] for o in unanswerable), len(unanswerable)),
        "hallucination_rate": percent(sum(o["answered"] for o in unanswerable), len(unanswerable)),
        "refused_before_llm": sum(not o["used_llm"] for o in outcomes),
        "best_similarity_answerable": {"min": min(sims_yes), "avg": round(statistics.mean(sims_yes), 3)}
        if sims_yes
        else None,
        "best_similarity_unanswerable": {"max": max(sims_no), "avg": round(statistics.mean(sims_no), 3)}
        if sims_no
        else None,
        "min_similarity_setting": get_settings().rag_min_similarity,
        "top_k": get_settings().rag_top_k,
        "average_seconds": round(statistics.mean(seconds), 2) if seconds else 0,
        "p95_seconds": round(p95(seconds), 2) if seconds else 0,
        "failed_calls": sum(o["error"] is not None for o in outcomes),
    }


def write_reports(summary: dict, outcomes: list[dict], model: str) -> Path:
    RESULTS.mkdir(exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M")
    base = RESULTS / f"rag_{PROMPT_VERSION}_{stamp}"
    meta = {"model": model, "prompt_version": PROMPT_VERSION, "run_at": stamp}
    base.with_suffix(".json").write_text(json.dumps(meta | {"summary": summary, "outcomes": outcomes}, indent=2))

    s = summary
    lines = [
        f"# RAG eval: {PROMPT_VERSION} on {model}",
        "",
        f"Run {stamp} UTC: {s['answerable_questions']} answerable + {s['unanswerable_questions']} unanswerable questions, "
        f"top_k={s['top_k']}, min similarity {s['min_similarity_setting']}.",
        "",
        "| Metric | Result |",
        "|---|---|",
        f"| Retrieval hit rate (right document found) | {s['retrieval_hit_rate']}% |",
        f"| **Correct answers** (facts right + right source cited) | **{s['correct_answers']}%** |",
        f"| Answerable but refused | {s['wrongly_refused']}% |",
        f'| **Correct refusals** ("I don\'t know" when not in the docs) | **{s["correct_refusals"]}%** |',
        f"| **Hallucination rate** (answered when it shouldn't) | **{s['hallucination_rate']}%** |",
        f"| Refused before calling the LLM (no close match) | {s['refused_before_llm']} questions |",
        f"| Best similarity, answerable questions | min {s['best_similarity_answerable']['min']}, avg {s['best_similarity_answerable']['avg']} |",
        f"| Best similarity, unanswerable questions | max {s['best_similarity_unanswerable']['max']}, avg {s['best_similarity_unanswerable']['avg']} |",
        f"| Average / p95 time | {s['average_seconds']} s / {s['p95_seconds']} s |",
        "",
        "## Every question",
        "",
        "| Question | Should answer | Result | Best similarity | Cited | Answer |",
        "|---|---|---|---|---|---|",
        *[
            f"| {o['id']} | {'yes' if o['should_answer'] else 'no'} | {'✅' if o['correct'] else '❌'} "
            f"{'answered' if o['answered'] else 'refused'} | {o['best_similarity']} | {', '.join(o['cited']) or '-'} | "
            f"{(o['answer'] or o['reason'] or '').replace('|', '/').replace(chr(10), ' ')[:160]} |"
            for o in outcomes
        ],
    ]
    base.with_suffix(".md").write_text("\n".join(lines) + "\n")
    return base


def main() -> None:
    settings = get_settings()
    ai = AIService(build_provider(settings), max_output_retries=settings.ai_max_output_retries)
    rows = [json.loads(line) for line in DATASET.read_text().splitlines() if line.strip()]

    engine = create_engine(settings.database_url(test=True))
    config = Config(str(BACKEND / "alembic.ini"))
    config.attributes["url"] = engine.url
    config.attributes["configure_logger"] = False
    command.upgrade(config, "head")

    # Everything happens in one transaction that is rolled back: the test database is left as it was.
    with engine.connect() as connection:
        outer = connection.begin()
        db = Session(bind=connection, join_transaction_mode="create_savepoint")
        try:
            print(f"Loaded {load_knowledge(db, ai)} documents into the test database (will be rolled back).\n")
            outcomes = evaluate(db, ai, rows)
        finally:
            db.close()
            outer.rollback()
    engine.dispose()

    summary = summarise(outcomes)
    base = write_reports(summary, outcomes, ai.chat_model)
    print("\n" + json.dumps(summary, indent=2))
    print(f"\nReports: {base}.md and {base}.json")


if __name__ == "__main__":
    main()
