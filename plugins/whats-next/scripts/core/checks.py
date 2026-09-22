"""core/checks.py — what a well-formed ending looks like.

Two things are checked. One is the call to the question tool: the number of
questions and options, the length of the header, whether each option says what
picking it does, whether one is marked as the recommendation and whether there
is a way to say stop. The other is the closing prose: whether it says how the
work was checked, whether the headline is a sentence rather than a paragraph,
and whether it asks the user to choose something without drawing a card.

Problems come back in two lists. A hard problem makes the call unusable, so it
is worth sending the model back; a soft one is about the shape of a card the
user has already answered, and sending the model back for it would only put a
second, tidier card in front of them for a question they have answered.
"""

from __future__ import annotations

import re

from .profile import AskLimits

RECOMMENDED = re.compile(r"\(recommended\)\s*$", re.I)
STOP_OPTION = re.compile(
    r"\b(stop here|stop there|leave it|leave as is|nothing (?:more|else)|"
    r"no (?:further|more)|that'?s all|hold off|not now|later|done for now|"
    r"wrap up|finish here|end here|park it)\b", re.I)

VERIFICATION = re.compile(
    r"(?im)^\s*(?:[-*]\s*)?(?:\*\*)?(?:tests?|checks?|verified|verification|"
    r"build|checked)(?:\*\*)?\s*:")
UNVERIFIED = re.compile(
    r"(?i)(left|not|un)\s*(it\s+)?(verified|tested|checked|run)|"
    r"did not (?:run|test|verify|check)|no tests? (?:were )?run")
NO_FOLLOWUP = re.compile(r"(?im)^\s*(?:[-*>]\s*)?(?:\*\*)?no follow-?up\b")
MISSING = (r"unavailable|not available|unsupported|not supported|disabled|"
           r"not enabled|cannot be called|can't be called|is missing")
SUBJECT = r"question tool|follow-?up selector|card of options"
CHOICE_IN_PROSE = re.compile(
    r"(?i)\b(should i|shall i|do you want me to|would you like me to|"
    r"want me to|which (?:one|option|approach|of these|would you)|"
    r"let me know (?:if|whether|which)|your call)\b[^.!?\n]*\?")

_DEFAULT_LIMITS = AskLimits()


def ask_problems(payload: dict, limits: AskLimits = _DEFAULT_LIMITS,
                 expect_stop_option: bool = False) -> tuple[list[str], list[str]]:
    """Check one call of the question tool. Returns (hard, soft). Every
    problem is reported at once so one pass fixes all of them."""
    hard: list[str] = []
    soft: list[str] = []
    questions = payload.get("questions")
    if not isinstance(questions, list) or not questions:
        return ["the call has no questions"], []
    if len(questions) > limits.max_questions:
        hard.append(f"{len(questions)} questions in one call; the tool takes "
                    f"at most {limits.max_questions}")

    recommended_total = 0
    for i, q in enumerate(questions, 1):
        where = f"question {i}"
        if not isinstance(q, dict):
            hard.append(f"{where} is not an object")
            continue
        text = (q.get("question") or "").strip()
        if not text:
            hard.append(f"{where} has no question text")
        header = (q.get("header") or "").strip()
        if not header:
            soft.append(f"{where} has no header")
        elif len(header) > limits.header_max:
            soft.append(f'{where} header "{header}" is {len(header)} characters; '
                        f"the card shows {limits.header_max}")
        options = q.get("options")
        if (not isinstance(options, list) or len(options) < limits.min_options
                or len(options) > limits.max_options):
            n = len(options) if isinstance(options, list) else 0
            hard.append(f"{where} has {n} options; give {limits.min_options} "
                        f"to {limits.max_options}")
            continue
        labels = []
        for j, opt in enumerate(options, 1):
            if not isinstance(opt, dict):
                hard.append(f"{where} option {j} is not an object")
                continue
            label = (opt.get("label") or "").strip()
            if not label:
                hard.append(f"{where} option {j} has no label")
            labels.append(label)
            if not (opt.get("description") or "").strip():
                soft.append(f'{where} option "{label or j}" has no description; '
                            "the description is where the consequence goes")
        marked = [k for k, lab in enumerate(labels) if RECOMMENDED.search(lab)]
        recommended_total += len(marked)
        if not q.get("multiSelect"):
            if len(marked) > 1:
                soft.append(f"{where} marks {len(marked)} options "
                            '"(Recommended)"; mark one')
            elif marked and marked[0] != 0:
                soft.append(f"{where} puts the recommended option at position "
                            f"{marked[0] + 1}; put it first")
        if expect_stop_option and i == len(questions):
            joined = " ".join(f"{lab} {(o.get('description') or '') if isinstance(o, dict) else ''}"
                              for lab, o in zip(labels, options))
            if not STOP_OPTION.search(joined):
                soft.append(f'{where} offers no way to stop; add an explicit '
                            '"Stop here" option so the turn can end')
    if expect_stop_option and recommended_total == 0:
        soft.append('no option is marked " (Recommended)"; mark the one you '
                    "would pick and say why in its description")
    return hard, soft


def says_no_followup(text: str) -> bool:
    return bool(NO_FOLLOWUP.search(text or ""))


def says_tool_unavailable(text: str, tool_name: str) -> bool:
    """True when the closing text says the question tool is not there.

    It can be missing for real: an agent may put its question tool behind a
    flag, leave it out of non-interactive runs, or let a project disable it.
    A model that cannot draw a card cannot satisfy the convention however
    often it is sent back, so saying so plainly is the honest ending. The turn
    is allowed to finish and the reason is kept in the index."""
    if not text:
        return False
    subject = f"{re.escape(tool_name)}|{SUBJECT}"
    tail = "\n".join([ln for ln in text.splitlines() if ln.strip()][-4:])
    return bool(re.search(rf"(?i)\b(?:{subject})\b[^.\n]{{0,80}}?\b(?:{MISSING})\b", tail)
                or re.search(rf"(?i)\b(?:{MISSING})\b[^.\n]{{0,80}}?\b(?:{subject})\b", tail))


def prose_problems(text: str) -> list[str]:
    """Soft checks on the closing prose of a turn that offers nothing."""
    out: list[str] = []
    text = (text or "").strip()
    if not text:
        return ["the turn ended with no text at all"]
    if not VERIFICATION.search(text) and not UNVERIFIED.search(text):
        out.append("no line saying how the work was checked; end with a "
                   '"Tests:" or "Checks:" line, or say what is left unverified '
                   "and why")
    first = next((ln.strip() for ln in text.splitlines() if ln.strip()), "")
    first = re.sub(r"^[#>*\-\s]+", "", first)
    if len(first) > 200:
        out.append(f"the opening line is {len(first)} characters; a headline is "
                   "one sentence carrying the material fact")
    return out


def offers_choice_in_prose(text: str) -> str | None:
    """The sentence where the closing text asks the user to choose, if it does.
    Only the last few lines count, so a rhetorical question earlier in the
    message is left alone."""
    lines = [ln for ln in (text or "").splitlines() if ln.strip()]
    tail = "\n".join(lines[-4:])
    m = CHOICE_IN_PROSE.search(tail)
    return m.group(0).strip() if m else None


def headline_of(text: str) -> str:
    first = next((ln.strip() for ln in (text or "").splitlines() if ln.strip()), "")
    return re.sub(r"^[#>*\-\s]+", "", first)[:240]


def verification_of(text: str) -> str:
    for line in (text or "").splitlines():
        if VERIFICATION.match(line.strip()):
            return line.strip()[:240]
    return ""
