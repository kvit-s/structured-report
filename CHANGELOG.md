# Changelog

Every version of the What's Next plugin, newest first. The version is the
`version` field in `plugins/whats-next/.claude-plugin/plugin.json`, which is
also what `claude plugin update` compares against to decide whether a machine
needs new files.

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
