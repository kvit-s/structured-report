"""core/journal.py — keeping a turn when the agent does not write one down.

Claude Code writes every session to a transcript this plugin can read back.
Gemini CLI does not: its hooks are handed a `transcript_path`, but the field
is stubbed and arrives empty, so a turn-end hook there has no record of what
the turn did. The way round it is to keep one: a tool hook appends a line per
prompt and per tool call, and the turn-end hook reads the lines back.

One file per session, under `~/.whats-next/sessions/<project>/<session>.jsonl`,
holding the same `Event` objects a transcript adapter produces, so everything
in `core/` works the same either way. The files are small — a few hundred bytes
per tool call, with tool inputs trimmed — and anything a fortnight old is
removed when a new session starts writing.
"""

from __future__ import annotations

import json
import os
import re
import time

from .turn import Event, ToolResult, ToolUse

KEEP_DAYS = 14
MAX_INPUT_CHARS = 20000


def project_key(cwd: str) -> str:
    return re.sub(r"[^A-Za-z0-9]", "-", os.path.abspath(cwd or ".")).strip("-")


def session_dir(cwd: str) -> str:
    return os.path.expanduser(f"~/.whats-next/sessions/{project_key(cwd)}")


def journal_path(cwd: str, session_id: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9_.-]", "_", session_id or "nosession")[:64]
    return os.path.join(session_dir(cwd), f"{safe}.jsonl")


def newest_journal(cwd: str) -> str | None:
    try:
        files = [os.path.join(session_dir(cwd), n)
                 for n in os.listdir(session_dir(cwd)) if n.endswith(".jsonl")]
    except OSError:
        return None
    return max(files, key=os.path.getmtime) if files else None


def _trim(value):
    """Tool inputs can hold a whole file. The rules only read the command of a
    shell call and the questions of a card, so anything longer than this is
    cut: the journal stays small and no file contents are copied into it."""
    text = json.dumps(value, default=str)
    if len(text) <= MAX_INPUT_CHARS:
        return value
    return {"_trimmed": len(text)}


def to_json(event: Event) -> dict:
    return {
        "role": event.role,
        "is_prompt": event.is_prompt,
        "text": event.text,
        "uses": [{"id": u.id, "name": u.name, "input": _trim(u.input)}
                 for u in event.tool_uses],
        "results": [{"id": r.id, "is_error": r.is_error, "payload": _trim(r.payload)}
                    for r in event.tool_results],
        "uuid": event.uuid,
        "timestamp": event.timestamp,
        "branch": event.branch,
    }


def from_json(raw: dict) -> Event:
    return Event(
        role=raw.get("role") or "",
        is_prompt=bool(raw.get("is_prompt")),
        text=raw.get("text") or "",
        tool_uses=[ToolUse(u.get("id") or "", u.get("name") or "", u.get("input") or {})
                   for u in raw.get("uses") or [] if isinstance(u, dict)],
        tool_results=[ToolResult(r.get("id") or "", bool(r.get("is_error")),
                                 r.get("payload") if isinstance(r.get("payload"), dict) else None)
                      for r in raw.get("results") or [] if isinstance(r, dict)],
        uuid=raw.get("uuid") or "",
        timestamp=raw.get("timestamp") or "",
        branch=raw.get("branch") or "",
    )


def append(cwd: str, session_id: str, event: Event) -> None:
    path = journal_path(cwd, session_id)
    fresh = not os.path.exists(path)
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(to_json(event), default=str) + "\n")
    except OSError:
        return
    if fresh:
        sweep(cwd)


def read(path: str) -> list[Event]:
    out: list[Event] = []
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    raw = json.loads(line)
                except ValueError:
                    continue
                if isinstance(raw, dict):
                    out.append(from_json(raw))
    except OSError:
        return []
    return out


def sweep(cwd: str, keep_days: int = KEEP_DAYS) -> None:
    """Remove journals nothing will read again. Runs when a session starts its
    own file, so the cost falls once per session rather than once per turn."""
    cutoff = time.time() - keep_days * 86400
    try:
        for name in os.listdir(session_dir(cwd)):
            path = os.path.join(session_dir(cwd), name)
            try:
                if os.path.getmtime(path) < cutoff:
                    os.remove(path)
            except OSError:
                continue
    except OSError:
        return
