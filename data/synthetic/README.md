# RetailEase synthetic telemetry (generated)

These four files are the telemetry the Phase 3 tools query. They are **generated, not
hand-written** — `generate.py` projects the answer key (`../answer_key/`) through the empirical
RCAEval profile (`../profiles/`). Do not edit them by hand; re-run the generator.

```
answer_key (signal)  ─┐
                      ├─► generate.py ─► logs.jsonl · metrics.json · deployments.json · dependencies.json
rcaeval_profile (noise ratios) ─┘
```

| File | Consumed by (Phase 3) | Contents |
| --- | --- | --- |
| `logs.jsonl` | `query_logs` | authored incident events + calibrated noise floor + ambient sub-threshold events |
| `metrics.json` | `get_metrics` | per-entity 5-min series; only referenced `(service, metric)` deviate |
| `deployments.json` | `get_deployments` | causal deploys + the inc-004 red herring + routine noise |
| `dependencies.json` | `get_service_dependencies` | the topology edge list (with `critical` flags) |
| `alerts.json` | `POST /investigate` input | per-incident alert **storm** across the blast-radius services + noise alerts |
| `incidents.json` | incident catalog / fast path | one record per scenario (priority/SLA/timeline), historical ones closed with resolution |

The alert/incident layer (`generate_alerts_incidents.py`) realizes the **services → alerts →
incidents → scenarios** hierarchy: each incident aggregates a storm (one `root_cause` alert + N
`symptom` alerts + one `is_trigger` alert — the customer-facing one that opens the investigation).
Fan-in and lifecycle are calibrated from `../profiles/itsm_profile.json` (real ITSM distributions)
plus the same blast radius the telemetry uses; noise alerts roll up to no incident.

## The three design invariants (enforced by `tests/test_telemetry.py`)

1. **Signal is authored, noise is calibrated.** Every `expected_evidence` ref in the answer key
   resolves to a real row here; the noise floor's density (metric sparsity, blast radius, ambient
   log-error fraction) comes from the RCAEval profile, not from guesses.
2. **Severity is checked, not invented.** Each authored severity is validated against a
   blast-radius × path-criticality estimate; a >1-level mismatch fails the build.
3. **Deterministic.** Seeded by content hash (no wall-clock, no RNG) → regenerable, reproducible.

## Regenerate

```
python data/profiles/build_profile.py            # only if the RCAEval cache changed
python data/profiles/build_incident_profile.py   # only if the ITSM cache changed
python data/synthetic/generate.py                # logs/metrics/deployments/dependencies
python data/synthetic/generate_alerts_incidents.py   # alerts + incidents
```

`NOISE_LOG_SCALE` in `generate.py` trades corpus size against noise-floor realism (RCAEval's real
rate is ~335 log lines/min/service; we scale down but preserve the ambient error ratio).

Provenance and the full cross-corpus closure check land at Phase 2e.
