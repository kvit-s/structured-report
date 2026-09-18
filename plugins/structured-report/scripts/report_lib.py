"""report_lib.py — reading a turn out of a Claude Code transcript.

What this is for
----------------
A convention for how a turn ends: a turn that edited files, ran commands or
started processes finishes with short prose (one headline sentence, what
changed, a line saying how it was checked) and one `AskUserQuestion` call
offering two to four concrete ways forward. That call is the report — the
options render as buttons, the user picks one, and the pick comes back inside
the same turn. Nothing is written in a second format alongside it.

Two programs share this module:

  report_gate.py  a Stop hook that checks the turn just finished against the
                  convention and, when a turn that changed something ended
                  without offering anything, sends the model back to write one.
  report_last.py  the `/report` command, which reprints the last such question
                  and the answer the user gave.

What a transcript looks like
----------------------------
`~/.claude/projects/<sanitised-cwd>/<session-id>.jsonl` holds one JSON object
per line. The objects this module cares about:

  {"type": "user", "message": {"content": "what the user typed"}}
  {"type": "user", "isMeta": true, "message": {"content": "Stop hook feedback: …"}}
  {"type": "assistant", "message": {"content": [{"type": "text", …},
                                                {"type": "tool_use", "name": "Edit", …}]}}
  {"type": "user", "message": {"content": [{"type": "tool_result", …}]},
   "toolUseResult": {"questions": […], "answers": {"<question>": "<label>"}}}

A turn is everything after the last line that is a real user prompt: type
`user`, not `isMeta` (hook feedback and system notes carry that flag), and
holding typed text rather than a tool result. Subagent traffic is written into
the same file with `isSidechain: true` and is skipped, because a Stop hook
fires for the main agent only.

The transcript is written asynchronously, so the final assistant text may not
be in the file yet when a Stop hook runs. Tool calls made earlier in the turn
are there; for the closing text, the hook uses `last_assistant_message` from
its own input instead.
"""

from __future__ import annotations

import glob
import json
import os
import re
import sys

# ------------------------------------------------------------- switched on?

STYLE_NAMES = {"report", "structuredreport"}


def read_json(path: str) -> dict:
    try:
        with open(path, encoding="utf-8") as f:
            obj = json.load(f)
        return obj if isinstance(obj, dict) else {}
    except (OSError, ValueError):
        return {}


def active_output_style(cwd: str) -> str:
    """The output style in force for a directory. `/output-style` writes the
    choice to `.claude/settings.local.json` beside the project, so walk up from
    the working directory and take the nearest answer, falling back to the
    user's own settings."""
    here = os.path.abspath(cwd or os.getcwd())
    while True:
        for name in ("settings.local.json", "settings.json"):
            style = read_json(os.path.join(here, ".claude", name)).get("outputStyle")
            if isinstance(style, str) and style.strip():
                return style
        parent = os.path.dirname(here)
        if parent == here:
            break
        here = parent
    style = read_json(os.path.expanduser("~/.claude/settings.json")).get("outputStyle")
    return style if isinstance(style, str) else ""


def convention_enabled(cwd: str, switch_var: str = "REPORT_GATE") -> bool:
    """True when turns in this directory are expected to end with a report."""
    switch = os.environ.get(switch_var, "auto").strip().lower()
    if switch in ("0", "off", "false", "no"):
        return False
    if switch in ("1", "on", "true", "yes"):
        return True
    style = active_output_style(cwd).lower()
    # The style may arrive as "report", "Structured report", or namespaced by a
    # plugin, so accept any of those spellings.
    if re.sub(r"[^a-z]", "", style) in STYLE_NAMES:
        return True
    return "report" in re.split(r"[^a-z]+", style)


# ------------------------------------------------------------- the index file

def index_path(cwd: str) -> str:
    """One file per project under ~/.claude/reports/, holding a line per turn
    that ended with a report. The transcript stays the record of what happened;
    this is a short index for reading back or feeding a changelog."""
    sanitized = re.sub(r"[^A-Za-z0-9]", "-", os.path.abspath(cwd or ".")).strip("-")
    return os.path.expanduser(f"~/.claude/reports/{sanitized}.jsonl")


def already_indexed(path: str, key: str, tail: int = 200) -> bool:
    try:
        with open(path, encoding="utf-8") as f:
            lines = f.readlines()[-tail:]
    except OSError:
        return False
    return any(f'"key": "{key}"' in ln or f'"key":"{key}"' in ln for ln in lines)


