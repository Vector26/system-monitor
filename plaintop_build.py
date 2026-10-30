"""Build rich pane content (graphs + tables) for PlainTop."""

from __future__ import annotations

from collectors import (
    SystemSnapshot,
    disks_display,
    disks_for_alerts,
)
from plaintop_graphs import (
    POWER_FILL,
    MetricHistory,
    core_bars,
    dual_sparkline,
    hbar,
    sparkline,
    sparkline_area,
)
from verdicts import (
    Verdict,
    _proc_basename,
    cpu_verdict,
    disk_combined_verdict,
    gpu_verdict,
    memory_verdict,
    network_verdict,
    power_verdict,
    process_plain,
)


def _chart_width(cols: int, fraction: float = 0.85) -> int:
    return max(36, min(64, int(cols * fraction)))


def build_cpu_pane(snap: SystemSnapshot, hist: MetricHistory, width: int, *, tui: bool) -> tuple[Verdict, list[str], list[str]]:
    v = cpu_verdict(snap, tui=tui)
    w = _chart_width(width)
    charts = sparkline_area(list(hist.cpu), w, height=5, max_val=100.0)
    charts = [f"CPU%  {line}" for line in charts]
    extra = core_bars(snap.cpu_per_core, width=min(72, w + 20))
    if snap.load_1 is not None:
        extra.insert(0, f"load {snap.load_1:.1f} / {snap.load_5:.1f} / {snap.load_15:.1f}  ({snap.cores} cores)")
    return v, charts, extra


def build_mem_pane(snap: SystemSnapshot, hist: MetricHistory, width: int, *, tui: bool) -> tuple[Verdict, list[str], list[str]]:
    v = memory_verdict(snap, tui=tui)
    w = _chart_width(width)
    charts = sparkline_area(list(hist.ram_pct), w, height=5, max_val=100.0)
    charts = [f"RAM%  {line}" for line in charts]
    pct = 100.0 * snap.ram_used_gb / snap.ram_total_gb if snap.ram_total_gb else 0
    extra = [
        f"used  {hbar(pct, 40)} {pct:.0f}%",
        f"free  {snap.ram_available_gb:.1f} GB available",
    ]
    return v, charts, extra


def build_gpu_pane(snap: SystemSnapshot, hist: MetricHistory, width: int, *, tui: bool) -> tuple[Verdict, list[str], list[str]]:
    v = gpu_verdict(snap, tui=tui)
    if not v:
        return v, [], []
    w = _chart_width(width)
    charts = sparkline_area(list(hist.gpu_vram_pct), w, height=4, max_val=100.0)
    charts = [f"VRAM% {line}" for line in charts]
    if hist.gpu_power:
        pw = sparkline(list(hist.gpu_power), w, max_val=max(max(hist.gpu_power), 50))
        charts.append(f"GPU W {pw}")
    extra = []
    if snap.gpu:
        util = snap.gpu.get("util_pct")
        if util is not None:
            extra.append(f"GPU util {hbar(float(util), 36)} {util:.0f}%")
    for p in snap.gpu_processes[:4]:
        extra.append(f"  {_proc_basename(p['name'])}  {p['memory_mib']:.0f} MiB")
    return v, charts, extra


def build_disk_pane(snap: SystemSnapshot, width: int, *, tui: bool) -> tuple[Verdict, list[str], list[str]]:
    v, alert_lines = disk_combined_verdict(snap, tui=tui)
    w = min(36, _chart_width(width) // 2)
    charts: list[str] = []
    for d in disks_for_alerts(snap.disks):
        label = d.mount if len(d.mount) <= 12 else d.mount[-12:]
        charts.append(f"{label:12} {hbar(d.percent, w)} {d.percent:4.0f}%  {d.free_gb:5.0f}G free")
    foreign = [d for d in disks_display(snap.disks) if d.kind == "foreign"]
    extra = list(alert_lines)
    if foreign:
        extra.append("[dim]---[/]")
        for d in foreign:
            extra.append(f"[dim]{d.mount}: {d.free_gb:.0f}G free (Windows)[/]")
    return v, charts, extra


def build_net_pane(snap: SystemSnapshot, hist: MetricHistory, width: int, *, tui: bool) -> tuple[Verdict, list[str], list[str]]:
    v = network_verdict(snap, tui=tui)
    w = _chart_width(width)
    if hist.net_down_mbps or hist.net_up_mbps:
        charts = dual_sparkline(
            list(hist.net_down_mbps),
            list(hist.net_up_mbps),
            width=w,
            height=3,
        )
    else:
        charts = ["(graph fills after a few seconds)"]
    net = snap.network
    extra = []
    if net:
        down = net.download_bps / (1024 * 1024)
        up = net.upload_bps / (1024 * 1024)
        extra.append(f"now  down {hbar(min(100, down * 10), 20)} {down:.2f} MB/s")
        extra.append(f"     up   {hbar(min(100, up * 10), 20)} {up:.2f} MB/s")
    return v, charts, extra


def build_power_pane(snap: SystemSnapshot, hist: MetricHistory, width: int, *, tui: bool) -> tuple[Verdict, list[str], list[str]]:
    v = power_verdict(snap, tui=tui)
    w = _chart_width(width)
    charts: list[str] = []
    if hist.ups_w:
        mx = max(max(hist.ups_w), snap.ups_rating_w or 900)
        charts = [f"UPS W {sparkline(list(hist.ups_w), w, max_val=mx)}"]
        charts.extend(sparkline_area(list(hist.ups_w), w, height=3, max_val=mx, char=POWER_FILL))
    h = snap.power_by_component
    extra = []
    if snap.power_db_available:
        for label, key in (("CPU", "cpu"), ("GPU", "gpu"), ("Total", "total")):
            wh = h.get(key, {}).get("24h", 0)
            extra.append(f"24h {label:5} {hbar(min(100, wh / 50), 24)} {wh:6.0f} Wh")
    return v, charts, extra


def build_process_rows(
    snap: SystemSnapshot, bar_width: int = 18
) -> list[tuple[str, str, str, str, str]]:
    rows = []
    for p in snap.top_processes:
        name, cpu_s, mem_s = process_plain(p)
        bar = hbar(min(100, p.cpu_percent), bar_width)
        rows.append((str(p.pid), name, cpu_s, mem_s, bar))
    return rows
