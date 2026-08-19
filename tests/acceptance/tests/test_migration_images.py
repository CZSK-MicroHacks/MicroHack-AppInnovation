"""Image migration tests for canonical membership and Azure data-plane safety."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from catalog_migrate import images
from catalog_migrate.errors import PreconditionError, VerificationError
from catalog_migrate.images import copy_images, source_image_verification, verify_target_images
from catalog_migrate.process import ProcessResult


class ImageRunner:
    """Return an exact Azure CLI version and a deterministic image listing."""

    def __init__(
        self,
        listing: list[dict],
        source_directory: Path | None = None,
        *,
        corrupt_first_download: bool = False,
    ) -> None:
        self.calls: list[tuple[list[str], dict[str, str]]] = []
        self.listing = listing
        self.source_directory = source_directory
        self.corrupt_first_download = corrupt_first_download

    def run(
        self,
        argv: list[str],
        *,
        environment: dict[str, str] | None = None,
        input_text: str | None = None,
        timeout: int = 300,
    ) -> ProcessResult:
        del input_text, timeout
        self.calls.append((list(argv), dict(environment or {})))
        if argv[:2] == ["az", "version"]:
            return ProcessResult('{"azure-cli":"2.80.0"}', "")
        if "list" in argv:
            return ProcessResult(json.dumps(self.listing), "")
        if "download" in argv:
            assert self.source_directory is not None
            name_option = "--name" if "--name" in argv else "--path"
            destination_option = "--file" if "--file" in argv else "--dest"
            source = self.source_directory / argv[argv.index(name_option) + 1]
            destination = Path(argv[argv.index(destination_option) + 1])
            content = source.read_bytes()
            if self.corrupt_first_download and not destination.exists():
                content += b"corrupt"
                self.corrupt_first_download = False
            destination.write_bytes(content)
            return ProcessResult("{}", "")
        return ProcessResult("{}", "")


@pytest.fixture
def blob_target() -> dict:
    """Return a schema-shaped Blob target fragment."""
    return {
        "resourceId": (
            "/subscriptions/00000000-0000-0000-0000-000000000000/"
            "resourceGroups/rg/providers/Microsoft.Storage/storageAccounts/catalog/"
            "blobServices/default/containers/catalog-images"
        ),
        "provider": "azure-blob",
        "location": "catalog-images",
        "authentication": "managed-identity",
    }


def test_source_verification_returns_only_manifest_members(repo_root: Path) -> None:
    """The copy source is the exact 198-image representative corpus."""
    members, verification = source_image_verification(repo_root / "data/images")

    assert len(members) == 198
    assert all(member.parent == repo_root / "data/images" for member in members)
    assert verification["imageCount"] == 198


def test_target_verification_uses_exact_names_bytes_and_hash(
    repo_root: Path,
    blob_target: dict,
) -> None:
    """Verification downloads and hashes bytes instead of trusting metadata."""
    listing = []
    for path in sorted((repo_root / "data/images").glob("*.png")):
        listing.append(
            {
                "name": path.name,
                "properties": {"contentLength": path.stat().st_size},
                "metadata": {"sha256": "0" * 64},
            }
        )
    runner = ImageRunner(listing, repo_root / "data/images")

    verification = verify_target_images(runner, blob_target)

    assert verification["imageCount"] == 198
    assert len([argv for argv, _ in runner.calls if "download" in argv]) == 198
    assert all(
        environment["AZURE_CONFIG_DIR"] == str(Path.home() / ".azure-365")
        for argv, environment in runner.calls
        if argv[0] == "az"
    )


def test_target_verification_rejects_corrupt_downloaded_bytes(
    repo_root: Path,
    blob_target: dict,
) -> None:
    """One corrupt downloaded object fails canonical target verification."""
    listing = [
        {
            "name": path.name,
            "properties": {"contentLength": path.stat().st_size},
            "metadata": {"sha256": hashlib.sha256(path.read_bytes()).hexdigest()},
        }
        for path in sorted((repo_root / "data/images").glob("*.png"))
    ]
    runner = ImageRunner(
        listing,
        repo_root / "data/images",
        corrupt_first_download=True,
    )

    with pytest.raises(VerificationError):
        verify_target_images(runner, blob_target)


def test_image_copy_refuses_a_nonempty_target(
    repo_root: Path,
    blob_target: dict,
) -> None:
    """Copy performs no upload when the target already contains any object."""
    runner = ImageRunner([{"name": "existing.png"}])

    with pytest.raises(PreconditionError, match="not empty"):
        copy_images(
            runner,
            source_directory=repo_root / "data/images",
            target={"images": blob_target},
        )

    assert not any("upload" in argv for argv, _ in runner.calls)


def test_azure_files_commands_require_oauth_backup_intent(tmp_path: Path) -> None:
    """Every Azure Files data-plane operation carries the required OAuth intent."""
    for command in (
        images._list_command("azure-files", "account", "share"),
        images._download_command(
            "azure-files",
            "account",
            "share",
            "image.png",
            tmp_path / "image.png",
        ),
        images._upload_command(
            "azure-files",
            "account",
            "share",
            tmp_path / "image.png",
            "0" * 64,
        ),
    ):
        assert "--auth-mode" in command
        assert command[command.index("--auth-mode") + 1] == "login"
        assert "--backup-intent" in command


def test_blob_commands_do_not_receive_file_only_backup_intent(tmp_path: Path) -> None:
    """Blob data-plane commands retain their separate OAuth argument surface."""
    for command in (
        images._list_command("azure-blob", "account", "container"),
        images._download_command(
            "azure-blob",
            "account",
            "container",
            "image.png",
            tmp_path / "image.png",
        ),
        images._upload_command(
            "azure-blob",
            "account",
            "container",
            tmp_path / "image.png",
            "0" * 64,
        ),
    ):
        assert "--auth-mode" in command
        assert command[command.index("--auth-mode") + 1] == "login"
        assert "--backup-intent" not in command
