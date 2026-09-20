"""report_record.py — writes down what a turn did, for agents that do not.

Claude Code keeps a transcript this plugin can read. Gemini CLI hands its
hooks a `transcript_path` that is stubbed and arrives empty, so the turn has
to be recorded as it happens: this script runs on the event that starts a turn
and on the event that finishes each tool call, and appends a line to the
session's journal under `~/.whats-next/sessions/`. The turn-end hook reads
those lines back.

It is registered only for hosts that need it, takes the same JSON on stdin as
any other hook, prints nothing, and never fails in a way the agent notices:
a lost line costs one imperfect judgement at the end of the turn.
"""

from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    from hosts import from_argv
except Exception:
    sys.exit(0)


def main() -> None:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        sys.exit(0)
    if not isinstance(payload, dict):
        sys.exit(0)
    try:
        host = from_argv()
        recorder = getattr(host, "record", None)
        if recorder is not None:
            recorder(payload)
    except Exception:
        pass
    sys.exit(0)


if __name__ == "__main__":
    main()
