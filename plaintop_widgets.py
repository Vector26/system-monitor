"""Textual widgets for PlainTop — fills 1080p with charts and tables."""

from __future__ import annotations

from textual.widgets import Static

from verdicts import Verdict, status_label, status_style


class ChartPane(Static):
    """Metric pane with verdict, sparkline area, and extra lines."""

    DEFAULT_CSS = """
    ChartPane {
        border: solid $primary;
        padding: 0 1;
        height: 1fr;
        width: 1fr;
        overflow: hidden;
    }
    """

    def __init__(self, title: str, **kwargs) -> None:
        super().__init__(**kwargs)
        self.pane_title = title

    def update_content(
        self,
        verdict: Verdict,
        chart_lines: list[str] | None = None,
        extra_lines: list[str] | None = None,
    ) -> None:
        style = status_style(verdict.status)
        lines = [
            f"[bold]{self.pane_title}[/]  [{style}]{status_label(verdict.status)}[/]",
            f"[bold]{verdict.headline}[/]",
            verdict.detail,
        ]
        if chart_lines:
            lines.append("")
            for cl in chart_lines:
                lines.append(f"[cyan]{cl}[/]")
        if verdict.bar_line:
            lines.append(f"[green]{verdict.bar_line}[/]  [dim]usage bar[/]")
        if extra_lines:
            lines.append("")
            lines.extend(extra_lines)
        self.update("\n".join(lines))


class HeaderBar(Static):
    DEFAULT_CSS = """
    HeaderBar {
        dock: top;
        height: 2;
        padding: 0 1;
        border: heavy $accent;
        background: $surface;
    }
    """

    def update_verdict(self, verdict: Verdict) -> None:
        style = status_style(verdict.status)
        self.update(f"[{style}]{verdict.headline}[/]  [dim]{verdict.detail}[/]")


class ProcessPane(Static):
    DEFAULT_CSS = """
    ProcessPane {
        border: solid $primary;
        padding: 0 1;
        height: 1fr;
        width: 1fr;
    }
    """

    def update_processes(self, rows: list[tuple[str, str, str, str]]) -> None:
        lines = [
            "[bold]Processes[/]  "
            "[dim]PID     NAME            CPU        RAM       BAR[/]"
        ]
        if not rows:
            lines.append("  (no data)")
        else:
            for pid, name, cpu_s, mem_s, bar in rows:
                lines.append(
                    f"  [dim]{pid:>6}[/] [cyan]{name:16}[/] {cpu_s:>10} {mem_s:>8}  [green]{bar}[/]"
                )
        self.update("\n".join(lines))


class FooterBar(Static):
    DEFAULT_CSS = """
    FooterBar {
        dock: bottom;
        height: 1;
        background: $panel;
        color: $text-muted;
        padding: 0 1;
    }
    """

    def __init__(self, **kwargs) -> None:
        super().__init__("q quit  |  r refresh  |  s services  |  ? help", **kwargs)

    def set_help_mode(self, on: bool) -> None:
        if on:
            self.update(
                "PlainTop — live host metrics + Fortress services. "
                "s opens fortress menu (start/stop stacks).  ? hide"
            )
        else:
            self.update("q quit  |  r refresh  |  s services  |  ? help")


class ServicesPane(Static):
    """Whole Fortress stacks ON/OFF (not individual containers)."""

    DEFAULT_CSS = """
    ServicesPane {
        border: solid $primary;
        padding: 0 1;
        height: 1fr;
        width: 1fr;
        overflow: hidden;
    }
    """

    def update_services(self, on: int, total: int, ai_label: str, rows: list[tuple[str, bool, bool]], ghosts: list[dict] | None = None) -> None:
        lines = [
            f"[bold]Fortress services[/]  [cyan]{on}/{total} up[/]",
            f"[dim]AI:[/] {ai_label}",
            "[dim]press s = manage[/]",
            "",
        ]
        if ghosts:
            lines.append(f"[red bold]⚠ {len(ghosts)} GHOST STACK(S) RUNNING[/]")
            for g in ghosts:
                containers = ", ".join(g.get("ghost_containers", [])[:3])
                lines.append(f"  [red]{g.get('service_name')}:[/] {containers}")
            lines.append("")
        if not rows:
            lines.append("  (control not installed)")
        else:
            for name, running, gpu in rows:
                mark = "[green]ON [/]" if running else "[dim]off[/]"
                g = " [yellow]GPU[/]" if gpu else ""
                lines.append(f"  {mark} {name}{g}")
        self.update("\n".join(lines))
