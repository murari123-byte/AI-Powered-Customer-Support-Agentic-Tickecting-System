"""The evaluation maths. If these numbers go on a resume, the code that computes them is tested."""

from evals.run_classification import load_dataset, p95, percent, summarise


def outcome(expected: str, got: str | None, confidence: float | None = 0.9, priority=("HIGH", "HIGH"), seconds=1.0):
    return {
        "id": "x",
        "expected_category": expected,
        "predicted_category": got,
        "expected_priority": priority[0],
        "predicted_priority": priority[1] if got else None,
        "confidence": confidence if got else None,
        "error": None if got else "AIUnavailableError: down",
        "seconds": seconds,
    }


def test_accuracy_and_the_confidence_split() -> None:
    outcomes = [
        outcome("BILLING", "BILLING", 0.9),  # confident, right
        outcome("BILLING", "PAYMENT", 0.9),  # confident, wrong
        outcome("LOGIN", "LOGIN", 0.5),  # unsure, right
        outcome("OTHER", "SECURITY", 0.4),  # unsure, wrong
    ]

    s = summarise(outcomes, threshold=0.7)

    assert s["category_accuracy"] == 50.0
    assert s["auto_applied_share"] == 50.0
    assert s["accuracy_when_auto_applied"] == 50.0
    assert s["accuracy_when_unsure"] == 50.0
    assert s["most_common_mistakes"] == {"BILLING -> PAYMENT": 1, "OTHER -> SECURITY": 1}


def test_failed_calls_are_counted_but_not_scored() -> None:
    s = summarise([outcome("BILLING", "BILLING"), outcome("LOGIN", None)], threshold=0.7)

    assert s["failed_calls"] == 1
    assert s["category_accuracy"] == 100.0


def test_priority_within_one_level() -> None:
    s = summarise(
        [
            outcome("BILLING", "BILLING", priority=("HIGH", "HIGH")),
            outcome("BILLING", "BILLING", priority=("HIGH", "MEDIUM")),  # one level off
            outcome("BILLING", "BILLING", priority=("CRITICAL", "LOW")),  # three levels off
        ],
        threshold=0.7,
    )

    assert s["priority_accuracy"] == 33.3
    assert s["priority_within_one_level"] == 66.7


def test_empty_groups_are_none_not_zero() -> None:
    s = summarise([outcome("BILLING", "BILLING", 0.9)], threshold=0.7)

    assert s["accuracy_when_unsure"] is None
    assert percent(0, 0) is None


def test_p95() -> None:
    assert p95(list(range(1, 101))) == 95
    assert p95([6.2, 6.5, 6.7, 17.5]) == 17.5  # a slow outlier must not hide below the average


def test_dataset_is_balanced_and_valid() -> None:
    from app.models import TicketCategory, TicketPriority

    rows = load_dataset(None)
    categories = [row["category"] for row in rows]

    assert len(rows) == 64
    assert {c: categories.count(c) for c in set(categories)} == {c.value: 8 for c in TicketCategory}
    assert all(row["priority"] in {p.value for p in TicketPriority} for row in rows)
    assert len({row["id"] for row in rows}) == 64


def test_holdout_set_is_separate_and_valid() -> None:
    from app.models import TicketCategory

    main_ids = {row["id"] for row in load_dataset(None, "main")}
    holdout = load_dataset(None, "holdout")

    assert len(holdout) == 16
    assert not main_ids & {row["id"] for row in holdout}
    assert sorted({row["category"] for row in holdout}) == sorted(c.value for c in TicketCategory)


# ---------- RAG evaluation ----------


def test_rag_fact_check_supports_alternatives() -> None:
    from evals.run_rag import contains_facts

    assert contains_facts("The link is valid for one hour.", [["1 hour", "one hour"]])
    assert contains_facts("Refunds within 14 days, minus 10%.", ["14", "10%"])
    assert not contains_facts("Refunds within 14 days.", ["14", "10%"])  # every item is required


def test_rag_summary_counts_hallucinations() -> None:
    from evals.run_rag import summarise

    def row(should_answer, answered, correct, hit=True, sim=0.8, used_llm=True):
        return {
            "should_answer": should_answer,
            "answered": answered,
            "correct": correct,
            "retrieval_hit": hit,
            "best_similarity": sim,
            "used_llm": used_llm,
            "seconds": 1.0,
            "error": None,
        }

    s = summarise(
        [
            row(True, True, True),
            row(True, False, False, hit=False),
            row(False, False, True, sim=0.4, used_llm=False),  # refused before the LLM: good
            row(False, True, False, sim=0.6),  # answered something not in the docs: hallucination
        ]
    )

    assert s["correct_answers"] == 50.0 and s["retrieval_hit_rate"] == 50.0
    assert s["correct_refusals"] == 50.0 and s["hallucination_rate"] == 50.0
    assert s["refused_before_llm"] == 1
    assert s["best_similarity_unanswerable"] == {"max": 0.6, "avg": 0.5}


def test_rag_dataset_is_valid() -> None:
    import json
    from pathlib import Path

    rows = [json.loads(line) for line in (Path("evals") / "rag_dataset.jsonl").read_text().splitlines() if line.strip()]
    titles = {
        "Refund policy",
        "Billing and invoices",
        "Payment methods",
        "Managing your account and workspace",
        "Signing in, passwords and two-factor authentication",
        "Security and suspicious activity",
        "Features: frequently asked questions",
        "Contacting support and response times",
    }

    assert len(rows) == 28 and sum(not r["answerable"] for r in rows) == 6
    assert all(r["expected_doc"] in titles and r["must_include"] for r in rows if r["answerable"])
