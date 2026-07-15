# Peptide Readiness & Response Model

A blood-based clinical decision-support layer for peptide programs (Tasso-collected samples).

Splits into two halves by design:
- **Tier 1 — Safety:** a deterministic, source-traceable rules engine returning red / yellow / green gates per peptide.
- **Tier 2 — Response:** a calibrated probabilistic model estimating likely response and side-effect risk (guidance, not a guarantee).
- **Tier 3 — Monitoring:** 8–12 week re-draw plans that also feed the response model over time.

Covers GLP-1 / GIP, GHK-Cu, sermorelin / GH secretagogues, and BPC-157.

## Contents

- `Peptide_Readiness_Model_Design.md` — technical design document (architecture, feasibility, validation, regulatory posture, sources).
- `peptide_readiness_engine.py` — runnable prototype of the model core.

## Run the prototype

```bash
python3 peptide_readiness_engine.py
```

Prints red/yellow/green safety reports plus a Tier-2 response score for a set of sample patients.

> Not medical, legal, or regulatory advice. Thresholds are demonstration defaults requiring medical-director validation before clinical use.
