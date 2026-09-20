"""core/card.py — drawing a report back as plain text.

The card the user answered is a tool call in the session record, so `/report`
reprints it rather than keeping a copy of its own: the prose that preceded it,
the question, every option with its description, and an arrow beside the one
that was picked. An answer the user typed instead of picking is shown too, and
marked as such.
"""

from __future__ import annotations


def render_card(question_payload: dict, answers: dict | None, prose: str = "",
                when: str = "", width: int = 78) -> str:
    lines: list[str] = []
    if when:
        lines.append(f"Report — {when}")
    if prose:
        lines.append("")
        lines.append(prose.strip())
    questions = question_payload.get("questions") or []
    answers = answers or {}
    for q in questions:
        if not isinstance(q, dict):
            continue
        header = (q.get("header") or "").strip()
        text = (q.get("question") or "").strip()
        lines.append("")
        lines.append(f"[{header}] {text}" if header else text)
        picked_raw = answers.get(text)
        picked = set()
        if isinstance(picked_raw, str):
            picked = {p.strip() for p in picked_raw.split(", ")}
        elif isinstance(picked_raw, list):
            picked = {str(p).strip() for p in picked_raw}
        for opt in q.get("options") or []:
            if not isinstance(opt, dict):
                continue
            label = (opt.get("label") or "").strip()
            mark = "->" if label in picked else "  "
            desc = (opt.get("description") or "").strip()
            lines.append(f"  {mark} {label}")
            if desc:
                for chunk in wrap(desc, width - 7):
                    lines.append(f"       {chunk}")
        if picked_raw is None:
            lines.append("     (unanswered)")
        else:
            shown = picked_raw if isinstance(picked_raw, str) else ", ".join(picked)
            unlisted = [p for p in picked
                        if p not in {(o.get("label") or "").strip()
                                     for o in q.get("options") or []
                                     if isinstance(o, dict)}]
            suffix = "  (typed, not one of the options)" if unlisted else ""
            lines.append(f"     answer: {shown}{suffix}")
    return "\n".join(lines).strip()


def wrap(text: str, width: int) -> list[str]:
    words, out, cur = text.split(), [], ""
    for w in words:
        if cur and len(cur) + 1 + len(w) > width:
            out.append(cur)
            cur = w
        else:
            cur = f"{cur} {w}".strip()
    if cur:
        out.append(cur)
    return out
