---
name: report
description: Reprint the last report of this session — the closing text of the turn, the question it ended with, its options, and the answer given.
disable-model-invocation: true
argument-hint: "[how many, default 1]"
allowed-tools: Bash(bash "${CLAUDE_PLUGIN_ROOT}/hooks/python.sh"*)
---

The last report of this session, read back out of the transcript:

!`bash "${CLAUDE_PLUGIN_ROOT}/hooks/python.sh" "${CLAUDE_PLUGIN_ROOT}/scripts/report_last.py" --session "${CLAUDE_SESSION_ID}" -n 1`

Print what is above as a fenced block, unchanged, and say nothing else. The
arrow marks the option the user picked.

If the user asked for more than one — `/report 3` — run
`bash "${CLAUDE_PLUGIN_ROOT}/hooks/python.sh" "${CLAUDE_PLUGIN_ROOT}/scripts/report_last.py" -n 3`
and print that instead. For `/report history`, run the same command with
`--history 20`, which lists one line per report across every session in this
directory. If the script says there is no report yet, say so in one line.
