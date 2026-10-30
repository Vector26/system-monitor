#!/usr/bin/env python3
"""
Plain-English system health dashboard. Run as: sys-check (after install)
Uses rich for a clean status card; reads sensors, RAPL, nvidia-smi, and power history DB.
"""

import sys

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich import box

from collectors import (
    bar,
    bar_ascii,
    collect_snapshot,
    read_cpu_power_w,
    read_cpu_temp,
    read_cpu_usage,
    read_gpu_info,
    read_ram_gb,
    read_ups_power_w,
    get_power_history_by_component,
)
console = Console()


def _print_plain(
    cpu_temp_str: str,
    cpu_usage_str: str,
    cpu_power_str: str,
    usage_frac: float,
    gpu_temp_s: str,
    gpu_mem_s: str,
    gpu_power_s: str,
    gpu_mem_frac: float,
    ram_str: str,
    ram_frac: float,
    ram_critical: bool,
    by_component: dict[str, dict[str, float]],
    ups_load_str: str,
) -> None:
    lines = [
        "+-------------------------------- System Health --------------------------------+",
        "",
        f"  CPU    Temp: {cpu_temp_str}   Usage: {cpu_usage_str}   Power: {cpu_power_str}",
        f"         {bar_ascii(usage_frac)} {cpu_usage_str}",
        "",
        f"  GPU    Temp: {gpu_temp_s}   VRAM: {gpu_mem_s}   Power: {gpu_power_s}",
        f"         {bar_ascii(gpu_mem_frac)}",
        "",
    ]
    if ram_critical:
        lines.append(f"  RAM    {ram_str}   *** Memory Critical ***")
        lines.append(f"         {bar_ascii(ram_frac)} {ram_frac*100:.0f}%")
    else:
        lines.append(f"  RAM    {ram_str}")
        lines.append(f"         {bar_ascii(ram_frac)} {ram_frac*100:.0f}%")
    if ups_load_str:
        lines.append("")
        lines.append(f"  System (UPS)  {ups_load_str}")
    comp_rows = [("cpu", "CPU"), ("gpu", "GPU")]
    if any(by_component.get("ups", {}).get(k, 0) for k in ("24h", "7d", "30d", "60d")):
        comp_rows.append(("ups", "System(UPS)"))
    comp_rows.append(("total", "Total"))
    lines.extend([
        "",
        "  Power consumption (Wh / kWh) by component:",
        "  +-------------+------------------+------------------+------------------+------------------+",
        "  | Component   |      24h         |       7d         |      30d         |      60d         |",
        "  +-------------+------------------+------------------+------------------+------------------+",
    ])
    for comp, label in comp_rows:
        h = by_component.get(comp, {k: 0.0 for k in ("24h", "7d", "30d", "60d")})
        c24 = f"{h['24h']:.1f} ({h['24h']/1000:.2f})"
        c7 = f"{h['7d']:.0f} ({h['7d']/1000:.2f})"
        c30 = f"{h['30d']:.0f} ({h['30d']/1000:.2f})"
        c60 = f"{h['60d']:.0f} ({h['60d']/1000:.2f})"
        lines.append(
            f"  | {label:11} | {c24:>16} | {c7:>16} | {c30:>16} | {c60:>16} |"
        )
    lines.extend([
        "  +-------------+------------------+------------------+------------------+------------------+",
        "",
        "+-------------------------------------------------------------------------------+",
    ])
    print("\n".join(lines))
    sys.stdout.flush()


