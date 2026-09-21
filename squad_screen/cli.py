from __future__ import annotations

import asyncio
from pathlib import Path
import typer
from rich.console import Console
from rich.table import Table

from squad_screen.logging_setup import setup_logging
from squad_screen.pipeline import run_screen

app = typer.Typer(
    add_completion=False,
    help="Squad Screen — 72-hour lifestyle and readiness briefing for a football squad.",
    no_args_is_help=True,
)
console = Console()


def _print_summary(team: str, mode: str, md_path: Path, json_path: Path, report) -> None:
    console.rule(f"[bold]{report.team.name}[/bold] · {mode}")
    table = Table(show_header=True, header_style="bold")
    table.add_column("Section")
    table.add_column("Count", justify="right")
    table.add_row("Roster", str(len(report.roster)))
    table.add_row("Articles", str(len(report.articles)))
    table.add_row("Social", str(len(report.social_items)))
    table.add_row("Signals", str(len(report.signals)))
    table.add_row("Coverage gaps", str(len(report.coverage_gaps)))
    table.add_row("Starting XI", str(len(report.lineup.starting_xi)))
    console.print(table)
    console.print(report.lineup.summary)
    console.print(f"\nMarkdown: [green]{md_path}[/green]")
    console.print(f"JSON:     [green]{json_path}[/green]")


@app.command()
def demo(
    team: str = typer.Argument("Barcelona"),
    days: int = typer.Option(3, "--days", "-d", help="Lookback window in days."),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
) -> None:
    """Write a full report from bundled fixtures. No API keys, no network."""
    setup_logging(verbose)
    report, md_path, json_path = asyncio.run(
        run_screen(team, mode="demo", lookback_days=days)
    )
    _print_summary(team, "demo", md_path, json_path, report)


@app.command()
def screen(
    team: str = typer.Argument(..., help="Club name, e.g. Barcelona"),
    days: int = typer.Option(3, "--days", "-d"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
) -> None:
    """Live collection. Never invents articles or posts if sources are empty."""
    setup_logging(verbose)
    report, md_path, json_path = asyncio.run(
        run_screen(team, mode="live", lookback_days=days)
    )
    _print_summary(team, "live", md_path, json_path, report)


@app.command()
def serve(
    host: str = typer.Option("0.0.0.0", "--host"),
    port: int = typer.Option(43123, "--port"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
) -> None:
    """Local briefing UI."""
    setup_logging(verbose)
    import uvicorn

    uvicorn.run(
        "squad_screen.web.app:app",
        host=host,
        port=port,
        log_level="debug" if verbose else "info",
    )
