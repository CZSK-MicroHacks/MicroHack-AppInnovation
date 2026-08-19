"""Canonical image copy and target verification operations."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from catalog_acceptance.manifest import load_catalog, load_json, validate_seed
from catalog_migrate.database import azure_environment, check_tool_versions
from catalog_migrate.errors import InvalidInputError, PreconditionError, VerificationError
from catalog_migrate.process import CommandRunner


def parse_storage_resource_id(resource_id: str) -> tuple[str, str]:
    """Extract storage account and container/share from a validated resource ID."""
    parts = resource_id.strip("/").split("/")
    try:
        account = parts[parts.index("storageAccounts") + 1]
        location = parts[-1]
    except (ValueError, IndexError) as error:
        raise InvalidInputError("image target resource ID is malformed") from error
    return account, location


def source_image_verification(source_directory: Path) -> tuple[list[Path], dict[str, Any]]:
    """Validate the representative corpus and return canonical members."""
    data_directory = source_directory.parent
    manifest = validate_seed(data_directory)
    members = sorted(
        (source_directory / item.filename for item in load_catalog(data_directory)),
        key=lambda path: path.name,
    )
    return members, {
        "imageCount": manifest.counts.images,
        "imageBytes": manifest.counts.image_bytes,
        "imageSetSha256": manifest.hashes.image_set_sha256,
        "seedManifestVersion": manifest.schema_version,
    }


def _list_command(provider: str, account: str, location: str) -> list[str]:
    if provider == "azure-blob":
        return [
            "az",
            "storage",
            "blob",
            "list",
            "--auth-mode",
            "login",
            "--account-name",
            account,
            "--container-name",
            location,
            "--output",
            "json",
        ]
    return [
        "az",
        "storage",
        "file",
        "list",
        "--auth-mode",
        "login",
        "--account-name",
        account,
        "--share-name",
        location,
        "--output",
        "json",
    ]


def list_target_images(
    runner: CommandRunner, target_images: dict[str, Any]
) -> list[dict[str, Any]]:
    """List target image objects with isolated Azure CLI authentication."""
    account, location = parse_storage_resource_id(target_images["resourceId"])
    result = runner.run(
        _list_command(target_images["provider"], account, location),
        environment=azure_environment(),
    )
    try:
        items = json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise VerificationError("Azure image listing is not valid JSON") from error
    if not isinstance(items, list):
        raise VerificationError("Azure image listing must be an array")
    return items


def _item_properties(item: dict[str, Any]) -> tuple[str, int, str | None]:
    name = item.get("name", "")
    properties = item.get("properties") or {}
    size = (
        properties.get("contentLength")
        or properties.get("content-length")
        or item.get("contentLength")
        or item.get("size")
        or 0
    )
    metadata = item.get("metadata") or properties.get("metadata") or {}
    return name, int(size), metadata.get("sha256")


def verify_target_images(
    runner: CommandRunner, target_images: dict[str, Any]
) -> dict[str, Any]:
    """Verify exact image names, bytes, and deterministic set digest."""
    check_tool_versions(runner, azure=True)
    manifest = load_json(
        Path(__file__).resolve().parents[3] / "data" / "manifest.json"
    )
    expected_names = {
        item.filename
        for item in load_catalog(Path(__file__).resolve().parents[3] / "data")
    }
    listed = list_target_images(runner, target_images)
    parsed = [_item_properties(item) for item in listed]
    names = {name for name, _, _ in parsed}
    if names != expected_names or len(parsed) != len(expected_names):
        raise VerificationError("image target has missing, extra, or duplicate members")
    digest = hashlib.sha256()
    total_bytes = 0
    for name, size, sha256 in sorted(parsed):
        if sha256 is None or len(sha256) != 64:
            raise VerificationError(f"image target lacks SHA-256 metadata: {name}")
        digest.update(f"{name}\t{size}\t{sha256}\n".encode())
        total_bytes += size
    verification = {
        "imageCount": len(parsed),
        "imageBytes": total_bytes,
        "imageSetSha256": digest.hexdigest(),
        "seedManifestVersion": manifest["schemaVersion"],
    }
    expected = {
        "imageCount": manifest["counts"]["images"],
        "imageBytes": manifest["counts"]["imageBytes"],
        "imageSetSha256": manifest["hashes"]["imageSetSha256"],
        "seedManifestVersion": manifest["schemaVersion"],
    }
    if verification != expected:
        raise VerificationError("image target differs from the canonical manifest")
    return verification


def copy_images(
    runner: CommandRunner,
    *,
    source_directory: Path,
    target: dict[str, Any],
) -> dict[str, Any]:
    """Copy only canonical manifest members to an empty Azure image target."""
    check_tool_versions(runner, azure=True)
    members, expected = source_image_verification(source_directory)
    target_images = target["images"]
    if list_target_images(runner, target_images):
        raise PreconditionError("image target is not empty")
    account, location = parse_storage_resource_id(target_images["resourceId"])
    provider = target_images["provider"]
    for member in members:
        sha256 = hashlib.sha256(member.read_bytes()).hexdigest()
        if provider == "azure-blob":
            argv = [
                "az",
                "storage",
                "blob",
                "upload",
                "--auth-mode",
                "login",
                "--account-name",
                account,
                "--container-name",
                location,
                "--name",
                member.name,
                "--file",
                str(member),
                "--overwrite",
                "false",
                "--metadata",
                f"sha256={sha256}",
            ]
        else:
            argv = [
                "az",
                "storage",
                "file",
                "upload",
                "--auth-mode",
                "login",
                "--account-name",
                account,
                "--share-name",
                location,
                "--path",
                member.name,
                "--source",
                str(member),
                "--metadata",
                f"sha256={sha256}",
            ]
        runner.run(argv, environment=azure_environment(), timeout=600)
    actual = verify_target_images(runner, target_images)
    if actual != expected:
        raise VerificationError("copied image verification differs from source")
    return actual
