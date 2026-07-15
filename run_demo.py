#!/usr/bin/env python3
"""
Demo runner for the Peptide Insight Engine.

Usage:
    python3 run_demo.py                # text reports for all sample patients
    python3 run_demo.py --json         # JSON payloads instead
    python3 run_demo.py --patient P-02 # a single patient

Run from the Tasso folder (the folder that contains peptide_insight_engine/).
"""

from __future__ import annotations
import argparse

from peptide_insight_engine import InsightEngine, render_report
from peptide_insight_engine.report import to_json
from peptide_insight_engine.sample_patients import SAMPLES


def main() -> None:
    ap = argparse.ArgumentParser(description="Peptide Insight Engine demo")
    ap.add_argument("--json", action="store_true", help="emit JSON instead of text")
    ap.add_argument("--patient", help="only run this patient id (e.g. P-02)")
    args = ap.parse_args()

    engine = InsightEngine()

    for patient, peptide_ids in SAMPLES:
        if args.patient and patient.patient_id != args.patient:
            continue
        for pid in peptide_ids:
            evaluation = engine.evaluate(patient, pid)
            if args.json:
                print(to_json(evaluation))
            else:
                print(render_report(patient, evaluation))
            print()


if __name__ == "__main__":
    main()
