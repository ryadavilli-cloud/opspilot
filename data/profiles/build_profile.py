"""Derive the empirical signal profile that calibrates OpsPilot's synthetic telemetry.

We do NOT copy RCAEval's data into RetailEase. We measure a handful of *dimensionless*
ratios from it — how sparse a fault's signal is, how far it spreads, how fast it onsets —
and hand those to the 2b generator so RetailEase telemetry has realistic proportions instead
of hand-guessed ones. Only normalized ratios transfer (RetailEase has 5 services; Train Ticket
has 64), so absolute structure is deliberately discarded.

Leakage split: we calibrate on Sock Shop + Train Ticket and HOLD OUT Online Boutique, which is
reserved for the held-out "wild" diagnosis eval. The calibration source and the generalization
test never touch.

Input  : RCAEval RE1 (metrics) + RE2 (logs) unzipped under data/.rcaeval_cache/ (gitignored).
Output : data/profiles/rcaeval_profile.json (committed; small).

Run:  python data/profiles/build_profile.py
"""

from __future__ import annotations

import json
import re
import statistics
from pathlib import Path
from typing import Any

import pandas as pd

PROFILES_DIR = Path(__file__).resolve().parent
REPO_ROOT = PROFILES_DIR.parents[1]
CACHE = REPO_ROOT / "data" / ".rcaeval_cache"
OUT_PATH = PROFILES_DIR / "rcaeval_profile.json"

# Leakage split — calibrate on these, hold out Online Boutique (RE*-OB) for the wild eval.
CALIBRATION_SYSTEMS = {"RE1-SS": "sockshop", "RE1-TT": "trainticket"}
RE2_LOG_SYSTEMS = {"RE2-SS": "sockshop"}  # logs only live in RE2; SS is the light one (245 MB)

# RCAEval RE1 fault types. We bucket them by the *symptom shape* they produce, which is what
# actually transfers to RetailEase categories (see CATEGORY_FAULT_BASIS below).
FAULT_TYPES = {"cpu", "mem", "disk", "delay", "loss"}

# How each RetailEase incident category maps onto the RCAEval fault type whose signal shape it
# resembles. This is the per-category calibration the generator consumes.
CATEGORY_FAULT_BASIS = {
    "payment": "delay",     # latency/timeout-shaped (inc-001, inc-004)
    "datastore": "mem",     # resource saturation → throttling (inc-002)
    "cache": "mem",         # memory pressure / eviction (inc-005)
    "messaging": "loss",    # dropped/blocked processing (inc-003)
    "inventory": "cpu",     # compute/deploy regression (inc-006)
}

NODE_PREFIX = re.compile(r"^\d")  # node-exporter columns are IP-prefixed; not app services.
MIN_WINDOW = 30  # require >=30 samples each side of injection to trust a case.
Z_THRESH = 4.0   # statistical deviation gate (post mean vs pre distribution).
REL_THRESH = 0.2  # AND a >=20% relative change, so tiny-but-significant noise isn't "affected".


def _service_of(metric_col: str) -> str | None:
    """Owning service = token before the first underscore; drop node-exporter columns."""
    head = metric_col.split("_", 1)[0]
    if not head or NODE_PREFIX.match(head):
        return None
    return head


def _as_rate(series: pd.Series) -> pd.Series:
    """Counters are cumulative — compare their rate, not their level. Gauges pass through."""
    s = series.astype(float)
    if s.is_monotonic_increasing and (s.iloc[-1] - s.iloc[0]) > 0:
        return s.diff()
    return s


def _analyze_case(case_dir: Path, root_service: str) -> dict[str, Any] | None:
    inject = int((case_dir / "inject_time.txt").read_text().strip())
    df = pd.read_csv(case_dir / "data.csv")
    if "time" not in df.columns:
        return None
    t = df["time"].astype(float)
    pre_mask, post_mask = t < inject, t >= inject
    if pre_mask.sum() < MIN_WINDOW or post_mask.sum() < MIN_WINDOW:
        return None

    metric_cols = [c for c in df.columns if c != "time"]
    services = {s for c in metric_cols if (s := _service_of(c))}
    affected_metrics: list[str] = []
    affected_services: set[str] = set()
    root_onset_lags: list[float] = []

    for col in metric_cols:
        rate = _as_rate(df[col])
        pre, post = rate[pre_mask].dropna(), rate[post_mask].dropna()
        if len(pre) < MIN_WINDOW or len(post) < 2:
            continue
        pre_mean = pre.mean()
        pre_std = pre.std()
        denom = pre_std if pre_std > 1e-9 else abs(pre_mean) * 0.01 + 1e-9
        z = abs(post.mean() - pre_mean) / denom
        rel = abs(post.mean() - pre_mean) / (abs(pre_mean) + 1e-9)
        if z > Z_THRESH and rel > REL_THRESH:
            affected_metrics.append(col)
            svc = _service_of(col)
            if svc:
                affected_services.add(svc)
            if svc == root_service:
                # First post-injection sample that breaches the pre-window band → onset.
                band = abs(pre_mean) + Z_THRESH * (pre_std + 1e-9)
                breach = post[post.abs() > band]
                if not breach.empty:
                    root_onset_lags.append(float(t[breach.index[0]] - inject))

    if not metric_cols or not services:
        return None
    return {
        "affected_metric_fraction": len(affected_metrics) / len(metric_cols),
        "blast_radius_fraction": len(affected_services) / len(services),
        "root_is_anomalous": root_service in affected_services,
        "onset_lag_seconds": min(root_onset_lags) if root_onset_lags else None,
    }


