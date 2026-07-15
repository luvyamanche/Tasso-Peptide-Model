# Peptide Readiness & Response Model — Technical Design

**A blood-based clinical decision-support layer for peptide programs (Tasso-collected samples)**

Prepared July 15, 2026 · Prototype accompanies this document (`peptide_readiness_engine.py`)

---

## 1. What we are building and why

Patients start peptides largely blind. The provider network screens intake, but there is no objective, blood-based layer answering the two questions everyone has before injecting: *is this safe for my specific body*, and *am I actually likely to respond*. This model is the software core that turns a Tasso blood draw into a provider-facing answer to both.

Critically, this is **not** one monolithic "AI that reads blood." A single black-box model deciding whether someone should inject a drug is the wrong architecture — it is unauditable, unregulatable, and clinically indefensible. Instead the system splits along the two questions, and each half uses the right tool:

- The **safety layer is a deterministic, fully-traceable rules engine.** Every gate points to a clinical source. A provider (and a regulator) can see exactly why a patient was flagged red. This is where certainty is required, so there is no ML in the hard gates.
- The **response layer is a calibrated probabilistic model.** Predicting who responds is genuinely statistical, the evidence supports it, and the output is explicitly framed as guidance, not a guarantee.

This division is the single most important design decision in the document.

---

## 2. What the research says is actually possible (feasibility)

The response-prediction premise is real and recent, not speculative.

A genome-wide association study of 27,885 GLP-1 users published in *Nature* (April 2026) identified a missense variant in **GLP1R** associated with greater weight loss (about an extra −0.76 kg per effect allele) and linked variation in **GLP1R** and **GIPR** to nausea/vomiting — people homozygous for risk alleles at both genes had roughly **15× the odds of vomiting on tirzepatide**. A combined genetic-plus-clinical model explained about **25% of the variance** in weight loss. That number is the honest ceiling: genetics adds a meaningful but modest slice on top of demographics and BMI, which is why the product must sell this as probability, not prophecy.

Separately, **Phenomix Sciences' MyPhenome** test (validated with Mayo Clinic, published in *Cell Metabolism*) uses a Calories-to-Satiation Genetic Risk Score reported to predict obesity-medication response with AUC up to **0.76 in men and 0.84 in women**. Blood-based epigenetic assays make comparable claims. So a Tier-2 response predictor in the 75–84% range is consistent with the published state of the art — as long as it is positioned honestly.

The safety side is even more grounded, because it rests on established drug labeling and clinical monitoring practice rather than novel prediction (see §4).

**Regulatory tailwind.** The path is friendlier than it was a year ago. In *ACLA v. FDA* (2025) a court vacated the FDA rule that would have regulated lab-developed tests as medical devices, reaffirming **CLIA** as the authority; the *Enhancing CLIA Act of 2026* would codify that. And revised FDA clinical-decision-support guidance (January 2026) keeps CDS software outside device regulation when it surfaces a single clinically appropriate recommendation **for a provider to review** rather than driving the decision itself. Both point to the same design: run the assays in a CLIA lab, keep a provider in the loop, present recommendations rather than automated verdicts.

---

## 3. System architecture

```
  Tasso device (patient, at home)
        |  whole-blood / dried-blood sample
        v
  CLIA lab partner  ── runs assays ──►  structured results (HL7/FHIR)
        |
        v
  ┌───────────────────────────── MODEL CORE ─────────────────────────────┐
  │                                                                       │
  │  INPUT NORMALIZER    unit harmonization, ref-range mapping,           │
  │                      sex/age adjustment, missing-value handling       │
  │        |                                                              │
  │        v                                                              │
  │  TIER 1  SAFETY RULES ENGINE   (deterministic, per-peptide gates)     │
  │        |         └─► red / yellow / green + personalized thresholds   │
  │        v                                                              │
  │  TIER 2  RESPONSE PREDICTOR    (calibrated ML; runs only if not RED)  │
  │        |         └─► response likelihood % + side-effect risk band    │
  │        v                                                              │
  │  REPORT ASSEMBLER   provider-facing summary + monitoring plan         │
  │                                                                       │
  └───────────────────────────────────────────────────────────────────────┘
        |
        v
  EMR (provider review)  ──►  patient
        ^
        |  Tier 3: re-draw at 8–12 wks feeds back as new baseline delta
        └──────────────────────────────────────────────────────────────
```

