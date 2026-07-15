"""
Deep insight generation.

This is where the engine earns its name. Beyond "value X is low/high", it
combines *multiple* data points about the patient with peptide pharmacology to
produce contextual, actionable statements a clinician would actually value:

  - drug-interaction insights (peptide x the patient's actual medications)
  - anticipatory biomarker insights (how the peptide will move this patient's labs)
  - cross-biomarker reasoning (the compound insights, e.g. low beta-cell reserve
    + insulin therapy => simultaneously poor response AND high hypoglycemia risk)
  - special-population insights (pregnancy, elderly, renal, hepatic)

Each generator returns Insights; the engine concatenates them.
"""

from __future__ import annotations

from ..models import Patient, Insight, Category, Severity, Flag
from ..knowledge.peptides import Peptide
from ..knowledge.interactions import DRUG_INTERACTIONS, BIOMARKER_EFFECTS
from ..patient_profile import PatientProfile


def _sev_to_flag(sev: Severity) -> Flag:
    return {Severity.MODERATE: Flag.YELLOW, Severity.HIGH: Flag.YELLOW,
            Severity.CRITICAL: Flag.RED}.get(sev, Flag.GREEN)


# ---------------------------------------------------------------------------
# 1. Drug interactions (declarative table -> insights)
# ---------------------------------------------------------------------------

def drug_interactions(patient: Patient, peptide: Peptide) -> list[Insight]:
    out = []
    for di in DRUG_INTERACTIONS.get(peptide.id, []):
        if patient.on_med_class(di.trigger_med_class):
            meds = [m.name for m in patient.medications
                    if m.drug_class == di.trigger_med_class]
            out.append(Insight(
                category=Category.DRUG_INTERACTION,
                title=f"Interaction with {di.trigger_med_class.replace('_', ' ')} "
                      f"({', '.join(meds)})",
                detail=di.effect,
                severity=di.severity,
                rationale=f"Patient is taking {', '.join(meds)}.",
                source=di.source,
                recommendation=di.recommendation,
                flag=_sev_to_flag(di.severity),
            ))
    return out


# ---------------------------------------------------------------------------
# 2. Anticipatory biomarker effects
# ---------------------------------------------------------------------------

def biomarker_effects(patient: Patient, peptide: Peptide, prof: PatientProfile) -> list[Insight]:
    out = []
    for be in BIOMARKER_EFFECTS.get(peptide.id, []):
        baseline = patient.lab(be.biomarker)
        note = f" Baseline {be.biomarker} = {baseline}." if baseline is not None else ""
        out.append(Insight(
            category=Category.BIOMARKER,
            title=f"Expected {be.direction} in {be.biomarker}",
            detail=be.effect + note,
            severity=Severity.INFO,
            rationale="Known pharmacodynamic effect of the peptide.",
            source=be.source,
        ))
    return out


# ---------------------------------------------------------------------------
# 3. Cross-biomarker compound reasoning (the differentiator)
# ---------------------------------------------------------------------------

def cross_biomarker(patient: Patient, peptide: Peptide, prof: PatientProfile) -> list[Insight]:
    if peptide.id == "glp1":
        return _glp1_compound(patient, prof)
    if peptide.id == "sermorelin":
        return _sermorelin_compound(patient, prof)
    if peptide.id == "ghk_cu":
        return _ghkcu_compound(patient, prof)
    return []


