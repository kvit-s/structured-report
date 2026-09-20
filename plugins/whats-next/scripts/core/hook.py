"""core/hook.py — the few facts a turn-end hook needs from its host.

Claude Code, Codex and Gemini CLI all hand a turn-end hook a JSON object on
stdin with much the same content under slightly different names, and OpenCode
hands a plugin an event object instead. The adapter reduces whichever it gets
to this.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class StopInput:
    cwd: str
    session_id: str
    final_text: str = ""          # the closing prose, as the host reports it
    stop_hook_active: bool = False  # this turn has already been sent back once
    busy: bool = False            # background work is still running
