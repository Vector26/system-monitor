"""Block-element charts for PlainTop (btop-style bars, 1080p)."""

from __future__ import annotations

from collections import deque
from typing import Deque

# Unicode block elements (UTF-8 terminal)
BAR_FULL = "\u2588"  # █
BAR_EMPTY = "\u2591"  # ░
SPARK_RAMP = "\u2581\u2582\u2583\u2584\u2585\u2586\u2587\u2588"  # ▁▂▃▄▅▆▇█
AREA_FILL = "\u2588"  # █ filled area charts
NET_DOWN_FILL = "\u2584"  # ▄ lower half — download
NET_UP_FILL = "\u2580"  # ▀ upper half — upload
POWER_FILL = "\u2593"  # ▓ medium shade — power history


def resample(values: list[float], width: int) -> list[float]:
    if not values:
        return [0.0] * width
    if len(values) >= width:
        step = len(values) / width
        return [values[int(i * step)] for i in range(width)]
    out = list(values)
    while len(out) < width:
        out.append(values[-1])
    return out[:width]


def sparkline(values: list[float], width: int = 48, *, max_val: float | None = None) -> str:
    """Single-row sparkline using ▁▂▃▄▅▆▇█."""
    if not values:
        return BAR_EMPTY * min(width, 40)
    vals = resample(values, width)
    mx = max_val if max_val and max_val > 0 else max(max(vals), 0.01)
    ramp = SPARK_RAMP
    return "".join(
        ramp[min(len(ramp) - 1, int((v / mx) * (len(ramp) - 1)))] for v in vals
    )


def sparkline_area(
    values: list[float],
    width: int = 48,
    height: int = 5,
    *,
    max_val: float | None = None,
    char: str = AREA_FILL,
) -> list[str]:
    """Multi-row filled area chart using block characters."""
    if not values:
        return [(BAR_EMPTY * width) for _ in range(height)]
    vals = resample(values, width)
    mx = max_val if max_val and max_val > 0 else max(max(vals), 0.01)
    grid = [[BAR_EMPTY] * width for _ in range(height)]
    for x, v in enumerate(vals):
        col_h = max(0, min(height - 1, int(round((v / mx) * (height - 1)))))
        for y in range(height - col_h - 1, height):
            grid[y][x] = char
    return ["".join(row) for row in grid]


def hbar(
    pct: float,
    width: int = 28,
    *,
    fill: str = BAR_FULL,
    empty: str = BAR_EMPTY,
) -> str:
    pct = max(0.0, min(100.0, pct))
    filled = int(round((pct / 100.0) * width))
    filled = max(0, min(width, filled))
    return fill * filled + empty * (width - filled)


def dual_sparkline(
    down: list[float],
    up: list[float],
    width: int = 40,
    height: int = 3,
) -> list[str]:
    """Network: download (▄) and upload (▀) area charts."""
    if not down and not up:
        return [BAR_EMPTY * width, BAR_EMPTY * width]
    d = sparkline_area(down, width, height, max_val=None, char=NET_DOWN_FILL)
    u = sparkline_area(up, width, height, max_val=None, char=NET_UP_FILL)
    return [f"down {line}" for line in d] + [f"up   {line}" for line in u]


class MetricHistory:
    """Rolling samples for live graphs (~72s at 1.5s refresh)."""

    def __init__(self, maxlen: int = 48) -> None:
        self.maxlen = maxlen
        self.cpu: Deque[float] = deque(maxlen=maxlen)
        self.ram_pct: Deque[float] = deque(maxlen=maxlen)
        self.gpu_vram_pct: Deque[float] = deque(maxlen=maxlen)
        self.gpu_power: Deque[float] = deque(maxlen=maxlen)
        self.net_down_mbps: Deque[float] = deque(maxlen=maxlen)
        self.net_up_mbps: Deque[float] = deque(maxlen=maxlen)
        self.ups_w: Deque[float] = deque(maxlen=maxlen)

    def push(self, snap) -> None:
        if snap.cpu_usage_pct is not None:
            self.cpu.append(float(snap.cpu_usage_pct))
        if snap.ram_total_gb:
            pct = 100.0 * snap.ram_used_gb / snap.ram_total_gb
            self.ram_pct.append(pct)
        if snap.gpu:
            tot = snap.gpu.get("memory_total_gb") or 0
            used = snap.gpu.get("memory_used_gb") or 0
            if tot > 0:
                self.gpu_vram_pct.append(100.0 * used / tot)
            pw = snap.gpu.get("power_w")
            if pw is not None:
                self.gpu_power.append(float(pw))
        if snap.network:
            self.net_down_mbps.append(snap.network.download_bps / (1024 * 1024))
            self.net_up_mbps.append(snap.network.upload_bps / (1024 * 1024))
        if snap.ups_load_w is not None:
            self.ups_w.append(float(snap.ups_load_w))


def core_bars(per_core: list[float], width: int = 32) -> list[str]:
    """One mini bar per CPU core (wraps to fit width)."""
    if not per_core:
        return ["(no per-core data)"]
    bar_w = max(4, width // max(1, (len(per_core) + 3) // 4))
    lines: list[str] = []
    chunk: list[str] = []
    for i, pct in enumerate(per_core):
        chunk.append(f"{i:2d}{hbar(pct, bar_w)}")
        if len(chunk) == 4:
            lines.append(" ".join(chunk))
            chunk = []
    if chunk:
        lines.append(" ".join(chunk))
    return lines
