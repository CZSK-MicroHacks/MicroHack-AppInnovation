"""Cross-resource validation for Challenge 2 through Challenge 4 evidence."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Literal, TypeVar
from urllib.parse import urlsplit, urlunsplit

from jsonschema import Draft202012Validator, FormatChecker
from pydantic import BaseModel

from catalog_acceptance.handoff import validate_handoff
from catalog_acceptance.models.shared_challenges import (
    ApprovalObservation,
    BuildObservation,
    ColdStartQueryObservation,
    DatabaseFailureQueryObservation,
    DiagnosticSettingObservation,
    ErrorRateQueryObservation,
    GitHubRunObservation,
    HealthObservation,
    IdentityObservation,
    LoadRunObservation,
    MetricObservation,
    LatencyQueryObservation,
    QueryObservationBase,
    ReplicaQueryObservation,
    RoleAssignmentEnumerationObservation,
    RevisionObservation,
    RollbackSafetyObservation,
    ScaleConfigurationObservation,
    SmokeObservation,
    TrafficObservation,
    WorkbookObservation,
    WorkflowRunObservation,
)

ChallengeKind = Literal["load", "cicd", "observability"]
Observation = TypeVar("Observation", bound=BaseModel)
_PACKAGE_REPOSITORY_ROOT = Path(__file__).absolute().parents[3]


def _reject_nonfinite_json_constant(value: str) -> None:
    """Reject non-standard numeric constants during JSON decoding."""
    raise ValueError(f"non-finite JSON constant is forbidden: {value}")


def _reject_duplicate_json_members(
    pairs: list[tuple[str, Any]],
) -> dict[str, Any]:
    """Build one JSON object while rejecting duplicate member names."""
    value: dict[str, Any] = {}
    for key, child in pairs:
        if key in value:
            raise ValueError(f"duplicate JSON member is forbidden: {key}")
        value[key] = child
    return value


def _load_json(path: Path) -> dict[str, Any]:
    """Load one strict JSON object from disk."""
    with path.open(encoding="utf-8") as handle:
        value = json.load(
            handle,
            parse_constant=_reject_nonfinite_json_constant,
            object_pairs_hook=_reject_duplicate_json_members,
        )
    if not isinstance(value, dict):
        raise ValueError(f"expected a JSON object: {path}")
    return value


def _load_json_array(path: Path) -> list[Any]:
    """Load one strict JSON array from disk."""
    with path.open(encoding="utf-8") as handle:
        value = json.load(
            handle,
            parse_constant=_reject_nonfinite_json_constant,
            object_pairs_hook=_reject_duplicate_json_members,
        )
    if not isinstance(value, list):
        raise ValueError(f"expected a JSON array: {path}")
    return value


def _same_resource(left: str, right: str) -> bool:
    """Compare Azure resource IDs using their case-insensitive semantics."""
    return left.rstrip("/").casefold() == right.rstrip("/").casefold()


def _subscription_scope(resource_id: str) -> str:
    """Return the subscription resource ID that owns one Azure resource."""
    parts = resource_id.strip("/").split("/")
    if (
        len(parts) < 2
        or parts[0].casefold() != "subscriptions"
        or not parts[1]
    ):
        raise ValueError(f"Azure resource is not subscription-scoped: {resource_id}")
    return f"/subscriptions/{parts[1]}"


def _parse_time(value: str) -> datetime:
    """Parse one schema-validated timestamp into an aware datetime."""
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("evidence timestamps must include a timezone")
    return parsed


def _revision_label_url(application_url: str, label: str) -> str:
    """Derive the official APP_NAME---LABEL Container Apps FQDN."""
    parsed = urlsplit(application_url)
    hostname = parsed.hostname
    if parsed.scheme != "https" or not hostname or "." not in hostname:
        raise ValueError("handoff application URL cannot derive a revision label FQDN")
    app_name, suffix = hostname.split(".", 1)
    return urlunsplit(
        ("https", f"{app_name}---{label}.{suffix}", "", "", "")
    ).rstrip("/")


def _sha256(path: Path) -> str:
    """Return the lowercase SHA-256 digest of one evidence file."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _sha256_text(value: str) -> str:
    """Return the lowercase SHA-256 digest of UTF-8 text."""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _require(condition: bool, message: str) -> None:
    """Raise a stable validation error when a contract invariant is false."""
    if not condition:
        raise ValueError(message)


def _read_control_commit_blob(
    repository_root: Path,
    commit_sha: str,
    repository_path: str,
) -> bytes:
    """Read one exact Git blob from the declared workflow control commit."""
    try:
        result = subprocess.run(
            [
                "git",
                "-C",
                str(repository_root),
                "cat-file",
                "blob",
                f"{commit_sha}:{repository_path}",
            ],
            check=False,
            capture_output=True,
            timeout=10,
        )
    except OSError as error:
        raise ValueError("git is unavailable for workflow control validation") from error
    except subprocess.TimeoutExpired as error:
        raise ValueError("workflow control commit lookup timed out") from error
    if result.returncode != 0:
        raise ValueError(
            "workflow control commit does not contain the declared handoff"
        )
    return result.stdout


def _resolve_evidence_file(repository_root: Path, value: str) -> Path:
    """Resolve one non-empty regular evidence file without symlink traversal."""
    root = repository_root.resolve()
    declared = _reject_repository_symlinks(root, value)
    resolved = declared.resolve()
    try:
        resolved.relative_to(root)
    except ValueError as error:
        raise ValueError(
            f"shared challenge evidence escapes the repository: {value}"
        ) from error
    if not resolved.is_file() or resolved.stat().st_size == 0:
        raise FileNotFoundError(
            f"shared challenge evidence must be a non-empty file: {resolved}"
        )
    return resolved


def _reject_repository_symlinks(repository_root: Path, value: str) -> Path:
    """Return one declared path after rejecting traversal and symlink components."""
    root = repository_root.resolve()
    relative = Path(value)
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError(f"shared challenge evidence path is invalid: {value}")
    declared = root
    for part in relative.parts:
        declared /= part
        if declared.is_symlink():
            raise ValueError(
                f"shared challenge evidence path contains a symlink: {declared}"
            )
    return declared


def _reject_consumed_tree_symlinks(repository_root: Path, value: str) -> None:
    """Reject symlinks anywhere below a referenced directory consumed recursively."""
    declared = _reject_repository_symlinks(repository_root, value)
    if not declared.is_dir():
        return
    for directory, child_directories, filenames in os.walk(
        declared, followlinks=False
    ):
        parent = Path(directory)
        for name in (*child_directories, *filenames):
            child = parent / name
            if child.is_symlink():
                raise ValueError(
                    f"shared challenge evidence path contains a symlink: {child}"
                )


def _validated_contracts_directory(contracts_directory: Path) -> Path:
    """Bind validation to the checked-in, symlink-free contract tree."""
    expected = (_PACKAGE_REPOSITORY_ROOT / "workshop/contracts").absolute()
    declared = contracts_directory.absolute()
    if declared != expected:
        raise ValueError(
            "contracts directory must be the checked-in workshop/contracts tree"
        )
    _reject_consumed_tree_symlinks(
        _PACKAGE_REPOSITORY_ROOT,
        "workshop/contracts",
    )
    if not expected.is_dir():
        raise FileNotFoundError(f"contracts directory does not exist: {expected}")
    return expected.resolve()


def _validate_handoff_reference_paths(
    handoff: dict[str, Any],
    repository_root: Path,
) -> None:
    """Reject symlink traversal in every file or directory consumed by handoff validation."""
    direct_references = [
        handoff["acceptance"]["report"],
        handoff["deployment"]["iacPath"],
        handoff["deployment"]["targetOutput"],
        handoff["rollback"]["runbook"],
        handoff["evidence"]["migrationReport"],
        handoff["evidence"]["telemetryReport"],
        handoff["evidence"]["runtimeTestReport"],
        *handoff["evidence"]["pathEvidence"],
    ]
    for reference in direct_references:
        _reject_consumed_tree_symlinks(repository_root, reference)

    nested_references = (
        (
            handoff["evidence"]["telemetryReport"],
            lambda value: [
                query["resultFile"] for query in value.get("queries", {}).values()
            ],
        ),
        (
            handoff["evidence"]["runtimeTestReport"],
            lambda value: [value["artifact"]] if "artifact" in value else [],
        ),
    )
    for report_reference, references in nested_references:
        report_path = repository_root / report_reference
        if report_path.is_file():
            report = _load_json(report_path)
            for reference in references(report):
                _reject_consumed_tree_symlinks(repository_root, reference)


