"""Validated normalized observations for the shared workshop challenges."""

from datetime import datetime
import math
from pathlib import PurePosixPath
from typing import Literal

from pydantic import (
    AwareDatetime,
    AnyHttpUrl,
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StrictFloat,
    StrictInt,
    field_validator,
    model_validator,
)


class StrictModel(BaseModel):
    """Reject undeclared fields in normalized evidence structures."""

    model_config = ConfigDict(
        extra="forbid",
        populate_by_name=True,
        allow_inf_nan=False,
    )


class StrictObservation(StrictModel):
    """Require a version on every normalized evidence observation."""

    schema_version: Literal["1.0.0"] = Field(alias="schemaVersion")


class LoadObservation(StrictModel):
    """Require the deterministic-renderer version on load observations."""

    schema_version: Literal["1.1.0"] = Field(alias="schemaVersion")


class ObservabilityObservation(StrictModel):
    """Require the post-refreeze version on observability observations."""

    schema_version: Literal["1.1.0"] = Field(alias="schemaVersion")


class CicdObservation(StrictModel):
    """Require the corrected workflow protocol version on CI/CD observations."""

    schema_version: Literal["1.1.0"] = Field(alias="schemaVersion")


class MetricPoint(StrictModel):
    """Represent one timestamped Azure Monitor metric value."""

    timestamp: AwareDatetime
    value: StrictFloat = Field(ge=0)

    @field_validator("timestamp")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        """Require an explicit offset so observations compare deterministically."""
        if value.tzinfo is None:
            raise ValueError("metric timestamp must include a timezone")
        return value


class MetricObservation(LoadObservation):
    """Represent normalized Azure Monitor metric output for one resource."""

    resource_id: str = Field(alias="resourceId", pattern=r"^/subscriptions/")
    metric: str = Field(min_length=1)
    aggregation: str = Field(min_length=1)
    start_time: AwareDatetime = Field(alias="startTime")
    end_time: AwareDatetime = Field(alias="endTime")
    points: list[MetricPoint] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_window(self) -> "MetricObservation":
        """Require an ordered, timezone-aware window containing every point."""
        if self.start_time.tzinfo is None or self.end_time.tzinfo is None:
            raise ValueError("metric window timestamps must include a timezone")
        if self.start_time >= self.end_time:
            raise ValueError("metric observation endTime must follow startTime")
        if any(
            point.timestamp < self.start_time or point.timestamp > self.end_time
            for point in self.points
        ):
            raise ValueError("metric points must fall within the observation window")
        return self


class LoadRunObservation(LoadObservation):
    """Represent normalized Azure Load Testing run statistics."""

    resource_id: str = Field(
        alias="resourceId",
        pattern=(
            r"^/subscriptions/[^/]+/resourceGroups/[^/]+/providers/"
            r"Microsoft\.LoadTestService/loadTests/[^/]+$"
        ),
    )
    test_run_id: str = Field(alias="testRunId", min_length=1)
    test_id: str = Field(alias="testId", min_length=1)
    application_url: AnyHttpUrl = Field(alias="applicationUrl")
    target_url: AnyHttpUrl = Field(alias="targetUrl")
    revision_name: str = Field(alias="revisionName", min_length=1)
    performance_path: Literal["/perftest/catalog"] = Field(alias="performancePath")
    configuration_file: Literal["tests/load/load-test.yaml"] = Field(
        alias="configurationFile"
    )
    configuration_sha256: str = Field(
        alias="configurationSha256", pattern=r"^[0-9a-f]{64}$"
    )
    jmeter_file: Literal["tests/load/catalog-load.jmx"] = Field(alias="jmeterFile")
    jmeter_sha256: str = Field(alias="jmeterSha256", pattern=r"^[0-9a-f]{64}$")
    status: Literal["DONE"]
    started_at: AwareDatetime = Field(alias="startedAt")
    completed_at: AwareDatetime = Field(alias="completedAt")
    total_requests: StrictInt = Field(alias="totalRequests", gt=0)
    failed_requests: StrictInt = Field(alias="failedRequests", ge=0, le=0)
    virtual_users: StrictInt = Field(alias="virtualUsers", ge=1)
    duration_seconds: StrictInt = Field(alias="durationSeconds", ge=1)
    captured_at: AwareDatetime = Field(alias="capturedAt")

    @model_validator(mode="after")
    def validate_times(self) -> "LoadRunObservation":
        """Require an ordered, timezone-aware load-test interval."""
        if self.started_at.tzinfo is None or self.completed_at.tzinfo is None:
            raise ValueError("load-test timestamps must include a timezone")
        if self.started_at >= self.completed_at:
            raise ValueError("load-test completion must follow its start")
        return self


