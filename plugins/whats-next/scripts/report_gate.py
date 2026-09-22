"""report_gate.py — the turn-end hook that checks how a turn ended.

The convention it enforces
--------------------------
A turn that edited files, ran commands or started processes ends with short
prose and one call of the question tool — `AskUserQuestion` in Claude Code —
offering two to four ways forward. The options render as buttons; the user's
pick arrives inside the same turn, so nothing waits for the next prompt. A
turn that only looked at things and answered ends in prose as usual. The rules
the model is given live in `output-styles/report.md`; the judgement is in
`core/decide.py`; this file is the part that talks to the agent.

What it does here
-----------------
Reads the hook's JSON from stdin, asks the host adapter for the turn, applies
the block budget, hands the turn to `core.decide`, appends a line to the index
and prints whatever the agent understands: `{"decision": "block", "reason": …}`
to send the model back, `{"systemMessage": …}` to say something to the user and
let the turn end, nothing at all to end it silently.

When it stays out of the way
----------------------------
  * the convention is switched off — `REPORT_GATE=off` in the environment, in
    a project's `.claude/settings.json` or in `~/.whats-next/config.json`.
    Having the plugin installed is otherwise the whole switch;
  * background tasks are still running, so the session is paused rather than
    finished;
  * this user prompt has already been blocked twice (REPORT_GATE_MAX_BLOCKS).
    Claude Code's own ceiling is eight consecutive blocks, which is a backstop
    rather than a plan. The ending is still written to the index, with a note
    saying it was let through.
"""

from __future__ import annotations

import datetime
import hashlib
import json
import os
import re
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    from core import checks, config, decide as decide_mod, index as index_mod
    from core import turn as turn_mod
    from hosts import from_argv
except Exception:
    sys.exit(0)  # the library is missing or broken: never disrupt a turn

STATE_DIR = os.path.join(tempfile.gettempdir(), "report_gate_state")
MAX_BLOCKS = int(os.environ.get("REPORT_GATE_MAX_BLOCKS", "2"))
POLL_ATTEMPTS = 20
POLL_INTERVAL = 0.1
DEBUG = os.environ.get("REPORT_GATE_DEBUG") or os.path.exists("/tmp/report_gate_debug.on")


def dbg(**kw) -> None:
    if not DEBUG:
        return
    try:
        with open("/tmp/report_gate_debug.log", "a", encoding="utf-8") as f:
            f.write(json.dumps(kw, default=str) + "\n")
    except OSError:
        pass


# ------------------------------------------------------------- block counting

def state_path(session_id: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9_.-]", "_", session_id or "nosession")[:64]
    return os.path.join(STATE_DIR, f"{safe}.json")


def load_state(session_id: str) -> dict:
    return config.read_json(state_path(session_id))


def save_state(session_id: str, state: dict) -> None:
    try:
        os.makedirs(STATE_DIR, exist_ok=True)
        with open(state_path(session_id), "w", encoding="utf-8") as f:
            json.dump(state, f)
    except OSError:
        pass


# ------------------------------------------------------------------ the index

def index(profile, stop, turn, kind: str, key: str, text: str,
          ask=None, problems: list[str] | None = None) -> None:
    """Add one line to the project's report index. The session record stays
    the account of what happened; this is the short form for reading back."""
    record = {
        "key": key,
        "ts": datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
        "host": profile.key,
        "session": stop.session_id,
        "cwd": stop.cwd,
        "branch": turn_mod.branch_of(turn),
        "kind": kind,
        "headline": checks.headline_of(text),
        "verification": checks.verification_of(text),
        "prose": (text or "")[:4000],
    }
    if ask is not None:
        record["questions"] = (ask.input or {}).get("questions") or []
        record["answers"] = (ask.result or {}).get("answers") or {}
    if problems:
        record["problems"] = problems
    index_mod.record_report(stop.cwd, record)


# ----------------------------------------------------------------------- main

def main() -> None:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        sys.exit(0)

    host = from_argv()
    profile = host.PROFILE
    stop = host.stop_input(payload)

    if not config.convention_enabled(host.settings_maps(stop.cwd), "REPORT_GATE"):
        dbg(action="disabled")
        sys.exit(0)

    if stop.busy:
        dbg(action="background-tasks")
        sys.exit(0)

    source = host.session_source(payload)
    if not source:
        dbg(action="no-transcript")
        sys.exit(0)

    turn: list = []
    prompt = None
    # Claude Code writes its transcript asynchronously, so the turn may not be
    # on disk yet; a host whose record this plugin keeps itself has nothing to
    # wait for and says so.
    attempts = POLL_ATTEMPTS if getattr(host, "poll_for_turn", True) else 1
    for _ in range(attempts):
        prompt, turn = turn_mod.split_turn(host.read_events(source))
        if turn:
            break
        time.sleep(POLL_INTERVAL)

    final_text = stop.final_text or turn_mod.last_text(turn)
    user_uuid = prompt.uuid if prompt is not None else ""

    state = load_state(stop.session_id)
    blocks_so_far = int(state.get("blocks") or 0) if state.get("user_uuid") == user_uuid else 0
    if stop.stop_hook_active and blocks_so_far == 0:
        blocks_so_far = 1  # state lost; assume one block has already happened
    spent = blocks_so_far >= MAX_BLOCKS

    verdict = decide_mod.decide(profile, turn, final_text)
    dbg(action=verdict.action, kind=verdict.kind, entries=len(turn),
        problems=verdict.problems, textlen=len(final_text), spent=spent)

    if verdict.action == "block" and spent:
        # The budget is there to stop a turn ending in a loop, so the ending
        # stands as it is. It still happened, so it is written down with the
        # reason it was not put right.
        digest = hashlib.sha1((user_uuid + final_text).encode("utf-8")).hexdigest()[:16]
        index(profile, stop, turn, "done", f"done:{digest}", final_text,
              problems=[f"blocked {blocks_so_far} times on this prompt; "
                        "the turn was allowed to end as it was"])
        host.emit_allow(f"report gate: {blocks_so_far} blocks on this prompt "
                        "already, letting the turn end.")
        sys.exit(0)

    if verdict.action == "block":
        save_state(stop.session_id, {"user_uuid": user_uuid, "blocks": blocks_so_far + 1})
        host.emit_block(verdict.reason)
        sys.exit(0)

    if verdict.reset_blocks:
        save_state(stop.session_id, {"user_uuid": user_uuid, "blocks": 0})

    if verdict.kind == "ask":
        records = turn_mod.find_reports(turn, profile, limit=1)
        prose = records[0].get("prose") if records else ""
        index(profile, stop, turn, "ask", verdict.ask.id or f"ask:{user_uuid}",
              prose or final_text, ask=verdict.ask,
              problems=verdict.problems + verdict.notes)
    elif verdict.kind == "done":
        digest = hashlib.sha1((user_uuid + final_text).encode("utf-8")).hexdigest()[:16]
        index(profile, stop, turn, "done", f"done:{digest}", final_text,
              problems=verdict.problems + verdict.notes)

    if verdict.problems:
        host.emit_allow("report gate: " + "; ".join(verdict.problems))
    sys.exit(0)


if __name__ == "__main__":
    main()
