"""Safe subprocess execution for pinned migration tools."""

from __future__ import annotations

import os
import subprocess
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from catalog_migrate.errors import ToolError


@dataclass(frozen=True)
class ProcessResult:
    """Capture non-secret process output needed by a migration operation."""

    stdout: str
    stderr: str


class CommandRunner:
    """Execute an argument vector without a shell and map failures consistently."""

    _SENSITIVE_ENVIRONMENT_MARKERS = ("PASSWORD", "SECRET", "TOKEN")

    def run(
        self,
        argv: Sequence[str],
        *,
        environment: Mapping[str, str] | None = None,
        input_text: str | None = None,
        timeout: int = 300,
    ) -> ProcessResult:
        """Run one child process.

        Args:
            argv: Exact executable and arguments. Secrets must not be present.
            environment: Additional child-only environment values.
            input_text: Non-secret commands supplied on standard input.
            timeout: Maximum execution time in seconds.

        Returns:
            Captured standard output and standard error.

        Raises:
            ToolError: If the process times out, is unavailable, or fails.
        """
        child_environment = os.environ.copy()
        child_environment.update(environment or {})
        try:
            completed = subprocess.run(
                list(argv),
                check=False,
                capture_output=True,
                text=True,
                input=input_text,
                timeout=timeout,
                env=child_environment,
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            raise ToolError(f"external tool could not complete: {argv[0]}") from error
        if completed.returncode != 0:
            detail = completed.stderr.strip() or completed.stdout.strip()
            for name, value in (environment or {}).items():
                if value and any(
                    marker in name.upper()
                    for marker in self._SENSITIVE_ENVIRONMENT_MARKERS
                ):
                    detail = detail.replace(value, "[REDACTED]")
            raise ToolError(
                f"external tool failed: {argv[0]}"
                + (f": {detail}" if detail else "")
            )
        return ProcessResult(completed.stdout, completed.stderr)
