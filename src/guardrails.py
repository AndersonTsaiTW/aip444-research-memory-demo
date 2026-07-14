import re

# Strong-signal patterns: content phrased as a command to override the agent's own behavior/safety
# rules (Dash et al.'s "Explicit Command Insertion" class — see ../aip444-research/literature/
# 06-dash-memory-poisoning.md). This is a deny-list, so it's well-suited to exactly this class of
# attack and not to subtler, non-imperative phrasing (see Implementation notes below once written).
BEHAVIOR_OVERRIDE_PATTERNS = [
    r"\bignore (all|any|previous|prior|future) .*(safety|instruction|warning|rule)",
    r"\bdisregard (all|any|previous|prior|future) .*(safety|instruction|warning|rule)",
    r"\byou are now\b",
    r"\bfrom now on you (are|will|must)\b",
    r"\bnew instructions?:",
    r"\bforget (all|your) (previous |prior )?(instructions|rules|safety)",
    r"\bdo not (follow|obey) (your|the) (safety|previous) (rules|instructions)",
]

SECRET_PATTERNS = [
    r"\bsk-[a-zA-Z0-9]{8,}\b",  # OpenAI/OpenRouter-style API keys
    r"\b(api[_ -]?key|password|passwd|secret key)\b\s*[:=]?\s*\S+",
    r"\b\d{4}[- ]\d{4}[- ]\d{4}[- ]\d{4}\b",  # credit-card-like number grouping
]

# Weak-signal-ish case: a fact about a named relationship (not the user) combined with a sensitive
# data type. Keyword co-occurrence, not a semantic judgment — see Implementation notes for the honest
# limits of this once tested.
THIRD_PARTY_RELATIONSHIP_WORDS = [
    r"\b(my|his|her|their) (friend|mother|father|mom|dad|sister|brother|coworker|colleague|"
    r"wife|husband|partner|boss|neighbor|roommate)('s)?\b",
]
SENSITIVE_DATA_TYPES = [
    r"\b(social security|ssn|password|credit card|medical (condition|history|record)|"
    r"diagnos(is|ed)|home address|phone number)\b",
]


def _matches_any(patterns: list[str], text: str) -> bool:
    return any(re.search(pattern, text) for pattern in patterns)


def check(content: str) -> str | None:
    """Returns a deny reason if content matches a guardrail rule, else None. Runs on the exact text
    about to be written (save_memory's content, update_memory's new_content) before it reaches
    storage — write-time enforcement, per Lin et al.'s "security cannot be retrofitted at retrieval or
    execution time alone" (../aip444-research/literature/05-lin-memory-security.md)."""
    lowered = content.lower()

    if _matches_any(BEHAVIOR_OVERRIDE_PATTERNS, lowered):
        return "behavior-override instruction"

    if _matches_any(SECRET_PATTERNS, lowered):
        return "secret/credential"

    if _matches_any(THIRD_PARTY_RELATIONSHIP_WORDS, lowered) and _matches_any(SENSITIVE_DATA_TYPES, lowered):
        return "third-party private data"

    return None
