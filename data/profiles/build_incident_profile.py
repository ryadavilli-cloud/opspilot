"""Derive the incident-layer distribution from the UCI incident-management event log.

Same "calibrate, don't copy" discipline as the RCAEval profiler: we take *distributions*
from a real ITSM system — how priority/impact/urgency are spread, the SLA-met rate, how much
incidents get reassigned, how long they stay open — and hand them to the 2c generator so
RetailEase's incident catalog has an honest shape instead of a hand-guessed one. The anonymized
content (categories, callers) is discarded; only the distributions transfer.

Input : data/.itsm_cache/incident_event_log.csv (UCI dataset 498, CC-BY-4.0; gitignored).
Output: data/profiles/itsm_profile.json (committed; small).

Run:  python data/profiles/build_incident_profile.py
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

PROFILES_DIR = Path(__file__).resolve().parent
REPO_ROOT = PROFILES_DIR.parents[1]
CSV = REPO_ROOT / "data" / ".itsm_cache" / "incident_event_log.csv"
OUT = PROFILES_DIR / "itsm_profile.json"


def _dist(series: pd.Series) -> dict[str, float]:
    return {k: round(v, 4) for k, v in series.value_counts(normalize=True).items() if k}


def main() -> None:
    df = pd.read_csv(CSV, dtype=str, keep_default_na=False)
    # Event log → one row per incident: the last event carries the final state/resolution.
    last = df.sort_values("sys_mod_count", key=lambda s: s.astype(int)).groupby("number").last()

    opened = pd.to_datetime(last["opened_at"], errors="coerce", dayfirst=True)
    resolved = pd.to_datetime(last["resolved_at"], errors="coerce", dayfirst=True)
    res_hours = ((resolved - opened).dt.total_seconds() / 3600).dropna()
    res_hours = res_hours[(res_hours > 0) & (res_hours < 24 * 30)]  # drop clock-skew outliers

    reassign = last["reassignment_count"].astype(int)
    profile = {
        "source": "UCI Incident Management Process Enriched Event Log (dataset 498, CC-BY-4.0). "
                  "Anonymized real ServiceNow data; distributions only, not redistributed.",
        "n_incidents": int(last.shape[0]),
        "priority_distribution": _dist(last["priority"]),
        "impact_distribution": _dist(last["impact"]),
        "urgency_distribution": _dist(last["urgency"]),
        "made_sla_rate": round((last["made_sla"] == "true").mean(), 4),
        "reassignment_count": {
            "mean": round(reassign.mean(), 3),
            "median": int(reassign.median()),
            "p75": int(reassign.quantile(0.75)),
            "max": int(reassign.max()),
        },
        "resolution_hours": {
            "median": round(res_hours.median(), 2),
            "p25": round(res_hours.quantile(0.25), 2),
            "p75": round(res_hours.quantile(0.75), 2),
        },
    }
    OUT.write_text(json.dumps(profile, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {OUT.relative_to(REPO_ROOT)} from {profile['n_incidents']} incidents")


if __name__ == "__main__":
    main()
