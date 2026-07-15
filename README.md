# Peptide Insight Engine

A clinical decision-support engine that takes **structured patient data** — labs,
demographics, conditions, medications, genetics — and produces **deep, contextual
insights** about how specific peptide therapies would interact with *that
individual patient*.

The goal is explicitly to go beyond "your cholesterol is low." The engine
reasons across multiple data points at once — for example, it recognizes that a
patient with low C-peptide *and* on insulin will get a **blunted glycemic
response to a GLP-1 while still being at high risk of hypoglycemia**, and says so,
with the reasoning and the source attached.

Covers four peptide classes: **GLP-1 / GIP agonists, GHK-Cu, sermorelin / GH
secretagogues, and BPC-157.**

> ⚠️ Research / prototype software. **Not medical advice.** Every threshold is a
> literature-aligned default that must be validated by a medical director before
> any clinical use.

---

## Quick start

From this folder (the one containing `peptide_insight_engine/`):

```bash
python3 run_demo.py                 # text reports for 10 sample patients
python3 run_demo.py --patient P-02  # one patient (the complex diabetic)
python3 run_demo.py --json          # structured JSON output for EMR/API use
```

No dependencies — pure Python 3.9+ standard library.

Minimal programmatic use:

```python
from peptide_insight_engine import InsightEngine, render_report
from peptide_insight_engine.models import Patient, LabResult, Medication, Sex

patient = Patient(
    "demo", age=61, sex=Sex.MALE, weight_kg=104, height_cm=178,
    labs={"hba1c": LabResult("hba1c", 9.4, "%"),
          "c_peptide": LabResult("c_peptide", 0.5, "ng/mL"),
          "egfr": LabResult("egfr", 54, "mL/min/1.73m2")},
    conditions={"type_2_diabetes", "diabetic_retinopathy"},
    medications=[Medication("insulin glargine", "insulin"),
                 Medication("glipizide", "sulfonylurea")],
    genetics={"GLP1R_effect": 1, "GIPR_risk": 1},
)

engine = InsightEngine()
evaluation = engine.evaluate(patient, "glp1")
print(render_report(patient, evaluation))
```

---

## How the code works

The engine is a pipeline of small, single-responsibility layers. Data flows in
one direction; each layer only depends on the ones above it. Nothing is a black
box — every insight carries a `rationale` (why it fired) and a `source`.

```
  raw patient data (labs, conditions, meds, genetics)
        │
        ▼
  reference_ranges.py   sex/age-aware interpretation + derived values
        │               (BMI, eGFR, IGF-1 SD, "x ULN")
        ▼
  patient_profile.py    derive physiological STATES & archetypes once
        │               (renal stage, beta-cell reserve, glycemic state,
        │                pregnancy, elderly, hepatic flag, …)
        ▼
  knowledge/            the facts, kept declarative & reviewable
        │   peptides.py       mechanisms, contraindications, biomarkers
        │   interactions.py   drug×peptide + biomarker×peptide tables
        ▼
  reasoning/            the thinking, kept transparent & sourced
        │   safety.py     deterministic red/yellow/green gates
        │   insights.py   drug interactions + CROSS-BIOMARKER compound
        │                 reasoning + special-population logic
        │   response.py   probabilistic response predictor (GLP-1)
        │   dosing.py     personalized titration guidance
        ▼
  engine.py             orchestrates the layers → PeptideEvaluation
        │
        ▼
  report.py             render_report (text) / to_json (structured)
```

### The layers, one by one

**`models.py` — the contract.** Defines every shared type: `Patient`,
`LabResult`, `Medication`, and the output types `Insight`, `ResponsePrediction`,
`PeptideEvaluation`. It also defines the **controlled vocabularies**
(`KNOWN_CONDITIONS`, `KNOWN_MED_CLASSES`) — patient conditions and medications
are *keys*, not free text, so they can be matched deterministically against the
knowledge base. An `Insight` is the core unit: a category, a severity, a
red/yellow/green flag (for safety items), plus `rationale` and `source`.

**`reference_ranges.py` — from numbers to meaning.** Holds sex/age-aware
reference intervals and classifies a value as low/normal/high. It also computes
the derived quantities the rest of the system needs: BMI, eGFR, IGF-1 SD score,
and "multiple of the upper limit of normal" (for gates like *lipase ≥ 3× ULN*).

**`patient_profile.py` — who is this patient?** Runs once and turns raw data
into physiological *states*: renal stage, glycemic state, **beta-cell reserve**
(from C-peptide), hepatic flag, thyroid state, life stage (pediatric / adult /
elderly), pregnancy / reproductive-age status, and copper state. This is the
layer that makes the engine "account for all types of patients" — every special
population is computed here **once**, so the reasoning rules stay clean. It also
emits human-readable `archetypes` ("elderly", "renal-impaired (moderate)",
"insulin-treated") shown at the top of each report.

**`knowledge/peptides.py` — the peptide facts.** Each peptide is a structured
record: mechanism, absolute vs. relative contraindications (as condition keys),
the biomarkers that matter, a monitoring plan, and an honest `evidence_grade`
(strong → experimental). The reasoning layer *reads* these records rather than
hard-coding peptide facts, so adding or editing a peptide is data entry.

