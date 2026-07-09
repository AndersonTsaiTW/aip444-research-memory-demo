# aip444-research-memory-demo

A small, self-contained demo of a dual-memory chatbot: short-term memory (STM — a bounded
conversation buffer) plus long-term memory (LTM — a JSON-backed key-value store), with an explicit
decision layer that classifies every message as SAVE / IGNORE / UPDATE / DELETE / RECALL, and rejects
memory-poisoning attempts at write time.

Built as the prototype component of a university AI course research project.

## Status

Early scaffold — project config and dependencies only, no application code yet.

## Planned stack

- TypeScript on Node.js, run directly via `tsx` (no build step)
- `openai` SDK pointed at OpenRouter for the LLM
- `zod` for validating tool-call arguments (added once the decision layer lands)
- Node's built-in `node:test` for unit tests

## Setup (once code lands)

Copy `.env.example` to `.env` and add your OpenRouter key:

```env
OPENROUTER_API_KEY=sk-or-v1-your-key-here
```

Install dependencies:

```bash
npm install
```
