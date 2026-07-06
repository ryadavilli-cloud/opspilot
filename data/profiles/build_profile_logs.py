"""Log-side calibration from RCAEval RE2 (additive to build_profile.py).

Honest scope: RE2's logs.csv ships raw application logs with EMPTY level/error columns, so
"anomalous" must be inferred from message text. And resource faults (cpu/mem) show their signal
in metrics, not in error logs — there's no reliable per-fault error-log lift to harvest. So we
calibrate only what the data robustly supports for the NOISE FLOOR:

  * log_lines_per_min_per_service — how chatty normal services are
  * ambient_error_fraction        — baseline rate of error-ish lines in steady state

Incident error-logs themselves are authored from the answer key (our signal rows already name
the explicit error events), not drawn from this profile.
"""

from __future__ import annotations

import re
import statistics
from pathlib import Path
from typing import Any

import pandas as pd

# Tight error pattern: no capture groups (avoids pandas warning), clear failure tokens only.
ERR_RE = re.compile(
    r"(?i)(?:\b(?:error|exception|timeout|panic|fatal|refused|unavailable)\b|err=(?!null)|status=5\d\d)"
)
MAX_CASES_PER_FAULT = 6  # logs are ~86k lines/case; a sample gives stable ratios cheaply.


def _summ(values: list[float]) -> dict[str, float] | None:
    vals = [v for v in values if v is not None]
    if not vals:
        return None
    q = statistics.quantiles(vals, n=4) if len(vals) > 1 else [vals[0], vals[0], vals[0]]
    return {"median": round(statistics.median(vals), 4), "p25": round(q[0], 4),
            "p75": round(q[2], 4), "n": len(vals)}


def _analyze_log_case(case_dir: Path) -> dict[str, float] | None:
    try:
        df = pd.read_csv(case_dir / "logs.csv", dtype=str, keep_default_na=False)
    except Exception:
        return None
    if df.empty or "timestamp" not in df.columns or "message" not in df.columns:
        return None
    ts = pd.to_numeric(df["timestamp"], errors="coerce") // 1_000_000_000
    span_min = max((ts.max() - ts.min()) / 60.0, 1e-9)
    n_services = max(df["container_name"].nunique(), 1)
    err_frac = df["message"].str.contains(ERR_RE).mean()
    return {
        "log_lines_per_min_per_service": len(df) / span_min / n_services,
        "ambient_error_fraction": float(err_frac),
    }


def profile_logs(cache: Path, systems: dict[str, str], fault_types: set[str]) -> dict[str, Any]:
    by_fault: dict[str, dict[str, list[float]]] = {
        f: {"log_lines_per_min_per_service": [], "ambient_error_fraction": []} for f in fault_types
    }
    for sysdir in systems:
        root = cache / sysdir
        if not root.exists():
            continue
        inner = next((p for p in root.iterdir() if p.is_dir()), root)
        for combo in sorted(inner.iterdir()):
            if not combo.is_dir() or "_" not in combo.name:
                continue
            fault = combo.name.rsplit("_", 1)[1]
            if fault not in fault_types:
                continue
            for instance in sorted(combo.iterdir())[:MAX_CASES_PER_FAULT]:
                if not (instance / "logs.csv").exists():
                    continue
                res = _analyze_log_case(instance)
                if res:
                    for k, v in res.items():
                        by_fault[fault][k].append(v)

    out: dict[str, Any] = {"by_fault_type": {}, "note": (
        "logs.csv has empty level/error; error inferred from message text. Resource faults show "
        "metric (not log) signal, so no per-fault error lift is harvested. These ratios calibrate "
        "the synthetic NOISE FLOOR only; incident error-logs are authored from the answer key."
    )}
    for fault, fields in by_fault.items():
        summ = {k: _summ(v) for k, v in fields.items()}
        if any(summ.values()):
            out["by_fault_type"][fault] = summ
    return out
