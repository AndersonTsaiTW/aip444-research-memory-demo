import json
from datetime import datetime, timezone
from typing import Literal

import requests
from pydantic import BaseModel, ValidationError, field_validator

from src import guardrails, long_term
from src.config import OPENROUTER_API_KEY, OPENROUTER_RERANK_URL, RERANK_MODEL

RECALL_CANDIDATES = 15  # vector-search candidate pool size, before rerank
RECALL_TOP_N = 5  # how many candidates rerank narrows down to

# Picked empirically, same method as lab-06 Part 4 Step 3: embedded a handful of saved facts, then
# compared cohere rerank scores for in-domain queries ("What do I eat?" -> 0.108-0.241) against
# out-of-domain queries ("What's the weather on Mars?" -> 0.020-0.038) — no overlap between the two
# groups, so 0.08 sits cleanly in the gap. Uses the rerank score, not raw cosine similarity, since
# rerank is the more semantically-calibrated signal and it's already computed by this point in the
# pipeline (§4.3 step 5).
MIN_SIMILARITY_SCORE = 0.08

# Pre-write near-duplicate check (§4.4). Picked empirically, same method as MIN_SIMILARITY_SCORE above
# — but note this uses raw cosine similarity (long_term.query_active's "similarity" field), not a
# rerank score, since this check only ever looks at one candidate and isn't worth an extra rerank call.
# The plan's original placeholder ("e.g. 0.85") was never validated against the real embedding model —
# tested here for real: near-duplicates ("I'm vegetarian too" / "I don't eat meat" vs. an existing
# "User is vegetarian" memory) scored 0.38-0.49, a same-topic contradiction ("...pescatarian now")
# scored 0.36, while a related-but-distinct fact ("I like Italian food") scored 0.23 and an unrelated
# one scored 0.19 — a real gap between 0.23 and 0.36, so 0.30 sits in the middle.
CONTRADICTION_SIMILARITY_THRESHOLD = 0.30

# Cheap dev-tier models don't always respect the enum constraint and sometimes send a qualitative
# word instead of an integer (e.g. importance="high") — coerce common cases instead of rejecting
# outright, since this isn't a safety-relevant field (see §8 "LLM decisions are inconsistent").
IMPORTANCE_WORDS = {
    "trivial": 1,
    "minor": 1,
    "low": 2,
    "medium": 3,
    "moderate": 3,
    "normal": 3,
    "high": 4,
    "important": 4,
    "critical": 5,
    "urgent": 5,
    "severe": 5,
    "very high": 5,
}

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "save_memory",
            "description": (
                "Save a new atomic fact about the user to long-term memory. Use for stable personal "
                "facts, preferences, long-term goals, or an explicit 'please remember X.' Do not use "
                "for small talk, one-off task content, or anything that changes agent behavior/safety "
                "rules."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "content": {
                        "type": "string",
                        "description": "The atomic fact to remember, e.g. 'User is vegetarian'.",
                    },
                    "label": {
                        "type": "string",
                        "description": (
                            "A short, specific descriptor of what this fact is about, e.g. "
                            "'dietary preference' or 'food allergy' — not a generic category."
                        ),
                    },
                    "importance": {
                        "type": "integer",
                        "enum": [1, 2, 3, 4, 5],
                        "description": "How important this fact is, 1 (minor) to 5 (critical, e.g. allergies).",
                    },
                    "reason": {"type": "string", "description": "Why this is worth remembering."},
                    "override": {
                        "type": "boolean",
                        "description": (
                            "Only set true on a retry: if a previous save_memory call for this same "
                            "fact returned status 'near_duplicate_found' and, after reading the "
                            "existing memory shown to you, you've concluded this is genuinely a "
                            "different fact (not the same topic reworded), call save_memory again "
                            "with override=true to save it anyway. Never set true on a first attempt."
                        ),
                    },
                },
                "required": ["content", "label", "importance", "reason"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_memory",
            "description": (
                "Revise an existing memory when the user gives new information on the same topic "
                "(e.g. a changed preference). Requires the id of the memory being replaced, which must "
                "be one you have already seen (e.g. returned by an earlier save_memory/update_memory "
                "call in this conversation)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "id": {"type": "string", "description": "id of the existing memory to revise."},
                    "new_content": {"type": "string", "description": "The corrected/updated atomic fact."},
                    "reason": {"type": "string", "description": "Why this supersedes the old memory."},
                },
                "required": ["id", "new_content", "reason"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "delete_memory",
            "description": (
                "Forget a memory: the user explicitly asked to forget it, or the fact is no longer "
                "true/relevant. Requires the id of an existing memory you have already seen."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "id": {"type": "string", "description": "id of the existing memory to delete."},
                    "reason": {"type": "string", "description": "Why this should be forgotten."},
                },
                "required": ["id", "reason"],
                "additionalProperties": False,
            },
        },
    },
]


