"""Strict repository artifact loading for deterministic evidence producers."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


def _reject_nonfinite(value: str) -> None:
    """Reject non-standard JSON numeric constants."""
    raise ValueError(f"non-finite JSON constant is forbidden: {value}")


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    """Build one object while rejecting duplicate JSON member names."""
    value: dict[str, Any] = {}
    for key, child in pairs:
        if key in value:
            raise ValueError(f"duplicate JSON member is forbidden: {key}")
        value[key] = child
    return value


def load_json_object(path: Path) -> dict[str, Any]:
    """Load one strict UTF-8 JSON object.

    Args:
        path: JSON document to load.

    Returns:
        The parsed JSON object.

    Raises:
        OSError: If the file cannot be read.
        ValueError: If the document is not strict JSON or is not an object.
    """
    with path.open(encoding="utf-8") as handle:
        value = json.load(
            handle,
            parse_constant=_reject_nonfinite,
            object_pairs_hook=_reject_duplicate_keys,
        )
    if not isinstance(value, dict):
        raise ValueError(f"expected a JSON object: {path}")
    return value


def sha256_file(path: Path) -> str:
    """Return the lowercase SHA-256 digest of one file.

    Args:
        path: File to hash.

    Returns:
        A lowercase hexadecimal SHA-256 digest.
    """
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def resolve_repository_file(repository_root: Path, value: str) -> Path:
    """Resolve one non-empty regular file without traversal or symlinks.

    Args:
        repository_root: Trusted repository boundary.
        value: Normalized repository-relative path.

    Returns:
        The resolved artifact path.

    Raises:
        ValueError: If the path is unsafe, missing, empty, or not a regular file.
    """
    root = repository_root.resolve()
    relative = Path(value)
    if (
        relative.is_absolute()
        or not relative.parts
        or value != relative.as_posix()
        or any(part in {"", ".", ".."} for part in relative.parts)
    ):
        raise ValueError(f"artifact path must stay within the repository: {value}")
    declared = root
    for part in relative.parts:
        declared /= part
        if declared.is_symlink():
            raise ValueError(f"artifact path contains a symlink: {value}")
    resolved = declared.resolve()
    try:
        resolved.relative_to(root)
    except ValueError as error:
        raise ValueError(f"artifact path escapes the repository: {value}") from error
    if not resolved.is_file() or resolved.stat().st_size == 0:
        raise ValueError(f"artifact path must be a non-empty regular file: {value}")
    return resolved


def load_digest_bound_json(
    repository_root: Path,
    file: str,
    expected_sha256: str,
) -> dict[str, Any]:
    """Load one strict JSON object only when its declared digest matches.

    Args:
        repository_root: Trusted repository boundary.
        file: Repository-relative JSON path.
        expected_sha256: Expected lowercase SHA-256 digest.

    Returns:
        The parsed JSON object.

    Raises:
        OSError: If the file cannot be read.
        ValueError: If the path, digest, or JSON document is invalid.
    """
    path = resolve_repository_file(repository_root, file)
    actual_sha256 = sha256_file(path)
    if actual_sha256 != expected_sha256:
        raise ValueError(
            f"artifact digest mismatch for {file}: "
            f"expected {expected_sha256}, got {actual_sha256}"
        )
    return load_json_object(path)