def record_report(cwd: str, record: dict) -> None:
    """Append one report to the project's index, skipping one already there."""
    path = index_path(cwd)
    key = record.get("key") or ""
    if key and already_indexed(path, key):
        return
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, default=str) + "\n")
    except OSError:
        pass


def read_index(cwd: str, limit: int = 10) -> list[dict]:
    out = []
    try:
        with open(index_path(cwd), encoding="utf-8") as f:
            for line in f:
                try:
                    out.append(json.loads(line))
                except ValueError:
                    continue
    except OSError:
        return []
    return out[-limit:]


def headline_of(text: str) -> str:
    first = next((ln.strip() for ln in (text or "").splitlines() if ln.strip()), "")
    first = re.sub(r"^[#>*\-\s]+", "", first)
    return first[:240]


def verification_of(text: str) -> str:
    for line in (text or "").splitlines():
        if VERIFICATION.match(line.strip()):
            return line.strip()[:240]
    return ""


# ---------------------------------------------------------------- transcripts


def find_transcript(payload: dict) -> str | None:
    """Path to the transcript for this session, or the newest one for the
    working directory when the payload does not name it."""
    path = payload.get("transcript_path")
    if path:
        path = os.path.expanduser(path)
        if os.path.isfile(path):
            return path
    return newest_transcript(payload.get("cwd") or os.getcwd())


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
    hits = glob.glob(os.path.expanduser(
        f"~/.claude/projects/*/{session_id}.jsonl"))
    return hits[0] if hits else None


def load_entries(path: str) -> list[dict]:
    out: list[dict] = []
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except Exception:
                    continue
                if isinstance(obj, dict) and not obj.get("isSidechain"):
                    out.append(obj)
    except OSError:
        return []
    return out


def is_user_prompt(entry: dict) -> bool:
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


def split_turn(entries: list[dict]) -> tuple[dict | None, list[dict]]:
    """(the last user prompt, everything after it)."""
    last = -1
    for i, e in enumerate(entries):
        if is_user_prompt(e):
            last = i
    if last < 0:
        return None, entries
    return entries[last], entries[last + 1:]


def blocks_of(entry: dict) -> list[dict]:
    content = (entry.get("message") or {}).get("content")
    return [b for b in content if isinstance(b, dict)] if isinstance(content, list) else []


def assistant_text(entry: dict) -> str:
    return "\n".join(b.get("text") or "" for b in blocks_of(entry)
                     if b.get("type") == "text").strip()


class ToolCall:
    """One tool call in a turn, with whatever came back for it."""

    def __init__(self, pos: int, name: str, inp: dict, call_id: str):
        self.pos = pos
        self.name = name
        self.input = inp if isinstance(inp, dict) else {}
        self.id = call_id
        self.is_error = False
        self.result = None        # the toolUseResult object, when there is one
        self.answered = False

    def __repr__(self) -> str:  # debugging only
        return f"<ToolCall {self.pos} {self.name} answered={self.answered}>"


def tool_calls(turn: list[dict]) -> list[ToolCall]:
    calls: list[ToolCall] = []
    by_id: dict[str, ToolCall] = {}
    for pos, entry in enumerate(turn):
        if entry.get("type") == "assistant":
            for b in blocks_of(entry):
                if b.get("type") == "tool_use":
                    call = ToolCall(pos, b.get("name") or "", b.get("input"),
                                    b.get("id") or "")
                    calls.append(call)
                    if call.id:
                        by_id[call.id] = call
        elif entry.get("type") == "user":
            for b in blocks_of(entry):
                if b.get("type") != "tool_result":
                    continue
                call = by_id.get(b.get("tool_use_id") or "")
                if call is None:
                    continue
                call.answered = True
                call.is_error = bool(b.get("is_error"))
                if isinstance(entry.get("toolUseResult"), dict):
                    call.result = entry["toolUseResult"]
    return calls


def last_text(turn: list[dict]) -> str:
    for entry in reversed(turn):
        if entry.get("type") == "assistant":
            text = assistant_text(entry)
            if text:
                return text
    return ""


# ------------------------------------------------------- what a turn changed

WRITE_TOOLS = {"Write", "Edit", "MultiEdit", "NotebookEdit", "ArtifactData"}

