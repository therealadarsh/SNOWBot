"""Filesystem-backed lesson CRUD with dedupe and index maintenance."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import yaml

from snowbot.errors import SnowbotError
from snowbot.lessons.evidence import unresolved_evidence_refs
from snowbot.lessons.models import Lesson, LessonIndex, LessonIndexEntry, LessonStatus
from snowbot.memory.layout import MemoryLayout


class LessonStoreError(SnowbotError):
    """Lesson persistence failures."""


class LessonStore:
    """Read/write lessons under ``lessons/proposed`` and ``lessons/accepted``."""

    def __init__(self, layout: MemoryLayout) -> None:
        self._layout = layout
        self._layout.ensure_structure()

    def list_lessons(self, *, status: LessonStatus | None = None) -> list[Lesson]:
        lessons: list[Lesson] = []
        seen: set[Path] = set()
        # Proposed and retired lessons share one directory. Scanning that
        # directory once per status listed every file twice in INDEX.yaml.
        for directory in self._directories_for_list(status):
            if not directory.is_dir():
                continue
            for path in sorted(directory.glob("*.yaml")):
                resolved = path.resolve()
                if resolved in seen:
                    continue
                seen.add(resolved)
                lesson = self._load_file(path)
                if status is not None and lesson.status != status:
                    continue
                lessons.append(lesson)
        return sorted(lessons, key=lambda item: item.created_at)

    def get(self, lesson_id: str) -> Lesson:
        path = self._find_path(lesson_id)
        if path is None:
            msg = f"Lesson not found: {lesson_id}"
            raise LessonStoreError(msg, code="lesson_not_found")
        return self._load_file(path)

    def add_proposed(self, lesson: Lesson, *, dry_run: bool = False) -> Lesson:
        if lesson.status != LessonStatus.PROPOSED:
            msg = "add_proposed requires status=proposed"
            raise LessonStoreError(msg)
        existing = self._find_by_dedupe(lesson.effective_dedupe_key())
        if existing is not None and existing.status != LessonStatus.RETIRED:
            msg = f"Duplicate lesson dedupe_key={lesson.effective_dedupe_key()!r} ({existing.id})"
            raise LessonStoreError(msg, code="lesson_duplicate")
        if dry_run:
            return lesson
        path = self._layout.lessons_proposed / f"{lesson.id}.yaml"
        self._write(path, lesson)
        self._rebuild_index()
        return lesson

    def accept(self, lesson_id: str, *, dry_run: bool = False) -> Lesson:
        lesson = self.get(lesson_id)
        missing = unresolved_evidence_refs(self._layout, lesson)
        if missing:
            msg = "Evidence does not resolve: " + ", ".join(missing)
            raise LessonStoreError(msg, code="evidence_unresolved", details={"refs": missing})
        if lesson.status == LessonStatus.ACCEPTED:
            return lesson
        lesson.status = LessonStatus.ACCEPTED
        lesson.updated_at = datetime.now(tz=UTC).isoformat()
        if dry_run:
            return lesson
        self._delete_if_exists(self._path_for(lesson_id))
        dest = self._layout.lessons_accepted / f"{lesson.id}.yaml"
        self._write(dest, lesson)
        self._rebuild_index()
        return lesson

    def retire(self, lesson_id: str, *, dry_run: bool = False) -> Lesson:
        lesson = self.get(lesson_id)
        lesson.status = LessonStatus.RETIRED
        lesson.updated_at = datetime.now(tz=UTC).isoformat()
        if dry_run:
            return lesson
        self._delete_if_exists(self._path_for(lesson_id))
        dest = self._layout.lessons_proposed / f"{lesson.id}.yaml"
        self._write(dest, lesson)
        self._rebuild_index()
        return lesson

    def _rebuild_index(self) -> None:
        entries: list[LessonIndexEntry] = []
        for lesson in self.list_lessons():
            path = self._path_for(lesson.id)
            rel = self._relative_display_path(path) if path else ""
            entries.append(
                LessonIndexEntry(
                    id=lesson.id,
                    status=lesson.status,
                    dedupe_key=lesson.effective_dedupe_key(),
                    path=rel,
                )
            )
        index = LessonIndex(lessons=entries)
        payload = index.model_dump(mode="json")
        self._layout.lessons_index.write_text(
            yaml.safe_dump(payload, sort_keys=False),
            encoding="utf-8",
        )
        self._layout.touch_index_updated()

    def _directories_for_list(self, status: LessonStatus | None) -> list[Path]:
        directories: list[Path] = []
        if status is None or status is LessonStatus.ACCEPTED:
            directories.append(self._layout.lessons_accepted)
        if status is None or status in (LessonStatus.PROPOSED, LessonStatus.RETIRED):
            directories.append(self._layout.lessons_proposed)
        return directories

    def _path_for(self, lesson_id: str) -> Path | None:
        return self._find_path(lesson_id)

    def _relative_display_path(self, path: Path) -> str:
        resolved = path.resolve()
        for base in (self._layout.root, self._layout.memory_dir):
            try:
                return resolved.relative_to(base.resolve()).as_posix()
            except ValueError:
                continue
        return resolved.as_posix()

    def _find_path(self, lesson_id: str) -> Path | None:
        directories = (self._layout.lessons_proposed, self._layout.lessons_accepted)
        for directory in directories:
            candidate = directory / f"{lesson_id}.yaml"
            if candidate.is_file():
                return candidate
        for directory in directories:
            if not directory.is_dir():
                continue
            for path in sorted(directory.glob("*.yaml")):
                if self._peek_id(path) == lesson_id:
                    return path
        return None

    def _peek_id(self, path: Path) -> str | None:
        try:
            raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except (OSError, yaml.YAMLError):
            return None
        if isinstance(raw, dict):
            lesson_id = raw.get("id")
            if isinstance(lesson_id, str):
                return lesson_id
        return None

    def _find_by_dedupe(self, dedupe_key: str) -> Lesson | None:
        for lesson in self.list_lessons():
            same_key = lesson.effective_dedupe_key() == dedupe_key
            if same_key and lesson.status != LessonStatus.RETIRED:
                return lesson
        return None

    def _load_file(self, path: Path) -> Lesson:
        try:
            raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError as exc:
            msg = f"Corrupted lesson YAML: {path}"
            raise LessonStoreError(msg, details={"path": str(path)}) from exc
        if not isinstance(raw, dict):
            msg = f"Lesson file must be a mapping: {path}"
            raise LessonStoreError(msg, details={"path": str(path)})
        try:
            return Lesson.model_validate(raw)
        except Exception as exc:
            msg = f"Invalid lesson schema: {path}"
            raise LessonStoreError(msg, details={"path": str(path)}) from exc

    def _write(self, path: Path, lesson: Lesson) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            yaml.safe_dump(lesson.model_dump_yaml_dict(), sort_keys=False),
            encoding="utf-8",
        )

    def _delete_if_exists(self, path: Path | None) -> None:
        if path is not None and path.is_file():
            path.unlink()
