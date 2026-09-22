# Changelog

Every version of the What's Next plugin, newest first. The version is the
`version` field in `plugins/whats-next/.claude-plugin/plugin.json`, which is
also what `claude plugin update` compares against to decide whether a machine
needs new files.

## 0.7.0 — 2026-09-22

**Gemini CLI support is removed too, and the plugin is a Claude Code plugin
again.** Gone with it: `hosts/gemini_cli.py`, the extension manifest and its
`hooks/hooks.json`, `scripts/report_record.py`, and `core/journal.py`, which
existed only because Gemini hands its hooks a `transcript_path` that is
stubbed and arrives empty. Nothing else needed them.

The reason is the same one that removed Codex in 0.6.0, applied honestly: the
Gemini adapter was written against documentation and never run against an
installed Gemini CLI. Codex looked just as convincing on paper and turned out,
in a real session, to draw the card and carry on without waiting for it —
which is the one behaviour the convention depends on. Shipping a second host
on that footing means asking people to find that out for themselves.

**The split between the rules and the agent stays.** `core/` still names no
tool and opens no file, `hosts/claude_code.py` still holds everything true of
Claude Code alone, and the test suite still runs the same decisions through an
invented second agent whose tools have other names, whose card takes other
numbers and whose question tool has been renamed once. That is what keeps
Claude Code's names out of the rules, and what a port would start from.
Nothing about the plugin's behaviour in Claude Code has changed since 0.3.0.

## 0.6.0 — 2026-09-22

**Codex support is removed.** The adapter, its hook file and its tests are
gone, and the README no longer offers it. What the plugin needs from a host is
a card whose answer comes back inside the turn, and Codex's Default
collaboration mode is specified not to work that way. Its own per-turn
instructions, which arrive with every request, say to prefer making reasonable
assumptions over stopping to ask, to use `request_user_input` only for
optional questions, and — the deciding line — to "continue with best judgment"
when the tool returns no answers rather than treating the turn as blocked.

That is what a real session did: the model built a correct card, Codex drew it
as an asynchronous question reading `Questions 0/1 answered`, the turn
finished without waiting, and the call returned `{"answers":{}}`. There is a
second mode, Plan, where asking may well block, but it has no command-line
switch and Codex states that neither tool descriptions nor user requests
change the mode, so nothing the plugin says can reach it.

Enforcing a card there would mean overriding the host's own instructions to
produce a question nobody answers. The work is in the history if Codex's
modes change: 0.5.0 through 0.5.3 record the hook contract, the tool names,
the trust prompt and the `id` requirement, and `core/` still knows nothing
about any particular agent.

**What the Codex work left behind, because it is useful anywhere.** A profile
can list other names its question tool has had and carry one sentence of
host-specific guidance. A turn let through after the block budget runs out is
written to the index. A closing text saying the question tool is unavailable
ends the turn instead of being sent back. All four are covered by the tests
that run the rules through an invented second agent.

If you registered the Codex hooks by hand, remove `~/.codex/hooks.json`, or
the four hooks will fail on every turn now that the adapter is gone.

## 0.5.3 — 2026-09-22

**Two things a real Codex card exposed.** Codex rejects `request_user_input`
outright when a question has no `id` — "failed to parse function arguments:
missing field `id`" — which cost a round trip every time, so the convention
now tells the model to include one. And an answer comes back keyed by that
`id` rather than by the question, so it is keyed back to the question text on
the way in; without that a pick would have been filed under `next_action` and
read back as unanswered.

**What the card does in Codex is worth knowing before you install it there.**
In the default mode, codex-cli 0.155.1 posts the question asynchronously: the
terminal shows `Questions 0/1 answered` and the turn finishes without waiting
for a pick. The options are drawn and can be answered afterwards, but the
answer does not arrive inside the turn, which is the round trip this
convention exists to save under Claude Code. A hook cannot change that. What
Codex users still get is the convention itself and the check on how a turn
ends. The README says so plainly rather than implying parity.

## 0.5.2 — 2026-09-22

**Codex hides the card behind a feature flag, and the gate now copes when it
is off.** In codex-cli 0.155.1 `request_user_input` is not offered in the
default mode unless `default_mode_request_user_input` is enabled, and it is
never offered in `codex exec`. A session without it produced two blocks in a
row and endings like "the follow-up selector is unavailable in this mode",
which no amount of sending the model back could fix.

So a closing text that says the question tool is unavailable now ends the
turn, the way `No follow-up:` does, with the reason kept in the index rather
than printed. The convention text also tells the model what to do when the
tool is missing instead of leaving it to improvise, and the README says which
flag to turn on, that Codex warns the flag is under development, and that CI
wants `REPORT_GATE=off`.

The README also records where Codex keeps hook trust — a
`[hooks.state."<file>:<event>:0:0"]` table per hook in `config.toml`, holding
a `trusted_hash` — so it is clear why changing `hooks.json` brings the review
prompt back.

## 0.5.1 — 2026-09-22

**Tried it on a real Codex, and fixed what that turned up.** Against codex-cli
0.155.1 the convention arrives at session start, the journal is written, and a
turn that changed a file and ended with bare prose is blocked, after which
Codex sends the reason back and the model rewrites its ending — the whole loop,
working. Three things were wrong in 0.5.0:

- The card is called `request_user_input` there, not `ask_user_question`, and
  its own description says one to three questions. A profile can now list other
  names the same tool has had, so a call under either name is recognised.
- Codex reports its shell tool to hooks as `Bash`, with the command as a
  string. Without that name in the profile, a turn that only ran commands
  looked like a turn that did nothing.
- `$PLUGIN_ROOT` is not set for hooks registered by hand, and the feature that
  let plugins ship hooks is gone from this version, so `codex/hooks.json` now
  uses `$WHATS_NEXT_ROOT`, which you either substitute or export.

**A turn that ends after the block budget runs out is now written to the
index.** It used to be allowed through and forgotten, which is the one ending
you most want a record of. The record says how many times the prompt was
blocked before it was let through. This applies to every host.

Codex also asks before running new hooks: the first interactive session says
they need review, `/hooks` approves them, and `codex exec
--dangerously-bypass-hook-trust` skips the approval for one run. The README
says so now, since the failure mode is silence.

Still unchecked: the card itself, which `codex exec` cannot draw. In that
environment the gate costs one extra round trip per turn that changes
something, so `REPORT_GATE=off` belongs in CI.

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
