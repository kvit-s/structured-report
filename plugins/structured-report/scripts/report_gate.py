"""report_gate.py — Stop hook that checks how a turn ended.

The convention it enforces
--------------------------
A turn that edited files, ran commands or started processes ends with short
prose and one `AskUserQuestion` call offering two to four ways forward. The
options render as buttons; the user's pick arrives inside the same turn, so
nothing waits for the next prompt. A turn that only looked at things and
answered ends in prose as usual. The rules the model is given live in the
`report` output style, which is installed beside this script; this script is
the part that checks them.

When it blocks
--------------
Three cases, and every problem found is reported at once so one pass fixes all
of them:

  * the turn changed something, offered nothing, and did not say why there is
    no follow-up;
  * the closing text asks the user to choose but no AskUserQuestion call was
    made, so there is nothing to click;
  * an AskUserQuestion call came back as an error, meaning the card never
    appeared.

Problems with a call that did work — a header too long for the card, an option
with no description, no way to stop — are not worth a second round trip,
because the user already answered the one they saw. Those are printed as a
`systemMessage`, which reaches the user and ends the turn.

When it stays out of the way
----------------------------
  * the convention is switched off, either with `REPORT_GATE=off` in the
    environment or with an `env` block saying the same in a project's
    `.claude/settings.json`. Having the plugin installed is otherwise the
    whole switch: uninstall it and this stops running;
  * background tasks are still running, so the session is paused rather than
    finished;
  * this user prompt has already been blocked twice (REPORT_GATE_MAX_BLOCKS).
    Claude Code's own ceiling is eight consecutive blocks, which is a backstop
    rather than a plan.

Input arrives as JSON on stdin and the answer goes to stdout as JSON:
`{"decision": "block", "reason": ...}` sends the model back to work,
`{"systemMessage": ...}` says something to the user and lets the turn end.
"""

from __future__ import annotations

import json
import os
import re
import sys
import datetime
import hashlib
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    import report_lib as lib
except Exception:
    sys.exit(0)  # library missing or broken: never disrupt a turn

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


# --------------------------------------------------------------- switched on?

active_output_style = lib.active_output_style


def gate_enabled(cwd: str) -> bool:
    return lib.convention_enabled(cwd, "REPORT_GATE")


# ------------------------------------------------------------- block counting

def state_path(session_id: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9_.-]", "_", session_id or "nosession")[:64]
    return os.path.join(STATE_DIR, f"{safe}.json")


def load_state(session_id: str) -> dict:
    return lib.read_json(state_path(session_id))


def save_state(session_id: str, state: dict) -> None:
    try:
        os.makedirs(STATE_DIR, exist_ok=True)
        with open(state_path(session_id), "w", encoding="utf-8") as f:
            json.dump(state, f)
    except OSError:
        pass


# ------------------------------------------------------------------- answers

def index(payload: dict, turn: list[dict], kind: str, key: str, text: str,
          ask=None, problems: list[str] | None = None) -> None:
    """Add one line to the project's report index. The transcript stays the
    record of what happened; this is the short form for reading back."""
    branch = ""
    for entry in reversed(turn):
        if entry.get("gitBranch"):
            branch = entry["gitBranch"]
            break
    record = {
        "key": key,
        "ts": datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
        "session": payload.get("session_id") or "",
        "cwd": payload.get("cwd") or "",
        "branch": branch,
        "kind": kind,
        "headline": lib.headline_of(text),
        "verification": lib.verification_of(text),
        "prose": (text or "")[:4000],
    }
    if ask is not None:
        record["questions"] = (ask.input or {}).get("questions") or []
        record["answers"] = (ask.result or {}).get("answers") or {}
    if problems:
        record["problems"] = problems
    lib.record_report(payload.get("cwd") or os.getcwd(), record)


def allow(system_message: str = "") -> None:
    if system_message:
        print(json.dumps({"systemMessage": system_message}))
    sys.exit(0)


def block(session_id: str, user_uuid: str, blocks_so_far: int, reason: str) -> None:
    save_state(session_id, {"user_uuid": user_uuid, "blocks": blocks_so_far + 1})
    print(json.dumps({"decision": "block", "reason": reason}))
    sys.exit(0)


ASK_SHAPE = (
    "Each question: 2 to 4 options, a header of 12 characters or fewer, the "
    "consequence of picking each option in its description, and \" (Recommended)\" "
    "on the first option when you have a recommendation, with the reason in its "
    "description. Free text is always available to the user, so no option for it "
    "is needed."
)

NO_ASK_REASON = (
    "This turn changed something and ended without offering a next step, so the "
    "user has nothing to click and will have to type \"what's next\".\n\n"
    "End it properly: short prose first — one headline sentence carrying the "
    "material fact, bullets for what changed, and a \"Tests:\" or \"Checks:\" line "
    "saying how it was checked — then one AskUserQuestion call with 2 to 4 real "
    "continuations (commit, add tests, the next subtask, review the diff) plus an "
    "explicit \"Stop here\" option. " + ASK_SHAPE + "\n\n"
    "If there is nothing to propose, because the instruction was to do one thing "
    "and stop or no plausible follow-up exists, send the same closing text again "
    "with a last line reading \"No follow-up: <why>.\" and the turn will end."
)


