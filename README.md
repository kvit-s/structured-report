# What's Next

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

**A SessionStart hook,** which gives Claude the convention at the start of
every session: write the prose first — one headline sentence with the material
fact, bullets for what changed, a `Tests:` or `Checks:` line saying how it was
verified — then call `AskUserQuestion` with continuations it would actually
carry out, plus an explicit "Stop here". It is added to whatever Claude Code
already sends, so it changes how a turn ends and nothing else. It runs again
after `/clear`, after a resume and after the context is compacted.

Installing the plugin is the whole switch. Claude Code loads an output style
only when somebody picks it from a menu, so delivering the convention this way
is what makes the plugin work the moment it is installed; Anthropic's own
`explanatory-output-style` and `learning-output-style` plugins do the same.

**An output style, `report`,** holding the text the hook reads, so the
convention is written down in one place. Selecting it with `/output-style
report` is optional and changes nothing, beyond replacing Claude Code's own
response-style instructions rather than adding to them; the hook notices it is
active and stays quiet rather than saying the same thing twice.

**A Stop hook,** the part that checks the convention was followed. It reads the
transcript back to your last message and blocks in three cases: the turn changed
something and offered nothing; the closing text asks you to choose but no
`AskUserQuestion` call was made, so there is nothing to click; a call came back
as an error, meaning no card was drawn. It blocks at most twice per prompt, well
inside Claude Code's own ceiling of eight, and stays silent while background
tasks are still running.

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
/plugin install whats-next@kvit
```

That is all. The next session starts with the convention in force, and removing
the plugin removes it — there is nothing to select and nothing left behind. If
the install summary says `Run /reload-plugins to activate`, do that or restart
first, and the convention arrives at the following session start rather than in
the middle of this one.

The shorthand `/plugin marketplace add kvit-s/structured-report` works too, but
Claude Code expands it to an SSH address, so it needs a GitHub key on that
machine. The full `https://` URL above needs nothing, and setting
`CLAUDE_CODE_PLUGIN_PREFER_HTTPS=1` makes the shorthand use HTTPS as well.

A project can switch it off for its own directory without uninstalling
anything, by setting the switch in `.claude/settings.json` beside it:

```json
{ "env": { "REPORT_GATE": "off" } }
```

The hooks walk up from the working directory reading `.claude/settings.local.json`
then `.claude/settings.json` at each level, take the first answer they find and
fall back to `~/.claude/settings.json`, so the nearest setting wins and a
subdirectory can turn it back on. A value in the real environment beats all of
them.

## Updating

Installing copies the plugin's files into
`~/.claude/plugins/cache/<marketplace>/whats-next/<version>/`, and that
copy stays at the commit it was taken from until it is updated. On a machine
where the plugin is already installed, two commands bring it up to date:

```
claude plugin marketplace update kvit
claude plugin update whats-next@kvit
```

The first pulls this repository into the local clone of the marketplace; without
it the second has nothing new to look at. Restart Claude Code afterwards, since
the update says `Restart to apply changes` and a running session keeps the files
it started with. Inside a session, `/plugin` offers the same actions.

The second command decides by the `version` field in
`plugins/whats-next/.claude-plugin/plugin.json`. If that number has not
changed since the machine installed the plugin, it answers `already at the
latest version` and copies nothing, however many commits were pushed in the
meantime. Bump it with every change other machines should pick up. When a change
did go out without a bump, reinstalling takes the current files whatever the
version says:

```
claude plugin marketplace update kvit
claude plugin uninstall whats-next@kvit
claude plugin install whats-next@kvit
```

## When it stops running on Windows

The failure looks like the plugin having been switched off: turns stop ending
with a question, the Stop hook never fires, `/report` is gone, and nothing says
why. `/plugin` still lists it as installed, and reinstalling it brings it back.

