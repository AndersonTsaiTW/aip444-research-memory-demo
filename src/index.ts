// CLI entry point. Subcommands:
//   chat      interactive dual-memory chat (default)
//   memories  list current long-term memories
//   reset     wipe long-term memory
//
// Run with: npx tsx src/index.ts chat

import "dotenv/config";
import { createInterface } from "node:readline/promises";
import { stdin, stdout } from "node:process";
import { LLM } from "./llm.ts";
import { ConversationBuffer } from "./shortTerm.ts";
import { MemoryStore } from "./longTerm.ts";
import { Agent } from "./agent.ts";
import type { DecisionTrace } from "./decision.ts";

const MEMORY_PATH = process.env["MEMORY_PATH"] ?? "memory.json";

function printTrace(t: DecisionTrace): void {
  if (t.decision === "IGNORE" && t.toolName === "-") {
    console.log(`  [MEMORY] IGNORE   — ${t.reason}`);
    return;
  }
  if (t.decision === "BLOCKED") {
    console.log(`  [MEMORY] BLOCKED ${t.toolName} — matched rule: ${t.blockedRule} (${t.reason})`);
    return;
  }
  const tag =
    t.decision === "SAVE"
      ? `SAVE   (imp=${t.importance}, ${t.category})`
      : t.decision.padEnd(6);
  console.log(`  [MEMORY] ${tag} ${t.detail} — reason: ${t.reason}`);
}

function listMemories(store: MemoryStore): void {
  const active = store.active();
  if (active.length === 0) {
    console.log("(no long-term memories stored)");
    return;
  }
  console.log(`Long-term memories (${active.length}):`);
  for (const m of active) {
    console.log(
      `  [${m.id}] (${m.category}, imp=${m.importance}) ${m.content}  ` +
        `— updated ${m.updatedAt.slice(0, 10)}`,
    );
  }
}

async function runChat(): Promise<void> {
  const llm = new LLM();
  const stm = new ConversationBuffer();
  const ltm = new MemoryStore(MEMORY_PATH);
  const agent = new Agent(llm, stm, ltm);

  console.log("Dual-memory chatbot. Type your message, or /memories, /reset, /exit.\n");
  const rl = createInterface({ input: stdin, output: stdout });

  while (true) {
    const line = (await rl.question("you> ")).trim();
    if (line === "") continue;
    if (line === "/exit" || line === "/quit") break;
    if (line === "/memories") {
      listMemories(ltm);
      continue;
    }
    if (line === "/reset") {
      ltm.reset();
      console.log("(long-term memory wiped)");
      continue;
    }

    try {
      const { reply, traces, summarized } = await agent.handle(line);
      for (const t of traces) printTrace(t);
      if (summarized) {
        console.log("  [STM] context over cap — oldest half summarized");
      }
      console.log(`  [STM] buffer at ${stm.pressure()}% (${stm.tokenCount()}/${stm.maxTokens} tokens)`);
      console.log(`bot> ${reply}\n`);
    } catch (err) {
      console.error("Error:", err instanceof Error ? err.message : err);
    }
  }
  rl.close();
}

async function main(): Promise<void> {
  const cmd = process.argv[2] ?? "chat";
  switch (cmd) {
    case "chat":
      await runChat();
      break;
    case "memories":
      listMemories(new MemoryStore(MEMORY_PATH));
      break;
    case "reset":
      new MemoryStore(MEMORY_PATH).reset();
      console.log("(long-term memory wiped)");
      break;
    default:
      console.log(`Unknown command "${cmd}". Use: chat | memories | reset`);
      process.exit(1);
  }
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
