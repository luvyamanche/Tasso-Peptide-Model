"""
Response prediction (Tier 2).

Transparent, inspectable scorer combining published response signals. In
production this is replaced by a model fitted + calibrated on the network's own
longitudinal outcomes; the structure (which signals, which direction) mirrors
the evidence so the swap is drop-in.

Only GLP-1 has enough evidence for a quantitative predictor. Others return a
qualitative statement so the report never implies false precision.
"""

from __future__ import annotations
import math
from typing import Optional

from ..models import Patient, ResponsePrediction
from ..knowledge.peptides import Peptide
from ..patient_profile import PatientProfile


def predict(patient: Patient, peptide: Peptide, prof: PatientProfile) -> Optional[ResponsePrediction]:
    if peptide.id == "glp1":
        return _glp1(patient, prof)
    return None  # no validated quantitative predictor for the others


def _glp1(patient: Patient, prof: PatientProfile) -> ResponsePrediction:
    # --- signals (illustrative weights; replace with fitted coefficients) ---
    glp1r = patient.gene("GLP1R_effect")     # 0/1/2  -> better weight loss
    gipr = patient.gene("GIPR_risk")         # 0/1/2  -> more GI side effects
    bmi = prof.bmi if prof.bmi is not None else 30.0
    female = 1 if patient.sex.value == "F" else 0
    a1c = patient.lab("hba1c")

    # beta-cell reserve strongly modulates *glycemic* response
    reserve_adj = {"adequate": 0.3, "reduced": -0.2,
                   "severely_reduced": -0.6, "unknown": 0.0}[prof.beta_cell_reserve]

    z = (-0.4
         + 0.35 * glp1r
         + 0.05 * (bmi - 30)
         + 0.25 * female
         + reserve_adj
         + (0.1 if (a1c is not None and a1c >= 9) else 0))   # high baseline HbA1c -> more room
    likelihood = round(100 / (1 + math.exp(-z)))

    # --- GI side-effect risk band (Nature GWAS: dual GLP1R+GIPR risk ~15x vomiting) ---
    if glp1r == 2 and gipr == 2:
        gi = "high"
    elif (glp1r + gipr) >= 2:
        gi = "moderate"
    else:
        gi = "low"

    # --- confidence depends on how much signal we actually have ---
    have_genetics = ("GLP1R_effect" in patient.genetics) or ("GIPR_risk" in patient.genetics)
    have_reserve = prof.beta_cell_reserve != "unknown"
    confidence = "high" if (have_genetics and have_reserve) else \
                 "moderate" if (have_genetics or have_reserve) else "low"

    return ResponsePrediction(
        likelihood_pct=likelihood,
        confidence=confidence,
        side_effect_risk=gi,
        drivers={
            "GLP1R_effect_alleles": glp1r,
            "GIPR_risk_alleles": gipr,
            "bmi": bmi,
            "sex": patient.sex.value,
            "beta_cell_reserve": prof.beta_cell_reserve,
            "baseline_hba1c": a1c,
        },
        disclaimer=("Probabilistic guidance for provider discussion, not a guarantee. "
                    "Genetic+clinical models explain only ~25% of weight-loss variance "
                    "(Nature GWAS 2026); ~18% of patients are non-responders."),
    )
