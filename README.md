<div align="center">

# system-monitor

**Linux health in plain English — snapshots or a live dashboard that tells you what matters.**

[![Python](https://img.shields.io/badge/Python-3.10+-3776AB?style=flat-square&logo=python&logoColor=white)](https://www.python.org/)
[![Textual](https://img.shields.io/badge/TUI-Textual-FFEAA7?style=flat-square)](https://textual.textualize.io/)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue?style=flat-square)](LICENSE)
[![Platform](https://img.shields.io/badge/Platform-Linux-lightgrey?style=flat-square)](https://kernel.org/)

</div>

---

## Why it exists

Raw metrics from `htop` or `btop` are fast — but when you are juggling a homelab GPU, disks, and services, you want **verdicts**, not homework. **sys-check** prints a one-shot health card; **PlainTop** is a full-screen live dashboard with **OK / Watch / Problem** labels and sentences like “10 GB free for new apps” instead of opaque percentages.

## Features

| | |
|---|---|
| **sys-check** | One-shot card — CPU, GPU, RAM, disk, network, power history; great with `watch -n 5 sys-check` |
| **PlainTop** | btop-style multi-pane TUI with rolling graphs and per-core CPU bars |
| **Human verdicts** | Green / yellow / red per pane — thresholds in `verdicts.py` |
| **Power history** | User systemd logger → 24h / 7d / 30d / 60d energy trends |
| **Fortress hook** | Optional Docker/service pane via `FORTRESS_HOME` + **`s`** control menu |
| **GPU helper** | `./check_gpu_usage.sh` lists NVIDIA compute clients |

### PlainTop keys

| Key | Action |
|-----|--------|
| `q` | Quit |
| `r` | Refresh now |
| `?` | Toggle help |
| `s` | Fortress control menu (when configured) |

Maximize the terminal (F11) for the intended layout: area graphs, disk bars, network charts, process list.

## Architecture

```
display_stats.py  →  sys-check CLI (Rich)
plaintop.py         →  PlainTop TUI (Textual)
        ↓
collectors.py       →  sensors, psutil, nvidia-smi, disk, network, processes, power DB
verdicts.py         →  metrics → OK / Watch / Problem + plain English
plaintop_build.py   →  pane content + bar charts
plaintop_graphs.py  →  rolling history for sparkline-style graphs
fortress_services.py→  optional Fortress status.py JSON (FORTRESS_HOME)
power_logger.py     →  background RAPL/GPU sampling
```

Power samples: `~/.local/share/system-monitor/power_history.db` (user unit `system-monitor-power`).

## Quick start

**Requirements:** Linux, Python 3.10+, `lm-sensors` (NVIDIA tools optional — GPU pane degrades gracefully).

```bash
git clone https://github.com/Vector26/system-monitor.git
cd system-monitor
./install.sh
```

Open a **new terminal** (or `source ~/.bashrc`), then:

```bash
sys-check    # snapshot
plaintop     # live dashboard
```

The installer creates `.venv`, installs deps, enables the power logger, and adds shell aliases.

### Optional Fortress integration

```bash
export FORTRESS_HOME="$HOME/fortress"   # adjust to your layout
```

Expects `$FORTRESS_HOME/control/fortress` and `$FORTRESS_HOME/control/status.py`. Without them, the services pane shows “control offline” — everything else still works.

> **What makes it different**
>
> Same machine data as classic TUIs — **interpretation layer included**. Load average becomes “4 tasks waiting; you have 16 cores — fine,” and each pane ends with a verdict you can act on without mental math.

## Compared to btop

| btop | PlainTop |
|------|----------|
| Raw numbers and graphs | Sentences + verdicts |
| You interpret load | Load vs core count explained |
| One interface | `sys-check` for snapshots, `plaintop` for live |

## Status

| Area | State |
|------|--------|
| sys-check / PlainTop | Stable daily driver |
| Power logger | Enabled by `install.sh` on supported hardware |
| Fortress pane | Optional; depends on your control scripts |

## Project layout

| File | Role |
|------|------|
| `install.sh` | Venv, deps, aliases, power logger service |
| `requirements.txt` | `rich`, `psutil`, `textual` |
| `collectors.py` | Hardware and OS metrics |
| `verdicts.py` | Human-readable thresholds |
| `display_stats.py` | `sys-check` entry |
| `plaintop.py` | Live TUI entry |

---

<div align="center">

**MIT** — see [LICENSE](LICENSE)

Built by **[Vector26](https://github.com/Vector26)** · Metrics with a point of view

</div>