def _validate_referenced_files(value: Any, repository_root: Path) -> None:
    """Validate every recursively declared file reference in an evidence bundle."""
    if isinstance(value, dict):
        for key, child in value.items():
            if key.lower().endswith("file") and isinstance(child, str):
                _resolve_evidence_file(repository_root, child)
            else:
                _validate_referenced_files(child, repository_root)
    elif isinstance(value, list):
        for child in value:
            _validate_referenced_files(child, repository_root)


def _load_observation(
    repository_root: Path,
    value: str,
    model: type[Observation],
) -> Observation:
    """Load and validate one normalized observation file."""
    return model.model_validate(
        _load_json(_resolve_evidence_file(repository_root, value))
    )


def _require_workflow_binding(
    observation: WorkflowRunObservation,
    workflow: GitHubRunObservation,
) -> None:
    """Bind one normalized CI observation to the same immutable GitHub run."""
    values = (
        observation.run_id == workflow.run_id,
        observation.run_attempt == workflow.run_attempt,
        observation.github_repository == workflow.github_repository,
        observation.workflow_path == workflow.workflow_path,
        observation.head_sha == workflow.head_sha,
        observation.ref == workflow.ref,
    )
    _require(all(values), "CI/CD observation differs from the observed GitHub run")


def _workbook_queries(
    serialized_data: str,
    expected_workspace_resource_id: str,
) -> dict[str, str]:
    """Extract the exact named KQL panels from deployed workbook serialized data."""
    try:
        workbook = json.loads(
            serialized_data,
            parse_constant=_reject_nonfinite_json_constant,
        )
    except json.JSONDecodeError as error:
        raise ValueError("deployed workbook serializedData is not valid JSON") from error
    if not isinstance(workbook, dict) or workbook.get("version") != "Notebook/1.0":
        raise ValueError("deployed workbook has an unsupported serializedData format")
    items = workbook.get("items")
    if not isinstance(items, list):
        raise ValueError("deployed workbook serializedData has no items")
    queries: dict[str, str] = {}

    def visit(children: list[Any]) -> None:
        """Visit standard top-level and grouped Azure Workbook items."""
        for item in children:
            if not isinstance(item, dict):
                raise ValueError("deployed workbook contains a malformed item")
            content = item.get("content")
            if item.get("type") == 3:
                name = item.get("name")
                if (
                    not isinstance(name, str)
                    or not isinstance(content, dict)
                    or content.get("version") != "KqlItem/1.0"
                    or type(content.get("queryType")) is not int
                    or content["queryType"] != 0
                    or str(content.get("resourceType", "")).casefold()
                    != "microsoft.operationalinsights/workspaces"
                    or not isinstance(content.get("query"), str)
                ):
                    raise ValueError(
                        "deployed workbook contains a malformed Logs query panel"
                    )
                cross_component_resources = content.get("crossComponentResources")
                if cross_component_resources not in (None, []):
                    if (
                        not isinstance(cross_component_resources, list)
                        or len(cross_component_resources) != 1
                        or not isinstance(cross_component_resources[0], str)
                        or not _same_resource(
                            cross_component_resources[0],
                            expected_workspace_resource_id,
                        )
                    ):
                        raise ValueError(
                            "workbook panel cross-component resources differ "
                            "from the handoff workspace"
                        )
                if name in queries:
                    raise ValueError(f"deployed workbook repeats query panel {name}")
                queries[name] = content["query"]
            if isinstance(content, dict) and "items" in content:
                nested = content["items"]
                if not isinstance(nested, list):
                    raise ValueError("deployed workbook group items must be an array")
                visit(nested)

    visit(items)
    return queries


def _validate_schema(
    evidence: dict[str, Any],
    kind: ChallengeKind,
    contracts_directory: Path,
) -> None:
    """Validate one challenge bundle against its frozen JSON Schema."""
    schema_name = {
        "load": "load-test-evidence.schema.json",
        "cicd": "cicd-evidence.schema.json",
        "observability": "observability-evidence.schema.json",
    }[kind]
    schema = _load_json(contracts_directory / schema_name)
    Draft202012Validator(schema, format_checker=FormatChecker()).validate(evidence)


def _load_observability_query_contract(
    contracts_directory: Path,
) -> dict[str, Any]:
    """Load and schema-validate the frozen observability query declarations."""
    query_contract = _load_json(contracts_directory / "observability-queries.json")
    query_schema = _load_json(
        contracts_directory / "observability-queries.schema.json"
    )
    Draft202012Validator(
        query_schema, format_checker=FormatChecker()
    ).validate(query_contract)
    return query_contract


def render_observability_query_source(contracts_directory: Path) -> str:
    """Render the exact checked-in KQL source from frozen query templates."""
    query_contract = _load_observability_query_contract(contracts_directory)
    return (
        "\n\n".join(
            f"// query-id: {declaration['id']}\n{declaration['template']}"
            for declaration in query_contract["queries"]
        )
        + "\n"
    )


def render_observability_queries(
    evidence: dict[str, Any],
    handoff: dict[str, Any],
    contracts_directory: Path,
) -> dict[str, dict[str, str]]:
    """Render exact P6 KQL and hashes from frozen templates.

    Args:
        evidence: Schema-valid observability evidence containing the query window.
        handoff: Fully validated modernization handoff.
        contracts_directory: Directory containing the frozen query contract.

    Returns:
        Query text, result kind, and SHA-256 keyed by panel ID.

    Raises:
        ValueError: If a frozen template contains an unresolved parameter.
        jsonschema.ValidationError: If the query contract violates its schema.
    """
    query_contract = _load_observability_query_contract(contracts_directory)
    replacements = {
        "__START_TIME__": evidence["window"]["startTime"],
        "__END_TIME__": evidence["window"]["endTime"],
        "__APPLICATION_INSIGHTS_RESOURCE_ID__": handoff["observability"][
            "applicationInsightsResourceId"
        ],
        "__CONTAINER_APP_RESOURCE_ID__": handoff["application"]["resourceId"],
        "__SERVICE_NAME__": handoff["observability"]["serviceName"],
        "__SOURCE_COMMIT__": handoff["source"]["commitSha"],
        "__REVISION_NAME__": handoff["application"]["revisionName"],
    }
    rendered: dict[str, dict[str, str]] = {}
    for declaration in query_contract["queries"]:
        query = declaration["template"]
        for parameter, value in replacements.items():
            query = query.replace(parameter, value)
        unresolved = [
            parameter
            for parameter in query_contract["parameters"]
            if parameter in query
        ]
        if unresolved:
            raise ValueError(
                f"observability query {declaration['id']} has unresolved parameters"
            )
        rendered[declaration["id"]] = {
            "query": query,
            "resultKind": declaration["resultKind"],
            "querySha256": _sha256_text(query),
        }
    return rendered


def _validate_common_subject(
    evidence: dict[str, Any],
    handoff: dict[str, Any],
) -> None:
    """Bind shared evidence identity to the validated modernization handoff."""
    subject = evidence["subject"]
    checks = (
        (subject["sliceId"] == handoff["sliceId"], "sliceId differs from handoff"),
        (
            subject["sourceCommit"] == handoff["source"]["commitSha"],
            "sourceCommit differs from handoff",
        ),
        (
            subject["revisionName"] == handoff["application"]["revisionName"],
            "revisionName differs from handoff",
        ),
        (
            _same_resource(
                subject["containerAppResourceId"],
                handoff["application"]["resourceId"],
            ),
            "Container App resource differs from handoff",
        ),
    )
    for passed, message in checks:
        _require(passed, message)
    if "imageDigest" in subject:
        _require(
            subject["imageDigest"] == handoff["containerImage"]["digest"],
            "subject image digest differs from handoff",
        )


