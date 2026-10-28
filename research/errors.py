"""Errors raised by the research harness."""

from __future__ import annotations


class ResearchError(Exception):
    """Base error for the research harness."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class ConfigError(ResearchError):
    """Invalid harness configuration."""


class HashMismatch(ResearchError):
    """A frozen file does not match its pinned digest."""


class GitError(ResearchError):
    """A git command failed while building or scoring a workspace."""


class BudgetError(ResearchError):
    """A cell or study exceeded its dollar cap."""


class ProviderCallsDisabled(ResearchError):
    """This build does not call model providers."""


class LiveAgentDisabled(ResearchError):
    """The requested agent CLI would call a provider and is not executed here."""


class ImmutableRecordError(ResearchError):
    """A run record already exists and cannot be replaced."""


class DockerUnavailable(ResearchError):
    """Docker is not available, so a container sandbox cannot be started."""


class TurnLimitExceeded(ResearchError):
    """The cell used more tool turns than its limit."""


class CellTimeout(ResearchError):
    """A sandbox command exceeded the cell wall clock."""


class ExtensionNotInThisPullRequest(ResearchError):
    """Named extension point reserved for a later pull request."""
