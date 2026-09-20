"""core/convention.py — the text the model is given, kept in one file.

The rules a turn is judged by are written once, in `output-styles/report.md`
beside the scripts. That file is a usable Claude Code output style, so anyone
who would rather pin it in settings can, and it is also what the SessionStart
hook reads and hands the model as additional context, which is what makes
installing the plugin the whole switch.

`convention_text` returns it with the YAML frontmatter stripped. When the host
calls its question tool something other than `AskUserQuestion` — Codex and
Grok Build use `ask_user_question`, Gemini CLI uses `ask_user`, OpenCode calls
it `question` — the name is substituted on the way out, so the model is told
to call a tool that exists where it is running.
"""

from __future__ import annotations

import os
import re

CLAUDE_ASK_TOOL = "AskUserQuestion"

PREAMBLE = ("The What's Next convention is active in this session. It governs "
            "how a turn ends and nothing else.\n\n")


def style_paths() -> list[str]:
    """Where the file holding the convention may be: beside the scripts in the
    plugin, or in the user's own output styles for a hand-registered install."""
    here = os.path.dirname(os.path.abspath(__file__))
    plugin_root = os.path.normpath(os.path.join(here, os.pardir, os.pardir))
    return [
        os.path.join(plugin_root, "output-styles", "report.md"),
        os.path.expanduser("~/.claude/output-styles/report.md"),
    ]


def strip_frontmatter(text: str) -> str:
    if text.lstrip().startswith("---"):
        text = text.lstrip()
        close = text.find("\n---", 3)
        if close != -1:
            nl = text.find("\n", close + 1)
            text = text[nl + 1:] if nl != -1 else ""
    return text.strip()


def style_body(path: str = "") -> str:
    """The convention as written, or "" when the file cannot be read."""
    for candidate in ([path] if path else style_paths()):
        try:
            with open(candidate, encoding="utf-8") as f:
                text = f.read()
        except OSError:
            continue
        body = strip_frontmatter(text)
        if body:
            return body
    return ""


def convention_text(profile, path: str = "") -> str:
    """The convention with the host's own tool name in it."""
    body = style_body(path)
    if body and profile.ask_tool != CLAUDE_ASK_TOOL:
        body = re.sub(re.escape(CLAUDE_ASK_TOOL), profile.ask_tool, body)
    return body
