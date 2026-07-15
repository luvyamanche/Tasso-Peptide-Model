"""
Peptide Insight Engine
======================

A clinical decision-support engine that ingests structured patient data
(labs, demographics, conditions, medications, genetics) and produces deep,
contextual insights about how specific peptide therapies would interact with
*that individual patient* — not generic "your cholesterol is low" statements.

The engine is intentionally split into transparent, auditable layers:

    reference_ranges  -> turns raw labs into sex/age-aware interpretations
    patient_profile   -> derives physiological states & patient archetypes
    knowledge/        -> the peptide knowledge base + interaction rules
    reasoning/        -> safety gating, cross-biomarker insights, response,
                         personalized dosing
    engine            -> orchestrates the layers into one evaluation
    report            -> renders a provider-facing report

Nothing here is a black box: every insight carries a rationale and a source.

DISCLAIMER: research/prototype software. Not medical advice. Thresholds are
literature-aligned defaults requiring medical-director validation.
"""

from .engine import InsightEngine
from .models import Patient, LabResult
from .report import render_report

__all__ = ["InsightEngine", "Patient", "LabResult", "render_report"]
__version__ = "0.2.0"