class ScaleConfigurationObservation(LoadObservation):
    """Represent the observed Container App autoscale configuration."""

    source: Literal["azure-resource-manager"]
    container_app_resource_id: str = Field(
        alias="containerAppResourceId", pattern=r"^/subscriptions/"
    )
    revision_name: str = Field(alias="revisionName", min_length=1)
    minimum_replicas: StrictInt = Field(alias="minimumReplicas", ge=1, le=1)
    maximum_replicas: StrictInt = Field(alias="maximumReplicas", ge=3, le=3)
    rule_name: Literal["http"] = Field(alias="ruleName")
    rule_type: Literal["http"] = Field(alias="ruleType")
    concurrent_requests: StrictInt = Field(alias="concurrentRequests", ge=50, le=50)
    provisioning_state: Literal["Succeeded"] = Field(alias="provisioningState")
    etag: str = Field(min_length=1)
    observed_at: AwareDatetime = Field(alias="observedAt")


class HealthObservation(LoadObservation):
    """Represent health and readiness checks against one deployed revision."""

    health_url: AnyHttpUrl = Field(alias="healthUrl")
    readiness_url: AnyHttpUrl = Field(alias="readinessUrl")
    revision_name: str = Field(alias="revisionName", min_length=1)
    observed_at: AwareDatetime = Field(alias="observedAt")
    health_status: StrictInt = Field(alias="healthStatus", ge=200, le=200)
    readiness_status: StrictInt = Field(alias="readinessStatus", ge=200, le=200)


def _validate_repository_file(value: str) -> str:
    """Validate one normalized repository-relative capture path."""
    path = PurePosixPath(value)
    if (
        path.is_absolute()
        or not path.parts
        or any(part in {"", ".", ".."} for part in path.parts)
    ):
        raise ValueError("capture paths must be normalized repository-relative paths")
    return value


class LoadCaptureFile(StrictModel):
    """Bind one raw Azure response to its repository path and digest."""

    file: str
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    _validate_file = field_validator("file")(_validate_repository_file)


class LoadRunCapture(LoadCaptureFile):
    """Describe the raw Azure Load Testing run response."""

    resource_id: str = Field(alias="resourceId", pattern=r"^/subscriptions/")


class LoadScaleCapture(LoadCaptureFile):
    """Describe the raw Container App scale-configuration response."""

    observed_at: AwareDatetime = Field(alias="observedAt")


class LoadMetricCapture(LoadCaptureFile):
    """Describe one bounded Azure Monitor metric response."""

    resource_id: str = Field(alias="resourceId", pattern=r"^/subscriptions/")
    metric_name: str = Field(alias="metricName", min_length=1)
    aggregation: Literal["Maximum", "Total"]
    interval: Literal["PT1M"]
    start: AwareDatetime
    end: AwareDatetime
    revision_name: str | None = Field(
        default=None,
        alias="revisionName",
        min_length=1,
    )

    @model_validator(mode="after")
    def validate_window(self) -> "LoadMetricCapture":
        """Require a forward metric query interval."""
        if self.end <= self.start:
            raise ValueError("metric capture end must be later than start")
        return self


class LoadRecoveryCapture(StrictModel):
    """Capture the post-load health and readiness observation."""

    observed_at: AwareDatetime = Field(alias="observedAt")
    health_url: AnyHttpUrl = Field(alias="healthUrl")
    health_status: Literal[200] = Field(alias="healthStatus")
    readiness_url: AnyHttpUrl = Field(alias="readinessUrl")
    readiness_status: Literal[200] = Field(alias="readinessStatus")