# Commands that only look. Anything else in a shell call counts as work done.
READONLY_CMDS = {
    "awk", "basename", "cat", "cd", "cksum", "column", "comm", "cut", "date",
    "df", "diff", "dirname", "du", "echo", "false", "file", "find",
    "fd", "fgrep", "grep", "egrep", "head", "hostname", "id", "jq", "less",
    "ls", "md5sum", "nl", "od", "pgrep", "printf", "ps", "pwd", "readlink",
    "realpath", "rg", "sha1sum", "sha256sum", "sort", "stat", "tail", "tr",
    "tree", "true", "type", "uname", "uniq", "wc", "which", "whoami", "xxd",
    "yq", "zcat",
}
# The PowerShell tool is what a Windows session runs commands with. Cmdlets and
# the aliases people actually type; ForEach-Object is left out on purpose,
# because its script block routinely holds something that writes.
POWERSHELL_READONLY = {
    "compare-object", "convertfrom-json", "convertto-json", "format-list",
    "format-table", "get-childitem", "get-command", "get-content", "get-date",
    "get-help", "get-item", "get-itemproperty", "get-location", "get-member",
    "get-process", "group-object", "join-path", "measure-object", "out-string",
    "resolve-path", "select-object", "select-string", "sort-object",
    "split-path", "test-path", "where-object", "write-host", "write-output",
    "gci", "gc", "gci", "gi", "gl", "gm", "gp", "gps", "sls", "select",
    "where", "measure", "ft", "fl", "dir", "compare", "diff",
}
# Cmdlets that write, wherever they appear — including inside a script block
# that the split above does not look into.
POWERSHELL_WRITING = (
    "remove-item", "set-content", "add-content", "out-file", "new-item",
    "move-item", "copy-item", "rename-item", "set-itemproperty",
    "clear-content", "remove-itemproperty", "start-process", "stop-process",
    "set-item", "new-itemproperty", "tee-object", "export-csv",
    "export-clixml", "invoke-expression",
)
GIT_READONLY = {
    "blame", "cat-file", "describe", "diff", "grep", "log", "ls-files",
    "reflog", "rev-parse", "shortlog", "show", "status",
}
# Programs that run another program: step past them and judge what follows.
WRAPPERS = {"command", "builtin", "env", "nice", "nohup", "stdbuf", "time", "!"}
# Read-only programs that can still write when asked to.
WRITING_FLAGS = {
    "find": ("-delete", "-exec", "-execdir", "-ok", "-okdir", "-fprint",
             "-fprintf", "-fls"),
    "rg": ("--replace",),
    "jq": ("--in-place",),
}
_SPLIT = re.compile(r"\|\||&&|\||;|\n")
_ENVASSIGN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")


def shell_is_readonly(command: str) -> bool:
    """True when every part of a shell command only reads. Conservative: a
    redirection, an unknown program or anything it cannot parse reads as work
    done, so the gate never stays silent about a turn that changed something."""
    if not command or not command.strip():
        return True
    lowered = command.lower()
    if any(name in lowered for name in POWERSHELL_WRITING):
        return False
    stripped = re.sub(r"2>&1|>&2|[12]?>>?\s*/dev/null|&>\s*/dev/null", " ", command)
    if ">" in stripped or "`" in command or "$(" in command:
        return False
    for segment in _SPLIT.split(stripped):
        words = segment.strip().lstrip("({ ").split()
        while words and (_ENVASSIGN.match(words[0]) or words[0] in WRAPPERS):
            words.pop(0)
        if not words:
            continue
        prog = os.path.basename(words[0])
        for flag in WRITING_FLAGS.get(prog, ()):
            if any(w == flag or w.startswith(flag + "=") for w in words[1:]):
                return False
        if prog == "sed":
            if any(w.startswith("-i") for w in words[1:]):
                return False
            continue
        if prog == "git":
            sub = next((w for w in words[1:] if not w.startswith("-")), "")
            if sub not in GIT_READONLY:
                return False
            continue
        if prog.lower() not in READONLY_CMDS and prog.lower() not in POWERSHELL_READONLY:
            return False
    return True


def extra_mutating_tools() -> set[str]:
    raw = os.environ.get("REPORT_GATE_MUTATING_TOOLS", "")
    return {n.strip() for n in raw.replace(",", " ").split() if n.strip()}


def is_mutating(call: ToolCall) -> bool:
    if call.name in WRITE_TOOLS or call.name in extra_mutating_tools():
        return True
    if call.name in ("Bash", "PowerShell"):
        return not shell_is_readonly(call.input.get("command") or "")
    return False


# --------------------------------------------------- checking one ask by hand

