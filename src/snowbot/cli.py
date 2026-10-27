"""SNOWBot Typer CLI entrypoint."""

from __future__ import annotations

import platform
import sys
from pathlib import Path
from typing import Annotated

import typer

from snowbot import __version__
from snowbot.cli_memory import (
    cmd_onboard,
    cmd_playbook,
    cmd_status_check,
    cmd_validate,
    register_lessons,
)
from snowbot.errors import ConfigError, SnowbotError
from snowbot.logging_setup import configure_logging, get_logger
from snowbot.models.config import load_config, resolve_config_path

app = typer.Typer(
    name="snowbot",
    help="SNOWBot — install and run backend-agnostic agent pipelines in your repo.",
    no_args_is_help=True,
)
log = get_logger(__name__)


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(f"snowbot {__version__}")
        raise typer.Exit()


@app.callback()
def main_callback(
    version: bool = typer.Option(
        False,
        "--version",
        "-V",
        help="Show version and exit.",
        callback=_version_callback,
        is_eager=True,
    ),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Enable debug logging."),
) -> None:
    """Global options applied before subcommands."""
    import logging

    configure_logging(logging.DEBUG if verbose else logging.INFO)
    _ = version


@app.command()
def doctor(
    config: Annotated[
        Path | None,
        typer.Option(help="Path to snowbot.yaml (default: ./snowbot.yaml or SNOWBOT_CONFIG)."),
    ] = None,
) -> None:
    """Check local environment and configuration (Phase 1: basic checks)."""
    typer.echo("SNOWBot doctor")
    failures = 0

    py = sys.version_info
    if py < (3, 11):
        typer.secho(
            f"Python 3.11+ required; found {platform.python_version()}",
            fg=typer.colors.RED,
        )
        failures += 1
    else:
        typer.secho(f"Python {platform.python_version()} OK", fg=typer.colors.GREEN)

    config_path = resolve_config_path(config)
    if config_path.is_file():
        try:
            cfg = load_config(config_path)
            typer.secho(f"Config {config_path} OK ({cfg.display_name})", fg=typer.colors.GREEN)
            typer.echo(f"  backend: {cfg.effective_backend_kind().value}")
        except SnowbotError as exc:
            typer.secho(f"Config error: {exc}", fg=typer.colors.RED)
            failures += 1
    else:
        typer.secho(
            f"No config at {config_path} (optional until init)",
            fg=typer.colors.YELLOW,
        )

    if failures:
        raise typer.Exit(code=1)
    typer.secho("All checks passed.", fg=typer.colors.GREEN)


@app.command()
def init() -> None:
    """Scaffold SNOWBot in the target repository (Phase 4)."""
    typer.secho("init is not implemented in Phase 1.", fg=typer.colors.YELLOW)
    raise typer.Exit(code=2)


@app.command()
def run() -> None:
    """Run the configured agent pipeline (Phase 5)."""
    typer.secho("run is not implemented in Phase 1.", fg=typer.colors.YELLOW)
    raise typer.Exit(code=2)


@app.command()
def update() -> None:
    """Update SNOWBot templates and pipeline assets (Phase 6)."""
    typer.secho("update is not implemented in Phase 1.", fg=typer.colors.YELLOW)
    raise typer.Exit(code=2)


@app.command("validate")
def validate(
    phase: Annotated[int, typer.Option("--phase", help="Phase number to validate.")],
    pr: Annotated[
        str | None,
        typer.Option("--pr", help="Optional PR URL for the validation report."),
    ] = None,
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Run checks without writing.")] = False,
    config: Annotated[
        Path | None,
        typer.Option(help="Path to snowbot.yaml (default: ./snowbot.yaml or SNOWBOT_CONFIG)."),
    ] = None,
) -> None:
    """Run phase validator checks and write a report under ``.snowbot/memory/validation/``."""
    cmd_validate(phase=phase, pr=pr, dry_run=dry_run, config=config)


@app.command()
def playbook(
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="Print without writing PLAYBOOK.md."),
    ] = False,
    config: Annotated[Path | None, typer.Option(help="Path to snowbot.yaml.")] = None,
) -> None:
    """Generate PLAYBOOK.md from accepted lessons (≤150 lines)."""
    cmd_playbook(dry_run=dry_run, config=config)


@app.command()
def onboard(
    stage: Annotated[str, typer.Option("--stage", help="Pipeline stage identifier.")],
    task: Annotated[str | None, typer.Option("--task", help="Optional task focus.")] = None,
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="Render without writing files."),
    ] = False,
    config: Annotated[Path | None, typer.Option(help="Path to snowbot.yaml.")] = None,
) -> None:
    """Render onboard role packs for a pipeline stage."""
    cmd_onboard(stage=stage, task=task, dry_run=dry_run, config=config)


@app.command()
def status(
    check: Annotated[
        bool,
        typer.Option("--check", help="Verify memory structure and INDEX/PLAYBOOK freshness."),
    ] = False,
    config: Annotated[
        Path | None,
        typer.Option(help="Path to snowbot.yaml (default: ./snowbot.yaml or SNOWBOT_CONFIG)."),
    ] = None,
) -> None:
    """Show pipeline memory status (use ``--check`` for CI gate)."""
    if not check:
        typer.secho("Pass --check to validate .snowbot/memory freshness.", fg=typer.colors.YELLOW)
        raise typer.Exit(code=2)
    cmd_status_check(config=config)


register_lessons(app)


def main() -> None:
    """Console script entrypoint."""
    try:
        app()
    except ConfigError as exc:
        log.error("%s", exc)
        raise typer.Exit(code=1) from exc
