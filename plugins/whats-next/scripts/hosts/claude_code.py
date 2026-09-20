"""hosts/claude_code.py — the Claude Code adapter.

Everything here is true of Claude Code and of nothing else: where it keeps
session transcripts and what they look like inside, which of its tools change
things, where its settings live, and the JSON its hooks are handed and may
print. The rules that use all this are in `core/`.

The transcript is `~/.claude/projects/<sanitised-cwd>/<session-id>.jsonl`, one
JSON object per line. The objects that matter:

  {"type": "user", "message": {"content": "what the user typed"}}
  {"type": "user", "isMeta": true, "message": {"content": "Stop hook feedback: …"}}
  {"type": "assistant", "message": {"content": [{"type": "text", …},
                                                {"type": "tool_use", "name": "Edit", …}]}}
  {"type": "user", "message": {"content": [{"type": "tool_result", …}]},
   "toolUseResult": {"questions": […], "answers": {"<question>": "<label>"}}}

Subagent traffic is written into the same file with `isSidechain: true` and is
skipped, because a Stop hook fires for the main agent only. The file is
written asynchronously, so the closing text of the turn may not be in it when
the Stop hook runs; the hook takes that from `last_assistant_message` in its
own input instead.
"""

from __future__ import annotations

import glob
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.config import read_json                      # noqa: E402
from core.hook import StopInput                        # noqa: E402
from core.profile import AskLimits, HostProfile        # noqa: E402
from core.turn import Event, ToolResult, ToolUse       # noqa: E402

PROFILE = HostProfile(
    key="claude-code",
    display="Claude Code",
    ask_tool="AskUserQuestion",
    write_tools=frozenset({"Write", "Edit", "MultiEdit", "NotebookEdit",
                           "ArtifactData"}),
    shell_tools=frozenset({"Bash", "PowerShell"}),
    ask=AskLimits(max_questions=4, min_options=2, max_options=4, header_max=12),
)

STYLE_NAMES = {"report", "structuredreport"}


# ------------------------------------------------------------------ settings

def settings_files(cwd: str):
    """Every settings file that applies to a directory, nearest first: the two
    Claude Code reads beside each project, walking up from the working
    directory, and the user's own at the end."""
    here = os.path.abspath(cwd or os.getcwd())
    while True:
        for name in ("settings.local.json", "settings.json"):
            yield os.path.join(here, ".claude", name)
        parent = os.path.dirname(here)
        if parent == here:
            break
        here = parent
    yield os.path.expanduser("~/.claude/settings.json")


def settings_maps(cwd: str):
    for path in settings_files(cwd):
        yield read_json(path)


def active_output_style(cwd: str) -> str:
    """The output style in force for a directory, or "" when none is named.
    `/output-style` writes the choice to `.claude/settings.local.json` beside
    the project, so the nearest answer wins."""
    for settings in settings_maps(cwd):
        style = settings.get("outputStyle")
        if isinstance(style, str) and style.strip():
            return style
    return ""


def suppressed(cwd: str) -> bool:
    """True when Claude Code is already sending the convention itself, which
    happens when this plugin's own output style is the active one. It may
    arrive as "report", "Structured report", or namespaced by a plugin."""
    style = active_output_style(cwd).lower()
    if re.sub(r"[^a-z]", "", style) in STYLE_NAMES:
        return True
    return "report" in re.split(r"[^a-z]+", style)


# --------------------------------------------------------------- transcripts

def project_dir(cwd: str) -> str:
    """Where Claude Code keeps this directory's transcripts. The folder name is
    the path with every character that is not a letter or a digit replaced by a
    dash: `/home/you/project` becomes `-home-you-project`, and
    `D:\\projects\\foo` becomes `D--projects-foo`."""
    sanitized = re.sub(r"[^A-Za-z0-9]", "-", os.path.abspath(cwd))
    return os.path.expanduser(f"~/.claude/projects/{sanitized}")


