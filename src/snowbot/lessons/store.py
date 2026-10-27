"""Filesystem-backed lesson CRUD with dedupe and index maintenance."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import yaml

from snowbot.errors import SnowbotError
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
        for st in (LessonStatus.PROPOSED, LessonStatus.ACCEPTED, LessonStatus.RETIRED):
            if status is not None and st != status:
                continue
            directory = self._dir_for_status(st)
            if not directory.is_dir():
                continue
            for path in sorted(directory.glob("*.yaml")):
                lessons.append(self._load_file(path))
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
            rel = path.relative_to(self._layout.root).as_posix() if path else ""
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

    def _dir_for_status(self, status: LessonStatus) -> Path:
        if status == LessonStatus.ACCEPTED:
            return self._layout.lessons_accepted
        return self._layout.lessons_proposed

    def _path_for(self, lesson_id: str) -> Path | None:
        return self._find_path(lesson_id)

    def _find_path(self, lesson_id: str) -> Path | None:
        for directory in (self._layout.lessons_proposed, self._layout.lessons_accepted):
            candidate = directory / f"{lesson_id}.yaml"
            if candidate.is_file():
                return candidate
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
