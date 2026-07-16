"""
Blood-test intake: parse a real lab report into a Patient the engine can run.

Handles the messy reality of lab data:
  - maps many real-world lab NAMES (e.g. "Hemoglobin A1c", "A1C", "HgbA1c")
    to the engine's canonical keys
  - converts common UNIT variants (e.g. HbA1c mmol/mol -> %, glucose mmol/L ->
    mg/dL) so the numbers land in the ranges the engine expects
  - reports anything it could not map, instead of silently dropping it

Accepts two file shapes:
  1. A plain lab CSV (columns: test/name, result/value, unit) + separate
     demographics passed in by the caller.
  2. A self-contained JSON "submission" bundling patient context + labs.
"""

from __future__ import annotations
import csv
import json
import re
from dataclasses import dataclass, field
from typing import Optional

from .models import Patient, LabResult, Medication, Sex


# ---------------------------------------------------------------------------
# Synonyms: canonical key -> the many ways a lab might name it
# ---------------------------------------------------------------------------

SYNONYMS: dict[str, list[str]] = {
    "hba1c": ["hba1c", "a1c", "hemoglobin a1c", "haemoglobin a1c", "hgba1c",
              "hgb a1c", "glycated hemoglobin", "glycosylated hemoglobin"],
    "lipase": ["lipase", "serum lipase"],
    "amylase": ["amylase", "serum amylase"],
    "fasting_glucose": ["fasting glucose", "glucose fasting", "fasting blood glucose",
                        "glucose", "blood glucose", "glucose serum"],
    "egfr": ["egfr", "e gfr", "estimated gfr", "gfr", "ckd epi egfr",
             "egfr ckd epi", "estimated glomerular filtration rate"],
    "ceruloplasmin": ["ceruloplasmin"],
    "serum_copper": ["copper", "serum copper", "copper serum", "cu"],
    "zinc": ["zinc", "serum zinc", "zn"],
    "c_peptide": ["c peptide", "c-peptide", "cpeptide", "fasting c peptide"],
    "triglycerides": ["triglycerides", "triglyceride", "trig", "trigs", "tg"],
    "tsh": ["tsh", "thyroid stimulating hormone", "thyrotropin"],
    "free_t4": ["free t4", "ft4", "free thyroxine", "t4 free", "thyroxine free"],
    "resting_hr": ["resting heart rate", "heart rate", "resting hr", "pulse", "hr"],
    "alt": ["alt", "alanine aminotransferase", "sgpt", "alt sgpt"],
    "ast": ["ast", "aspartate aminotransferase", "sgot", "ast sgot"],
    "igf1_sd": ["igf 1 sd", "igf1 sd", "igf 1 sd score", "igf1 z score",
                "igf 1 z score", "igf1 standard deviation"],
    "total_testosterone": ["testosterone", "total testosterone", "testosterone total",
                           "testosterone serum"],
    "calcitonin": ["calcitonin"],
    "hdl": ["hdl", "hdl cholesterol", "hdl c"],
}

# raw IGF-1 (ng/mL) can't be interpreted without age/sex norms; recognize it so
# we can warn instead of silently ignoring it.
_RAW_IGF1 = ["igf 1", "igf1", "insulin like growth factor 1", "insulin like growth factor"]


def _norm(name: str) -> str:
    """Lowercase, strip units-in-parens and punctuation, collapse spaces."""
    s = name.lower()
    s = re.sub(r"\(.*?\)", " ", s)          # drop "(SGPT)" etc.
    s = re.sub(r"[^a-z0-9]+", " ", s)        # punctuation -> space
    return re.sub(r"\s+", " ", s).strip()


_REVERSE: dict[str, str] = {}
for _canon, _names in SYNONYMS.items():
    for _n in _names:
        _REVERSE[_norm(_n)] = _canon
for _n in _RAW_IGF1:
    _REVERSE[_norm(_n)] = "_raw_igf1"


# ---------------------------------------------------------------------------
# Unit conversions into the engine's expected units
# ---------------------------------------------------------------------------

EXPECTED_UNIT = {
    "hba1c": "%", "fasting_glucose": "mg/dL", "triglycerides": "mg/dL",
    "total_testosterone": "ng/dL", "serum_copper": "ug/dL", "egfr": "mL/min/1.73m2",
    "lipase": "U/L", "c_peptide": "ng/mL", "resting_hr": "bpm",
}


def _convert(canon: str, value: float, unit: str) -> tuple[float, Optional[str]]:
    """Return (converted_value, warning_or_None)."""
    u = _norm(unit)
    if canon == "hba1c" and "mmol" in u:                 # IFCC mmol/mol -> NGSP %
        return round(value / 10.929 + 2.15, 2), "converted HbA1c mmol/mol -> %"
    if canon == "fasting_glucose" and "mmol" in u:       # mmol/L -> mg/dL
        return round(value * 18.0182, 0), "converted glucose mmol/L -> mg/dL"
    if canon == "triglycerides" and "mmol" in u:         # mmol/L -> mg/dL
        return round(value * 88.57, 0), "converted triglycerides mmol/L -> mg/dL"
    if canon == "total_testosterone" and "nmol" in u:    # nmol/L -> ng/dL
        return round(value * 28.85, 0), "converted testosterone nmol/L -> ng/dL"
    return value, None