def _validate_load(
    evidence: dict[str, Any],
    handoff: dict[str, Any],
    repository_root: Path,
    handoff_path: Path,
) -> None:
    """Validate load success, scale-out, database load, and recovery observations."""
    from catalog_acceptance.load_evidence import (
        expected_database_metric_resource_id,
    )

    _validate_common_subject(evidence, handoff)
    capture = evidence["capture"]
    _require(
        capture["manifestSha256"]
        == _sha256(
            _resolve_evidence_file(repository_root, capture["manifestFile"])
        ),
        "load capture manifest digest differs from the referenced file",
    )
    subject = evidence["subject"]
    _require(
        subject["databaseFamily"] == handoff["database"]["family"],
        "load database family differs from handoff",
    )
    _require(
        subject["stack"] == handoff["source"]["stack"],
        "load stack differs from handoff",
    )
    _require(
        _same_resource(subject["databaseResourceId"], handoff["database"]["resourceId"]),
        "load database resource differs from handoff",
    )

    declared_run = evidence["testRun"]
    captured_at = _parse_time(evidence["capturedAt"])
    windows = {key: _parse_time(value) for key, value in evidence["windows"].items()}
    _require(
        windows["baselineStart"]
        < windows["loadStart"]
        < windows["loadEnd"]
        < windows["recoveryEnd"],
        "load evidence windows are not strictly ordered",
    )
    _require(
        windows["loadStart"] == _parse_time(declared_run["startedAt"])
        and windows["loadEnd"] == _parse_time(declared_run["completedAt"]),
        "load evidence windows differ from the declared test run",
    )
    _require(
        windows["loadEnd"] - windows["loadStart"]
        == timedelta(seconds=declared_run["durationSeconds"]),
        "load duration differs from the observed run timestamps",
    )
    _require(
        windows["recoveryEnd"] - windows["loadEnd"]
        == timedelta(seconds=evidence["recovery"]["withinSeconds"]),
        "recovery deadline differs from the declared duration",
    )
    run = _load_observation(
        repository_root,
        declared_run["resultFile"],
        LoadRunObservation,
    )
    for actual, expected, message in (
        (run.test_run_id, declared_run["testRunId"], "test run ID differs"),
        (run.test_id, declared_run["testId"], "test ID differs"),
        (
            run.resource_id.casefold(),
            declared_run["resourceId"].casefold(),
            "load-test resource ID differs",
        ),
        (run.started_at.isoformat(), declared_run["startedAt"].replace("Z", "+00:00"), "test start differs"),
        (
            run.completed_at.isoformat(),
            declared_run["completedAt"].replace("Z", "+00:00"),
            "test completion differs",
        ),
        (run.virtual_users, declared_run["virtualUsers"], "virtual-user count differs"),
        (run.duration_seconds, declared_run["durationSeconds"], "duration differs"),
        (
            str(run.application_url).rstrip("/"),
            handoff["application"]["url"].rstrip("/"),
            "load run application URL differs from handoff",
        ),
        (
            str(run.target_url).rstrip("/"),
            f"{handoff['application']['url'].rstrip('/')}/perftest/catalog",
            "load run target URL differs from handoff",
        ),
        (
            run.revision_name,
            handoff["application"]["revisionName"],
            "load run revision differs from handoff",
        ),
        (
            run.configuration_sha256,
            declared_run["configurationSha256"],
            "load configuration digest differs",
        ),
        (
            run.jmeter_sha256,
            declared_run["jmeterSha256"],
            "JMeter digest differs",
        ),
    ):
        _require(actual == expected, message)
    _require(
        declared_run["applicationUrl"].rstrip("/")
        == handoff["application"]["url"].rstrip("/")
        and declared_run["targetUrl"].rstrip("/")
        == f"{handoff['application']['url'].rstrip('/')}/perftest/catalog",
        "declared load target differs from handoff",
    )
    _require(
        declared_run["configurationSha256"]
        == _sha256(
            _resolve_evidence_file(
                repository_root, declared_run["configurationFile"]
            )
        ),
        "declared load configuration digest differs from checked-in file",
    )
    _require(
        declared_run["jmeterSha256"]
        == _sha256(
            _resolve_evidence_file(repository_root, declared_run["jmeterFile"])
        ),
        "declared JMeter digest differs from checked-in file",
    )
    _require(
        run.completed_at <= run.captured_at <= captured_at,
        "load-run observation capture is outside the report window",
    )

    scale_declaration = evidence["scaleConfiguration"]
    scale = _load_observation(
        repository_root,
        scale_declaration["resultFile"],
        ScaleConfigurationObservation,
    )
    for passed, message in (
        (
            scale.source == scale_declaration["source"],
            "scale configuration is not an Azure Resource Manager observation",
        ),
        (
            _same_resource(
                scale.container_app_resource_id,
                handoff["application"]["resourceId"],
            )
            and _same_resource(
                scale_declaration["containerAppResourceId"],
                handoff["application"]["resourceId"],
            ),
            "observed scale configuration belongs to a different Container App",
        ),
        (
            scale.revision_name == handoff["application"]["revisionName"]
            == scale_declaration["revisionName"],
            "observed scale configuration belongs to a different revision",
        ),
        (
            scale.minimum_replicas
            == scale_declaration["minimumReplicas"]
            == evidence["replicas"]["minimumConfigured"],
            "observed minimum replicas differ from the frozen scale contract",
        ),
        (
            scale.maximum_replicas
            == scale_declaration["maximumReplicas"]
            == evidence["replicas"]["maximumConfigured"],
            "observed maximum replicas differ from the frozen scale contract",
        ),
        (
            scale.rule_name == scale_declaration["ruleName"]
            and scale.rule_type == scale_declaration["ruleType"]
            and scale.concurrent_requests
            == scale_declaration["concurrentRequests"],
            "observed HTTP scale rule differs from the frozen scale contract",
        ),
        (
            scale.observed_at.isoformat()
            == scale_declaration["observedAt"].replace("Z", "+00:00"),
            "scale configuration timestamp differs",
        ),
    ):
        _require(passed, message)
    _require(
        windows["baselineStart"] - timedelta(minutes=15)
        <= scale.observed_at
        <= windows["baselineStart"],
        "scale configuration was not observed immediately before the load window",
    )

    replica = _load_observation(
        repository_root,
        evidence["replicas"]["resultFile"],
        MetricObservation,
    )
    _require(
        _same_resource(replica.resource_id, handoff["application"]["resourceId"]),
        "replica observation is for a different Container App",
    )
    _require(
        _same_resource(
            evidence["replicas"]["resourceId"],
            handoff["application"]["resourceId"],
        ),
        "declared replica resource differs from handoff",
    )
    _require(replica.metric == "Replicas", "replica observation metric differs")
    _require(replica.aggregation == "Maximum", "replica aggregation differs")
    _require(
        replica.start_time <= windows["baselineStart"]
        and replica.end_time >= windows["recoveryEnd"],
        "replica observation does not cover all declared windows",
    )
    before = [
        point.value
        for point in replica.points
        if windows["baselineStart"] <= point.timestamp < windows["loadStart"]
    ]
    during = [
        point.value
        for point in replica.points
        if windows["loadStart"] <= point.timestamp <= windows["loadEnd"]
    ]
    recovery_deadline = windows["recoveryEnd"]
    after = [
        point
        for point in replica.points
        if windows["loadEnd"] < point.timestamp <= recovery_deadline
    ]
    _require(bool(before and during and after), "replica window lacks baseline, run, or recovery points")
    _require(
        max(before) == evidence["replicas"]["baselineObserved"] == 1,
        "observed replica baseline differs from metric output",
    )
    peak = max(during)
    _require(
        peak == evidence["replicas"]["peakObserved"],
        "observed replica peak differs from metric output",
    )
    _require(
        peak > max(before),
        "replica metric does not prove scale-out above baseline",
    )
    _require(
        evidence["replicas"]["minimumConfigured"]
        <= max(before)
        <= evidence["replicas"]["maximumConfigured"]
        and 2 <= peak <= evidence["replicas"]["maximumConfigured"],
        "replica observations fall outside the frozen 1-3 scale contract",
    )
    _require(
        all(
            evidence["replicas"]["minimumConfigured"]
            <= point.value
            <= evidence["replicas"]["maximumConfigured"]
            for point in replica.points
        ),
        "replica metric contains a value outside configured bounds",
    )
    _require(
        after[-1].value == evidence["replicas"]["minimumConfigured"],
        "final post-load replica point did not recover to the configured minimum",
    )
    _require(
        all(point.value.is_integer() for point in replica.points),
        "replica metric contains a fractional value",
    )

    database = _load_observation(
        repository_root,
        evidence["databaseSignal"]["resultFile"],
        MetricObservation,
    )
    declared_database = evidence["databaseSignal"]
    expected_database_resource_id = expected_database_metric_resource_id(handoff)
    _require(
        _same_resource(database.resource_id, expected_database_resource_id),
        "database metric is for a different resource",
    )
    _require(
        _same_resource(
            declared_database["resourceId"],
            expected_database_resource_id,
        ),
        "declared database metric resource differs from handoff",
    )
    expected_database_signal = {
        "azure-sql": ("app_cpu_billed", "Total"),
        "postgresql-flexible": ("cpu_percent", "Maximum"),
    }[handoff["database"]["family"]]
    _require(
        (
            declared_database["metric"],
            declared_database["aggregation"],
        )
        == expected_database_signal,
        "database metric does not match the handoff database family",
    )
    _require(database.metric == declared_database["metric"], "database metric differs")
    _require(
        database.aggregation == declared_database["aggregation"],
        "database metric aggregation differs",
    )
    _require(
        database.start_time <= windows["baselineStart"]
        and database.end_time >= windows["loadEnd"],
        "database observation does not cover baseline and load windows",
    )
    database_before = [
        point.value
        for point in database.points
        if windows["baselineStart"] <= point.timestamp < windows["loadStart"]
    ]
    database_during = [
        point.value
        for point in database.points
        if windows["loadStart"] <= point.timestamp <= windows["loadEnd"]
    ]
    _require(
        bool(database_before and database_during),
        "database metric window lacks baseline or load points",
    )
    baseline = max(database_before)
    database_peak = max(database_during)
    _require(
        baseline == declared_database["baseline"],
        "database baseline differs from metric output",
    )
    _require(
        database_peak == declared_database["peak"],
        "database peak differs from metric output",
    )
    _require(
        database_peak > baseline,
        "database metric does not prove load above baseline",
    )

    recovery = _load_observation(
        repository_root,
        evidence["recovery"]["resultFile"],
        HealthObservation,
    )
    _require(
        str(recovery.health_url).rstrip("/") == handoff["application"]["healthUrl"]
        and str(recovery.readiness_url).rstrip("/")
        == handoff["application"]["readinessUrl"],
        "recovery checks target different health or readiness URLs",
    )
    _require(
        evidence["recovery"]["healthUrl"] == handoff["application"]["healthUrl"]
        and evidence["recovery"]["readinessUrl"]
        == handoff["application"]["readinessUrl"],
        "declared recovery URLs differ from handoff",
    )
    _require(
        recovery.revision_name == handoff["application"]["revisionName"],
        "recovery checks target a different revision",
    )
    _require(
        windows["loadEnd"] < recovery.observed_at <= recovery_deadline,
        "recovery checks fall outside the declared recovery window",
    )
    _require(
        any(
            point.value == evidence["replicas"]["minimumConfigured"]
            and point.timestamp <= recovery.observed_at
            for point in after
        ),
        "health recovery was recorded before replica recovery",
    )
    _require(
        recovery.observed_at <= captured_at,
        "load report was captured before recovery evidence",
    )
    from catalog_acceptance.load_evidence import build_load_evidence

    expected_report, expected_observations = build_load_evidence(
        repository_root / evidence["capture"]["manifestFile"],
        handoff_path,
        repository_root,
    )
    _require(
        evidence == expected_report,
        "load report differs from deterministic raw-capture rendering",
    )
    for path, expected in expected_observations.items():
        _require(
            _load_json(_resolve_evidence_file(repository_root, path)) == expected,
            f"normalized load observation differs from raw capture: {path}",
        )


