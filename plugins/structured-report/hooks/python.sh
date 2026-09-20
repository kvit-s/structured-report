#!/usr/bin/env bash
# python.sh — find a Python 3 to run a hook with, then exec it.
#
# Hooks are registered as:
#
#   bash "${CLAUDE_PLUGIN_ROOT}/hooks/python.sh" \
#        "${CLAUDE_PLUGIN_ROOT}/scripts/report_gate.py" [args...]
#
# Everything after the script path is passed on untouched, and stdin goes
# straight through, which is how a hook receives its JSON.
#
# Why a shim rather than calling python3 directly: on Windows `python3` is
# usually the Microsoft Store stub, which exits without running anything, so a
# hook wired to that name silently does nothing there. Each candidate is asked
# to run a one-line program that checks its own version, and the first that
# answers wins:
#
#   1. python3  — the name on macOS and Linux; the Store stub fails the test.
#   2. python   — what a python.org install on Windows provides, and what a few
#                 older Linux distributions still point at Python 2, which the
#                 version check rejects.
#   3. py -3    — the Windows Python launcher.
#
# PYTHONUTF8=1 is exported first. Without it Python on Windows reads and writes
# in the console code page, which fails on a path or a transcript holding any
# character outside it.
#
# PYTHONDONTWRITEBYTECODE=1 goes with it, so that importing report_lib never
# leaves a __pycache__ folder inside the copy of the plugin Claude Code runs.
# That copy lives under ~/.claude/plugins/cache/ and Claude Code refreshes it
# while sessions are open; on Windows a file that is open stops its folder being
# renamed or deleted, so a .pyc of ours held by a running hook can make the
# refresh fail, and then nothing of this plugin loads until it is installed
# again. Nothing here needs the speed a cached .pyc buys.
#
# When no Python is found the hook says so once through a systemMessage, which
# the Stop event shows the user, and then keeps quiet rather than complaining
# every turn.

set -u
export PYTHONUTF8=1
export PYTHONDONTWRITEBYTECODE=1

if [ "$#" -lt 1 ]; then
    echo "python.sh: no script to run" >&2
    exit 1
fi

script="$1"
shift

# Git Bash hands over POSIX paths such as /c/Users/... A Windows python.exe
# reads that leading slash as the root of the current drive, so translate.
if command -v cygpath >/dev/null 2>&1; then
    script="$(cygpath -w "$script" 2>/dev/null || printf '%s' "$script")"
fi

usable() {
    "$@" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 8) else 1)' \
        >/dev/null 2>&1
}

# $candidate is left unquoted on purpose, so that "py -3" splits into a command
# and its argument; the three values are literals in this file, so there is
# nothing else for the split to pick up. Whatever followed the script path is
# still in "$@", and the two branches are spelled out because expanding an empty
# "$@" under `set -u` is an error in bash 4.3 and earlier, which is what macOS
# ships as /bin/bash.
for candidate in python3 python "py -3"; do
    if usable $candidate; then
        if [ "$#" -eq 0 ]; then
            exec $candidate "$script"
        else
            exec $candidate "$script" "$@"
        fi
    fi
done

# Nothing usable. Say it once per machine, then stay silent.
marker="${TMPDIR:-/tmp}/structured-report-no-python"
if [ ! -e "$marker" ]; then
    : > "$marker" 2>/dev/null || true
    printf '%s\n' '{"systemMessage": "structured-report: no Python 3.8 or later found (tried python3, python, py -3), so the report hooks are not running. Install Python or point one of those names at it."}'
fi
exit 0
