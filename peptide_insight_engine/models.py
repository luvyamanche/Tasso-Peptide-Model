"""
Core data structures shared across the whole engine.

Everything downstream (profiling, knowledge base, reasoning, reporting) speaks
in terms of these types, so this module is the contract for the system.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


# ---------------------------------------------------------------------------
# Controlled vocabularies
# ---------------------------------------------------------------------------
# We use string keys (not free text) for conditions / medication classes so
# that patient data can be matched deterministically against the knowledge
# base. Add to these lists as coverage grows.

class Sex(str, Enum):
    MALE = "M"
    FEMALE = "F"


class Flag(str, Enum):
    """Traffic-light safety verdict."""
    GREEN = "green"
    YELLOW = "yellow"
    RED = "red"

    @property
    def rank(self) -> int:
        return {"green": 0, "yellow": 1, "red": 2}[self.value]


class Severity(str, Enum):
    INFO = "info"
    LOW = "low"
    MODERATE = "moderate"
    HIGH = "high"
    CRITICAL = "critical"

    @property
    def rank(self) -> int:
        return {"info": 0, "low": 1, "moderate": 2, "high": 3, "critical": 4}[self.value]


class Category(str, Enum):
    """What kind of insight this is — drives grouping in the report."""
    SAFETY = "safety"                 # can this patient take it at all
    DRUG_INTERACTION = "drug_interaction"
    BIOMARKER = "biomarker"           # cross-lab reasoning
    RESPONSE = "response"             # likely to work?
    DOSING = "dosing"                 # personalized dose / titration
    MONITORING = "monitoring"         # what to re-check and when
    SPECIAL_POPULATION = "special_population"


# Recognized condition keys (patient.conditions is a set of these)
KNOWN_CONDITIONS = {
    "mtc_men2", "pancreatitis_history", "gallbladder_disease",
    "diabetic_retinopathy", "proliferative_retinopathy", "type_1_diabetes",
    "type_2_diabetes", "eating_disorder", "gastroparesis",
    "wilsons_disease", "menkes_disease",
    "active_malignancy", "malignancy_history",
    "pituitary_disease", "adrenal_insufficiency", "hypothyroidism",
    "chronic_kidney_disease", "hepatic_impairment", "cardiovascular_disease",
    "pregnancy", "breastfeeding", "reproductive_age_female",
}

# Recognized medication-class keys (Medication.drug_class)
KNOWN_MED_CLASSES = {
    "insulin", "sulfonylurea", "warfarin", "doac", "antiplatelet",
    "oral_contraceptive", "glucocorticoid", "levothyroxine",
    "oral_narrow_therapeutic_index", "sglt2_inhibitor", "metformin",
}


# ---------------------------------------------------------------------------
# Inputs
# ---------------------------------------------------------------------------

@dataclass
class LabResult:
    name: str          # canonical key, e.g. "hba1c", "lipase", "egfr"
    value: float
    unit: str = ""


@dataclass
class Medication:
    name: str
    drug_class: str    # one of KNOWN_MED_CLASSES
    route: str = "oral"


@dataclass
class Patient:
    patient_id: str
    age: int
    sex: Sex
    weight_kg: Optional[float] = None
    height_cm: Optional[float] = None

    labs: dict[str, LabResult] = field(default_factory=dict)
    conditions: set[str] = field(default_factory=set)     # KNOWN_CONDITIONS keys
    medications: list[Medication] = field(default_factory=list)
    family_history: set[str] = field(default_factory=set)  # e.g. {"mtc_men2"}
    genetics: dict[str, int] = field(default_factory=dict)  # allele dosage 0/1/2
    notes: str = ""

    # -- convenience accessors -------------------------------------------------
    def lab(self, key: str) -> Optional[float]:
        r = self.labs.get(key)
        return r.value if r else None

    def has(self, condition: str) -> bool:
        return condition in self.conditions or condition in self.family_history

    def med_classes(self) -> set[str]:
        return {m.drug_class for m in self.medications}

    def on_med_class(self, drug_class: str) -> bool:
        return drug_class in self.med_classes()

    def gene(self, key: str) -> int:
        return self.genetics.get(key, 0)


# ---------------------------------------------------------------------------
# Outputs
# ---------------------------------------------------------------------------

@dataclass
class Insight:
    """One reasoned statement about this patient + this peptide.

    The point of the whole engine: an Insight is contextual and actionable,
    combining multiple data points, and always carries WHY (rationale) and a
    traceable source.
    """
    category: Category
    title: str
    detail: str
    severity: Severity
    rationale: str
    source: str
    recommendation: Optional[str] = None
    flag: Optional[Flag] = None          # set for SAFETY insights

    def to_dict(self) -> dict:
        return {
            "category": self.category.value,
            "title": self.title,
            "detail": self.detail,
            "severity": self.severity.value,
            "rationale": self.rationale,
            "source": self.source,
            "recommendation": self.recommendation,
            "flag": self.flag.value if self.flag else None,
        }


@dataclass
class ResponsePrediction:
    likelihood_pct: int
    confidence: str                       # "low" / "moderate" / "high"
    side_effect_risk: str                 # "low" / "moderate" / "high"
    drivers: dict
    disclaimer: str

    def to_dict(self) -> dict:
        return {
            "likelihood_pct": self.likelihood_pct,
            "confidence": self.confidence,
            "side_effect_risk": self.side_effect_risk,
            "drivers": self.drivers,
            "disclaimer": self.disclaimer,
        }


@dataclass
class PeptideEvaluation:
    peptide_id: str
    peptide_name: str
    overall_flag: Flag
    insights: list[Insight] = field(default_factory=list)
    response: Optional[ResponsePrediction] = None
    monitoring: list[str] = field(default_factory=list)

    def by_category(self, category: Category) -> list[Insight]:
        return [i for i in self.insights if i.category == category]

    def to_dict(self) -> dict:
        return {
            "peptide_id": self.peptide_id,
            "peptide_name": self.peptide_name,
            "overall_flag": self.overall_flag.value,
            "insights": [i.to_dict() for i in self.insights],
            "response": self.response.to_dict() if self.response else None,
            "monitoring": self.monitoring,
        }
