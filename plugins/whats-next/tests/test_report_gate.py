#!/usr/bin/env python3
"""test_report_gate.py — checks for the Stop hook in report_gate.py.

Each case builds a small transcript by hand, runs the hook as Claude Code runs
it (JSON on stdin, JSON on stdout) and asserts what came back: nothing means
the turn may end, a `decision` of `block` means the model is sent back to write
a report, and a `systemMessage` alone means the turn ends with a note to the
user. Run it with `python3 ~/.claude/scripts/test_report_gate.py`.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
# The scripts sit beside this file in a plain install, and one directory over
# in the plugin, where the tests live in tests/ and the scripts in scripts/.
SCRIPTS = HERE if os.path.exists(os.path.join(HERE, "report_gate.py")) \
    else os.path.join(os.path.dirname(HERE), "scripts")
GATE = os.path.join(SCRIPTS, "report_gate.py")
CONTEXT = os.path.join(SCRIPTS, "report_context.py")
sys.path.insert(0, SCRIPTS)
import report_lib as lib  # noqa: E402

FAILURES: list[str] = []


# --------------------------------------------------------------- transcripts

def prompt(uuid: str = "u1", text: str = "do the thing") -> dict:
    return {"type": "user", "uuid": uuid, "message": {"content": text}}


def call(name: str, inp: dict, call_id: str) -> dict:
    return {"type": "assistant", "message": {"content": [
        {"type": "tool_use", "id": call_id, "name": name, "input": inp}]}}


def result(call_id: str, is_error: bool = False, tool_use_result=None) -> dict:
    entry = {"type": "user", "message": {"content": [
        {"type": "tool_result", "tool_use_id": call_id, "content": "ok",
         "is_error": is_error}]}}
    if tool_use_result is not None:
        entry["toolUseResult"] = tool_use_result
    return entry


def text(body: str) -> dict:
    return {"type": "assistant", "message": {"content": [
        {"type": "text", "text": body}]}}


def question(header: str = "Next", options=None, multi: bool = False) -> dict:
    options = options or [
        {"label": "Commit (Recommended)", "description": "Commit the change now."},
        {"label": "Add tests", "description": "Write tests first, then commit."},
        {"label": "Stop here", "description": "Leave it uncommitted; nothing more runs."},
    ]
    return {"questions": [{"question": "Ordering works, 14/14 tests pass. How to proceed?",
                           "header": header, "multiSelect": multi,
                           "options": options}]}


def ask_pair(payload: dict, call_id: str = "q1", answer: str = "Commit (Recommended)",
             is_error: bool = False) -> list[dict]:
    tur = {"questions": payload["questions"],
           "answers": {payload["questions"][0]["question"]: answer}}
    return [call("AskUserQuestion", payload, call_id),
            result(call_id, is_error=is_error, tool_use_result=None if is_error else tur)]


EDIT = [call("Edit", {"file_path": "/tmp/x.go"}, "e1"), result("e1")]
LOOK = [call("Bash", {"command": "git status && ls -la"}, "b1"), result("b1")]


# ------------------------------------------------------------------- harness

def run(entries: list[dict], *, last_message: str, session: str,
        workspace: str, stop_hook_active: bool = False,
        background: list | None = None, env: dict | None = None) -> dict:
    path = os.path.join(workspace, "transcript.jsonl")
    with open(path, "w", encoding="utf-8") as f:
        for e in entries:
            f.write(json.dumps(e) + "\n")
    payload = {
        "session_id": session,
        "transcript_path": path,
        "cwd": workspace,
        "hook_event_name": "Stop",
        "stop_hook_active": stop_hook_active,
        "last_assistant_message": last_message,
        "background_tasks": background or [],
        "session_crons": [],
    }
    proc = subprocess.run([sys.executable, GATE], input=json.dumps(payload),
                          capture_output=True, text=True,
                          env={**os.environ, **(env or {})})
    if proc.returncode != 0:
        return {"_exit": proc.returncode, "_stderr": proc.stderr}
    out = proc.stdout.strip()
    return json.loads(out) if out else {}


def check(name: str, condition: bool, detail: str = "") -> None:
    if condition:
        print(f"  ok   {name}")
    else:
        FAILURES.append(f"{name}: {detail}")
        print(f"  FAIL {name}: {detail}")


def workspace_with_env(root: str, value: str) -> str:
    """A project whose own settings set the switch, the way a repository that
    wants none of this would."""
    ws = tempfile.mkdtemp(dir=root)
    os.makedirs(os.path.join(ws, ".claude"))
    with open(os.path.join(ws, ".claude", "settings.json"), "w") as f:
        json.dump({"env": {"REPORT_GATE": value}}, f)
    return ws


def run_context(workspace: str, env: dict | None = None) -> dict:
    """The SessionStart hook, run the way Claude Code runs it."""
    payload = {"cwd": workspace, "hook_event_name": "SessionStart",
               "source": "startup"}
    proc = subprocess.run([sys.executable, CONTEXT], input=json.dumps(payload),
                          capture_output=True, text=True,
                          env={**os.environ, **(env or {})})
    out = proc.stdout.strip()
    return json.loads(out) if out else {}


def workspace_with_style(root: str, style: str | None) -> str:
    ws = tempfile.mkdtemp(dir=root)
    if style is not None:
        os.makedirs(os.path.join(ws, ".claude"))
        with open(os.path.join(ws, ".claude", "settings.local.json"), "w") as f:
            json.dump({"outputStyle": style}, f)
    return ws


# --------------------------------------------------------------------- cases

def gate_cases(root: str) -> None:
    ws = workspace_with_style(root, "report")
    off = workspace_with_style(root, "Concise")   # another style, so: off
    n = [0]

    def sid() -> str:
        n[0] += 1
        return f"test-session-{n[0]}"

    print("the gate")

    out = run(LOOK + [text("Here is what I found. Tests: none needed.")],
              last_message="Here is what I found.", session=sid(), workspace=ws)
    check("a turn that only looked may end", out == {}, json.dumps(out))

    out = run(EDIT + [text("Done: moved the loop. Tests: go test ./... 14/14 pass.")],
              last_message="Done: moved the loop. Tests: go test ./... 14/14 pass.",
              session=sid(), workspace=ws)
    check("a turn that changed something and offered nothing is blocked",
          out.get("decision") == "block" and "next step" in out.get("reason", ""),
          json.dumps(out)[:200])

    out = run(EDIT + ask_pair(question()) + [text("Committed.")],
              last_message="Committed.", session=sid(), workspace=ws)
    check("a well-formed answered ask ends the turn silently", out == {},
          json.dumps(out))

    long_header = question(header="Commit scope now",
                           options=[{"label": "Commit", "description": "Commit it."},
                                    {"label": "Add tests", "description": ""}])
    out = run(EDIT + ask_pair(long_header) + [text("Committed.")],
              last_message="Committed.", session=sid(), workspace=ws)
    msg = out.get("systemMessage", "")
    check("shape problems in an answered ask reach the user, not the model",
          "decision" not in out and "16 characters" in msg and "no description" in msg
          and "no way to stop" in msg, json.dumps(out)[:300])

    out = run(EDIT + ask_pair(question(), is_error=True) + [text("Sorry.")],
              last_message="Sorry.", session=sid(), workspace=ws)
    check("an ask that errored is worth another round trip",
          out.get("decision") == "block" and "did not go through" in out.get("reason", ""),
          json.dumps(out)[:200])

    out = run(EDIT + ask_pair(question()) + EDIT + [text("Also fixed the typo.")],
              last_message="Also fixed the typo.", session=sid(), workspace=ws)
    check("work done after the ask needs a fresh one",
          out.get("decision") == "block", json.dumps(out)[:200])

    out = run(LOOK + [text("I can fix it two ways. Do you want me to change the parser?")],
              last_message="I can fix it two ways. Do you want me to change the parser?",
              session=sid(), workspace=ws)
    check("a choice offered in prose is blocked",
          out.get("decision") == "block" and "nothing to click" in out.get("reason", ""),
          json.dumps(out)[:200])

    body = ("Done: renamed the flag.\nTests: go build ./... passes.\n"
            "No follow-up: you asked for the rename only.")
    out = run(EDIT + [text(body)], last_message=body, session=sid(), workspace=ws)
    check("a stated reason for no follow-up ends the turn", out == {}, json.dumps(out))

    body = "Done: renamed the flag.\nNo follow-up: you asked for the rename only."
    out = run(EDIT + [text(body)], last_message=body, session=sid(), workspace=ws)
    check("no follow-up without a verification line gets a note",
          "decision" not in out and "how the work was checked" in out.get("systemMessage", ""),
          json.dumps(out)[:300])

    session = sid()
    first = run(EDIT + [text("Done.")], last_message="Done.", session=session, workspace=ws)
    second = run(EDIT + [text("Done.")], last_message="Done.", session=session,
                 workspace=ws, stop_hook_active=True)
    third = run(EDIT + [text("Done.")], last_message="Done.", session=session,
                workspace=ws, stop_hook_active=True)
    check("the block budget runs out",
          first.get("decision") == "block" and second.get("decision") == "block"
          and "decision" not in third,
          json.dumps([first.get("decision"), second.get("decision"), third])[:200])

    plain = workspace_with_style(root, None)   # no output style named anywhere
    out = run(EDIT + [text("Done.")], last_message="Done.", session=sid(),
              workspace=plain)
    check("being installed is enough, with no output style named",
          out.get("decision") == "block", json.dumps(out)[:120])

    out = run(EDIT + [text("Done.")], last_message="Done.", session=sid(), workspace=off)
    check("another output style no longer switches it off",
          out.get("decision") == "block", json.dumps(out)[:120])

    out = run(EDIT + [text("Done.")], last_message="Done.", session=sid(), workspace=ws,
              env={"REPORT_GATE": "off"})
    check("REPORT_GATE=off switches it off", out == {}, json.dumps(out))

    quiet = workspace_with_env(root, "off")
    out = run(EDIT + [text("Done.")], last_message="Done.", session=sid(),
              workspace=quiet)
    check("a project switches it off in its own settings", out == {}, json.dumps(out))

    nested_on = os.path.join(quiet, "internal", "order")
    os.makedirs(os.path.join(nested_on, ".claude"), exist_ok=True)
    with open(os.path.join(nested_on, ".claude", "settings.local.json"), "w") as f:
        json.dump({"env": {"REPORT_GATE": "on"}}, f)
    out = run(EDIT + [text("Done.")], last_message="Done.", session=sid(),
              workspace=nested_on)
    check("the nearest settings win over the ones above them",
          out.get("decision") == "block", json.dumps(out)[:120])

    out = run(EDIT + [text("Done.")], last_message="Done.", session=sid(),
              workspace=quiet, env={"REPORT_GATE": "on"})
    check("the environment beats a project's settings",
          out.get("decision") == "block", json.dumps(out)[:120])

    out = run(EDIT + [text("Done.")], last_message="Done.", session=sid(), workspace=ws,
              background=[{"id": "t1", "type": "shell", "status": "running",
                           "description": "tail logs"}])
    check("a session waiting on background work is left alone", out == {}, json.dumps(out))

    print("the index")
    fresh = workspace_with_style(root, "report")   # its own index file
    session = sid()
    entries = [prompt("u9")] + EDIT + ask_pair(question()) + [text("Committed.")]
    run(entries, last_message="Committed.", session=session, workspace=fresh)
    run(entries, last_message="Committed.", session=session, workspace=fresh)
    records = lib.read_index(fresh, limit=10)
    check("an answered ask is indexed once, not twice",
          len(records) == 1 and records[0]["kind"] == "ask"
          and records[0]["answers"], json.dumps(records)[:300])

    body = ("Done: renamed the flag.\nTests: go build ./... passes.\n"
            "No follow-up: you asked for the rename only.")
    run([prompt("u10")] + EDIT + [text(body)], last_message=body, session=sid(),
        workspace=fresh)
    records = lib.read_index(fresh, limit=10)
    check("an ending with no follow-up is indexed too",
          len(records) == 2 and records[1]["kind"] == "done"
          and records[1]["verification"].startswith("Tests:"),
          json.dumps(records)[-300:])

    print("the gate, continued")
    out = run([prompt(), call("Agent", {"prompt": "look around"}, "a1"), result("a1"),
               text("The agent found three callers.")],
              last_message="The agent found three callers.", session=sid(), workspace=ws)
    check("a subagent call is not by itself work done", out == {}, json.dumps(out))


def library_cases() -> None:
    print("shell commands")
    for cmd, expected in [
        ("ls -la", True),
        ("git status && git log --oneline -5", True),
        ("sed -n '1,20p' file.go", True),
        ("grep -rn foo . | head -20", True),
        ("cat a.txt > b.txt", False),
        ("sed -i s/a/b/ file.go", False),
        ("go test ./...", False),
        ("git commit -m x", False),
        ("python3 - <<'PY'\nprint(1)\nPY", False),
        ("rm -rf build", False),
        ("echo hi", True),
        ("find . -name '*.go' -delete", False),
        # the PowerShell tool, which is what a Windows session uses
        ("Get-ChildItem -Recurse", True),
        ("Get-Content .\\go.mod | Select-String module", True),
        ("git status; git log -3", True),
        ("Set-Content .\\x.txt 'hi'", False),
        ("Get-ChildItem | ForEach-Object { Remove-Item $_ }", False),
        ("Remove-Item -Recurse build", False),
        ("Get-ChildItem *.go | Out-File list.txt", False),
    ]:
        got = lib.shell_is_readonly(cmd)
        check(f"{cmd.splitlines()[0]!r} reads only = {expected}", got == expected,
              f"got {got}")

    print("the ask itself")
    hard, soft = lib.ask_problems({"questions": [{
        "question": "Which?", "header": "Pick",
        "options": [{"label": "A (Recommended)", "description": "does a"},
                    {"label": "B", "description": "does b"}]}]})
    check("a clean ask has no problems", not hard and not soft, f"{hard} {soft}")

    hard, _ = lib.ask_problems({"questions": [{
        "question": "Which?", "header": "Pick",
        "options": [{"label": "only one", "description": "x"}]}]})
    check("one option is a hard problem", any("options" in p for p in hard), str(hard))

    _, soft = lib.ask_problems({"questions": [{
        "question": "Which?", "header": "Pick",
        "options": [{"label": "A", "description": "does a"},
                    {"label": "B (Recommended)", "description": "does b"}]}]})
    check("a recommendation out of first place is noted",
          any("position 2" in p for p in soft), str(soft))

    print("the closing prose")
    check("a question in the last lines counts",
          lib.offers_choice_in_prose("Done.\n\nShould I commit this?") is not None)
    check("a question further up does not",
          lib.offers_choice_in_prose(
              "Should I have used a map? No.\n\n" + "\n".join(["filler"] * 6)
              + "\nDone: it uses a slice.\nTests: all pass.") is None)
    check("a verification line is recognised",
          not lib.prose_problems("Done: x.\nTests: go test ./... passes."))
    check("its absence is noticed",
          any("checked" in p for p in lib.prose_problems("Done: x.")))
    check("saying what is unverified counts too",
          not lib.prose_problems("Done: x.\nI did not run the suite; no network."))


def context_cases(root: str) -> None:
    print("the convention at session start")
    plain = workspace_with_style(root, None)
    body = (run_context(plain).get("hookSpecificOutput") or {}).get("additionalContext", "")
    check("the convention is delivered when no output style is named",
          "How a turn ends" in body and "AskUserQuestion" in body, body[:140])
    check("it says what it is before the rules",
          body.startswith("The What's Next convention"), body[:80])
    check("the frontmatter is stripped off",
          "keep-coding-instructions" not in body and not body.lstrip().startswith("---"),
          body[:80])

    styled = workspace_with_style(root, "report")
    out = run_context(styled)
    check("it stays quiet when the output style already sends the same text",
          out == {}, json.dumps(out)[:140])

    out = run_context(plain, env={"REPORT_GATE": "off"})
    check("REPORT_GATE=off stays quiet", out == {}, json.dumps(out)[:140])

    out = run_context(workspace_with_env(root, "off"))
    check("a project that switched it off gets nothing", out == {}, json.dumps(out)[:140])


def display_cases() -> None:
    print("the markers on screen")
    import report_display as disp
    got = disp.mark("Done: it works.\nTests: go test ./... 14/14 pass.\n")
    check("a verification line is marked", got == "Done: it works.\n\u2713 Tests: go test ./... 14/14 pass.\n", repr(got))
    got = disp.mark("Done.\nNo follow-up: you asked for one thing.\n")
    check("a no-follow-up line is marked", got == "Done.\n\u00b7 No follow-up: you asked for one thing.\n", repr(got))
    check("ordinary prose is left alone", disp.mark("One thing: it works.\n") is None)
    check("a fenced line is left alone", disp.mark("```\nTests: inside\n```\n") is None)
    check("an unfinished line waits for its batch",
          disp.mark("Tests: still streaming") is None)


def main() -> int:
    root = tempfile.mkdtemp(prefix="report-gate-tests-")
    # The switch and the output style are both read by walking up from the
    # working directory and falling back to ~/.claude/settings.json, so the
    # suite needs a home of its own or the machine it runs on decides the
    # answers. Keeping it inside root means the cleanup below removes the
    # report index files too.
    home = os.path.join(root, "home")
    os.makedirs(os.path.join(home, ".claude"), exist_ok=True)
    os.environ["HOME"] = home
    os.environ["USERPROFILE"] = home
    try:
        library_cases()
        display_cases()
        context_cases(root)
        gate_cases(root)
    finally:
        shutil.rmtree(root, ignore_errors=True)
        state = os.path.join(tempfile.gettempdir(), "report_gate_state")
        for name in os.listdir(state) if os.path.isdir(state) else []:
            if name.startswith("test-session-"):
                os.remove(os.path.join(state, name))
    print()
    if FAILURES:
        print(f"{len(FAILURES)} failed:")
        for f in FAILURES:
            print(f"  - {f}")
        return 1
    print("all checks pass")
    return 0


if __name__ == "__main__":
    sys.exit(main())
