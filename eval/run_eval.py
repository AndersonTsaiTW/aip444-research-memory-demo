"""Replays eval/cases/*.yaml through the real agent (real LLM, real Chroma, no mocks) and reports
pass/fail per case, per §7. Each case gets a fresh, isolated memory store so cases can't contaminate
each other. Usage: python -m eval.run_eval
"""

import io
import re
import sys
import tempfile
from contextlib import redirect_stdout
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src import decision, long_term  # noqa: E402
from src.agent import get_reply  # noqa: E402
from src.short_term import ConversationBuffer  # noqa: E402

CASES_DIR = Path(__file__).resolve().parent / "cases"
RESULTS_DIR = Path(__file__).resolve().parent / "results"

TRACE_PATTERN = re.compile(r"^\[MEMORY]\s+(\w+)\s*(.*)$")


def _reset_memory_store() -> None:
    """Fresh, isolated Chroma store per case (§7) — a temp dir, real embedding function."""
    long_term._default_store = long_term.MemoryStore(path=tempfile.mkdtemp(), collection_name="eval")


def _parse_trace_line(line: str) -> dict:
    match = TRACE_PATTERN.match(line)
    if not match:
        return {"decision": None, "label": None, "importance": None, "raw": line}
    decision_label, rest = match.groups()
    label_match = re.search(r'label="([^"]*)"', rest)
    imp_match = re.search(r"imp=(\d+)", rest)
    return {
        "decision": decision_label,
        "label": label_match.group(1) if label_match else None,
        "importance": int(imp_match.group(1)) if imp_match else None,
        "raw": line,
    }


def _run_turns(turns: list[dict]) -> tuple[str, list[dict]]:
    """Replays every turn through the real agent (get_reply — same function main.py's chat loop
    uses). Only the last turn's trace lines/reply are graded; earlier turns are setup context."""
    buffer = ConversationBuffer()
    reply = ""
    last_turn_trace: list[dict] = []

    for turn in turns:
        user_msg = turn["user"]
        buffer.add("user", user_msg)
        captured = io.StringIO()
        with redirect_stdout(captured):
            reply, new_messages = get_reply(buffer.messages, source=user_msg)
        buffer.extend(new_messages)
        last_turn_trace = [
            _parse_trace_line(line) for line in captured.getvalue().splitlines() if line.startswith("[MEMORY]")
        ]

    return reply, last_turn_trace


def _run_direct_tool_call(spec: dict) -> tuple[str, list[dict]]:
    """Bypasses the LLM entirely and calls decision.execute_tool_call directly with a crafted
    payload — for cases that need to prove the write-time guardrail itself works, independent of
    whether a given model would actually attempt the write (see §4.5 Implementation notes)."""
    import json

    captured = io.StringIO()
    with redirect_stdout(captured):
        decision.execute_tool_call(spec["name"], json.dumps(spec["args"]), source="eval")
    trace = [_parse_trace_line(line) for line in captured.getvalue().splitlines() if line.startswith("[MEMORY]")]
    return "", trace


def _expected_decisions(expect: dict) -> list[str] | None:
    if "decision" not in expect:
        return None
    wanted = expect["decision"]
    return wanted if isinstance(wanted, list) else [wanted]


def _grade_case(case: dict, reply: str, trace: list[dict]) -> tuple[bool, str]:
    expect = case.get("expect", {})
    non_recall = [t for t in trace if t["decision"] and t["decision"] != "RECALL"]
    recall_lines = [t for t in trace if t["decision"] == "RECALL"]

    wanted_decisions = _expected_decisions(expect)
    if wanted_decisions is not None:
        actual_decisions = [t["decision"] for t in non_recall] or ["IGNORE"]
        if not any(d in wanted_decisions for d in actual_decisions):
            return False, f"expected decision in {wanted_decisions}, got {actual_decisions}"

    if "label_contains" in expect:
        wanted = expect["label_contains"].lower()
        if not any(t["label"] and wanted in t["label"].lower() for t in non_recall):
            return False, f"no decision's label contained '{wanted}'"

    if "min_importance" in expect:
        wanted = expect["min_importance"]
        if not any(t["importance"] is not None and t["importance"] >= wanted for t in non_recall):
            return False, f"no decision met min_importance={wanted}"

    if "recall_empty" in expect:
        is_empty = any(
            "no relevant memory" in t["raw"] or "no memories stored" in t["raw"] for t in recall_lines
        )
        if bool(expect["recall_empty"]) != is_empty:
            return False, f"expected recall_empty={expect['recall_empty']}, got {is_empty}"

    if "response_contains" in expect:
        for substring in expect["response_contains"]:
            if substring.lower() not in (reply or "").lower():
                return False, f"reply did not contain '{substring}'"

    return True, "ok"


def run_all_cases(cases_dir: Path = CASES_DIR) -> list[dict]:
    results = []
    for yaml_file in sorted(cases_dir.glob("*.yaml")):
        cases = yaml.safe_load(yaml_file.read_text(encoding="utf-8")) or []
        for case in cases:
            _reset_memory_store()
            if "direct_tool_call" in case:
                reply, trace = _run_direct_tool_call(case["direct_tool_call"])
            else:
                reply, trace = _run_turns(case["turns"])
            passed, detail = _grade_case(case, reply, trace)
            results.append(
                {
                    "file": yaml_file.name,
                    "id": case["id"],
                    "expect": case.get("expect", {}),
                    "passed": passed,
                    "detail": detail,
                }
            )
    return results


def format_results_table(results: list[dict]) -> str:
    lines = ["| Case | Expected | Pass | Detail |", "|---|---|---|---|"]
    for r in results:
        status = "PASS" if r["passed"] else "FAIL"
        lines.append(f"| {r['id']} | `{r['expect']}` | {status} | {r['detail']} |")
    total = len(results)
    passed = sum(1 for r in results if r["passed"])
    lines.append("")
    lines.append(f"**{passed}/{total} passed**")
    return "\n".join(lines)


def main() -> None:
    results = run_all_cases()
    table = format_results_table(results)
    print(table)

    RESULTS_DIR.mkdir(exist_ok=True)
    (RESULTS_DIR / "latest.md").write_text(table, encoding="utf-8")

    if any(not r["passed"] for r in results):
        sys.exit(1)


if __name__ == "__main__":
    main()
