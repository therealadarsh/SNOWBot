"""CLI handlers for validate, lessons, playbook, onboard, and status."""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Annotated

import typer
import yaml

from snowbot.lessons.digest import generate_playbook
from snowbot.lessons.models import Lesson, LessonEvidence, LessonStatus
from snowbot.lessons.promote import promote_lesson
from snowbot.lessons.store import LessonStore, LessonStoreError
from snowbot.memory.layout import MemoryLayout
from snowbot.memory.stops import StopKind, capture_stop_event
from snowbot.models.config import load_config, resolve_config_path
from snowbot.pipeline.hooks import StageHooks
from snowbot.status_check import run_status_check
from snowbot.validator.runner import run_phase_validation

lesson_app = typer.Typer(help="Manage proposed and accepted lessons.")


def _layout_from_cwd(config_path: Path | None) -> MemoryLayout:
    path = resolve_config_path(config_path)
    memory_dir: Path | None = None
    root = Path.cwd()
    if path.is_file():
        cfg = load_config(path)
        root = cfg.project.root
        memory_dir = cfg.project.memory_dir
    return MemoryLayout.from_project_root(root, memory_dir)


def cmd_status_check(
    config: Annotated[
        Path | None,
        typer.Option(help="Path to snowbot.yaml"),
    ] = None,
) -> None:
    """Verify memory structure and INDEX/PLAYBOOK freshness."""
    layout = _layout_from_cwd(config)
    report = run_status_check(layout)
    for issue in report.issues:
        color = typer.colors.RED if issue.severity == "error" else typer.colors.YELLOW
        typer.secho(f"[{issue.code}] {issue.message}", fg=color)
    if not report.ok:
        raise typer.Exit(code=1)
    typer.secho("Memory status OK.", fg=typer.colors.GREEN)


def cmd_validate(
    phase: Annotated[str, typer.Option("--phase", help="Phase id (e.g. 1, 1b, 2).")],
    pr: Annotated[str | None, typer.Option("--pr", help="Optional PR URL for the report.")] = None,
    base_ref: Annotated[
        str | None,
        typer.Option(
            "--base-ref",
            help="Git ref for anti-gaming diff (default: SNOWBOT_VALIDATE_BASE env).",
        ),
    ] = None,
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Run checks without writing.")] = False,
    config: Annotated[Path | None, typer.Option(help="Path to snowbot.yaml")] = None,
) -> None:
    layout = _layout_from_cwd(config)
    try:
        result = run_phase_validation(
            layout,
            phase,
            pr_url=pr,
            dry_run=dry_run,
            base_ref=base_ref,
        )
    except ValueError as exc:
        typer.secho(str(exc), fg=typer.colors.RED)
        raise typer.Exit(code=1) from exc

    for outcome in result.outcomes:
        color = typer.colors.GREEN if outcome.passed else typer.colors.RED
        label = "pass" if outcome.passed else "FAIL"
        typer.secho(f"[{label}] {outcome.spec.id}: {outcome.message}", fg=color)
    if not result.passed:
        raise typer.Exit(code=1)
    typer.secho(f"Phase {phase} validation passed.", fg=typer.colors.GREEN)


def cmd_playbook(
    dry_run: Annotated[bool, typer.Option("--dry-run")] = False,
    config: Annotated[Path | None, typer.Option(help="Path to snowbot.yaml")] = None,
) -> None:
    layout = _layout_from_cwd(config)
    content = generate_playbook(layout, dry_run=dry_run)
    if dry_run:
        typer.echo(content)
    else:
        typer.secho(f"Wrote {layout.playbook}", fg=typer.colors.GREEN)


def cmd_onboard(
    stage: Annotated[str, typer.Option("--stage", help="Pipeline stage id.")],
    task: Annotated[str | None, typer.Option("--task", help="Optional task description.")] = None,
    dry_run: Annotated[bool, typer.Option("--dry-run")] = False,
    config: Annotated[Path | None, typer.Option(help="Path to snowbot.yaml")] = None,
) -> None:
    layout = _layout_from_cwd(config)
    hooks = StageHooks(layout)
    content = hooks.at_stage_start(stage, task=task, dry_run=dry_run)
    if dry_run:
        typer.echo(content)
    else:
        onboard = layout.memory_dir / "onboard"
        typer.secho(f"Onboard pack written under {onboard}", fg=typer.colors.GREEN)


