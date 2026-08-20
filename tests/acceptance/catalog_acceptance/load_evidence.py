"""Render deterministic load evidence from captured Azure responses."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker
from jsonschema.exceptions import ValidationError as JsonSchemaValidationError
from pydantic import ValidationError

from catalog_acceptance.models.shared_challenges import (
    HealthObservation,
    LoadEvidenceCapture,
    LoadMetricCapture,
    LoadRunObservation,
    MetricObservation,
    ScaleConfigurationObservation,
)

_LOAD_REPORT_VERSION = "1.1.0"
_OBSERVATION_VERSION = "1.1.0"
_PACKAGE_REPOSITORY_ROOT = Path(__file__).absolute().parents[3]
_CAPTURE_SCHEMA_PATH = (
    _PACKAGE_REPOSITORY_ROOT
    / "workshop/contracts/load-evidence-capture.schema.json"
)
_REPORT_SCHEMA_PATH = (
    _PACKAGE_REPOSITORY_ROOT
    / "workshop/contracts/load-test-evidence.schema.json"
)
_CAPTURE_MANIFEST_PATH = "evidence/load/capture.json"
_HANDOFF_PATH = "evidence/modernization-contract.json"
_REPORT_OUTPUT = "evidence/load-test-report.json"
_RESULT_FILES = {
    "loadRun": "evidence/load/test-run.json",
    "scaleConfiguration": "evidence/load/scale-configuration.json",
    "replicas": "evidence/load/replicas.json",
    "databaseSignal": "evidence/load/database.json",
    "recovery": "evidence/load/recovery.json",
}
_DATABASE_SIGNALS = {
    "azure-sql": ("app_cpu_billed", "Total", "count"),
    "postgresql-flexible": ("cpu_percent", "Maximum", "percent"),
}


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


def _load_json_object(path: Path) -> dict[str, Any]:
    """Load one strict UTF-8 JSON object."""
    with path.open(encoding="utf-8") as handle:
        value = json.load(
            handle,
            parse_constant=_reject_nonfinite,
            object_pairs_hook=_reject_duplicate_keys,
        )
    if not isinstance(value, dict):
        raise ValueError(f"expected a JSON object: {path}")
    return value


def _sha256_file(path: Path) -> str:
    """Return the lowercase SHA-256 digest of one file."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _resolve_file(repository_root: Path, value: str) -> Path:
    """Resolve one non-empty regular file without traversal or symlinks."""
    root = repository_root.resolve()
    relative = Path(value)
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError(f"capture path must stay within the repository: {value}")
    declared = root
    for part in relative.parts:
        declared /= part
        if declared.is_symlink():
            raise ValueError(f"capture path contains a symlink: {value}")
    resolved = declared.resolve()
    try:
        resolved.relative_to(root)
    except ValueError as error:
        raise ValueError(f"capture path escapes the repository: {value}") from error
    if not resolved.is_file() or resolved.stat().st_size == 0:
        raise ValueError(f"capture path must be a non-empty regular file: {value}")
    return resolved


def _require_mapping(value: Any, name: str) -> dict[str, Any]:
    """Return one mapping or fail with its source field name."""
    if not isinstance(value, dict):
        raise ValueError(f"{name} must be an object")
    return value


def _require_list(value: Any, name: str) -> list[Any]:
    """Return one list or fail with its source field name."""
    if not isinstance(value, list):
        raise ValueError(f"{name} must be an array")
    return value


def _require_string(value: Any, name: str) -> str:
    """Return one non-empty string or fail with its source field name."""
    if not isinstance(value, str) or not value:
        raise ValueError(f"{name} must be a non-empty string")
    return value


def _require_integer(value: Any, name: str) -> int:
    """Return one strict integer or fail with its source field name."""
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{name} must be an integer")
    return value


