"""A simple, deterministic check: does this ticket text try to give the AI instructions?

The classifier prompt already tells the model to ignore instructions inside tickets, but the
classify-v1 evaluation showed a model can still obey them. So the CODE also checks, and when the
text looks like an injection attempt, triage doesn't act on the AI's answer at all.

This is "defence in depth": two independent layers, so one failing isn't enough to cause harm.
Like the redaction patterns, it catches common phrasings, not every possible trick.
"""

import re

_VALUES = "billing|payment|technical|account|login|product|security|other|low|medium|high|critical"

_PATTERNS = [
    r"\bignore (all |any |the )?(previous|prior|above|earlier|your) (instructions|rules|prompts?)\b",
    r"\bdisregard (all |any |the )?(previous|prior|above|your) (instructions|rules)\b",
    r"\b(system|admin|developer) (override|mode)\b",
    r"\byou are now (in |an? )?(admin|developer|system|jailbreak|unrestricted|ai|assistant)\b",
    r"\b(system prompt|your instructions)\b",
    # "set category SECURITY", "mark the priority as critical", "use priority: high"
    rf"\b(set|change|mark|make|use)\W+(the\W+)?(category|priority)\W+(to\W+|as\W+|=\W*|:\W*)?({_VALUES})\b",
    # "category=SECURITY", "priority: critical"
    rf"\b(category|priority)\s*[=:]\s*({_VALUES})\b",
]
_INJECTION = re.compile("|".join(_PATTERNS), re.IGNORECASE)


def looks_like_prompt_injection(text: str) -> bool:
    return _INJECTION.search(text) is not None
