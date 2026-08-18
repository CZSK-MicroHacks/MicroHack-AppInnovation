"""Typed representations of the seed and runtime acceptance contracts."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Literal
from uuid import UUID

from pydantic import (
    AnyHttpUrl,
    BaseModel,
    ConfigDict,
    Field,
    SecretStr,
    field_validator,
    model_validator,
)

from catalog_acceptance.normalization import category_slug


FULL_ACCEPTANCE_CHECKS = (
    "liveness",
    "readiness",
    "catalog-order-and-count",
    "name-search",
    "name-only-search",
    "category-filter-slug",
    "category-filter-name",
    "known-figure",
    "unknown-figure",
    "image-storage",
    "import-new-category",
    "idempotent-import",
    "invalid-import",
    "performance-authentication-missing",
    "performance-authentication-invalid",
    "performance-contract",
    "database-corpus",
    "database-schema",
    "database-constraints",
    "database-indexes",
    "database-migrations",
    "database-tls",
)


class CatalogItem(BaseModel):
    """Represent one canonical catalog record."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    product_id: UUID = Field(alias="productId")
    name: str = Field(min_length=3, max_length=80)
    description: str = Field(min_length=20, max_length=1200)
    category: str = Field(min_length=2, max_length=60)
    filename: str
    image_prompt: str = Field(alias="imagePrompt", min_length=30, max_length=260)

    @field_validator("product_id", mode="before")
    @classmethod
    def require_canonical_uuid(cls, value: object) -> object:
        """Reject UUID spellings that are not canonical lowercase strings."""
        parsed = UUID(str(value))
        if str(value) != str(parsed):
            raise ValueError("productId must be a canonical lowercase UUID")
        return value

    @model_validator(mode="after")
    def require_matching_filename(self) -> CatalogItem:
        """Require derived filename and a non-empty normalized category slug."""
        expected = f"{self.product_id}.png"
        if self.filename != expected:
            raise ValueError(f"filename must equal {expected}")
        if not category_slug(self.category):
            raise ValueError("category must normalize to a non-empty slug")
        return self


class CatalogDto(BaseModel):
    """Represent the stable JSON DTO returned by the performance endpoint."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    product_id: UUID = Field(alias="productId")
    name: str
    description: str
    category: str
    category_slug: str = Field(alias="categorySlug")
    filename: str

    @field_validator("product_id", mode="before")
    @classmethod
    def require_canonical_uuid(cls, value: object) -> object:
        """Reject UUID spellings that are not canonical lowercase strings."""
        parsed = UUID(str(value))
        if str(value) != str(parsed):
            raise ValueError("productId must be a canonical lowercase UUID")
        return value

    @model_validator(mode="after")
    def require_derived_values(self) -> CatalogDto:
        """Require filename and category slug to be derived consistently."""
        if self.filename != f"{self.product_id}.png":
            raise ValueError("filename must be derived from productId")
        if self.category_slug != category_slug(self.category):
            raise ValueError("categorySlug must use category-slug-v1")
        return self


class ManifestCounts(BaseModel):
    """Represent expected corpus counts."""

    figures: int = Field(ge=1)
    categories: int = Field(ge=1)
    images: int = Field(ge=1)
    image_bytes: int = Field(alias="imageBytes", ge=1)


class ManifestHashes(BaseModel):
    """Represent immutable corpus digests."""

    catalog_sha256: str = Field(alias="catalogSha256", pattern=r"^[0-9a-f]{64}$")
    categories_sha256: str = Field(
        alias="categoriesSha256", pattern=r"^[0-9a-f]{64}$"
    )
    image_set_sha256: str = Field(
        alias="imageSetSha256", pattern=r"^[0-9a-f]{64}$"
    )


class ManifestSources(BaseModel):
    """Represent repository-relative corpus source paths."""

    catalog: str
    categories: str
    images: str


class CategorySummary(BaseModel):
    """Represent one category's stable slug and expected figure count."""

    name: str
    slug: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    figure_count: int = Field(alias="figureCount", ge=1)


class SeedManifest(BaseModel):
    """Represent the checked-in canonical seed manifest."""

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    schema_version: Literal["1.0.0"] = Field(alias="schemaVersion")
    verified_at: str = Field(alias="verifiedAt")
    sources: ManifestSources
    counts: ManifestCounts
    hashes: ManifestHashes
    category_summary: list[CategorySummary] = Field(alias="categorySummary")


class HealthResponse(BaseModel):
    """Represent a liveness or readiness response."""

    model_config = ConfigDict(extra="allow")

    status: str
    checks: dict[str, str] | None = None


class ImportResult(BaseModel):
    """Represent the transactional import result."""

    model_config = ConfigDict(extra="forbid")

    inserted: int = Field(ge=0)
    skipped: int = Field(ge=0)
    total: int = Field(ge=0)

    @model_validator(mode="after")
    def require_complete_accounting(self) -> ImportResult:
        """Require inserted and skipped records to account for the input."""
        if self.inserted + self.skipped != self.total:
            raise ValueError("inserted plus skipped must equal total")
        return self