def _require_number(value: Any, name: str) -> float:
    """Return one finite strict JSON number."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a number")
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"{name} must be finite")
    return number


def _parse_datetime(value: Any, name: str) -> datetime:
    """Parse one offset-aware ISO-8601 timestamp."""
    text = _require_string(value, name)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError(f"{name} must be an ISO-8601 timestamp") from error
    if parsed.tzinfo is None:
        raise ValueError(f"{name} must include a timezone")
    return parsed


def _format_datetime(value: datetime) -> str:
    """Render one timestamp canonically in UTC."""
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _load_captured_json(
    repository_root: Path,
    file: str,
    expected_sha256: str,
) -> dict[str, Any]:
    """Load one digest-bound raw capture document."""
    path = _resolve_file(repository_root, file)
    actual_sha256 = _sha256_file(path)
    if actual_sha256 != expected_sha256:
        raise ValueError(
            f"raw capture digest mismatch for {file}: "
            f"expected {expected_sha256}, got {actual_sha256}"
        )
    return _load_json_object(path)


def _validate_artifact(
    repository_root: Path,
    file: str,
    expected_sha256: str,
) -> None:
    """Validate one digest-bound load-test input."""
    path = _resolve_file(repository_root, file)
    actual_sha256 = _sha256_file(path)
    if actual_sha256 != expected_sha256:
        raise ValueError(
            f"load artifact digest mismatch for {file}: "
            f"expected {expected_sha256}, got {actual_sha256}"
        )


def _parse_load_run(
    raw: dict[str, Any],
    capture: LoadEvidenceCapture,
    handoff: dict[str, Any],
) -> tuple[dict[str, Any], datetime, datetime]:
    """Normalize one Azure Load Testing run response."""
    test_run = capture.test_run
    if raw.get("status") != "DONE":
        raise ValueError("load test status must be DONE")
    started_at = _parse_datetime(
        raw.get("executionStartDateTime"),
        "executionStartDateTime",
    )
    completed_at = _parse_datetime(
        raw.get("executionEndDateTime"),
        "executionEndDateTime",
    )
    duration_ms = _require_integer(raw.get("duration"), "duration")
    virtual_users = _require_integer(raw.get("virtualUsers"), "virtualUsers")
    if duration_ms != 300_000 or virtual_users != 40:
        raise ValueError("load test must use exactly 40 users for 300 seconds")
    if int((completed_at - started_at).total_seconds()) != 300:
        raise ValueError("load test timestamps must span exactly 300 seconds")
    statistics = _require_mapping(
        raw.get("testRunStatistics"),
        "testRunStatistics",
    )
    totals = _require_mapping(statistics.get("Total"), "testRunStatistics.Total")
    sample_count = _require_integer(totals.get("sampleCount"), "sampleCount")
    error_count = _require_integer(totals.get("errorCount"), "errorCount")
    if sample_count <= 0 or error_count != 0:
        raise ValueError("load test must contain requests and zero errors")
    application_url = handoff["application"]["url"].rstrip("/")
    observation = {
        "schemaVersion": _OBSERVATION_VERSION,
        "resourceId": test_run.resource_id,
        "testRunId": raw["testRunId"],
        "testId": raw["testId"],
        "applicationUrl": application_url,
        "targetUrl": f"{application_url}/perftest/catalog",
        "revisionName": handoff["application"]["revisionName"],
        "performancePath": "/perftest/catalog",
        "configurationFile": capture.artifacts.configuration_file,
        "configurationSha256": capture.artifacts.configuration_sha256,
        "jmeterFile": capture.artifacts.jmeter_file,
        "jmeterSha256": capture.artifacts.jmeter_sha256,
        "status": "DONE",
        "startedAt": _format_datetime(started_at),
        "completedAt": _format_datetime(completed_at),
        "totalRequests": sample_count,
        "failedRequests": error_count,
        "virtualUsers": virtual_users,
        "durationSeconds": duration_ms // 1000,
        "capturedAt": _format_datetime(capture.captured_at),
    }
    return observation, started_at, completed_at


def _parse_scale_configuration(
    raw: dict[str, Any],
    capture: LoadEvidenceCapture,
    handoff: dict[str, Any],
) -> dict[str, Any]:
    """Normalize one Container App ARM response."""
    resource_id = handoff["application"]["resourceId"]
    if raw.get("id") != resource_id or raw.get("type") != "Microsoft.App/containerApps":
        raise ValueError("scale capture does not identify the handoff Container App")
    properties = _require_mapping(raw.get("properties"), "properties")
    if properties.get("latestReadyRevisionName") != handoff["application"][
        "revisionName"
    ]:
        raise ValueError("scale capture latest-ready revision does not match handoff")
    if properties.get("provisioningState") != "Succeeded":
        raise ValueError("Container App provisioning state must be Succeeded")
    template = _require_mapping(properties.get("template"), "properties.template")
    scale = _require_mapping(template.get("scale"), "properties.template.scale")
    rules = _require_list(scale.get("rules"), "properties.template.scale.rules")
    if len(rules) != 1:
        raise ValueError("Container App must expose exactly one scale rule")
    rule = _require_mapping(rules[0], "scale rule")
    http = _require_mapping(rule.get("http"), "scale rule http")
    metadata = _require_mapping(http.get("metadata"), "scale rule metadata")
    if (
        scale.get("minReplicas") != 1
        or scale.get("maxReplicas") != 3
        or rule.get("name") != "http"
        or metadata.get("concurrentRequests") != "50"
    ):
        raise ValueError("Container App scale contract must remain 1/3/http/50")
    return {
        "schemaVersion": _OBSERVATION_VERSION,
        "source": "azure-resource-manager",
        "containerAppResourceId": resource_id,
        "revisionName": handoff["application"]["revisionName"],
        "minimumReplicas": 1,
        "maximumReplicas": 3,
        "ruleName": "http",
        "ruleType": "http",
        "concurrentRequests": 50,
        "provisioningState": "Succeeded",
        "etag": _require_string(raw.get("etag"), "etag"),
        "observedAt": _format_datetime(capture.scale_configuration.observed_at),
    }


def _parse_metric(
    raw: dict[str, Any],
    metric_capture: LoadMetricCapture,
    *,
    expected_unit: str,
) -> list[dict[str, Any]]:
    """Normalize one exact Azure Monitor metric series."""
    if raw.get("interval") != metric_capture.interval:
        raise ValueError("raw metric interval does not match the capture")
    expected_timespan = (
        f"{_format_datetime(metric_capture.start)}/"
        f"{_format_datetime(metric_capture.end)}"
    )
    if raw.get("timespan") != expected_timespan:
        raise ValueError("raw metric timespan does not match the capture")
    metrics = _require_list(raw.get("value"), "value")
    if len(metrics) != 1:
        raise ValueError("metric response must contain exactly one metric")
    metric = _require_mapping(metrics[0], "value[0]")
    name = _require_mapping(metric.get("name"), "value[0].name")
    if name.get("value") != metric_capture.metric_name:
        raise ValueError("raw metric name does not match the capture")
    if str(metric.get("unit", "")).casefold() != expected_unit.casefold():
        raise ValueError("raw metric unit does not match the frozen contract")
    expected_id = (
        f"{metric_capture.resource_id}/providers/Microsoft.Insights/metrics/"
        f"{metric_capture.metric_name}"
    )
    if str(metric.get("id", "")).casefold() != expected_id.casefold():
        raise ValueError("raw metric ID does not match the captured resource")
    series = _require_list(metric.get("timeseries"), "value[0].timeseries")
    if len(series) != 1:
        raise ValueError("metric response must contain exactly one time series")
    time_series = _require_mapping(series[0], "value[0].timeseries[0]")
    metadata = _require_list(
        time_series.get("metadatavalues", []),
        "metadatavalues",
    )
    if metric_capture.revision_name is None:
        if metadata:
            raise ValueError("database metric series must not contain dimensions")
    else:
        if len(metadata) != 1:
            raise ValueError("replica metric must contain one revision dimension")
        dimension = _require_mapping(metadata[0], "metadatavalues[0]")
        dimension_name = _require_mapping(
            dimension.get("name"),
            "metadatavalues[0].name",
        )
        if (
            dimension_name.get("value") != "revisionName"
            or dimension.get("value") != metric_capture.revision_name
        ):
            raise ValueError("replica metric revision dimension is not exact")
    aggregation_key = metric_capture.aggregation.casefold()
    data = _require_list(time_series.get("data"), "timeseries data")
    if not data:
        raise ValueError("metric series must contain data")
    points: list[dict[str, Any]] = []
    timestamps: set[datetime] = set()
    for index, raw_point in enumerate(data):
        point = _require_mapping(raw_point, f"metric point {index}")
        timestamp = _parse_datetime(point.get("timeStamp"), "timeStamp")
        if timestamp in timestamps:
            raise ValueError("metric timestamps must be unique")
        timestamps.add(timestamp)
        if timestamp < metric_capture.start or timestamp > metric_capture.end:
            raise ValueError("metric point falls outside the capture window")
        number = _require_number(point.get(aggregation_key), aggregation_key)
        points.append(
            {
                "timestamp": _format_datetime(timestamp),
                "value": number,
            }
        )
    points.sort(key=lambda point: point["timestamp"])
    return points


def _validate_scale_lifecycle(
    points: list[dict[str, Any]],
    capture: LoadEvidenceCapture,
    started_at: datetime,
    completed_at: datetime,
) -> int:
    """Require baseline one, observed scale-out, and post-load recovery."""
    normalized = [
        (_parse_datetime(point["timestamp"], "replica timestamp"), point["value"])
        for point in points
    ]
    if any(not float(value).is_integer() for _, value in normalized):
        raise ValueError("replica values must be whole numbers")
    baseline = [
        value
        for timestamp, value in normalized
        if capture.baseline_start <= timestamp < started_at
    ]
    in_load = [
        value
        for timestamp, value in normalized
        if started_at <= timestamp <= completed_at
    ]
    post_load = [
        (timestamp, value)
        for timestamp, value in normalized
        if completed_at < timestamp <= capture.recovery.observed_at
    ]
    if not baseline or baseline[-1] != 1:
        raise ValueError("replica series must establish a one-replica baseline")
    if not in_load or max(in_load) < 2 or max(in_load) > 3:
        raise ValueError("replica series must observe in-load scale-out to 2..3")
    recovered = [
        timestamp for timestamp, value in post_load if value == 1
    ]
    if not recovered:
        raise ValueError("replica series must observe post-load recovery to one")
    if normalized[-1][1] != 1:
        raise ValueError("final replica observation must remain at one")
    return int(max(in_load))


def _validate_handoff(handoff: dict[str, Any]) -> None:
    """Require the load renderer's frozen handoff fields."""
    _require_string(handoff.get("sliceId"), "handoff sliceId")
    required_paths = (
        ("source", "stack"),
        ("source", "commitSha"),
        ("application", "resourceId"),
        ("application", "revisionName"),
        ("application", "url"),
        ("application", "healthUrl"),
        ("application", "readinessUrl"),
        ("database", "resourceId"),
        ("database", "family"),
        ("containerImage", "digest"),
    )
    for parent, child in required_paths:
        value = _require_mapping(handoff.get(parent), parent).get(child)
        if not isinstance(value, str) or not value:
            raise ValueError(f"handoff {parent}.{child} is required")


