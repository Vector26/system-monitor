"""System metric collectors shared by sys-check and PlainTop."""

from __future__ import annotations

import os
import re
import sqlite3
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

try:
    import psutil
except ImportError:
    psutil = None

DATA_DIR = Path(os.environ.get("XDG_DATA_HOME", "~/.local/share")).expanduser() / "system-monitor"
DB_PATH = DATA_DIR / "power_history.db"
BAR_LEN = 20

# Mount kinds for alerts vs display-only
MOUNT_SYSTEM = "system"  # Ubuntu OS: /, /home, /boot, ...
MOUNT_DATA = "data"  # Your data under /mnt (ollama, movies, ...)
MOUNT_FOREIGN = "foreign"  # Windows dual-boot drives — show, never alert
MOUNT_IGNORE = "ignore"  # Recovery / tiny Windows partitions — hidden


def ascii_safe(text: str) -> str:
    """Avoid mojibake in SSH terminals without full UTF-8."""
    return (
        text.replace("\u2014", "-")
        .replace("\u2013", "-")
        .replace("\u2022", "-")
        .replace("\u00b0C", " C")
        .replace("\u00b0", " ")
        .replace("—", "-")
        .replace("•", "-")
        .replace("°C", " C")
        .replace("°", " ")
    )


def bar(fraction: float, width: int = BAR_LEN) -> str:
    filled = int(round(fraction * width))
    filled = max(0, min(width, filled))
    return "█" * filled + "░" * (width - filled)


def bar_ascii(fraction: float, width: int = BAR_LEN) -> str:
    filled = int(round(fraction * width))
    filled = max(0, min(width, filled))
    return "[" + "#" * filled + "-" * (width - filled) + "]"


def temp_label(c: float) -> str:
    if c < 50:
        return "Cool"
    if c < 70:
        return "Warm"
    if c < 85:
        return "Hot"
    return "Critical"


def read_cpu_temp() -> tuple[float | None, str]:
    try:
        out = subprocess.run(
            ["sensors"],
            capture_output=True,
            text=True,
            timeout=3,
        )
        if out.returncode == 0 and out.stdout:
            best = None
            for line in out.stdout.splitlines():
                if "Package" in line or "Tctl" in line or "Core 0" in line or "temp1" in line.lower():
                    m = re.search(r"\+?([\d.]+)\s*°?C", line)
                    if m:
                        t = float(m.group(1))
                        if best is None or "Package" in line or "Tctl" in line:
                            best = t
                        if "Core 0" in line or ("temp1" in line.lower() and best is None):
                            best = t
            if best is not None:
                return (best, temp_label(best))
            m = re.search(r"\+?([\d.]+)\s*°?C", out.stdout)
            if m:
                t = float(m.group(1))
                return (t, temp_label(t))
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    base = Path("/sys/class/thermal")
    if base.exists():
        for name in sorted(base.iterdir()):
            if name.name.startswith("thermal_zone"):
                p = name / "temp"
                if p.exists():
                    try:
                        t = int(p.read_text().strip()) / 1000.0
                        if 0 < t < 120:
                            return (t, temp_label(t))
                    except (OSError, ValueError):
                        pass
    return (None, "N/A")


def read_cpu_usage(interval: float = 0.1) -> float | None:
    if psutil is None:
        return None
    return psutil.cpu_percent(interval=interval)


def read_cpu_per_core(interval: float = 0.0) -> list[float]:
    if psutil is None:
        return []
    return list(psutil.cpu_percent(percpu=True, interval=interval))


def read_cpu_power_w() -> float | None:
    base = Path("/sys/class/powercap")
    if not base.exists():
        return None
    for name in sorted(base.iterdir()):
        if not name.is_dir() or not name.name.startswith("intel-rapl"):
            continue
        power_path = name / "power_uw"
        if power_path.exists():
            try:
                return float(power_path.read_text().strip()) / 1e6
            except (OSError, ValueError):
                pass
    return None


def read_load_avg() -> tuple[float, float, float] | None:
    if psutil is None:
        return None
    return psutil.getloadavg()


def cpu_count() -> int:
    if psutil is not None:
        return psutil.cpu_count(logical=True) or 1
    return os.cpu_count() or 1