def _glp1_compound(patient: Patient, prof: PatientProfile) -> list[Insight]:
    out = []

    # (a) beta-cell reserve x insulin/SU => response AND hypoglycemia interplay
    if prof.beta_cell_reserve in ("reduced", "severely_reduced"):
        c = patient.lab("c_peptide")
        detail = (f"Fasting C-peptide {c} ng/mL indicates {prof.beta_cell_reserve.replace('_',' ')} "
                  "beta-cell reserve, which predicts a weaker glycemic response to a "
                  "mechanism that depends on glucose-dependent insulin secretion.")
        rec = "Set realistic glycemic expectations; weight effect may still occur."
        if prof.hypoglycemia_risk_meds:
            detail += (" The patient is ALSO on an insulin secretagogue/insulin — so the "
                       "residual insulin effect that remains is enough to cause "
                       "hypoglycemia while overall glycemic response is blunted.")
            rec = ("Lower the sulfonylurea/insulin dose at initiation AND counsel that "
                   "glycemic (not weight) response may be modest.")
        out.append(Insight(
            category=Category.RESPONSE, title="Low beta-cell reserve shapes both response and risk",
            detail=detail, severity=Severity.MODERATE,
            rationale="Combines C-peptide with the patient's diabetes medications.",
            source="Jones et al., Diabetes Care 2016 (C-peptide predicts GLP-1 response)",
            recommendation=rec,
        ))

    # (b) retinopathy x insulin x high HbA1c => rapid-drop retinal risk
    a1c = patient.lab("hba1c")
    if patient.has("diabetic_retinopathy") and a1c is not None and a1c >= 9.0:
        extra = " Insulin co-therapy further increases this risk." if prof.insulin_treated else ""
        out.append(Insight(
            category=Category.SAFETY, title="Rapid HbA1c drop may transiently worsen retinopathy",
            detail=(f"Baseline HbA1c {a1c}% with existing diabetic retinopathy. A large, fast "
                    f"HbA1c reduction is the setting where transient retinopathy worsening was "
                    f"seen in semaglutide trials.{extra}"),
            severity=Severity.HIGH, flag=Flag.YELLOW,
            rationale="Combines retinopathy history, baseline HbA1c, and insulin use.",
            source="SUSTAIN-6 retinopathy analysis",
            recommendation="Baseline dilated retinal exam; titrate more gradually.",
        ))

    # (c) triglycerides x pancreatitis history => additive pancreatitis risk
    tg = patient.lab("triglycerides")
    if tg is not None and tg >= 500 and patient.has("pancreatitis_history"):
        out.append(Insight(
            category=Category.SAFETY, title="Compounded pancreatitis risk",
            detail=(f"Triglycerides {tg} mg/dL (severe hypertriglyceridemia) plus prior "
                    "pancreatitis — two independent pancreatitis risk factors stack."),
            severity=Severity.HIGH, flag=Flag.YELLOW,
            rationale="Combines triglycerides with pancreatitis history.",
            source="Hypertriglyceridemia-pancreatitis literature",
            recommendation="Lower triglycerides first; monitor lipase closely.",
        ))

    # (d) baseline tachycardia x known HR increase
    if prof.tachycardia:
        out.append(Insight(
            category=Category.MONITORING, title="Baseline tachycardia + expected HR rise",
            detail=(f"Resting HR {patient.lab('resting_hr')} bpm is already elevated; GLP-1s "
                    "add a further small resting-HR increase."),
            severity=Severity.LOW,
            rationale="Combines baseline resting HR with the peptide's HR effect.",
            source="GLP-1 class labeling",
            recommendation="Investigate the tachycardia; monitor HR on therapy.",
        ))

    # (e) favorable responder profile (positive framing)
    if (prof.beta_cell_reserve == "adequate" and prof.bmi is not None
            and prof.bmi >= 30 and patient.gene("GLP1R_effect") >= 1):
        out.append(Insight(
            category=Category.RESPONSE, title="Favorable responder profile",
            detail=("Adequate beta-cell reserve, obesity-range BMI, and a GLP1R effect allele "
                    "together predict an above-average response."),
            severity=Severity.INFO,
            rationale="Combines C-peptide, BMI, and GLP1R genotype.",
            source="Nature GWAS 2026 + beta-cell response literature",
        ))
    return out


def _sermorelin_compound(patient: Patient, prof: PatientProfile) -> list[Insight]:
    out = []
    # GH worsens glycemia — flag the diabetic/insulin-resistant patient
    if prof.glycemic_state in ("prediabetes", "diabetes"):
        detail = (f"Glycemic state '{prof.glycemic_state}' (HbA1c {patient.lab('hba1c')}%). GH "
                  "secretagogues reduce insulin sensitivity, so glucose is likely to drift up.")
        rec = "Monitor fasting glucose/HbA1c; co-manage glycemia."
        if prof.insulin_treated:
            detail += " On insulin — anticipate a possible increase in insulin requirement."
            rec = "Monitor glucose closely; be ready to up-titrate insulin."
        out.append(Insight(
            category=Category.BIOMARKER, title="GH stimulation may worsen glucose control",
            detail=detail, severity=Severity.MODERATE,
            rationale="Combines glycemic state with GH's insulin-antagonist effect.",
            source="GH labeling (somatropin)", recommendation=rec,
        ))
    # Pituitary/adrenal unmasking
    if patient.has("pituitary_disease") or patient.has("adrenal_insufficiency"):
        out.append(Insight(
            category=Category.SAFETY, title="Risk of unmasking hypoadrenalism / hypothyroidism",
            detail=("GH reverses cortisone->cortisol conversion and lowers free T4; in a patient "
                    "with pituitary/adrenal disease this can precipitate cortisol or thyroid "
                    "insufficiency."),
            severity=Severity.HIGH, flag=Flag.YELLOW,
            rationale="Combines pituitary/adrenal history with GH endocrine effects.",
            source="GH labeling / Endocrine Society guidance",
            recommendation="Check cortisol and free T4; adjust replacement before/with therapy.",
        ))
    return out


