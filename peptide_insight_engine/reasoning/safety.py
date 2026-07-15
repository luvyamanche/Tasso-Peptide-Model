"""
Safety gating (Tier 1).

Deterministic, source-traceable hard/soft gates. Produces SAFETY-category
Insights carrying a red/yellow/green flag. This layer answers only: *can this
specific patient take this peptide at all?* — nothing probabilistic lives here.

Two sources of gates:
  1. Declarative contraindications from the peptide knowledge base
     (matched against the patient's condition + family-history keys).
  2. A few lab-threshold gates that need a numeric comparison.
"""

from __future__ import annotations
from typing import Optional

from ..models import Patient, Insight, Category, Severity, Flag
from ..knowledge.peptides import Peptide
from ..patient_profile import PatientProfile
from .. import reference_ranges as rr


def _mk(title, detail, flag, rationale, source, severity, rec=None) -> Insight:
    return Insight(
        category=Category.SAFETY, title=title, detail=detail, severity=severity,
        rationale=rationale, source=source, recommendation=rec, flag=flag,
    )


def evaluate(patient: Patient, peptide: Peptide, prof: PatientProfile) -> list[Insight]:
    out: list[Insight] = []

    # 1. Absolute contraindications (RED) from history/conditions
    for cond, why in peptide.absolute_contraindications.items():
        if patient.has(cond):
            out.append(_mk(
                f"Absolute contraindication: {cond.replace('_', ' ')}",
                why, Flag.RED,
                f"Patient record includes '{cond}'.",
                "Peptide knowledge base (contraindication)",
                Severity.CRITICAL,
                rec="Do not initiate. Resolve/escalate to prescriber.",
            ))

    # 2. Relative contraindications (YELLOW)
    for cond, why in peptide.relative_contraindications.items():
        if patient.has(cond):
            out.append(_mk(
                f"Relative contraindication: {cond.replace('_', ' ')}",
                why, Flag.YELLOW,
                f"Patient record includes '{cond}'.",
                "Peptide knowledge base (precaution)",
                Severity.MODERATE,
                rec="Proceed only with provider judgement and closer monitoring.",
            ))

    # 3. Lab-threshold gates (peptide-specific)
    out.extend(_lab_gates(patient, peptide, prof))

    # 4. Required-but-missing key biomarkers -> YELLOW (never silently pass)
    for bm in peptide.key_biomarkers:
        if patient.lab(bm) is None and bm not in ("calcitonin",):  # optional extras
            out.append(_mk(
                f"Missing baseline: {bm}",
                f"{bm} is a key baseline for {peptide.name} but was not provided.",
                Flag.YELLOW,
                "Required biomarker absent from panel.",
                "Peptide knowledge base (monitoring)",
                Severity.LOW,
                rec=f"Order {bm} before initiating.",
            ))

    return out


def _lab_gates(patient: Patient, peptide: Peptide, prof: PatientProfile) -> list[Insight]:
    g: list[Insight] = []

    if peptide.id == "glp1":
        x = rr.x_uln("lipase", patient)
        if x is not None and x >= 3.0:
            g.append(_mk("Lipase >=3x ULN",
                         f"Lipase is {x}x the upper limit of normal.", Flag.RED,
                         "GLP-1 trial escalation threshold for pancreatitis workup.",
                         "GLP-1 trial safety practice", Severity.HIGH,
                         rec="Evaluate for pancreatitis before initiating."))
        elif x is not None and x >= 1.0:
            g.append(_mk("Lipase mildly elevated",
                         f"Lipase {x}x ULN.", Flag.YELLOW,
                         "Below the 3x action threshold but abnormal.",
                         "GLP-1 trial safety practice", Severity.LOW,
                         rec="Provider judgement; recheck on therapy."))
        if prof.renal_stage == "severe":
            g.append(_mk("Severe renal impairment",
                         f"eGFR {prof.egfr}.", Flag.RED,
                         "GI-loss dehydration on GLP-1 raises acute-kidney-injury risk.",
                         "Renal safety", Severity.HIGH,
                         rec="Avoid or use with nephrology co-management."))

    if peptide.id == "ghk_cu":
        cer = patient.lab("ceruloplasmin")
        if cer is not None and cer < 20:
            g.append(_mk("Low ceruloplasmin",
                         f"Ceruloplasmin {cer} mg/dL (<20).", Flag.RED,
                         "Wilson's-disease screening threshold; ceruloplasmin "
                         "reflects functional copper better than total copper.",
                         "Wilson's screen", Severity.HIGH,
                         rec="Screen for Wilson's disease before any copper therapy."))

    if peptide.id == "sermorelin":
        sd = prof.igf1_sd
        if sd is not None and sd > 2.0:
            g.append(_mk("IGF-1 already high",
                         f"IGF-1 {sd:+.1f} SD (> +2).", Flag.RED,
                         "Do not further stimulate a maxed GH axis.",
                         "GH-axis safety", Severity.HIGH,
                         rec="Do not initiate until IGF-1 normalizes / cause found."))
        elif sd is not None and sd > 1.0:
            g.append(_mk("IGF-1 upper range",
                         f"IGF-1 {sd:+.1f} SD.", Flag.YELLOW,
                         "Limited headroom before the +2 SD ceiling.",
                         "GH-axis monitoring", Severity.LOW,
                         rec="Start low, recheck IGF-1 at 4 weeks."))

    if peptide.id == "bpc157":
        g.append(_mk("Experimental agent",
                     "Not FDA-approved; minimal human safety data; no validated "
                     "response biomarker.", Flag.YELLOW,
                     "Evidence-quality gate for research peptides.",
                     "FDA safety review / evidence grade", Severity.MODERATE,
                     rec="Informed consent + provider oversight required."))

    return g


def overall_flag(insights: list[Insight]) -> Flag:
    flag = Flag.GREEN
    for i in insights:
        if i.flag and i.flag.rank > flag.rank:
            flag = i.flag
    return flag
