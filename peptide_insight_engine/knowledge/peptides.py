"""
The peptide knowledge base.

Each Peptide is a structured record: mechanism, the biomarkers that matter for
it, hard contraindications (matched against patient condition keys), the
medication classes it interacts with, its monitoring markers, and an honest
evidence grade. The reasoning layer reads these records — it does not hard-code
peptide facts itself.
"""

from __future__ import annotations
from dataclasses import dataclass, field


@dataclass
class Peptide:
    id: str
    name: str
    drug_class: str
    mechanism: str
    # condition keys (models.KNOWN_CONDITIONS) that are hard stops
    absolute_contraindications: dict[str, str] = field(default_factory=dict)
    # condition keys that warrant caution (value = why)
    relative_contraindications: dict[str, str] = field(default_factory=dict)
    # biomarkers that must be reviewed before/while on therapy
    key_biomarkers: list[str] = field(default_factory=list)
    # monitoring plan strings
    monitoring: list[str] = field(default_factory=list)
    # 'strong' / 'moderate' / 'limited' / 'experimental'
    evidence_grade: str = "moderate"
    notes: str = ""


PEPTIDES: dict[str, Peptide] = {

    "glp1": Peptide(
        id="glp1",
        name="GLP-1 / GIP agonist (semaglutide, tirzepatide)",
        drug_class="incretin_agonist",
        mechanism=("Agonizes the GLP-1 (and, for tirzepatide, GIP) receptor: "
                   "enhances glucose-dependent insulin secretion, suppresses "
                   "glucagon, slows gastric emptying, and increases satiety."),
        absolute_contraindications={
            "mtc_men2": "Boxed warning: personal/family history of medullary "
                        "thyroid carcinoma or MEN2 (rodent C-cell tumor signal).",
            "pregnancy": "Animal data show fetal harm; contraindicated in pregnancy.",
        },
        relative_contraindications={
            "pancreatitis_history": "Prior pancreatitis raises recurrence concern.",
            "gallbladder_disease": "GLP-1s increase cholelithiasis risk.",
            "diabetic_retinopathy": "Rapid glucose lowering can transiently worsen "
                                    "retinopathy, especially with insulin.",
            "gastroparesis": "Further delayed gastric emptying is poorly tolerated.",
            "eating_disorder": "Appetite suppression is hazardous in ED history.",
            "breastfeeding": "Insufficient lactation safety data; generally avoided.",
        },
        key_biomarkers=["lipase", "hba1c", "c_peptide", "egfr", "triglycerides",
                        "calcitonin", "resting_hr"],
        monitoring=[
            "Lipase: baseline; recheck if abdominal pain (flag >=3x ULN).",
            "HbA1c + weight: baseline and 12 weeks (efficacy).",
            "Renal function: during dose escalation if GI losses (dehydration/AKI).",
            "Retinal exam: if pre-existing retinopathy + large expected HbA1c drop.",
        ],
        evidence_grade="strong",
    ),

    "ghk_cu": Peptide(
        id="ghk_cu",
        name="GHK-Cu (copper tripeptide)",
        drug_class="copper_peptide",
        mechanism=("Glycyl-L-histidyl-L-lysine bound to copper(II); delivers "
                   "copper and modulates tissue remodeling, angiogenesis and "
                   "antioxidant gene expression."),
        absolute_contraindications={
            "wilsons_disease": "Impaired copper excretion; copper-containing "
                               "therapy is contraindicated.",
            "menkes_disease": "Disordered copper metabolism; avoid copper load.",
        },
        relative_contraindications={
            "hepatic_impairment": "Liver is the primary route of copper excretion.",
        },
        key_biomarkers=["ceruloplasmin", "serum_copper", "zinc"],
        monitoring=[
            "Ceruloplasmin + serum copper: baseline (Wilson's screen), recheck at 12 wks.",
            "Zinc: baseline and 12 wks — copper/zinc are antagonists; cycle dosing.",
        ],
        evidence_grade="limited",
        notes="Human systemic-therapy evidence is thin; topical evidence stronger.",
    ),

    "sermorelin": Peptide(
        id="sermorelin",
        name="Sermorelin / GH secretagogue",
        drug_class="gh_secretagogue",
        mechanism=("GHRH analog that stimulates pulsatile pituitary GH release, "
                   "raising downstream IGF-1. Preserves physiologic feedback "
                   "better than exogenous rhGH."),
        absolute_contraindications={
            "active_malignancy": "GH/IGF-1 are mitogenic; contraindicated in "
                                 "active or suspected malignancy.",
            "proliferative_retinopathy": "Contraindicated per GH labeling.",
        },
        relative_contraindications={
            "malignancy_history": "Prior cancer warrants oncology input.",
            "type_2_diabetes": "GH reduces insulin sensitivity; may worsen control.",
            "pituitary_disease": "May unmask central hypoadrenalism / hypothyroidism.",
            "adrenal_insufficiency": "GH can lower cortisol; adjust glucocorticoids.",
        },
        key_biomarkers=["igf1_sd", "fasting_glucose", "hba1c", "free_t4",
                        "total_testosterone"],
        monitoring=[
            "IGF-1 SD: baseline, 4 wks, 12 wks — titrate to keep <= +2 SD.",
            "Fasting glucose / HbA1c: baseline and 12 wks (insulin sensitivity).",
            "Free T4 & cortisol: monitor if pituitary/adrenal risk (GH lowers both).",
        ],
        evidence_grade="moderate",
    ),

    "bpc157": Peptide(
        id="bpc157",
        name="BPC-157 (research repair peptide)",
        drug_class="research_peptide",
        mechanism=("Synthetic pentadecapeptide; promotes angiogenesis and tissue "
                   "repair in animal models. Human mechanism/PK largely "
                   "uncharacterized."),
        absolute_contraindications={
            "active_malignancy": "Pro-angiogenic signaling is theorized; avoid "
                                 "pending human evidence.",
        },
        relative_contraindications={
            "malignancy_history": "Precautionary given angiogenic activity.",
        },
        key_biomarkers=["alt", "ast"],
        monitoring=[
            "Baseline organ safety (ALT/AST); recheck at 12 wks.",
            "No validated biomarker predicts response — clinical follow-up only.",
        ],
        evidence_grade="experimental",
        notes=("Not FDA-approved; removed from 503B bulk-compounding eligibility "
               "in 2024 over safety/immunogenicity concerns."),
    ),
}


def get_peptide(peptide_id: str) -> Peptide:
    if peptide_id not in PEPTIDES:
        raise ValueError(f"Unknown peptide '{peptide_id}'. Known: {list(PEPTIDES)}")
    return PEPTIDES[peptide_id]