class LoadArtifactCapture(StrictModel):
    """Bind the checked-in Azure Load Testing and JMeter inputs."""

    configuration_file: str = Field(alias="configurationFile")
    configuration_sha256: str = Field(
        alias="configurationSha256",
        pattern=r"^[0-9a-f]{64}$",
    )
    jmeter_file: str = Field(alias="jmeterFile")
    jmeter_sha256: str = Field(alias="jmeterSha256", pattern=r"^[0-9a-f]{64}$")

    _validate_configuration_file = field_validator("configuration_file")(
        _validate_repository_file
    )
    _validate_jmeter_file = field_validator("jmeter_file")(
        _validate_repository_file
    )


class LoadEvidenceCapture(StrictModel):
    """Define trusted inputs for deterministic load evidence rendering."""

    schema_version: Literal["1.0.0"] = Field(alias="schemaVersion")
    captured_at: AwareDatetime = Field(alias="capturedAt")
    baseline_start: AwareDatetime = Field(alias="baselineStart")
    test_run: LoadRunCapture = Field(alias="testRun")
    scale_configuration: LoadScaleCapture = Field(alias="scaleConfiguration")
    replicas: LoadMetricCapture
    database_signal: LoadMetricCapture = Field(alias="databaseSignal")
    recovery: LoadRecoveryCapture
    artifacts: LoadArtifactCapture

    @model_validator(mode="after")
    def validate_contract(self) -> "LoadEvidenceCapture":
        """Enforce frozen metric identities and capture ordering."""
        if (
            self.replicas.metric_name != "Replicas"
            or self.replicas.aggregation != "Maximum"
            or self.replicas.revision_name is None
        ):
            raise ValueError(
                "replicas must capture revision-filtered Replicas/Maximum/PT1M"
            )
        if (
            (
                self.database_signal.metric_name,
                self.database_signal.aggregation,
            )
            not in {
                ("app_cpu_billed", "Total"),
                ("cpu_percent", "Maximum"),
            }
            or self.database_signal.revision_name is not None
        ):
            raise ValueError(
                "databaseSignal must use a frozen family metric without a revision"
            )
        if self.scale_configuration.observed_at > self.baseline_start:
            raise ValueError(
                "scale configuration must be observed no later than baseline start"
            )
        if self.captured_at < self.recovery.observed_at:
            raise ValueError("capturedAt must not precede recovery observedAt")
        if len(
            {
                self.test_run.file,
                self.scale_configuration.file,
                self.replicas.file,
                self.database_signal.file,
            }
        ) != 4:
            raise ValueError("raw capture files must be distinct")
        return self


class WorkflowRunObservation(CicdObservation):
    """Bind a normalized CI/CD observation to one immutable workflow attempt."""

    run_id: StrictInt = Field(alias="runId", ge=1)
    run_attempt: StrictInt = Field(alias="runAttempt", ge=1)
    github_repository: str = Field(
        alias="githubRepository", pattern=r"^[^/\s]+/[^/\s]+$"
    )
    workflow_path: str = Field(
        alias="workflowPath",
        pattern=r"^\.github/workflows/catalog-(?:dotnet|java)\.yml$",
    )
    head_sha: str = Field(alias="headSha", pattern=r"^[0-9a-f]{40}$")
    ref: str = Field(pattern=r"^refs/(?:heads|tags)/.+$")


class WorkflowJobObservation(StrictModel):
    """Represent one completed environment-bound job in a GitHub run."""

    job_id: StrictInt = Field(alias="jobId", ge=1)
    name: Literal["staging", "production"]
    environment: Literal["staging", "production"]
    status: Literal["completed"]
    conclusion: Literal["success"]
    started_at: AwareDatetime = Field(alias="startedAt")
    completed_at: AwareDatetime = Field(alias="completedAt")

    @model_validator(mode="after")
    def validate_window(self) -> "WorkflowJobObservation":
        """Require each observed GitHub job to have a positive run window."""
        if self.started_at >= self.completed_at:
            raise ValueError("workflow job completion must follow its start")
        if self.name != self.environment:
            raise ValueError("workflow job name must match its environment")
        return self


