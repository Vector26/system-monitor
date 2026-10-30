"""Plain-English verdicts for system metrics.

Thresholds tuned for a 16-core / ~30 GB RAM / ~16 GB VRAM workstation.
Status: ok | watch | problem
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from collectors import (
    DiskMount,
    MOUNT_FOREIGN,
    ProcessInfo,
    SystemSnapshot,
    ascii_safe,
    bar,
    disks_display,
    disks_for_alerts,
)

Status = Literal["ok", "watch", "problem"]


@dataclass
class Verdict:
    status: Status
    headline: str
    detail: str
    bar_fraction: float = 0.0
    bar_line: str = ""


def _t(text: str, tui: bool) -> str:
    return ascii_safe(text) if tui else text


def _b(frac: float, tui: bool) -> str:
    # PlainTop uses block bars (█░) in the terminal UI
    return bar(frac)


def _worst(*statuses: Status) -> Status:
    order = {"ok": 0, "watch": 1, "problem": 2}
    return max(statuses, key=lambda s: order[s])


def _disk_status(d: DiskMount) -> Status:
    if d.percent >= 90:
        return "problem"
    if d.percent >= 70:
        return "watch"
    return "ok"


def _single_disk_verdict(d: DiskMount, tui: bool) -> Verdict:
    status = _disk_status(d)
    if status == "problem":
        headline = f"{d.label}: {d.percent:.0f}% full, {d.free_gb:.0f} GB left"
        detail = "Delete or move files on this drive soon."
    elif status == "watch":
        headline = f"{d.label}: {d.percent:.0f}% used, {d.free_gb:.0f} GB free"
        detail = "Plan cleanup before it fills up."
    else:
        headline = f"{d.label}: {d.free_gb:.0f} GB free ({d.percent:.0f}% used)"
        detail = "Plenty of space."
    return Verdict(
        status=status,
        headline=_t(headline, tui),
        detail=_t(detail, tui),
        bar_fraction=d.percent / 100.0,
        bar_line=_b(d.percent / 100.0, tui),
    )


def disk_verdicts(snap: SystemSnapshot, *, alerts_only: bool = False, tui: bool = False) -> list[tuple[DiskMount, Verdict]]:
    disks = disks_for_alerts(snap.disks) if alerts_only else disks_display(snap.disks)
    return [(d, _single_disk_verdict(d, tui)) for d in disks]


def disk_combined_verdict(snap: SystemSnapshot, *, tui: bool = False) -> tuple[Verdict, list[str]]:
    """Alert on Ubuntu system + data drives only; foreign mounts shown separately."""
    alert_disks = disks_for_alerts(snap.disks)
    foreign = [d for d in snap.disks if d.kind == MOUNT_FOREIGN]

    if not alert_disks and not foreign:
        return (
            Verdict(status="ok", headline=_t("No storage info", tui), detail=_t("Could not read disks.", tui)),
            [],
        )

    pairs = [(d, _single_disk_verdict(d, tui)) for d in alert_disks]
    combined_status: Status = "ok"
    combined: Verdict | None = None
    for _, dv in pairs:
        if dv.status == "problem":
            combined = dv
            combined_status = "problem"
        elif dv.status == "watch" and combined_status != "problem":
            combined = dv
            combined_status = "watch"

    if combined is None:
        combined = pairs[0][1] if pairs else Verdict(status="ok", headline="OK", detail="")
        combined_status = "ok"

    # Headline: worst alert drive only, with numbers
    worst_d = next((d for d, v in pairs if v.status == combined_status), pairs[0][0] if pairs else None)
    if worst_d and combined_status != "ok":
        headline = _t(
            f"{worst_d.label}: {worst_d.percent:.0f}% used, {worst_d.free_gb:.0f} GB free",
            tui,
        )
    elif pairs:
        d0 = pairs[0][0]
        headline = _t(f"Ubuntu disks OK - smallest free space: {d0.free_gb:.0f} GB on {d0.mount}", tui)
    else:
        headline = _t("Ubuntu disks OK", tui)

    detail = _t(
        "Alerts use /, /home, /boot, and your /mnt data drives - not Windows partitions.",
        tui,
    )

    lines: list[str] = []
    for d, dv in pairs:
        if dv.status == "ok":
            continue
        tag = status_label(dv.status)
        lines.append(
            _t(
                f"[{status_style(dv.status)}]{tag}[/] {d.label}: {d.percent:.0f}% | {d.free_gb:.0f} GB free",
                tui,
            )
        )

    ok_parts = [
        f"{d.mount} {d.free_gb:.0f}G free"
        for d, dv in pairs
        if dv.status == "ok"
    ]
    if ok_parts:
        lines.append(_t(f"[dim]OK: {', '.join(ok_parts)}[/]", tui))

    if foreign:
        foreign_bits = [f"{d.mount} {d.free_gb:.0f}G free" for d in foreign]
        lines.append(
            _t(f"[dim]Windows/other (not counted): {', '.join(foreign_bits)}[/]", tui)
        )

    return (
        Verdict(
            status=combined_status,
            headline=headline,
            detail=detail,
            bar_fraction=combined.bar_fraction,
            bar_line=combined.bar_line,
        ),
        lines,
    )


def cpu_verdict(snap: SystemSnapshot, *, tui: bool = False) -> Verdict:
    usage = snap.cpu_usage_pct or 0.0
    frac = usage / 100.0
    cores = snap.cores
    load = snap.load_1

    if usage < 40:
        u_status: Status = "ok"
        u_word = "Idle"
    elif usage < 75:
        u_status = "watch"
        u_word = "Busy"
    else:
        u_status = "problem"
        u_word = "Saturated"

    temp = snap.cpu_temp_c
    temp_s = f"{int(temp)}C {snap.cpu_temp_label}" if temp is not None else "temp n/a"
    load_s = f"load {load:.1f}/{cores}" if load is not None and cores else ""

    headline = _t(f"{u_word} {usage:.0f}% | {temp_s}" + (f" | {load_s}" if load_s else ""), tui)

    if usage < 40:
        detail = "Lots of CPU headroom."
    elif usage < 75:
        detail = "Fine for heavy work."
    else:
        detail = "CPU near limit - close heavy apps if sluggish."

    status = u_status
    if temp is not None:
        if temp >= 85:
            status = _worst(status, "problem")
            detail = _t(f"Hot {int(temp)}C - throttling risk.", tui)
        elif temp >= 70:
            status = _worst(status, "watch")
            detail = _t(f"Warm {int(temp)}C - OK under load.", tui)

    if load is not None and cores > 0:
        if load > cores * 2:
            status = _worst(status, "problem")
            detail += _t(f" Queue {load:.1f} vs {cores} cores (high).", tui)
        elif load > cores * 1.5:
            status = _worst(status, "watch")
            detail += _t(f" Queue {load:.1f} vs {cores} cores (moderate).", tui)

    if snap.cpu_power_w is not None:
        detail += _t(f" CPU power {snap.cpu_power_w:.0f}W.", tui)

    return Verdict(
        status=status,
        headline=headline,
        detail=_t(detail.strip(), tui),
        bar_fraction=frac,
        bar_line=_b(frac, tui),
    )


def memory_verdict(snap: SystemSnapshot, *, tui: bool = False) -> Verdict:
    total = snap.ram_total_gb
    used = snap.ram_used_gb
    avail = snap.ram_available_gb
    pct = (100.0 * used / total) if total else 0.0
    frac = used / total if total else 0.0

    if avail < 2:
        status: Status = "problem"
        headline = _t(f"Critical - {avail:.1f} GB free ({pct:.0f}% used)", tui)
        detail = _t(f"{used:.1f}/{total:.0f} GB used. Close apps now.", tui)
    elif avail < 4:
        status = "watch"
        headline = _t(f"Tight - {avail:.1f} GB free ({pct:.0f}% used)", tui)
        detail = _t(f"{used:.1f}/{total:.0f} GB used. Avoid big new jobs.", tui)
    else:
        status = "ok"
        headline = _t(f"OK - {avail:.1f} GB free ({pct:.0f}% used)", tui)
        detail = _t(f"{used:.1f}/{total:.0f} GB in use.", tui)

    return Verdict(
        status=status,
        headline=headline,
        detail=detail,
        bar_fraction=frac,
        bar_line=_b(frac, tui),
    )


def _proc_basename(name: str) -> str:
    return name.rsplit("/", 1)[-1] if "/" in name else name


def gpu_verdict(snap: SystemSnapshot, *, tui: bool = False) -> Verdict | None:
    gpu = snap.gpu
    if not gpu:
        return Verdict(
            status="ok",
            headline=_t("No NVIDIA GPU", tui),
            detail=_t("GPU stats unavailable.", tui),
            bar_fraction=0.0,
            bar_line=_b(0, tui),
        )

    used = gpu.get("memory_used_gb", 0) or 0
    total = gpu.get("memory_total_gb", 0) or 1
    frac = used / total if total else 0.0
    pct = frac * 100.0
    free_gb = total - used

    if frac < 0.5:
        status: Status = "ok"
        word = "OK"
    elif frac < 0.85:
        status = "watch"
        word = "Watch"
    else:
        status = "problem"
        word = "Full"

    procs = snap.gpu_processes
    who = _proc_basename(procs[0]["name"]) if procs else ""
    power = gpu.get("power_w")
    temp = gpu.get("temp_c")

    headline = _t(f"{word} - VRAM {used:.1f}/{total:.0f} GB ({pct:.0f}%)", tui)
    parts = []
    if who:
        parts.append(who)
    if temp is not None:
        parts.append(f"{int(temp)}C")
    if power is not None:
        parts.append(f"{power:.0f}W")
    detail = _t(f"{free_gb:.1f} GB VRAM free. " + " | ".join(parts) + ".", tui)
    if status == "problem":
        detail += _t(" Run one GPU job at a time.", tui)
    elif status == "watch":
        detail += _t(" One more medium job OK.", tui)

    if temp is not None and temp >= 85:
        status = _worst(status, "problem")

    return Verdict(
        status=status,
        headline=headline,
        detail=detail.strip(),
        bar_fraction=frac,
        bar_line=_b(frac, tui),
    )


def network_verdict(snap: SystemSnapshot, *, tui: bool = False) -> Verdict:
    net = snap.network
    if net is None:
        return Verdict(
            status="ok",
            headline=_t("Measuring...", tui),
            detail=_t("Network rates appear after one refresh.", tui),
        )
    down_mbps = net.download_bps / (1024 * 1024)
    up_mbps = net.upload_bps / (1024 * 1024)

    def bucket(mbps: float) -> str:
        if mbps < 1:
            return "light"
        if mbps < 10:
            return "moderate"
        return "heavy"

    headline = _t(
        f"Down {down_mbps:.2f} MB/s ({bucket(down_mbps)}) | Up {up_mbps:.2f} MB/s ({bucket(up_mbps)})",
        tui,
    )
    if down_mbps < 0.01 and up_mbps < 0.01:
        detail = _t("Almost idle.", tui)
        status: Status = "ok"
    elif down_mbps >= 10 or up_mbps >= 10:
        detail = _t("Heavy traffic.", tui)
        status = "watch"
    else:
        detail = _t("Normal browsing/sync.", tui)
        status = "ok"

    return Verdict(status=status, headline=headline, detail=detail)


def process_plain(p: ProcessInfo) -> tuple[str, str, str]:
    cpu = p.cpu_percent
    cores = max(1, int(cpu / 100)) if cpu >= 100 else 0
    if cpu < 5:
        cpu_s = f"{cpu:.0f}% CPU"
    elif cpu < 100:
        cpu_s = f"{cpu:.0f}% CPU"
    else:
        cpu_s = f"{cpu:.0f}% (~{cores}c)"
    mem_s = f"{p.memory_gb:.1f} GB"
    name = _proc_basename(p.name)
    return (name, cpu_s, mem_s)


def power_verdict(snap: SystemSnapshot, *, tui: bool = False) -> Verdict:
    if not snap.power_db_available:
        return Verdict(
            status="watch",
            headline=_t("Power log not set up", tui),
            detail=_t("Run install.sh once.", tui),
        )
    h = snap.power_by_component
    cpu_24 = h.get("cpu", {}).get("24h", 0)
    gpu_24 = h.get("gpu", {}).get("24h", 0)
    total_24 = h.get("total", {}).get("24h", 0)

    ups = snap.ups_load_w
    now_w = f"{ups:.0f}W now" if ups is not None else ""

    if total_24 <= 0 and cpu_24 <= 0 and gpu_24 <= 0:
        return Verdict(
            status="ok",
            headline=_t("Logger running - collecting data", tui),
            detail=_t(now_w or "Check back later for 24h totals.", tui),
        )

    kwh = total_24 / 1000.0
    headline = _t(
        (f"{now_w} | " if now_w else "") + f"24h: {total_24:.0f} Wh ({kwh:.2f} kWh)",
        tui,
    )
    detail = _t(f"24h breakdown - CPU {cpu_24:.0f} Wh, GPU {gpu_24:.0f} Wh, total {total_24:.0f} Wh.", tui)
    return Verdict(status="ok", headline=headline, detail=detail)


def ups_verdict(snap: SystemSnapshot, *, tui: bool = False) -> Verdict | None:
    if snap.ups_load_w is None:
        return None
    load = snap.ups_load_w
    rating = snap.ups_rating_w
    pct = (100 * load / rating) if rating else None
    if pct is not None and pct > 80:
        return Verdict(
            status="watch",
            headline=_t(f"UPS {load:.0f}W ({pct:.0f}% of {rating:.0f}W)", tui),
            detail=_t("High wall power draw.", tui),
        )
    return Verdict(
        status="ok",
        headline=_t(f"UPS {load:.0f}W" + (f" ({pct:.0f}%)" if pct else ""), tui),
        detail=_t("Total system power from wall meter.", tui),
    )


def overall_verdict(snap: SystemSnapshot, *, tui: bool = False) -> Verdict:
    parts = [
        cpu_verdict(snap, tui=tui).status,
        memory_verdict(snap, tui=tui).status,
    ]
    gv = gpu_verdict(snap, tui=tui)
    if gv:
        parts.append(gv.status)
    for _, dv in disk_verdicts(snap, alerts_only=True, tui=tui):
        parts.append(dv.status)
    parts.append(network_verdict(snap, tui=tui).status)

    worst = _worst(*parts)
    if worst == "problem":
        return Verdict(
            status="problem",
            headline=_t("Overall: needs attention", tui),
            detail=_t("Check red panes (GPU, disk, CPU, or RAM).", tui),
        )
    if worst == "watch":
        return Verdict(
            status="watch",
            headline=_t("Overall: OK, some things to watch", tui),
            detail=_t("Yellow panes have details.", tui),
        )
    return Verdict(
        status="ok",
        headline=_t("Overall: healthy", tui),
        detail=_t("Ubuntu disks, CPU, RAM, and GPU look fine.", tui),
    )


def status_style(status: Status) -> str:
    return {"ok": "green", "watch": "yellow", "problem": "bold red"}[status]


def status_label(status: Status) -> str:
    return {"ok": "OK", "watch": "Watch", "problem": "Problem"}[status]
