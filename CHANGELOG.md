# Changelog

Every version of the What's Next plugin, newest first. The version is the
`version` field in `plugins/whats-next/.claude-plugin/plugin.json`, which is
also what `claude plugin update` compares against to decide whether a machine
needs new files.

## 0.5.0 — 2026-09-20

**It runs in Codex as well.** Codex's hooks follow Claude Code's closely —
`SessionStart` takes `hookSpecificOutput.additionalContext`, `Stop` is handed
`last_assistant_message` and `stop_hook_active` — so the adapter is mostly a
map of names. The one difference that shows: `{"decision": "block", "reason":
…}` there starts a new turn with the reason as its prompt rather than resuming
the one that just ended. The card is Codex's `ask_user_question`.

Installing is by hand for now. `codex/hooks.json` in this repository registers
`SessionStart`, `UserPromptSubmit`, `PostToolUse` and `Stop`; copy it into
`~/.codex/hooks.json` or a project's `.codex/hooks.json` with `$PLUGIN_ROOT`
replaced by the path to a clone, or install the repository as a Codex plugin,
where `$PLUGIN_ROOT` is set for you.

The turn is written down through `UserPromptSubmit` and `PostToolUse` rather
than read out of the transcript: Codex populates `transcript_path` and says
the transcript format is not a stable interface for hooks, while the
`PostToolUse` payload is documented. Shell calls arrive there as a list —
`["bash", "-lc", "git status"]` — and the adapter takes the command out of it
so the classifier judges what actually ran.

`ask_user_question`'s schema is not documented, so the adapter accepts the
spellings it is likely to use and leaves a call it cannot read alone, rather
than telling the user their card was malformed. As with Gemini CLI, this has
not been run against an installed Codex.

## 0.4.0 — 2026-09-20

**It runs in Gemini CLI as well.** `gemini extensions install
https://github.com/kvitapp/kvit-plugins.git` registers four hooks there:
`SessionStart` hands the model the convention with Gemini's own tool name and
limits in it, `AfterAgent` is the gate, and `BeforeAgent` and `AfterTool`
write down what the turn did. The card is Gemini's `ask_user`, whose header is
sixteen characters rather than twelve. Blocking is spelled `{"decision":
"deny", "reason": …}` there, which rejects the response the model just gave
and sends the reason back as a new prompt.

The recording hooks exist because Gemini hands every hook a `transcript_path`
that is stubbed and arrives empty, so there is no session record to read the
turn out of. `core/journal.py` keeps one instead, at
`~/.whats-next/sessions/<project>/<session>.jsonl`: a line per prompt and per
finished tool call, with tool inputs over 20,000 characters trimmed out, and
anything a fortnight old removed when a new session starts writing. If Gemini
CLI fills `transcript_path` in later, reading its own transcript would replace
two functions in the adapter and nothing else.

Two things are missing there compared with Claude Code. There is no `/report`
command, because a Gemini custom command cannot reliably find the extension's
own directory, so the history is read by running `report_last.py --history`
directly. And the card comes back without the prose that preceded it, since
Gemini hands over the response text only after the turn has finished.

None of this changes Claude Code, where the plugin behaves exactly as it did
in 0.3.0. Hooks now take `--host <name>` to say which adapter to load, which
is how the Gemini extension points the same scripts at its own adapter;
without it they load Claude Code's, as before.

The Gemini side is tested against payloads of the shape its documentation
gives, not yet against an installed Gemini CLI.

## 0.3.0 — 2026-09-20

**The rules and the agent are now separate code.** Everything the plugin knows
about how a turn should end — whether the turn changed anything, what a
well-formed card looks like, what the model is told when it is sent back, how a
report is drawn again — moved into `scripts/core/`, which names no tool and
opens no file. Everything that is true of Claude Code in particular moved into
`scripts/hosts/claude_code.py`: the transcript format and where transcripts
live, the settings files, which tools count as writing, the name
`AskUserQuestion` and the twelve-character header its card draws, and the JSON
its hooks are handed and may print. `scripts/report_lib.py` is gone, with its
contents split between the two.

Nothing about the plugin's behaviour in Claude Code changed. The same turns are
blocked for the same reasons with the same wording, the four switches work as
before, and `/report` prints what it printed.

The reason for the split is that the convention suits other coding agents, and
several of them can now run it: Gemini CLI has a blocking `AfterAgent` hook and
an `ask_user` tool, Codex has a `Stop` hook and `ask_user_question`, Grok Build
and OpenCode have the question tool without a turn-end hook that can send the
model back. Each of those needs an adapter of its own — a session-record reader,
a tool profile, and the JSON its hooks speak — and none of them needs a second
copy of the rules. `WHATS_NEXT_HOST` picks the adapter; `claude_code` is the
default and the only one shipped so far.

**The index of reports moved to `~/.whats-next/reports/<project>.jsonl`,** out
of Claude Code's directory, because a machine may run several agents over the
same repository and the history reads better in one place. Each record now says
which agent produced it. `/report history` still reads anything left in the old
`~/.claude/reports/<project>.jsonl`, so nothing has to be migrated; new lines
are written to the new place only.

**The switches can also be set in `~/.whats-next/config.json`,** as
`{"REPORT_GATE": "off"}`, for a machine-wide answer that belongs to no
particular agent. The environment still wins, and a project's
`.claude/settings.json` still beats the new file.

