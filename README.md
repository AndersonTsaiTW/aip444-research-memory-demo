# aip444-research-memory-demo

A small, self-contained demo of a dual-memory chatbot: short-term memory (STM — a bounded
conversation buffer) plus long-term memory (LTM — a Chroma vector database of atomic facts), with an
explicit decision layer that classifies every message as SAVE / IGNORE / UPDATE / DELETE / RECALL, and
rejects memory-poisoning attempts at write time.

Built as the prototype component of a university AI course research project.

## Architecture

One user message flows through this pipeline every turn:

```text
User types a message
  │
  ▼
1. STM ingest (short_term.py) — append to the conversation buffer; if it's over the token cap,
   summarize the oldest half into a single "[Conversation summary] ..." message so the
   conversation keeps going without the buffer growing unbounded.
  │
  ▼
2. RECALL (decision.py) — embed the message (+ recent user turns) → Chroma vector search,
   filtered to status="active" → rerank → top 5 → re-scored by recency + importance +
   relevance → below threshold = "nothing relevant" (an honest refusal, not a guess).
   Injected into the system prompt with a human-readable date per memory.
  │
  ▼
3. Prompt assembly — system prompt + memory policy (prompts.py) + RECALL result + STM
   buffer/summary + the new message.
  │
  ▼
4. LLM call, tools exposed (agent.py) — the model replies, and may call save_memory /
   update_memory / delete_memory zero, one, or several times in the same turn (one call per
   atomic fact worth acting on). No tool call at all = IGNORE — most small talk produces zero
   calls. This is a tool-calling loop (call → execute tools → feed results back → call again
   if needed), not strictly one shot — see step 6.
  │
  ▼
5. decision.py validates — malformed tool-call arguments (pydantic) are rejected before
   anything else runs.
  │
  ▼
6. Pre-write near-duplicate check (decision.py, save_memory only) — queries active memories
   again; a close match is surfaced back to the LLM as tool feedback instead of silently
   double-saving. The model gets another turn to react — typically switching to
   update_memory, or retrying save_memory with override=true if the match turns out to be
   unrelated — still within the same user turn.
  │
  ▼
7. guardrails.py — deny-checks every tool call that made it this far: behavior-override
   instructions, secrets/credentials, third-party private data. A match → BLOCKED, the write
   never reaches storage.
  │
  ▼
8. Storage write (long_term.py), if not blocked:
     save_memory   → new row, status="active"
     update_memory → non-destructive: old row → status="superseded"; new row inserted,
                      supersedes=<old_id>
     delete_memory → soft delete, status="deleted", never physically removed
  │
  ▼
9. Decision trace printed to the terminal either way — SAVE / IGNORE / UPDATE / DELETE /
   BLOCKED / RECALL, every time. Decisions are always visible, never silent.
  │
  ▼
10. Reply printed to the user → loop back to step 1 for the next message.
```

**Across sessions**: STM is discarded when the process exits; LTM lives on disk in `chroma_db/`
and persists. A new `chat` invocation starts with empty STM but the full accumulated LTM.

**Which of SAVE / UPDATE / DELETE the model picks is entirely the model's judgment call, not
code's.** Code never classifies "this should be an update" — it only validates arguments,
surfaces near-duplicates as feedback so the model can reconsider before a write happens, and
enforces guardrail denials.

## Status

M0-M4 done, M5 (polish) partly under way — chat loop with short-term memory, long-term memory backed by
Chroma (SAVE / UPDATE non-destructively / DELETE softly, with an `override` escape hatch on save_memory
for when the near-duplicate check false-positives), retrieval (vector search + rerank +
recency/importance/relevance re-score before replying, so memories persist and get used across separate
`chat` sessions), write-time guardrails that deny behavior-override instructions, secrets/credentials,
and third-party private data before they ever reach storage, a pre-write near-duplicate check that
surfaces a close-matching existing memory instead of silently double-saving, and an `eval/` regression
suite (real LLM, no mocks) covering all of the above. Of M5's remaining items, the architecture diagram
and Usage section below are already in place and the `unittest` suite covers every `src/` module; a demo
GIF is still outstanding. Run it with `python -m src.main chat`; inspect stored memories with
`python -m src.main memories` (add `--all` to include superseded/deleted rows); run the eval suite with
`python -m eval.run_eval` (16/16 passing as of 2026-07-16, checked stable across 3 runs).

**Eval note**: `eval/cases/*.yaml` replays scripted conversations through the real agent (no mocks) and
grades the decision layer's output; `eval/cases/poisoning.yaml` also has `direct_tool_call` cases that
bypass the LLM entirely to prove the write-time guardrail works on its own. One early test case
(deleting a standalone "I'm working on my project" mention) surfaced a real LLM-consistency finding —
that fact alone didn't get saved reliably outside the demo script's paired-with-a-preference framing —
not a code bug; see `eval/cases/delete.yaml`'s rationale field for the fix (a food-allergy fact instead).

**Near-duplicate note**: `CONTRADICTION_SIMILARITY_THRESHOLD` is 0.30, not an unvalidated "e.g. 0.85"
placeholder — that number was never tested against the real embedding model and turned out far too high
(the clearest possible near-duplicate only scored 0.49). See the comment above the constant in
`src/decision.py` for the empirical basis. No single threshold is airtight, though: two short, unrelated
facts about the same user (a dietary preference and a favorite sport) once scored 0.33 — above the
threshold — which silently blocked a real save and, in one traced case, caused a later `delete_memory`
call to target the wrong (surfaced-but-unrelated) memory instead. `save_memory` now accepts an
`override: true` argument so the model can force the save through once it has confirmed the surfaced
memory is unrelated, instead of the fact being silently dropped; see
`tests/test_decision.py::TestExecuteToolCallSaveMemory.test_override_skips_near_duplicate_check_and_saves`
and `eval/cases/contradiction.yaml`'s `contradiction-002` case for regression coverage.

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
same demo script `gpt-4o-mini` ran correctly end-to-end. Not a bug in this codebase — it's a real
reliability gap between models at following multi-step tool-calling instructions consistently.

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

## Usage

Run the chat loop:

```bash
python -m src.main chat
```

Type `exit` or `quit` to end the session. Every message you send may trigger a `[MEMORY] ...` trace
line — SAVE, IGNORE, UPDATE, DELETE, BLOCKED, or RECALL — showing exactly what the decision layer did
with it (see Architecture above for what each one means).

Inspect what's actually stored in long-term memory:

```bash
python -m src.main memories          # active memories only
python -m src.main memories --all    # include superseded/deleted rows too
```

Run the regression suite (real LLM/embedding/rerank calls, no mocks — takes 1-2 minutes and uses API
quota):

```bash
python -m eval.run_eval
```

Run the unit tests (no API calls, fakes/mocks only):

```bash
python -m unittest discover -s tests
```

**Windows note**: if a `python -m src.main chat` session ever raises `UnicodeEncodeError`, that's a
non-UTF-8 terminal codepage (e.g. `cp950`) rejecting an emoji or other character — `src/main.py`
already reconfigures stdout to UTF-8 with `errors="replace"`, so at worst you'll see a `?` in place of
an unsupported character rather than a crash.
