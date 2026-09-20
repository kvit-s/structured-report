"""core/config.py — is the convention switched on in this directory?

Having the plugin installed is what switches the convention on: its hooks are
registered, so it applies, and removing the plugin removes it. There are three
places to turn it off again without uninstalling anything, read in this order
and the first answer wins:

  1. the real environment, `REPORT_GATE=off`;
  2. the agent's own settings, walked from the working directory upwards —
     the host adapter supplies those already parsed, because every agent keeps
     them somewhere different, and for Claude Code they are the `env` blocks of
     `.claude/settings.local.json` and `.claude/settings.json`;
  3. `~/.whats-next/config.json`, which belongs to this plugin rather than to
     any agent and so is the one place a machine running several agents can
     set a switch once:

         {"REPORT_GATE": "off"}

Each source may spell the setting either at the top level or inside an `env`
block, which is the shape Claude Code requires.
"""

from __future__ import annotations

import json
import os
from typing import Iterable, Mapping

ON = ("1", "on", "true", "yes")
OFF = ("0", "off", "false", "no")

USER_CONFIG = "~/.whats-next/config.json"


def read_json(path: str) -> dict:
    try:
        with open(path, encoding="utf-8") as f:
            obj = json.load(f)
        return obj if isinstance(obj, dict) else {}
    except (OSError, ValueError):
        return {}


def user_config() -> dict:
    return read_json(os.path.expanduser(USER_CONFIG))


def _in_map(settings: Mapping, var: str) -> str:
    env = settings.get("env")
    if isinstance(env, Mapping) and env.get(var) is not None:
        return str(env[var]).strip().lower()
    if settings.get(var) is not None:
        return str(settings[var]).strip().lower()
    return ""


def switch_value(settings: Iterable[Mapping], var: str) -> str:
    """What the named switch is set to, or "" when nobody has set it."""
    value = os.environ.get(var, "").strip().lower()
    if value:
        return value
    for source in settings:
        found = _in_map(source, var)
        if found:
            return found
    return _in_map(user_config(), var)


def convention_enabled(settings: Iterable[Mapping], var: str = "REPORT_GATE") -> bool:
    """True when turns in this directory are expected to end with a report."""
    return switch_value(settings, var) not in OFF