class GitHubRunObservation(WorkflowRunObservation):
    """Represent immutable GitHub workflow metadata and its exact jobs."""

    status: Literal["completed"]
    conclusion: Literal["success"]
    event: Literal["workflow_dispatch"]
    jobs: list[WorkflowJobObservation] = Field(min_length=2, max_length=2)
    captured_at: AwareDatetime = Field(alias="capturedAt")

    @model_validator(mode="after")
    def validate_jobs(self) -> "GitHubRunObservation":
        """Require exactly one successful staging and production job."""
        if {job.name for job in self.jobs} != {"staging", "production"}:
            raise ValueError("workflow run must contain staging and production jobs")
        return self


class BuildObservation(WorkflowRunObservation):
    """Represent the immutable image produced by one successful workflow run."""

    source_commit: str = Field(alias="sourceCommit", pattern=r"^[0-9a-f]{40}$")
    registry_resource_id: str = Field(
        alias="registryResourceId", pattern=r"^/subscriptions/"
    )
    repository: str = Field(min_length=1)
    tag: str = Field(pattern=r"^[0-9a-f]{40}$")
    digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    reference: str = Field(pattern=r"^[^@]+@sha256:[0-9a-f]{64}$")
    completed_at: AwareDatetime = Field(alias="completedAt")
    status: Literal["success"]


class FederatedCredentialObservation(StrictModel):
    """Represent one observed managed-identity federated credential."""

    environment: Literal["staging", "production"]
    resource_id: str = Field(
        alias="resourceId",
        pattern=(
            r"^/subscriptions/.+/providers/Microsoft\.ManagedIdentity/"
            r"userAssignedIdentities/.+/federatedIdentityCredentials/.+$"
        ),
    )
    subject: str = Field(
        pattern=r"^repo:[^/]+/[^:]+:environment:(?:staging|production)$"
    )
    issuer: Literal["https://token.actions.githubusercontent.com"]
    audiences: list[Literal["api://AzureADTokenExchange"]] = Field(
        min_length=1, max_length=1
    )


class RoleAssignmentObservation(StrictModel):
    """Represent one observed Azure role assignment for the workflow principal."""

    resource_id: str = Field(
        alias="resourceId",
        pattern=(
            r"^/subscriptions/.+/providers/Microsoft\.Authorization/"
            r"roleAssignments/[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-"
            r"[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
        ),
    )
    principal_id: str = Field(
        alias="principalId",
        pattern=(
            r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
            r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
        ),
    )
    role_definition_id: str = Field(
        alias="roleDefinitionId",
        pattern=r"^[0-9a-fA-F]{8}-[0-9a-fA-F-]{27,}$",
    )
    scope: str = Field(pattern=r"^/subscriptions/")


class RoleAssignmentEnumerationObservation(StrictModel):
    """Describe the unfiltered Azure CLI assignment enumeration."""

    assignee_object_id: str = Field(
        alias="assigneeObjectId",
        pattern=(
            r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
            r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
        ),
    )
    execution_boundary: Literal["facilitator-session"] = Field(
        alias="executionBoundary"
    )
    subscription_id: str = Field(
        alias="subscriptionId",
        pattern=(
            r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
            r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
        ),
    )
    required_permission: Literal[
        "Microsoft.Authorization/roleAssignments/read"
    ] = Field(alias="requiredPermission")
    minimum_built_in_role: Literal["Reader"] = Field(alias="minimumBuiltInRole")
    command: str = Field(min_length=1)
    raw_result_file: str = Field(
        alias="rawResultFile",
        pattern=r"^evidence/cicd/[a-z0-9-]+\.raw\.json$",
    )
    raw_result_sha256: str = Field(
        alias="rawResultSha256",
        pattern=r"^[0-9a-f]{64}$",
    )
    performed_at: AwareDatetime = Field(alias="performedAt")
    all_assignments: StrictBool = Field(alias="all")
    include_inherited: StrictBool = Field(alias="includeInherited")
    fill_principal_name: StrictBool = Field(alias="fillPrincipalName")
    fill_role_definition_name: StrictBool = Field(alias="fillRoleDefinitionName")
    filtered: StrictBool

    @model_validator(mode="after")
    def require_exhaustive_query(self) -> "RoleAssignmentEnumerationObservation":
        """Require the complete principal assignment query without Graph enrichment."""
        if (
            not self.all_assignments
            or not self.include_inherited
            or self.fill_principal_name
            or self.fill_role_definition_name
            or self.filtered
        ):
            raise ValueError(
                "role assignment enumeration must be complete and unfiltered"
            )
        expected_command = (
            "az role assignment list --all --include-inherited "
            f"--assignee-object-id {self.assignee_object_id} "
            "--fill-principal-name false --fill-role-definition-name false "
            "--output json"
        )
        if self.command != expected_command:
            raise ValueError(
                "role assignment enumeration command differs from the frozen CLI"
            )
        return self


