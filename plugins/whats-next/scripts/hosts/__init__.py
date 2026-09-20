"""hosts — one adapter per agent.

An adapter is the only part of the plugin that knows how a particular agent
stores a session, what its hooks are handed and what they may print. It
supplies a `PROFILE` naming that agent's tools, reads the session record into
`core.turn.Event` objects, and prints the replies its agent understands.

`load()` picks one. Claude Code is the default and the only adapter shipped;
`WHATS_NEXT_HOST=codex` would load `hosts/codex.py` if one were written, which
is what a port adds.
"""

from __future__ import annotations

import importlib
import os

DEFAULT = "claude_code"


def load(key: str = ""):
    name = (key or os.environ.get("WHATS_NEXT_HOST") or DEFAULT).strip()
    return importlib.import_module("hosts." + name.replace("-", "_"))
