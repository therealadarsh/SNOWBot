"""Shared SNOWBot memory layout under ``.snowbot/memory/``."""

from snowbot.memory.layout import MemoryLayout
from snowbot.memory.stops import StopKind, capture_stop_event

__all__ = ["MemoryLayout", "StopKind", "capture_stop_event"]