HEADER_MAX = 12
RECOMMENDED = re.compile(r"\(recommended\)\s*$", re.I)
STOP_OPTION = re.compile(
    r"\b(stop here|stop there|leave it|leave as is|nothing (?:more|else)|"
    r"no (?:further|more)|that'?s all|hold off|not now|later|done for now|"
    r"wrap up|finish here|end here|park it)\b", re.I)


def ask_problems(payload: dict, expect_stop_option: bool = False
                 ) -> tuple[list[str], list[str]]:
    """Check one AskUserQuestion input. Returns (hard, soft): hard problems make
    the call unusable, soft ones are about the shape of a call that worked.
    Every problem is reported at once so one pass fixes all of them."""
    hard: list[str] = []
    soft: list[str] = []
    questions = payload.get("questions")
    if not isinstance(questions, list) or not questions:
        return ["the call has no questions"], []
    if len(questions) > 4:
        hard.append(f"{len(questions)} questions in one call; the tool takes at most 4")

    recommended_total = 0
    for i, q in enumerate(questions, 1):
        where = f"question {i}"
        if not isinstance(q, dict):
            hard.append(f"{where} is not an object")
            continue
        text = (q.get("question") or "").strip()
        if not text:
            hard.append(f"{where} has no question text")
        header = (q.get("header") or "").strip()
        if not header:
            soft.append(f"{where} has no header")
        elif len(header) > HEADER_MAX:
            soft.append(f'{where} header "{header}" is {len(header)} characters; '
                        f"the card shows {HEADER_MAX}")
        options = q.get("options")
        if not isinstance(options, list) or len(options) < 2 or len(options) > 4:
            n = len(options) if isinstance(options, list) else 0
            hard.append(f"{where} has {n} options; give 2 to 4")
            continue
        labels = []
        for j, opt in enumerate(options, 1):
            if not isinstance(opt, dict):
                hard.append(f"{where} option {j} is not an object")
                continue
            label = (opt.get("label") or "").strip()
            if not label:
                hard.append(f"{where} option {j} has no label")
            labels.append(label)
            if not (opt.get("description") or "").strip():
                soft.append(f'{where} option "{label or j}" has no description; '
                            "the description is where the consequence goes")
        marked = [k for k, lab in enumerate(labels) if RECOMMENDED.search(lab)]
        recommended_total += len(marked)
        if not q.get("multiSelect"):
            if len(marked) > 1:
                soft.append(f"{where} marks {len(marked)} options "
                            '"(Recommended)"; mark one')
            elif marked and marked[0] != 0:
                soft.append(f"{where} puts the recommended option at position "
                            f"{marked[0] + 1}; put it first")
        if expect_stop_option and i == len(questions):
            joined = " ".join(f"{lab} {(o.get('description') or '') if isinstance(o, dict) else ''}"
                              for lab, o in zip(labels, options))
            if not STOP_OPTION.search(joined):
                soft.append(f'{where} offers no way to stop; add an explicit '
                            '"Stop here" option so the turn can end')
    if expect_stop_option and recommended_total == 0:
        soft.append('no option is marked " (Recommended)"; mark the one you '
                    "would pick and say why in its description")
    return hard, soft


# ------------------------------------------------------- the closing prose

VERIFICATION = re.compile(
    r"(?im)^\s*(?:[-*]\s*)?(?:\*\*)?(?:tests?|checks?|verified|verification|"
    r"build|checked)(?:\*\*)?\s*:")
UNVERIFIED = re.compile(
    r"(?i)(left|not|un)\s*(it\s+)?(verified|tested|checked|run)|"
    r"did not (?:run|test|verify|check)|no tests? (?:were )?run")
NO_FOLLOWUP = re.compile(r"(?im)^\s*(?:[-*>]\s*)?(?:\*\*)?no follow-?up\b")
CHOICE_IN_PROSE = re.compile(
    r"(?i)\b(should i|shall i|do you want me to|would you like me to|"
    r"want me to|which (?:one|option|approach|of these|would you)|"
    r"let me know (?:if|whether|which)|your call)\b[^.!?\n]*\?")


def says_no_followup(text: str) -> bool:
    return bool(NO_FOLLOWUP.search(text or ""))