def _validate_role_assignment_raw_capture(
    enumeration: RoleAssignmentEnumerationObservation,
    identity: IdentityObservation,
    repository_root: Path,
) -> None:
    """Verify the facilitator's raw Azure CLI result against normalized roles."""
    raw_path = _resolve_evidence_file(
        repository_root,
        enumeration.raw_result_file,
    )
    _require(
        _sha256(raw_path) == enumeration.raw_result_sha256,
        "role assignment raw-result digest differs",
    )
    raw_assignments = _load_json_array(raw_path)
    normalized = {
        (
            assignment.resource_id.casefold(),
            assignment.principal_id.casefold(),
            assignment.role_definition_id.casefold(),
            assignment.scope.casefold(),
        )
        for assignment in identity.role_assignments
    }
    observed: set[tuple[str, str, str, str]] = set()
    role_definition_prefix = (
        f"/subscriptions/{enumeration.subscription_id}/providers/"
        "Microsoft.Authorization/roleDefinitions/"
    ).casefold()
    for index, value in enumerate(raw_assignments):
        if not isinstance(value, dict):
            raise ValueError(
                f"raw role assignment {index} must be an object"
            )
        fields = tuple(
            value.get(name)
            for name in ("id", "principalId", "roleDefinitionId", "scope")
        )
        if not all(isinstance(field, str) and field for field in fields):
            raise ValueError(
                f"raw role assignment {index} lacks exact identity fields"
            )
        role_definition_id = fields[2].casefold()
        if (
            not role_definition_id.startswith(role_definition_prefix)
            or "/" in role_definition_id.removeprefix(role_definition_prefix)
        ):
            raise ValueError(
                f"raw role assignment {index} has an invalid role definition ID"
            )
        observed.add(
            (
                fields[0].casefold(),
                fields[1].casefold(),
                role_definition_id.removeprefix(role_definition_prefix),
                fields[3].casefold(),
            )
        )
    _require(
        len(observed) == len(raw_assignments),
        "raw role assignment result contains duplicates",
    )
    _require(
        observed == normalized,
        "normalized role assignments differ from facilitator raw output",
    )


def _load_revision_states(
    declaration: dict[str, Any],
    container_app_resource_id: str,
    repository_root: Path,
) -> dict[str, dict[str, Any]]:
    """Load one digest-bound Container App revision-list response."""
    _require(
        declaration["source"] == "azure-container-app-revision-list",
        "revision state source is not the Azure revision list",
    )
    raw_path = _resolve_evidence_file(
        repository_root,
        declaration["rawResultFile"],
    )
    _require(
        _sha256(raw_path) == declaration["rawResultSha256"],
        "revision-list raw-result digest differs",
    )
    raw_revisions = _load_json_array(raw_path)
    states: dict[str, dict[str, Any]] = {}
    expected_id_prefix = (
        f"{container_app_resource_id.rstrip('/')}/revisions/".casefold()
    )
    for index, value in enumerate(raw_revisions):
        if not isinstance(value, dict):
            raise ValueError(f"raw revision {index} must be an object")
        name = value.get("name")
        resource_id = value.get("id")
        properties = value.get("properties")
        if (
            not isinstance(name, str)
            or not name
            or not isinstance(resource_id, str)
            or not resource_id.casefold().startswith(expected_id_prefix)
            or not isinstance(properties, dict)
        ):
            raise ValueError(
                f"raw revision {index} lacks exact Container App identity"
            )
        active = properties.get("active")
        health_state = properties.get("healthState")
        traffic_weight = properties.get("trafficWeight")
        template = properties.get("template")
        containers = (
            template.get("containers")
            if isinstance(template, dict)
            else None
        )
        if (
            not isinstance(active, bool)
            or not isinstance(health_state, str)
            or isinstance(traffic_weight, bool)
            or not isinstance(traffic_weight, int)
            or not isinstance(containers, list)
            or not containers
            or not all(
                isinstance(container, dict)
                and isinstance(container.get("image"), str)
                and container["image"]
                for container in containers
            )
        ):
            raise ValueError(f"raw revision {index} has invalid state fields")
        if name in states:
            raise ValueError(f"raw revision name is duplicated: {name}")
        states[name] = {
            "active": active,
            "healthState": health_state,
            "trafficWeight": traffic_weight,
            "images": [container["image"] for container in containers],
        }
    return states


