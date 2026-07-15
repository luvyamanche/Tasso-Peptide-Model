"""
Personalized dosing / titration guidance (Tier 1.5).

Turns the patient profile into concrete, individualized dosing notes — the
practical "so what do I actually do" layer. Not a prescription; provider-facing
guidance with rationale + source.
"""

from __future__ import annotations

from ..models import Patient, Insight, Category, Severity
from ..knowledge.peptides import Peptide
from ..patient_profile import PatientProfile


def _mk(title, detail, rationale, source, rec, severity=Severity.LOW) -> Insight:
    return Insight(category=Category.DOSING, title=title, detail=detail,
                   severity=severity, rationale=rationale, source=source,
                   recommendation=rec)


def guidance(patient: Patient, peptide: Peptide, prof: PatientProfile) -> list[Insight]:
    out = []

    if peptide.id == "glp1":
        if prof.life_stage == "elderly" or prof.renal_stage in ("moderate", "severe"):
            out.append(_mk(
                "Slow titration advised",
                "Extend the dose-escalation interval and reinforce hydration.",
                f"Life stage '{prof.life_stage}', renal stage '{prof.renal_stage}'.",
                "Geriatric/renal prescribing principles",
                "Use the longest reasonable titration schedule; recheck renal function.",
            ))
        if prof.hypoglycemia_risk_meds:
            out.append(_mk(
                "Pre-emptive background-therapy reduction",
                "Reduce insulin/sulfonylurea at initiation to offset additive glucose lowering.",
                "Patient on insulin and/or sulfonylurea.",
                "GLP-1 + secretagogue hypoglycemia literature",
                "Reduce sulfonylurea 20-50% (or basal insulin ~20%) at start.",
                severity=Severity.MODERATE,
            ))

    if peptide.id == "sermorelin":
        if prof.igf1_sd is not None and prof.igf1_sd > 1.0:
            out.append(_mk(
                "Cap dose to protect IGF-1 ceiling",
                "Start at the low end and titrate against IGF-1, not symptoms alone.",
                f"Baseline IGF-1 {prof.igf1_sd:+.1f} SD leaves limited headroom.",
                "GH-axis titration principle",
                "Keep IGF-1 <= +2 SD; recheck at 4 weeks before escalating.",
            ))

    if peptide.id == "ghk_cu":
        out.append(_mk(
            "Cycle dosing to protect copper/zinc balance",
            "Use on/off cycling rather than continuous dosing.",
            "Chronic copper loading can deplete zinc and risk copper excess.",
            "Copper/zinc physiology",
            "Typical pattern: 4 weeks on / 4 weeks off; recheck zinc and copper.",
        ))

    return out
