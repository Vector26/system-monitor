# system-monitor

Plain-English Linux health tools: **sys-check** for one-shot snapshots and **PlainTop** for a live full-screen dashboard (btop-style layout, human-readable verdicts).

## Requirements

- Linux with Python 3.10+
- **sys-check / PlainTop:** `lm-sensors`, NVIDIA tools optional (GPU pane degrades gracefully)
- Debian/Ubuntu: `install.sh` installs `lm-sensors` and `python3-venv`

## Install

Clone anywhere, then run the installer from the project directory:

```bash
git clone https://github.com/Vector26/system-monitor.git
cd system-monitor
./install.sh
```

Open a **new terminal** (or `source ~/.bashrc`) and run `plaintop` or `sys-check`.

The installer creates a local `.venv`, installs Python dependencies, enables a **user systemd** power logger, and adds shell aliases.

### Optional: Fortress stack integration

If you use [Fortress](https://github.com/Vector26) (or your own layout under `~/fortress`), PlainTop can show Docker/service status and open the control menu with **`s`**.

Set the install root if it is not `~/fortress`:

```bash
export FORTRESS_HOME="$HOME/fortress"   # or your path
```

Expected layout: `$FORTRESS_HOME/control/fortress` and `$FORTRESS_HOME/control/status.py`. Without these files, the services pane shows “control offline” and everything else still works.

## Commands

| Command | What it does |
|---------|----------------|
| `sys-check` | One-shot health card (CPU, GPU, RAM, disk, network, power history). Good for `watch -n 5 sys-check`. |
| `plaintop` | Full-screen live monitor with panes and OK / Watch / Problem verdicts. Press **`q`** to quit. |
| `./check_gpu_usage.sh` | Lists processes using the NVIDIA GPU (helper script). |

### PlainTop keys

| Key | Action |
|-----|--------|
| `q` | Quit |
| `r` | Refresh now |
| `?` | Toggle help |
| `s` | Open Fortress control menu (when `FORTRESS_HOME` is configured) |

Maximize the terminal (or F11) for the intended multi-row layout: area graphs, per-core CPU bars, disk bars, network charts, and a process list.

### PlainTop panes

- **Overall** — summary verdict at the top
- **Processor (CPU)** — utilization, temperature wording, load vs core count
- **Memory (RAM)** — free GB for apps, not just used %
- **Graphics (GPU)** — VRAM and compute clients (NVIDIA when available)
- **Storage** — mount points you care about; Windows/recovery partitions can be ignored for alerts (see `collectors.py`)
- **Network** — download/upload with light/moderate/heavy labels
- **Top programs** — who is using CPU/RAM
- **Power** — energy from the background logger (24h / 7d / 30d / 60d when data exists)
- **Services** — Fortress stack status (optional)

## Compared to btop

| btop | PlainTop |
|------|----------|
| Raw numbers and graphs | Sentences: “10 GB free for new apps” |
| You interpret load average | “4 tasks waiting; you have 16 cores — fine” |
| Per-metric colors | Green / yellow / red **verdict** per pane |
| One interface | `sys-check` for snapshots, `plaintop` for live |

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
setup_service.sh    →  systemd user unit for power_logger
```

**Power history:** `install.sh` enables `system-monitor-power` (user systemd). Samples go to `~/.local/share/system-monitor/power_history.db`.

## Project layout

| File | Role |
|------|------|
| `install.sh` | Venv, deps, aliases, power logger service |
| `requirements.txt` | `rich`, `psutil`, `textual` |
| `collectors.py` | Hardware and OS metrics |
| `verdicts.py` | Human-readable thresholds |
| `display_stats.py` | `sys-check` entry point |
| `plaintop.py` | Live TUI entry point |

## License

MIT — see [LICENSE](LICENSE).