def expected_database_metric_resource_id(handoff: dict[str, Any]) -> str:
    """Return the Azure resource that exposes the handoff database metric.

    Args:
        handoff: Validated modernization handoff document.

    Returns:
        The database resource for Azure SQL or flexible-server parent for PostgreSQL.

    Raises:
        ValueError: If the database family or PostgreSQL child resource ID is invalid.
    """
    resource_id = _require_string(
        _require_mapping(handoff.get("database"), "database").get("resourceId"),
        "handoff database.resourceId",
    ).rstrip("/")
    family = _require_string(
        _require_mapping(handoff.get("database"), "database").get("family"),
        "handoff database.family",
    )
    if family == "azure-sql":
        return resource_id
    if family != "postgresql-flexible":
        raise ValueError(f"unsupported database family: {family}")
    parts = resource_id.strip("/").split("/")
    lowered = [part.casefold() for part in parts]
    try:
        provider_index = lowered.index("providers")
    except ValueError as error:
        raise ValueError(
            "PostgreSQL handoff database must be a flexible-server database child"
        ) from error
    if (
        len(parts) < 10
        or lowered[-2] != "databases"
        or lowered[-4] != "flexibleservers"
        or provider_index + 1 >= len(parts)
        or lowered[provider_index + 1] != "microsoft.dbforpostgresql"
    ):
        raise ValueError(
            "PostgreSQL handoff database must be a flexible-server database child"
        )
    return "/" + "/".join(parts[:-2])


