"""
Peptide Readiness & Safety Engine  —  Tasso / blood-draw peptide program
========================================================================

A working prototype of the clinical decision-support core described in the
three-tier product spec:

  Tier 1  Readiness & Safety Panel  -> red / yellow / green gating + thresholds
  Tier 2  Response Predictor        -> probabilistic response / side-effect score
  Tier 3  Longitudinal Monitoring   -> delta checks vs. baseline at 8-12 weeks

DESIGN INTENT
-------------
This is deliberately a *deterministic, auditable rules engine* for the safety
layer (Tier 1) with a *transparent scoring model* for the response layer
(Tier 2). In a regulated CDS product the safety gates MUST be explainable and
traceable to a clinical source — a black-box neural net is the wrong tool for
"should this person inject this drug." The ML lives in Tier 2 (probabilistic
guidance), never in the hard safety gates.

Every threshold below carries a `source` tag so the rule is traceable. The
values here are reasonable, literature-aligned defaults for a PROTOTYPE — they
are NOT a validated clinical protocol and must be signed off by the medical
director before any real use.

Output is always routed to a human provider for review (matches the spec:
"results routed into your EMR for provider review").
"""

from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Optional
import json


# ---------------------------------------------------------------------------
# 1. Core data structures
# ---------------------------------------------------------------------------

class Flag(Enum):
    GREEN = "green"     # clear to proceed, standard monitoring
    YELLOW = "yellow"   # proceed with caution / provider judgement / extra monitoring
    RED = "red"         # do not initiate without resolving; possible contraindication

    @property
    def rank(self) -> int:
        return {"green": 0, "yellow": 1, "red": 2}[self.value]


@dataclass
class Analyte:
    """A single lab result. Units matter — kept explicit to avoid unit bugs."""
    name: str
    value: float
    unit: str


@dataclass
class Patient:
    """Intake + history. History flags come from your existing provider intake."""
    patient_id: str
    age: int
    sex: str                              # "M" / "F"
    labs: dict[str, Analyte] = field(default_factory=dict)
    history: dict[str, bool] = field(default_factory=dict)  # e.g. {"mtc_men2": False}
    genetics: dict[str, int] = field(default_factory=dict)  # allele dosage 0/1/2

    def lab(self, key: str) -> Optional[float]:
        a = self.labs.get(key)
        return a.value if a else None


@dataclass
class Finding:
    """One rule's verdict, fully traceable."""
    analyte: str
    flag: Flag
    message: str
    source: str
    value: Optional[float] = None
    threshold: Optional[str] = None


@dataclass
class MonitoringItem:
    analyte: str
    cadence: str
    threshold: str
    rationale: str


# ---------------------------------------------------------------------------
# 2. Reference ranges (adult; sex-aware where it matters)
#    Prototype defaults — medical director to confirm against lab's own ranges.
# ---------------------------------------------------------------------------

def ref_alt_upper(p: Patient) -> float:
    return 33.0 if p.sex == "F" else 41.0    # U/L, rough clinical ULN

REF = {
    "lipase_uln":        60.0,    # U/L
    "amylase_uln":       100.0,   # U/L
    "egfr_low":          60.0,    # mL/min/1.73m2
    "hba1c_diab":        6.5,     # %
    "hba1c_pre":         5.7,     # %
    "fasting_glucose_high": 100,  # mg/dL (impaired fasting)
    "fasting_glucose_diab": 126,  # mg/dL
    "igf1_sd_high":      2.0,     # SD score above age/sex mean
    "ceruloplasmin_low": 20.0,    # mg/dL (Wilson's screen threshold)
    "prolactin_uln_m":   18.0,    # ng/mL
    "prolactin_uln_f":   29.0,    # ng/mL
}


# ---------------------------------------------------------------------------
# 3. Peptide safety-gate definitions  (Tier 1)
#    Each peptide is a list of rule functions. A rule returns a Finding or None.
#    Keeping rules as small pure functions makes them unit-testable and auditable.
# ---------------------------------------------------------------------------

def _mult_uln(value: Optional[float], uln: float) -> Optional[float]:
    if value is None:
        return None
    return value / uln


# ---- GLP-1 / GIP class (semaglutide, tirzepatide) ----

def glp1_mtc_history(p: Patient) -> Optional[Finding]:
    if p.history.get("mtc_men2"):
        return Finding("history:MTC/MEN2", Flag.RED,
                       "Personal/family history of medullary thyroid carcinoma or MEN2 — "
                       "boxed-warning contraindication for GLP-1/GIP agonists.",
                       "FDA boxed warning (GLP-1 class labeling)")
    return None