def _validate_cicd(
    evidence: dict[str, Any],
    handoff: dict[str, Any],
    repository_root: Path,
) -> None:
    """Validate immutable CI/CD build, approval, promotion, and rollback evidence."""
    _validate_common_subject(evidence, handoff)
    workflow = evidence["workflow"]
    _require(
        evidence["subject"]["stack"] == handoff["source"]["stack"],
        "CI/CD stack differs from handoff",
    )
    expected_workflow = {
        "dotnet-sqlserver": ".github/workflows/catalog-dotnet.yml",
        "java-postgresql": ".github/workflows/catalog-java.yml",
    }[handoff["source"]["stack"]]
    _require(
        workflow["file"] == expected_workflow,
        "workflow file differs from the handoff stack",
    )
    _require(
        workflow["handoffFile"] == "evidence/modernization-contract.json",
        "workflow handoff path differs from the frozen control input",
    )
    _require(
        workflow["headSha"] != handoff["source"]["commitSha"],
        "workflow control SHA must differ from the handoff source commit",
    )
    handoff_path = _resolve_evidence_file(
        repository_root,
        workflow["handoffFile"],
    )
    control_handoff = _read_control_commit_blob(
        repository_root,
        workflow["headSha"],
        workflow["handoffFile"],
    )
    _require(
        workflow["handoffSha256"] == _sha256(handoff_path)
        and workflow["handoffSha256"]
        == hashlib.sha256(control_handoff).hexdigest(),
        "workflow handoff digest differs from the control-commit blob",
    )
    workflow_observation = _load_observation(
        repository_root,
        workflow["resultFile"],
        GitHubRunObservation,
    )
    for passed, message in (
        (
            str(workflow_observation.run_id) == workflow["runId"]
            and workflow_observation.run_attempt == workflow["runAttempt"],
            "observed GitHub workflow attempt differs",
        ),
        (
            workflow_observation.github_repository == workflow["repository"],
            "observed GitHub workflow repository differs",
        ),
        (
            workflow_observation.workflow_path == workflow["file"],
            "observed GitHub workflow path differs",
        ),
        (
            workflow_observation.head_sha == workflow["headSha"],
            "observed GitHub workflow head SHA differs from control commit",
        ),
        (
            workflow_observation.ref == workflow["ref"],
            "observed GitHub workflow ref differs",
        ),
        (
            workflow_observation.event == workflow["event"],
            "observed GitHub workflow event differs",
        ),
    ):
        _require(passed, message)
    observed_jobs = {job.name: job for job in workflow_observation.jobs}
    for environment in ("staging", "production"):
        declared_job = workflow["jobs"][environment]
        observed_job = observed_jobs[environment]
        _require(
            observed_job.job_id == declared_job["jobId"],
            f"observed {environment} GitHub job ID differs",
        )
        _require(
            observed_job.started_at.isoformat()
            == declared_job["startedAt"].replace("Z", "+00:00")
            and observed_job.completed_at.isoformat()
            == declared_job["completedAt"].replace("Z", "+00:00"),
            f"observed {environment} GitHub job window differs",
        )
    expected_staging = f"repo:{workflow['repository']}:environment:staging"
    expected_production = f"repo:{workflow['repository']}:environment:production"
    identity = evidence["identity"]
    expected_subscription_scope = _subscription_scope(identity["resourceId"])
    _require(
        all(
            _same_resource(
                _subscription_scope(resource_id),
                expected_subscription_scope,
            )
            for resource_id in (
                identity["acrScope"],
                identity["containerAppScope"],
                handoff["containerImage"]["registryResourceId"],
                handoff["application"]["resourceId"],
            )
        ),
        "workflow identity and handoff resources must share one subscription",
    )
    role_enumeration = identity["roleAssignmentEnumeration"]
    expected_subscription_id = expected_subscription_scope.split("/")[2]
    _require(
        role_enumeration["assigneeObjectId"].casefold()
        == identity["principalId"].casefold()
        and role_enumeration["subscriptionId"].casefold()
        == expected_subscription_id.casefold(),
        "declared role assignment enumeration differs from the workflow principal",
    )
    for environment in ("staging", "production"):
        job = workflow["jobs"][environment]
        _require(
            job["clientId"] == identity["clientId"]
            and job["principalId"] == identity["principalId"],
            f"{environment} job identity differs from the declared workflow identity",
        )
    _require(
        identity["stagingFederatedSubject"] == expected_staging,
        "staging OIDC subject differs from workflow repository",
    )
    _require(
        identity["productionFederatedSubject"] == expected_production,
        "production OIDC subject differs from workflow repository",
    )
    _require(
        workflow["jobs"]["staging"]["federatedSubject"] == expected_staging,
        "staging job used a different OIDC subject",
    )
    _require(
        workflow["jobs"]["production"]["federatedSubject"] == expected_production,
        "production job used a different OIDC subject",
    )
    _require(
        _same_resource(
            identity["acrScope"], handoff["containerImage"]["registryResourceId"]
        ),
        "AcrPush scope differs from handoff registry",
    )
    _require(
        _same_resource(
            identity["containerAppScope"], handoff["application"]["resourceId"]
        ),
        "Container Apps Contributor scope differs from handoff application",
    )
    identity_observation = _load_observation(
        repository_root,
        identity["resultFile"],
        IdentityObservation,
    )
    _require_workflow_binding(identity_observation, workflow_observation)
    for passed, message in (
        (
            str(identity_observation.run_id) == workflow["runId"]
            and identity_observation.run_attempt == workflow["runAttempt"],
            "OIDC observation workflow attempt differs",
        ),
        (
            identity_observation.github_repository == workflow["repository"],
            "OIDC observation repository differs",
        ),
        (
            identity_observation.client_id == identity["clientId"]
            and identity_observation.principal_id == identity["principalId"],
            "observed workflow identity differs",
        ),
        (
            _same_resource(identity_observation.resource_id, identity["resourceId"]),
            "observed managed identity resource differs",
        ),
        (
            identity_observation.staging_federated_subject == expected_staging,
            "observed staging OIDC subject differs",
        ),
        (
            identity_observation.production_federated_subject == expected_production,
            "observed production OIDC subject differs",
        ),
        (
            _same_resource(
                identity_observation.acr_scope,
                handoff["containerImage"]["registryResourceId"],
            ),
            "observed AcrPush scope differs from handoff registry",
        ),
        (
            _same_resource(
                identity_observation.container_app_scope,
                handoff["application"]["resourceId"],
            ),
            "observed Container Apps Contributor scope differs from handoff",
        ),
    ):
        _require(passed, message)
    observed_enumeration = identity_observation.role_assignment_enumeration
    declared_enumeration = RoleAssignmentEnumerationObservation.model_validate(
        role_enumeration
    )
    _require(
        observed_enumeration == declared_enumeration
        and observed_enumeration.assignee_object_id.casefold()
        == identity["principalId"].casefold()
        and observed_enumeration.subscription_id.casefold()
        == expected_subscription_id.casefold()
        and observed_enumeration.performed_at
        == identity_observation.observed_at,
        "observed role assignment enumeration differs from the workflow principal",
    )
    observed_credentials = {
        credential.environment: credential
        for credential in identity_observation.federated_credentials
    }
    _require(
        set(observed_credentials) == {"staging", "production"},
        "observed federated credentials differ from required environments",
    )
    for environment, expected_subject in (
        ("staging", expected_staging),
        ("production", expected_production),
    ):
        credential = observed_credentials[environment]
        _require(
            credential.subject == expected_subject
            and _same_resource(
                credential.resource_id,
                identity["federatedCredentialResourceIds"][environment],
            ),
            f"{environment} federated credential differs from the workflow identity",
        )
        _require(
            credential.resource_id.casefold().startswith(
                f"{identity['resourceId'].rstrip('/')}/federatedIdentityCredentials/".casefold()
            ),
            f"{environment} federated credential is not owned by the workflow identity",
        )
    _require(
        all(
            assignment.principal_id.casefold()
            == identity["principalId"].casefold()
            for assignment in identity_observation.role_assignments
        ),
        "observed role assignments include another principal",
    )
    observed_roles = {
        (assignment.role_definition_id.casefold(), assignment.scope.casefold())
        for assignment in identity_observation.role_assignments
    }
    role_assignment_marker = (
        "/providers/Microsoft.Authorization/roleAssignments/"
    )
    for assignment in identity_observation.role_assignments:
        marker_index = assignment.resource_id.casefold().rfind(
            role_assignment_marker.casefold()
        )
        _require(
            marker_index > 0
            and _same_resource(
                assignment.resource_id[:marker_index],
                assignment.scope,
            ),
            "role assignment resource ID differs from its declared scope",
        )
    expected_roles = {
        (identity["acrRoleDefinitionId"].casefold(), identity["acrScope"].casefold()),
        (
            identity["containerAppRoleDefinitionId"].casefold(),
            identity["containerAppScope"].casefold(),
        ),
    }
    _require(
        observed_roles == expected_roles,
        "observed role assignments do not bind exact roles and scopes to the workflow principal",
    )
    _validate_role_assignment_raw_capture(
        observed_enumeration,
        identity_observation,
        repository_root,
    )

    build = _load_observation(
        repository_root,
        evidence["image"]["resultFile"],
        BuildObservation,
    )
    _require_workflow_binding(build, workflow_observation)
    image = evidence["image"]
    source_commit = handoff["source"]["commitSha"]
    expected_repository = (
        f"{handoff['containerImage']['registry']}/"
        f"{handoff['containerImage']['repository']}"
    )
    expected_reference = f"{expected_repository}@{image['digest']}"
    for passed, message in (
        (str(build.run_id) == workflow["runId"], "build run ID differs"),
        (
            build.run_attempt == workflow["runAttempt"],
            "build run attempt differs",
        ),
        (
            build.source_commit == source_commit,
            "build source commit differs from handoff",
        ),
        (
            _same_resource(
                build.registry_resource_id,
                handoff["containerImage"]["registryResourceId"],
            ),
            "build registry differs from handoff",
        ),
        (
            build.repository == expected_repository == image["repository"],
            "build repository differs from handoff",
        ),
        (
            source_commit
            == evidence["subject"]["sourceCommit"]
            == image["sourceCommit"]
            == image["tag"]
            == build.source_commit
            == build.tag,
            "CI/CD image identity is not the exact handoff commit",
        ),
        (build.digest == image["digest"], "build digest differs"),
        (
            build.reference == image["reference"] == expected_reference,
            "build reference is not the exact digest-qualified handoff repository",
        ),
    ):
        _require(passed, message)

    candidate = _load_observation(
        repository_root,
        evidence["revisions"]["resultFile"],
        RevisionObservation,
    )
    _require_workflow_binding(candidate, workflow_observation)
    revisions = evidence["revisions"]
    _require(
        str(candidate.run_id) == workflow["runId"]
        and candidate.run_attempt == workflow["runAttempt"],
        "candidate workflow attempt differs",
    )
    _require(
        revisions["previous"] == handoff["application"]["revisionName"],
        "retained previous revision differs from handoff",
    )
    _require(
        _same_resource(candidate.container_app_resource_id, handoff["application"]["resourceId"]),
        "candidate belongs to a different Container App",
    )
    _require(
        candidate.revision_name == revisions["candidate"],
        "candidate revision observation differs",
    )
    _require(
        revisions["candidate"].endswith(f"--ci-{source_commit[:12]}"),
        "candidate revision suffix differs from the handoff commit",
    )
    expected_candidate_url = _revision_label_url(
        handoff["application"]["url"],
        revisions["candidateLabel"],
    )
    _require(
        revisions["candidateUrl"].rstrip("/") == expected_candidate_url,
        "candidate label URL is not derived from the handoff application",
    )
    _require(candidate.active, "candidate revision was not active")
    _require(candidate.image_reference == image["reference"], "candidate image differs")
    _require(
        candidate.traffic_weight == 0 and candidate.label == revisions["candidateLabel"],
        "candidate was not observed at zero traffic with its label",
    )
    _require(
        str(candidate.label_url).rstrip("/")
        == expected_candidate_url,
        "candidate label URL differs",
    )

    smoke = _load_observation(
        repository_root,
        evidence["smoke"]["resultFile"],
        SmokeObservation,
    )
    _require_workflow_binding(smoke, workflow_observation)
    _require(
        str(smoke.run_id) == workflow["runId"]
        and smoke.run_attempt == workflow["runAttempt"],
        "smoke workflow attempt differs",
    )
    for actual, expected, message in (
        (
            str(smoke.candidate_url).rstrip("/"),
            expected_candidate_url,
            "smoke candidate URL differs",
        ),
        (
            str(smoke.health_url).rstrip("/"),
            f"{expected_candidate_url}/healthz",
            "smoke health URL differs",
        ),
        (
            str(smoke.readiness_url).rstrip("/"),
            f"{expected_candidate_url}/readyz",
            "smoke readiness URL differs",
        ),
        (
            evidence["smoke"]["candidateUrl"].rstrip("/"),
            expected_candidate_url,
            "declared smoke candidate URL differs",
        ),
        (
            evidence["smoke"]["healthUrl"].rstrip("/"),
            f"{expected_candidate_url}/healthz",
            "declared smoke health URL differs",
        ),
        (
            evidence["smoke"]["readinessUrl"].rstrip("/"),
            f"{expected_candidate_url}/readyz",
            "declared smoke readiness URL differs",
        ),
    ):
        _require(actual == expected, message)
    _require(smoke.revision_name == revisions["candidate"], "smoke revision differs")
    _require(smoke.image_reference == image["reference"], "smoke image differs")

    approval = _load_observation(
        repository_root,
        evidence["approval"]["resultFile"],
        ApprovalObservation,
    )
    _require_workflow_binding(approval, workflow_observation)
    _require(
        str(approval.run_id) == workflow["runId"]
        and approval.run_attempt == workflow["runAttempt"],
        "approval workflow attempt differs",
    )
    _require(
        approval.reviewer == evidence["approval"]["reviewer"],
        "approval reviewer differs",
    )
    _require(
        approval.approved_at.isoformat()
        == evidence["approval"]["approvedAt"].replace("Z", "+00:00"),
        "approval timestamp differs",
    )

    traffic_observations: dict[str, TrafficObservation] = {}
    raw_revision_states: dict[str, dict[str, dict[str, Any]]] = {}
    expected_weights = {
        "before": (100, 0),
        "promotion": (0, 100),
        "rollback": (100, 0),
    }
    for stage, (previous_weight, candidate_weight) in expected_weights.items():
        declaration = evidence["traffic"][stage]
        observation = _load_observation(
            repository_root,
            declaration["resultFile"],
            TrafficObservation,
        )
        traffic_observations[stage] = observation
        stage_states = _load_revision_states(
            declaration,
            handoff["application"]["resourceId"],
            repository_root,
        )
        raw_revision_states[stage] = stage_states
        _require_workflow_binding(observation, workflow_observation)
        _require(
            str(observation.run_id) == workflow["runId"]
            and observation.run_attempt == workflow["runAttempt"],
            f"{stage} traffic workflow attempt differs",
        )
        _require(
            _same_resource(
                observation.container_app_resource_id,
                handoff["application"]["resourceId"],
            ),
            f"{stage} traffic observation belongs to a different Container App",
        )
        _require(
            observation.previous_revision == revisions["previous"]
            and observation.candidate_revision == revisions["candidate"],
            f"{stage} traffic observation names different revisions",
        )
        _require(
            observation.previous_weight
            == declaration["previous"]
            == previous_weight
            and observation.candidate_weight
            == declaration["candidate"]
            == candidate_weight,
            f"{stage} traffic weights differ",
        )
        _require(
            observation.observed_at.isoformat()
            == declaration["observedAt"].replace("Z", "+00:00"),
            f"{stage} traffic timestamp differs",
        )
        _require(
            observation.previous_active and observation.candidate_active,
            f"{stage} does not prove both revisions remained active",
        )
        _require(
            str(observation.application_url).rstrip("/")
            == handoff["application"]["url"].rstrip("/")
            and str(observation.health_url).rstrip("/")
            == handoff["application"]["healthUrl"].rstrip("/")
            and str(observation.readiness_url).rstrip("/")
            == handoff["application"]["readinessUrl"].rstrip("/"),
            f"{stage} health checks target different application endpoints",
        )
        _require(
            revisions["previous"] in stage_states
            and revisions["candidate"] in stage_states,
            f"{stage} raw revision list omits a retained revision",
        )
        previous_state = stage_states[revisions["previous"]]
        candidate_state = stage_states[revisions["candidate"]]
        _require(
            previous_state["active"] == observation.previous_active
            and previous_state["healthState"]
            == observation.previous_health_state
            and previous_state["trafficWeight"]
            == observation.previous_weight
            and candidate_state["active"] == observation.candidate_active
            and candidate_state["healthState"]
            == observation.candidate_health_state
            and candidate_state["trafficWeight"]
            == observation.candidate_weight,
            f"{stage} normalized revision state differs from raw Azure output",
        )
        _require(
            image["reference"] in candidate_state["images"],
            f"{stage} candidate image differs from raw Azure output",
        )

    before = traffic_observations["before"]
    promotion = traffic_observations["promotion"]
    rollback = traffic_observations["rollback"]
    safety_declaration = evidence["traffic"]["safety"]
    safety = _load_observation(
        repository_root,
        safety_declaration["resultFile"],
        RollbackSafetyObservation,
    )
    _require_workflow_binding(safety, workflow_observation)
    _require(
        str(safety.run_id) == workflow["runId"]
        and safety.run_attempt == workflow["runAttempt"],
        "rollback safety workflow attempt differs",
    )
    for field, actual in (
        ("mechanism", safety.mechanism),
        ("guardInstalledAt", safety.guard_installed_at),
        ("promotionAttemptedAt", safety.promotion_attempted_at),
        ("rollbackAttemptedAt", safety.rollback_attempted_at),
        ("rollbackCompletedAt", safety.rollback_completed_at),
        ("executesOnFailure", safety.executes_on_failure),
        ("promotionSucceeded", safety.promotion_succeeded),
        ("rollbackSucceeded", safety.rollback_succeeded),
    ):
        expected = safety_declaration[field]
        if isinstance(actual, datetime):
            expected = _parse_time(expected)
        _require(
            actual == expected,
            f"rollback safety {field} differs",
        )
    before_candidate_state = raw_revision_states["before"][
        revisions["candidate"]
    ]
    _require(
        candidate.active == before_candidate_state["active"]
        and candidate.health_state == before_candidate_state["healthState"]
        and candidate.traffic_weight
        == before_candidate_state["trafficWeight"]
        and candidate.image_reference
        in before_candidate_state["images"],
        "candidate observation differs from pre-promotion raw revision state",
    )
    staging = workflow["jobs"]["staging"]
    production = workflow["jobs"]["production"]
    staging_start = datetime.fromisoformat(staging["startedAt"].replace("Z", "+00:00"))
    staging_end = datetime.fromisoformat(staging["completedAt"].replace("Z", "+00:00"))
    production_start = datetime.fromisoformat(
        production["startedAt"].replace("Z", "+00:00")
    )
    production_end = datetime.fromisoformat(
        production["completedAt"].replace("Z", "+00:00")
    )
    _require(
        staging_start
        < staging_end
        <= approval.approved_at
        <= production_start
        < production_end,
        "staging, approval, and production windows are out of order",
    )
    _require(
        production_end
        <= identity_observation.observed_at
        <= _parse_time(evidence["capturedAt"]),
        "CI/CD report was captured before post-run evidence",
    )
    _require(
        staging_start
        <= build.completed_at
        <= candidate.observed_at
        <= smoke.observed_at
        <= staging_end,
        "build, candidate, and smoke observations fall outside the staging job",
    )
    _require(
        production_start
        <= safety.guard_installed_at
        <= safety.promotion_attempted_at
        <= promotion.observed_at
        < safety.rollback_attempted_at
        <= rollback.observed_at
        <= safety.rollback_completed_at
        <= production_end,
        "promotion and fail-safe rollback fall outside the production job",
    )
    _require(
        build.completed_at
        <= candidate.observed_at
        <= smoke.observed_at
        <= before.observed_at
        <= staging_end
        <= approval.approved_at
        <= production_start
        <= safety.guard_installed_at
        <= safety.promotion_attempted_at
        <= promotion.observed_at
        < safety.rollback_attempted_at
        <= rollback.observed_at
        <= safety.rollback_completed_at,
        "CI/CD observations violate build-smoke-approval-promotion-rollback order",
    )
    _require(
        smoke.observed_at <= before.observed_at <= staging_end,
        "pre-promotion traffic was not observed before approval",
    )
    _require(
        production_end
        <= workflow_observation.captured_at
        <= _parse_time(evidence["capturedAt"])
        and max(
            safety.rollback_completed_at,
            identity_observation.observed_at,
            workflow_observation.captured_at,
        )
        <= _parse_time(evidence["capturedAt"]),
        "CI/CD report was captured before rollback evidence",
    )


