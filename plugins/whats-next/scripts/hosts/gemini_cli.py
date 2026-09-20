"""hosts/gemini_cli.py — the Gemini CLI adapter.

What Gemini CLI provides
------------------------
All three things the convention needs, under its own names. A `SessionStart`
hook takes `hookSpecificOutput.additionalContext` and injects it as the first
turn of the session. An `AfterAgent` hook fires once per turn after the model's
final response, and printing `{"decision": "deny", "reason": …}` rejects that
response and sends the reason back to the model as a new prompt, which is this
plugin's block. The card is `ask_user`, whose questions take a header of up to
sixteen characters and two to four options with labels and descriptions.

Hooks are registered under a `hooks` key in `~/.gemini/settings.json` or a
project's `.gemini/settings.json`, and an extension may ship its own
`hooks/hooks.json`, which is how this plugin installs them.

What it does not provide
------------------------
A readable record of the session. Every hook is handed a `transcript_path`,
but the field is stubbed and arrives empty, so there is no file to read the
turn out of. The adapter therefore keeps its own: a `BeforeAgent` hook writes
down the prompt, an `AfterTool` hook writes down each tool call with its
result, and `AfterAgent` reads those lines back as the turn. `core/journal.py`
holds that file; when Gemini CLI starts filling `transcript_path` in, reading
its transcript instead would replace `record()` and `read_events()` and
nothing else.

One consequence is visible in `/report`: the card and the answer come back,
and the prose that preceded them does not, because Gemini hands the response
text over only once the turn is over, after the card was drawn.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import journal                               # noqa: E402
from core.config import read_json                      # noqa: E402
from core.hook import StopInput                        # noqa: E402
from core.profile import AskLimits, HostProfile        # noqa: E402
from core.turn import Event, ToolResult, ToolUse       # noqa: E402

PROFILE = HostProfile(
    key="gemini-cli",
    display="Gemini CLI",
    ask_tool="ask_user",
    # `write_file` creates and overwrites, `replace` edits in place. Anything
    # else that writes — a tool from an MCP server, or a name a later release
    # introduces — is added with REPORT_GATE_MUTATING_TOOLS.
    write_tools=frozenset({"write_file", "replace"}),
    shell_tools=frozenset({"run_shell_command"}),
    ask=AskLimits(max_questions=4, min_options=2, max_options=4, header_max=16),
)

# The journal is written by the tool hook before the turn-end hook runs, so
# there is nothing to wait for.
poll_for_turn = False


# ------------------------------------------------------------------ settings

def settings_maps(cwd: str):
    """`.gemini/settings.json` from the working directory upwards, then the
    user's own. Gemini CLI reads the project and user files; the switches this
    plugin uses are read from them too, and from `~/.whats-next/config.json`,
    which is where a setting shared with other agents belongs."""
    here = os.path.abspath(cwd or os.getcwd())
    while True:
        yield read_json(os.path.join(here, ".gemini", "settings.json"))
        parent = os.path.dirname(here)
        if parent == here:
            break
        here = parent
    yield read_json(os.path.expanduser("~/.gemini/settings.json"))


def suppressed(cwd: str) -> bool:
    """Gemini CLI has nothing like an output style that would already be
    sending the convention, so the session-start hook always speaks."""
    return False


# ------------------------------------------------------- recording the turn

def _answers_by_question(tool_input: dict, response) -> dict | None:
    """`ask_user` answers come back keyed by the question's position —
    `{"answers": {"0": "Commit"}}` — and sometimes as a JSON string. The rules
    and the card expect them keyed by the question text, the way Claude Code
    reports them, so they are turned round here."""
    if isinstance(response, str):
        try:
            response = json.loads(response)
        except ValueError:
            return None
    if not isinstance(response, dict):
        return None
    answers = response.get("answers")
    if not isinstance(answers, dict):
        return None
    questions = tool_input.get("questions")
    if not isinstance(questions, list):
        return None
    out = {}
    for key, value in answers.items():
        try:
            index = int(key)
        except (TypeError, ValueError):
            out[str(key)] = value
            continue
        if 0 <= index < len(questions) and isinstance(questions[index], dict):
            out[(questions[index].get("question") or "").strip()] = value
    return out


def _is_error(response) -> bool:
    if isinstance(response, dict):
        return bool(response.get("error"))
    return False


def record(payload: dict) -> None:
    """One line in the journal per prompt and per finished tool call. Called
    by `report_record.py`, which Gemini's BeforeAgent and AfterTool hooks
    run."""
    cwd = payload.get("cwd") or os.getcwd()
    session = str(payload.get("session_id") or "nosession")
    event_name = payload.get("hook_event_name") or ""
    stamp = payload.get("timestamp") or ""

    if event_name == "BeforeAgent":
        prompt = payload.get("prompt")
        prompt = prompt if isinstance(prompt, str) else ""
        journal.append(cwd, session, Event(
            role="user", is_prompt=True, text=prompt.strip(), timestamp=stamp,
            uuid=hashlib.sha1((stamp + prompt).encode("utf-8")).hexdigest()[:16]))
        return

    if event_name != "AfterTool":
        return

    name = payload.get("tool_name") or ""
    tool_input = payload.get("tool_input")
    tool_input = tool_input if isinstance(tool_input, dict) else {}
    response = payload.get("tool_response")
    call_id = f"{name}:{time.time_ns()}"

    result_payload = None
    if name == PROFILE.ask_tool:
        answers = _answers_by_question(tool_input, response)
        if answers is not None:
            result_payload = {"answers": answers}

    journal.append(cwd, session, Event(
        role="assistant", timestamp=stamp,
        tool_uses=[ToolUse(call_id, name, tool_input)],
        tool_results=[ToolResult(call_id, _is_error(response), result_payload)]))


# ------------------------------------------------------------ reading it back

def session_source(payload: dict) -> str:
    """The journal for this session. A path is returned whether or not the
    file exists: a turn that called no tool has nothing written down, and the
    closing prose still has to be looked at."""
    return journal.journal_path(payload.get("cwd") or os.getcwd(),
                                str(payload.get("session_id") or "nosession"))


def read_events(source: str) -> list[Event]:
    return journal.read(source)


def transcript_for_session(cwd: str, session_id: str) -> str | None:
    path = journal.journal_path(cwd, session_id)
    return path if os.path.isfile(path) else None


def newest_transcript(cwd: str) -> str | None:
    return journal.newest_journal(cwd)


# ----------------------------------------------------------- hooks in and out

def stop_input(payload: dict) -> StopInput:
    final = payload.get("prompt_response")
    return StopInput(
        cwd=payload.get("cwd") or os.getcwd(),
        session_id=str(payload.get("session_id") or "nosession"),
        final_text=final if isinstance(final, str) else "",
        stop_hook_active=bool(payload.get("stop_hook_active")),
        busy=False,
    )


def emit_block(reason: str) -> None:
    # "deny" rejects the response the model just gave and sends `reason` back
    # as a new prompt, which is Gemini's spelling of Claude Code's "block".
    print(json.dumps({"decision": "deny", "reason": reason}))


def emit_allow(system_message: str = "") -> None:
    if system_message:
        print(json.dumps({"systemMessage": system_message}))


def emit_context(text: str) -> None:
    # Only `additionalContext` is documented under `hookSpecificOutput` here,
    # so nothing else is put in it.
    print(json.dumps({"hookSpecificOutput": {"additionalContext": text}}))