@lesson_app.command("add")
def lesson_add(
    title: Annotated[str, typer.Option("--title", prompt=True)],
    body: Annotated[str, typer.Option("--body", prompt=True)],
    evidence_ref: Annotated[
        str,
        typer.Option("--evidence-ref", help="Path, URL, or PR reference."),
    ],
    evidence_summary: Annotated[str, typer.Option("--evidence-summary")] = "",
    dedupe_key: Annotated[str, typer.Option("--dedupe-key")] = "",
    dry_run: Annotated[bool, typer.Option("--dry-run")] = False,
    config: Annotated[Path | None, typer.Option(help="Path to snowbot.yaml")] = None,
) -> None:
    layout = _layout_from_cwd(config)
    lesson = Lesson(
        id=str(uuid.uuid4())[:8],
        title=title,
        body=body,
        status=LessonStatus.PROPOSED,
        evidence=[LessonEvidence(ref=evidence_ref, summary=evidence_summary)],
        dedupe_key=dedupe_key,
    )
    store = LessonStore(layout)
    try:
        store.add_proposed(lesson, dry_run=dry_run)
    except LessonStoreError as exc:
        typer.secho(str(exc), fg=typer.colors.RED)
        raise typer.Exit(code=1) from exc
    if not dry_run:
        capture_stop_event(
            layout,
            StopKind.HUMAN_LESSON_ADD,
            detail=f"Lesson proposed: {lesson.id}",
            metadata={"lesson_id": lesson.id},
        )
    typer.secho(f"Lesson {lesson.id} recorded as proposed.", fg=typer.colors.GREEN)


@lesson_app.command("list")
def lesson_list(
    config: Annotated[Path | None, typer.Option(help="Path to snowbot.yaml")] = None,
) -> None:
    layout = _layout_from_cwd(config)
    store = LessonStore(layout)
    for lesson in store.list_lessons():
        typer.echo(f"{lesson.id}\t{lesson.status.value}\t{lesson.title}")


@lesson_app.command("show")
def lesson_show(
    lesson_id: Annotated[str, typer.Argument(help="Lesson id.")],
    config: Annotated[Path | None, typer.Option(help="Path to snowbot.yaml")] = None,
) -> None:
    layout = _layout_from_cwd(config)
    store = LessonStore(layout)
    try:
        lesson = store.get(lesson_id)
    except LessonStoreError as exc:
        typer.secho(str(exc), fg=typer.colors.RED)
        raise typer.Exit(code=1) from exc
    typer.echo(yaml.safe_dump(lesson.model_dump(mode="json"), sort_keys=False))


@lesson_app.command("accept")
def lesson_accept(
    lesson_id: Annotated[str, typer.Argument()],
    dry_run: Annotated[bool, typer.Option("--dry-run")] = False,
    config: Annotated[Path | None, typer.Option(help="Path to snowbot.yaml")] = None,
) -> None:
    layout = _layout_from_cwd(config)
    store = LessonStore(layout)
    try:
        store.accept(lesson_id, dry_run=dry_run)
    except LessonStoreError as exc:
        typer.secho(str(exc), fg=typer.colors.RED)
        raise typer.Exit(code=1) from exc
    typer.secho(f"Accepted {lesson_id}", fg=typer.colors.GREEN)


@lesson_app.command("retire")
def lesson_retire(
    lesson_id: Annotated[str, typer.Argument()],
    dry_run: Annotated[bool, typer.Option("--dry-run")] = False,
    config: Annotated[Path | None, typer.Option(help="Path to snowbot.yaml")] = None,
) -> None:
    layout = _layout_from_cwd(config)
    store = LessonStore(layout)
    store.retire(lesson_id, dry_run=dry_run)
    typer.secho(f"Retired {lesson_id}", fg=typer.colors.GREEN)


@lesson_app.command("promote")
def lesson_promote(
    lesson_id: Annotated[str, typer.Argument()],
    dry_run: Annotated[bool, typer.Option("--dry-run")] = False,
    config: Annotated[Path | None, typer.Option(help="Path to snowbot.yaml")] = None,
) -> None:
    layout = _layout_from_cwd(config)
    try:
        promote_lesson(layout, lesson_id, dry_run=dry_run)
    except LessonStoreError as exc:
        typer.secho(str(exc), fg=typer.colors.RED)
        raise typer.Exit(code=1) from exc
    typer.secho(f"Promoted {lesson_id}", fg=typer.colors.GREEN)


def register_lessons(app: typer.Typer) -> None:
    app.add_typer(lesson_app, name="lesson")