def build_load_evidence(
    capture_path: Path,
    handoff_path: Path,
    repository_root: Path,
) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    """Build a report and normalized observations without writing files.

    Args:
        capture_path: Repository-local load capture manifest.
        handoff_path: Repository-local modernization handoff.
        repository_root: Root used to resolve every referenced file.

    Returns:
        A validated report and a path-keyed normalized observation mapping.

    Raises:
        ValueError: If any source, identity, hash, metric, or lifecycle invariant fails.
    """
    root = repository_root.resolve()
    capture_resolved = _resolve_file(
        root,
        str(capture_path.resolve().relative_to(root)),
    )
    handoff_resolved = _resolve_file(
        root,
        str(handoff_path.resolve().relative_to(root)),
    )
    if capture_resolved.relative_to(root).as_posix() != _CAPTURE_MANIFEST_PATH:
        raise ValueError(
            f"load capture manifest must be {_CAPTURE_MANIFEST_PATH}"
        )
    if handoff_resolved.relative_to(root).as_posix() != _HANDOFF_PATH:
        raise ValueError(f"modernization handoff must be {_HANDOFF_PATH}")
    capture_value = _load_json_object(capture_resolved)
    try:
        Draft202012Validator(
            _load_json_object(_CAPTURE_SCHEMA_PATH),
            format_checker=FormatChecker(),
        ).validate(capture_value)
    except JsonSchemaValidationError as error:
        raise ValueError(
            f"load capture manifest violates its frozen schema: {error.message}"
        ) from error
    try:
        capture = LoadEvidenceCapture.model_validate(capture_value)
    except ValidationError as error:
        raise ValueError(f"invalid load capture manifest: {error}") from error
    handoff = _load_json_object(handoff_resolved)
    _validate_handoff(handoff)

    if capture.replicas.resource_id != handoff["application"]["resourceId"]:
        raise ValueError("capture replica resource ID does not match handoff")
    if capture.replicas.revision_name != handoff["application"]["revisionName"]:
        raise ValueError("capture replica revision does not match handoff")
    database_metric_resource_id = expected_database_metric_resource_id(handoff)
    if capture.database_signal.resource_id != database_metric_resource_id:
        raise ValueError("capture database resource ID does not match handoff")
    database_family = handoff["database"]["family"]
    if database_family not in _DATABASE_SIGNALS:
        raise ValueError(f"unsupported database family: {database_family}")
    metric_name, aggregation, unit = _DATABASE_SIGNALS[database_family]
    if (
        capture.database_signal.metric_name,
        capture.database_signal.aggregation,
    ) != (metric_name, aggregation):
        raise ValueError("database metric does not match the handoff family")

    _validate_artifact(
        root,
        capture.artifacts.configuration_file,
        capture.artifacts.configuration_sha256,
    )
    _validate_artifact(
        root,
        capture.artifacts.jmeter_file,
        capture.artifacts.jmeter_sha256,
    )
    load_raw = _load_captured_json(
        root,
        capture.test_run.file,
        capture.test_run.sha256,
    )
    scale_raw = _load_captured_json(
        root,
        capture.scale_configuration.file,
        capture.scale_configuration.sha256,
    )
    replica_raw = _load_captured_json(
        root,
        capture.replicas.file,
        capture.replicas.sha256,
    )
    database_raw = _load_captured_json(
        root,
        capture.database_signal.file,
        capture.database_signal.sha256,
    )

    load_run, started_at, completed_at = _parse_load_run(
        load_raw,
        capture,
        handoff,
    )
    if capture.baseline_start >= started_at:
        raise ValueError("baselineStart must precede the load run")
    if capture.recovery.observed_at <= completed_at:
        raise ValueError("recovery observation must follow the load run")
    scale_configuration = _parse_scale_configuration(scale_raw, capture, handoff)
    replica_points = _parse_metric(
        replica_raw,
        capture.replicas,
        expected_unit="Count",
    )
    peak_replicas = _validate_scale_lifecycle(
        replica_points,
        capture,
        started_at,
        completed_at,
    )
    database_points = _parse_metric(
        database_raw,
        capture.database_signal,
        expected_unit=unit,
    )
    database_before = [
        point["value"]
        for point in database_points
        if capture.baseline_start
        <= _parse_datetime(point["timestamp"], "database timestamp")
        < started_at
    ]
    database_during = [
        point["value"]
        for point in database_points
        if started_at
        <= _parse_datetime(point["timestamp"], "database timestamp")
        <= completed_at
    ]
    if not database_before or not database_during:
        raise ValueError("database metric must include baseline and in-load points")
    if max(database_during) <= max(database_before):
        raise ValueError("database metric must prove load above baseline")
    recovery_seconds = int(
        (capture.recovery.observed_at - completed_at).total_seconds()
    )
    if recovery_seconds < 1 or recovery_seconds > 900:
        raise ValueError("recovery observation must follow load within 900 seconds")
    if (
        capture.replicas.start > capture.baseline_start
        or capture.replicas.end < capture.recovery.observed_at
        or capture.database_signal.start > capture.baseline_start
        or capture.database_signal.end < completed_at
    ):
        raise ValueError("metric captures do not cover the declared evidence windows")
    if (
        capture.baseline_start - capture.scale_configuration.observed_at
    ).total_seconds() > 900:
        raise ValueError("scale configuration must be captured within 15 minutes")

    application_url = handoff["application"]["url"].rstrip("/")
    if (
        str(capture.recovery.health_url).rstrip("/")
        != handoff["application"]["healthUrl"]
        or str(capture.recovery.readiness_url).rstrip("/")
        != handoff["application"]["readinessUrl"]
    ):
        raise ValueError("recovery URLs must target the handoff application")
    observations = {
        _RESULT_FILES["loadRun"]: load_run,
        _RESULT_FILES["scaleConfiguration"]: scale_configuration,
        _RESULT_FILES["replicas"]: {
            "schemaVersion": _OBSERVATION_VERSION,
            "resourceId": handoff["application"]["resourceId"],
            "metric": "Replicas",
            "aggregation": "Maximum",
            "startTime": _format_datetime(capture.replicas.start),
            "endTime": _format_datetime(capture.replicas.end),
            "points": replica_points,
        },
        _RESULT_FILES["databaseSignal"]: {
            "schemaVersion": _OBSERVATION_VERSION,
            "resourceId": database_metric_resource_id,
            "metric": metric_name,
            "aggregation": aggregation,
            "startTime": _format_datetime(capture.database_signal.start),
            "endTime": _format_datetime(capture.database_signal.end),
            "points": database_points,
        },
        _RESULT_FILES["recovery"]: {
            "schemaVersion": _OBSERVATION_VERSION,
            "healthUrl": str(capture.recovery.health_url),
            "readinessUrl": str(capture.recovery.readiness_url),
            "revisionName": handoff["application"]["revisionName"],
            "observedAt": _format_datetime(capture.recovery.observed_at),
            "healthStatus": capture.recovery.health_status,
            "readinessStatus": capture.recovery.readiness_status,
        },
    }
    validators = (
        (LoadRunObservation, observations[_RESULT_FILES["loadRun"]]),
        (
            ScaleConfigurationObservation,
            observations[_RESULT_FILES["scaleConfiguration"]],
        ),
        (MetricObservation, observations[_RESULT_FILES["replicas"]]),
        (MetricObservation, observations[_RESULT_FILES["databaseSignal"]]),
        (HealthObservation, observations[_RESULT_FILES["recovery"]]),
    )
    try:
        for model, value in validators:
            model.model_validate(value)
    except ValidationError as error:
        raise ValueError(f"rendered load observation is invalid: {error}") from error

    report = {
        "schemaVersion": _LOAD_REPORT_VERSION,
        "capturedAt": _format_datetime(capture.captured_at),
        "subject": {
            "sliceId": handoff["sliceId"],
            "stack": handoff["source"]["stack"],
            "databaseFamily": database_family,
            "sourceCommit": handoff["source"]["commitSha"],
            "imageDigest": handoff["containerImage"]["digest"],
            "revisionName": handoff["application"]["revisionName"],
            "containerAppResourceId": handoff["application"]["resourceId"],
            "databaseResourceId": handoff["database"]["resourceId"],
        },
        "capture": {
            "manifestFile": str(capture_resolved.relative_to(root)),
            "manifestSha256": _sha256_file(capture_resolved),
        },
        "windows": {
            "baselineStart": _format_datetime(capture.baseline_start),
            "loadStart": _format_datetime(started_at),
            "loadEnd": _format_datetime(completed_at),
            "recoveryEnd": _format_datetime(capture.recovery.observed_at),
        },
        "testRun": {
            "resourceId": load_run["resourceId"],
            "testId": load_run["testId"],
            "testRunId": load_run["testRunId"],
            "configurationFile": load_run["configurationFile"],
            "configurationSha256": load_run["configurationSha256"],
            "jmeterFile": load_run["jmeterFile"],
            "jmeterSha256": load_run["jmeterSha256"],
            "applicationUrl": load_run["applicationUrl"],
            "targetUrl": load_run["targetUrl"],
            "performancePath": load_run["performancePath"],
            "apiKeyTransport": "secret-environment",
            "virtualUsers": load_run["virtualUsers"],
            "durationSeconds": load_run["durationSeconds"],
            "startedAt": load_run["startedAt"],
            "completedAt": load_run["completedAt"],
            "resultFile": _RESULT_FILES["loadRun"],
        },
        "scaleConfiguration": {
            "source": scale_configuration["source"],
            "containerAppResourceId": scale_configuration[
                "containerAppResourceId"
            ],
            "revisionName": scale_configuration["revisionName"],
            "minimumReplicas": scale_configuration["minimumReplicas"],
            "maximumReplicas": scale_configuration["maximumReplicas"],
            "ruleName": scale_configuration["ruleName"],
            "ruleType": scale_configuration["ruleType"],
            "concurrentRequests": scale_configuration["concurrentRequests"],
            "observedAt": scale_configuration["observedAt"],
            "resultFile": _RESULT_FILES["scaleConfiguration"],
        },
        "replicas": {
            "resourceId": handoff["application"]["resourceId"],
            "resultFile": _RESULT_FILES["replicas"],
            "metric": "Replicas",
            "minimumConfigured": 1,
            "maximumConfigured": 3,
            "baselineObserved": 1,
            "peakObserved": peak_replicas,
        },
        "databaseSignal": {
            "resultFile": _RESULT_FILES["databaseSignal"],
            "resourceId": database_metric_resource_id,
            "family": database_family,
            "metric": metric_name,
            "aggregation": aggregation,
            "unit": unit,
            "baseline": max(database_before),
            "peak": max(database_during),
        },
        "recovery": {
            "resultFile": _RESULT_FILES["recovery"],
            "observedReplicas": 1,
            "withinSeconds": recovery_seconds,
            "healthStatus": 200,
            "readinessStatus": 200,
            "healthUrl": handoff["application"]["healthUrl"],
            "readinessUrl": handoff["application"]["readinessUrl"],
        },
        "assertions": {
            "allRequestsPassed": True,
            "scaledOut": True,
            "stayedWithinBounds": True,
            "databaseLoadObserved": True,
            "recovered": True,
        },
    }
    try:
        Draft202012Validator(
            _load_json_object(_REPORT_SCHEMA_PATH),
            format_checker=FormatChecker(),
        ).validate(report)
    except JsonSchemaValidationError as error:
        raise ValueError(
            f"rendered load report violates its frozen schema: {error.message}"
        ) from error
    return report, observations