## 0.2.0 — 2026-09-20

**The install name changed, which breaks existing installs.** The plugin was
`structured-report` and the marketplace was `kvit-s`; they are now `whats-next`
and `kvit`, so the install line is `whats-next@kvit`. The repository also moved
to `github.com/kvitapp/kvit-plugins`, and GitHub redirects the old address for
both web and git use.

If you installed the plugin before this version, the surest way across is to
drop the old marketplace and add the new one:

```
claude plugin uninstall structured-report@kvit-s
claude plugin marketplace remove kvit-s
claude plugin marketplace add https://github.com/kvitapp/kvit-plugins.git
claude plugin install whats-next@kvit
```

The marketplace does also carry a `renames` map, `{"structured-report":
"whats-next"}`, which moves an installed plugin to its new slug on the next
update if your Claude Code is v2.1.193 or later. It covers the plugin's name,
not the marketplace's, so on a machine that added the marketplace as `kvit-s`
the four commands above are the reliable route.

Restart Claude Code afterwards. The session-start hook that sends the convention
runs only when a session begins, so a session that is already open keeps the
files it started with.

The name changed because "report" already means usage analytics in Anthropic's
plugin directory: `session-report` and `receipts` both read session transcripts
and produce statistics, so a third name ending in `-report` reads as another one
of those. The card of next steps is what the plugin is for, and "what's next" is
the phrase it saves you typing.

Nothing about how the plugin works changed, beyond the name it uses when it
speaks: the text it hands the model now opens "The What's Next convention is
active in this session", and the message shown when no Python can be found is
prefixed `whats-next:` instead of `structured-report:`. The scripts, the hooks,
the output style, the `/report` command and the four environment switches are
otherwise as they were in 0.1.3. `/report` kept its name because it reprints the
report half specifically, so the word is still accurate.

The marketplace entry also gained the fields plugin directories render —
`displayName`, `description`, `category`, `keywords`, `homepage`, `repository`
and `author` — which were empty before and would have produced a blank listing.

## 0.1.3 — 2026-09-20

**Fixed: the hooks did not run at all on macOS.** `hooks/python.sh` guarded its
pass-through arguments with `${1+"${passthrough[@]}"}`, but that guard sat
inside a function, where `$1` is the argument the function was called with
rather than anything the script received. When a hook was invoked with no
arguments after the script path, the array expanded empty, and bash 4.3 and
earlier reject that under `set -u` — which is the bash Apple ships as
`/bin/bash`. The shim exited before it ever reached the hook.

The two functions are now one loop over `python3`, `python` and `py -3`, and the
arguments come straight from `"$@"` with the empty case written out separately.

## 0.1.2 — 2026-09-20

**Fixed: on Windows the whole plugin could silently stop loading.** Claude Code
runs an installed plugin from a copy under `~/.claude/plugins/cache/`, not from
the marketplace clone, and it refreshes that copy while sessions are open.
Windows will not rename or delete a folder while a file under it is open, and
importing `report_lib` left a `__pycache__` folder inside the installed copy
that a running hook holds. When the refresh failed, Claude Code loaded nothing
from the plugin and said so only in its debug log, so every part of it
disappeared until it was installed again.

`hooks/python.sh` now exports `PYTHONDONTWRITEBYTECODE=1` and all four entry
points go through it, so the plugin no longer writes anything into its own
installed copy. A virus scanner or an editor holding a file there has the same
effect and nothing here can prevent that, so the README gained a section on
recognising this failure, along with the other Windows way the hooks stop
working: `bash` resolving to WSL's launcher rather than Git's.

## 0.1.1 — 2026-09-19

Documentation only, with the version bumped so that machines already running the
plugin would pick the new files up. The README gained the two commands that
update an installed copy, an explanation of why `claude plugin update` does
nothing when the version field has not moved, and the reinstall sequence that
works when a change went out without a bump.

## 0.1.0 — 2026-09-18

First release. A turn that edited files or ran commands ends with a short report
— one headline sentence, bullets for what changed, and a line saying how it was
checked — followed by a card of two to four labelled options picked with a
single key, and the agent acts on the pick within the same turn.

The plugin ships a Stop hook that checks how the turn ended and asks again when
the card is missing, a display hook for the on-screen markers, a `/report`
command that reprints the last report, an output style, and a test suite. The
Python shim probes `python3`, `python` and `py -3` in turn, skipping the
Microsoft Store stub that answers to `python3` on Windows without running
anything.

Later in 0.1.0's life, before the version number moved, a session-start hook was
added. Until then the convention reached the model only through the output
style, which Claude Code loads only when somebody picks it from the
`/output-style` menu, so the plugin installed cleanly and then did nothing. The
hook reads the same text out of `output-styles/report.md` with the frontmatter
stripped and hands it to the model at every session start, including after
`/clear`, a resume and a compaction, which makes installing the plugin the only
step. The style file stays selectable for anyone who already had
`"outputStyle": "report"` in their settings, and the hook stays quiet when it is
active rather than delivering the same text twice. The off switch became
`REPORT_GATE=off` at the same time, in the environment or in an `env` block in a
project's `.claude/settings.json`.
