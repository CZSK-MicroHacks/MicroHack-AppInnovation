"""Canonical image copy and target verification operations."""

from __future__ import annotations

import hashlib
import json
import tempfile
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
        "--backup-intent",
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


def _download_command(
    provider: str,
    account: str,
    location: str,
    name: str,
    destination: Path,
) -> list[str]:
    """Build one target-byte download command."""
    if provider == "azure-blob":
        return [
            "az",
            "storage",
            "blob",
            "download",
            "--auth-mode",
            "login",
            "--account-name",
            account,
            "--container-name",
            location,
            "--name",
            name,
            "--file",
            str(destination),
        ]
    return [
        "az",
        "storage",
        "file",
        "download",
        "--auth-mode",
        "login",
        "--backup-intent",
        "--account-name",
        account,
        "--share-name",
        location,
        "--path",
        name,
        "--dest",
        str(destination),
    ]


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
    listed_names = [str(item.get("name", "")) for item in listed]
    if set(listed_names) != expected_names or len(listed_names) != len(expected_names):
        raise VerificationError("image target has missing, extra, or duplicate members")
    account, location = parse_storage_resource_id(target_images["resourceId"])
    provider = target_images["provider"]
    digest = hashlib.sha256()
    total_bytes = 0
    with tempfile.TemporaryDirectory(prefix="catalog-image-verification-") as temporary:
        temporary_directory = Path(temporary)
        for name in sorted(listed_names):
            destination = temporary_directory / name
            runner.run(
                _download_command(provider, account, location, name, destination),
                environment=azure_environment(),
                timeout=600,
            )
            if not destination.is_file():
                raise VerificationError(f"target image download is absent: {name}")
            content = destination.read_bytes()
            sha256 = hashlib.sha256(content).hexdigest()
            size = len(content)
            digest.update(f"{name}\t{size}\t{sha256}\n".encode())
            total_bytes += size
    verification = {
        "imageCount": len(listed_names),
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


def _upload_command(
    provider: str,
    account: str,
    location: str,
    member: Path,
    sha256: str,
) -> list[str]:
    """Build one immutable target-byte upload command."""
    if provider == "azure-blob":
        return [
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
    return [
        "az",
        "storage",
        "file",
        "upload",
        "--auth-mode",
        "login",
        "--backup-intent",
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
        argv = _upload_command(provider, account, location, member, sha256)
        runner.run(argv, environment=azure_environment(), timeout=600)
    actual = verify_target_images(runner, target_images)
    if actual != expected:
        raise VerificationError("copied image verification differs from source")
    return actual
