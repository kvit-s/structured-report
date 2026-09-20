"""report_context.py — the session-start hook that hands the model the convention.

Why this exists
---------------
Claude Code loads an output style only when somebody picks it from the
`/output-style` menu, so a plugin that shipped the convention as a style alone
would install cleanly and then do nothing at all until the user found that
menu. Having the plugin installed is meant to be the whole switch, so this
hook runs at the start of every session and gives the model the same text as
additional context. Anthropic's own `explanatory-output-style` and
`learning-output-style` plugins are built the same way.

The text is read from `output-styles/report.md` with its YAML frontmatter
removed, which keeps the convention written down in one place, and the name of
the question tool is the host's own. That file is still a usable output style
for anyone who would rather pin it in settings, and when it is the active
style this hook says nothing rather than delivering the same instructions
twice.

It stays quiet when:

  * the convention is switched off, with `REPORT_GATE=off` in the environment,
    in an `env` block in a project's `.claude/settings.json`, or in
    `~/.whats-next/config.json`;
  * the host is already sending the text itself, which for Claude Code means
    the `report` output style is the active one;
  * the style file cannot be read, which leaves the session exactly as it was.

Registered for every SessionStart source, so the convention is delivered again
after `/clear`, after a resume and after the context is compacted.
"""

from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    from core import config, convention
    from hosts import from_argv
except Exception:
    sys.exit(0)  # library missing or broken: never disrupt a session


def main() -> None:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        payload = {}
    if not isinstance(payload, dict):
        payload = {}

    host = from_argv()
    cwd = payload.get("cwd") or os.getcwd()
    if not config.convention_enabled(host.settings_maps(cwd), "REPORT_GATE"):
        return
    if host.suppressed(cwd):
        return

    body = convention.convention_text(host.PROFILE)
    if not body:
        return

    host.emit_context(convention.PREAMBLE + body)


if __name__ == "__main__":
    main()