def _validate_observability(
    evidence: dict[str, Any],
    handoff: dict[str, Any],
    repository_root: Path,
    contracts_directory: Path,
) -> None:
    """Validate workbook deployment and handoff-bound Azure Monitor results."""
    _validate_common_subject(evidence, handoff)
    _require(
        evidence["subject"]["serviceName"] == handoff["observability"]["serviceName"],
        "observability subject service differs from handoff",
    )
    source = evidence["source"]
    _require(
        _same_resource(
            source["applicationInsightsResourceId"],
            handoff["observability"]["applicationInsightsResourceId"],
        ),
        "observability data source differs from handoff",
    )
    _require(
        source["serviceName"] == handoff["observability"]["serviceName"]
        and source["serviceNamespace"] == handoff["observability"]["serviceNamespace"]
        and source["environment"] == handoff["observability"]["environment"],
        "observability service attributes differ from handoff",
    )
    _require(
        _same_resource(
            source["logAnalyticsWorkspaceResourceId"],
            handoff["observability"]["logAnalyticsWorkspaceResourceId"],
        ),
        "observability workspace differs from handoff",
    )
    _require(
        evidence["telemetryReport"] == handoff["evidence"]["telemetryReport"],
        "observability telemetry report differs from handoff",
    )

    metrics_export = evidence["metricsExport"]
    metrics_observation = _load_observation(
        repository_root,
        metrics_export["resultFile"],
        DiagnosticSettingObservation,
    )
    for passed, message in (
        (
            _same_resource(
                metrics_export["containerAppResourceId"],
                handoff["application"]["resourceId"],
            )
            and _same_resource(
                metrics_observation.container_app_resource_id,
                handoff["application"]["resourceId"],
            ),
            "metrics export targets a different Container App",
        ),
        (
            _same_resource(
                metrics_export["workspaceResourceId"],
                handoff["observability"]["logAnalyticsWorkspaceResourceId"],
            )
            and _same_resource(
                metrics_observation.workspace_resource_id,
                handoff["observability"]["logAnalyticsWorkspaceResourceId"],
            ),
            "metrics export targets a different Log Analytics workspace",
        ),
        (
            metrics_observation.observed_at.isoformat()
            == metrics_export["deployedAt"].replace("Z", "+00:00"),
            "metrics export deployment timestamp differs",
        ),
    ):
        _require(passed, message)

    expected_queries = render_observability_queries(
        evidence, handoff, contracts_directory
    )
    workbook = _load_observation(
        repository_root,
        evidence["workbook"]["resultFile"],
        WorkbookObservation,
    )
    _require(
        _same_resource(
            workbook.workbook_resource_id,
            evidence["workbook"]["resourceId"],
        ),
        "deployed workbook resource differs",
    )
    _require(
        _same_resource(
            workbook.application_insights_resource_id,
            handoff["observability"]["applicationInsightsResourceId"],
        ),
        "deployed workbook uses a different Application Insights resource",
    )
    _require(
        _same_resource(
            workbook.log_analytics_workspace_resource_id,
            handoff["observability"]["logAnalyticsWorkspaceResourceId"],
        ),
        "deployed workbook uses a different Log Analytics workspace",
    )
    _require(
        _same_resource(
            workbook.source_id,
            handoff["observability"]["logAnalyticsWorkspaceResourceId"],
        )
        and _same_resource(workbook.source_id, evidence["workbook"]["sourceId"]),
        "deployed workbook ARM sourceId differs from the handoff workspace",
    )
    _require(
        _same_resource(
            evidence["workbook"]["sourceId"],
            handoff["observability"]["logAnalyticsWorkspaceResourceId"],
        ),
        "declared workbook source differs from handoff",
    )
    _require(
        workbook.source_commit == handoff["source"]["commitSha"]
        and workbook.revision_name == handoff["application"]["revisionName"],
        "deployed workbook identity differs from handoff",
    )
    template_path = _resolve_evidence_file(
        repository_root, evidence["workbook"]["templateFile"]
    )
    queries_path = _resolve_evidence_file(
        repository_root, evidence["workbook"]["queriesFile"]
    )
    for actual, expected, message in (
        (
            workbook.template_sha256,
            evidence["workbook"]["templateSha256"],
            "workbook template digest differs",
        ),
        (
            workbook.queries_sha256,
            evidence["workbook"]["queriesSha256"],
            "workbook query-source digest differs",
        ),
        (
            workbook.serialized_data_sha256,
            evidence["workbook"]["serializedDataSha256"],
            "deployed workbook content digest differs",
        ),
        (
            workbook.template_sha256,
            _sha256(template_path),
            "workbook template digest differs from the checked-in file",
        ),
        (
            workbook.queries_sha256,
            _sha256(queries_path),
            "workbook query-source digest differs from the checked-in file",
        ),
        (
            workbook.serialized_data_sha256,
            _sha256_text(workbook.serialized_data),
            "deployed workbook serializedData digest is invalid",
        ),
    ):
        _require(actual == expected, message)
    query_contract = _load_observability_query_contract(contracts_directory)
    expected_templates = {
        declaration["id"]: declaration["template"]
        for declaration in query_contract["queries"]
    }
    _require(
        _workbook_queries(
            template_path.read_text(encoding="utf-8"),
            handoff["observability"]["logAnalyticsWorkspaceResourceId"],
        )
        == expected_templates,
        "checked-in workbook template differs from the frozen query templates",
    )
    _require(
        queries_path.read_text(encoding="utf-8")
        == render_observability_query_source(contracts_directory),
        "checked-in KQL source differs from the frozen query templates",
    )
    _require(
        _workbook_queries(
            workbook.serialized_data,
            handoff["observability"]["logAnalyticsWorkspaceResourceId"],
        )
        == {
            query_id: declaration["query"]
            for query_id, declaration in expected_queries.items()
        },
        "deployed workbook panels differ from the frozen rendered queries",
    )
    _require(
        workbook.deployed_at.isoformat()
        == evidence["workbook"]["deployedAt"].replace("Z", "+00:00"),
        "workbook deployment timestamp differs",
    )
    _require(
        metrics_observation.observed_at <= workbook.deployed_at,
        "workbook was deployed before its ACA metrics export",
    )

    report_captured_at = _parse_time(evidence["capturedAt"])
    window_start = _parse_time(evidence["window"]["startTime"])
    window_end = _parse_time(evidence["window"]["endTime"])
    _require(
        metrics_observation.observed_at
        <= workbook.deployed_at
        <= workbook.captured_at
        <= window_start
        < window_end
        <= report_captured_at,
        "observability deployment, query, and report windows are out of order",
    )
    query_models: dict[str, type[QueryObservationBase]] = {
        "error-rate": ErrorRateQueryObservation,
        "latency": LatencyQueryObservation,
        "database-dependency-failures": DatabaseFailureQueryObservation,
        "replica-count": ReplicaQueryObservation,
        "cold-starts": ColdStartQueryObservation,
    }
    panel_ids = {panel["id"] for panel in evidence["panels"]}
    _require(
        panel_ids == set(expected_queries),
        "observability panels differ from the frozen panel set",
    )
    for panel in evidence["panels"]:
        query_id = panel["id"]
        expected_query = expected_queries[query_id]
        observation = _load_observation(
            repository_root,
            panel["resultFile"],
            query_models[query_id],
        )
        _require(observation.query_id == query_id, f"{query_id} result ID differs")
        _require(
            panel["resultKind"]
            == observation.result_kind
            == expected_query["resultKind"],
            f"{query_id} result kind differs from the frozen query",
        )
        _require(
            _same_resource(
                observation.application_insights_resource_id,
                handoff["observability"]["applicationInsightsResourceId"],
            ),
            f"{query_id} result uses a different Application Insights resource",
        )
        _require(
            _same_resource(
                observation.log_analytics_workspace_resource_id,
                handoff["observability"]["logAnalyticsWorkspaceResourceId"],
            ),
            f"{query_id} result uses a different Log Analytics workspace",
        )
        _require(
            observation.source_commit == handoff["source"]["commitSha"]
            and observation.revision_name == handoff["application"]["revisionName"]
            and observation.service_name == handoff["observability"]["serviceName"],
            f"{query_id} result identity differs from handoff",
        )
        _require(
            observation.query == panel["query"] == expected_query["query"],
            f"{query_id} query text differs from the frozen template",
        )
        _require(
            observation.query_sha256
            == panel["querySha256"]
            == expected_query["querySha256"],
            f"{query_id} query hash differs from the frozen template",
        )
        _require(
            len(observation.rows) == panel["rowCount"],
            f"{query_id} row count differs from normalized results",
        )
        _require(
            observation.window_start == window_start
            and observation.window_end == window_end,
            f"{query_id} result window differs from the report",
        )
        _require(
            window_end <= observation.captured_at <= report_captured_at,
            f"{query_id} was not captured in the workbook evidence window",
        )
    _require(
        handoff["authentication"]["telemetry"] == "connection-string-secret",
        "handoff does not prove direct Azure Monitor exporter configuration",
    )


