# aip444-research-memory-demo

A small, self-contained demo of a dual-memory chatbot: short-term memory (STM — a bounded
conversation buffer) plus long-term memory (LTM — a Chroma vector database of atomic facts), with an
explicit decision layer that classifies every message as SAVE / IGNORE / UPDATE / DELETE / RECALL, and
rejects memory-poisoning attempts at write time.

Built as the prototype component of a university AI course research project.

## Status

M0-M4 done — chat loop with short-term memory, long-term memory backed by Chroma (SAVE / UPDATE
non-destructively / DELETE softly), retrieval (vector search + rerank + recency/importance/relevance
re-score before replying, so memories persist and get used across separate `chat` sessions), write-time
guardrails that deny behavior-override instructions, secrets/credentials, and third-party private data
before they ever reach storage, a pre-write near-duplicate check that surfaces a close-matching existing
memory instead of silently double-saving, and an `eval/` regression suite (real LLM, no mocks) covering
all of the above. Run it with `python -m src.main chat`; inspect stored memories with
`python -m src.main memories` (add `--all` to include superseded/deleted rows); run the eval suite with
`python -m eval.run_eval` (15/15 passing as of 2026-07-16, checked stable across 3 runs).

**Eval note**: `eval/cases/*.yaml` replays scripted conversations through the real agent (no mocks) and
grades the decision layer's output; `eval/cases/poisoning.yaml` also has `direct_tool_call` cases that
bypass the LLM entirely to prove the write-time guardrail works on its own. One early test case
(deleting a standalone "I'm working on my project" mention) surfaced a real LLM-consistency finding —
that fact alone didn't get saved reliably outside the demo script's paired-with-a-preference framing —
not a code bug; see `eval/cases/delete.yaml`'s rationale field for the fix (a food-allergy fact instead).

**Near-duplicate note**: `CONTRADICTION_SIMILARITY_THRESHOLD` is 0.30, not the plan's original "e.g.
0.85" placeholder — that number was never validated and turned out far too high for the real embedding
model (the clearest possible near-duplicate only scored 0.49). See the comment above the constant in
`src/decision.py` for the empirical basis.

**Guardrails note**: with a capable, safety-trained model (the current default, `gpt-4o-mini`), asking
it to remember an API key or "ignore all future safety warnings" gets refused by the model itself
(`IGNORE`) before it ever calls `save_memory` — the write-time deny-list in `src/guardrails.py` never
gets exercised through the natural chat flow for these two lines. That's not a sign it's untested: see
`tests/test_guardrails.py`, which calls the decision layer directly with the same payloads a
non-compliant model would send, and confirms both get `BLOCKED` before reaching storage.

**Retrieval note**: a broad "what do you remember about me?"-style question doesn't share vocabulary
with any single stored fact, so it scores just as low under similarity/rerank as a genuinely irrelevant
question — verified empirically. Broad recall questions get their own path (skip the similarity gate,
surface the most important/recent facts) instead of a lower threshold, which would let genuinely
irrelevant queries through too. See the comment above `BROAD_RECALL_PHRASES` in `src/decision.py`.

**Model note**: `CHAT_MODEL` defaults to `openai/gpt-4o-mini`. Two cheaper candidates
(`google/gemini-2.5-flash-lite`, `deepseek/deepseek-v4-flash`) were tried first and dropped — both
intermittently skipped or under-extracted tool calls (a missed fact, a hallucinated id) on the exact
same demo script `gpt-4o-mini` ran correctly end-to-end. Not a bug in this codebase; see §8 "LLM
decisions are inconsistent" in the plan.

## Stack

- Python 3.11+, run in a project-local `venv`, no build step
- `openai` SDK pointed at OpenRouter for the LLM and embeddings
- `chromadb` (embedded, persistent) for long-term memory
- `pydantic` for validating tool-call arguments and data models
- Python's built-in `unittest` for unit tests (see `tests/`)

## Setup

Copy `.env.example` to `.env` and add your OpenRouter key:

```env
OPENROUTER_API_KEY=sk-or-v1-your-key-here
```

Create a virtual environment and install dependencies:

```bash
python -m venv .venv
.venv/Scripts/activate   # on Windows; use .venv/bin/activate on macOS/Linux
pip install -r requirements.txt
```

Run the chat loop:

```bash
python -m src.main chat
```
