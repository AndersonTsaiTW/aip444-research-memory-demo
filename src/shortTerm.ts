// Short-term memory (STM): a bounded conversation buffer that mirrors an LLM's
// limited context window. When it overflows, the oldest half is summarized into a
// single summary message — the same "memory pressure" idea as MemGPT.

import type { ChatMessage } from "./types.ts";
import type { LLM } from "./llm.ts";

// Rough token estimate: ~4 characters per token
export function estimateTokens(text: string): number {
  return Math.ceil(text.length / 4);
}

function messageTokens(m: ChatMessage): number {
  return estimateTokens(m.content) + 4; // +4 for role/formatting overhead
}

export class ConversationBuffer {
  private messages: ChatMessage[] = [];
  readonly maxTokens: number;

  constructor(maxTokens = 4000) {
    this.maxTokens = maxTokens;
  }

  add(message: ChatMessage): void {
    this.messages.push(message);
  }

  // All messages currently held (the working context)
  getMessages(): ChatMessage[] {
    return this.messages;
  }

  tokenCount(): number {
    return this.messages.reduce((sum, m) => sum + messageTokens(m), 0);
  }

  // Percentage of the token budget currently used 
  pressure(): number {
    return Math.round((this.tokenCount() / this.maxTokens) * 100);
  }

  isOverCap(): boolean {
    return this.tokenCount() > this.maxTokens;
  }

  /**
   * If over the token cap, summarize the oldest half of the (non-summary) messages
   * into a single system summary, replacing the originals. Returns true if it summarized.
   */
  async summarizeIfNeeded(llm: LLM): Promise<boolean> {
    if (!this.isOverCap() || this.messages.length < 4) return false;

    const half = Math.floor(this.messages.length / 2);
    const toSummarize = this.messages.slice(0, half);
    const remaining = this.messages.slice(half);

    const transcript = toSummarize
      .map((m) => `${m.role}: ${m.content}`)
      .join("\n");

    const { content } = await llm.chat([
      {
        role: "system",
        content:
          "Summarize the following conversation excerpt into a few compact bullet points, " +
          "preserving any facts, names, preferences, or decisions. Be terse.",
      },
      { role: "user", content: transcript },
    ]);

    const summaryMessage: ChatMessage = {
      role: "system",
      content: `[Conversation summary]\n${content}`,
    };
    this.messages = [summaryMessage, ...remaining];
    return true;
  }
}
