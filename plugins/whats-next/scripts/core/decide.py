"""core/decide.py — the judgement a turn-end hook makes.

Given the turn and the closing prose, this says whether the model should be
sent back to write a report, and what to record either way. It reads nothing
and writes nothing: the host adapter has already turned the session record
into events, and the entry point that called this applies the block budget,
appends to the index and prints whatever JSON its agent expects. Keeping the
judgement separate is what lets a second agent reuse it unchanged.

Three endings send the model back:

  * the turn changed something, offered nothing, and did not say why there is
    no follow-up;
  * the closing text asks the user to choose, with no card drawn;
  * a call of the question tool came back as an error, so no card appeared.

Problems with a card that did work are reported to the user instead, because
they have already answered the one they saw.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from . import checks, messages, mutations, turn as turn_mod


@dataclass
class Verdict:
    action: str                      # "block" or "allow"
    reason: str = ""                 # what the model is told, when blocking
    kind: str = ""                   # "ask" or "done": what to index, if anything
    ask: object | None = None        # the ToolCall the turn ended with
    problems: list[str] = field(default_factory=list)
    reset_blocks: bool = False       # this prompt is settled; forget its blocks


def decide(profile, turn: list[turn_mod.Event], final_text: str) -> Verdict:
    calls = turn_mod.tool_calls(turn)
    asks = [c for c in calls if c.name == profile.ask_tool]
    changes = [c for c in calls if mutations.is_mutating(c, profile)]
    last_change = changes[-1].pos if changes else -1
    last_ask = asks[-1].pos if asks else -1

    # A call that errored means no card was drawn: worth another round trip.
    for ask in asks:
        if ask.is_error:
            hard, soft = checks.ask_problems(ask.input, profile.ask)
            problems = hard + soft or ["the tool rejected the call"]
            return Verdict("block", reason=messages.failed_ask(profile, problems))

    # The turn ended by asking, and the user answered.
    if asks and last_ask > last_change:
        hard, soft = checks.ask_problems(asks[-1].input, profile.ask,
                                         expect_stop_option=last_change >= 0)
        return Verdict("allow", kind="ask", ask=asks[-1], problems=hard + soft,
                       reset_blocks=True)

    sentence = checks.offers_choice_in_prose(final_text)
    if sentence:
        return Verdict("block", reason=messages.prose_choice(profile, sentence))

    if last_change < 0:
        return Verdict("allow", reset_blocks=True)

    if checks.says_no_followup(final_text):
        return Verdict("allow", kind="done", problems=checks.prose_problems(final_text),
                       reset_blocks=True)

    return Verdict("block", reason=messages.no_ask(profile))
