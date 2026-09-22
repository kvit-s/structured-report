"""hosts — one adapter per agent.

An adapter is the only part of the plugin that knows how a particular agent
stores a session, what its hooks are handed and what they may print. It
supplies a `PROFILE` naming that agent's tools, reads the session record into
`core.turn.Event` objects, and prints the replies its agent understands.

`load()` picks one, by name: Claude Code is the default, Gemini CLI is
`gemini_cli`, and `WHATS_NEXT_HOST=<name>` or `--host <name>` on a hook's
command line chooses between them. A port adds a file here and nothing else.
"""

from __future__ import annotations

import importlib
import os
import sys

DEFAULT = "claude_code"


def load(key: str = ""):
    name = (key or os.environ.get("WHATS_NEXT_HOST") or DEFAULT).strip()
    return importlib.import_module("hosts." + name.replace("-", "_"))


def from_argv(argv: list[str] | None = None):
    """The adapter named by `--host name` on the command line, which is how a
    hook says which agent invoked it. Agents differ in whether they run a hook
    command through a shell, so an argument is safer than an environment
    variable set in front of it."""
    args = list(argv if argv is not None else sys.argv[1:])
    for i, arg in enumerate(args):
        if arg == "--host" and i + 1 < len(args):
            return load(args[i + 1])
        if arg.startswith("--host="):
            return load(arg.split("=", 1)[1])
    return load()
