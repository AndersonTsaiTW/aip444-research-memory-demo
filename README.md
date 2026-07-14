# aip444-research-memory-demo

A small, self-contained demo of a dual-memory chatbot: short-term memory (STM — a bounded
conversation buffer) plus long-term memory (LTM — a Chroma vector database of atomic facts), with an
explicit decision layer that classifies every message as SAVE / IGNORE / UPDATE / DELETE / RECALL, and
rejects memory-poisoning attempts at write time.

Built as the prototype component of a university AI course research project.

## Status

Early scaffold — Python environment and dependencies only, no application code yet.

## Planned stack

- Python 3.11+, run in a project-local `venv`, no build step
- `openai` SDK pointed at OpenRouter for the LLM and embeddings
- `chromadb` (embedded, persistent) for long-term memory
- `pydantic` for validating tool-call arguments and data models
- Python's built-in `unittest` for unit tests

## Setup (once code lands)

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
