"""Exit codes (build prompt §20) and the exception types that map onto them."""

from __future__ import annotations

from enum import IntEnum


class ExitCode(IntEnum):
    OK = 0
    FAILURE = 1
    USAGE = 2
    VERIFICATION_FAILED = 3
    SPEND_GUARD_REFUSED = 4
    CONFIG_INVALID = 5


class ReturnsManagerError(Exception):
    """Base class. `exit_code` tells the CLI how to exit when this escapes a command."""

    exit_code: ExitCode = ExitCode.FAILURE


class ConfigError(ReturnsManagerError):
    """Configuration is missing or invalid. The message never contains secret values."""

    exit_code = ExitCode.CONFIG_INVALID


class VerificationFailed(ReturnsManagerError):
    exit_code = ExitCode.VERIFICATION_FAILED


class SpendGuardRefused(ReturnsManagerError):
    exit_code = ExitCode.SPEND_GUARD_REFUSED


class NotFound(ReturnsManagerError):
    """The resource does not exist for this caller. Other orgs' resources are reported the same way (404)."""


class NotBuiltYet(ReturnsManagerError):
    """A command that exists in the CLI tree but whose phase has not been built yet."""

    exit_code = ExitCode.FAILURE

    def __init__(self, command: str, phase: str) -> None:
        super().__init__(f"`{command}` is not built yet (planned for phase {phase}).")
        self.command = command
        self.phase = phase