def _iter_cases(system_root: Path):
    """Yield (case_dir, root_service, fault_type) for every RE1 case under a system dir."""
    inner = next((p for p in system_root.iterdir() if p.is_dir()), system_root)
    for combo in sorted(inner.iterdir()):
        if not combo.is_dir() or "_" not in combo.name:
            continue
        root_service, fault = combo.name.rsplit("_", 1)
        if fault not in FAULT_TYPES:
            continue
        for instance in sorted(combo.iterdir()):
            if (instance / "data.csv").exists() and (instance / "inject_time.txt").exists():
                yield instance, root_service, fault


def _summarize(values: list[float]) -> dict[str, float] | None:
    vals = [v for v in values if v is not None]
    if not vals:
        return None
    return {
        "median": round(statistics.median(vals), 4),
        "p25": round(statistics.quantiles(vals, n=4)[0], 4) if len(vals) > 1 else round(vals[0], 4),
        "p75": round(statistics.quantiles(vals, n=4)[2], 4) if len(vals) > 1 else round(vals[0], 4),
        "n": len(vals),
    }


def profile_metrics() -> dict[str, Any]:
    by_fault: dict[str, dict[str, list[float]]] = {
        f: {"affected_metric_fraction": [], "blast_radius_fraction": [], "onset_lag_seconds": []}
        for f in FAULT_TYPES
    }
    root_hits = 0
    total = 0
    for sysdir, _ in CALIBRATION_SYSTEMS.items():
        root = CACHE / sysdir
        if not root.exists():
            print(f"  ! missing {sysdir} — skipping (run the download first)")
            continue
        for case_dir, root_service, fault in _iter_cases(root):
            res = _analyze_case(case_dir, root_service)
            if res is None:
                continue
            total += 1
            root_hits += int(res["root_is_anomalous"])
            for k in ("affected_metric_fraction", "blast_radius_fraction", "onset_lag_seconds"):
                by_fault[fault][k].append(res[k])
        print(f"  · {sysdir}: cumulative {total} usable cases")

    out = {"by_fault_type": {}, "root_cause_recall": round(root_hits / total, 4) if total else None}
    for fault, metrics in by_fault.items():
        summ = {k: _summarize(v) for k, v in metrics.items()}
        if any(summ.values()):
            out["by_fault_type"][fault] = summ
    return out


def resolve_categories(
    metric_profile: dict[str, Any], log_profile: dict[str, Any]
) -> dict[str, Any]:
    """Project the per-fault-type stats onto RetailEase categories the generator consumes."""
    resolved: dict[str, Any] = {}
    for category, fault in CATEGORY_FAULT_BASIS.items():
        mf = metric_profile.get("by_fault_type", {}).get(fault, {})
        lf = log_profile.get("by_fault_type", {}).get(fault, {})
        resolved[category] = {
            "basis_fault_type": fault,
            "affected_metric_fraction": (mf.get("affected_metric_fraction") or {}).get("median"),
            "blast_radius_fraction": (mf.get("blast_radius_fraction") or {}).get("median"),
            "onset_lag_seconds": (mf.get("onset_lag_seconds") or {}).get("median"),
            "ambient_error_fraction": (lf.get("ambient_error_fraction") or {}).get("median"),
            "log_lines_per_min_per_service": (
                lf.get("log_lines_per_min_per_service") or {}).get("median"),
        }
    return resolved


def main() -> None:
    print("profiling metrics (RE1, calibration split)…")
    metric_profile = profile_metrics()

    # Log profiling (RE2) is added once RE2-SS is present and its logs.csv schema is known.
    log_profile: dict[str, Any] = {"by_fault_type": {}, "note": "pending RE2 log schema"}
    try:
        from build_profile_logs import profile_logs  # type: ignore

        log_profile = profile_logs(CACHE, RE2_LOG_SYSTEMS, FAULT_TYPES)
    except Exception as exc:  # noqa: BLE001 — log profiling is additive; don't block metrics.
        print(f"  (log profiling skipped: {exc})")

    profile = {
        "source": "RCAEval RE1+RE2 (Zenodo 14590730, CC-BY-4.0). Calibration only, not redistributed.",  # noqa: E501
        "calibration_systems": list(CALIBRATION_SYSTEMS.values()),
        "held_out_for_wild_eval": ["onlineboutique"],
        "method": {
            "sample_rate_seconds": 1,
            "deviation_gate": {"z_thresh": Z_THRESH, "rel_thresh": REL_THRESH},
            "note": "Dimensionless ratios only; absolute structure intentionally discarded.",
        },
        "category_fault_basis": CATEGORY_FAULT_BASIS,
        "metric_signal": metric_profile,
        "log_signal": log_profile,
        "per_category": resolve_categories(metric_profile, log_profile),
    }
    OUT_PATH.write_text(json.dumps(profile, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {OUT_PATH.relative_to(REPO_ROOT)}")


if __name__ == "__main__":
    main()
