"""
Patient profiling.

Derives higher-level *physiological states* from raw labs + history so the
reasoning layer can talk about the patient the way a clinician would ("stage 3b
CKD", "beta-cell reserve low", "reproductive-age female", "elderly") instead of
re-deriving these facts in every rule.

This is the layer that makes the engine "account for all types of patients":
every special population is turned into a boolean/enum state here, once.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional

from .models import Patient, Sex
from . import reference_ranges as rr


@dataclass
class PatientProfile:
    # anthropometrics
    bmi: Optional[float]
    # renal
    egfr: Optional[float]
    renal_stage: str                 # "normal" / "mild" / "moderate" / "severe" / "unknown"
    # metabolic
    glycemic_state: str              # "normal" / "prediabetes" / "diabetes" / "unknown"
    beta_cell_reserve: str           # "adequate" / "reduced" / "severely_reduced" / "unknown"
    insulin_treated: bool
    hypoglycemia_risk_meds: bool     # on insulin or sulfonylurea
    # hepatic
    hepatic_flag: bool
    # cardiovascular
    tachycardia: bool
    cardiovascular_disease: bool
    # endocrine / GH axis
    igf1_sd: Optional[float]
    thyroid_state: str               # "normal" / "hypo" / "hyper" / "unknown"
    # life stage / reproductive
    life_stage: str                  # "pediatric" / "adult" / "elderly"
    pregnancy: bool
    breastfeeding: bool
    reproductive_age_female: bool
    # copper axis
    copper_state: str                # "normal" / "low_ceruloplasmin" / "high_copper" / "unknown"
    # convenience
    archetypes: list[str] = field(default_factory=list)


def _renal_stage(egfr: Optional[float]) -> str:
    if egfr is None:
        return "unknown"
    if egfr >= 90:
        return "normal"
    if egfr >= 60:
        return "mild"
    if egfr >= 30:
        return "moderate"
    return "severe"


def _glycemic_state(p: Patient) -> str:
    if p.has("type_1_diabetes") or p.has("type_2_diabetes"):
        return "diabetes"
    a1c = p.lab("hba1c")
    if a1c is None:
        return "unknown"
    if a1c >= 6.5:
        return "diabetes"
    if a1c >= 5.7:
        return "prediabetes"
    return "normal"


def _beta_cell_reserve(p: Patient) -> str:
    """Lower fasting C-peptide => reduced beta-cell reserve => worse GLP-1
    glycemic response (Jones et al., Diabetes Care 2016)."""
    c = p.lab("c_peptide")
    if c is None:
        return "unknown"
    if c < 0.25:
        return "severely_reduced"
    if c < 0.8:
        return "reduced"
    return "adequate"


def _thyroid_state(p: Patient) -> str:
    tsh = p.lab("tsh")
    if p.has("hypothyroidism"):
        return "hypo"
    if tsh is None:
        return "unknown"
    if tsh > 4.0:
        return "hypo"
    if tsh < 0.4:
        return "hyper"
    return "normal"


def _life_stage(age: int) -> str:
    if age < 18:
        return "pediatric"
    if age >= 65:
        return "elderly"
    return "adult"


def _copper_state(p: Patient) -> str:
    cer = p.lab("ceruloplasmin")
    cu = p.lab("serum_copper")
    if cer is not None and cer < 20:
        return "low_ceruloplasmin"
    if cu is not None and cu > 155:
        return "high_copper"
    if cer is None and cu is None:
        return "unknown"
    return "normal"


def build_profile(p: Patient) -> PatientProfile:
    egfr = rr.egfr(p)
    hr = p.lab("resting_hr")

    prof = PatientProfile(
        bmi=rr.bmi(p),
        egfr=egfr,
        renal_stage=_renal_stage(egfr),
        glycemic_state=_glycemic_state(p),
        beta_cell_reserve=_beta_cell_reserve(p),
        insulin_treated=p.on_med_class("insulin") or p.has("type_1_diabetes"),
        hypoglycemia_risk_meds=p.on_med_class("insulin") or p.on_med_class("sulfonylurea"),
        hepatic_flag=p.has("hepatic_impairment")
                     or rr.classify("alt", p) == rr.Level.HIGH
                     or rr.classify("ast", p) == rr.Level.HIGH,
        tachycardia=(hr is not None and hr > 100),
        cardiovascular_disease=p.has("cardiovascular_disease"),
        igf1_sd=rr.igf1_sd(p),
        thyroid_state=_thyroid_state(p),
        life_stage=_life_stage(p.age),
        pregnancy=p.has("pregnancy"),
        breastfeeding=p.has("breastfeeding"),
        reproductive_age_female=(p.sex == Sex.FEMALE and 12 <= p.age <= 51
                                 and not p.has("pregnancy")),
        copper_state=_copper_state(p),
    )
    prof.archetypes = _archetypes(p, prof)
    return prof


def _archetypes(p: Patient, prof: PatientProfile) -> list[str]:
    """Human-readable tags summarizing who this patient is."""
    tags = []
    if prof.life_stage == "elderly":
        tags.append("elderly")
    if prof.life_stage == "pediatric":
        tags.append("pediatric")
    if prof.pregnancy:
        tags.append("pregnant")
    if prof.breastfeeding:
        tags.append("breastfeeding")
    if prof.renal_stage in ("moderate", "severe"):
        tags.append(f"renal-impaired ({prof.renal_stage})")
    if prof.hepatic_flag:
        tags.append("hepatic-impaired")
    if prof.glycemic_state == "diabetes":
        tags.append("diabetic")
    if prof.insulin_treated:
        tags.append("insulin-treated")
    if prof.cardiovascular_disease:
        tags.append("cardiovascular disease")
    if prof.bmi is not None and prof.bmi >= 30:
        tags.append("obesity")
    if not tags:
        tags.append("otherwise-healthy adult")
    return tags
