"""Validated capture models for the Defender for Cloud challenge."""

from pathlib import PurePosixPath
from typing import Literal

from pydantic import (
    AwareDatetime,
    AnyHttpUrl,
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    field_validator,
    model_validator,
)


class StrictModel(BaseModel):
    """Reject undeclared fields in Defender evidence inputs."""

    model_config = ConfigDict(
        extra="forbid",
        populate_by_name=True,
        allow_inf_nan=False,
    )


def _validate_repository_file(value: str) -> str:
    """Validate one normalized repository-relative file path."""
    path = PurePosixPath(value)
    if (
        path.is_absolute()
        or not path.parts
        or value != str(path)
        or any(part in {"", ".", ".."} for part in path.parts)
    ):
        raise ValueError("artifact paths must be normalized repository-relative paths")
    return value


class ArtifactReference(StrictModel):
    """Bind one captured artifact to its repository path and digest."""

    file: str
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    _validate_file = field_validator("file")(_validate_repository_file)


class QueryArtifact(ArtifactReference):
    """Bind one point-in-time Defender query response."""

    queried_at: AwareDatetime = Field(alias="queriedAt")
    scope_resource_id: str = Field(
        alias="scopeResourceId",
        pattern=r"^/subscriptions/",
    )
    api_version: str = Field(
        alias="apiVersion",
        pattern=r"^20[0-9]{2}-[0-9]{2}-[0-9]{2}(?:-preview)?$",
    )


class ResourceCapturePair(StrictModel):
    """Hold digest-bound before and after ARM state for one resource."""

    before: ArtifactReference
    after: ArtifactReference

    @model_validator(mode="after")
    def require_distinct_files(self) -> "ResourceCapturePair":
        """Prevent a single file from impersonating both observed states."""
        if self.before.file == self.after.file:
            raise ValueError("before and after captures must use distinct files")
        return self


class DefenderDecision(StrictModel):
    """Describe one explicit control disposition and its rationale."""

    disposition: Literal[
        "remediated",
        "already-compliant",
        "justified",
        "documented-exception",
    ]
    justification: str | None
    compensating_controls: list[str] = Field(alias="compensatingControls")

    @model_validator(mode="after")
    def validate_rationale(self) -> "DefenderDecision":
        """Require meaningful rationale only for accepted residual exposure."""
        residual = self.disposition in {"justified", "documented-exception"}
        if residual:
            if self.justification is None or len(self.justification.strip()) < 40:
                raise ValueError(
                    "residual exposure requires a justification of at least 40 characters"
                )
            if not self.compensating_controls:
                raise ValueError(
                    "residual exposure requires at least one compensating control"
                )
        elif self.justification is not None or self.compensating_controls:
            raise ValueError(
                "remediated and already-compliant decisions cannot carry exceptions"
            )
        if any(len(item.strip()) < 3 for item in self.compensating_controls):
            raise ValueError("compensating controls must be meaningful strings")
        if len(set(self.compensating_controls)) != len(self.compensating_controls):
            raise ValueError("compensating controls must be unique")
        return self


class DefenderIdentityCapture(StrictModel):
    """Bind the Defender capture to frozen modernization identity artifacts."""

    handoff: ArtifactReference
    target_output: ArtifactReference = Field(alias="targetOutput")
    lab_profile: ArtifactReference = Field(alias="labProfile")
    cleanup_manifest: ArtifactReference = Field(alias="cleanupManifest")


class DefenderFoundationCapture(StrictModel):
    """Describe facilitator-owned subscription preparation evidence."""

    subscription_id: str = Field(
        alias="subscriptionId",
        pattern=r"^[0-9a-fA-F-]{36}$",
    )
    dedicated_workshop_subscription: Literal[True] = Field(
        alias="dedicatedWorkshopSubscription"
    )
    facilitator_change_approval: str = Field(
        alias="facilitatorChangeApproval",
        min_length=8,
        max_length=200,
    )
    pricings: ArtifactReference
    budget: QueryArtifact
    legacy_vm_coverage: ArtifactReference = Field(alias="legacyVmCoverage")
    seed_snapshot: ArtifactReference = Field(alias="seedSnapshot")
    manual_preflight: ArtifactReference = Field(alias="manualPreflight")


class DefenderResourceCaptures(StrictModel):
    """Group the four resource posture comparisons required by Challenge 5."""

    container_registry: ResourceCapturePair = Field(alias="containerRegistry")
    container_registry_role_assignments: ArtifactReference = Field(
        alias="containerRegistryRoleAssignments"
    )
    container_app: ResourceCapturePair = Field(alias="containerApp")
    database: ResourceCapturePair
    legacy_vm: ResourceCapturePair = Field(alias="legacyVm")


