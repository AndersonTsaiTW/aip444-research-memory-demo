// Long-term memory (LTM): a JSON-file key-value store of atomic facts.
// Writes use a write-temp-then-rename pattern so the file is never left half-written
// if the process crashes mid-save (the guarantee we lose by not using a real DB).

import { readFileSync, writeFileSync, renameSync, existsSync } from "node:fs";
import { randomUUID } from "node:crypto";
import type { Memory, MemoryCategory, MemoryFile } from "./types.ts";

const DEFAULT_PATH = "memory.json";

export interface NewMemoryInput {
  content: string;
  category: MemoryCategory;
  importance: 1 | 2 | 3 | 4 | 5;
  source: string;
}

export class MemoryStore {
  private path: string;
  private memories: Memory[];
  //Injectable clock so tests are deterministic, defaults to real time
  private now: () => string;

  constructor(path: string = DEFAULT_PATH, now: () => string = () => new Date().toISOString()) {
    this.path = path;
    this.now = now;
    this.memories = this.load();
  }

  private load(): Memory[] {
    if (!existsSync(this.path)) return [];
    try {
      const raw = readFileSync(this.path, "utf8");
      const parsed = JSON.parse(raw) as MemoryFile;
      return Array.isArray(parsed.memories) ? parsed.memories : [];
    } catch {
      // Corrupt/unreadable file: start empty rather than crash the demo.
      return [];
    }
  }

  // Atomic persist: write to a temp file, then rename over the real file
  private persist(): void {
    const data: MemoryFile = { memories: this.memories };
    const json = JSON.stringify(data, null, 2);
    const tmp = `${this.path}.tmp`;
    writeFileSync(tmp, json, "utf8");
    renameSync(tmp, this.path);
  }

  // All memories including soft-deleted ones (audit view)
  all(): Memory[] {
    return this.memories;
  }

  //Only the active (non-deleted) memories — what gets recalled into the prompt
  active(): Memory[] {
    return this.memories.filter((m) => m.status === "active");
  }

  getById(id: string): Memory | undefined {
    return this.memories.find((m) => m.id === id);
  }

  save(input: NewMemoryInput): Memory {
    const ts = this.now();
    const memory: Memory = {
      id: randomUUID().slice(0, 8),
      content: input.content,
      category: input.category,
      importance: input.importance,
      createdAt: ts,
      updatedAt: ts,
      source: input.source,
      status: "active",
    };
    this.memories.push(memory);
    this.persist();
    return memory;
  }

  // Replace the content of an existing active memory. Returns the updated memory or undefined. 
  update(id: string, newContent: string): Memory | undefined {
    const memory = this.memories.find((m) => m.id === id && m.status === "active");
    if (!memory) return undefined;
    memory.content = newContent;
    memory.updatedAt = this.now();
    this.persist();
    return memory;
  }

  // Soft-delete: mark deleted but keep the record for the audit trail
  delete(id: string): Memory | undefined {
    const memory = this.memories.find((m) => m.id === id && m.status === "active");
    if (!memory) return undefined;
    memory.status = "deleted";
    memory.updatedAt = this.now();
    this.persist();
    return memory;
  }

  // Wipe all memories (used by the `reset` CLI subcommand). 
  reset(): void {
    this.memories = [];
    this.persist();
  }
}