def glp1_pancreatitis_history(p: Patient) -> Optional[Finding]:
    if p.history.get("pancreatitis"):
        return Finding("history:pancreatitis", Flag.RED,
                       "Prior pancreatitis — relative/absolute contraindication; do not "
                       "initiate without specialist review.",
                       "Clinical guideline (GLP-1 long-term use)")
    return None

def glp1_lipase(p: Patient) -> Optional[Finding]:
    x = _mult_uln(p.lab("lipase"), REF["lipase_uln"])
    if x is None:
        return Finding("lipase", Flag.YELLOW, "Baseline lipase not provided — required before GLP-1.",
                       "Trial monitoring practice")
    if x >= 3.0:
        return Finding("lipase", Flag.RED,
                       f"Lipase {x:.1f}x ULN (>=3x). Evaluate for pancreatitis before initiating.",
                       "GLP-1 trial safety rule (>=3x ULN)", value=x, threshold=">=3x ULN")
    if x >= 1.0:
        return Finding("lipase", Flag.YELLOW,
                       f"Lipase {x:.1f}x ULN (mildly elevated). Provider judgement; recheck on therapy.",
                       "Trial monitoring practice", value=x, threshold="1-3x ULN")
    return Finding("lipase", Flag.GREEN, "Lipase within range.", "Reference range", value=x)

def glp1_egfr(p: Patient) -> Optional[Finding]:
    v = p.lab("egfr")
    if v is None:
        return None
    if v < 30:
        return Finding("egfr", Flag.RED,
                       f"eGFR {v:.0f} — severe renal impairment; dehydration from GI side effects "
                       "raises acute kidney injury risk.", "Renal safety", value=v, threshold="<30")
    if v < REF["egfr_low"]:
        return Finding("egfr", Flag.YELLOW,
                       f"eGFR {v:.0f} — reduced renal function; monitor hydration and function.",
                       "Renal safety", value=v, threshold="<60")
    return Finding("egfr", Flag.GREEN, "Renal function adequate.", "Reference range", value=v)


# ---- GHK-Cu (copper peptide) ----

def ghkcu_wilsons_history(p: Patient) -> Optional[Finding]:
    if p.history.get("wilsons"):
        return Finding("history:Wilson's", Flag.RED,
                       "Known Wilson's disease — copper-containing therapy contraindicated.",
                       "Copper metabolism contraindication")
    return None

def ghkcu_ceruloplasmin(p: Patient) -> Optional[Finding]:
    v = p.lab("ceruloplasmin")
    if v is None:
        return Finding("ceruloplasmin", Flag.YELLOW,
                       "Ceruloplasmin not provided — Wilson's screen required before GHK-Cu.",
                       "Wilson's screen")
    if v < REF["ceruloplasmin_low"]:
        return Finding("ceruloplasmin", Flag.RED,
                       f"Ceruloplasmin {v:.0f} mg/dL (low) — screen for Wilson's disease before "
                       "any copper-containing therapy.", "Wilson's screen (<20 mg/dL)",
                       value=v, threshold="<20 mg/dL")
    return Finding("ceruloplasmin", Flag.GREEN, "Ceruloplasmin within range.", "Reference range", value=v)

def ghkcu_copper(p: Patient) -> Optional[Finding]:
    v = p.lab("serum_copper")
    if v is None:
        return None
    if v > 155:   # ug/dL rough ULN
        return Finding("serum_copper", Flag.YELLOW,
                       f"Serum copper {v:.0f} ug/dL elevated — avoid adding copper load; investigate.",
                       "Copper balance", value=v, threshold=">155 ug/dL")
    return Finding("serum_copper", Flag.GREEN, "Serum copper within range.", "Reference range", value=v)


# ---- Sermorelin / GH secretagogues ----

def sermorelin_malignancy(p: Patient) -> Optional[Finding]:
    if p.history.get("active_malignancy"):
        return Finding("history:malignancy", Flag.RED,
                       "Active/suspected malignancy — GH/IGF-1 can promote proliferation; "
                       "contraindicated.", "GH-axis contraindication")
    return None