def prose_choice_reason(sentence: str) -> str:
    return (
        f"Your closing text asks the user to choose — \"{sentence}\" — but no "
        "AskUserQuestion call was made, so the question is buried in prose and "
        "there is nothing to click.\n\n"
        "Restate that choice as one AskUserQuestion call and end there. "
        + ASK_SHAPE
    )


def failed_ask_reason(problems: list[str]) -> str:
    listed = "\n".join(f"  - {p}" for p in problems)
    return (
        "Your AskUserQuestion call did not go through, so the user saw no card. "
        "Problems:\n" + listed + "\n\nCall it again with all of these fixed. "
        + ASK_SHAPE
    )


# ----------------------------------------------------------------------- main

def main() -> None:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        sys.exit(0)

    cwd = payload.get("cwd") or os.getcwd()
    session_id = str(payload.get("session_id") or "nosession")
    if not gate_enabled(cwd):
        dbg(action="disabled", style=active_output_style(cwd))
        sys.exit(0)

    if payload.get("background_tasks"):
        dbg(action="background-tasks")
        sys.exit(0)

    transcript = lib.find_transcript(payload)
    if not transcript:
        dbg(action="no-transcript")
        sys.exit(0)

    final_text = payload.get("last_assistant_message")
    if not isinstance(final_text, str):
        final_text = ""

    turn: list[dict] = []
    prompt = None
    for _ in range(POLL_ATTEMPTS):
        entries = lib.load_entries(transcript)
        prompt, turn = lib.split_turn(entries)
        if turn:
            break
        time.sleep(POLL_INTERVAL)
    if not final_text:
        final_text = lib.last_text(turn)

    user_uuid = (prompt or {}).get("uuid") or ""
    state = load_state(session_id)
    blocks_so_far = int(state.get("blocks") or 0) if state.get("user_uuid") == user_uuid else 0
    if payload.get("stop_hook_active") and blocks_so_far == 0:
        blocks_so_far = 1  # state lost; assume one block has already happened
    if blocks_so_far >= MAX_BLOCKS:
        dbg(action="budget-spent", blocks=blocks_so_far)
        allow(f"report gate: {blocks_so_far} blocks on this prompt already, "
              "letting the turn end.")

    calls = lib.tool_calls(turn)
    asks = [c for c in calls if c.name == "AskUserQuestion"]
    mutations = [c for c in calls if lib.is_mutating(c)]
    last_mutation = mutations[-1].pos if mutations else -1
    last_ask = asks[-1].pos if asks else -1
    dbg(action="turn", entries=len(turn), calls=len(calls), asks=len(asks),
        mutations=[c.name for c in mutations], last_ask=last_ask,
        last_mutation=last_mutation, textlen=len(final_text))

    # A call that errored means no card was drawn: worth another round trip.
    for ask in asks:
        if ask.is_error:
            hard, soft = lib.ask_problems(ask.input)
            block(session_id, user_uuid, blocks_so_far,
                  failed_ask_reason(hard + soft or ["the tool rejected the call"]))

    # The turn ended by asking, and the user answered. Report shape problems to
    # the user rather than making them answer a second, tidier card.
    if asks and last_ask > last_mutation:
        hard, soft = lib.ask_problems(asks[-1].input, expect_stop_option=last_mutation >= 0)
        save_state(session_id, {"user_uuid": user_uuid, "blocks": 0})
        problems = hard + soft
        records = lib.find_reports(turn, limit=1)
        report_prose = records[0].get("prose") if records else ""
        index(payload, turn, "ask", asks[-1].id or f"ask:{user_uuid}",
              report_prose or final_text, ask=asks[-1], problems=problems)
        if problems:
            allow("report gate: " + "; ".join(problems))
        allow()

    sentence = lib.offers_choice_in_prose(final_text)
    if sentence:
        block(session_id, user_uuid, blocks_so_far, prose_choice_reason(sentence))

    if last_mutation < 0:
        save_state(session_id, {"user_uuid": user_uuid, "blocks": 0})
        allow()

    if lib.says_no_followup(final_text):
        save_state(session_id, {"user_uuid": user_uuid, "blocks": 0})
        problems = lib.prose_problems(final_text)
        digest = hashlib.sha1((user_uuid + final_text).encode("utf-8")).hexdigest()[:16]
        index(payload, turn, "done", f"done:{digest}", final_text, problems=problems)
        if problems:
            allow("report gate: " + "; ".join(problems))
        allow()

    block(session_id, user_uuid, blocks_so_far, NO_ASK_REASON)


if __name__ == "__main__":
    main()
