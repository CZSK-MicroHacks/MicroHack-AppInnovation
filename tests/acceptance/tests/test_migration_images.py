"""Image migration tests for canonical membership and Azure data-plane safety."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from catalog_migrate.errors import PreconditionError
from catalog_migrate.images import copy_images, source_image_verification, verify_target_images
from catalog_migrate.process import ProcessResult


class ImageRunner:
    """Return an exact Azure CLI version and a deterministic image listing."""

    def __init__(self, listing: list[dict]) -> None:
        self.calls: list[tuple[list[str], dict[str, str]]] = []
        self.listing = listing

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
    """Azure listing metadata reconstructs the frozen image-set digest."""
    listing = []
    for path in sorted((repo_root / "data/images").glob("*.png")):
        listing.append(
            {
                "name": path.name,
                "properties": {"contentLength": path.stat().st_size},
                "metadata": {"sha256": hashlib.sha256(path.read_bytes()).hexdigest()},
            }
        )
    runner = ImageRunner(listing)

    verification = verify_target_images(runner, blob_target)

    assert verification["imageCount"] == 198
    assert all(
        environment["AZURE_CONFIG_DIR"] == str(Path.home() / ".azure-365")
        for argv, environment in runner.calls
        if argv[0] == "az"
    )


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
