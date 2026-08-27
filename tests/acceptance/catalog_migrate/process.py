"""Safe subprocess execution for pinned migration tools."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import PurePath

from catalog_migrate.errors import ToolError


@dataclass(frozen=True)
class ProcessResult:
    """Capture non-secret process output needed by a migration operation."""

    stdout: str
    stderr: str


class CommandRunner:
    """Execute an argument vector without a shell and map failures consistently."""

    _SENSITIVE_ENVIRONMENT_MARKERS = ("PASSWORD", "SECRET", "TOKEN")
    _UTF8_TOOLS = frozenset({"psql", "pg_dump", "pg_restore", "pg_isready"})

    @classmethod
    def _decoding_for(cls, executable: str) -> dict[str, str]:
        """Pin PostgreSQL tool output to UTF-8, leaving other tools on the locale.

        ``psql`` emits the server encoding verbatim, so decoding it through the
        Windows locale turns every non-ASCII character into mojibake that is
        then written into the migration export. sqlcmd is left alone because it
        has only ever been validated against the interpreter default.
        """
        name = PurePath(executable.replace("\\", "/")).name.lower()
        if name.endswith(".exe"):
            name = name[: -len(".exe")]
        if name in cls._UTF8_TOOLS:
            return {"encoding": "utf-8", "errors": "strict"}
        return {}

    _INHERITED_ENVIRONMENT_ALLOWLIST = frozenset(
        {
            "APPDATA",
            "COMSPEC",
            "HOME",
            "LANG",
            "LC_ALL",
            "LOCALAPPDATA",
            "PATH",
            "PATHEXT",
            "PROGRAMDATA",
            "SSL_CERT_DIR",
            "SSL_CERT_FILE",
            "SYSTEMROOT",
            "TEMP",
            "TMP",
            "USERPROFILE",
            "WINDIR",
        }
    )

    @staticmethod
    def _resolve_executable(command: str, environment: Mapping[str, str]) -> str:
        """Return an executable path Windows can launch without a shell.

        ``subprocess`` with ``shell=False`` applies ``PATHEXT`` only to the
        arguments, never to ``argv[0]``. On Windows a bare ``az`` therefore
        fails with ``FileNotFoundError`` because the real file is ``az.cmd``.
        Resolve through the child environment so the lookup honours the same
        ``PATH`` the child will run with.
        """
        if sys.platform != "win32" or os.path.splitext(command)[1]:
            return command
        return (
            shutil.which(
                command,
                path=environment.get("PATH"),
            )
            or command
        )

    def run(
        self,
        argv: Sequence[str],
        *,
        environment: Mapping[str, str] | None = None,
        input_text: str | None = None,
        redactions: Sequence[str] = (),
        timeout: int = 300,
    ) -> ProcessResult:
        """Run one child process.

        Args:
            argv: Exact executable and arguments. Secrets must not be present.
            environment: Additional child-only environment values.
            input_text: Non-secret commands supplied on standard input.
            redactions: Secret values to remove from failures without forwarding them.
            timeout: Maximum execution time in seconds.

        Returns:
            Captured standard output and standard error.

        Raises:
            ToolError: If the process times out, is unavailable, or fails.
        """
        child_environment = {
            name: value
            for name, value in os.environ.items()
            if name.upper() in self._INHERITED_ENVIRONMENT_ALLOWLIST
        }
        child_environment.update(environment or {})
        resolved_argv = list(argv)
        if resolved_argv:
            resolved_argv[0] = self._resolve_executable(
                resolved_argv[0], child_environment
            )
        decoding = self._decoding_for(argv[0] if argv else "")
        if decoding:
            child_environment["PGCLIENTENCODING"] = "UTF8"
        try:
            completed = subprocess.run(
                resolved_argv,
                check=False,
                capture_output=True,
                text=True,
                input=input_text,
                timeout=timeout,
                env=child_environment,
                **decoding,
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            raise ToolError(f"external tool could not complete: {argv[0]}") from error
        if completed.returncode != 0:
            detail = completed.stderr.strip() or completed.stdout.strip()
            sensitive_values = list(redactions)
            sensitive_values.extend(
                value
                for name, value in (environment or {}).items()
                if value
                and any(
                    marker in name.upper()
                    for marker in self._SENSITIVE_ENVIRONMENT_MARKERS
                )
            )
            for value in sensitive_values:
                if value:
                    detail = detail.replace(value, "[REDACTED]")
            raise ToolError(
                f"external tool failed: {argv[0]}"
                + (f": {detail}" if detail else "")
            )
        return ProcessResult(completed.stdout, completed.stderr)
