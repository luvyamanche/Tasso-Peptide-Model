"""
Reference ranges & derived clinical quantities.

Turns a raw number into a *sex/age-aware interpretation* (low / normal / high),
and computes derived values (BMI, eGFR, IGF-1 SD score) that the profiling and
reasoning layers depend on.

Ranges here are reasonable adult defaults for a PROTOTYPE. In production these
must be replaced by the partner lab's own validated reference intervals.
"""

from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
from typing import Optional

from .models import Patient, Sex


class Level(str, Enum):
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    UNKNOWN = "unknown"


@dataclass
class RefRange:
    low: Optional[float]
    high: Optional[float]
    unit: str

    def classify(self, value: Optional[float]) -> Level:
        if value is None:
            return Level.UNKNOWN
        if self.low is not None and value < self.low:
            return Level.LOW
        if self.high is not None and value > self.high:
            return Level.HIGH
        return Level.NORMAL


# Static ranges that don't need sex/age. Keyed by canonical lab name.
_STATIC = {
    "lipase":         RefRange(0, 60, "U/L"),
    "amylase":        RefRange(0, 100, "U/L"),
    "hba1c":          RefRange(4.0, 5.7, "%"),
    "fasting_glucose": RefRange(70, 100, "mg/dL"),
    "egfr":           RefRange(60, None, "mL/min/1.73m2"),
    "ceruloplasmin":  RefRange(20, 35, "mg/dL"),
    "serum_copper":   RefRange(70, 155, "ug/dL"),
    "zinc":           RefRange(60, 120, "ug/dL"),
    "c_peptide":      RefRange(0.8, 3.1, "ng/mL"),
    "triglycerides":  RefRange(0, 150, "mg/dL"),
    "tsh":            RefRange(0.4, 4.0, "mIU/L"),
    "free_t4":        RefRange(0.8, 1.8, "ng/dL"),
    "resting_hr":     RefRange(60, 100, "bpm"),
    "calcitonin":     RefRange(0, 10, "pg/mL"),
}


def _sex_range(name: str, sex: Sex) -> Optional[RefRange]:
    """Ranges that differ by sex."""
    if name == "alt":
        return RefRange(0, 33 if sex == Sex.FEMALE else 41, "U/L")
    if name == "ast":
        return RefRange(0, 32 if sex == Sex.FEMALE else 40, "U/L")
    if name == "total_testosterone":
        return (RefRange(15, 70, "ng/dL") if sex == Sex.FEMALE
                else RefRange(300, 1000, "ng/dL"))
    if name == "prolactin":
        return RefRange(0, 29 if sex == Sex.FEMALE else 18, "ng/mL")
    if name == "hdl":
        return RefRange(50 if sex == Sex.FEMALE else 40, None, "mg/dL")
    return None


def range_for(name: str, patient: Patient) -> Optional[RefRange]:
    if name in _STATIC:
        return _STATIC[name]
    return _sex_range(name, patient.sex)


def classify(name: str, patient: Patient) -> Level:
    rr = range_for(name, patient)
    if rr is None:
        return Level.UNKNOWN
    return rr.classify(patient.lab(name))


# ---------------------------------------------------------------------------
# Derived quantities
# ---------------------------------------------------------------------------

def bmi(patient: Patient) -> Optional[float]:
    if patient.weight_kg and patient.height_cm:
        m = patient.height_cm / 100.0
        return round(patient.weight_kg / (m * m), 1)
    return patient.lab("bmi")


def egfr(patient: Patient) -> Optional[float]:
    """Prefer a measured eGFR lab; otherwise leave to explicit value.

    (A full CKD-EPI 2021 implementation would need serum creatinine; we accept
    a precomputed eGFR to keep the prototype lab-agnostic.)
    """
    return patient.lab("egfr")


def igf1_sd(patient: Patient) -> Optional[float]:
    """IGF-1 is best expressed as an age/sex SD (z) score. We accept a
    precomputed 'igf1_sd' lab; if only a raw igf1 (ng/mL) is present we return
    None rather than guess, because the age normalization matters clinically."""
    return patient.lab("igf1_sd")


def x_uln(name: str, patient: Patient) -> Optional[float]:
    """Value as a multiple of the upper limit of normal (for gates like
    'lipase >= 3x ULN')."""
    rr = range_for(name, patient)
    v = patient.lab(name)
    if rr is None or rr.high is None or v is None:
        return None
    return round(v / rr.high, 2)
