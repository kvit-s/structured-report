"""core/mutations.py — did this turn change anything?

The gate only asks for a report when the turn did something: wrote a file, ran
a command that was not a lookup, started a process. A turn that read code and
answered a question ends in prose as usual.

Two sources decide it. The host profile lists the tools that write by their
nature — Claude Code's `Write` and `Edit`, Codex's `apply_patch`, OpenCode's
`write` — and for the tool that runs shell commands the command itself is
read. That reading is deliberately conservative: a redirection, a program not
on the list of lookups, or anything the parser cannot make sense of counts as
work done, so the gate never stays quiet about a turn that changed something.
The opposite mistake, asking for a report after a turn that only looked, costs
one needless card.
"""

from __future__ import annotations

import os
import re

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
# PowerShell is what a Windows session runs commands with. Cmdlets and the
# aliases people actually type; ForEach-Object is left out on purpose, because
# its script block routinely holds something that writes.
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
# that the split below does not look into.
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
    """True when every part of a shell command only reads."""
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
    """Tool names the user has added with REPORT_GATE_MUTATING_TOOLS, which is
    how a host's own tool — or an MCP server's — is counted as work done
    without editing anything here."""
    raw = os.environ.get("REPORT_GATE_MUTATING_TOOLS", "")
    return {n.strip() for n in raw.replace(",", " ").split() if n.strip()}


def is_mutating(call, profile) -> bool:
    if call.name in profile.write_tools or call.name in extra_mutating_tools():
        return True
    if call.name in profile.shell_tools:
        return not shell_is_readonly(call.input.get("command") or "")
    return False
