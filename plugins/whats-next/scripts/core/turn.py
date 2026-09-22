"""core/turn.py — one turn of a session, in a shape no agent owns.

Every agent records a session differently. Claude Code writes a JSON object
per line under `~/.claude/projects/`; Codex writes rollout files under
`~/.codex/sessions/`; OpenCode keeps messages and parts of its own and hands
them back through an SDK. A host adapter's job is to read whichever of those
it is looking at and produce a list of `Event` objects, oldest first. From
there the rules are the same everywhere.

An event is one entry in the record: something the user sent, or something the
agent said, with any tool calls it made and any results that came back. The
turn is everything after the last event the user actually typed — hook
feedback and system notes are not that, and neither is a tool result.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ToolUse:
    id: str
    name: str
    input: dict = field(default_factory=dict)


@dataclass
class ToolResult:
    id: str
    is_error: bool = False
    payload: dict | None = None   # whatever the host records about the result


@dataclass
class Event:
    role: str = ""                # "user" or "assistant"
    is_prompt: bool = False       # something the user typed, not a tool result
    text: str = ""
    tool_uses: list[ToolUse] = field(default_factory=list)
    tool_results: list[ToolResult] = field(default_factory=list)
    uuid: str = ""
    timestamp: str = ""
    branch: str = ""


class ToolCall:
    """One tool call in a turn, with whatever came back for it."""

    def __init__(self, pos: int, name: str, inp: Any, call_id: str):
        self.pos = pos
        self.name = name
        self.input = inp if isinstance(inp, dict) else {}
        self.id = call_id
        self.is_error = False
        self.result: dict | None = None
        self.answered = False

    def __repr__(self) -> str:  # debugging only
        return f"<ToolCall {self.pos} {self.name} answered={self.answered}>"


def split_turn(events: list[Event]) -> tuple[Event | None, list[Event]]:
    """(the last thing the user typed, everything after it)."""
    last = -1
    for i, event in enumerate(events):
        if event.is_prompt:
            last = i
    if last < 0:
        return None, events
    return events[last], events[last + 1:]


def tool_calls(turn: list[Event]) -> list[ToolCall]:
    """Every tool call of the turn, in order, each carrying its result."""
    calls: list[ToolCall] = []
    by_id: dict[str, ToolCall] = {}
    for pos, event in enumerate(turn):
        for use in event.tool_uses:
            call = ToolCall(pos, use.name, use.input, use.id)
            calls.append(call)
            if call.id:
                by_id[call.id] = call
        for result in event.tool_results:
            call = by_id.get(result.id)
            if call is None:
                continue
            call.answered = True
            call.is_error = result.is_error
            if isinstance(result.payload, dict):
                call.result = result.payload
    return calls


def last_text(turn: list[Event]) -> str:
    """The closing prose of the turn, as far as the record goes."""
    for event in reversed(turn):
        if event.role == "assistant" and event.text.strip():
            return event.text.strip()
    return ""


def branch_of(turn: list[Event]) -> str:
    for event in reversed(turn):
        if event.branch:
            return event.branch
    return ""


def find_reports(events: list[Event], ask_tool, limit: int = 1) -> list[dict]:
    """The most recent calls of the question tool, newest first. Each item
    holds the call's input, the answers the user gave, the prose that preceded
    it and when it happened — which is all `/report` needs to draw the card
    again, without anything having been written down a second time.

    `ask_tool` is the tool's name, or a host profile when the name has
    alternatives."""
    matches = getattr(ask_tool, "is_ask", None) or (lambda name: name == ask_tool)
    out: list[dict] = []
    pending: dict[str, dict] = {}
    recent_text = ""
    for event in events:
        if event.role == "assistant":
            text = event.text.strip()
            for use in event.tool_uses:
                if not matches(use.name):
                    continue
                pending[use.id] = {
                    "input": use.input or {},
                    "prose": text or recent_text,
                    "when": event.timestamp,
                    "answers": None,
                }
            if text:
                recent_text = text
        for result in event.tool_results:
            record = pending.pop(result.id, None)
            if record is None:
                continue
            if isinstance(result.payload, dict):
                record["answers"] = result.payload.get("answers")
            out.append(record)
    out.extend(pending.values())
    return list(reversed(out))[:limit]