class DefenderDecisions(StrictModel):
    """Hold the permitted decisions for controls that can retain exposure."""

    container_app_ingress: DefenderDecision = Field(alias="containerAppIngress")
    database_network: DefenderDecision = Field(alias="databaseNetwork")
    legacy_vm_exposure: DefenderDecision = Field(alias="legacyVmExposure")

    @model_validator(mode="after")
    def validate_control_dispositions(self) -> "DefenderDecisions":
        """Restrict each control to the dispositions frozen by the registry."""
        if self.container_app_ingress.disposition not in {
            "remediated",
            "already-compliant",
            "justified",
        }:
            raise ValueError(
                "containerAppIngress must be compliant, remediated, or justified"
            )
        if self.database_network.disposition == "justified":
            raise ValueError(
                "databaseNetwork uses documented-exception, not justified"
            )
        if self.legacy_vm_exposure.disposition == "justified":
            raise ValueError(
                "legacyVmExposure uses documented-exception, not justified"
            )
        return self


class DefenderImageAssessmentCapture(ArtifactReference):
    """Describe a digest-specific vulnerability assessment query."""

    queried_at: AwareDatetime = Field(alias="queriedAt")
    status: Literal["completed", "pending", "unavailable"]
    digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    registry_resource_id: str = Field(
        alias="registryResourceId",
        pattern=r"^/subscriptions/",
    )
    api_version: str = Field(
        alias="apiVersion",
        pattern=r"^20[0-9]{2}-[0-9]{2}-[0-9]{2}(?:-preview)?$",
    )


class DefenderSecurityContextCapture(StrictModel):
    """Bind query attempts for recommendations and posture context."""

    recommendations: QueryArtifact
    secure_score: QueryArtifact = Field(alias="secureScore")
    mcsb: QueryArtifact
    attack_paths: QueryArtifact = Field(alias="attackPaths")


class DefenderHealthCapture(StrictModel):
    """Record post-remediation health and readiness for the selected revision."""

    observed_at: AwareDatetime = Field(alias="observedAt")
    revision_name: str = Field(alias="revisionName", min_length=1)
    health_url: AnyHttpUrl = Field(alias="healthUrl")
    health_status: Literal[200] = Field(alias="healthStatus")
    readiness_url: AnyHttpUrl = Field(alias="readinessUrl")
    readiness_status: Literal[200] = Field(alias="readinessStatus")


class DefenderEvidenceCapture(StrictModel):
    """Define trusted inputs for deterministic Challenge 5 rendering."""

    schema_version: Literal["1.1.0"] = Field(alias="schemaVersion")
    captured_at: AwareDatetime = Field(alias="capturedAt")
    identity: DefenderIdentityCapture
    foundation: DefenderFoundationCapture
    resources: DefenderResourceCaptures
    decisions: DefenderDecisions
    image_assessment: DefenderImageAssessmentCapture = Field(
        alias="imageAssessment"
    )
    security_context: DefenderSecurityContextCapture = Field(alias="securityContext")
    health: DefenderHealthCapture

    @model_validator(mode="after")
    def validate_manifest(self) -> "DefenderEvidenceCapture":
        """Require unique inputs and a capture time after all observations."""
        references = [
            self.identity.handoff,
            self.identity.target_output,
            self.identity.lab_profile,
            self.identity.cleanup_manifest,
            self.foundation.pricings,
            self.foundation.budget,
            self.foundation.legacy_vm_coverage,
            self.foundation.seed_snapshot,
            self.foundation.manual_preflight,
            self.resources.container_registry.before,
            self.resources.container_registry.after,
            self.resources.container_registry_role_assignments,
            self.resources.container_app.before,
            self.resources.container_app.after,
            self.resources.database.before,
            self.resources.database.after,
            self.resources.legacy_vm.before,
            self.resources.legacy_vm.after,
            self.image_assessment,
            self.security_context.recommendations,
            self.security_context.secure_score,
            self.security_context.mcsb,
            self.security_context.attack_paths,
        ]
        files = [reference.file for reference in references]
        if len(files) != len(set(files)):
            raise ValueError("every Defender capture role must use a distinct file")
        observed = [
            self.image_assessment.queried_at,
            self.foundation.budget.queried_at,
            self.security_context.recommendations.queried_at,
            self.security_context.secure_score.queried_at,
            self.security_context.mcsb.queried_at,
            self.security_context.attack_paths.queried_at,
            self.health.observed_at,
        ]
        if any(self.captured_at < timestamp for timestamp in observed):
            raise ValueError("capturedAt must not precede any observation")
        return self