The prototype implements the Input Normalizer, the full Tier-1 engine for four peptide classes, a transparent Tier-2 scorer for GLP-1, the Tier-3 monitoring plans, and the Report Assembler.

---

## 4. Tier 1 — Readiness & Safety (the deterministic core)

Each peptide is defined as an ordered list of small, pure, independently testable **gate functions**. A gate returns a finding tagged `green` / `yellow` / `red` with a message, the triggering value, the threshold, and a **clinical source**. The peptide's overall flag is the worst individual flag. Missing but required labs return `yellow` ("required before initiating"), so gaps never silently pass as safe.

**GLP-1 / GIP class** (semaglutide, tirzepatide). Red on history of medullary thyroid carcinoma / MEN-2 (class boxed warning) or prior pancreatitis; red on lipase ≥3× ULN (the escalation threshold used in GLP-1 trials), yellow on mild elevation; renal gate on eGFR because GI-driven dehydration raises acute-kidney-injury risk.

**GHK-Cu** (copper peptide). Red on known Wilson's disease (copper therapy contraindicated) or low ceruloplasmin (<20 mg/dL — the Wilson's screening trigger, and ceruloplasmin reflects functional copper better than total copper alone); yellow on elevated serum copper.

**Sermorelin / GH secretagogues.** Red on active/suspected malignancy (GH/IGF-1 are proliferative) or baseline IGF-1 already above +2 SD (don't stimulate a maxed axis); glycemic gate because GH reduces insulin sensitivity, so pre-diabetic/diabetic HbA1c triggers closer monitoring.

**BPC-157** (research peptide). Always emits a yellow evidence-quality notice — minimal human safety data, not FDA-approved, no validated response biomarker — plus a malignancy precaution and a baseline organ-safety (ALT) gate. This peptide is where the model's honesty about evidence quality matters most.

Every threshold in the prototype is a literature-aligned **default for demonstration**, tagged with its source in code, and must be signed off by the medical director against the partner lab's own reference ranges before any clinical use.

---

## 5. Tier 2 — Response Predictor (the probabilistic layer)

**Inputs:** genetic dosage (GLP1R effect allele, GIPR risk allele), baseline biomarkers, BMI, sex, age, drug type. **Outputs:** a response-likelihood percentage and a GI side-effect risk band (low/moderate/high).

The prototype ships a *transparent linear/logistic scorer* so the mechanics are inspectable — GLP1R dosage and BMI raise predicted response, dual GLP1R+GIPR risk alleles raise the nausea band toward the ~15× tirzepatide signal from the GWAS. In production this stub is replaced by a model **fitted on your own longitudinal outcomes** (Tier-3 re-draws are the training label source) and, crucially, **calibrated** — a predicted 70% should mean 70% observed. Report probabilities, and validate them with reliability curves, not just AUC.

Two guardrails are built into the output: the predictor **never runs on a RED patient** (a good predicted response cannot override a safety contraindication), and every response object carries the explicit disclaimer that models of this type explain only ~25% of weight-loss variance and are guidance for provider discussion, not a guarantee.

---

## 6. Tier 3 — Longitudinal Monitoring

Each peptide carries a monitoring plan (analyte, cadence, threshold, rationale) defining the 8–12 week re-draw. The re-draw does two jobs: it is the recurring-revenue line that fits the subscription model and keeps patients engaged, and it is the **outcome-label feedback loop** that lets the Tier-2 model improve over time on the network's real population instead of borrowed study cohorts. This is the compounding data advantage — every re-draw makes the response predictor slightly better for the next patient.

---

## 7. Validation plan

The two layers are validated differently, because they make different kinds of claims.

The **safety engine** is validated by clinical correctness, not statistics: a rule-coverage matrix mapping every gate to its source, unit tests per gate (the prototype's demo already exercises green/yellow/red per peptide), adversarial "missing-lab" and unit-mismatch tests, and medical-director sign-off on every threshold. The question is "does it faithfully encode the guideline," not "what's its AUC."

The **response predictor** is validated statistically: hold-out and prospective AUC (target range 0.75–0.84, consistent with MyPhenome), **calibration** curves, and subgroup performance by sex and ancestry — the GWAS evidence skews toward European-ancestry cohorts, so ancestry-stratified performance must be reported honestly and the model must not silently underperform for underrepresented groups.

---

## 8. Regulatory & compliance posture

Run assays through the **CLIA lab partner** (reaffirmed post-*ACLA v. FDA* as the operative authority). Keep the product inside the **non-device CDS** lane per the January 2026 FDA guidance by surfacing recommendations **for provider review** — the provider decides, the software informs; route all output into the EMR rather than direct-to-patient verdicts. Frame Tier 2 as probabilistic guidance in both UI and consent. Standard HIPAA handling for PHI, and genetic data carries extra consent obligations (GINA and state genetic-privacy law). None of this is legal advice — bring in regulatory counsel before launch; treat this section as the engineering-side posture, not a compliance opinion.

---

## 9. Build sequence

Ship **Tier 1 first** — it is deterministic, defensible, and immediately useful, and it already differentiates the program on safety and liability reduction. Layer in **Tier 2** for GLP-1 (best evidence) once genetic assays are wired through the lab, extending to other peptides only as evidence supports. **Tier 3** re-draws then close the loop and begin training the network-specific response model. The prototype in this repo demonstrates Tiers 1–3 end-to-end for GLP-1, GHK-Cu, sermorelin, and BPC-157.

---

## 10. Honest limitations

Response prediction has a real ceiling (~25% of variance for weight loss); this is decision *support*, not a crystal ball. Peptide evidence quality is wildly uneven — GLP-1 is well-studied, BPC-157 barely studied in humans, and the model encodes that gap rather than papering over it. Genetic-prediction evidence is ancestry-skewed and must be monitored for equity. And the prototype's thresholds are reasonable defaults for demonstration, not a validated protocol — clinical sign-off is a hard prerequisite, not a formality.

---

## Sources

- [Genetic predictors of GLP1 receptor agonist weight loss and side effects — *Nature* (2026)](https://www.nature.com/articles/s41586-026-10330-z)
- [New Study Reveals Genetic Predictors for GLP-1 Weight Loss and Side Effects — PharmExec](https://www.pharmexec.com/view/new-study-reveals-genetic-predictors-glp-weight-loss-side-effects)
- [Phenomix / Mayo Clinic MyPhenome validation — Clinical Research News](https://www.clinicalresearchnewsonline.com/news/2025/06/11/phenomix-and-mayo-clinic-publish-research-demonstrating-utility-of-myphenome-test-for-personalized-glp-1-and-phen-top-treatment)
- [Mayo Clinic study using Phenomix AI to predict GLP-1 side effects — PR Newswire](https://www.prnewswire.com/news-releases/mayo-clinic-study-uses-phenomix-ai-algorithm-to-predict-glp-1-side-effects-advancing-personalized-obesity-care-and-drug-development-302448298.html)
- [GLP-1 Blood Work / Monitoring Guide 2026 — Telehealth Ally](https://telehealthally.com/guides/glp1-labs-monitoring-guide)
- [GLP-1 Contraindications Reference (MTC/MEN2, pancreatitis) — Trimi](https://trytrimi.com/blog/glp1-contraindications-reference-provider)
- [GHK-Cu Contraindications & Safety (Wilson's, zinc) — Newtropin](https://newtropin.com/blog/ghk-cu-contraindications-zinc-wilsons-disease-safety)
- [Wilson Disease Workup (ceruloplasmin, copper) — Medscape](https://emedicine.medscape.com/article/183456-workup)
- [Sermorelin & IGF-1 monitoring](https://sermorelin.com/article/sermorelin-and-igf-1)
- [Sermorelin safety / contraindications — Testing.com](https://www.testing.com/treatments/sermorelin/)
- [FDA Updates Guidance on Clinical Decision Support (Jan 2026) — ACR](https://www.acr.org/News-and-Publications/2026/fda-updates-guidance-on-clinical-decision-support)
- [Oversight of LDTs after ACLA v. FDA — Arnold & Porter](https://www.arnoldporter.com/en/perspectives/advisories/2026/07/oversight-of-laboratory-developed-tests-one-year-after-acla-v-fda)
- [Enhancing CLIA Act of 2026 — Covington & Burling](https://www.cov.com/en/news-and-insights/insights/2026/06/enhancing-clinical-laboratory-innovation-and-access-act-enhancing-clia-act-of-2026)

*Not medical, legal, or regulatory advice. Thresholds are demonstration defaults requiring medical-director validation before clinical use.*