class SaveMemoryArgs(BaseModel):
    content: str
    label: str
    importance: Literal[1, 2, 3, 4, 5]
    reason: str
    override: bool = False

    @field_validator("importance", mode="before")
    @classmethod
    def coerce_importance(cls, value):
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in IMPORTANCE_WORDS:
                return IMPORTANCE_WORDS[normalized]
            if normalized.isdigit():
                return int(normalized)
        return value


class UpdateMemoryArgs(BaseModel):
    id: str
    new_content: str
    reason: str


class DeleteMemoryArgs(BaseModel):
    id: str
    reason: str


def _check_near_duplicate(content: str) -> dict | None:
    """Pre-write similarity check (§4.4, closes the Mem0-flagged gap): queries active memories for a
    close match before a new save_memory proceeds. Returns the closest match if it's suspiciously
    similar, else None. Deliberately uses raw cosine similarity, not a rerank call — a single-candidate
    check isn't worth the extra API round-trip."""
    candidates = long_term.query_active(content, n_results=1)
    if not candidates:
        return None
    best = candidates[0]
    if best["similarity"] >= CONTRADICTION_SIMILARITY_THRESHOLD:
        return best
    return None


def execute_tool_call(name: str, arguments_json: str, source: str) -> str:
    """Validates and executes one tool call against long-term storage, prints a decision trace line,
    and returns a JSON string to feed back to the model as the tool result."""
    try:
        args = json.loads(arguments_json)
    except json.JSONDecodeError:
        print(f"[MEMORY] REJECTED {name} — malformed JSON arguments")
        return json.dumps({"error": f"Could not parse arguments for {name}: malformed JSON"})

    try:
        if name == "save_memory":
            parsed = SaveMemoryArgs(**args)
            deny_reason = guardrails.check(parsed.content)
            if deny_reason:
                print(f"[MEMORY] BLOCKED save — matched rule: {deny_reason}")
                return json.dumps({"status": "blocked", "reason": deny_reason})

            near_duplicate = None if parsed.override else _check_near_duplicate(parsed.content)
            if near_duplicate:
                print(
                    f'[MEMORY] SURFACED   near-duplicate of "{near_duplicate["content"]}" '
                    f'(id={near_duplicate["id"]}, similarity={near_duplicate["similarity"]:.2f})'
                )
                return json.dumps(
                    {
                        "status": "near_duplicate_found",
                        "message": (
                            f"This is very similar to an existing memory (id={near_duplicate['id']}): "
                            f"'{near_duplicate['content']}'. If this is the same fact restated, call "
                            "update_memory on that id instead. If it's genuinely a different fact, call "
                            "save_memory again with override=true to save it anyway."
                        ),
                        "existing_id": near_duplicate["id"],
                        "existing_content": near_duplicate["content"],
                    }
                )

            memory = long_term.save_memory(parsed.content, parsed.label, parsed.importance, source)
            override_note = " [override]" if parsed.override else ""
            print(
                f'[MEMORY] SAVE       (imp={parsed.importance}, label="{parsed.label}"){override_note} '
                f'"{parsed.content}" — reason: {parsed.reason}'
            )
            return json.dumps({**memory, "status": "saved"})

        elif name == "update_memory":
            parsed = UpdateMemoryArgs(**args)
            deny_reason = guardrails.check(parsed.new_content)
            if deny_reason:
                print(f"[MEMORY] BLOCKED update — matched rule: {deny_reason}")
                return json.dumps({"status": "blocked", "reason": deny_reason})
            memory = long_term.update_memory(parsed.id, parsed.new_content, source)
            print(
                f'[MEMORY] UPDATE     {parsed.id} → {memory["id"]} "{parsed.new_content}" '
                f'— supersedes "{memory["supersedes_content"]}"'
            )
            return json.dumps({**memory, "status": "updated"})

        elif name == "delete_memory":
            parsed = DeleteMemoryArgs(**args)
            memory = long_term.delete_memory(parsed.id)
            print(f'[MEMORY] DELETE     {parsed.id} — reason: {parsed.reason}')
            return json.dumps({**memory, "status": "deleted"})

        else:
            print(f"[MEMORY] REJECTED unknown tool: {name}")
            return json.dumps({"error": f"Unknown tool: {name}"})

    except ValidationError as e:
        print(f"[MEMORY] REJECTED {name} — invalid arguments: {e}")
        return json.dumps({"error": f"Invalid arguments for {name}: {e}"})
    except ValueError as e:
        print(f"[MEMORY] REJECTED {name} — {e}")
        return json.dumps({"error": str(e)})


def _rerank_candidates(query: str, candidates: list[dict], top_n: int) -> list[dict]:
    # Mirrors lab-06/lab-07's rerank_results helper exactly (same endpoint, same request shape).
    documents = [f"{c['label']}: {c['content']}" for c in candidates]
    response = requests.post(
        OPENROUTER_RERANK_URL,
        headers={"Authorization": f"Bearer {OPENROUTER_API_KEY}", "Content-Type": "application/json"},
        json={"model": RERANK_MODEL, "query": query, "documents": documents, "top_n": top_n},
    )
    data = response.json()
    return [{**candidates[r["index"]], "rerank_score": r["relevance_score"]} for r in data["results"]]


