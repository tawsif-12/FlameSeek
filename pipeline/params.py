"""Versioned parameter files: params/<kind>_v<N>.json.

Kinds: calibration, detection_curve, pi_modis, diurnal. Processing stages only READ these
(`load`); `python refit_params.py --window <name>` writes the next version. Each file records
the source window, era, sample size, fit method, values with intervals, and a status:
  provisional            fitted, not yet validated
  validated-sync-window  fitted on a window where Aqua and S-NPP observe nearly together
  drift-affected         fitted in a drifted era; superseded by a sync-window fit
  not_available          could not be fitted (reason given)
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

from pipeline.config import ROOT

KINDS = ("calibration", "detection_curve", "pi_modis", "diurnal")
STATUSES = ("provisional", "validated-sync-window", "drift-affected", "not_available")


def pdir(cfg: dict | None = None) -> Path:
    d = ROOT / ((cfg or {}).get("params", {}).get("dir", "params"))
    d.mkdir(parents=True, exist_ok=True)
    return d


def versions(kind: str, cfg=None) -> list[int]:
    return sorted(int(m.group(1)) for f in pdir(cfg).glob(f"{kind}_v*.json")
                  if (m := re.fullmatch(rf"{kind}_v(\d+)\.json", f.name)))


def path(kind: str, version: int, cfg=None) -> Path:
    return pdir(cfg) / f"{kind}_v{version}.json"


def load(kind: str, version: int | None = None, statuses=None, cfg=None) -> dict | None:
    """A specific version, or the newest one whose status is in `statuses` (any by default)."""
    vs = [version] if version else list(reversed(versions(kind, cfg)))
    for v in vs:
        p = path(kind, v, cfg)
        if p.exists():
            d = json.loads(p.read_text())
            if statuses is None or d["status"] in statuses:
                return d
    return None


def write(kind: str, payload: dict, cfg=None) -> Path:
    assert kind in KINDS and payload["status"] in STATUSES
    v = (versions(kind, cfg) or [0])[-1] + 1
    doc = {"kind": kind, "version": v, "created_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
           **payload}
    p = path(kind, v, cfg)
    p.write_text(json.dumps(doc, indent=2, default=_jsonable))
    return p


def set_status(kind: str, version: int, status: str, reason: str, cfg=None) -> None:
    """Change a file's status, keeping the history (used to mark drift-affected fits)."""
    p = path(kind, version, cfg)
    d = json.loads(p.read_text())
    d.setdefault("status_history", []).append({"from": d["status"], "to": status, "reason": reason,
                                               "utc": datetime.now(timezone.utc).isoformat(timespec="seconds")})
    d["status"] = status
    p.write_text(json.dumps(d, indent=2, default=_jsonable))


def _jsonable(o):
    import numpy as np
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating,)):
        return None if not np.isfinite(o) else float(o)
    if isinstance(o, np.ndarray):
        return o.tolist()
    return str(o)
