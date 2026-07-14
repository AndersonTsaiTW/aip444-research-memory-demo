# aip444-research-memory-demo

A small, self-contained demo of a dual-memory chatbot: short-term memory (STM — a bounded
conversation buffer) plus long-term memory (LTM — a Chroma vector database of atomic facts), with an
explicit decision layer that classifies every message as SAVE / IGNORE / UPDATE / DELETE / RECALL, and
rejects memory-poisoning attempts at write time.

Built as the prototype component of a university AI course research project.

## Status

M0 + M1 + M2 done — chat loop with short-term memory, plus long-term memory backed by Chroma: the
agent can SAVE / UPDATE (non-destructively) / DELETE (soft) atomic facts about the user, with every
decision printed to the terminal. No retrieval (RECALL) or guardrails yet. Run it with
`python -m src.main chat`; inspect stored memories with `python -m src.main memories` (add `--all` to
include superseded/deleted rows).

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