What happened is that the whole plugin failed to load for that session, so none
of its parts exist. Claude Code does not run an installed plugin from the clone
of this repository under `~/.claude/plugins/marketplaces/kvit/`. It copies the
plugin into `~/.claude/plugins/cache/kvit/whats-next/<version>/` and
runs it from there. When it cannot refresh that copy it does not fall back to
the clone; it loads nothing from the plugin and writes the reason to the debug
log, where its own wording is that reinstalling the plugin retries the copy.
A once-a-day cleanup of cached plugin folders that no running session has marked
as in use can take the folder away as well, which the log reports as the
directory having been removed before it could be loaded.

Windows is where the copy fails, because it will not rename or delete a folder
while any file under it is open. Until 0.1.2 this plugin caused that itself:
importing `report_lib` left a `__pycache__` folder inside the installed copy,
and a hook's Python holds those files whenever it runs, which with a Stop hook
and a display hook is most of the time. `hooks/python.sh` now exports
`PYTHONDONTWRITEBYTECODE=1`, so nothing of this plugin is written there any
more. A virus scanner, a file indexer or an editor holding a file in that folder
has the same effect, and nothing here can prevent that.

The hooks can also stop working without any of that. They run `bash
hooks/python.sh`, and on a machine with WSL installed
`C:\Windows\System32\bash.exe` is always on the path, while Git's `bash.exe`
sits in `C:\Program Files\Git\bin`, which Git adds to the path only under one
of its setup options. Which one a session gets depends on the path of the
terminal Claude Code was started from, so the same install can work in one
window and fail in the next — with a visible error this time rather than
silence. `where.exe bash` says which one wins, putting Git's `bin` folder ahead
of `System32` in `PATH` settles it, and registering the hooks by hand as
described under [Requirements](#requirements) avoids `bash` altogether.

Four commands tell these apart. Run them while it is broken, before reinstalling:

```powershell
dir "$env:USERPROFILE\.claude\plugins\cache\kvit\whats-next"
dir "$env:USERPROFILE\.claude\plugins\marketplaces\kvit"
where.exe bash
claude --debug
```

A missing or half-empty version folder in the first is the copy having failed.
A folder with `hooks\hooks.json` in it, together with `System32\bash.exe` from
the third, points at `bash` instead. `claude --debug` prints what the loader
decided at startup, and the lines to look for name this plugin.

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
packages: the five scripts use the standard library only.

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
| `REPORT_GATE=off` | The convention is not sent and the Stop hook does nothing. |
| `REPORT_CARD_DISPLAY=off` | No screen markers. |
| `REPORT_GATE_MAX_BLOCKS` | How many times one prompt may be blocked before the hook gives up. Default 2. |
| `REPORT_GATE_MUTATING_TOOLS` | Extra tool names to count as work done, space or comma separated. |

## Tests

```
python3 plugins/whats-next/tests/test_report_gate.py
```

Builds transcripts by hand, runs the hook the way Claude Code runs it — JSON on
stdin, JSON on stdout — and checks what came back: every block and allow path,
the block budget, the index, the screen markers, the text the SessionStart hook
delivers, the switch resolving across nested directories, and the classifier that
decides whether a shell or PowerShell command changed anything. The suite gives
itself a temporary home directory, so the settings on the machine running it
cannot change the answers.

## Layout

```
.claude-plugin/marketplace.json        the catalogue
plugins/whats-next/
  .claude-plugin/plugin.json           the manifest
  hooks/hooks.json                     SessionStart, Stop and MessageDisplay
  hooks/python.sh                      finds an interpreter, execs it
  scripts/report_lib.py                transcript parsing, checks, the card
  scripts/report_context.py            the SessionStart hook
  scripts/report_gate.py               the Stop hook
  scripts/report_display.py            the MessageDisplay hook
  scripts/report_last.py               what /report runs
  skills/report/SKILL.md               the /report command
  output-styles/report.md              the convention itself, read by the hook
  tests/test_report_gate.py
```

## Licence

MIT. See [LICENSE](LICENSE).