class IdentityObservation(WorkflowRunObservation):
    """Represent observed GitHub OIDC claims and exact Azure RBAC scopes."""

    identity_kind: Literal["user-assigned-managed-identity"] = Field(
        alias="identityKind"
    )
    resource_id: str = Field(
        alias="resourceId",
        pattern=(
            r"^/subscriptions/.+/providers/Microsoft\.ManagedIdentity/"
            r"userAssignedIdentities/.+$"
        ),
    )
    client_id: str = Field(
        alias="clientId",
        pattern=(
            r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
            r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
        ),
    )
    principal_id: str = Field(
        alias="principalId",
        pattern=(
            r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
            r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
        ),
    )
    staging_federated_subject: str = Field(
        alias="stagingFederatedSubject",
        pattern=r"^repo:[^/]+/[^:]+:environment:staging$",
    )
    production_federated_subject: str = Field(
        alias="productionFederatedSubject",
        pattern=r"^repo:[^/]+/[^:]+:environment:production$",
    )
    acr_role_definition_id: Literal[
        "8311e382-0749-4cb8-b61a-304f252e45ec"
    ] = Field(alias="acrRoleDefinitionId")
    acr_scope: str = Field(alias="acrScope", pattern=r"^/subscriptions/")
    container_app_role_definition_id: Literal[
        "358470bc-b998-42bd-ab17-a7e34c199c0f"
    ] = Field(alias="containerAppRoleDefinitionId")
    container_app_scope: str = Field(
        alias="containerAppScope", pattern=r"^/subscriptions/"
    )
    client_secret_used: StrictBool = Field(alias="clientSecretUsed")
    registry_admin_used: StrictBool = Field(alias="registryAdminUsed")
    federated_credentials: list[FederatedCredentialObservation] = Field(
        alias="federatedCredentials", min_length=2, max_length=2
    )
    role_assignments: list[RoleAssignmentObservation] = Field(
        alias="roleAssignments", min_length=2, max_length=2
    )
    role_assignment_enumeration: RoleAssignmentEnumerationObservation = Field(
        alias="roleAssignmentEnumeration"
    )
    observed_at: AwareDatetime = Field(alias="observedAt")

    @model_validator(mode="after")
    def validate_forbidden_credentials(self) -> "IdentityObservation":
        """Require secret-free OIDC and managed-identity authentication."""
        if self.client_secret_used or self.registry_admin_used:
            raise ValueError("workflow identity must not use credential secrets")
        return self


class RevisionObservation(WorkflowRunObservation):
    """Represent one observed Azure Container Apps revision."""

    container_app_resource_id: str = Field(
        alias="containerAppResourceId", pattern=r"^/subscriptions/"
    )
    revision_name: str = Field(alias="revisionName", min_length=1)
    image_reference: str = Field(
        alias="imageReference", pattern=r"^[^@]+@sha256:[0-9a-f]{64}$"
    )
    active: StrictBool
    health_state: Literal["Healthy"] = Field(alias="healthState")
    traffic_weight: StrictInt = Field(alias="trafficWeight", ge=0, le=100)
    label: str | None = None
    label_url: AnyHttpUrl | None = Field(default=None, alias="labelUrl")
    observed_at: AwareDatetime = Field(alias="observedAt")


