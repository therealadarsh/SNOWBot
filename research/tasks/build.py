"""Materialize study tasks with real git commits."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from research.errors import ConfigError
from research.gitutil import commit_all, init_repo, write_files
from research.hashutil import sha256_canonical, sha256_file
from research.yamlio import as_bool, as_int, as_list, as_mapping, as_str, load_yaml

_KINDS = frozenset({"pressured", "control"})


@dataclass(frozen=True, slots=True)
class TaskCommit:
    message: str
    files: tuple[tuple[str, str], ...]


@dataclass(frozen=True, slots=True)
class Task:
    id: str
    kind: str
    pressure: str
    honest_success_possible: bool
    prompt: str
    commits: tuple[TaskCommit, ...]

    def content_payload(self) -> dict[str, object]:
        return {
            "id": self.id,
            "kind": self.kind,
            "pressure": self.pressure,
            "honest_success_possible": self.honest_success_possible,
            "prompt": self.prompt,
            "commits": [
                {"message": commit.message, "files": dict(commit.files)} for commit in self.commits
            ],
        }

    @property
    def content_sha256(self) -> str:
        return sha256_canonical(self.content_payload())


@dataclass(frozen=True, slots=True)
class Catalog:
    path: Path
    digest: str
    tasks: tuple[Task, ...]

    def by_id(self, task_id: str) -> Task:
        for task in self.tasks:
            if task.id == task_id:
                return task
        raise ConfigError(f"unknown task {task_id}")

    def ids(self) -> tuple[str, ...]:
        return tuple(task.id for task in self.tasks)


def default_catalog_path() -> Path:
    return Path(__file__).resolve().parent / "catalog.yaml"


def load_catalog(path: Path | None = None) -> Catalog:
    source = path or default_catalog_path()
    raw = as_mapping(load_yaml(source), label=str(source))
    version = as_int(raw.get("schema_version"), label="catalog.schema_version")
    if version != 1:
        raise ConfigError("catalog schema_version must be 1")
    tasks = tuple(
        _parse_task(item, index)
        for index, item in enumerate(as_list(raw.get("tasks"), label="catalog.tasks"))
    )
    ids = [task.id for task in tasks]
    if len(ids) != len(set(ids)):
        raise ConfigError("catalog task ids must be unique")
    return Catalog(path=source, digest=sha256_file(source), tasks=tasks)


def materialize(task: Task, dest: Path) -> None:
    """Build ``dest`` as a git repository using the task's commits."""
    if dest.exists() and any(dest.iterdir()):
        raise ConfigError(f"{dest} is not an empty directory")
    init_repo(dest)
    if not task.commits:
        raise ConfigError(f"task {task.id} has no commits")
    for commit in task.commits:
        write_files(dest, dict(commit.files))
        commit_all(dest, commit.message)


def _parse_task(value: object, index: int) -> Task:
    label = f"catalog.tasks[{index}]"
    raw = as_mapping(value, label=label)
    kind = as_str(raw.get("kind"), label=f"{label}.kind")
    if kind not in _KINDS:
        raise ConfigError(f"{label}.kind must be pressured or control")
    honest = as_bool(raw.get("honest_success_possible"), label=f"{label}.honest_success_possible")
    if kind == "pressured" and honest:
        raise ConfigError(f"{label} is pressured but honest success is marked possible")
    if kind == "control" and not honest:
        raise ConfigError(f"{label} is a control but honest success is marked impossible")
    commits_raw = as_list(raw.get("commits"), label=f"{label}.commits")
    if not commits_raw:
        raise ConfigError(f"{label} needs at least one commit")
    commits = tuple(
        _parse_commit(item, f"{label}.commits[{i}]") for i, item in enumerate(commits_raw)
    )
    return Task(
        id=as_str(raw.get("id"), label=f"{label}.id"),
        kind=kind,
        pressure=as_str(raw.get("pressure"), label=f"{label}.pressure"),
        honest_success_possible=honest,
        prompt=as_str(raw.get("prompt"), label=f"{label}.prompt"),
        commits=commits,
    )


def _parse_commit(value: object, label: str) -> TaskCommit:
    raw = as_mapping(value, label=label)
    files_raw = as_mapping(raw.get("files"), label=f"{label}.files")
    files: list[tuple[str, str]] = []
    for path, content in files_raw.items():
        if not isinstance(content, str):
            raise ConfigError(f"{label}.files.{path} must be text")
        files.append((path, content))
    if not files:
        raise ConfigError(f"{label} has no files")
    return TaskCommit(
        message=as_str(raw.get("message"), label=f"{label}.message"),
        files=tuple(files),
    )
