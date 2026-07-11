// Decision layer: defines the memory tools, validates the model's tool-call
// arguments with zod, runs guardrails, applies the change to the store, and
// records a decision trace. This is where "model proposes, code enforces" lives.

import { z } from "zod";
import type { ToolDef } from "./llm.ts";
import type { ToolCall, Decision } from "./types.ts";
import { MemoryStore } from "./longTerm.ts";
import { checkWrite, type GuardrailRule } from "./guardrails.ts";

// Tool argument schemas using zod
const saveSchema = z.object({
  content: z.string().min(1),
  category: z.enum(["profile", "preference", "project", "constraint"]),
  importance: z.number().int().min(1).max(5),
  reason: z.string().default(""),
});

const updateSchema = z.object({
  id: z.string().min(1),
  new_content: z.string().min(1),
  reason: z.string().default(""),
});

const deleteSchema = z.object({
  id: z.string().min(1),
  reason: z.string().default(""),
});

// Tool definitions handed to the LLM 
export const MEMORY_TOOLS: ToolDef[] = [
  {
    type: "function",
    function: {
      name: "save_memory",
      description: "Store one atomic, durable fact about the user in long-term memory.",
      parameters: {
        type: "object",
        properties: {
          content: { type: "string", description: "One atomic fact, e.g. 'User is vegetarian'." },
          category: { type: "string", enum: ["profile", "preference", "project", "constraint"] },
          importance: { type: "integer", minimum: 1, maximum: 5 },
          reason: { type: "string", description: "Short justification for saving." },
        },
        required: ["content", "category", "importance"],
      },
    },
  },
  {
    type: "function",
    function: {
      name: "update_memory",
      description: "Revise an existing memory when new info contradicts or refines it. Use its id.",
      parameters: {
        type: "object",
        properties: {
          id: { type: "string", description: "The id of the existing memory to update." },
          new_content: { type: "string" },
          reason: { type: "string" },
        },
        required: ["id", "new_content"],
      },
    },
  },
  {
    type: "function",
    function: {
      name: "delete_memory",
      description: "Remove a memory when the user asks to forget it or it has expired. Use its id.",
      parameters: {
        type: "object",
        properties: {
          id: { type: "string", description: "The id of the memory to delete." },
          reason: { type: "string" },
        },
        required: ["id"],
      },
    },
  },
];

// Outcome of applying a single tool call — carries the decision trace. 
export interface DecisionTrace {
  decision: Decision;
  toolName: string;
  detail: string; // this is a human readable description of what happened
  reason: string; 
  blockedRule?: GuardrailRule;
  memoryId?: string;
  importance?: number;
  category?: string;
  toolResult: string; // this is what the tool result should tell the model, so it can phrase its reply honestly.
}

/**
 * Apply one tool call: validate args -> guardrail -> mutate store. Never throws on
 * bad model output; malformed args become an IGNORE with an explanatory trace.
 */
export function applyToolCall(
  call: ToolCall,
  store: MemoryStore,
  sourceMessage: string,
): DecisionTrace {
  const name = call.function.name;
  let args: unknown;
  try {
    args = JSON.parse(call.function.arguments || "{}");
  } catch {
    return {
      decision: "IGNORE",
      toolName: name,
      detail: "malformed tool arguments (not valid JSON)",
      reason: "arguments could not be parsed",
      toolResult: "Error: tool arguments were not valid JSON; no memory change made.",
    };
  }

  if (name === "save_memory") {
    const parsed = saveSchema.safeParse(args);
    if (!parsed.success) {
      return rejectInvalid(name, parsed.error.message);
    }
    const { content, category, importance, reason } = parsed.data;

    const guard = checkWrite(content, sourceMessage);
    if (guard.blocked) {
      return {
        decision: "BLOCKED",
        toolName: name,
        detail: `blocked save "${content}"`,
        reason: guard.reason ?? "guardrail veto",
        ...(guard.rule ? { blockedRule: guard.rule } : {}),
        toolResult: `BLOCKED: not stored. Guardrail matched (${guard.rule}). Do not claim to have saved this; briefly explain you can't store it.`,
      };
    }

    const mem = store.save({
      content,
      category,
      importance: importance as 1 | 2 | 3 | 4 | 5,
      source: sourceMessage,
    });
    return {
      decision: "SAVE",
      toolName: name,
      detail: `"${content}"`,
      reason: reason || "durable fact about the user",
      memoryId: mem.id,
      importance,
      category,
      toolResult: `Saved memory ${mem.id}: "${content}".`,
    };
  }

  if (name === "update_memory") {
    const parsed = updateSchema.safeParse(args);
    if (!parsed.success) {
      return rejectInvalid(name, parsed.error.message);
    }
    const { id, new_content, reason } = parsed.data;

    const guard = checkWrite(new_content, sourceMessage);
    if (guard.blocked) {
      return {
        decision: "BLOCKED",
        toolName: name,
        detail: `blocked update of ${id}`,
        reason: guard.reason ?? "guardrail veto",
        ...(guard.rule ? { blockedRule: guard.rule } : {}),
        toolResult: `BLOCKED: not updated. Guardrail matched (${guard.rule}).`,
      };
    }

    const mem = store.update(id, new_content);
    if (!mem) {
      return {
        decision: "IGNORE",
        toolName: name,
        detail: `no active memory with id ${id}`,
        reason: "target memory not found",
        toolResult: `No active memory with id ${id}; nothing updated.`,
      };
    }
    return {
      decision: "UPDATE",
      toolName: name,
      detail: `${id} -> "${new_content}"`,
      reason: reason || "new info refines an existing memory",
      memoryId: id,
      toolResult: `Updated memory ${id} to "${new_content}".`,
    };
  }

  if (name === "delete_memory") {
    const parsed = deleteSchema.safeParse(args);
    if (!parsed.success) {
      return rejectInvalid(name, parsed.error.message);
    }
    const { id, reason } = parsed.data;
    const mem = store.delete(id);
    if (!mem) {
      return {
        decision: "IGNORE",
        toolName: name,
        detail: `no active memory with id ${id}`,
        reason: "target memory not found",
        toolResult: `No active memory with id ${id}; nothing deleted.`,
      };
    }
    return {
      decision: "DELETE",
      toolName: name,
      detail: `${id} ("${mem.content}")`,
      reason: reason || "user asked to forget, or fact expired",
      memoryId: id,
      toolResult: `Deleted memory ${id}.`,
    };
  }

  return {
    decision: "IGNORE",
    toolName: name,
    detail: `unknown tool "${name}"`,
    reason: "tool not recognized",
    toolResult: `Unknown tool ${name}; no action taken.`,
  };
}

function rejectInvalid(name: string, message: string): DecisionTrace {
  return {
    decision: "IGNORE",
    toolName: name,
    detail: "invalid tool arguments (schema validation failed)",
    reason: message,
    toolResult: `Error: tool arguments failed validation; no memory change made.`,
  };
}
