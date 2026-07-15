#!/usr/bin/env python3
"""
Interactive intake for the Peptide Insight Engine.

Run it and answer the questions — it builds a patient from your answers, runs
the engine, and prints the report. Press Enter to skip any question you don't
have data for (the engine will flag important missing baselines for you).

    python3 intake.py

Everything you type stays local; nothing is sent anywhere.
"""

from __future__ import annotations

from peptide_insight_engine import InsightEngine, render_report
from peptide_insight_engine.models import Patient, LabResult, Medication, Sex
from peptide_insight_engine.knowledge.peptides import PEPTIDES, get_peptide


# ---------------------------------------------------------------------------
# small prompt helpers (forgiving: blank = skip)
# ---------------------------------------------------------------------------

def ask(prompt: str) -> str:
    return input(prompt).strip()


def ask_float(prompt: str) -> float | None:
    while True:
        raw = ask(prompt)
        if raw == "":
            return None
        try:
            return float(raw)
        except ValueError:
            print("   ! please enter a number (or press Enter to skip)")


def ask_int(prompt: str, lo: int | None = None, hi: int | None = None) -> int | None:
    while True:
        raw = ask(prompt)
        if raw == "":
            return None
        try:
            v = int(raw)
            if (lo is not None and v < lo) or (hi is not None and v > hi):
                print(f"   ! enter a value between {lo} and {hi}")
                continue
            return v
        except ValueError:
            print("   ! please enter a whole number (or press Enter to skip)")


def ask_choice_multi(prompt: str, options: list[str]) -> list[str]:
    """Show a numbered menu; accept comma-separated picks. Blank = none."""
    print(prompt)
    for i, opt in enumerate(options, 1):
        print(f"   {i:>2}. {opt}")
    raw = ask("   pick numbers (comma-separated), or Enter for none: ")
    if not raw:
        return []
    picked = []
    for tok in raw.replace(" ", "").split(","):
        if tok.isdigit() and 1 <= int(tok) <= len(options):
            picked.append(options[int(tok) - 1])
    return picked


# ---------------------------------------------------------------------------
# human-friendly labels for the controlled vocabularies
# ---------------------------------------------------------------------------

CONDITION_CHOICES = [
    "type_2_diabetes", "type_1_diabetes", "diabetic_retinopathy",
    "pancreatitis_history", "gallbladder_disease", "mtc_men2",
    "wilsons_disease", "active_malignancy", "malignancy_history",
    "pituitary_disease", "adrenal_insufficiency", "hypothyroidism",
    "chronic_kidney_disease", "hepatic_impairment", "cardiovascular_disease",
    "eating_disorder", "pregnancy", "breastfeeding",
]

MED_CHOICES = [
    "insulin", "sulfonylurea", "warfarin", "doac", "antiplatelet",
    "oral_contraceptive", "glucocorticoid", "levothyroxine", "metformin",
]

LAB_UNITS = {
    "lipase": "U/L", "hba1c": "%", "fasting_glucose": "mg/dL",
    "egfr": "mL/min/1.73m2", "ceruloplasmin": "mg/dL", "serum_copper": "ug/dL",
    "zinc": "ug/dL", "c_peptide": "ng/mL", "triglycerides": "mg/dL",
    "tsh": "mIU/L", "free_t4": "ng/dL", "resting_hr": "bpm", "alt": "U/L",
    "ast": "U/L", "igf1_sd": "SD score", "total_testosterone": "ng/dL",
    "calcitonin": "pg/mL",
}


def main() -> None:
    print("\n" + "=" * 60)
    print(" PEPTIDE INSIGHT ENGINE — interactive intake")
    print("=" * 60)
    print(" Press Enter to skip anything you don't have.\n")

    # 1. which peptide(s)
    peptide_ids = list(PEPTIDES.keys())
    labels = [f"{PEPTIDES[p].name}" for p in peptide_ids]
    chosen_names = ask_choice_multi("Which peptide(s) do you want to evaluate?", labels)
    if not chosen_names:
        print("No peptide selected — evaluating ALL of them.")
        chosen = peptide_ids
    else:
        chosen = [peptide_ids[labels.index(n)] for n in chosen_names]

    # 2. demographics
    print("\n-- Basics --")
    age = ask_int("Age: ", 0, 120) or 40
    sex_raw = ask("Sex (M/F): ").upper()
    sex = Sex.FEMALE if sex_raw.startswith("F") else Sex.MALE
    weight = ask_float("Weight in kg (optional): ")
    height = ask_float("Height in cm (optional): ")

    # 3. labs — only ask the ones relevant to the chosen peptides
    needed: list[str] = []
    for pid in chosen:
        for bm in get_peptide(pid).key_biomarkers:
            if bm not in needed:
                needed.append(bm)
    print("\n-- Labs (Enter to skip any) --")
    labs: dict[str, LabResult] = {}
    for bm in needed:
        unit = LAB_UNITS.get(bm, "")
        v = ask_float(f"{bm} ({unit}): ")
        if v is not None:
            labs[bm] = LabResult(bm, v, unit)

    # 4. conditions
    print()
    conds = set(ask_choice_multi("-- Conditions / history --", CONDITION_CHOICES))

    # 5. family history (just MTC/MEN2 matters most here)
    fam = set()
    if ask("\nFamily history of medullary thyroid cancer / MEN2? (y/N): ").lower().startswith("y"):
        fam.add("mtc_men2")

    # 6. medications
    print()
    med_classes = ask_choice_multi("-- Current medications (by class) --", MED_CHOICES)
    meds = [Medication(mc.replace("_", " "), mc) for mc in med_classes]

    # 7. genetics (only if GLP-1 chosen)
    genetics: dict[str, int] = {}
    if "glp1" in chosen:
        print("\n-- Genetics (optional; improves GLP-1 prediction) --")
        g1 = ask_int("GLP1R effect-allele count (0/1/2): ", 0, 2)
        g2 = ask_int("GIPR risk-allele count (0/1/2): ", 0, 2)
        if g1 is not None:
            genetics["GLP1R_effect"] = g1
        if g2 is not None:
            genetics["GIPR_risk"] = g2

    patient = Patient(
        patient_id="INTERACTIVE", age=age, sex=sex,
        weight_kg=weight, height_cm=height,
        labs=labs, conditions=conds, family_history=fam,
        medications=meds, genetics=genetics,
    )

    # 8. run + print
    engine = InsightEngine()
    print("\n")
    for pid in chosen:
        evaluation = engine.evaluate(patient, pid)
        print(render_report(patient, evaluation))
        print()

    print("Done. (Not medical advice — prototype output for provider review.)")


if __name__ == "__main__":
    try:
        main()
    except (KeyboardInterrupt, EOFError):
        print("\nCancelled.")
