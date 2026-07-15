"""
Declarative interaction knowledge.

Two tables:
  DRUG_INTERACTIONS  — peptide x medication-class effects (the reasoning layer
                       fires these when the patient is on the trigger class).
  BIOMARKER_EFFECTS  — how a peptide is expected to move / interact with a
                       biomarker, used to generate anticipatory insights.

Keeping this declarative means a clinician can review the whole interaction
surface in one file, and adding coverage is data-entry, not code.
"""

from __future__ import annotations
from dataclasses import dataclass

from ..models import Severity


@dataclass
class DrugInteraction:
    trigger_med_class: str
    effect: str
    severity: Severity
    recommendation: str
    source: str


@dataclass
class BiomarkerEffect:
    biomarker: str
    direction: str          # "increase" / "decrease" / "variable"
    effect: str
    source: str


DRUG_INTERACTIONS: dict[str, list[DrugInteraction]] = {

    "glp1": [
        DrugInteraction(
            "insulin",
            "Additive glucose lowering — symptomatic hypoglycemia reported in "
            "~17-30% on GLP-1 + insulin.",
            Severity.HIGH,
            "Pre-emptively reduce basal insulin ~20% at initiation; intensify "
            "glucose monitoring during titration.",
            "Systematic review, GLP-1 + insulin/secretagogue hypoglycemia (2024)",
        ),
        DrugInteraction(
            "sulfonylurea",
            "Additive insulin secretion raises hypoglycemia risk (~17-24%).",
            Severity.HIGH,
            "Reduce sulfonylurea dose 20-50% at GLP-1 start; consider deprescribing.",
            "Systematic review, GLP-1 + insulin/secretagogue hypoglycemia (2024)",
        ),
        DrugInteraction(
            "warfarin",
            "Delayed gastric emptying can shift warfarin absorption and destabilize "
            "INR (narrow therapeutic index), especially during dose escalation.",
            Severity.MODERATE,
            "Check INR more frequently during each GLP-1 dose increase.",
            "Springer Drug Safety systematic review (2024)",
        ),
        DrugInteraction(
            "oral_contraceptive",
            "Tirzepatide reduces oral-contraceptive exposure and can lower "
            "efficacy; GLP-1 delayed emptying alters absorption timing.",
            Severity.MODERATE,
            "For tirzepatide: add a barrier method or switch to non-oral "
            "contraception for 4 weeks after start/each dose increase.",
            "Tirzepatide labeling / DDI review",
        ),
        DrugInteraction(
            "oral_narrow_therapeutic_index",
            "Delayed gastric emptying can alter Tmax of oral drugs with narrow "
            "therapeutic windows.",
            Severity.LOW,
            "Where feasible, dose the oral drug ~1 hour before the GLP-1.",
            "Springer Drug Safety systematic review (2024)",
        ),
        DrugInteraction(
            "levothyroxine",
            "Altered absorption timing possible with delayed gastric emptying.",
            Severity.LOW,
            "Maintain consistent dosing separation; recheck TSH if symptoms.",
            "GLP-1 DDI guidance",
        ),
    ],

    "sermorelin": [
        DrugInteraction(
            "glucocorticoid",
            "GH reverses cortisone->cortisol conversion and can unmask "
            "hypoadrenalism; glucocorticoid needs may rise.",
            Severity.MODERATE,
            "Monitor for adrenal insufficiency; may need to increase "
            "maintenance/stress glucocorticoid dosing.",
            "GH labeling (somatropin) / Endocrine Society guidance",
        ),
        DrugInteraction(
            "insulin",
            "GH reduces insulin sensitivity — glucose may rise, increasing "
            "insulin requirement.",
            Severity.MODERATE,
            "Monitor glucose; anticipate possible insulin dose increase.",
            "GH labeling (somatropin)",
        ),
        DrugInteraction(
            "levothyroxine",
            "GH lowers free T4 (increased peripheral conversion / unmasked central "
            "hypothyroidism); may increase thyroid replacement need.",
            Severity.MODERATE,
            "Recheck free T4/TSH after initiation; adjust levothyroxine as needed.",
            "GH labeling (somatropin)",
        ),
    ],

    "ghk_cu": [
        # copper/zinc antagonism is handled as a biomarker insight; no common
        # prescription-drug DDIs of note for a prototype.
    ],

    "bpc157": [
        DrugInteraction(
            "warfarin",
            "Animal data suggest coagulation-system effects; combined with an "
            "anticoagulant the interaction is uncharacterized in humans.",
            Severity.MODERATE,
            "Avoid or use only with explicit provider oversight and INR monitoring.",
            "BPC-157 preclinical coagulation data / FDA safety review",
        ),
        DrugInteraction(
            "doac",
            "Uncharacterized interaction with anticoagulation.",
            Severity.MODERATE,
            "Avoid pending human data; provider oversight required.",
            "BPC-157 preclinical coagulation data",
        ),
        DrugInteraction(
            "antiplatelet",
            "Theoretical additive bleeding/vascular effects.",
            Severity.LOW,
            "Discuss risk; monitor for bleeding.",
            "BPC-157 preclinical data",
        ),
    ],
}


BIOMARKER_EFFECTS: dict[str, list[BiomarkerEffect]] = {
    "glp1": [
        BiomarkerEffect("resting_hr", "increase",
                        "GLP-1s modestly raise resting heart rate (~2-4 bpm).",
                        "GLP-1 class labeling"),
        BiomarkerEffect("hba1c", "decrease",
                        "Expected HbA1c and weight reduction (primary efficacy).",
                        "SUSTAIN/STEP programs"),
        BiomarkerEffect("triglycerides", "decrease",
                        "Triglycerides typically fall with weight loss.",
                        "GLP-1 metabolic trials"),
    ],
    "sermorelin": [
        BiomarkerEffect("igf1_sd", "increase",
                        "IGF-1 rises with GH stimulation — the titration target.",
                        "GH physiology"),
        BiomarkerEffect("fasting_glucose", "increase",
                        "GH lowers insulin sensitivity; glucose may drift up.",
                        "GH labeling"),
        BiomarkerEffect("free_t4", "decrease",
                        "Free T4 can fall; monitor thyroid axis.",
                        "GH labeling"),
    ],
    "ghk_cu": [
        BiomarkerEffect("zinc", "decrease",
                        "Chronic copper loading can deplete zinc (antagonists).",
                        "Copper/zinc physiology"),
    ],
    "bpc157": [],
}
