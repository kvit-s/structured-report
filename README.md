# structured-report

A Claude Code plugin. It changes how a turn ends: instead of a paragraph saying
the work is done, a turn that edited files or ran commands finishes with a short
report and a question you answer by clicking one of two to four options.

## The problem it addresses

When Claude finishes a piece of work, the thing you have to act on — do this
next, or answer that, or it stopped because of this — sits inside prose. You
read the paragraph, then type "what's next" or "continue", and pay for another
round trip to get back to where the work was already pointing.

Claude Code already has the right widget for this: the `AskUserQuestion` tool
draws a card of labelled options, keyboard-selectable, with free text always
available, and it renders the same way in the terminal, the IDE extension, the
desktop app and the web. This plugin makes that call the way a working turn
ends, and checks that it happened.

There is no second format. The question, its options and the answer you gave are
an ordinary tool call in the session transcript, which is what `/report` reads
back and what the index below is built from.

## What it installs

**An output style, `report`.** The instructions Claude follows: write the prose
first — one headline sentence with the material fact, bullets for what changed,
a `Tests:` or `Checks:` line saying how it was verified — then call
`AskUserQuestion` with continuations it would actually carry out, plus an
explicit "Stop here". It keeps Claude Code's built-in engineering instructions,
so it changes how a turn ends and nothing else.

**A Stop hook.** It reads the transcript back to your last message and blocks in
three cases: the turn changed something and offered nothing; the closing text
asks you to choose but no `AskUserQuestion` call was made, so there is nothing to
click; a call came back as an error, meaning no card was drawn. It blocks at most
twice per prompt, well inside Claude Code's own ceiling of eight, and stays
silent while background tasks are still running.

Problems with a card you already answered — a header too long to fit, an option
with no description, no way to stop, a misplaced "(Recommended)" — do not block.
Sending Claude back would only put a second, tidier card in front of you for a
question you have answered, so those print as a note to you and the turn ends.

**A `/report` command.** Reprints the last report of the session: the closing
text, the question, every option with its description, and the one you picked.
`/report 3` shows the last three. `/report history` lists one line per report
across every session in the current directory.

**A MessageDisplay hook,** which marks the `Tests:` line and a `No follow-up:`
line in the left margin as a message streams. Display only: the transcript and
what Claude sees keep the original text.

## Install

```
/plugin marketplace add https://github.com/kvit-s/structured-report.git
/plugin install structured-report@kvit-s
/output-style report
```

The first two commands add the plugin and its hooks. Nothing changes until the
third: the hook checks which output style is active and does nothing unless it is
this one, so `/output-style default` switches the whole convention off again. If
the install summary says `Run /reload-plugins to activate`, do that or restart
before the hooks fire.

The shorthand `/plugin marketplace add kvit-s/structured-report` works too, but
Claude Code expands it to an SSH address, so it needs a GitHub key on that
machine. The full `https://` URL above needs nothing, and setting
`CLAUDE_CODE_PLUGIN_PREFER_HTTPS=1` makes the shorthand use HTTPS as well.

A project can override the style for its own directory: a `.claude/settings.local.json`
naming a different `outputStyle` turns the convention off there, whatever the
user-level setting says.

## What a turn looks like afterwards

> Reordering works and survives a restart.
> - Moved the reorder logic into `internal/order`, hidden rows keep their slots.
> - Tests: `go test ./internal/order` — 14/14 pass.

followed by a card:

```
  Reordering works, 14/14 tests pass. How to proceed?          [Next]
  -> Commit (Recommended)   Commit the reorder implementation now.
     Changelog too          Add the changelog entry, then commit.
     Stop here              Leave it uncommitted; nothing more runs.
```

Picking an option resumes the same turn, so Claude acts on the answer
immediately rather than waiting for your next prompt.

When there is nothing to propose — you asked for one thing and said stop, or no
follow-up exists — the turn ends in prose whose last line reads
`No follow-up: <why>.` and the hook accepts that.

## Where things are kept

Nothing is duplicated. The report is the `AskUserQuestion` call in the session
transcript, which Claude Code already writes.

For reading back and for feeding a changelog, the Stop hook also appends one
line per finished report to `~/.claude/reports/<project>.jsonl`: the time, the
session, the git branch, the headline, the verification line, and the questions
with your answers. A turn that stops twice is recorded once. Deleting the file
loses nothing that matters.

## Requirements

Python 3.8 or later, under any of the names `python3`, `python` or `py -3`. No
packages: the four scripts use the standard library only.

`hooks/python.sh` finds the interpreter. It tries each name in turn and asks it
to report its own version, so the Microsoft Store stub that Windows installs as
`python3` falls through to a real Python. It also exports `PYTHONUTF8=1`, without
which Python on Windows reads files in the console code page and fails on any
path or transcript holding a character outside it. If no Python is found, the
hook says so once and then stays quiet.

The shim runs under bash, so on Windows it needs Git Bash — the same requirement
Anthropic's own `security-guidance` plugin has. On a Windows machine without Git
Bash, register the hooks by hand in `settings.json` instead, calling
`C:\Windows\py.exe` with `-3` and the script path as `args`.

## Switches

| Variable | Effect |
|---|---|
| `REPORT_GATE=off` | The Stop hook does nothing, whatever style is active. `on` forces it without the style. |
| `REPORT_CARD_DISPLAY=off` | No screen markers. |
| `REPORT_GATE_MAX_BLOCKS` | How many times one prompt may be blocked before the hook gives up. Default 2. |
| `REPORT_GATE_MUTATING_TOOLS` | Extra tool names to count as work done, space or comma separated. |

## Tests

```
python3 plugins/structured-report/tests/test_report_gate.py
```

Builds transcripts by hand, runs the hook the way Claude Code runs it — JSON on
stdin, JSON on stdout — and checks what came back: every block and allow path,
the block budget, the index, the screen markers, output-style precedence across
nested directories, and the classifier that decides whether a shell or PowerShell
command changed anything.

## Layout

```
.claude-plugin/marketplace.json        the catalogue
plugins/structured-report/
  .claude-plugin/plugin.json           the manifest
  hooks/hooks.json                     Stop and MessageDisplay
  hooks/python.sh                      finds an interpreter, execs it
  scripts/report_lib.py                transcript parsing, checks, the card
  scripts/report_gate.py               the Stop hook
  scripts/report_display.py            the MessageDisplay hook
  scripts/report_last.py               what /report runs
  skills/report/SKILL.md               the /report command
  output-styles/report.md              the convention itself
  tests/test_report_gate.py
```

## Licence

MIT. See [LICENSE](LICENSE).
