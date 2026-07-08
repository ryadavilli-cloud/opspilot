# Data provenance

RetailEase is a **fully synthetic** system. All telemetry, alerts, incidents, and knowledge-base
content under `data/` is authored for this project. **No employer, customer, or production data is
included**, and no real logs, tickets, or postmortems are copied in.

Real public datasets are used **only to calibrate distributions and to inform document structure —
never as content**. We measure ratios and shapes from them and generate our own coherent corpus
("calibrate, don't copy"). Raw datasets are gitignored; only the derived profiles
(`data/profiles/*.json`) and this citation are committed.

## Calibration & reference sources

| Source | License | Used for | Committed to repo |
| --- | --- | --- | --- |
| **RCAEval** (Zenodo 14590730) | CC-BY-4.0 (data) / MIT (code) | Telemetry signal ratios — metric sparsity, blast radius, onset lag, ambient log-error rate — via `build_profile.py`. Calibrated on Sock Shop + Train Ticket; **Online Boutique held out** for the diagnosis-generalization ("wild") eval. | derived `rcaeval_profile.json` only; raw gitignored |
| **UCI Incident Management Process Enriched Event Log** (dataset 498) | CC-BY-4.0 | Incident-layer distributions — priority/impact/urgency, SLA-met rate, reassignment, resolution time — via `build_incident_profile.py`. Anonymized real ServiceNow data. | derived `itsm_profile.json` only; raw gitignored |
| **AIOps alert-storm study** (Electronics 2024, 13(22):4425, MDPI) | published statistics only | Alert-storm shape — storm size, 2–35 min duration, severity mix. The raw dataset is not public; only summary statistics are cited in `generate_alerts_incidents.py`. | none (stats cited in code) |
| **danluu/post-mortems** + general SRE runbook practice | reference | Document *structure* for postmortems and runbooks. Content is RetailEase-authored and Azure-native. | none |

## Attribution

- RCAEval: Pham et al., *RCAEval: A Benchmark for Root Cause Analysis of Microservice Systems with Telemetry Data.* Zenodo, DOI 10.5281/zenodo.14590730 (CC-BY-4.0).
- UCI ITSM: *Incident Management Process Enriched Event Log*, UCI Machine Learning Repository, dataset 498 (CC-BY-4.0).
- Alert-storm statistics: *Leveraging Large Language Models for Efficient Alert Aggregation in AIOps*, Electronics 2024, 13(22):4425 (MDPI).

## What is synthetic (the whole corpus)

| Path | Contents | Origin |
| --- | --- | --- |
| `data/answer_key/` | topology + incident scenarios | authored (the source of truth) |
| `data/synthetic/` | logs, metrics, deployments, dependencies, alerts, incidents | generated from the answer key + calibration profiles |
| `data/kb/` | runbooks, architecture, postmortems | authored; Azure-native; structure only from real SRE practice |
| `eval/golden_*.json` | retrieval + incident golden sets | projected from the answer key |

The corpus is internally closed — every evidence reference resolves to a telemetry row, every
retrieval target to a KB doc, and every postmortem to a historical incident. This is enforced by
`tests/test_closure.py`.
