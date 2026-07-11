// The agent: one turn = build prompt (with recalled memories) -> call LLM ->
// apply any memory tool calls through the decision layer -> get the final reply.

import type { ChatMessage } from "./types.ts";
import { LLM } from "./llm.ts";
import { ConversationBuffer } from "./shortTerm.ts";
import { MemoryStore } from "./longTerm.ts";
import { buildSystemPrompt } from "./prompts.ts";
import { MEMORY_TOOLS, applyToolCall, type DecisionTrace } from "./decision.ts";

export interface TurnResult {
  reply: string;
  traces: DecisionTrace[];
  summarized: boolean;
}

export class Agent {
  private llm: LLM;
  private stm: ConversationBuffer;
  private ltm: MemoryStore;

  constructor(llm: LLM, stm: ConversationBuffer, ltm: MemoryStore) {
    this.llm = llm;
    this.stm = stm;
    this.ltm = ltm;
  }

  get shortTerm(): ConversationBuffer {
    return this.stm;
  }

  get longTerm(): MemoryStore {
    return this.ltm;
  }

  // Process one user message end-to-end
  async handle(userMessage: string): Promise<TurnResult> {
    this.stm.add({ role: "user", content: userMessage });

    // 1. RECALL: active memories are injected into the system prompt.
    const system: ChatMessage = {
      role: "system",
      content: buildSystemPrompt(this.ltm.active()),
    };
    const request: ChatMessage[] = [system, ...this.stm.getMessages()];

    // 2. LLM replies, optionally requesting memory tools.
    const first = await this.llm.chat(request, MEMORY_TOOLS);
    const traces: DecisionTrace[] = [];

    if (first.toolCalls.length === 0) {
      // No tool call means ignore which is default and the reply is whatever the model said.
      const reply = first.content || "(no reply)";
      this.stm.add({ role: "assistant", content: reply });
      traces.push({
        decision: "IGNORE",
        toolName: "-",
        detail: "no memory operation",
        reason: "nothing durable to store",
        toolResult: "",
      });
      const summarized = await this.stm.summarizeIfNeeded(this.llm);
      return { reply, traces, summarized };
    }

    // 3 and 4. Apply each tool call through the decision layer: validate -> guardrail -> store
    this.stm.add({
      role: "assistant",
      content: first.content,
      tool_calls: first.toolCalls,
    });
    for (const call of first.toolCalls) {
      const trace = applyToolCall(call, this.ltm, userMessage);
      traces.push(trace);
      this.stm.add({
        role: "tool",
        content: trace.toolResult,
        tool_call_id: call.id,
      });
    }

    // 5. Second LLM call so it can phrase a natural reply given what actually happened.
    const followupSystem: ChatMessage = {
      role: "system",
      content: buildSystemPrompt(this.ltm.active()),
    };
    const second = await this.llm.chat(
      [followupSystem, ...this.stm.getMessages()],
      MEMORY_TOOLS,
    );
    const reply = second.content || first.content || "(done)";
    this.stm.add({ role: "assistant", content: reply });

    const summarized = await this.stm.summarizeIfNeeded(this.llm);
    return { reply, traces, summarized };
  }
}
