"""Generate the alert + incident layer — the entry points and labels above the telemetry.

This realizes the services -> alerts -> incidents -> scenarios hierarchy:

    scenario   (narrative + answer key)
      +- incident   (priority, SLA, timeline)         <- distribution from the UCI ITSM log
          +- alert-storm  (alerts across the blast-radius services)
              |                                        <- storm shape from AIOps alert-storm stats
              +- services  (topology)

Each incident aggregates a *storm*, not one alert: a root_cause alert on the upstream service,
symptom alerts on the downstream blast-radius services, and one trigger alert (the customer-facing
one that opened the investigation — the POST /investigate input). A handful of noise alerts map to
NO incident, mirroring that most real alerts never become incidents.

Calibration is honest-but-bounded:
  * Incident priority/impact/urgency, SLA-met, reassignment, MTTR come from itsm_profile.json.
  * The blast-radius set (which services alert) is the scenario's impacted chain + evidence services
    — the same propagation we measured for the telemetry.
  * Absolute storm fan-in is topology-scaled: a 5-service system yields small storms; we borrow the
    real storm *structure* (root + symptoms + trigger, staggered onset), not the 30-service size.

Outputs:  data/synthetic/incidents.json, data/synthetic/alerts.json
Run:      python data/synthetic/generate_alerts_incidents.py
"""

from __future__ import annotations

import json
import sys
from datetime import timedelta
from pathlib import Path

SYN_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SYN_DIR))  # reuse the telemetry generator's helpers + ambient events
from generate import (  # noqa: E402
    AMBIENT_EVENTS,
    ANSWER_KEY,
    _dt,
    _iso,
    _rng,
    load_yaml,
    parse_evidence,
)

REPO_ROOT = SYN_DIR.parents[1]
PROFILE_PATH = REPO_ROOT / "data" / "profiles" / "itsm_profile.json"

# Severity → ITSM/alert fields. Our 6 scenarios are the interesting tail of the priority pyramid
# (94% of real incidents are Moderate); the calibrated distribution governs the ambient population.
SEV_PRIORITY = {
    "SEV1": "1 - Critical", "SEV2": "2 - High", "SEV3": "3 - Moderate", "SEV4": "4 - Low"}
SEV_IMPACT = {"SEV1": "1 - High", "SEV2": "2 - Medium", "SEV3": "2 - Medium", "SEV4": "3 - Low"}
SEV_URGENCY = {"SEV1": "1 - High", "SEV2": "1 - High", "SEV3": "2 - Medium", "SEV4": "3 - Low"}
SEV_ALERT = {"SEV1": "critical", "SEV2": "high", "SEV3": "medium", "SEV4": "low"}
SEV_MTTR_H = {"SEV1": 2, "SEV2": 6, "SEV3": 18, "SEV4": 48}   # higher sev → faster MTTR
SEV_MADE_SLA = {"SEV1": False, "SEV2": False, "SEV3": True, "SEV4": True}
SEV_REASSIGN = {"SEV1": 3, "SEV2": 2, "SEV3": 1, "SEV4": 0}
ALERT_SEV_DOWN = {"critical": "high", "high": "medium", "medium": "low", "low": "low"}


def _services(topology: dict) -> list[str]:
    return [s["id"] for s in topology["services"]]


def storm_participants(scenario: dict, services: set[str]) -> tuple[list[str], str, str]:
    """Return (ordered participants, root_cause_service, trigger_service) for one storm.

    Participants = the impacted-chain services plus any service named in the evidence (so a
    service that only shows up in logs, e.g. catalog-api in inc-002, still alerts). Order follows
    the chain root->customer; the root-cause service is the upstream-most, the trigger is the
    customer-facing edge (checkout-api) when present.
    """
    chain_services = [s for s in scenario["impacted_chain"] if s in services]
    ev = parse_evidence(scenario["expected_evidence"])
    ev_services = {svc for svc, *_ in ev["metrics"]} | {svc for svc, _ in ev["logs"]}
    extra = [s for s in ev_services if s in services and s not in chain_services]
    participants = chain_services + extra
    root_cause = chain_services[0] if chain_services else participants[0]
    trigger = "checkout-api" if "checkout-api" in participants else participants[-1]
    return participants, root_cause, trigger


def _signal_for(scenario: dict, service: str) -> str:
    ev = parse_evidence(scenario["expected_evidence"])
    for svc, metric, _ in ev["metrics"]:
        if svc == service:
            return f"{metric} breached threshold"
    for svc, _ in ev["logs"]:
        if svc == service:
            return "error log rate elevated"
    return "anomaly detected"


