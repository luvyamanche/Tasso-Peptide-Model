"""
Plain-language summary layer.

The detailed report is precise but dense. This module distills a
PeptideEvaluation into the parts a reader actually needs first:

  - a one-line BOTTOM LINE verdict
  - the top reasons behind it, in plain English
  - a consolidated, de-duplicated WHAT TO DO NEXT list
  - a readable interpretation of the response prediction

Kept separate from report.py so it can also feed a UI / API later.
"""

from __future__ import annotations
from dataclasses import dataclass, field

from .models import PeptideEvaluation, Flag, Insight


@dataclass
class Summary:
    bottom_line: str
    reasons: list[str] = field(default_factory=list)
    next_steps: list[str] = field(default_factory=list)
    response_line: str | None = None


def _peptide_short(ev: PeptideEvaluation) -> str:
    return ev.peptide_name.split(" (")[0].split(" / ")[0]


def bottom_line(ev: PeptideEvaluation) -> str:
    p = _peptide_short(ev)
    if ev.overall_flag == Flag.RED:
        return (f"NOT RECOMMENDED RIGHT NOW — at least one issue must be resolved "
                f"before {p} would be safe for this person.")
    if ev.overall_flag == Flag.YELLOW:
        return (f"POSSIBLE, WITH CAUTION — {p} may be appropriate, but there are "
                f"items to address and monitor first.")
    return (f"NO BLOCKING ISSUES FOUND — {p} looks reasonable to start, with the "
            f"standard monitoring below.")


def _flag_weight(i: Insight) -> int:
    return (i.flag.rank if i.flag else 0) * 10 + i.severity.rank


def top_reasons(ev: PeptideEvaluation, limit: int = 4) -> list[str]:
    flagged = [i for i in ev.insights if i.flag in (Flag.RED, Flag.YELLOW)]
    flagged.sort(key=_flag_weight, reverse=True)
    out = []
    for i in flagged[:limit]:
        tag = "BLOCKER" if i.flag == Flag.RED else "caution"
        out.append(f"({tag}) {i.title} — {i.detail}")
    if not out:
        # green: surface the positive / informational highlights
        for i in ev.insights[:2]:
            out.append(i.title + " — " + i.detail)
    return out


def next_steps(ev: PeptideEvaluation) -> list[str]:
    steps, seen = [], set()
    for i in sorted(ev.insights, key=_flag_weight, reverse=True):
        rec = i.recommendation
        if rec and rec not in seen:
            seen.add(rec)
            steps.append(rec)
    return steps


def response_line(ev: PeptideEvaluation) -> str | None:
    r = ev.response
    if not r:
        return None
    if r.likelihood_pct >= 65:
        band = "above-average"
    elif r.likelihood_pct >= 45:
        band = "roughly average"
    else:
        band = "below-average"
    return (f"Estimated likelihood of a good response: {r.likelihood_pct}% "
            f"({band}); GI side-effect risk: {r.side_effect_risk}; "
            f"prediction confidence: {r.confidence}. {r.disclaimer}")


def build_summary(ev: PeptideEvaluation) -> Summary:
    return Summary(
        bottom_line=bottom_line(ev),
        reasons=top_reasons(ev),
        next_steps=next_steps(ev),
        response_line=response_line(ev),
    )