class SmokeObservation(WorkflowRunObservation):
    """Represent candidate-label smoke checks from a workflow."""

    candidate_url: AnyHttpUrl = Field(alias="candidateUrl")
    health_url: AnyHttpUrl = Field(alias="healthUrl")
    readiness_url: AnyHttpUrl = Field(alias="readinessUrl")
    revision_name: str = Field(alias="revisionName", min_length=1)
    image_reference: str = Field(
        alias="imageReference", pattern=r"^[^@]+@sha256:[0-9a-f]{64}$"
    )
    observed_at: AwareDatetime = Field(alias="observedAt")
    health_status: StrictInt = Field(alias="healthStatus", ge=200, le=200)
    readiness_status: StrictInt = Field(alias="readinessStatus", ge=200, le=200)


class ApprovalObservation(WorkflowRunObservation):
    """Represent one GitHub environment approval for a workflow run."""

    environment: Literal["production"]
    reviewer: str = Field(min_length=1)
    approved_at: AwareDatetime = Field(alias="approvedAt")
    state: Literal["approved"]


class TrafficObservation(WorkflowRunObservation):
    """Represent observed traffic and health for two retained revisions."""

    container_app_resource_id: str = Field(
        alias="containerAppResourceId", pattern=r"^/subscriptions/"
    )
    previous_revision: str = Field(alias="previousRevision", min_length=1)
    candidate_revision: str = Field(alias="candidateRevision", min_length=1)
    previous_weight: StrictInt = Field(alias="previousWeight", ge=0, le=100)
    candidate_weight: StrictInt = Field(alias="candidateWeight", ge=0, le=100)
    previous_active: StrictBool = Field(alias="previousActive")
    candidate_active: StrictBool = Field(alias="candidateActive")
    previous_health_state: Literal["Healthy"] = Field(alias="previousHealthState")
    candidate_health_state: Literal["Healthy"] = Field(alias="candidateHealthState")
    application_url: AnyHttpUrl = Field(alias="applicationUrl")
    health_url: AnyHttpUrl = Field(alias="healthUrl")
    readiness_url: AnyHttpUrl = Field(alias="readinessUrl")
    health_status: StrictInt = Field(alias="healthStatus", ge=200, le=200)
    readiness_status: StrictInt = Field(alias="readinessStatus", ge=200, le=200)
    observed_at: AwareDatetime = Field(alias="observedAt")

    @model_validator(mode="after")
    def validate_weights(self) -> "TrafficObservation":
        """Require the two declared revision weights to account for all traffic."""
        if self.previous_weight + self.candidate_weight != 100:
            raise ValueError("revision traffic weights must total 100")
        return self


class RollbackSafetyObservation(WorkflowRunObservation):
    """Represent the fail-safe promotion and rollback lifecycle."""

    mechanism: Literal["shell-trap"]
    guard_installed_at: AwareDatetime = Field(alias="guardInstalledAt")
    promotion_attempted_at: AwareDatetime = Field(alias="promotionAttemptedAt")
    rollback_attempted_at: AwareDatetime = Field(alias="rollbackAttemptedAt")
    rollback_completed_at: AwareDatetime = Field(alias="rollbackCompletedAt")
    executes_on_failure: Literal[True] = Field(alias="executesOnFailure")
    promotion_succeeded: Literal[True] = Field(alias="promotionSucceeded")
    rollback_succeeded: Literal[True] = Field(alias="rollbackSucceeded")

    @model_validator(mode="after")
    def validate_lifecycle(self) -> "RollbackSafetyObservation":
        """Require the guard before promotion and a completed rollback after it."""
        if not (
            self.guard_installed_at
            <= self.promotion_attempted_at
            < self.rollback_attempted_at
            <= self.rollback_completed_at
        ):
            raise ValueError("rollback safety lifecycle timestamps are out of order")
        return self


