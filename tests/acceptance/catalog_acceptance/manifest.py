"""Validate canonical catalog files and shared normalization rules."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any

from catalog_acceptance.models.contracts import CatalogItem, SeedManifest
from catalog_acceptance.normalization import category_slug, identity_is_valid

__all__ = ["category_slug", "identity_is_valid"]


def repository_root() -> Path:
    """Return the repository root containing ``data`` and ``workshop``."""
    return Path(__file__).resolve().parents[3]


def load_json(path: Path) -> Any:
    """Load a UTF-8 JSON document from ``path``."""
    with path.open(encoding="utf-8") as stream:
        return json.load(stream)


def load_catalog(data_directory: Path) -> list[CatalogItem]:
    """Load and validate every canonical catalog item."""
    raw_items = load_json(data_directory / "catalog.json")
    return [CatalogItem.model_validate(item) for item in raw_items]


def load_manifest(data_directory: Path) -> SeedManifest:
    """Load the checked-in seed manifest."""
    return SeedManifest.model_validate(load_json(data_directory / "manifest.json"))


def sha256_file(path: Path) -> str:
    """Return the lowercase SHA-256 digest for one file."""
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def image_set_sha256(images_directory: Path) -> tuple[str, int, int]:
    """Return the deterministic image-set digest, file count, and total bytes."""
    digest = hashlib.sha256()
    count = 0
    total_bytes = 0
    for path in sorted(images_directory.glob("*.png"), key=lambda item: item.name):
        size = path.stat().st_size
        line = f"{path.name}\t{size}\t{sha256_file(path)}\n"
        digest.update(line.encode("utf-8"))
        count += 1
        total_bytes += size
    return digest.hexdigest(), count, total_bytes


def validate_seed(data_directory: Path) -> SeedManifest:
    """Validate identities, categories, files, counts, and corpus digests.

    Raises:
        ValueError: If any manifest or corpus invariant does not hold.
    """
    manifest = load_manifest(data_directory)
    catalog_path = data_directory / manifest.sources.catalog
    categories_path = data_directory / manifest.sources.categories
    images_directory = data_directory / manifest.sources.images
    items = load_catalog(data_directory)
    categories = load_json(categories_path)
    errors: list[str] = []

    if not isinstance(categories, list) or not all(
        isinstance(category, str) for category in categories
    ):
        errors.append("categories.json must contain an array of strings")
        categories = []

    ids = [str(item.product_id) for item in items]
    names = [item.name.casefold() for item in items]
    if len(ids) != len(set(ids)):
        errors.append("catalog product IDs must be unique")
    if len(names) != len(set(names)):
        errors.append("catalog names must be unique case-insensitively")
    if len(categories) != len(set(categories)):
        errors.append("category names must be unique")

    category_counts = Counter(item.category for item in items)
    unknown_categories = sorted(set(category_counts) - set(categories))
    if unknown_categories:
        errors.append(f"catalog contains unknown categories: {unknown_categories}")

    expected_summary = {
        summary.name: (summary.slug, summary.figure_count)
        for summary in manifest.category_summary
    }
    actual_summary = {
        category: (category_slug(category), category_counts[category])
        for category in categories
    }
    if actual_summary != expected_summary:
        errors.append("category summary does not match catalog.json")

    expected_files = {item.filename for item in items}
    actual_files = {path.name for path in images_directory.glob("*.png")}
    if actual_files != expected_files:
        errors.append("image filenames do not exactly match catalog identities")

    image_digest, image_count, image_bytes = image_set_sha256(images_directory)
    actual_counts = (
        len(items),
        len(categories),
        image_count,
        image_bytes,
    )
    expected_counts = (
        manifest.counts.figures,
        manifest.counts.categories,
        manifest.counts.images,
        manifest.counts.image_bytes,
    )
    if actual_counts != expected_counts:
        errors.append(
            f"corpus counts {actual_counts} do not match manifest {expected_counts}"
        )

    actual_hashes = (
        sha256_file(catalog_path),
        sha256_file(categories_path),
        image_digest,
    )
    expected_hashes = (
        manifest.hashes.catalog_sha256,
        manifest.hashes.categories_sha256,
        manifest.hashes.image_set_sha256,
    )
    if actual_hashes != expected_hashes:
        errors.append("corpus hashes do not match manifest.json")

    if errors:
        raise ValueError("; ".join(errors))
    return manifest