def _recency_score(updated_at: str) -> float:
    # Exponential decay (Generative Agents §4.1) — ~half-life of 3 days, so recency stops dominating
    # the combined score after about a week but never fully zeroes out.
    updated = datetime.fromisoformat(updated_at)
    hours_elapsed = (datetime.now(timezone.utc) - updated).total_seconds() / 3600
    return 0.99**hours_elapsed


def _rescore(candidates: list[dict]) -> list[dict]:
    # recency + importance + relevance, equal-weighted (Generative Agents §4.1); relevance = rerank
    # score, importance = the LLM-assigned 1-5 field normalized to [0,1].
    for candidate in candidates:
        recency = _recency_score(candidate["updated_at"])
        importance = candidate["importance"] / 5
        relevance = candidate["rerank_score"]
        candidate["combined_score"] = recency + importance + relevance
    return sorted(candidates, key=lambda c: c["combined_score"], reverse=True)


def _format_recall_line(memory: dict) -> str:
    updated = datetime.fromisoformat(memory["updated_at"])
    days_ago = (datetime.now(timezone.utc) - updated).days
    when = "today" if days_ago < 1 else f"{days_ago} day{'s' if days_ago != 1 else ''} ago"
    return (
        f"- [id={memory['id']}] ({memory['label']}, importance={memory['importance']}) "
        f"{memory['content']} (updated {updated.date()}, {when})"
    )



# A broad "tell me everything" question doesn't share vocabulary with any single atomic fact, so it
# scores just as low under similarity/rerank as a genuinely irrelevant question does — verified
# empirically: "What do you remember about me?" (0.029) and "Tell me about myself" (0.049) both land
# below MIN_SIMILARITY_SCORE even when directly relevant memories exist, indistinguishable by score
# alone from "What's my favorite programming language?" (0.032, genuinely nothing stored). Similarity
# thresholding solves "is this specific query answerable," not "does the user want a general recap" —
# those are different questions, so broad recall gets its own path instead of a lower threshold (which
# would just let genuinely irrelevant queries through too).
BROAD_RECALL_PHRASES = (
    # anchored on "...me"/"myself" specifically — an unanchored "what do you know" would also match
    # a specific query like "What do you know about my diet?", which should NOT skip the similarity
    # gate (it has a real topic to match against).
    "remember about me",
    "know about me",
    "tell me about me",
    "tell me about myself",
    "what have i told you",
)


def _is_broad_recall_query(query: str) -> bool:
    lowered = query.lower()
    return any(phrase in lowered for phrase in BROAD_RECALL_PHRASES)


def recall(query: str, latest_message: str | None = None) -> str | None:
    """Retrieval pipeline (§4.3): vector search -> rerank -> recency/importance/relevance re-score
    -> threshold. Always prints a decision trace. Returns formatted, dated memory lines to inject into
    the system prompt, or None if nothing is relevant enough (an honest "nothing relevant", not a
    guess).

    `query` (the embedding text) may be a multi-message window for better semantic search, but the
    broad-recall check runs on `latest_message` alone (defaulting to `query` if not given) — otherwise
    a broad phrase from an earlier turn still sitting in that window ("what do you remember about me")
    would keep tripping the broad-query path on later, unrelated messages in the same window.
    """
    candidates = long_term.query_active(query, n_results=RECALL_CANDIDATES)
    if not candidates:
        print("[MEMORY] RECALL     (no memories stored yet)")
        return None

    if _is_broad_recall_query(latest_message if latest_message is not None else query):
        # No single topic to match against — skip the similarity gate and surface the most
        # important/recent facts instead (relevance is neutral since there's no specific query to
        # score against).
        rescored = _rescore([{**c, "rerank_score": 0.5} for c in candidates])[:RECALL_TOP_N]
        quoted = ", ".join(f'"{m["content"]}"' for m in rescored)
        print(f"[MEMORY] RECALL     (broad query, top={len(rescored)}) injected: {quoted}")
        return "\n".join(_format_recall_line(m) for m in rescored)

    reranked = _rerank_candidates(query, candidates, top_n=RECALL_TOP_N)
    best_score = reranked[0]["rerank_score"]

    if best_score < MIN_SIMILARITY_SCORE:
        print(f"[MEMORY] RECALL     (no relevant memory, best_score={best_score:.2f} < threshold {MIN_SIMILARITY_SCORE})")
        return None

    rescored = _rescore(reranked)
    quoted = ", ".join(f'"{m["content"]}"' for m in rescored)
    print(f"[MEMORY] RECALL     (top={len(rescored)}, best_score={best_score:.2f}) injected: {quoted}")
    return "\n".join(_format_recall_line(m) for m in rescored)