class QueryResultRow(StrictModel):
    """Represent one timestamped workbook query result."""

    timestamp: AwareDatetime


class ScalarQueryResultRow(QueryResultRow):
    """Represent one positive scalar workbook result."""

    value: StrictFloat = Field(gt=0)


class ErrorRateResultRow(QueryResultRow):
    """Represent an exercised HTTP error-rate result."""

    value: StrictFloat = Field(gt=0, le=100)
    total_requests: StrictInt = Field(alias="totalRequests", gt=0)
    failed_requests: StrictInt = Field(alias="failedRequests", gt=0)

    @model_validator(mode="after")
    def validate_request_counts(self) -> "ErrorRateResultRow":
        """Require failures to be a subset of the measured requests."""
        if self.failed_requests > self.total_requests:
            raise ValueError("failedRequests cannot exceed totalRequests")
        expected = 100.0 * self.failed_requests / self.total_requests
        if not math.isclose(self.value, expected, rel_tol=1e-9, abs_tol=1e-9):
            raise ValueError("error-rate value differs from request counts")
        return self


class CountQueryResultRow(QueryResultRow):
    """Represent one positive integral count."""

    value: StrictInt = Field(gt=0)


class ReplicaQueryResultRow(QueryResultRow):
    """Represent one app-scoped ACA replica count."""

    value: StrictInt = Field(ge=1)


class QueryObservationBase(ObservabilityObservation):
    """Bind one normalized workbook result to exact query inputs."""

    query_id: str = Field(alias="queryId", min_length=1)
    result_kind: str = Field(alias="resultKind", min_length=1)
    application_insights_resource_id: str = Field(
        alias="applicationInsightsResourceId", pattern=r"^/subscriptions/"
    )
    log_analytics_workspace_resource_id: str = Field(
        alias="logAnalyticsWorkspaceResourceId", pattern=r"^/subscriptions/"
    )
    source_commit: str = Field(alias="sourceCommit", pattern=r"^[0-9a-f]{40}$")
    revision_name: str = Field(alias="revisionName", min_length=1)
    service_name: str = Field(alias="serviceName", min_length=1)
    query: str = Field(min_length=1)
    query_sha256: str = Field(alias="querySha256", pattern=r"^[0-9a-f]{64}$")
    window_start: AwareDatetime = Field(alias="windowStart")
    window_end: AwareDatetime = Field(alias="windowEnd")
    captured_at: AwareDatetime = Field(alias="capturedAt")

    def _validate_result_window(self, rows: list[QueryResultRow]) -> None:
        """Require result rows and capture to fall in the declared query window."""
        if self.window_start >= self.window_end:
            raise ValueError("query window end must follow its start")
        if self.captured_at < self.window_end:
            raise ValueError("query capture must not precede its window end")
        if any(
            row.timestamp < self.window_start or row.timestamp > self.window_end
            for row in rows
        ):
            raise ValueError("query rows must fall within the declared window")


class ErrorRateQueryObservation(QueryObservationBase):
    """Represent exact error-rate query output."""

    query_id: Literal["error-rate"] = Field(alias="queryId")
    result_kind: Literal["error-rate"] = Field(alias="resultKind")
    rows: list[ErrorRateResultRow] = Field(min_length=1, max_length=1)

    @model_validator(mode="after")
    def validate_rows(self) -> "ErrorRateQueryObservation":
        """Validate the error-rate result window."""
        self._validate_result_window(self.rows)
        return self


class LatencyQueryObservation(QueryObservationBase):
    """Represent exact p95 HTTP latency output in milliseconds."""

    query_id: Literal["latency"] = Field(alias="queryId")
    result_kind: Literal["duration-ms"] = Field(alias="resultKind")
    rows: list[ScalarQueryResultRow] = Field(min_length=1, max_length=1)

    @model_validator(mode="after")
    def validate_rows(self) -> "LatencyQueryObservation":
        """Validate the latency result window."""
        self._validate_result_window(self.rows)
        return self


