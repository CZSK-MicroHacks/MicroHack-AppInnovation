"""Typed migration failures and their frozen process exit codes."""


class MigrationError(Exception):
    """Base class for a migration failure with a stable exit code."""

    exit_code = 2


class InvalidInputError(MigrationError):
    """Report malformed arguments, documents, artifacts, or secret boundaries."""

    exit_code = 2


class PreconditionError(MigrationError):
    """Report a safe precondition that prevents target mutation."""

    exit_code = 3


class ToolError(MigrationError):
    """Report a pinned external tool failure or timeout."""

    exit_code = 4


class VerificationError(MigrationError):
    """Report target state that differs from the frozen contracts."""

    exit_code = 5
