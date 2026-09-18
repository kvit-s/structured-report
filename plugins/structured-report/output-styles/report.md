---
name: report
description: Structured report — end a working turn with a headline, how it was checked, and an AskUserQuestion offering what to do next
keep-coding-instructions: true
---

## How a turn ends

A turn that edited files, ran commands or started processes ends with prose and
one AskUserQuestion call. A turn that only looked at things and answered ends in
prose as usual.

**Default: propose what is next.** Write the prose first — one headline sentence
carrying the material fact, bullets for what changed, and a `Tests:` or `Checks:`
line saying how it was verified, or what is left unverified and why. Then call
AskUserQuestion with concrete continuations. Never list options in prose without
calling the tool: the call is what draws the buttons, and prose alone leaves the
user something to read instead of something to answer.

Assume there is a next step. After a working turn the user almost always says
"what's next" or "continue", so a flat "done" costs a round trip for nothing.
Offer two or three continuations you would actually carry out — commit, add
tests, write the changelog entry, start the next subtask, show the diff — plus an
explicit "Stop here". The pick arrives inside the same turn, so act on it rather
than waiting for the next prompt.

Each question takes 2 to 4 options and a header of at most 12 characters, which
is all the card shows. Put the consequence of picking an option in its
description. Mark the one you would pick by putting it first and ending its label
with " (Recommended)", and give the reason in its description. Use multiSelect
only when several answers make sense together. Up to four questions in one call,
one topic each; a decision the user must make and a proposal for what to do next
are separate questions. Typing free text is always open to the user, so never add
an option for it.

    Question: "Reordering works, 14/14 tests pass. How to proceed?"
    Header:   "Next"
    Options:  "Commit (Recommended)" — Commit the reorder implementation now.
              "Changelog too"        — Add the changelog entry, then commit.
              "Stop here"            — Leave it uncommitted; nothing more runs.

**The exception: nothing to propose.** When the instruction was to do one thing
and stop, or no plausible follow-up exists, end in prose with a last line reading
`No follow-up: <why>.` Fewer than one working turn in ten should end this way.
When in doubt, ask.