def newest_transcript(cwd: str) -> str | None:
    files = glob.glob(os.path.join(project_dir(cwd), "*.jsonl"))
    return max(files, key=os.path.getmtime) if files else None


def transcript_for_session(cwd: str, session_id: str) -> str | None:
    """The transcript whose file name is this session id, searching the
    working directory's project folder first and every other one after."""
    if not session_id or not re.fullmatch(r"[A-Za-z0-9-]{6,64}", session_id):
        return None
    candidate = os.path.join(project_dir(cwd), f"{session_id}.jsonl")
    if os.path.isfile(candidate):
        return candidate
    hits = glob.glob(os.path.expanduser(f"~/.claude/projects/*/{session_id}.jsonl"))
    return hits[0] if hits else None


def find_transcript(payload: dict) -> str | None:
    """Path to the transcript for this session, or the newest one for the
    working directory when the payload does not name it."""
    path = payload.get("transcript_path")
    if path:
        path = os.path.expanduser(path)
        if os.path.isfile(path):
            return path
    return newest_transcript(payload.get("cwd") or os.getcwd())


# ------------------------------------------------------- transcript to events

def _blocks(entry: dict) -> list[dict]:
    content = (entry.get("message") or {}).get("content")
    return [b for b in content if isinstance(b, dict)] if isinstance(content, list) else []


def _is_prompt(entry: dict) -> bool:
    """True for something the user actually sent, as opposed to a tool result
    or the note Claude Code writes when a hook blocks a stop."""
    if entry.get("type") != "user" or entry.get("isMeta"):
        return False
    content = (entry.get("message") or {}).get("content")
    if isinstance(content, str):
        return bool(content.strip())
    if isinstance(content, list):
        kinds = {b.get("type") for b in content if isinstance(b, dict)}
        return "text" in kinds and "tool_result" not in kinds
    return False


def _event(entry: dict) -> Event:
    blocks = _blocks(entry)
    content = (entry.get("message") or {}).get("content")
    text = content if isinstance(content, str) else "\n".join(
        b.get("text") or "" for b in blocks if b.get("type") == "text")
    payload = entry.get("toolUseResult")
    payload = payload if isinstance(payload, dict) else None
    return Event(
        role=entry.get("type") or "",
        is_prompt=_is_prompt(entry),
        text=(text or "").strip(),
        tool_uses=[ToolUse(b.get("id") or "", b.get("name") or "", b.get("input") or {})
                   for b in blocks if b.get("type") == "tool_use"],
        tool_results=[ToolResult(b.get("tool_use_id") or "", bool(b.get("is_error")),
                                 payload)
                      for b in blocks if b.get("type") == "tool_result"],
        uuid=entry.get("uuid") or "",
        timestamp=entry.get("timestamp") or "",
        branch=entry.get("gitBranch") or "",
    )


def read_events(path: str) -> list[Event]:
    out: list[Event] = []
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except ValueError:
                    continue
                if isinstance(entry, dict) and not entry.get("isSidechain"):
                    out.append(_event(entry))
    except OSError:
        return []
    return out


# ------------------------------------------------------------ hooks in and out

def stop_input(payload: dict) -> StopInput:
    final = payload.get("last_assistant_message")
    return StopInput(
        cwd=payload.get("cwd") or os.getcwd(),
        session_id=str(payload.get("session_id") or "nosession"),
        final_text=final if isinstance(final, str) else "",
        stop_hook_active=bool(payload.get("stop_hook_active")),
        busy=bool(payload.get("background_tasks")),
    )


def emit_block(reason: str) -> None:
    print(json.dumps({"decision": "block", "reason": reason}))


def emit_allow(system_message: str = "") -> None:
    if system_message:
        print(json.dumps({"systemMessage": system_message}))


def emit_context(text: str) -> None:
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "SessionStart", "additionalContext": text}}))


# The turn-end hook asks the adapter for a session record by this name.
session_source = find_transcript
