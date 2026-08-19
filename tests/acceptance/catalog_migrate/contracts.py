"""Frozen contract loading, schema validation, and safety guards."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker
from jsonschema.exceptions import ValidationError

from catalog_acceptance.handoff import _validate_target_resource_ids
from catalog_migrate.errors import InvalidInputError, PreconditionError

KNOWN_SECRETS = {
    "MIGRATION_SOURCE_DATABASE_PASSWORD",
    "MIGRATION_TARGET_ADMINISTRATOR_PASSWORD",
    "MIGRATION_TARGET_APPLICATION_PASSWORD",
}
COMMIT_PATTERN = re.compile(r"^[0-9a-f]{40}$")


def repository_root() -> Path:
    """Return the repository root for contracts and canonical data."""
    return Path(__file__).resolve().parents[3]


def load_json(path: Path) -> Any:
    """Read one UTF-8 JSON document.

    Raises:
        InvalidInputError: If the file is absent or malformed.
    """
    try:
        with path.open(encoding="utf-8") as stream:
            return json.load(stream)
    except (OSError, json.JSONDecodeError) as error:
        raise InvalidInputError(f"invalid JSON document: {path}") from error


def validate_document(document: Any, schema_name: str) -> None:
    """Validate a document against one checked-in frozen schema.

    Raises:
        InvalidInputError: If schema validation fails.
    """
    schema_path = repository_root() / "workshop" / "contracts" / schema_name
    try:
        Draft202012Validator(
            load_json(schema_path),
            format_checker=FormatChecker(),
        ).validate(document)
    except ValidationError as error:
        raise InvalidInputError(
            f"document does not satisfy {schema_name}: {error.message}"
        ) from error


def load_target_output(
    path: Path,
    *,
    required_stage: str,
) -> dict[str, Any]:
    """Load and validate one Azure target-output document.

    Raises:
        InvalidInputError: If the target is malformed or at the wrong stage.
    """
    target = load_json(path)
    validate_document(target, "azure-target-output.schema.json")
    try:
        _validate_target_resource_ids(target)
    except ValueError as error:
        raise InvalidInputError(str(error)) from error
    if target["deploymentStage"] != required_stage:
        raise InvalidInputError(f"target output must be {required_stage}-stage")
    return target


def require_secrets(allowed: set[str], required: set[str]) -> dict[str, str]:
    """Enforce required, forbidden, and undeclared migration secrets.

    Returns:
        A mapping containing only allowed populated secret values.

    Raises:
        InvalidInputError: If a required secret is missing or a forbidden one is set.
    """
    populated = {name for name in KNOWN_SECRETS if os.environ.get(name)}
    undeclared = populated - allowed
    if undeclared:
        raise InvalidInputError(
            f"secret environment is not allowed for this command: {sorted(undeclared)}"
        )
    missing = required - populated
    if missing:
        raise InvalidInputError(
            f"required secret environment is missing: {sorted(missing)}"
        )
    return {name: os.environ[name] for name in populated}


def guard_target(
    target: dict[str, Any],
    target_resource_id: str,
    confirmation: str,
    execute: bool,
    section: str,
) -> dict[str, Any]:
    """Require exact target identity confirmation and explicit execution.

    Raises:
        InvalidInputError: If the resource ID does not identify the selected target.
        PreconditionError: If confirmation or execution approval is absent.
    """
    declared = target[section]["resourceId"]
    if target_resource_id != declared:
        raise InvalidInputError("target resource ID differs from target output")
    if confirmation != declared:
        raise PreconditionError("target confirmation must exactly match the resource ID")
    if not execute:
        raise PreconditionError("--execute is required for target mutation")
    return target[section]


def artifact_metadata_path(path: Path) -> Path:
    """Return the non-secret sidecar path for an exported database artifact."""
    return path.with_name(f"{path.name}.metadata.json")


def repository_path(path: Path) -> str:
    """Return a normalized repository-relative path.

    Raises:
        InvalidInputError: If the path is outside the repository.
    """
    try:
        return path.resolve().relative_to(repository_root().resolve()).as_posix()
    except ValueError as error:
        raise InvalidInputError(f"path must be inside the repository: {path}") from error
