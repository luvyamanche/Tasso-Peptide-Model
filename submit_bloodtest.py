#!/usr/bin/env python3
"""
Submit a blood test and get an insight report.

Two ways to use it:

  1. A self-contained JSON submission (patient context + labs + peptides):
       python3 submit_bloodtest.py sample_submission.json

  2. A plain lab CSV plus demographics on the command line:
       python3 submit_bloodtest.py sample_bloodtest.csv \
           --age 61 --sex M --weight 104 --height 178 \
           --conditions type_2_diabetes,diabetic_retinopathy \
           --meds insulin,sulfonylurea,warfarin \
           --peptide glp1

Add --json to emit a structured JSON payload instead of the text report.

The parser understands common lab-name variants (e.g. "Hemoglobin A1c",
"A1C", "HgbA1c") and converts common units, and it will tell you about
anything it could not map.
"""

from __future__ import annotations
import argparse
import os
import sys

from peptide_insight_engine import InsightEngine, render_report
from peptide_insight_engine.report import to_json
from peptide_insight_engine.bloodtest import patient_from_csv, load_submission
from peptide_insight_engine.knowledge.peptides import PEPTIDES


def _csv_list(v: str | None) -> list[str]:
    return [x.strip() for x in v.split(",")] if v else []


def main() -> None:
    ap = argparse.ArgumentParser(description="Run the peptide engine on a blood test.")
    ap.add_argument("file", help="path to a lab CSV or a JSON submission")
    ap.add_argument("--peptide", help="peptide id (glp1, ghk_cu, sermorelin, bpc157). "
                    "Repeatable via comma. Defaults to all for CSV.")
    ap.add_argument("--age", type=int, default=40)
    ap.add_argument("--sex", default="M")
    ap.add_argument("--weight", type=float)
    ap.add_argument("--height", type=float)
    ap.add_argument("--conditions", help="comma-separated condition keys")
    ap.add_argument("--meds", help="comma-separated medication classes")
    ap.add_argument("--family", help="comma-separated family-history keys (e.g. mtc_men2)")
    ap.add_argument("--json", action="store_true", help="emit JSON instead of text")
    args = ap.parse_args()

    if not os.path.exists(args.file):
        sys.exit(f"File not found: {args.file}")

    is_json = args.file.lower().endswith(".json")

    if is_json:
        patient, parsed, peptides = load_submission(args.file)
        if args.peptide:
            peptides = _csv_list(args.peptide)
    else:
        patient, parsed = patient_from_csv(
            args.file, age=args.age, sex=args.sex,
            weight_kg=args.weight, height_cm=args.height,
            conditions=set(_csv_list(args.conditions)),
            medications=_csv_list(args.meds),
            family_history=set(_csv_list(args.family)),
        )
        peptides = _csv_list(args.peptide) or list(PEPTIDES.keys())

    engine = InsightEngine()

    # --- JSON mode: one clean machine-readable object, no human preamble ---
    if args.json:
        import json
        received = {
            "recognized_labs": {k: {"value": r.value, "unit": r.unit}
                                for k, r in parsed.labs.items()},
            "warnings": parsed.warnings,
            "unmapped": parsed.unmapped,
        }
        evaluations = []
        for pid in peptides:
            if pid in PEPTIDES:
                evaluations.append(json.loads(to_json(engine.evaluate(patient, pid))))
        print(json.dumps({"received": received, "evaluations": evaluations,
                          "disclaimer": "Not medical advice — prototype output "
                                        "for provider review."}, indent=2))
        return

    # --- text mode: show what the parser understood, then the reports ---
    print("=" * 78)
    print("BLOOD TEST RECEIVED")
    print("=" * 78)
    if parsed.labs:
        print("Recognized labs:")
        for k, r in parsed.labs.items():
            print(f"  - {k}: {r.value} {r.unit}")
    else:
        print("  (no recognized labs — check the file format)")
    for w in parsed.warnings:
        print(f"  note: {w}")
    if parsed.unmapped:
        print("Could not map (ignored):")
        for u in parsed.unmapped:
            print(f"  ? {u}")
    print()

    for pid in peptides:
        if pid not in PEPTIDES:
            print(f"(skipping unknown peptide '{pid}')")
            continue
        print(render_report(patient, engine.evaluate(patient, pid)))
        print()

    print("Not medical advice — prototype output intended for provider review.")


if __name__ == "__main__":
    main()