def prose_problems(text: str) -> list[str]:
    """Soft checks on the closing prose of a turn that offers nothing."""
    out: list[str] = []
    text = (text or "").strip()
    if not text:
        return ["the turn ended with no text at all"]
    if not VERIFICATION.search(text) and not UNVERIFIED.search(text):
        out.append("no line saying how the work was checked; end with a "
                   '"Tests:" or "Checks:" line, or say what is left unverified '
                   "and why")
    first = next((ln.strip() for ln in text.splitlines() if ln.strip()), "")
    first = re.sub(r"^[#>*\-\s]+", "", first)
    if len(first) > 200:
        out.append(f"the opening line is {len(first)} characters; a headline is "
                   "one sentence carrying the material fact")
    return out


def offers_choice_in_prose(text: str) -> str | None:
    """The sentence where the closing text asks the user to choose, if it does.
    Only the last few lines count, so a rhetorical question earlier in the
    message is left alone."""
    lines = [ln for ln in (text or "").splitlines() if ln.strip()]
    tail = "\n".join(lines[-4:])
    m = CHOICE_IN_PROSE.search(tail)
    return m.group(0).strip() if m else None


# ------------------------------------------------------------------ the card


def render_card(question_payload: dict, answers: dict | None, prose: str = "",
                when: str = "", width: int = 78) -> str:
    """The question, its options and what the user picked, as plain text."""
    lines: list[str] = []
    if when:
        lines.append(f"Report — {when}")
    if prose:
        lines.append("")
        lines.append(prose.strip())
    questions = question_payload.get("questions") or []
    answers = answers or {}
    for q in questions:
        if not isinstance(q, dict):
            continue
        header = (q.get("header") or "").strip()
        text = (q.get("question") or "").strip()
        lines.append("")
        lines.append(f"[{header}] {text}" if header else text)
        picked_raw = answers.get(text)
        picked = set()
        if isinstance(picked_raw, str):
            picked = {p.strip() for p in picked_raw.split(", ")}
        elif isinstance(picked_raw, list):
            picked = {str(p).strip() for p in picked_raw}
        for opt in q.get("options") or []:
            if not isinstance(opt, dict):
                continue
            label = (opt.get("label") or "").strip()
            mark = "->" if label in picked else "  "
            desc = (opt.get("description") or "").strip()
            lines.append(f"  {mark} {label}")
            if desc:
                for chunk in _wrap(desc, width - 7):
                    lines.append(f"       {chunk}")
        if picked_raw is None:
            lines.append("     (unanswered)")
        else:
            shown = picked_raw if isinstance(picked_raw, str) else ", ".join(picked)
            unlisted = [p for p in picked
                        if p not in {(o.get("label") or "").strip()
                                     for o in q.get("options") or []
                                     if isinstance(o, dict)}]
            suffix = "  (typed, not one of the options)" if unlisted else ""
            lines.append(f"     answer: {shown}{suffix}")
    return "\n".join(lines).strip()


def _wrap(text: str, width: int) -> list[str]:
    words, out, cur = text.split(), [], ""
    for w in words:
        if cur and len(cur) + 1 + len(w) > width:
            out.append(cur)
            cur = w
        else:
            cur = f"{cur} {w}".strip()
    if cur:
        out.append(cur)
    return out


def find_reports(entries: list[dict], limit: int = 1) -> list[dict]:
    """The most recent AskUserQuestion calls, newest first. Each item holds the
    call's input, the answers the user gave, the assistant text that preceded
    it and when it happened."""
    out: list[dict] = []
    pending: dict[str, dict] = {}
    recent_text = ""
    for entry in entries:
        if entry.get("type") == "assistant":
            text = assistant_text(entry)
            for b in blocks_of(entry):
                if b.get("type") == "tool_use" and b.get("name") == "AskUserQuestion":
                    pending[b.get("id") or ""] = {
                        "input": b.get("input") or {},
                        "prose": text or recent_text,
                        "when": entry.get("timestamp") or "",
                        "answers": None,
                    }
            if text:
                recent_text = text
        elif entry.get("type") == "user":
            for b in blocks_of(entry):
                if b.get("type") != "tool_result":
                    continue
                rec = pending.pop(b.get("tool_use_id") or "", None)
                if rec is None:
                    continue
                result = entry.get("toolUseResult")
                if isinstance(result, dict):
                    rec["answers"] = result.get("answers")
                out.append(rec)
    out.extend(pending.values())
    return list(reversed(out))[:limit]


def prose_before(entries: list[dict], record: dict) -> str:
    return record.get("prose") or ""


def main_selftest() -> int:  # pragma: no cover - convenience
    print("report_lib: no self-test here; run test_report_gate.py", file=sys.stderr)
    return 0
