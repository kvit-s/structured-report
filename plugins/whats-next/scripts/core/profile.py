"""core/profile.py — what one agent calls its tools, and what its card allows.

A host profile is the whole of what the rules need to know about the agent
they are running inside. Claude Code's is in `hosts/claude_code.py`; a port to
another agent writes its own, changing the names and the limits rather than
any of the rules.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class AskLimits:
    """What one call of the question tool may contain. The defaults are Claude
    Code's `AskUserQuestion`: up to four questions, each with two to four
    options, and a header of which only the first twelve characters are drawn.
    Another agent's tool has its own numbers, and the checks read them from
    here rather than from constants of their own."""

    max_questions: int = 4
    min_options: int = 2
    max_options: int = 4
    header_max: int = 12


@dataclass(frozen=True)
class HostProfile:
    key: str                      # "claude-code", used in index records
    display: str                  # what to call it when speaking to the user
    ask_tool: str                 # the tool that draws the card of options
    write_tools: frozenset        # tools whose use means the turn changed something
    shell_tools: frozenset        # tools running a command, judged by the command
    ask: AskLimits = field(default_factory=AskLimits)
    # Other names the same card has had. An agent that renames its question
    # tool between releases is recognised either way, while the convention
    # text always tells the model to call `ask_tool`.
    ask_aliases: frozenset = frozenset()
    # One extra sentence about calling that tool here, appended to the
    # convention when it is delivered. For anything the host requires that
    # the file itself cannot know about.
    ask_note: str = ""

    def is_ask(self, tool_name: str) -> bool:
        return tool_name == self.ask_tool or tool_name in self.ask_aliases
