# aip444-research-memory-demo

A small, self-contained demo of a dual-memory chatbot: short-term memory (STM — a bounded
conversation buffer) plus long-term memory (LTM — a Chroma vector database of atomic facts), with an
explicit decision layer that classifies every message as SAVE / IGNORE / UPDATE / DELETE / RECALL, and
rejects memory-poisoning attempts at write time.

Built as the prototype component of a university AI course research project.

## Status

M0-M3 done — chat loop with short-term memory, long-term memory backed by Chroma (SAVE / UPDATE
non-destructively / DELETE softly), and retrieval: every turn does a vector search + rerank +
recency/importance/relevance re-score before replying, so memories actually persist and get used
across separate `chat` sessions, not just within one. No guardrails yet. Run it with
`python -m src.main chat`; inspect stored memories with `python -m src.main memories` (add `--all` to
include superseded/deleted rows).

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