**`knowledge/interactions.py` — the interaction tables.** Two declarative
tables: `DRUG_INTERACTIONS` (peptide × medication-class → effect, severity,
recommendation, source) and `BIOMARKER_EFFECTS` (how the peptide is expected to
move a lab). A clinician can review the entire interaction surface in this one
file.

**`reasoning/safety.py` — can they take it at all?** Deterministic gating only —
no probability here. It matches the peptide's contraindications against the
patient's conditions/family history (RED for absolute, YELLOW for relative),
applies numeric lab gates (lipase ≥3× ULN, low ceruloplasmin, IGF-1 > +2 SD),
and flags *required-but-missing* baselines as YELLOW so gaps never pass silently
as "safe". The overall flag is the worst individual flag.

**`reasoning/insights.py` — the differentiator.** This is where "deep" happens.
Three kinds of reasoning:
- *Drug interactions* — fires table entries against the patient's actual meds.
- *Cross-biomarker compound reasoning* — combines multiple data points, e.g.
  low beta-cell reserve **+** insulin (blunted response *and* hypoglycemia),
  retinopathy **+** high HbA1c **+** insulin (rapid-drop retinal risk), severe
  hypertriglyceridemia **+** pancreatitis history (stacked pancreatitis risk).
- *Special populations* — pregnancy, reproductive-age washout, elderly,
  pediatric, hepatic impairment.

**`reasoning/response.py` — will it work? (Tier 2)** A transparent, inspectable
scorer for GLP-1 combining published signals (GLP1R/GIPR genotype, BMI, sex,
beta-cell reserve, baseline HbA1c) into a response likelihood, a GI side-effect
risk band, and a **confidence** level that reflects how much signal was actually
available. It is deliberately *not* a black box: in production the same
structure is swapped for a model calibrated on your own outcomes. Peptides
without a validated predictor return nothing rather than fake precision.

**`reasoning/dosing.py` — so what do I do? (Tier 1.5)** Turns the profile into
concrete titration guidance: slow escalation for elderly/renal patients,
pre-emptive insulin/sulfonylurea reduction, IGF-1 dose caps, GHK-Cu cycling.

**`engine.py` — the orchestrator.** `InsightEngine.evaluate(patient,
peptide_id)` profiles the patient, runs every layer, sorts insights (most severe
first), skips the response predictor if hard-contraindicated, and returns a
`PeptideEvaluation`. `evaluate_all(patient)` runs every peptide.

**`report.py` — output.** `render_report` produces the grouped, provider-facing
text report; `to_json` produces a structured payload for EMR/API integration.

### Why the safety/response split matters

Safety is **deterministic and traceable** (a provider and a regulator can see
exactly why someone was flagged); response is **probabilistic and calibrated**.
A good predicted response can never override a safety contraindication — the
engine enforces this by skipping the predictor whenever the overall flag is RED.

---

## Adding to the engine

- **A new peptide:** add a record to `PEPTIDES` in `knowledge/peptides.py`
  (contraindications, biomarkers, monitoring). Add interaction rows in
  `knowledge/interactions.py`. Compound reasoning is optional.
- **A new drug interaction:** add a `DrugInteraction` row to the peptide's list
  in `knowledge/interactions.py`. No code changes needed.
- **A new compound insight:** add a rule to the relevant `_..._compound`
  function in `reasoning/insights.py`.
- **A new patient state / population:** add it to `patient_profile.py` so every
  rule can use it.

---

## Files in this folder

| File | What it is |
|------|-----------|
| `peptide_insight_engine/` | The engine (this README describes it). |
| `run_demo.py` | Runs the engine over 10 diverse sample patients. |
| `peptide_insight_engine/sample_patients.py` | The 10 patients (healthy → complex diabetic → contraindicated → pregnant → elderly). |
| `Peptide_Readiness_Model_Design.md` | The design/strategy document: feasibility research, three-tier product, validation, and CLIA/FDA regulatory posture. |
| `peptide_readiness_engine.py` | The earlier single-file prototype (superseded by the package; kept for reference). |

---

## Sample patients (what each one tests)

| ID | Scenario |
|----|----------|
| P-01 | Healthy adult, favorable GLP-1 responder genetics |
| P-02 | Complex diabetic on insulin + sulfonylurea + warfarin (interaction storm + compound reasoning) |
| P-03 | Reproductive-age female on oral contraceptive (tirzepatide contraception rule) |
| P-04 | MTC/MEN2 family history + high lipase → **RED** |
| P-05 | GHK-Cu with low ceruloplasmin (Wilson's screen) + low zinc |
| P-06 | Sermorelin, pituitary disease on glucocorticoid + levothyroxine (unmasking risk) |
| P-07 | Sermorelin with IGF-1 already high + cancer history → **RED** |
| P-08 | BPC-157 on a DOAC (experimental + anticoagulant interaction) |
| P-09 | Elderly + renal impairment + sparse panel (missing-baseline handling) |
| P-10 | Pregnant → **RED** |

---

*Not medical, legal, or regulatory advice. Thresholds are demonstration defaults
requiring medical-director validation before clinical use.*
