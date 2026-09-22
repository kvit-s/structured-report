"""hosts/codex.py — the Codex adapter.

What Codex provides
-------------------
A hook system whose shape and field names follow Claude Code's closely, in
`~/.codex/hooks.json` and `<repo>/.codex/hooks.json`. `SessionStart` takes
`hookSpecificOutput.additionalContext`, exactly as Claude Code does. `Stop`
fires when a turn ends and is handed `last_assistant_message` and
`stop_hook_active`, and printing `{"decision": "block", "reason": …}` keeps
Codex going — the difference from Claude Code is that the reason becomes a new
continuation prompt rather than a rejection of the stop, so the user sees the
model pick the work up again rather than the same turn resuming. Codex draws the
card with `request_user_input`, which takes one to three questions; builds
that call the same tool `ask_user_question` are recognised as well.

Why this keeps its own record of the turn
-----------------------------------------
Codex does hand hooks a `transcript_path`, and says in the same breath that
the transcript format is not a stable interface for hooks and may change. Its
`PostToolUse` event, on the other hand, is documented: it carries `tool_name`,
`tool_use_id`, `tool_input` and `tool_response`. So the adapter writes the
turn down from those, the way the Gemini CLI one does, and reads nothing it
has been warned not to rely on.

What is verified and what is not
--------------------------------
The event names, the payload fields and the two output shapes come from
Codex's hooks documentation. The exact schema of `ask_user_question` is not
documented, so `normalize_ask` accepts the spellings it is likely to use and
falls back to leaving the call alone: a card that cannot be read is reported
as nothing rather than as a fault, and the worst case is that the checks on a
card's shape stay quiet there.
"""

from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import journal                               # noqa: E402
from core.hook import StopInput                        # noqa: E402
from core.profile import AskLimits, HostProfile        # noqa: E402
from core.turn import Event                            # noqa: E402

PROFILE = HostProfile(
    key="codex",
    display="Codex",
    ask_tool="request_user_input",
    # `apply_patch` is how Codex edits and creates files, and it arrives in a
    # PostToolUse payload under that name. The Claude Code names are here too
    # because Codex reports some tools under them — codex-cli 0.155.1 calls
    # its shell tool `Bash` in hook payloads, whatever the model called.
    write_tools=frozenset({"apply_patch", "Write", "Edit", "MultiEdit",
                           "NotebookEdit"}),
    shell_tools=frozenset({"Bash", "shell", "local_shell", "exec_command",
                           "unified_exec"}),
    # From the tool's own description in codex-cli 0.155.1: "Request user
    # input for one to three short questions and wait for the response." The
    # option count and the header width are not stated anywhere, so Claude
    # Code's numbers stand in; they only ever produce advice printed to the
    # user, never a block.
    ask=AskLimits(max_questions=3, min_options=2, max_options=4, header_max=12),
    # Some builds and much of the writing about Codex call the same card
    # `ask_user_question`, so a call by that name counts too.
    ask_aliases=frozenset({"ask_user_question"}),
)

poll_for_turn = False


def settings_maps(cwd: str):
    """Codex keeps its settings in `config.toml`, and reading TOML needs a
    Python newer than this plugin asks for, so the switches are taken from the
    environment and from `~/.whats-next/config.json` only. `core.config` adds
    that file itself, which is why nothing is yielded here."""
    return iter(())


def suppressed(cwd: str) -> bool:
    return False


# ------------------------------------------------------- recording the turn

def _command_string(tool_input: dict) -> dict:
    """Codex passes a shell call as a list — `["bash", "-lc", "git status"]` —
    and the classifier reads a command string. The program and its `-c` flag
    are dropped so that what is judged is the command that was actually run."""
    command = tool_input.get("command")
    if isinstance(command, str) or command is None:
        return tool_input
    if not isinstance(command, list):
        return tool_input
    words = [str(w) for w in command]
    if len(words) >= 3 and os.path.basename(words[0]) in (
            "bash", "sh", "zsh", "dash") and words[1] in ("-lc", "-c", "-lic"):
        text = words[2]
    else:
        text = " ".join(words)
    out = dict(tool_input)
    out["command"] = text
    return out


