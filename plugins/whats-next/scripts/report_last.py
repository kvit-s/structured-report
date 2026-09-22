#!/usr/bin/env python3
"""report_last.py — reprint the last report of a session.

A turn that changes something ends with a call of the question tool: the prose
before it is the headline and what changed, the options are the ways forward,
and the user's pick is the answer. All of that is already in the session
record the agent writes, so bringing the card back is a matter of reading it
out again rather than keeping a copy somewhere.

This is what the `/report` command runs. With no arguments it prints the most
recent card of the current session; `-n 3` prints the last three, oldest last.

    report_last.py [--session ID] [--cwd DIR] [-n N] [--json]
    report_last.py --history [N]

`--history` prints one line per report from every session in this directory,
oldest first, out of the index the turn-end hook keeps in
`~/.whats-next/reports/<project>.jsonl`, together with anything left in the
pre-0.3.0 location under `~/.claude/reports/`. That index is a convenience for
reading back and for feeding a changelog; the session record remains the
account of what happened.

`--session` takes a session id; without it, or when the id does not name a
session record, the newest one for the working directory is used, which is
this session in all but the case of two open on the same directory.
"""

from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from core import card, index as index_mod, turn as turn_mod  # noqa: E402
from hosts import load as load_host  # noqa: E402

try:   # a card can hold any character the model wrote; a Windows console
       # would otherwise refuse the ones outside its code page
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


def local_time(stamp: str) -> str:
    if not stamp:
        return ""
    try:
        import datetime as dt
        parsed = dt.datetime.fromisoformat(stamp.replace("Z", "+00:00"))
        return parsed.astimezone().strftime("%Y-%m-%d %H:%M")
    except Exception:
        return stamp


def print_history(cwd: str, limit: int, as_json: bool) -> int:
    records = index_mod.read_index(cwd, limit=max(1, limit))
    if not records:
        print("No reports recorded for this directory yet.")
        return 0
    if as_json:
        print(json.dumps(records, indent=2))
        return 0
    for rec in records:
        when = local_time(rec.get("ts") or "")
        branch = rec.get("branch") or ""
        print(f"{when}  {branch:<12} {rec.get('headline') or ''}")
        verification = (rec.get("verification") or "")[:100]
        if verification:
            print(f"{'':<18}  {'':<12} {verification}")
        for question, answer in (rec.get("answers") or {}).items():
            shown = answer if isinstance(answer, str) else ", ".join(answer)
            print(f"{'':<18}  {'':<12} -> {shown}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(add_help=True)
    ap.add_argument("--session", default="")
    ap.add_argument("--host", default="")
    ap.add_argument("--cwd", default=os.getcwd())
    ap.add_argument("-n", "--count", type=int, default=1)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--history", nargs="?", type=int, const=10, default=None,
                    metavar="N")
    args = ap.parse_args()

    if args.history is not None:
        return print_history(args.cwd, args.history, args.json)

    host = load_host(args.host)
    session = args.session.strip()
    if "$" in session or "{" in session:   # placeholder arrived unsubstituted
        session = ""

    path = host.transcript_for_session(args.cwd, session) if session else None
    if not path:
        path = host.newest_transcript(args.cwd)
    if not path:
        print("No session record found for this directory.")
        return 1

    reports = turn_mod.find_reports(host.read_events(path), host.PROFILE,
                                    limit=max(1, args.count))
    if not reports:
        print(f"No report in this session yet ({os.path.basename(path)}).\n"
              f"A report is the {host.PROFILE.ask_tool} call a turn ends with.")
        return 0

    if args.json:
        print(json.dumps(reports, indent=2))
        return 0

    for i, rec in enumerate(reports):
        if i:
            print("\n" + "-" * 72 + "\n")
        print(card.render_card(rec.get("input") or {}, rec.get("answers"),
                               prose=rec.get("prose") or "",
                               when=local_time(rec.get("when") or "")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