def read_gpu_info() -> dict | None:
    try:
        out = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=temperature.gpu,memory.used,memory.total,power.draw,utilization.gpu",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if out.returncode != 0 or not out.stdout.strip():
            return None
        line = out.stdout.strip().splitlines()[0]
        parts = [p.strip() for p in line.split(",")]

        def _num(s: str) -> float | None:
            s = s.replace(" MiB", "").replace("W", "").replace(" %", "").strip()
            try:
                return float(s)
            except ValueError:
                return None

        temp = _num(parts[0]) if len(parts) > 0 else None
        mem_used = _num(parts[1]) if len(parts) > 1 else None
        mem_tot = _num(parts[2]) if len(parts) > 2 else None
        power = _num(parts[3]) if len(parts) > 3 else None
        util = _num(parts[4]) if len(parts) > 4 else None
        if mem_used is not None and mem_tot is not None:
            mem_used = mem_used / 1024.0
            mem_tot = mem_tot / 1024.0
        return {
            "temp_c": temp,
            "memory_used_gb": mem_used or 0,
            "memory_total_gb": mem_tot or 0,
            "power_w": power,
            "util_pct": util,
        }
    except (FileNotFoundError, subprocess.TimeoutExpired, ValueError, IndexError):
        return None


def read_gpu_processes(limit: int = 3) -> list[dict]:
    try:
        out = subprocess.run(
            [
                "nvidia-smi",
                "--query-compute-apps=pid,process_name,used_memory",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if out.returncode != 0 or not out.stdout.strip():
            return []
        procs = []
        for line in out.stdout.strip().splitlines():
            parts = [p.strip() for p in line.split(",")]
            if len(parts) < 3:
                continue
            try:
                pid = int(parts[0])
                name = parts[1]
                mem_mib = float(parts[2])
            except ValueError:
                continue
            procs.append({"pid": pid, "name": name, "memory_mib": mem_mib})
        procs.sort(key=lambda p: p["memory_mib"], reverse=True)
        return procs[:limit]
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return []


def read_ram_gb() -> tuple[float, float]:
    if psutil is None:
        return (0.0, 0.0)
    v = psutil.virtual_memory()
    return (v.used / (1024**3), v.total / (1024**3))


def read_ram_available_gb() -> float:
    if psutil is None:
        return 0.0
    return psutil.virtual_memory().available / (1024**3)


def read_ups_power_w() -> tuple[float | None, float | None]:
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
            load_w = rating_w = None
            for line in out.stdout.splitlines():
                m = re.search(r"Load\s*\.+\s+(\d+)\s*Watt", line, re.IGNORECASE)
                if m:
                    load_w = float(m.group(1))
                m = re.search(r"Rating\s+Power\s*\.+\s+(\d+)\s*Watt", line, re.IGNORECASE)
                if m:
                    rating_w = float(m.group(1))
            if load_w is not None:
                return (load_w, rating_w)
        except (FileNotFoundError, subprocess.TimeoutExpired, ValueError):
            continue
    return (None, None)


@dataclass
class DiskMount:
    mount: str
    used_gb: float
    total_gb: float
    percent: float
    free_gb: float
    kind: str = MOUNT_SYSTEM
    label: str = ""
    fstype: str = ""


def classify_mount(mountpoint: str, fstype: str, total_gb: float) -> str:
    """Classify mounts so Windows recovery does not trigger Ubuntu alerts."""
    low = mountpoint.lower()
    name = low.rsplit("/", 1)[-1]

    if "recovery" in low or name.endswith("_recovery") or name == "recovery":
        return MOUNT_IGNORE
    if low.startswith("/mnt/win_") and total_gb < 3.0:
        return MOUNT_IGNORE
    if low in ("/", "/home", "/var") or low.startswith("/boot"):
        return MOUNT_SYSTEM
    if low.startswith("/mnt/win_"):
        return MOUNT_FOREIGN
    if low.startswith("/mnt/"):
        return MOUNT_DATA
    if mountpoint.startswith("/"):
        return MOUNT_SYSTEM
    return MOUNT_FOREIGN


def mount_display_label(mountpoint: str, kind: str) -> str:
    if mountpoint == "/":
        return "Main system (/)"
    if mountpoint == "/home":
        return "Home (/home)"
    if mountpoint.startswith("/boot"):
        return f"Boot ({mountpoint})"
    if kind == MOUNT_FOREIGN:
        return f"Windows/extra ({mountpoint})"
    if kind == MOUNT_DATA:
        return f"Data ({mountpoint})"
    return mountpoint


def read_disk_mounts() -> list[DiskMount]:
    if psutil is None:
        return []
    mounts: list[DiskMount] = []
    seen: set[str] = set()
    for part in psutil.disk_partitions(all=False):
        if part.fstype in ("", "squashfs", "tmpfs", "devtmpfs", "overlay"):
            continue
        if part.mountpoint in seen:
            continue
        try:
            usage = psutil.disk_usage(part.mountpoint)
        except (PermissionError, OSError):
            continue
        seen.add(part.mountpoint)
        total_gb = usage.total / (1024**3)
        used_gb = usage.used / (1024**3)
        free_gb = usage.free / (1024**3)
        kind = classify_mount(part.mountpoint, part.fstype, total_gb)
        mounts.append(
            DiskMount(
                mount=part.mountpoint,
                used_gb=used_gb,
                total_gb=total_gb,
                percent=usage.percent,
                free_gb=free_gb,
                kind=kind,
                label=mount_display_label(part.mountpoint, kind),
                fstype=part.fstype,
            )
        )

    def _sort_key(m: DiskMount) -> tuple:
        order = {MOUNT_SYSTEM: 0, MOUNT_DATA: 1, MOUNT_FOREIGN: 2, MOUNT_IGNORE: 3}
        return (order.get(m.kind, 9), m.mount != "/", m.mount)

    mounts.sort(key=_sort_key)
    return mounts


def disks_for_alerts(disks: list[DiskMount]) -> list[DiskMount]:
    """Mounts that matter for Ubuntu health (excludes Windows recovery & foreign)."""
    return [d for d in disks if d.kind in (MOUNT_SYSTEM, MOUNT_DATA)]


def disks_display(disks: list[DiskMount]) -> list[DiskMount]:
    """Mounts to show in the UI (excludes ignored)."""
    return [d for d in disks if d.kind != MOUNT_IGNORE]


@dataclass
class NetworkRates:
    download_bps: float
    upload_bps: float


class NetworkSampler:
    """Compute bytes/sec from counter deltas between samples."""

    def __init__(self) -> None:
        self._last: dict[str, tuple[int, int]] = {}
        self._last_ts: float | None = None

    @property
    def has_baseline(self) -> bool:
        return self._last_ts is not None

    def sample(self) -> NetworkRates | None:
        if psutil is None:
            return None
        now = time.time()
        counters = psutil.net_io_counters(pernic=False)
        if counters is None:
            return None
        cur = (counters.bytes_recv, counters.bytes_sent)
        if self._last_ts is None:
            self._last_ts = now
            self._last["total"] = cur
            return NetworkRates(0.0, 0.0)
        dt = now - self._last_ts
        if dt <= 0:
            return NetworkRates(0.0, 0.0)
        prev = self._last.get("total", cur)
        down = max(0, (cur[0] - prev[0]) / dt)
        up = max(0, (cur[1] - prev[1]) / dt)
        self._last["total"] = cur
        self._last_ts = now
        return NetworkRates(download_bps=down, upload_bps=up)


@dataclass
class ProcessInfo:
    pid: int
    name: str
    cpu_percent: float
    memory_gb: float


def read_top_processes(limit: int = 8) -> list[ProcessInfo]:
    if psutil is None:
        return []
    # Prime CPU percent counters
    for p in psutil.process_iter(["pid"]):
        try:
            p.cpu_percent(None)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    procs: list[ProcessInfo] = []
    for p in psutil.process_iter(["pid", "name", "cpu_percent", "memory_info"]):
        try:
            info = p.info
            mem = info.get("memory_info")
            mem_gb = (mem.rss / (1024**3)) if mem else 0.0
            cpu = info.get("cpu_percent") or 0.0
            procs.append(
                ProcessInfo(
                    pid=info["pid"],
                    name=info.get("name") or "?",
                    cpu_percent=cpu,
                    memory_gb=mem_gb,
                )
            )
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            continue
    procs.sort(key=lambda x: (x.cpu_percent, x.memory_gb), reverse=True)
    return procs[:limit]


def get_power_history() -> dict[str, float]:
    return get_power_history_by_component()["total"]


def get_power_history_by_component() -> dict[str, dict[str, float]]:
    windows = [(24 * 3600, "24h"), (7 * 86400, "7d"), (30 * 86400, "30d"), (60 * 86400, "60d")]
    result = {
        "cpu": {k: 0.0 for _, k in windows},
        "gpu": {k: 0.0 for _, k in windows},
        "ups": {k: 0.0 for _, k in windows},
        "total": {k: 0.0 for _, k in windows},
    }
    if not DB_PATH.exists():
        return result
    now = int(time.time())
    try:
        conn = sqlite3.connect(str(DB_PATH))
        try:
            cur = conn.execute(
                "SELECT ts, cpu_energy_uj, gpu_power_w, ups_power_w FROM power_samples WHERE ts >= ? ORDER BY ts",
                (now - 60 * 86400,),
            )
            rows = list(cur.fetchall())
            has_ups = True
        except sqlite3.OperationalError:
            cur = conn.execute(
                "SELECT ts, cpu_energy_uj, gpu_power_w FROM power_samples WHERE ts >= ? ORDER BY ts",
                (now - 60 * 86400,),
            )
            rows = [(r[0], r[1], r[2], None) for r in cur.fetchall()]
            has_ups = False
        conn.close()
    except (sqlite3.Error, OSError):
        return result

    for window_sec, key in windows:
        cutoff = now - window_sec
        window_rows = [r for r in rows if r[0] >= cutoff]
        if len(window_rows) < 2:
            continue
        cpu_wh = 0.0
        for i in range(1, len(window_rows)):
            e_prev = window_rows[i - 1][1] or 0
            e_cur = window_rows[i][1] or 0
            delta_uj = e_cur - e_prev
            if delta_uj < 0:
                delta_uj += 2**32
            cpu_wh += delta_uj / (3.6e9)
        gpu_wh = 0.0
        for i in range(len(window_rows) - 1):
            t1 = window_rows[i][0]
            p1 = window_rows[i][2]
            t2 = window_rows[i + 1][0]
            p2 = window_rows[i + 1][2]
            dt = t2 - t1
            if dt <= 0:
                continue
            avg_p = (p1 + p2) / 2.0 if (p1 and p2) else (p1 or p2 or 0)
            gpu_wh += avg_p * dt / 3600.0
        ups_wh = 0.0
        if has_ups and len(window_rows[0]) > 3:
            for i in range(len(window_rows) - 1):
                t1 = window_rows[i][0]
                p1 = window_rows[i][3]
                t2 = window_rows[i + 1][0]
                p2 = window_rows[i + 1][3]
                dt = t2 - t1
                if dt <= 0 or (p1 is None and p2 is None):
                    continue
                avg_p = (p1 + p2) / 2.0 if (p1 and p2) else (p1 or p2 or 0)
                ups_wh += avg_p * dt / 3600.0
        result["cpu"][key] = round(cpu_wh, 1)
        result["gpu"][key] = round(gpu_wh, 1)
        result["ups"][key] = round(ups_wh, 1)
        result["total"][key] = round(cpu_wh + gpu_wh, 1)
        if has_ups and ups_wh > 0:
            result["total"][key] = round(ups_wh, 1)
    return result


def power_db_exists() -> bool:
    return DB_PATH.exists()


@dataclass
class SystemSnapshot:
    cpu_temp_c: float | None
    cpu_temp_label: str
    cpu_usage_pct: float | None
    cpu_power_w: float | None
    load_1: float | None
    load_5: float | None
    load_15: float | None
    cores: int
    cpu_per_core: list[float]
    gpu: dict | None
    gpu_processes: list[dict]
    ram_used_gb: float
    ram_total_gb: float
    ram_available_gb: float
    ups_load_w: float | None
    ups_rating_w: float | None
    disks: list[DiskMount]
    network: NetworkRates | None
    top_processes: list[ProcessInfo]
    power_by_component: dict[str, dict[str, float]]
    power_db_available: bool


def collect_snapshot(
    cpu_interval: float = 0.1,
    process_limit: int = 8,
    network_sampler: NetworkSampler | None = None,
) -> SystemSnapshot:
    cpu_temp, temp_label = read_cpu_temp()
    load = read_load_avg()
    gpu = read_gpu_info()
    ups_load, ups_rating = read_ups_power_w()
    ram_used, ram_total = read_ram_gb()
    net = network_sampler.sample() if network_sampler else None
    cpu_usage = read_cpu_usage(interval=cpu_interval)
    return SystemSnapshot(
        cpu_temp_c=cpu_temp,
        cpu_temp_label=temp_label,
        cpu_usage_pct=cpu_usage,
        cpu_power_w=read_cpu_power_w(),
        load_1=load[0] if load else None,
        load_5=load[1] if load else None,
        load_15=load[2] if load else None,
        cores=cpu_count(),
        cpu_per_core=read_cpu_per_core(interval=0.0),
        gpu=gpu,
        gpu_processes=read_gpu_processes(3) if gpu else [],
        ram_used_gb=ram_used,
        ram_total_gb=ram_total,
        ram_available_gb=read_ram_available_gb(),
        ups_load_w=ups_load,
        ups_rating_w=ups_rating,
        disks=read_disk_mounts(),
        network=net,
        top_processes=read_top_processes(process_limit),
        power_by_component=get_power_history_by_component(),
        power_db_available=power_db_exists(),
    )
