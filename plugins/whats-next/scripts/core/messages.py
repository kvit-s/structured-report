"""core/messages.py — what the model is told when it is sent back.

A blocked stop is expensive: the model works again and the user waits, so the
reason has to say what was wrong and what a correct ending looks like, in one
go. Each of these is built from the host profile, so the text names the tool
that exists where it is running and quotes that tool's own limits.
"""

from __future__ import annotations


def ask_shape(profile) -> str:
    limits = profile.ask
    return (
        f"Each question: {limits.min_options} to {limits.max_options} options, a "
        f"header of {limits.header_max} characters or fewer, the consequence of "
        "picking each option in its description, and \" (Recommended)\" on the "
        "first option when you have a recommendation, with the reason in its "
        "description. Free text is always available to the user, so no option "
        "for it is needed."
    )


def no_ask(profile) -> str:
    return (
        "This turn changed something and ended without offering a next step, so the "
        "user has nothing to click and will have to type \"what's next\".\n\n"
        "End it properly: short prose first — one headline sentence carrying the "
        "material fact, bullets for what changed, and a \"Tests:\" or \"Checks:\" line "
        f"saying how it was checked — then one {profile.ask_tool} call with "
        f"{profile.ask.min_options} to {profile.ask.max_options} real "
        "continuations (commit, add tests, the next subtask, review the diff) plus an "
        "explicit \"Stop here\" option. " + ask_shape(profile) + "\n\n"
        "If there is nothing to propose, because the instruction was to do one thing "
        "and stop or no plausible follow-up exists, send the same closing text again "
        "with a last line reading \"No follow-up: <why>.\" and the turn will end."
    )


def prose_choice(profile, sentence: str) -> str:
    return (
        f"Your closing text asks the user to choose — \"{sentence}\" — but no "
        f"{profile.ask_tool} call was made, so the question is buried in prose and "
        "there is nothing to click.\n\n"
        f"Restate that choice as one {profile.ask_tool} call and end there. "
        + ask_shape(profile)
    )


def failed_ask(profile, problems: list[str]) -> str:
    listed = "\n".join(f"  - {p}" for p in problems)
    return (
        f"Your {profile.ask_tool} call did not go through, so the user saw no card. "
        "Problems:\n" + listed + "\n\nCall it again with all of these fixed. "
        + ask_shape(profile)
    )
