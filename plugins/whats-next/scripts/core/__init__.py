"""core — the rules, with no knowledge of which agent is running them.

Everything in here works on two host-neutral things: a `HostProfile`, which
says what the agent calls its tools and what its question card allows, and a
list of `Event` objects, which is one turn of a session after a host adapter
has read it out of whatever the agent writes to disk. Nothing here opens a
transcript, parses a hook payload or prints a hook reply; that is the adapter's
work, and `hosts/claude_code.py` is the one adapter this plugin ships.

The split exists so that a second agent needs an adapter rather than a fork:
the shell-command classifier, the checks on a question card, the closing-prose
checks, the index and the decision the Stop hook makes are the same wherever
they run.
"""
