"""
Report rendering.

Two renderers:
  render_report  -> human-readable provider-facing text
  to_json        -> structured payload for EMR / API integration
"""

from __future__ import annotations
import json

from .models import Patient, PeptideEvaluation, Category, Flag
from .patient_profile import build_profile

_FLAG_TAG = {Flag.GREEN: "[GREEN] ", Flag.YELLOW: "[YELLOW]", Flag.RED: "[RED]   "}

_CATEGORY_ORDER = [
    Category.SAFETY, Category.SPECIAL_POPULATION, Category.DRUG_INTERACTION,
    Category.RESPONSE, Category.BIOMARKER, Category.DOSING, Category.MONITORING,
]
_CATEGORY_TITLE = {
    Category.SAFETY: "SAFETY GATES",
    Category.SPECIAL_POPULATION: "SPECIAL POPULATION",
    Category.DRUG_INTERACTION: "DRUG INTERACTIONS",
    Category.RESPONSE: "RESPONSE / EFFICACY",
    Category.BIOMARKER: "BIOMARKER OUTLOOK",
    Category.DOSING: "PERSONALIZED DOSING",
    Category.MONITORING: "MONITORING",
}


def render_report(patient: Patient, evaluation: PeptideEvaluation) -> str:
    prof = build_profile(patient)
    L = []
    L.append("=" * 78)
    L.append(f"PATIENT {patient.patient_id}  |  {patient.age}{patient.sex.value}  "
             f"|  {evaluation.peptide_name}")
    L.append(f"WHO THIS PATIENT IS: {', '.join(prof.archetypes)}")
    L.append(f"OVERALL: {evaluation.overall_flag.value.upper()}")
    L.append("=" * 78)

    for cat in _CATEGORY_ORDER:
        items = evaluation.by_category(cat)
        if not items:
            continue
        L.append(f"\n-- {_CATEGORY_TITLE[cat]} " + "-" * (74 - len(_CATEGORY_TITLE[cat])))
        for i in items:
            tag = _FLAG_TAG[i.flag] if i.flag else "        "
            L.append(f"  {tag} {i.title}  ({i.severity.value})")
            L.append(f"           {i.detail}")
            if i.recommendation:
                L.append(f"           -> {i.recommendation}")
            L.append(f"           why: {i.rationale}  [src: {i.source}]")

    if evaluation.response:
        r = evaluation.response
        L.append("\n-- RESPONSE PREDICTION " + "-" * 55)
        L.append(f"  likely response: {r.likelihood_pct}%   "
                 f"(confidence: {r.confidence})   GI side-effect risk: {r.side_effect_risk}")
        L.append(f"  drivers: {r.drivers}")
        L.append(f"  note: {r.disclaimer}")

    if evaluation.monitoring:
        L.append("\n-- MONITORING PLAN " + "-" * 59)
        for m in evaluation.monitoring:
            L.append(f"  - {m}")

    L.append("=" * 78)
    return "\n".join(L)


def to_json(evaluation: PeptideEvaluation, indent: int = 2) -> str:
    return json.dumps(evaluation.to_dict(), indent=indent)
