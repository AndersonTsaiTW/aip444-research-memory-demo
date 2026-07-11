import { test } from "node:test";
import assert from "node:assert/strict";
import { ConversationBuffer, estimateTokens } from "../src/shortTerm.ts";

test("estimateTokens grows with text length", () => {
  assert.ok(estimateTokens("hello world") > 0);
  assert.ok(estimateTokens("a".repeat(400)) > estimateTokens("a".repeat(40)));
});

test("pressure rises as messages accumulate", () => {
  const buf = new ConversationBuffer(1000);
  assert.equal(buf.pressure(), 0);
  buf.add({ role: "user", content: "x".repeat(2000) }); // ~500 tokens
  assert.ok(buf.pressure() > 0);
  assert.ok(buf.isOverCap() === false || buf.tokenCount() > 1000);
});

test("isOverCap trips once the budget is exceeded", () => {
  const buf = new ConversationBuffer(100);
  assert.equal(buf.isOverCap(), false);
  buf.add({ role: "user", content: "y".repeat(1000) }); // ~250 tokens > 100
  assert.equal(buf.isOverCap(), true);
});
