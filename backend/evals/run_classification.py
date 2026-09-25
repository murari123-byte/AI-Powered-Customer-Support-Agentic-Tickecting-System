"""Measure how well the AI classifies tickets, using the REAL model on a labelled test set.

    cd backend
    .venv/bin/python -m evals.run_classification            # all 64 tickets
    .venv/bin/python -m evals.run_classification --limit 8  # quick try
    .venv/bin/python -m evals.run_classification --dataset holdout  # the 16 unseen tickets

Needs Ollama running with the chat model (see docs/setup.md). Writes a JSON and a Markdown
report to evals/results/.

The most important number is not plain accuracy. It's this: "When the AI was confident
enough for the code to act on its answer, how often was it right?" That's what decides
whether it's safe to let the AI route tickets on its own.
"""

import argparse
import json
import math
import statistics
import time
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

from app.ai.classifier import PROMPT_VERSION, PROMPTS, classify_ticket
from app.ai.dependencies import build_provider
from app.ai.errors import AIError
from app.ai.injection import looks_like_prompt_injection
from app.ai.service import AIService
from app.core.config import get_settings
from app.models import TicketPriority

HERE = Path(__file__).parent
DATASETS = {
    "main": HERE / "classification_dataset.jsonl",  # 64 tickets; used while improving the prompt
    "holdout": HERE / "classification_holdout.jsonl",  # 16 tickets NOT looked at while improving it
}
RESULTS = HERE / "results"
PRIORITY_ORDER = [TicketPriority.LOW, TicketPriority.MEDIUM, TicketPriority.HIGH, TicketPriority.CRITICAL]


def load_dataset(limit: int | None, name: str = "main") -> list[dict]:
    rows = [json.loads(line) for line in DATASETS[name].read_text().splitlines() if line.strip()]
    return rows[:limit] if limit else rows


def run(rows: list[dict], ai: AIService, prompt_version: str = PROMPT_VERSION) -> list[dict]:
    """Classify every row. One failure doesn't stop the run: it's counted as a failure."""
    outcomes = []
    for index, row in enumerate(rows, start=1):
        started = time.perf_counter()
        try:
            result = classify_ticket(
                ai, subject=row["subject"], description=row["description"], prompt_version=prompt_version
            )
            answer = result.classification
            outcome = {
                "predicted_category": answer.category.value,
                "predicted_priority": answer.priority.value,
                "confidence": answer.confidence,
                "reasoning": answer.reasoning,
                "error": None,
            }
        except AIError as exc:
            outcome = {
                "predicted_category": None,
                "predicted_priority": None,
                "confidence": None,
                "reasoning": None,
                "error": f"{exc.__class__.__name__}: {exc}",
            }
        outcome |= {
            "id": row["id"],
            "expected_category": row["category"],
            "expected_priority": row["priority"],
            "seconds": round(time.perf_counter() - started, 2),
            # Would the code-level guard stop triage from acting on this answer?
            "injection_guard": looks_like_prompt_injection(f"{row['subject']}\n{row['description']}"),
        }
        mark = "ok " if outcome["predicted_category"] == row["category"] else "BAD"
        print(
            f"[{index:2}/{len(rows)}] {mark} {row['id']:13} expected {row['category']:9} "
            f"got {outcome['predicted_category'] or 'ERROR':9} conf {outcome['confidence'] or 0:.2f} "
            f"({outcome['seconds']}s)"
        )
        outcomes.append(outcome)
    return outcomes


def percent(part: int, whole: int) -> float | None:
    """Percentage, or None when there's nothing to measure (shown as "n/a", never a fake 0%)."""
    return round(100 * part / whole, 1) if whole else None


def p95(values: list[float]) -> float:
    """95th percentile, nearest-rank method: 95% of values are at or below this."""
    ordered = sorted(values)
    return ordered[max(0, math.ceil(0.95 * len(ordered)) - 1)]


