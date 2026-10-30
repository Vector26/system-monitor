"""Fortress whole-stack service status for PlainTop."""
from __future__ import annotations

import json
import subprocess
import time
from dataclasses import dataclass
import os
from pathlib import Path

_FORTRESS_HOME = Path(
    os.environ.get("FORTRESS_HOME", os.path.expanduser("~/fortress"))
).expanduser()
STATUS_PY = _FORTRESS_HOME / "control" / "status.py"
CONTROL_VENV = _FORTRESS_HOME / "control" / ".venv" / "bin" / "python"

_cache: tuple[float, "FortressServicesSnapshot | None"] = (0.0, None)
CACHE_SEC = 4.0


@dataclass
class FortressServiceRow:
    id: str
    name: str
    running: bool
    gpu: bool


@dataclass
class FortressServicesSnapshot:
    on: int
    total: int
    ai_label: str
    rows: list[FortressServiceRow]
    ghosts: list[dict] | None = None


def collect_fortress_services(force: bool = False) -> FortressServicesSnapshot | None:
    global _cache
    now = time.time()
    if not force and _cache[1] is not None and (now - _cache[0]) < CACHE_SEC:
        return _cache[1]
    py = str(CONTROL_VENV if CONTROL_VENV.exists() else Path("/usr/bin/python3"))
    if not STATUS_PY.exists():
        return None
    try:
        out = subprocess.check_output(
            [py, str(STATUS_PY), "status"],
            text=True,
            timeout=6,
            stderr=subprocess.DEVNULL,
        )
        data = json.loads(out)
        rows = [
            FortressServiceRow(
                id=s["id"],
                name=s["name"],
                running=bool(s["running"]),
                gpu=bool(s.get("gpu")),
            )
            for s in data.get("services") or []
        ]
        snap = FortressServicesSnapshot(
            on=int(data.get("on") or 0),
            total=int(data.get("total") or 0),
            ai_label=(data.get("ai") or {}).get("label") or "?",
            rows=rows,
            ghosts=data.get("ghosts") or [],
        )
        _cache = (now, snap)
        return snap
    except Exception:
        return _cache[1]
