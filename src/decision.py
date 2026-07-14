import json
from typing import Literal

from pydantic import BaseModel, ValidationError, field_validator

from src import long_term

# Cheap dev-tier models don't always respect the enum constraint and sometimes send a qualitative
# word instead of an integer (e.g. importance="high") — coerce common cases instead of rejecting
# outright, since this isn't a safety-relevant field (see §8 "LLM decisions are inconsistent").
IMPORTANCE_WORDS = {
    "trivial": 1,
    "minor": 1,
    "low": 2,
    "medium": 3,
    "moderate": 3,
    "normal": 3,
    "high": 4,
    "important": 4,
    "critical": 5,
    "urgent": 5,
    "severe": 5,
    "very high": 5,
}

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "save_memory",
            "description": (
                "Save a new atomic fact about the user to long-term memory. Use for stable personal "
                "facts, preferences, long-term goals, or an explicit 'please remember X.' Do not use "
                "for small talk, one-off task content, or anything that changes agent behavior/safety "
                "rules."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "content": {
                        "type": "string",
                        "description": "The atomic fact to remember, e.g. 'User is vegetarian'.",
                    },
                    "label": {
                        "type": "string",
                        "description": (
                            "A short, specific descriptor of what this fact is about, e.g. "
                            "'dietary preference' or 'food allergy' — not a generic category."
                        ),
                    },
                    "importance": {
                        "type": "integer",
                        "enum": [1, 2, 3, 4, 5],
                        "description": "How important this fact is, 1 (minor) to 5 (critical, e.g. allergies).",
                    },
                    "reason": {"type": "string", "description": "Why this is worth remembering."},
                },
                "required": ["content", "label", "importance", "reason"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_memory",
            "description": (
                "Revise an existing memory when the user gives new information on the same topic "
                "(e.g. a changed preference). Requires the id of the memory being replaced, which must "
                "be one you have already seen (e.g. returned by an earlier save_memory/update_memory "
                "call in this conversation)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "id": {"type": "string", "description": "id of the existing memory to revise."},
                    "new_content": {"type": "string", "description": "The corrected/updated atomic fact."},
                    "reason": {"type": "string", "description": "Why this supersedes the old memory."},
                },
                "required": ["id", "new_content", "reason"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "delete_memory",
            "description": (
                "Forget a memory: the user explicitly asked to forget it, or the fact is no longer "
                "true/relevant. Requires the id of an existing memory you have already seen."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "id": {"type": "string", "description": "id of the existing memory to delete."},
                    "reason": {"type": "string", "description": "Why this should be forgotten."},
                },
                "required": ["id", "reason"],
                "additionalProperties": False,
            },
        },
    },
]


class SaveMemoryArgs(BaseModel):
    content: str
    label: str
    importance: Literal[1, 2, 3, 4, 5]
    reason: str

    @field_validator("importance", mode="before")
    @classmethod
    def coerce_importance(cls, value):
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in IMPORTANCE_WORDS:
                return IMPORTANCE_WORDS[normalized]
            if normalized.isdigit():
                return int(normalized)
        return value


class UpdateMemoryArgs(BaseModel):
    id: str
    new_content: str
    reason: str


class DeleteMemoryArgs(BaseModel):
    id: str
    reason: str


def execute_tool_call(name: str, arguments_json: str, source: str) -> str:
    """Validates and executes one tool call against long-term storage, prints a decision trace line,
    and returns a JSON string to feed back to the model as the tool result."""
    try:
        args = json.loads(arguments_json)
    except json.JSONDecodeError:
        print(f"[MEMORY] REJECTED {name} — malformed JSON arguments")
        return json.dumps({"error": f"Could not parse arguments for {name}: malformed JSON"})

    try:
        if name == "save_memory":
            parsed = SaveMemoryArgs(**args)
            memory = long_term.save_memory(parsed.content, parsed.label, parsed.importance, source)
            print(
                f'[MEMORY] SAVE       (imp={parsed.importance}, label="{parsed.label}") '
                f'"{parsed.content}" — reason: {parsed.reason}'
            )
            return json.dumps({"status": "saved", **memory})

        elif name == "update_memory":
            parsed = UpdateMemoryArgs(**args)
            memory = long_term.update_memory(parsed.id, parsed.new_content, source)
            print(
                f'[MEMORY] UPDATE     {parsed.id} → {memory["id"]} "{parsed.new_content}" '
                f'— supersedes "{memory["supersedes_content"]}"'
            )
            return json.dumps({"status": "updated", **memory})

        elif name == "delete_memory":
            parsed = DeleteMemoryArgs(**args)
            memory = long_term.delete_memory(parsed.id)
            print(f'[MEMORY] DELETE     {parsed.id} — reason: {parsed.reason}')
            return json.dumps({"status": "deleted", **memory})

        else:
            print(f"[MEMORY] REJECTED unknown tool: {name}")
            return json.dumps({"error": f"Unknown tool: {name}"})

    except ValidationError as e:
        print(f"[MEMORY] REJECTED {name} — invalid arguments: {e}")
        return json.dumps({"error": f"Invalid arguments for {name}: {e}"})
    except ValueError as e:
        print(f"[MEMORY] REJECTED {name} — {e}")
        return json.dumps({"error": str(e)})