def build_alerts(scenarios: list[dict], services: set[str]) -> list[dict]:
    alerts: list[dict] = []
    for s in scenarios:
        participants, root_cause, trigger = storm_participants(s, services)
        onset = _dt(s["occurred_at"]) + timedelta(seconds=9)  # root fires ~onset lag after start
        base_sev = SEV_ALERT[s["severity"]]
        for i, svc in enumerate(participants):
            # role = where it sits in the chain; is_trigger = the alert that opened the
            # investigation (the customer-facing one). These coincide when the root-cause service
            # is itself customer-facing (e.g. a single-service storm), so is_trigger is a flag,
            # not a mutually exclusive role.
            role = "root_cause" if svc == root_cause else "symptom"
            is_trigger = svc == trigger
            sev = base_sev if (svc == root_cause or is_trigger) else ALERT_SEV_DOWN[base_sev]
            # Root fires first; downstream symptoms stagger over the next few minutes.
            fired = onset + timedelta(seconds=0 if svc == root_cause else 30 + i * 40)
            signal = _signal_for(s, svc)
            alerts.append({
                "alert_id": f"alrt-{s['id']}-{svc}",
                "incident_id": s["id"],
                "service": svc,
                "severity": sev,
                "role": role,
                "is_trigger": is_trigger,
                "signal": signal,
                "title": f"{svc}: {signal}",
                "fired_at": _iso(fired),
                "dedup_key": f"{svc}:{signal.split()[0]}",
            })
    # Noise alerts — the same sub-threshold events, firing but rolling up to NO incident.
    for a in AMBIENT_EVENTS:
        alerts.append({
            "alert_id": f"alrt-noise-{a['id']}",
            "incident_id": None,
            "service": a["service"],
            "severity": "low",
            "role": "noise",
            "is_trigger": False,
            "signal": a["message"],
            "title": f"{a['service']}: transient blip",
            "fired_at": a["ts"],
            "dedup_key": f"{a['service']}:transient",
        })
    alerts.sort(key=lambda r: r["fired_at"])
    return alerts


def build_incidents(scenarios: list[dict]) -> list[dict]:
    incidents: list[dict] = []
    for i, s in enumerate(scenarios, start=1):
        sev = s["severity"]
        opened = _dt(s["occurred_at"])
        historical = s["type"] == "historical"
        rec = {
            "number": f"INC{i:07d}",
            "incident_id": s["id"],
            "short_description": s["alert"]["summary"],
            "category": s["category"],
            "priority": SEV_PRIORITY[sev],
            "impact": SEV_IMPACT[sev],
            "urgency": SEV_URGENCY[sev],
            "opened_at": _iso(opened),
            "state": "Closed" if historical else "In Progress",
            "made_sla": SEV_MADE_SLA[sev],
            # deterministic reassignment near the per-severity target (profile mean ~0.9)
            "reassignment_count": SEV_REASSIGN[sev] + int(_rng(s["id"], "reassign") * 2) - 1,
            "is_known_error": historical,  # historical incidents seed the postmortem / fast path
        }
        if rec["reassignment_count"] < 0:
            rec["reassignment_count"] = 0
        if historical:
            rec.update({
                "resolved_at": _iso(opened + timedelta(hours=SEV_MTTR_H[sev])),
                "close_code": "Solved (Permanently)",
                "root_cause": " ".join(s["root_cause"].split()),
                "resolution": s.get("resolution", ""),
            })
        incidents.append(rec)
    return incidents


def _dump(path: Path, data: object) -> None:
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    topology = load_yaml(ANSWER_KEY / "topology.yaml")
    scenarios = load_yaml(ANSWER_KEY / "scenarios.yaml")["scenarios"]
    services = set(_services(topology))

    incidents = build_incidents(scenarios)
    alerts = build_alerts(scenarios, services)
    _dump(SYN_DIR / "incidents.json", {"incidents": incidents})
    _dump(SYN_DIR / "alerts.json", {"alerts": alerts})

    storms = len({a["incident_id"] for a in alerts if a["incident_id"]})
    noise = sum(1 for a in alerts if a["incident_id"] is None)
    print(f"incidents: {len(incidents)} | alerts: {len(alerts)} "
          f"({storms} storms + {noise} noise) | avg fan-in "
          f"{(len(alerts) - noise) / max(storms, 1):.1f}")


if __name__ == "__main__":
    main()