def write_load_evidence(
    capture_path: Path,
    handoff_path: Path,
    report_path: Path,
    repository_root: Path,
) -> dict[str, Any]:
    """Render and atomically write one complete load evidence bundle.

    Args:
        capture_path: Repository-local load capture manifest.
        handoff_path: Repository-local modernization handoff.
        report_path: Repository-local destination for the rendered report.
        repository_root: Root used to resolve inputs and outputs.

    Returns:
        A machine-readable summary of all written files.

    Raises:
        ValueError: If validation fails or an output path is unsafe.
    """
    root = repository_root.resolve()
    try:
        report_relative = report_path.absolute().relative_to(root).as_posix()
    except ValueError as error:
        raise ValueError("load report output must stay inside the repository") from error
    if report_relative != _REPORT_OUTPUT:
        raise ValueError(f"load report output must be {_REPORT_OUTPUT}")
    report, observations = build_load_evidence(
        capture_path,
        handoff_path,
        repository_root,
    )
    destinations = {report_relative: report, **observations}
    staged: list[tuple[Path, Path]] = []
    try:
        for relative, value in destinations.items():
            relative_path = Path(relative)
            if relative_path.is_absolute() or ".." in relative_path.parts:
                raise ValueError(f"output path escapes the repository: {relative}")
            destination = root
            for part in relative_path.parts:
                destination /= part
                if destination.is_symlink():
                    raise ValueError(f"output path contains a symlink: {relative}")
            destination.parent.mkdir(parents=True, exist_ok=True)
            temporary = destination.with_name(
                f".{destination.name}.{os.getpid()}.tmp"
            )
            with temporary.open("x", encoding="utf-8") as handle:
                handle.write(json.dumps(value, indent=2, sort_keys=True) + "\n")
            staged.append((temporary, destination))
        for temporary, destination in staged:
            os.replace(temporary, destination)
    finally:
        for temporary, _ in staged:
            temporary.unlink(missing_ok=True)
    return {
        "schemaVersion": _LOAD_REPORT_VERSION,
        "report": str(report_path.resolve().relative_to(root)),
        "observations": sorted(observations),
    }