def normalize_ask(tool_input: dict) -> dict:
    """The card as `core` expects it: a list under `questions`, each with
    `question`, `header` and `options` of `label` and `description`. Anything
    that cannot be read this way is returned unchanged."""
    questions = tool_input.get("questions")
    if not isinstance(questions, list):
        return tool_input
    out = []
    for q in questions:
        if not isinstance(q, dict):
            return tool_input
        options = q.get("options") or q.get("choices") or []
        normalized = []
        for opt in options if isinstance(options, list) else []:
            if isinstance(opt, str):
                normalized.append({"label": opt, "description": ""})
            elif isinstance(opt, dict):
                label = opt.get("label") or opt.get("name") or opt.get("value") or ""
                if opt.get("recommended") and "(recommended)" not in label.lower():
                    label = f"{label} (Recommended)"
                normalized.append({
                    "label": label,
                    "description": opt.get("description") or opt.get("detail") or "",
                })
        out.append({
            "question": q.get("question") or q.get("prompt") or q.get("text") or "",
            "header": q.get("header") or q.get("label") or "",
            "multiSelect": bool(q.get("multiSelect") or q.get("multi_select")
                                or q.get("kind") == "multiple"),
            "options": normalized,
        })
    return {"questions": out}


def _answers(tool_input: dict, response) -> dict | None:
    """The picks, keyed by the question text. Codex does not document what
    comes back, so several shapes are accepted: a mapping of question to
    answer, a mapping of position to answer, and a list in question order."""
    if isinstance(response, str):
        try:
            response = json.loads(response)
        except ValueError:
            return None
    if isinstance(response, dict):
        answers = response.get("answers", response)
    else:
        answers = response
    questions = [q.get("question") or "" for q in tool_input.get("questions") or []
                 if isinstance(q, dict)]
    if isinstance(answers, list):
        return {q: a for q, a in zip(questions, answers)}
    if not isinstance(answers, dict):
        return None
    out = {}
    for key, value in answers.items():
        text = str(key)
        if text.isdigit() and int(text) < len(questions):
            text = questions[int(text)]
        out[text] = value
    return out


def record(payload: dict) -> None:
    """Called by `report_record.py` from the UserPromptSubmit and PostToolUse
    hooks, which is where the turn is written down."""
    cwd = payload.get("cwd") or os.getcwd()
    session = str(payload.get("session_id") or "nosession")
    event_name = payload.get("hook_event_name") or ""

    if event_name == "UserPromptSubmit":
        prompt = payload.get("prompt")
        journal.record_prompt(cwd, session,
                              prompt if isinstance(prompt, str) else "",
                              uuid=str(payload.get("turn_id") or ""))
        return

    if event_name != "PostToolUse":
        return

    name = payload.get("tool_name") or ""
    tool_input = payload.get("tool_input")
    tool_input = tool_input if isinstance(tool_input, dict) else {}
    response = payload.get("tool_response")

    answers = None
    if PROFILE.is_ask(name):
        tool_input = normalize_ask(tool_input)
        found = _answers(tool_input, response)
        if found is not None:
            answers = {"answers": found}
    elif name in PROFILE.shell_tools:
        tool_input = _command_string(tool_input)

    is_error = bool(isinstance(response, dict) and response.get("error"))
    journal.record_tool(cwd, session, str(payload.get("tool_use_id") or name),
                        name, tool_input, is_error, answers)


# ------------------------------------------------------------ reading it back

def session_source(payload: dict) -> str:
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
    final = payload.get("last_assistant_message")
    return StopInput(
        cwd=payload.get("cwd") or os.getcwd(),
        session_id=str(payload.get("session_id") or "nosession"),
        final_text=final if isinstance(final, str) else "",
        stop_hook_active=bool(payload.get("stop_hook_active")),
        busy=False,
    )


def emit_block(reason: str) -> None:
    # Codex treats this as "keep going", with the reason as the next prompt.
    print(json.dumps({"decision": "block", "reason": reason}))


def emit_allow(system_message: str = "") -> None:
    if system_message:
        print(json.dumps({"systemMessage": system_message}))


def emit_context(text: str) -> None:
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "SessionStart", "additionalContext": text}}))
