"""Move a superseded research version into the archive.

The git tag name ``research-v<version>`` is computed and printed. This module
does not create or push that tag. It refuses to run when the replacement
version is not on the named branch, and it never overwrites an existing archive.
"""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from research.errors import ArchiveRefused, GitError
from research.gitutil import run_git
from research.versioning import load_version, parse_semver, version_of


@dataclass(frozen=True, slots=True)
class ArchiveResult:
    tag: str
    destination: Path
    docs_destination: Path | None
    idempotent: bool


def tag_name(version: str) -> str:
    parse_semver(version)
    return f"research-v{version}"


def preserve_current_version(repo: Path) -> Path:
    """Copy ``versions/current`` to ``versions/<version>`` without overwriting."""
    source = repo / "research" / "versions" / "current"
    if not (source / "VERSION").is_file():
        raise ArchiveRefused("current version directory is missing")
    version = version_of(load_version(source / "VERSION"))
    dest = repo / "research" / "versions" / version
    if dest.exists():
        return dest
    shutil.copytree(source, dest)
    return dest


def archive_version(
    repo: Path,
    *,
    old_version: str,
    new_version: str,
    why: str,
    fix_pr: str,
    on: date | None = None,
    into: str = "HEAD",
) -> ArchiveResult:
    """Move the old version bundle and run data. Does not push a tag."""
    parse_semver(old_version)
    parse_semver(new_version)
    if parse_semver(new_version) <= parse_semver(old_version):
        raise ArchiveRefused("new version must be greater than the archived version")
    if not why.strip():
        raise ArchiveRefused("why outdated must be set")
    if not fix_pr.strip():
        raise ArchiveRefused("fix PR link must be set")
    if not _version_is_merged(repo, new_version, into):
        raise ArchiveRefused(f"{new_version} is not merged into {into}")
    source = repo / "research" / "versions" / old_version
    dest = repo / "research" / "archive" / old_version
    results = repo / "docs" / "research" / "results"
    docs_dest = repo / "docs" / "research" / "archive" / old_version
    if source.exists() and dest.exists():
        raise ArchiveRefused(f"{dest} already exists and will not be overwritten")
    if results.exists() and docs_dest.exists():
        raise ArchiveRefused(f"{docs_dest} already exists and will not be overwritten")
    tag = tag_name(old_version)
    if not source.exists():
        if _archive_complete(dest):
            moved_docs = docs_dest if docs_dest.exists() else None
            if results.exists():
                _move_results(results, docs_dest)
                moved_docs = docs_dest
            _print_tag(tag)
            return ArchiveResult(
                tag=tag,
                destination=dest,
                docs_destination=moved_docs,
                idempotent=True,
            )
        raise ArchiveRefused(f"nothing to archive for {old_version}")
    when = date.today() if on is None else on
    superseded = _superseded(
        old_version=old_version,
        new_version=new_version,
        why=why.strip(),
        fix_pr=fix_pr.strip(),
        when=when,
        tag=tag,
    )
    (source / "SUPERSEDED.md").write_text(superseded, encoding="utf-8")
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(source), str(dest))
    moved_docs = None
    if results.exists():
        _move_results(results, docs_dest)
        moved_docs = docs_dest
    _print_tag(tag)
    return ArchiveResult(
        tag=tag,
        destination=dest,
        docs_destination=moved_docs,
        idempotent=False,
    )


def _version_is_merged(repo: Path, new_version: str, into: str) -> bool:
    try:
        run_git(repo, ["rev-parse", "--verify", "--quiet", into])
        text = run_git(repo, ["show", f"{into}:research/versions/current/VERSION"])
    except GitError:
        return False
    try:
        loaded = json.loads(text)
    except json.JSONDecodeError:
        return False
    if not isinstance(loaded, dict):
        return False
    return loaded.get("version") == new_version


def _archive_complete(dest: Path) -> bool:
    return (dest / "VERSION").is_file() and (dest / "SUPERSEDED.md").is_file()


def _move_results(results: Path, docs_dest: Path) -> None:
    if docs_dest.exists():
        raise ArchiveRefused(f"{docs_dest} already exists and will not be overwritten")
    docs_dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(results), str(docs_dest))


def _print_tag(tag: str) -> None:
    print(f"git tag (not pushed): {tag}")


def _superseded(
    *,
    old_version: str,
    new_version: str,
    why: str,
    fix_pr: str,
    when: date,
    tag: str,
) -> str:
    return (
        f"# Superseded research version {old_version}\n"
        "\n"
        f"- Date: {when.isoformat()}\n"
        f"- Why outdated: {why}\n"
        f"- Fix PR: {fix_pr}\n"
        f"- New version: {new_version}\n"
        f"- Git tag (not pushed): {tag}\n"
    )
