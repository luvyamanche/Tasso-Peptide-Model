"""
Diverse sample patients spanning the patient types the engine must handle.

Each is annotated with the scenario it exercises so the demo doubles as a
readable test of coverage.
"""

from __future__ import annotations

from .models import Patient, LabResult, Medication, Sex


def _labs(**kw) -> dict[str, LabResult]:
    units = {
        "lipase": "U/L", "amylase": "U/L", "hba1c": "%", "fasting_glucose": "mg/dL",
        "egfr": "mL/min/1.73m2", "ceruloplasmin": "mg/dL", "serum_copper": "ug/dL",
        "zinc": "ug/dL", "c_peptide": "ng/mL", "triglycerides": "mg/dL",
        "tsh": "mIU/L", "free_t4": "ng/dL", "resting_hr": "bpm", "alt": "U/L",
        "ast": "U/L", "igf1_sd": "SD", "total_testosterone": "ng/dL",
    }
    return {k: LabResult(k, v, units.get(k, "")) for k, v in kw.items()}


SAMPLES: list[tuple[Patient, list[str]]] = [

    # 1. Healthy adult, favorable GLP-1 responder genetics
    (Patient(
        "P-01", 42, Sex.FEMALE, weight_kg=95, height_cm=165,
        labs=_labs(lipase=35, hba1c=5.9, c_peptide=2.4, egfr=98, triglycerides=140,
                   resting_hr=72),
        genetics={"GLP1R_effect": 2, "GIPR_risk": 0},
    ), ["glp1"]),

    # 2. Complex diabetic on insulin + sulfonylurea + warfarin: interaction storm
    (Patient(
        "P-02", 61, Sex.MALE, weight_kg=104, height_cm=178,
        labs=_labs(lipase=48, hba1c=9.4, c_peptide=0.5, egfr=54, triglycerides=210,
                   resting_hr=105),
        conditions={"type_2_diabetes", "diabetic_retinopathy", "cardiovascular_disease"},
        medications=[Medication("insulin glargine", "insulin", "subcutaneous"),
                     Medication("glipizide", "sulfonylurea"),
                     Medication("warfarin", "warfarin")],
        genetics={"GLP1R_effect": 1, "GIPR_risk": 1},
    ), ["glp1"]),

    # 3. Reproductive-age female on oral contraceptive considering tirzepatide
    (Patient(
        "P-03", 29, Sex.FEMALE, weight_kg=88, height_cm=170,
        labs=_labs(lipase=30, hba1c=5.6, c_peptide=2.9, egfr=110, resting_hr=68),
        medications=[Medication("ethinylestradiol/levonorgestrel", "oral_contraceptive")],
        genetics={"GLP1R_effect": 1, "GIPR_risk": 2},
    ), ["glp1"]),

    # 4. Absolute contraindication: MTC/MEN2 family history + high lipase
    (Patient(
        "P-04", 50, Sex.MALE, weight_kg=99, height_cm=175,
        labs=_labs(lipase=205, hba1c=6.2, egfr=80),
        family_history={"mtc_men2"},
    ), ["glp1"]),

    # 5. GHK-Cu candidate with low ceruloplasmin (Wilson's screen) + low zinc
    (Patient(
        "P-05", 37, Sex.FEMALE, weight_kg=63, height_cm=168,
        labs=_labs(ceruloplasmin=16, serum_copper=88, zinc=62),
    ), ["ghk_cu"]),

    # 6. Sermorelin candidate: prediabetic on levothyroxine + glucocorticoid
    (Patient(
        "P-06", 55, Sex.MALE, weight_kg=90, height_cm=180,
        labs=_labs(igf1_sd=0.4, hba1c=6.1, fasting_glucose=108, free_t4=1.0,
                   total_testosterone=420),
        conditions={"pituitary_disease"},
        medications=[Medication("levothyroxine", "levothyroxine"),
                     Medication("hydrocortisone", "glucocorticoid")],
    ), ["sermorelin"]),

    # 7. Sermorelin hard stop: IGF-1 already high + malignancy history
    (Patient(
        "P-07", 48, Sex.MALE, weight_kg=85, height_cm=176,
        labs=_labs(igf1_sd=2.7, hba1c=5.4),
        conditions={"malignancy_history"},
    ), ["sermorelin"]),

    # 8. BPC-157 on a DOAC: experimental + anticoagulant interaction
    (Patient(
        "P-08", 34, Sex.MALE, weight_kg=80, height_cm=182,
        labs=_labs(alt=26, ast=24),
        medications=[Medication("apixaban", "doac")],
    ), ["bpc157"]),

    # 9. Elderly, renal impairment, sparse panel (missing-baseline handling)
    (Patient(
        "P-09", 74, Sex.FEMALE, weight_kg=70, height_cm=160,
        labs=_labs(egfr=38, hba1c=7.8),
        conditions={"type_2_diabetes"},
        medications=[Medication("insulin degludec", "insulin", "subcutaneous")],
    ), ["glp1"]),

    # 10. Pregnant patient: absolute contraindication path
    (Patient(
        "P-10", 31, Sex.FEMALE, weight_kg=78, height_cm=167,
        labs=_labs(lipase=33, hba1c=5.5, c_peptide=2.5, egfr=105),
        conditions={"pregnancy"},
    ), ["glp1"]),
]
