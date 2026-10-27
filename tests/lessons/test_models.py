"""Lesson schema tests."""

from __future__ import annotations

import pytest

from snowbot.lessons.models import Lesson, LessonEvidence, LessonStatus


def test_lesson_requires_evidence() -> None:
    with pytest.raises(ValueError, match="evidence"):
        Lesson(id="x", title="t", body="b", status=LessonStatus.PROPOSED, evidence=[])


def test_dedupe_key_from_title() -> None:
    lesson = Lesson(
        id="1",
        title="Hello World",
        body="body",
        evidence=[LessonEvidence(ref="a")],
    )
    assert lesson.effective_dedupe_key() == "hello-world"


def test_redaction_on_body() -> None:
    lesson = Lesson(
        id="1",
        title="t",
        body="api_key=secret123",
        evidence=[LessonEvidence(ref="file")],
    )
    assert "[REDACTED]" in lesson.body