class DatabaseFailureQueryObservation(QueryObservationBase):
    """Represent exact failed database dependency count output."""

    query_id: Literal["database-dependency-failures"] = Field(alias="queryId")
    result_kind: Literal["failure-count"] = Field(alias="resultKind")
    rows: list[CountQueryResultRow] = Field(min_length=1, max_length=1)

    @model_validator(mode="after")
    def validate_rows(self) -> "DatabaseFailureQueryObservation":
        """Validate the database-failure result window."""
        self._validate_result_window(self.rows)
        return self


class ReplicaQueryObservation(QueryObservationBase):
    """Represent exact app-scoped replica metric output."""

    query_id: Literal["replica-count"] = Field(alias="queryId")
    result_kind: Literal["container-app-peak-replica-count"] = Field(
        alias="resultKind"
    )
    rows: list[ReplicaQueryResultRow] = Field(min_length=1, max_length=1)

    @model_validator(mode="after")
    def validate_rows(self) -> "ReplicaQueryObservation":
        """Validate the replica result window."""
        self._validate_result_window(self.rows)
        return self


class ColdStartQueryObservation(QueryObservationBase):
    """Represent first-request observations for new ACA role instances."""

    query_id: Literal["cold-starts"] = Field(alias="queryId")
    result_kind: Literal["instance-first-request-count"] = Field(alias="resultKind")
    rows: list[CountQueryResultRow] = Field(min_length=1, max_length=1)

    @model_validator(mode="after")
    def validate_rows(self) -> "ColdStartQueryObservation":
        """Validate the cold-start proxy result window."""
        self._validate_result_window(self.rows)
        return self


class WorkbookObservation(ObservabilityObservation):
    """Represent deployed workbook content captured from Azure Resource Manager."""

    workbook_resource_id: str = Field(
        alias="workbookResourceId",
        pattern=r"^/subscriptions/.+/providers/Microsoft\.Insights/workbooks/",
    )
    application_insights_resource_id: str = Field(
        alias="applicationInsightsResourceId", pattern=r"^/subscriptions/"
    )
    log_analytics_workspace_resource_id: str = Field(
        alias="logAnalyticsWorkspaceResourceId", pattern=r"^/subscriptions/"
    )
    source_id: str = Field(alias="sourceId", pattern=r"^/subscriptions/")
    api_version: Literal["2023-06-01"] = Field(alias="apiVersion")
    source_commit: str = Field(alias="sourceCommit", pattern=r"^[0-9a-f]{40}$")
    revision_name: str = Field(alias="revisionName", min_length=1)
    template_sha256: str = Field(alias="templateSha256", pattern=r"^[0-9a-f]{64}$")
    queries_sha256: str = Field(alias="queriesSha256", pattern=r"^[0-9a-f]{64}$")
    serialized_data: str = Field(alias="serializedData", min_length=1)
    serialized_data_sha256: str = Field(
        alias="serializedDataSha256", pattern=r"^[0-9a-f]{64}$"
    )
    deployed_at: AwareDatetime = Field(alias="deployedAt")
    captured_at: AwareDatetime = Field(alias="capturedAt")


class DiagnosticSettingObservation(ObservabilityObservation):
    """Represent ACA metric export into the handoff Log Analytics workspace."""

    container_app_resource_id: str = Field(
        alias="containerAppResourceId", pattern=r"^/subscriptions/"
    )
    workspace_resource_id: str = Field(
        alias="workspaceResourceId", pattern=r"^/subscriptions/"
    )
    diagnostic_setting_name: Literal["all-metrics-to-workspace"] = Field(
        alias="diagnosticSettingName"
    )
    metric_category: Literal["AllMetrics"] = Field(alias="metricCategory")
    destination_table: Literal["AzureMetrics"] = Field(alias="destinationTable")
    enabled: StrictBool
    observed_at: AwareDatetime = Field(alias="observedAt")

    @field_validator("enabled")
    @classmethod
    def require_enabled(cls, value: bool) -> bool:
        """Require the observed diagnostic setting to be enabled."""
        if not value:
            raise ValueError("diagnostic setting must be enabled")
        return value