def _ghkcu_compound(patient: Patient, prof: PatientProfile) -> list[Insight]:
    out = []
    zinc = patient.lab("zinc")
    if zinc is not None and zinc < 70:
        out.append(Insight(
            category=Category.BIOMARKER, title="Low baseline zinc + copper loading",
            detail=(f"Baseline zinc {zinc} ug/dL is low-normal/low. Adding copper (a zinc "
                    "antagonist) chronically may deepen zinc depletion."),
            severity=Severity.MODERATE,
            rationale="Combines baseline zinc with copper/zinc antagonism.",
            source="Copper/zinc physiology",
            recommendation="Cycle dosing (e.g. 4 wks on/off); recheck zinc; consider repletion.",
        ))
    return out


# ---------------------------------------------------------------------------
# 4. Special-population insights
# ---------------------------------------------------------------------------

def special_populations(patient: Patient, peptide: Peptide, prof: PatientProfile) -> list[Insight]:
    out = []

    if prof.reproductive_age_female and peptide.id == "glp1":
        out.append(Insight(
            category=Category.SPECIAL_POPULATION, title="Reproductive-age female: contraception & washout",
            detail=("GLP-1s are contraindicated in pregnancy. Due to the long half-life, "
                    "semaglutide should be stopped >=8 weeks before planned conception."),
            severity=Severity.MODERATE, flag=Flag.YELLOW,
            rationale="Female of reproductive age not recorded as pregnant.",
            source="GLP-1 pregnancy guidance / labeling",
            recommendation="Ensure effective contraception; plan >=8-week washout pre-conception.",
        ))

    if prof.life_stage == "elderly":
        out.append(Insight(
            category=Category.SPECIAL_POPULATION, title="Elderly patient",
            detail=("Age >=65: greater vulnerability to GI-driven dehydration, hypoglycemia, "
                    "sarcopenia with rapid weight loss, and falls."),
            severity=Severity.LOW,
            rationale="Age-based risk modifier.",
            source="Geriatric prescribing principles",
            recommendation="Titrate slowly; monitor hydration, renal function, lean mass.",
        ))

    if prof.life_stage == "pediatric":
        out.append(Insight(
            category=Category.SPECIAL_POPULATION, title="Pediatric patient",
            detail="Peptide use in minors requires specialist oversight and indication-specific approval.",
            severity=Severity.HIGH, flag=Flag.YELLOW,
            rationale="Age < 18.", source="Pediatric prescribing principles",
            recommendation="Refer to pediatric specialist; do not initiate in primary program.",
        ))

    if prof.hepatic_flag and peptide.id in ("ghk_cu", "bpc157", "glp1"):
        out.append(Insight(
            category=Category.SPECIAL_POPULATION, title="Hepatic impairment",
            detail=("Reduced hepatic function affects clearance/excretion (copper for GHK-Cu) "
                    "and baseline organ-safety margin."),
            severity=Severity.MODERATE, flag=Flag.YELLOW,
            rationale="ALT/AST elevated or hepatic impairment recorded.",
            source="Hepatic dosing principles",
            recommendation="Confirm hepatic status; monitor LFTs; caution with copper load.",
        ))

    return out


# ---------------------------------------------------------------------------
# Aggregate
# ---------------------------------------------------------------------------

def all_insights(patient: Patient, peptide: Peptide, prof: PatientProfile) -> list[Insight]:
    out = []
    out += drug_interactions(patient, peptide)
    out += cross_biomarker(patient, peptide, prof)
    out += special_populations(patient, peptide, prof)
    out += biomarker_effects(patient, peptide, prof)
    return out
