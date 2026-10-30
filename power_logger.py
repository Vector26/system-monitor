#!/usr/bin/env python3
"""
Background power logger: polls CPU RAPL and GPU power every 5 minutes,
stores in SQLite at ~/.local/share/system-monitor/.
Run as systemd user service via setup_service.sh.
"""

import os
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

POLL_INTERVAL_SEC = 5 * 60  # 5 minutes
DATA_DIR = Path(os.environ.get("XDG_DATA_HOME", "~/.local/share")).expanduser() / "system-monitor"
DB_PATH = DATA_DIR / "power_history.db"


def ensure_data_dir() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)


def _read_ups_power_w() -> float | None:
    """Read current load (W) from CyberPower UPS via pwrstat. Returns None if unavailable.
    Tries pwrstat then sudo -n pwrstat (non-interactive) for when run as user."""
    import re
    for cmd in (["pwrstat", "-status"], ["sudo", "-n", "pwrstat", "-status"]):
        try:
            out = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=5,
            )
            if out.returncode != 0 or not out.stdout:
                continue
            for line in out.stdout.splitlines():
                m = re.search(r"Load\s*\.+\s+(\d+)\s*Watt", line, re.IGNORECASE)
                if m:
                    return float(m.group(1))
        except (FileNotFoundError, subprocess.TimeoutExpired, ValueError):
            continue
    return None


def init_db(conn: sqlite3.Connection) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS power_samples (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts INTEGER NOT NULL,
            cpu_energy_uj REAL,
            gpu_power_w REAL,
            ups_power_w REAL
        )
    """)
    # Migration: add ups_power_w if table existed without it
    try:
        conn.execute("ALTER TABLE power_samples ADD COLUMN ups_power_w REAL")
        conn.commit()
    except sqlite3.OperationalError:
        conn.rollback()
    conn.execute("CREATE INDEX IF NOT EXISTS idx_ts ON power_samples(ts)")
    conn.commit()


def read_cpu_rapl_energy_uj() -> float | None:
    """Read package-level energy from Intel RAPL (energy_uj). Returns None if not available."""
    base = Path("/sys/class/powercap")
    if not base.exists():
        return None
    for name in sorted(base.iterdir()):
        if not name.is_dir() or not name.name.startswith("intel-rapl"):
            continue
        energy_path = name / "energy_uj"
        if energy_path.exists():
            try:
                return float(energy_path.read_text().strip())
            except (OSError, ValueError):
                pass
        # Subzones (e.g. 0:0) - prefer package level; intel-rapl:0 is package
        for sub in name.iterdir():
            if sub.is_dir() and sub.name.isdigit():
                e = sub / "energy_uj"
                if e.exists():
                    try:
                        return float(e.read_text().strip())
                    except (OSError, ValueError):
                        pass
    return None


def read_gpu_power_w() -> float | None:
    """Read GPU power in watts. Prefer nvidia-smi; fallback AMD if needed."""
    # NVIDIA
    try:
        out = subprocess.run(
            ["nvidia-smi", "--query-gpu=power.draw", "--format=csv,noheader,nounits"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if out.returncode == 0 and out.stdout.strip():
            parts = out.stdout.strip().split()
            if parts:
                return float(parts[0])
    except (FileNotFoundError, subprocess.TimeoutExpired, ValueError):
        pass
    # TODO: AMD rocm-smi / sysfs if needed
    return None


def sample(conn: sqlite3.Connection) -> None:
    ts = int(time.time())
    cpu_uj = read_cpu_rapl_energy_uj()
    gpu_w = read_gpu_power_w()
    ups_w = _read_ups_power_w()
    conn.execute(
        "INSERT INTO power_samples (ts, cpu_energy_uj, gpu_power_w, ups_power_w) VALUES (?, ?, ?, ?)",
        (
            ts,
            cpu_uj if cpu_uj is not None else 0.0,
            gpu_w if gpu_w is not None else 0.0,
            ups_w if ups_w is not None else 0.0,
        ),
    )
    conn.commit()


def main() -> None:
    ensure_data_dir()
    conn = sqlite3.connect(str(DB_PATH))
    init_db(conn)
    try:
        while True:
            sample(conn)
            time.sleep(POLL_INTERVAL_SEC)
    except KeyboardInterrupt:
        pass
    finally:
        conn.close()


if __name__ == "__main__":
    main()
    sys.exit(0)
