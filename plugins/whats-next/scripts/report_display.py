"""report_display.py — marks the closing lines of a report on screen.

A MessageDisplay hook, so it changes only what is drawn in the terminal: the
transcript keeps the original text and the model never sees the replacement.
It does one small thing. In a turn that ends with a report, the line saying how
the work was checked and the line explaining why there is no follow-up are the
two the eye should land on, so each gets a marker in the left margin:

    Tests: go test ./internal/order — 14/14 pass.
  becomes
    ✓ Tests: go test ./internal/order — 14/14 pass.

Nothing else is touched, and when anything at all goes wrong Claude Code draws
the original text, so the worst case is no markers.

Claude Code calls this once per batch of completed lines while a message
streams. Batches hold whole lines apart from the last one, which can end
mid-line, so a trailing fragment is left alone until the batch that completes
it. The hook returns quickly when a batch has nothing to mark, before it looks
at any settings, because the whole message waits on it.

Switched off with REPORT_CARD_DISPLAY=off, in the environment or in an `env`
block in a project's `.claude/settings.json`.
"""

from __future__ import annotations

import json
import os
import re
import sys

CANDIDATE = re.compile(
    r"(?im)^\s*(?:[-*]\s*)?(?:\*\*)?(?:tests?|checks?|verified|verification|"
    r"no follow-?up)(?:\*\*)?\s*:")
VERIFY = re.compile(r"(?i)^\s*(?:[-*]\s*)?(?:\*\*)?(?:tests?|checks?|verified|verification)")
FENCE = re.compile(r"^\s*(?:```|~~~)")


def mark(delta: str) -> str | None:
    """The delta with markers added, or None when there is nothing to change."""
    lines = delta.split("\n")
    # The last element is the text after the final newline: a fragment of a line
    # that is not complete yet, or "" when the batch ended on a newline.
    tail = lines.pop()
    changed = False
    fenced = False
    for i, line in enumerate(lines):
        if FENCE.match(line):
            fenced = not fenced
            continue
        if fenced or not CANDIDATE.match(line):
            continue
        marker = "✓ " if VERIFY.match(line) else "· "
        lines[i] = marker + line
        changed = True
    if not changed:
        return None
    lines.append(tail)
    return "\n".join(lines)


def main() -> None:
    try:
        payload = json.load(sys.stdin)
        delta = payload.get("delta")
        if not isinstance(delta, str) or ":" not in delta:
            return
        marked = mark(delta)
        if marked is None:
            return
        if os.environ.get("REPORT_CARD_DISPLAY", "").strip().lower() in ("0", "off", "false", "no"):
            return
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import report_lib as lib
        if not lib.convention_enabled(payload.get("cwd") or os.getcwd(), "REPORT_CARD_DISPLAY"):
            return
        print(json.dumps({"hookSpecificOutput": {
            "hookEventName": "MessageDisplay", "displayContent": marked}}))
    except Exception:
        return  # the original text is drawn


if __name__ == "__main__":
    main()