def validate_shared_challenge_evidence(
    kind: ChallengeKind,
    evidence_path: Path,
    handoff_path: Path,
    contracts_directory: Path,
    repository_root: Path,
) -> dict[str, Any]:
    """Validate one P6 evidence bundle and all referenced observations.

    Args:
        kind: Shared challenge evidence kind.
        evidence_path: Path to the evidence bundle.
        handoff_path: Path to the authoritative modernization handoff.
        contracts_directory: Directory containing frozen JSON schemas.
        repository_root: Repository root containing all referenced files.

    Returns:
        The validated evidence object.

    Raises:
        FileNotFoundError: If required evidence is missing or empty.
        ValueError: If cross-resource or temporal invariants do not hold.
        jsonschema.ValidationError: If evidence violates its JSON Schema.
        pydantic.ValidationError: If a normalized observation is malformed.
    """
    contracts = _validated_contracts_directory(contracts_directory)
    root = repository_root.resolve()
    try:
        handoff_relative = handoff_path.absolute().relative_to(root).as_posix()
    except ValueError as error:
        raise ValueError("modernization handoff must be inside the repository") from error
    safe_handoff_path = _resolve_evidence_file(root, handoff_relative)
    handoff_document = _load_json(safe_handoff_path)
    _validate_handoff_reference_paths(handoff_document, root)
    handoff = validate_handoff(
        safe_handoff_path,
        contracts,
        root,
    )
    try:
        evidence_relative = evidence_path.absolute().relative_to(root).as_posix()
    except ValueError as error:
        raise ValueError("shared challenge evidence must be inside the repository") from error
    evidence = _load_json(_resolve_evidence_file(root, evidence_relative))
    _validate_schema(evidence, kind, contracts)
    _validate_referenced_files(evidence, root)
    if kind == "load":
        _validate_load(evidence, handoff, root, safe_handoff_path)
    elif kind == "cicd":
        _validate_cicd(evidence, handoff, root)
    else:
        _validate_observability(
            evidence,
            handoff,
            root,
            contracts,
        )
    return evidence
