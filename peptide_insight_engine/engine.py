"""
The orchestrator.

Wires the layers together: profile the patient once, then for each requested
peptide run safety gating, deep insights, dosing, and response prediction, and
assemble a PeptideEvaluation. This is the public entry point (see __init__).
"""

from __future__ import annotations
from typing import Optional

from .models import Patient, PeptideEvaluation, Insight, Category
from .patient_profile import build_profile, PatientProfile
from .knowledge.peptides import get_peptide, PEPTIDES
from .reasoning import safety, insights as insight_mod, response as response_mod, dosing


class InsightEngine:
    """Stateless engine; construct once, evaluate many patients."""

    def profile(self, patient: Patient) -> PatientProfile:
        return build_profile(patient)

    def evaluate(self, patient: Patient, peptide_id: str,
                 prof: Optional[PatientProfile] = None) -> PeptideEvaluation:
        peptide = get_peptide(peptide_id)
        prof = prof or self.profile(patient)

        all_insights: list[Insight] = []

        # 1. Safety gates (deterministic, flagged)
        safety_insights = safety.evaluate(patient, peptide, prof)
        all_insights += safety_insights

        # 2. Deep insights (interactions, cross-biomarker, special populations)
        all_insights += insight_mod.all_insights(patient, peptide, prof)

        # 3. Personalized dosing guidance
        all_insights += dosing.guidance(patient, peptide, prof)

        # 4. Overall flag = worst safety flag across all flagged insights
        overall = safety.overall_flag(all_insights)

        # 5. Response prediction (skipped if hard-contraindicated)
        response = None
        if overall.value != "red":
            response = response_mod.predict(patient, peptide, prof)

        # order insights: most severe first, safety category leads
        all_insights.sort(key=lambda i: (-(i.flag.rank if i.flag else 0),
                                         -i.severity.rank))

        return PeptideEvaluation(
            peptide_id=peptide.id,
            peptide_name=peptide.name,
            overall_flag=overall,
            insights=all_insights,
            response=response,
            monitoring=peptide.monitoring,
        )

    def evaluate_all(self, patient: Patient) -> dict[str, PeptideEvaluation]:
        prof = self.profile(patient)
        return {pid: self.evaluate(patient, pid, prof) for pid in PEPTIDES}
