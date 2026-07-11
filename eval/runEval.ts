// Evaluation harness. Reads every YAML case in eval/cases/, runs its turns through a
// fresh agent with an isolated memory file, and compares the resulting decision (and,
// for RECALL cases, the reply text) against the expected outcome. Emits a markdown
// results table to eval/results/ and prints a summary.
//
// Requires OPENROUTER_API_KEY Run:
//   npx tsx eval/runEval.ts            (all cases)
//   npx tsx eval/runEval.ts save.yaml  (one file)

import "dotenv/config";
import { readFileSync, readdirSync, writeFileSync, rmSync, existsSync, mkdirSync } from "node:fs";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import { parse } from "yaml";
import { LLM } from "../src/llm.ts";
import { ConversationBuffer } from "../src/shortTerm.ts";
import { MemoryStore } from "../src/longTerm.ts";
import { Agent } from "../src/agent.ts";
import type { Decision } from "../src/types.ts";

const HERE = dirname(fileURLToPath(import.meta.url));
const CASES_DIR = join(HERE, "cases");
const RESULTS_DIR = join(HERE, "results");

interface TestCase {
  id: string;
  turns: { user: string }[];
  expect: {
    decision: Decision;
    category?: string;
    min_importance?: number;
    response_contains?: string[];
  };
  rationale?: string;
}

interface CaseResult {
  id: string;
  expected: Decision;
  actual: Decision;
  pass: boolean;
  note: string;
}

function loadCases(fileFilter?: string): TestCase[] {
  const files = readdirSync(CASES_DIR).filter(
    (f) => f.endsWith(".yaml") && (!fileFilter || f === fileFilter),
  );
  const cases: TestCase[] = [];
  for (const f of files) {
    const parsed = parse(readFileSync(join(CASES_DIR, f), "utf8")) as TestCase[];
    if (Array.isArray(parsed)) cases.push(...parsed);
  }
  return cases;
}

/** Run one case in isolation and decide pass/fail. */
async function runCase(tc: TestCase, llm: LLM): Promise<CaseResult> {
  const memPath = join(RESULTS_DIR, `.tmp-${tc.id}.json`);
  if (existsSync(memPath)) rmSync(memPath);
  const stm = new ConversationBuffer();
  const ltm = new MemoryStore(memPath);
  const agent = new Agent(llm, stm, ltm);

  let lastReply = "";
  let lastDecisions: Decision[] = [];
  for (const turn of tc.turns) {
    const res = await agent.handle(turn.user);
    lastReply = res.reply;
    lastDecisions = res.traces.map((t) => t.decision);
  }
  rmSync(memPath, { force: true });

  const expected = tc.expect.decision;

  // For RECALL, the operative signal is the reply text, not a tool call.
  if (expected === "RECALL") {
    const needles = tc.expect.response_contains ?? [];
    const hit = needles.some((n) => lastReply.toLowerCase().includes(n.toLowerCase()));
    return {
      id: tc.id,
      expected,
      actual: hit ? "RECALL" : lastDecisions.includes("BLOCKED") ? "BLOCKED" : "IGNORE",
      pass: hit,
      note: hit ? `matched one of [${needles.join(", ")}]` : `reply lacked any of [${needles.join(", ")}]`,
    };
  }

  // Otherwise the actual decision is the "strongest" op on the final turn.
  const actual = strongestDecision(lastDecisions);
  return {
    id: tc.id,
    expected,
    actual,
    pass: actual === expected,
    note: actual === expected ? "ok" : `got ${actual}`,
  };
}

/** Collapse a turn's traces into one headline decision. */
function strongestDecision(decisions: Decision[]): Decision {
  const order: Decision[] = ["BLOCKED", "DELETE", "UPDATE", "SAVE", "RECALL", "IGNORE"];
  for (const d of order) if (decisions.includes(d)) return d;
  return "IGNORE";
}

function toMarkdown(results: CaseResult[]): string {
  const passed = results.filter((r) => r.pass).length;
  const rate = results.length ? ((passed / results.length) * 100).toFixed(1) : "0.0";
  const rows = results
    .map((r) => `| ${r.id} | ${r.expected} | ${r.actual} | ${r.pass ? "✅" : "❌"} | ${r.note} |`)
    .join("\n");
  return [
    `# Evaluation results`,
    ``,
    `**Pass rate: ${passed}/${results.length} (${rate}%)**`,
    ``,
    `| Case | Expected | Actual | Pass | Note |`,
    `|---|---|---|---|---|`,
    rows,
    ``,
  ].join("\n");
}

async function main(): Promise<void> {
  const fileFilter = process.argv[2];
  const cases = loadCases(fileFilter);
  if (cases.length === 0) {
    console.log("No test cases found.");
    return;
  }
  if (!existsSync(RESULTS_DIR)) mkdirSync(RESULTS_DIR, { recursive: true });

  const llm = new LLM();
  const results: CaseResult[] = [];
  for (const tc of cases) {
    process.stdout.write(`  ${tc.id} ... `);
    try {
      const r = await runCase(tc, llm);
      results.push(r);
      console.log(r.pass ? "PASS" : `FAIL (${r.actual})`);
    } catch (err) {
      results.push({
        id: tc.id,
        expected: tc.expect.decision,
        actual: "IGNORE",
        pass: false,
        note: `error: ${err instanceof Error ? err.message : String(err)}`,
      });
      console.log("ERROR");
    }
  }

  const md = toMarkdown(results);
  const outPath = join(RESULTS_DIR, "results.md");
  writeFileSync(outPath, md, "utf8");
  console.log(`\n${md}`);
  console.log(`Written to ${outPath}`);
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
