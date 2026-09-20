"""core/index.py — the short record of reports, one file per project.

Nothing is duplicated: the report is the question tool's call in the session
record the agent already writes, and `/report` reads it back from there. This
index exists for the two things that record is bad at — looking across
sessions, and feeding a changelog — and holds one line per finished report:
the time, the session, the branch, the headline, the verification line and the
questions with the answers given. Deleting the file loses nothing that matters.

It lives at `~/.whats-next/reports/<project>.jsonl`, outside any one agent's
directory, because a machine may run several agents over the same repository
and the history reads better in one place. Up to version 0.2.0 it was
`~/.claude/reports/<project>.jsonl`; that file is still read when it exists, so
older history stays visible, and nothing is written there any more.
"""

from __future__ import annotations

import json
import os
import re


def project_key(cwd: str) -> str:
    return re.sub(r"[^A-Za-z0-9]", "-", os.path.abspath(cwd or ".")).strip("-")


def index_path(cwd: str) -> str:
    return os.path.expanduser(f"~/.whats-next/reports/{project_key(cwd)}.jsonl")


def legacy_index_path(cwd: str) -> str:
    return os.path.expanduser(f"~/.claude/reports/{project_key(cwd)}.jsonl")


def already_indexed(path: str, key: str, tail: int = 200) -> bool:
    try:
        with open(path, encoding="utf-8") as f:
            lines = f.readlines()[-tail:]
    except OSError:
        return False
    return any(f'"key": "{key}"' in ln or f'"key":"{key}"' in ln for ln in lines)


def record_report(cwd: str, record: dict) -> None:
    """Append one report, skipping one that is already there. A turn that is
    stopped twice reaches this twice and is recorded once."""
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


def _read_file(path: str) -> list[dict]:
    out: list[dict] = []
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                try:
                    out.append(json.loads(line))
                except ValueError:
                    continue
    except OSError:
        return []
    return out


def read_index(cwd: str, limit: int = 10) -> list[dict]:
    """The last `limit` reports for this project, oldest first. Anything in
    the pre-0.3.0 location comes first, since nothing is written there now."""
    records = _read_file(legacy_index_path(cwd)) + _read_file(index_path(cwd))
    return records[-limit:]