# ---------------------------------------------------------------------------
# Result of parsing
# ---------------------------------------------------------------------------

@dataclass
class ParsedLabs:
    labs: dict[str, LabResult] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    unmapped: list[str] = field(default_factory=list)


def parse_rows(rows: list[dict]) -> ParsedLabs:
    """rows: list of {name, value, unit}."""
    out = ParsedLabs()
    for row in rows:
        name = str(row.get("name", "")).strip()
        if not name:
            continue
        canon = _REVERSE.get(_norm(name))
        raw_val = row.get("value")
        try:
            value = float(raw_val)
        except (TypeError, ValueError):
            out.unmapped.append(f"{name} (non-numeric value '{raw_val}')")
            continue
        unit = str(row.get("unit", "")).strip()

        if canon is None:
            out.unmapped.append(f"{name} = {value} {unit}".strip())
            continue
        if canon == "_raw_igf1":
            out.warnings.append(
                f"'{name}' given as a raw IGF-1 value; the engine needs an "
                f"age/sex SD score ('igf1_sd'). Skipped — provide IGF-1 SD.")
            continue

        value, warn = _convert(canon, value, unit)
        if warn:
            out.warnings.append(warn)
        out.labs[canon] = LabResult(canon, value, EXPECTED_UNIT.get(canon, unit))
    return out


# ---------------------------------------------------------------------------
# File loaders
# ---------------------------------------------------------------------------

def _rows_from_csv(path: str) -> list[dict]:
    with open(path, newline="", encoding="utf-8-sig") as f:
        sample = f.read(2048)
        f.seek(0)
        # sniff delimiter, fall back to comma
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
        except csv.Error:
            dialect = csv.excel
        reader = csv.reader(f, dialect)
        raw = [r for r in reader if any(c.strip() for c in r)]

    if not raw:
        return []

    # Identify columns by header keywords; else assume name,value,unit positional.
    header = [_norm(c) for c in raw[0]]
    name_i = _find(header, ["test", "name", "analyte", "marker", "component"])
    val_i = _find(header, ["result", "value", "reading"])
    unit_i = _find(header, ["unit", "units"])
    has_header = name_i is not None and val_i is not None
    if not has_header:
        name_i, val_i, unit_i = 0, 1, (2 if len(raw[0]) > 2 else None)
        body = raw
    else:
        body = raw[1:]

    rows = []
    for r in body:
        if len(r) <= val_i:
            continue
        rows.append({
            "name": r[name_i],
            "value": r[val_i],
            "unit": r[unit_i] if (unit_i is not None and len(r) > unit_i) else "",
        })
    return rows


def _find(header: list[str], keys: list[str]) -> Optional[int]:
    for i, h in enumerate(header):
        if any(k in h for k in keys):
            return i
    return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def patient_from_csv(path: str, *, patient_id="BLOODTEST", age=40, sex="M",
                     weight_kg=None, height_cm=None, conditions=None,
                     medications=None, family_history=None,
                     genetics=None) -> tuple[Patient, ParsedLabs]:
    parsed = parse_rows(_rows_from_csv(path))
    patient = _build_patient(parsed.labs, dict(
        patient_id=patient_id, age=age, sex=sex, weight_kg=weight_kg,
        height_cm=height_cm, conditions=conditions, medications=medications,
        family_history=family_history, genetics=genetics))
    return patient, parsed


def load_submission(path: str) -> tuple[Patient, ParsedLabs, list[str]]:
    """Load a self-contained JSON submission: {patient:{...}, labs:[...], peptides:[...]}."""
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    labs_in = data.get("labs", [])
    # labs may be a list of {name,value,unit} or a dict {name: value}
    if isinstance(labs_in, dict):
        labs_in = [{"name": k, "value": v} for k, v in labs_in.items()]
    parsed = parse_rows(labs_in)
    meta = data.get("patient", {})
    patient = _build_patient(parsed.labs, meta)
    peptides = data.get("peptides") or data.get("peptide") or []
    if isinstance(peptides, str):
        peptides = [peptides]
    return patient, parsed, peptides


def _build_patient(labs: dict[str, LabResult], meta: dict) -> Patient:
    sex = Sex.FEMALE if str(meta.get("sex", "M")).upper().startswith("F") else Sex.MALE
    meds = []
    for m in (meta.get("medications") or []):
        if isinstance(m, dict):
            meds.append(Medication(m.get("name", m.get("drug_class", "")),
                                    m.get("drug_class", ""), m.get("route", "oral")))
        else:  # bare class string
            meds.append(Medication(str(m).replace("_", " "), str(m)))
    return Patient(
        patient_id=meta.get("patient_id", "BLOODTEST"),
        age=int(meta.get("age", 40)),
        sex=sex,
        weight_kg=meta.get("weight_kg"),
        height_cm=meta.get("height_cm"),
        labs=labs,
        conditions=set(meta.get("conditions") or []),
        medications=meds,
        family_history=set(meta.get("family_history") or []),
        genetics=dict(meta.get("genetics") or {}),
    )
