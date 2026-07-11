// Shared type definitions for the dual-memory chatbot.

// A single long-term memory = one atomic fact about the user
export interface Memory {
  id: string;
  content: string; 
  category: MemoryCategory;
  importance: 1 | 2 | 3 | 4 | 5; // scored by the decision layer (1 trivial .. 5 safety-critical)
  createdAt: string; 
  updatedAt: string; 
  source: string; // the original user message that triggered this memory (for audit)
  status: "active" | "deleted"; // soft delete
}

export type MemoryCategory = "profile" | "preference" | "project" | "constraint";

// On-disk shape of memory.json
export interface MemoryFile {
  memories: Memory[];
}

// A chat message in the short-term buffer / LLM request
export interface ChatMessage {
  role: "system" | "user" | "assistant" | "tool";
  content: string;
  // Present only on assistant messages that requested tools:
  tool_calls?: ToolCall[];
  // Present only on tool-result messages:
  tool_call_id?: string;
}

export interface ToolCall {
  id: string;
  type: "function";
  function: {
    name: string;
    arguments: string; // raw JSON string as returned by the model
  };
}

// The five memory decisions the agent can make about a message (BLOCKED = guardrail veto)
export type Decision = "SAVE" | "IGNORE" | "UPDATE" | "DELETE" | "RECALL" | "BLOCKED";