def summarise(outcomes: list[dict], threshold: float) -> dict:
    answered = [o for o in outcomes if o["error"] is None]
    right = [o for o in answered if o["predicted_category"] == o["expected_category"]]
    priority_right = [o for o in answered if o["predicted_priority"] == o["expected_priority"]]

    def priority_distance(o: dict) -> int:
        return abs(PRIORITY_ORDER.index(o["predicted_priority"]) - PRIORITY_ORDER.index(o["expected_priority"]))

    priority_close = [o for o in answered if priority_distance(o) <= 1]

    # The code only acts on confident answers. How many were confident, and how many of THOSE were right?
    confident = [o for o in answered if o["confidence"] >= threshold]
    confident_right = [o for o in confident if o["predicted_category"] == o["expected_category"]]
    unsure = [o for o in answered if o["confidence"] < threshold]
    unsure_right = [o for o in unsure if o["predicted_category"] == o["expected_category"]]

    per_category = {}
    for category in sorted({o["expected_category"] for o in outcomes}):
        rows = [o for o in answered if o["expected_category"] == category]
        per_category[category] = percent(sum(o["predicted_category"] == category for o in rows), len(rows))

    seconds = [o["seconds"] for o in outcomes]
    mistakes = Counter(f"{o['expected_category']} -> {o['predicted_category']}" for o in answered if o not in right)
    return {
        "tickets": len(outcomes),
        "failed_calls": len(outcomes) - len(answered),
        "category_accuracy": percent(len(right), len(answered)),
        "priority_accuracy": percent(len(priority_right), len(answered)),
        "priority_within_one_level": percent(len(priority_close), len(answered)),
        "confidence_threshold": threshold,
        "auto_applied_share": percent(len(confident), len(answered)),
        "accuracy_when_auto_applied": percent(len(confident_right), len(confident)),
        "accuracy_when_unsure": percent(len(unsure_right), len(unsure)),
        "per_category_accuracy": per_category,
        "most_common_mistakes": dict(mistakes.most_common(5)),
        "average_seconds": round(statistics.mean(seconds), 2) if seconds else 0,
        "p95_seconds": round(p95(seconds), 2) if seconds else 0,
        "blocked_by_injection_guard": [o["id"] for o in outcomes if o.get("injection_guard")],
    }


def write_reports(summary: dict, outcomes: list[dict], model: str, dataset: str, prompt_version: str) -> Path:
    RESULTS.mkdir(exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M")
    base = RESULTS / f"classification_{prompt_version}_{dataset}_{stamp}"
    meta = {"model": model, "prompt_version": prompt_version, "dataset": dataset, "run_at": stamp}
    base.with_suffix(".json").write_text(json.dumps(meta | {"summary": summary, "outcomes": outcomes}, indent=2))

    s = {k: ("n/a" if v is None else v) for k, v in summary.items()}
    lines = [
        f"# Classification eval: {prompt_version} on {model} ({dataset} set)",
        "",
        f"Run {stamp} UTC on {s['tickets']} labelled tickets ({s['failed_calls']} failed calls).",
        "",
        "| Metric | Result |",
        "|---|---|",
        f"| Category accuracy | **{s['category_accuracy']}%** |",
        f"| Priority exactly right | {s['priority_accuracy']}% |",
        f"| Priority within one level | {s['priority_within_one_level']}% |",
        f"| Confident enough to act (≥ {s['confidence_threshold']}) | {s['auto_applied_share']}% of tickets |",
        f"| **Accuracy when the AI acted** | **{s['accuracy_when_auto_applied']}%** |",
        f"| Accuracy when unsure (left for people) | {s['accuracy_when_unsure']}% |",
        f"| Average / p95 time per ticket | {s['average_seconds']} s / {s['p95_seconds']} s |",
        f"| Stopped by the code's injection guard | {', '.join(summary['blocked_by_injection_guard']) or 'none'} |",
        "",
        "## Per category",
        "",
        "| Category | Accuracy |",
        "|---|---|",
        *[f"| {c} | {'n/a' if a is None else f'{a}%'} |" for c, a in summary["per_category_accuracy"].items()],
        "",
        "## Most common mistakes",
        "",
        *([f"- {m}: {n}×" for m, n in s["most_common_mistakes"].items()] or ["- none"]),
        "",
        "## Wrong answers",
        "",
        "| Ticket | Expected | Got | Confidence | Model's reason |",
        "|---|---|---|---|---|",
        *[
            f"| {o['id']} | {o['expected_category']} | {o['predicted_category'] or 'ERROR'} | "
            f"{o['confidence'] if o['confidence'] is not None else '-'} | {(o['reasoning'] or o['error'] or '').replace('|', '/')} |"
            for o in outcomes
            if o["predicted_category"] != o["expected_category"]
        ],
    ]
    base.with_suffix(".md").write_text("\n".join(lines) + "\n")
    return base


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, help="only the first N tickets")
    parser.add_argument("--dataset", choices=sorted(DATASETS), default="main")
    parser.add_argument("--prompt", choices=sorted(PROMPTS), default=PROMPT_VERSION, help="prompt version to test")
    args = parser.parse_args()

    settings = get_settings()
    ai = AIService(build_provider(settings), max_output_retries=settings.ai_max_output_retries)
    rows = load_dataset(args.limit, args.dataset)
    print(f"Classifying {len(rows)} {args.dataset} tickets with {ai.chat_model} (prompt {args.prompt})...\n")

    outcomes = run(rows, ai, args.prompt)
    summary = summarise(outcomes, settings.ai_confidence_threshold)
    base = write_reports(summary, outcomes, ai.chat_model, args.dataset, args.prompt)

    print("\n" + json.dumps({k: v for k, v in summary.items() if k not in {"per_category_accuracy"}}, indent=2))
    print(f"\nReports: {base}.md and {base}.json")


if __name__ == "__main__":
    main()
