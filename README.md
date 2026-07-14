# aip444-research-memory-demo

A small, self-contained demo of a dual-memory chatbot: short-term memory (STM — a bounded
conversation buffer) plus long-term memory (LTM — a Chroma vector database of atomic facts), with an
explicit decision layer that classifies every message as SAVE / IGNORE / UPDATE / DELETE / RECALL, and
rejects memory-poisoning attempts at write time.

Built as the prototype component of a university AI course research project.

## Status

M0 + M1 done — chat loop with short-term memory (bounded conversation buffer, overflow summarization).
No long-term memory or decision layer yet. Run it with `python -m src.main chat`.

## Stack

- Python 3.11+, run in a project-local `venv`, no build step
- `openai` SDK pointed at OpenRouter for the LLM and embeddings
- `chromadb` (embedded, persistent) for long-term memory (not wired up yet)
- `pydantic` for validating tool-call arguments and data models (not wired up yet)
- Python's built-in `unittest` for unit tests (see `tests/test_short_term.py`)

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
