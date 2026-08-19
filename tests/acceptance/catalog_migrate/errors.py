"""Typed migration failures and their frozen process exit codes."""

from __future__ import annotations

import re
from collections.abc import Iterable
from typing import Any


class MigrationError(Exception):
    """Base class for a migration failure with a stable exit code."""

    exit_code = 2
    error_code = "invalid-input"

    @property
    def code(self) -> int:
        """Expose argparse-compatible numeric status for direct parser tests."""
        return self.exit_code


class InvalidInputError(MigrationError):
    """Report malformed arguments, documents, artifacts, or secret boundaries."""

    exit_code = 2
    error_code = "invalid-input"


class PreconditionError(MigrationError):
    """Report a safe precondition that prevents target mutation."""

    exit_code = 3
    error_code = "precondition-failed"


class ToolError(MigrationError):
    """Report a pinned external tool failure or timeout."""

    exit_code = 4
    error_code = "tool-failed"


class VerificationError(MigrationError):
    """Report target state that differs from the frozen contracts."""

    exit_code = 5
    error_code = "verification-failed"


def single_line_message(value: object) -> str:
    """Normalize an error into one bounded, non-empty protocol-safe line."""
    message = re.sub(r"\s+", " ", str(value)).strip()
    return (message or "migration command failed")[:1024]


def error_document(
    error: MigrationError,
    command: str | None,
    *,
    redactions: Iterable[str] = (),
) -> dict[str, Any]:
    """Build the exact typed migration failure document."""
    message = str(error)
    for value in redactions:
        if value:
            message = message.replace(value, "[REDACTED]")
    message = single_line_message(message)
    return {
        "schemaVersion": "1.0.0",
        "status": "failed",
        "command": command,
        "exitCode": error.exit_code,
        "error": {
            "code": error.error_code,
            "message": message,
        },
    }
