// LLM provider abstraction. Wraps the OpenAI SDK pointed at OpenRouter so that
// switching providers/models later only touches this file.

import OpenAI from "openai";
import type { ChatMessage, ToolCall } from "./types.ts";

// A tool definition in OpenAI's function calling forma
export interface ToolDef {
  type: "function";
  function: {
    name: string;
    description: string;
    parameters: Record<string, unknown>; // JSON Schema
  };
}

export interface LLMResponse {
  content: string;
  toolCalls: ToolCall[];
}

// note:swap to a stronger model for the final demo
// by setting MODEL in .env
const DEFAULT_MODEL = "google/gemini-2.5-flash-lite";

export class LLM {
  private client: OpenAI;
  private model: string;

  constructor() {
    const apiKey = process.env["OPENROUTER_API_KEY"];
    if (!apiKey) {
      throw new Error(
        "OPENROUTER_API_KEY is not set. Copy .env.example to .env and add your OpenRouter key.",
      );
    }
    this.model = process.env["MODEL"] ?? DEFAULT_MODEL;
    this.client = new OpenAI({
      apiKey,
      baseURL: "https://openrouter.ai/api/v1",
    });
  }

  /// Send messages (optionally with tools) and return the assistant reply + any tool calls. 
  async chat(messages: ChatMessage[], tools?: ToolDef[]): Promise<LLMResponse> {
    const response = await this.client.chat.completions.create({
      model: this.model,
      // The SDK's message type is wider than ours; the shapes are compatible at runtime.
      messages: messages as unknown as OpenAI.Chat.ChatCompletionMessageParam[],
      ...(tools && tools.length > 0 ? { tools } : {}),
    });

    const choice = response.choices[0];
    const message = choice?.message;
    const toolCalls: ToolCall[] = (message?.tool_calls ?? [])
      .filter((tc) => "function" in tc && tc.type === "function")
      .map((tc) => {
        const fn = (tc as { function: { name: string; arguments: string } }).function;
        return {
          id: tc.id,
          type: "function" as const,
          function: { name: fn.name, arguments: fn.arguments },
        };
      });

    return { content: message?.content ?? "", toolCalls };
  }
}
