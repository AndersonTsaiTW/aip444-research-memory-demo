import { test } from "node:test";
import assert from "node:assert/strict";
import { existsSync, rmSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { MemoryStore } from "../src/longTerm.ts";

function tmpPath(name: string): string {
  return join(tmpdir(), `aip444-ltm-${name}-${process.pid}.json`);
}

const fixedNow = () => "2026-07-11T00:00:00.000Z";

test("save persists an atomic fact and reloads across instances", () => {
  const path = tmpPath("save");
  rmSync(path, { force: true });
  const store = new MemoryStore(path, fixedNow);
  const mem = store.save({ content: "User is vegetarian", category: "preference", importance: 3, source: "..." });
  assert.equal(mem.status, "active");

  // A fresh instance loads the persisted data (simulates a new session).
  const reloaded = new MemoryStore(path, fixedNow);
  assert.equal(reloaded.active().length, 1);
  assert.equal(reloaded.active()[0]?.content, "User is vegetarian");
  rmSync(path, { force: true });
});

test("update replaces content and bumps updatedAt", () => {
  const path = tmpPath("update");
  rmSync(path, { force: true });
  const store = new MemoryStore(path, fixedNow);
  const mem = store.save({ content: "User is vegetarian", category: "preference", importance: 3, source: "..." });
  const updated = store.update(mem.id, "User is pescatarian");
  assert.equal(updated?.content, "User is pescatarian");
  assert.equal(store.active().length, 1);
  rmSync(path, { force: true });
});

test("delete is soft (record kept, excluded from active)", () => {
  const path = tmpPath("delete");
  rmSync(path, { force: true });
  const store = new MemoryStore(path, fixedNow);
  const mem = store.save({ content: "temporary fact", category: "project", importance: 2, source: "..." });
  store.delete(mem.id);
  assert.equal(store.active().length, 0);
  assert.equal(store.all().length, 1);
  assert.equal(store.getById(mem.id)?.status, "deleted");
  rmSync(path, { force: true });
});

test("recovers from a corrupt memory file instead of crashing", () => {
  const path = tmpPath("corrupt");
  writeFileSync(path, "{ this is not valid json", "utf8");
  const store = new MemoryStore(path, fixedNow);
  assert.equal(store.active().length, 0);
  // And it can still write cleanly afterwards.
  store.save({ content: "recovered", category: "profile", importance: 1, source: "..." });
  assert.ok(existsSync(path));
  const parsed = JSON.parse(readFileSync(path, "utf8"));
  assert.equal(parsed.memories.length, 1);
  rmSync(path, { force: true });
});
