#!/usr/bin/env python3
"""
PlainTop — btop-style live monitor in plain English (1080p layout).
Run: plaintop (after install.sh)
"""

from __future__ import annotations

import os
import subprocess

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical

from collectors import NetworkSampler, collect_snapshot
from fortress_services import collect_fortress_services
from plaintop_build import (
    build_cpu_pane,
    build_disk_pane,
    build_gpu_pane,
    build_mem_pane,
    build_net_pane,
    build_power_pane,
    build_process_rows,
)
from plaintop_graphs import MetricHistory
from plaintop_widgets import ChartPane, FooterBar, HeaderBar, ProcessPane, ServicesPane
from verdicts import Verdict, overall_verdict

REFRESH_SEC = 1.5
TUI = True
PROCESS_LIMIT = 12
_FORTRESS_HOME = os.path.expanduser(os.environ.get("FORTRESS_HOME", "~/fortress"))
FORTRESS = os.path.join(_FORTRESS_HOME, "control", "fortress")


class PlainTopApp(App):
    """Full-screen 1080p dashboard with live graphs."""

    TITLE = "PlainTop"
    CSS = """
    Screen {
        layout: vertical;
        background: $background;
    }

    #main-grid {
        height: 1fr;
        layout: vertical;
    }

    #row-top {
        height: 2fr;
        min-height: 14;
        layout: horizontal;
    }

    #row-mid {
        height: 1fr;
        min-height: 10;
        layout: horizontal;
    }

    #row-bottom {
        height: 2fr;
        min-height: 14;
        layout: horizontal;
    }

    #pane-disk {
        width: 2fr;
    }

    #pane-procs {
        width: 3fr;
    }

    #pane-services {
        width: 2fr;
    }

    ChartPane, ProcessPane, ServicesPane {
        height: 1fr;
        width: 1fr;
    }
    """

    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("Q", "quit", "Quit"),
        Binding("r", "refresh", "Refresh"),
        Binding("s", "open_fortress", "Services"),
        Binding("?", "toggle_help", "Help"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self._net_sampler = NetworkSampler()
        self._history = MetricHistory(maxlen=48)
        self._help_visible = False
        self._first_sample = True

    def compose(self) -> ComposeResult:
        yield HeaderBar(id="header")
        with Vertical(id="main-grid"):
            with Horizontal(id="row-top"):
                yield ChartPane("Processor (CPU)", id="pane-cpu")
                yield ChartPane("Memory (RAM)", id="pane-mem")
                yield ChartPane("Graphics (GPU)", id="pane-gpu")
            with Horizontal(id="row-mid"):
                yield ChartPane("Storage (disk)", id="pane-disk")
                yield ChartPane("Network", id="pane-net")
                yield ChartPane("Power", id="pane-power")
            with Horizontal(id="row-bottom"):
                yield ProcessPane(id="pane-procs")
                yield ServicesPane(id="pane-services")
        yield FooterBar(id="footer")

    def on_mount(self) -> None:
        self.set_interval(REFRESH_SEC, self._do_refresh)
        if self.size.height < 40:
            self.notify(
                "Maximize this terminal window for the full 1080p dashboard.",
                timeout=5,
            )
        self._do_refresh()

    def action_toggle_help(self) -> None:
        self._help_visible = not self._help_visible
        self.query_one("#footer", FooterBar).set_help_mode(self._help_visible)

    def action_refresh(self) -> None:
        self._do_refresh()

    def action_open_fortress(self) -> None:
        """Suspend TUI and open Fortress Control menu."""
        with self.suspend():
            try:
                subprocess.call([FORTRESS, "menu"])
            except Exception as e:
                print(f"Could not open fortress menu: {e}")
        self._do_refresh()

    def _do_refresh(self) -> None:
        cpu_iv = 0.1 if self._first_sample else 0.0
        snap = collect_snapshot(
            cpu_interval=cpu_iv,
            process_limit=PROCESS_LIMIT,
            network_sampler=self._net_sampler,
        )
        self._first_sample = False
        self._history.push(snap)

        cols = max(100, self.size.width or 120)
        svc = collect_fortress_services()
        header = overall_verdict(snap, tui=TUI)
        if svc:
            header = Verdict(
                status=header.status,
                headline=header.headline,
                detail=f"{header.detail}  ·  Fortress {svc.on}/{svc.total} up",
                bar_fraction=header.bar_fraction,
                bar_line=header.bar_line,
            )
        self.query_one("#header", HeaderBar).update_verdict(header)

        for pane_id, builder in (
            ("#pane-cpu", build_cpu_pane),
            ("#pane-mem", build_mem_pane),
            ("#pane-gpu", build_gpu_pane),
        ):
            v, charts, extra = builder(snap, self._history, cols, tui=TUI)
            self.query_one(pane_id, ChartPane).update_content(v, charts, extra)

        v, charts, extra = build_disk_pane(snap, cols, tui=TUI)
        self.query_one("#pane-disk", ChartPane).update_content(v, charts, extra)

        v, charts, extra = build_net_pane(snap, self._history, cols, tui=TUI)
        self.query_one("#pane-net", ChartPane).update_content(v, charts, extra)

        v, charts, extra = build_power_pane(snap, self._history, cols, tui=TUI)
        self.query_one("#pane-power", ChartPane).update_content(v, charts, extra)

        rows = build_process_rows(snap, bar_width=max(14, cols // 7))
        self.query_one("#pane-procs", ProcessPane).update_processes(rows)

        sp = self.query_one("#pane-services", ServicesPane)
        if svc:
            sp.update_services(
                svc.on,
                svc.total,
                svc.ai_label,
                [(r.name, r.running, r.gpu) for r in svc.rows],
                ghosts=svc.ghosts,
            )
        else:
            sp.update_services(0, 0, "control offline", [])


def main() -> None:
    PlainTopApp().run()


if __name__ == "__main__":
    main()
