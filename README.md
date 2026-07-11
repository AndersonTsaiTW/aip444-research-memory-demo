# aip444-research-memory-demo

A small, self-contained demo of a dual-memory chatbot: short-term memory (STM — a bounded
conversation buffer) plus long-term memory (LTM — a JSON-backed key-value store), with an explicit
decision layer that classifies every message as SAVE / IGNORE / UPDATE / DELETE / RECALL, and rejects
memory-poisoning attempts at write time.

Built as the prototype component of a university AI course research project (AIP444).

## What it does

For every user message the agent decides — via LLM tool-calling — whether to:

- **SAVE** a stable, reusable fact (preference, profile, goal, constraint),
- **IGNORE** conversational noise (the default),
- **UPDATE** an existing memory when new info refines/contradicts it,
- **DELETE** a memory when asked to forget,
- **RECALL** stored memories to answer a later question (memories are injected into the prompt),

and a write-time **guardrail** layer blocks poisoning instructions, secrets/credentials, and sensitive
third-party data *even if the model tries to store them* — "model proposes, code enforces."

## Architecture

```
user message
  │
  ├─ RECALL: active LTM facts injected into the system prompt
  │
  ▼
 LLM ── tool calls ──▶ decision layer (decision.ts)
  │                      │  1. zod-validate tool arguments
  │                      │  2. guardrails.ts deny-rules (poisoning / secrets / third-party PII)
  │                      │  3. apply to LTM store (save / update / soft-delete)
  │                      ▼
  │                  memory.json  (atomic write: temp file → rename)
  ▼
 reply + printed decision trace + STM pressure meter
```

| Module | Role |
|---|---|
| `src/shortTerm.ts` | STM: bounded buffer, token estimate, overflow summarization (MemGPT-style pressure) |
| `src/longTerm.ts` | LTM: JSON-file CRUD of atomic facts, soft-delete, atomic persist |
| `src/decision.ts` | Tool definitions + zod validation + guardrail gate + store mutation → decision trace |
| `src/guardrails.ts` | Write-time deny-rules (the security gate) |
| `src/prompts.ts` | System prompt + memory policy (from the decision rubric) |
| `src/agent.ts` | One-turn orchestration: recall → LLM → apply tools → reply |
| `src/llm.ts` | LLM provider abstraction (OpenAI SDK → OpenRouter) |
| `src/index.ts` | CLI: `chat` / `memories` / `reset` |
| `eval/` | YAML test cases + `runEval.ts` pass-rate harness |
| `tests/` | `node:test` unit tests (pure logic, no API calls) |

## Setup

Copy `.env.example` to `.env` and add your OpenRouter key:

```env
OPENROUTER_API_KEY=sk-or-v1-your-key-here
# optional: override the model (default is a cheap dev model)
# MODEL=openai/gpt-4o-mini
```

Install dependencies:

```bash
npm install
```

## Usage

```bash
npm run chat        # interactive dual-memory chat
npm run memories    # list stored long-term memories
npm run reset       # wipe long-term memory
npm run eval        # run the YAML evaluation cases (needs the API key)
npm test            # unit tests (no API key needed)
npm run typecheck   # tsc --noEmit
```

In chat, use `/memories`, `/reset`, `/exit`. Each turn prints a decision trace, e.g.:

```
you> I'm a vegetarian.
  [MEMORY] SAVE   (imp=3, preference) "User is vegetarian" — reason: stable dietary preference
  [STM] buffer at 4% (168/4000 tokens)
bot> Got it — I'll remember you're vegetarian.
```

## Design provenance

STM/LTM split ← MemGPT (Packer et al., 2023); SAVE/IGNORE/UPDATE/DELETE ← Mem0's ADD/UPDATE/DELETE/NOOP
(Chhikara et al., 2025); importance/recall ranking ← Generative Agents (Park et al., 2023); write-time
guardrails ← Lin et al. (2026) lifecycle + Dash et al. (2026) poisoning taxonomy. Full write-up in the
group report.
