"""2c gate: the services -> alerts -> incidents -> scenarios mapping must hold and be consistent.

Guards that every scenario has an incident, every incident aggregates a well-formed alert storm
across its blast-radius services, historical incidents are closed with a resolution (so Demo 2 /
the fast path have something to match), and noise alerts roll up to no incident.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SYN = REPO_ROOT / "data" / "synthetic"
ANSWER_KEY = REPO_ROOT / "data" / "answer_key"


def _load(name: str, rel: str):
    spec = importlib.util.spec_from_file_location(name, REPO_ROOT / rel)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


build_goldens = _load("build_goldens", "data/answer_key/build_goldens.py")
gai = _load("generate_alerts_incidents", "data/synthetic/generate_alerts_incidents.py")

TOPOLOGY = build_goldens.load_topology()
SCENARIOS = build_goldens.load_scenarios()
SERVICES = {s["id"] for s in TOPOLOGY["services"]}
SCEN_BY_ID = {s["id"]: s for s in SCENARIOS}

INCIDENTS = json.loads((SYN / "incidents.json").read_text(encoding="utf-8"))["incidents"]
ALERTS = json.loads((SYN / "alerts.json").read_text(encoding="utf-8"))["alerts"]
INC_BY_SCEN = {i["incident_id"]: i for i in INCIDENTS}
ALERT_SEVS = {"critical", "high", "medium", "low"}
SEV_PRIORITY = gai.SEV_PRIORITY


def test_one_incident_per_scenario_with_unique_numbers():
    assert {i["incident_id"] for i in INCIDENTS} == set(SCEN_BY_ID)
    assert len({i["number"] for i in INCIDENTS}) == len(INCIDENTS)


def test_incident_priority_tracks_severity():
    for inc in INCIDENTS:
        sev = SCEN_BY_ID[inc["incident_id"]]["severity"]
        assert inc["priority"] == SEV_PRIORITY[sev], inc["incident_id"]


def test_historical_closed_with_resolution_novel_open():
    for inc in INCIDENTS:
        scen = SCEN_BY_ID[inc["incident_id"]]
        if scen["type"] == "historical":
            assert inc["state"] == "Closed" and inc["is_known_error"]
            assert inc.get("resolved_at") and inc.get("resolution") and inc.get("close_code")
        else:
            assert inc["state"] == "In Progress" and not inc["is_known_error"]
            assert "resolved_at" not in inc and "resolution" not in inc


def test_every_incident_has_a_wellformed_storm():
    for scen_id, scen in SCEN_BY_ID.items():
        storm = [a for a in ALERTS if a["incident_id"] == scen_id]
        assert storm, f"{scen_id} has no alerts"
        roles = [a["role"] for a in storm]
        assert roles.count("root_cause") == 1, f"{scen_id} needs exactly one root_cause"
        assert sum(a["is_trigger"] for a in storm) == 1, f"{scen_id} needs one trigger alert"
        assert all(a["service"] in SERVICES for a in storm)
        assert all(a["severity"] in ALERT_SEVS for a in storm)
        # root_cause alert on the upstream-most chain service; trigger on the customer-facing one
        _, root_cause, trigger = gai.storm_participants(scen, SERVICES)
        assert next(a for a in storm if a["role"] == "root_cause")["service"] == root_cause
        assert next(a for a in storm if a["is_trigger"])["service"] == trigger


def test_storm_covers_blast_radius_including_evidence_only_services():
    """inc-002's catalog-api appears only in log evidence, not the chain — it must still alert."""
    inc2 = [a["service"] for a in ALERTS if a["incident_id"] == "inc-002"]
    assert "catalog-api" in inc2


def test_root_cause_fires_before_trigger():
    for scen_id in SCEN_BY_ID:
        storm = [a for a in ALERTS if a["incident_id"] == scen_id]
        root = next(a for a in storm if a["role"] == "root_cause")
        trig = next(a for a in storm if a["is_trigger"])
        assert root["fired_at"] <= trig["fired_at"], f"{scen_id}: root fired after trigger"


def test_noise_alerts_map_to_no_incident():
    noise = [a for a in ALERTS if a["role"] == "noise"]
    assert noise, "expected some noise alerts"
    assert all(a["incident_id"] is None for a in noise)


def test_generation_is_deterministic():
    assert gai.build_incidents(SCENARIOS) == gai.build_incidents(SCENARIOS)
    assert gai.build_alerts(SCENARIOS, SERVICES) == gai.build_alerts(SCENARIOS, SERVICES)