def sermorelin_igf1(p: Patient) -> Optional[Finding]:
    v = p.lab("igf1_sd")   # SD score vs age/sex norm
    if v is None:
        return Finding("igf1_sd", Flag.YELLOW,
                       "Baseline IGF-1 not provided — required to set response/safety ceiling.",
                       "GH-axis monitoring")
    if v > REF["igf1_sd_high"]:
        return Finding("igf1_sd", Flag.RED,
                       f"IGF-1 {v:+.1f} SD (already high) — do not stimulate GH axis further.",
                       "GH-axis safety (>+2 SD)", value=v, threshold=">+2 SD")
    if v > 1.0:
        return Finding("igf1_sd", Flag.YELLOW,
                       f"IGF-1 {v:+.1f} SD (upper end) — cap dose, recheck early.",
                       "GH-axis monitoring", value=v, threshold="+1 to +2 SD")
    return Finding("igf1_sd", Flag.GREEN, "IGF-1 in acceptable range.", "Reference range", value=v)

def sermorelin_glycemia(p: Patient) -> Optional[Finding]:
    a1c = p.lab("hba1c")
    if a1c is None:
        return None
    if a1c >= REF["hba1c_diab"]:
        return Finding("hba1c", Flag.YELLOW,
                       f"HbA1c {a1c:.1f}% (diabetic range) — GH reduces insulin sensitivity; "
                       "co-manage glycemia and monitor closely.", "GH/insulin interaction",
                       value=a1c, threshold=">=6.5%")
    if a1c >= REF["hba1c_pre"]:
        return Finding("hba1c", Flag.YELLOW,
                       f"HbA1c {a1c:.1f}% (pre-diabetic) — monitor fasting glucose on therapy.",
                       "GH/insulin interaction", value=a1c, threshold="5.7-6.4%")
    return Finding("hba1c", Flag.GREEN, "Glycemia normal.", "Reference range", value=a1c)


# ---- BPC-157 (research repair peptide; thin human evidence) ----

def bpc157_evidence_notice(p: Patient) -> Optional[Finding]:
    return Finding("evidence", Flag.YELLOW,
                   "BPC-157 has minimal human clinical-safety data and is not FDA-approved. "
                   "No validated blood biomarker predicts response. Treat as experimental; "
                   "informed-consent and provider judgement required.",
                   "Evidence-quality gate")

def bpc157_malignancy(p: Patient) -> Optional[Finding]:
    if p.history.get("active_malignancy"):
        return Finding("history:malignancy", Flag.RED,
                       "Active/suspected malignancy — angiogenic/proliferative signals theorized; "
                       "avoid pending evidence.", "Precautionary gate")
    return None

def bpc157_liver(p: Patient) -> Optional[Finding]:
    alt = p.lab("alt")
    if alt is None:
        return None
    if alt > 3 * ref_alt_upper(p):
        return Finding("alt", Flag.RED, f"ALT {alt:.0f} (>3x ULN) — resolve hepatic issue first.",
                       "Baseline organ safety", value=alt, threshold=">3x ULN")
    if alt > ref_alt_upper(p):
        return Finding("alt", Flag.YELLOW, f"ALT {alt:.0f} mildly elevated — recheck.",
                       "Baseline organ safety", value=alt)
    return Finding("alt", Flag.GREEN, "Liver enzymes within range.", "Reference range", value=alt)


# Registry: peptide -> ordered list of gate functions
SAFETY_GATES: dict[str, list[Callable[[Patient], Optional[Finding]]]] = {
    "glp1": [glp1_mtc_history, glp1_pancreatitis_history, glp1_lipase, glp1_egfr],
    "ghk_cu": [ghkcu_wilsons_history, ghkcu_ceruloplasmin, ghkcu_copper],
    "sermorelin": [sermorelin_malignancy, sermorelin_igf1, sermorelin_glycemia],
    "bpc157": [bpc157_evidence_notice, bpc157_malignancy, bpc157_liver],
}

PEPTIDE_LABELS = {
    "glp1": "GLP-1 / GIP agonist (e.g. semaglutide, tirzepatide)",
    "ghk_cu": "GHK-Cu (copper peptide)",
    "sermorelin": "Sermorelin / GH secretagogue",
    "bpc157": "BPC-157 (research repair peptide)",
}


# ---------------------------------------------------------------------------
# 4. Monitoring plans (Tier 3 baseline -> re-test at 8-12 wks)
# ---------------------------------------------------------------------------