class PerformanceResult(BaseModel):
    """Represent the bounded performance endpoint response."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    iterations: int = Field(ge=1, le=25)
    item_count: int = Field(alias="itemCount", ge=0)
    elapsed_milliseconds: float = Field(alias="elapsedMilliseconds", ge=0)
    items: list[CatalogDto]

    @model_validator(mode="after")
    def require_matching_item_count(self) -> PerformanceResult:
        """Require the declared item count to match the returned DTOs."""
        if self.item_count != len(self.items):
            raise ValueError("itemCount must equal the number of returned items")
        return self


class CorpusCounts(BaseModel):
    """Represent corpus counts written to an acceptance report."""

    figures: int = Field(ge=1)
    categories: int = Field(ge=1)
    images: int = Field(ge=1)


class CheckResult(BaseModel):
    """Represent one independently reportable acceptance check."""

    name: str
    status: Literal["passed", "failed", "skipped"]
    detail: str
    required: bool = True


class AcceptanceSubject(BaseModel):
    """Bind deployed acceptance evidence to immutable release identity."""

    model_config = ConfigDict(populate_by_name=True)

    source_commit: str = Field(alias="sourceCommit", pattern=r"^[0-9a-f]{40}$")
    image_digest: str = Field(alias="imageDigest", pattern=r"^sha256:[0-9a-f]{64}$")
    revision_name: str = Field(alias="revisionName", min_length=1)


class AcceptanceReport(BaseModel):
    """Represent the machine-readable result of a live acceptance run."""

    model_config = ConfigDict(populate_by_name=True)

    schema_version: Literal["1.0.0"] = Field(
        default="1.0.0", alias="schemaVersion"
    )
    profile: Literal["full", "smoke"]
    status: Literal["passed", "failed"]
    started_at: datetime = Field(alias="startedAt")
    finished_at: datetime = Field(alias="finishedAt")
    base_url: AnyHttpUrl = Field(alias="baseUrl")
    database_kind: Literal["sqlserver", "postgresql"] | None = Field(
        default=None, alias="databaseKind"
    )
    database_target: Literal["local", "managed"] | None = Field(
        default=None, alias="databaseTarget"
    )
    subject: AcceptanceSubject | None = None
    corpus: CorpusCounts
    checks: list[CheckResult]

    @model_validator(mode="after")
    def require_consistent_result(self) -> AcceptanceReport:
        """Prevent passing evidence from hiding failed or required skipped checks."""
        has_blocking_check = any(
            check.status == "failed"
            or (check.required and check.status == "skipped")
            for check in self.checks
        )
        if self.status == "passed" and has_blocking_check:
            raise ValueError("passing report contains a blocking check")
        if self.profile == "full":
            if self.database_kind is None or self.database_target is None:
                raise ValueError("full report requires database kind and target")
            actual_names = tuple(check.name for check in self.checks)
            if actual_names != FULL_ACCEPTANCE_CHECKS:
                raise ValueError("full report does not contain the exact ordered check set")
            if any(
                check.status == "skipped" or not check.required for check in self.checks
            ):
                raise ValueError("full report requires every check")
            if self.status == "passed" and any(
                check.status != "passed" for check in self.checks
            ):
                raise ValueError("passing full report contains a non-passing check")
        return self
class AcceptanceSettings(BaseModel):
    """Configure one live acceptance run without exposing secret values."""

    profile: Literal["full", "smoke"] = "full"
    base_url: AnyHttpUrl
    performance_api_key: SecretStr
    data_directory: Path
    database_kind: Literal["sqlserver", "postgresql"] | None = None
    database_host: str | None = None
    database_name: str | None = None
    database_username: str | None = None
    database_password: SecretStr | None = None
    database_port: int | None = Field(default=None, ge=1, le=65535)
    database_ssl_mode: Literal["disable", "allow", "prefer", "require"] = "prefer"
    database_trust_certificate: bool = False
    database_target: Literal["local", "managed"] = "local"
    source_commit: str | None = Field(default=None, pattern=r"^[0-9a-f]{40}$")
    image_digest: str | None = Field(
        default=None, pattern=r"^sha256:[0-9a-f]{64}$"
    )
    revision_name: str | None = Field(default=None, min_length=1)
    expected_work_factor: int = Field(default=10, ge=1, le=25)
    verify_import: bool = True
    verify_all_images: bool = True
    timeout_seconds: float = Field(default=30.0, gt=0, le=300)

    @model_validator(mode="after")
    def require_database_pair(self) -> AcceptanceSettings:
        """Require a complete database CLI configuration when verification is enabled."""
        database_values = (
            self.database_host,
            self.database_name,
            self.database_username,
            self.database_password,
        )
        if self.database_kind is None and any(
            value is not None for value in database_values
        ):
            raise ValueError("database_kind is required with database connection values")
        if self.database_kind is not None and any(
            value is None for value in database_values
        ):
            raise ValueError(
                "database host, name, username, and password are all required"
            )
        if self.profile == "full" and self.database_kind is None:
            raise ValueError("full profile requires database verification")
        if self.profile == "full" and not self.verify_import:
            raise ValueError("full profile requires import verification")
        if self.profile == "full" and not self.verify_all_images:
            raise ValueError("full profile requires complete image verification")
        if self.database_target == "managed" and self.database_ssl_mode != "require":
            raise ValueError("managed database verification requires TLS")
        if self.database_target == "managed" and self.database_trust_certificate:
            raise ValueError("managed database verification cannot trust certificates")
        subject_values = (
            self.source_commit,
            self.image_digest,
            self.revision_name,
        )
        if any(value is not None for value in subject_values) and any(
            value is None for value in subject_values
        ):
            raise ValueError("release subject values must be supplied together")
        return self