def main() -> None:
    cpu_temp, temp_label = read_cpu_temp()
    cpu_usage = read_cpu_usage()
    cpu_power = read_cpu_power_w()
    cpu_temp_str = f"{int(cpu_temp)}°C - {temp_label}" if cpu_temp is not None else "N/A"
    cpu_usage_str = f"{cpu_usage:.0f}%" if cpu_usage is not None else "N/A"
    cpu_power_str = f"{cpu_power:.1f} W" if cpu_power is not None else "N/A"
    usage_frac = (cpu_usage or 0) / 100.0
    cpu_bar = bar(usage_frac)

    gpu = read_gpu_info()
    if gpu:
        gpu_temp_s = f"{int(gpu['temp_c'])}°C" if gpu.get("temp_c") is not None else "N/A"
        gpu_mem_s = f"{gpu['memory_used_gb']:.1f}GB used of {gpu['memory_total_gb']:.0f}GB"
        gpu_power_s = f"{gpu['power_w']:.1f} W" if gpu.get("power_w") is not None else "N/A"
        gpu_mem_frac = gpu["memory_used_gb"] / gpu["memory_total_gb"] if gpu["memory_total_gb"] else 0
        gpu_bar = bar(gpu_mem_frac)
    else:
        gpu_temp_s = gpu_mem_s = gpu_power_s = "No GPU detected"
        gpu_bar = bar(0)
        gpu_mem_frac = 0.0

    ram_used, ram_total = read_ram_gb()
    ram_frac = ram_used / ram_total if ram_total else 0
    ram_str = f"{ram_used:.1f}GB / {ram_total:.0f}GB" if ram_total else "N/A"
    ram_bar = bar(ram_frac)
    ram_critical = ram_frac > 0.80

    by_component = get_power_history_by_component()

    ups_load_w, ups_rating_w = read_ups_power_w()
    if ups_load_w is not None:
        ups_pct = f"{100 * ups_load_w / ups_rating_w:.0f}%" if ups_rating_w else ""
        ups_load_str = f"Load: [white]{ups_load_w:.0f} W[/]"
        if ups_rating_w:
            ups_load_str += f" ([white]{ups_pct}[/] of [white]{ups_rating_w:.0f} W[/])"
        ups_load_str_plain = f"Load: {ups_load_w:.0f} W" + (
            f" ({ups_pct} of {ups_rating_w:.0f} W)" if ups_rating_w else ""
        )
    else:
        ups_load_str = ""
        ups_load_str_plain = ""

    if not sys.stdout.isatty():
        _print_plain(
            cpu_temp_str, cpu_usage_str, cpu_power_str, usage_frac,
            gpu_temp_s, gpu_mem_s, gpu_power_s, gpu_mem_frac,
            ram_str, ram_frac, ram_critical, by_component,
            ups_load_str_plain,
        )
        return

    table = Table(show_header=False, box=None, padding=(0, 1))
    table.add_column(style="bold cyan", width=10)
    table.add_column(style="white")

    table.add_row("CPU", f"Temp: [white]{cpu_temp_str}[/]  Usage: [white]{cpu_usage_str}[/]  Power: [white]{cpu_power_str}[/]")
    table.add_row("", f"[dim]{cpu_bar}[/] [dim]{cpu_usage_str}[/]")
    table.add_row("GPU", f"Temp: [white]{gpu_temp_s}[/]  VRAM: [white]{gpu_mem_s}[/]  Power: [white]{gpu_power_s}[/]")
    table.add_row("", f"[dim]{gpu_bar}[/]")
    if ram_critical:
        table.add_row("RAM", f"[bold red]{ram_str}[/]  [bold red]⚠️ Memory Critical[/]")
        table.add_row("", f"[bold red]{ram_bar}[/] [bold red]{ram_frac*100:.0f}%[/]")
    else:
        table.add_row("RAM", f"[white]{ram_str}[/]")
        table.add_row("", f"[dim]{ram_bar}[/] [dim]{ram_frac*100:.0f}%[/]")

    if ups_load_str:
        table.add_row("System (UPS)", ups_load_str)

    power_table = Table(
        title="Power consumption (Wh / kWh) by component",
        box=box.ROUNDED,
        show_header=True,
        header_style="bold magenta",
        padding=(0, 1),
    )
    power_table.add_column("Component", style="cyan", width=12)
    power_table.add_column("24h", justify="right", style="green")
    power_table.add_column("7d", justify="right", style="green")
    power_table.add_column("30d", justify="right", style="green")
    power_table.add_column("60d", justify="right", style="green")
    power_rows = [("cpu", "CPU"), ("gpu", "GPU")]
    if any(by_component.get("ups", {}).get(k, 0) for k in ("24h", "7d", "30d", "60d")):
        power_rows.append(("ups", "System (UPS)"))
    power_rows.append(("total", "Total"))
    for comp, label in power_rows:
        h = by_component.get(comp, {k: 0.0 for k in ("24h", "7d", "30d", "60d")})
        power_table.add_row(
            label,
            f"{h['24h']:.1f} Wh ({h['24h']/1000:.2f} kWh)",
            f"{h['7d']:.0f} Wh ({h['7d']/1000:.2f} kWh)",
            f"{h['30d']:.0f} Wh ({h['30d']/1000:.2f} kWh)",
            f"{h['60d']:.0f} Wh ({h['60d']/1000:.2f} kWh)",
        )
    table.add_row("Power", "")
    table.add_row("", power_table)

    console.print(
        Panel(
            table,
            title="[bold]System Health[/]",
            border_style="blue",
            box=box.ROUNDED,
            padding=(1, 2),
        )
    )
    sys.stdout.flush()


if __name__ == "__main__":
    main()
    sys.exit(0)