MONITORING: dict[str, list[MonitoringItem]] = {
    "glp1": [
        MonitoringItem("lipase", "baseline, then if symptomatic", "flag >=3x ULN",
                       "Detect drug-associated pancreatitis."),
        MonitoringItem("hba1c", "baseline + 12 wks", "efficacy trend",
                       "Metabolic efficacy signal."),
        MonitoringItem("weight", "baseline + 8-12 wks", "% change",
                       "Primary efficacy endpoint."),
    ],
    "ghk_cu": [
        MonitoringItem("ceruloplasmin", "baseline + 12 wks", "flag <20 mg/dL", "Copper safety."),
        MonitoringItem("zinc", "baseline + 12 wks", "avoid depletion", "Copper-zinc balance."),
    ],
    "sermorelin": [
        MonitoringItem("igf1_sd", "baseline, 4 wks, 12 wks", "keep <=+2 SD",
                       "Titrate to response without overshoot."),
        MonitoringItem("fasting_glucose", "baseline + 12 wks", "watch rise",
                       "GH lowers insulin sensitivity."),
    ],
    "bpc157": [
        MonitoringItem("alt", "baseline + 12 wks", "organ safety", "Experimental — general safety."),
    ],
}


# ---------------------------------------------------------------------------
# 5. Tier 2 — Response Predictor (transparent scoring stub)
#    In production this is a calibrated model trained on your longitudinal
#    outcomes; here it is a documented linear scorer using published signals
#    (GLP1R/GIPR dosage, BMI, sex) so the mechanics are inspectable.
# ---------------------------------------------------------------------------

def glp1_response_score(p: Patient) -> dict:
    """Returns probabilistic guidance, NOT a guarantee.

    Signals (illustrative weights, to be replaced by a fitted+calibrated model):
      - GLP1R effect-allele dosage  -> higher weight-loss response
      - GIPR risk-allele dosage     -> higher nausea/vomiting risk (tirzepatide)
      - Higher baseline BMI         -> larger absolute response
      - Female sex                  -> modestly higher predicted response (per satiation data)
    """
    glp1r = p.genetics.get("GLP1R_effect", 0)     # 0/1/2
    gipr = p.genetics.get("GIPR_risk", 0)         # 0/1/2
    bmi = p.lab("bmi") or 30.0
    female = 1 if p.sex == "F" else 0

    # --- response likelihood (0-100, illustrative logistic) ---
    z = -0.4 + 0.35 * glp1r + 0.05 * (bmi - 30) + 0.25 * female
    resp = 1 / (1 + pow(2.718281828, -z))
    response_pct = round(resp * 100)

    # --- GI side-effect risk band ---
    # Nature GWAS: homozygous risk at both GLP1R & GIPR ~ up to 15x vomiting odds on tirzepatide
    gi_load = glp1r + gipr
    if glp1r == 2 and gipr == 2:
        gi_band = "high"
    elif gi_load >= 2:
        gi_band = "moderate"
    else:
        gi_band = "low"

    return {
        "response_likelihood_pct": response_pct,
        "gi_side_effect_risk": gi_band,
        "drivers": {"GLP1R_effect": glp1r, "GIPR_risk": gipr, "bmi": bmi, "sex": p.sex},
        "disclaimer": "Probabilistic guidance for provider discussion, not a guarantee. "
                      "Variance explained by such models is modest (~25% for weight loss).",
    }


RESPONSE_PREDICTORS = {"glp1": glp1_response_score}


# ---------------------------------------------------------------------------
# 6. Report assembly
# ---------------------------------------------------------------------------

@dataclass
class PeptideReport:
    peptide: str
    label: str
    overall: Flag
    findings: list[Finding]
    monitoring: list[MonitoringItem]
    response: Optional[dict] = None

    def to_dict(self) -> dict:
        return {
            "peptide": self.peptide,
            "label": self.label,
            "overall_flag": self.overall.value,
            "findings": [
                {"analyte": f.analyte, "flag": f.flag.value, "message": f.message,
                 "source": f.source, "value": f.value, "threshold": f.threshold}
                for f in self.findings
            ],
            "monitoring_plan": [
                {"analyte": m.analyte, "cadence": m.cadence,
                 "threshold": m.threshold, "rationale": m.rationale}
                for m in self.monitoring
            ],
            "response_prediction": self.response,
        }


def evaluate(patient: Patient, peptide: str) -> PeptideReport:
    if peptide not in SAFETY_GATES:
        raise ValueError(f"Unknown peptide '{peptide}'. Known: {list(SAFETY_GATES)}")

    findings: list[Finding] = []
    for gate in SAFETY_GATES[peptide]:
        f = gate(patient)
        if f is not None:
            findings.append(f)

    overall = Flag.GREEN
    for f in findings:
        if f.flag.rank > overall.rank:
            overall = f.flag

    response = None
    if peptide in RESPONSE_PREDICTORS and overall is not Flag.RED:
        response = RESPONSE_PREDICTORS[peptide](patient)

    return PeptideReport(
        peptide=peptide,
        label=PEPTIDE_LABELS[peptide],
        overall=overall,
        findings=findings,
        monitoring=MONITORING.get(peptide, []),
        response=response,
    )


# ---------------------------------------------------------------------------
# 7. Pretty-printer (provider-facing red/yellow/green summary)
# ---------------------------------------------------------------------------

_ICON = {Flag.GREEN: "[GREEN] ", Flag.YELLOW: "[YELLOW]", Flag.RED: "[RED]   "}

def render(patient: Patient, report: PeptideReport) -> str:
    lines = []
    lines.append("=" * 72)
    lines.append(f"PATIENT {patient.patient_id}  ({patient.age}{patient.sex})   ->   {report.label}")
    lines.append(f"OVERALL: {report.overall.value.upper()}")
    lines.append("-" * 72)
    for f in sorted(report.findings, key=lambda x: -x.flag.rank):
        lines.append(f"  {_ICON[f.flag]} {f.analyte}: {f.message}")
        lines.append(f"            source: {f.source}")
    if report.response:
        r = report.response
        lines.append("-" * 72)
        lines.append(f"  RESPONSE PREDICTOR (Tier 2):")
        lines.append(f"     likely response: {r['response_likelihood_pct']}%   "
                     f"GI side-effect risk: {r['gi_side_effect_risk']}")
        lines.append(f"     drivers: {r['drivers']}")
    lines.append("-" * 72)
    lines.append("  MONITORING PLAN (Tier 3):")
    for m in report.monitoring:
        lines.append(f"     - {m.analyte}: {m.cadence}  ({m.threshold}) — {m.rationale}")
    lines.append("=" * 72)
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# 8. Demo — sample patients spanning green / yellow / red
# ---------------------------------------------------------------------------

def _labs(**kw) -> dict[str, Analyte]:
    units = {"lipase": "U/L", "amylase": "U/L", "egfr": "mL/min/1.73m2",
             "hba1c": "%", "ceruloplasmin": "mg/dL", "serum_copper": "ug/dL",
             "igf1_sd": "SD", "alt": "U/L", "bmi": "kg/m2", "fasting_glucose": "mg/dL",
             "zinc": "ug/dL", "prolactin": "ng/mL"}
    return {k: Analyte(k, v, units.get(k, "")) for k, v in kw.items()}


def demo():
    patients = [
        # GREEN GLP-1 candidate, favorable genetics
        (Patient("P-1001", 44, "F",
                 labs=_labs(lipase=40, egfr=95, hba1c=5.9, bmi=34),
                 history={"mtc_men2": False, "pancreatitis": False},
                 genetics={"GLP1R_effect": 2, "GIPR_risk": 0}),
         "glp1"),
        # RED GLP-1: MTC/MEN2 history + high lipase
        (Patient("P-1002", 52, "M",
                 labs=_labs(lipase=210, egfr=72, hba1c=6.1, bmi=31),
                 history={"mtc_men2": True},
                 genetics={"GLP1R_effect": 1, "GIPR_risk": 2}),
         "glp1"),
        # YELLOW GHK-Cu: low ceruloplasmin -> Wilson's screen
        (Patient("P-1003", 38, "F",
                 labs=_labs(ceruloplasmin=16, serum_copper=90),
                 history={"wilsons": False}),
         "ghk_cu"),
        # RED sermorelin: already-high IGF-1
        (Patient("P-1004", 47, "M",
                 labs=_labs(igf1_sd=2.6, hba1c=5.4, fasting_glucose=92),
                 history={"active_malignancy": False}),
         "sermorelin"),
        # BPC-157: experimental notice + clean labs
        (Patient("P-1005", 35, "M",
                 labs=_labs(alt=28),
                 history={"active_malignancy": False}),
         "bpc157"),
    ]
    out = []
    for p, pep in patients:
        rep = evaluate(p, pep)
        out.append(render(p, rep))
    print("\n\n".join(out))


if __name__ == "__main__":
    demo()
