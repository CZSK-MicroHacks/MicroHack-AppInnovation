"""Validate modernization handoff bundles and their referenced evidence."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from uuid import UUID
from xml.etree import ElementTree

from jsonschema import Draft202012Validator, FormatChecker

from catalog_acceptance.manifest import load_json
from catalog_acceptance.models.contracts import AcceptanceReport

REQUIRED_RUNTIME_TEST_IDS = {
    "liveness-database-outage",
    "readiness-database-outage",
    "readiness-import-failure",
    "performance-database-failure",
    "performance-timeout",
    "performance-missing-key",
    "performance-invalid-key",
    "work-factor-default",
    "work-factor-bounds",
    "work-factor-invalid",
}


def _validate_schema(schema_path: Path, instance: Any) -> None:
    """Validate one instance against a checked-in JSON Schema."""
    schema = load_json(schema_path)
    Draft202012Validator(
        schema,
        format_checker=FormatChecker(),
    ).validate(instance)


def _xml_files(artifact: Path, artifact_format: str) -> list[Path]:
    """Resolve one result file or a framework result directory."""
    if artifact.is_file():
        return [artifact]
    pattern = "*.trx" if artifact_format == "trx" else "TEST-*.xml"
    files = sorted(artifact.glob(pattern)) if artifact.is_dir() else []
    if not files:
        raise FileNotFoundError(f"no {artifact_format} results found at {artifact}")
    return files


def _runtime_test_outcomes(
    artifact: Path,
    artifact_format: str,
) -> dict[str, list[str]]:
    """Parse native TRX or JUnit artifacts into test-name outcomes."""
    outcomes: dict[str, list[str]] = {}
    for result_path in _xml_files(artifact, artifact_format):
        root = ElementTree.parse(result_path).getroot()
        if artifact_format == "trx":
            for result in root.iter():
                if result.tag.rsplit("}", 1)[-1] != "UnitTestResult":
                    continue
                name = result.attrib.get("testName")
                outcome = result.attrib.get("outcome")
                if name and outcome:
                    outcomes.setdefault(name, []).append(outcome.casefold())
        else:
            for case in root.iter():
                if case.tag.rsplit("}", 1)[-1] != "testcase":
                    continue
                name = case.attrib.get("name")
                if not name:
                    continue
                failed = any(
                    child.tag.rsplit("}", 1)[-1]
                    in ("failure", "error", "skipped")
                    for child in case
                )
                outcomes.setdefault(name, []).append("failed" if failed else "passed")
    return outcomes


def _validate_runtime_results(runtime_tests: dict[str, Any], artifact: Path) -> None:
    """Require every frozen runtime test ID to map to a native passing result."""
    ids = [test["id"] for test in runtime_tests["tests"]]
    if len(ids) != len(set(ids)) or set(ids) != REQUIRED_RUNTIME_TEST_IDS:
        raise ValueError("runtime evidence does not contain the exact unique test ID set")
    test_names = [test["testName"] for test in runtime_tests["tests"]]
    if len(test_names) != len(set(test_names)):
        raise ValueError("runtime evidence maps multiple requirements to one test")
    outcomes = _runtime_test_outcomes(artifact, runtime_tests["artifactFormat"])
    expected_pass = "passed" if runtime_tests["artifactFormat"] == "junit" else "passed"
    failures = [
        name
        for name in test_names
        if name not in outcomes
        or not outcomes[name]
        or any(outcome != expected_pass for outcome in outcomes[name])
    ]
    if failures:
        raise ValueError(f"runtime result artifact lacks passing tests: {failures}")


def _validate_telemetry_results(
    telemetry: dict[str, Any],
    contracts_directory: Path,
    repository_root: Path,
) -> None:
    """Validate normalized, non-empty query results against frozen signal names."""
    behavior = load_json(contracts_directory / "behavior-contract.json")["telemetry"]
    expected_by_query = {
        "resources": ["resource"],
        "traces": list(behavior["traces"]),
        "metrics": list(behavior["metrics"]),
        "logs": list(behavior["logs"]),
    }
    attributes_by_query = {
        "traces": behavior["traces"],
        "metrics": behavior["metrics"],
        "logs": behavior["logs"],
    }
    for query_id, expected_names in expected_by_query.items():
        query = telemetry["queries"][query_id]
        if query["expectedSignalNames"] != expected_names:
            raise ValueError(f"telemetry {query_id} names differ from signal contract")
        result_path = _resolve_repository_path(repository_root, query["resultFile"])
        result = load_json(result_path)
        _validate_schema(
            contracts_directory / "telemetry-query-result.schema.json",
            result,
        )
        if result["queryId"] != query_id:
            raise ValueError(f"telemetry result query ID differs for {query_id}")
        rows = {row["signalName"]: row for row in result["rows"]}
        if set(rows) != set(expected_names) or len(rows) != len(result["rows"]):
            raise ValueError(f"telemetry {query_id} result set is incomplete or duplicated")
        if query_id == "resources":
            resource_row = rows["resource"]
            if not set(telemetry["resourceAttributes"]).issubset(
                resource_row["observedAttributes"]
            ):
                raise ValueError("telemetry resource attributes were not all observed")
            if resource_row.get("resourceAttributes") != telemetry["resourceAttributes"]:
                raise ValueError("telemetry resource query values differ from evidence")
            continue
        for signal_name, row in rows.items():
            required_attributes = set(attributes_by_query[query_id][signal_name])
            if not required_attributes.issubset(row["observedAttributes"]):
                raise ValueError(
                    f"telemetry signal {signal_name} lacks required attributes"
                )


def _resolve_repository_path(repository_root: Path, value: str) -> Path:
    """Resolve a declared repository path and reject traversal through symlinks."""
    root = repository_root.resolve()
    candidate = (root / value).resolve()
    try:
        candidate.relative_to(root)
    except ValueError as error:
        raise ValueError(f"repository path escapes root: {value}") from error
    return candidate


def _require_nonempty(path: Path) -> None:
    """Require one referenced file or directory to contain durable evidence."""
    if path.is_file() and path.stat().st_size > 0:
        return
    if path.is_dir() and any(
        child.is_file() and child.stat().st_size > 0 for child in path.rglob("*")
    ):
        return
    raise ValueError(f"referenced handoff artifact is empty: {path}")


def _require_iac(path: Path, mechanism: str) -> None:
    """Require non-empty mechanism-appropriate infrastructure source."""
    suffixes = (
        {".bicep"}
        if mechanism == "bicep"
        else {".tf"}
        if mechanism == "terraform"
        else {".bicep", ".tf"}
    )
    candidates = [path] if path.is_file() else list(path.rglob("*"))
    if any(
        candidate.is_file()
        and candidate.suffix in suffixes
        and candidate.stat().st_size > 0
        for candidate in candidates
    ):
        return
    raise ValueError(
        f"IaC artifact has no non-empty {sorted(suffixes)} source: {path}"
    )


def _parse_resource_id(value: str) -> dict[str, Any]:
    """Parse and normalize an Azure resource ID with exact type/name pairs."""
    parts = value.strip("/").split("/")
    if (
        len(parts) < 8
        or parts[0].casefold() != "subscriptions"
        or parts[2].casefold() != "resourcegroups"
        or parts[4].casefold() != "providers"
        or (len(parts) - 6) % 2 != 0
    ):
        raise ValueError(f"malformed Azure resource ID: {value}")
    UUID(parts[1])
    resource_pairs = parts[6:]
    return {
        "subscription": parts[1].casefold(),
        "resourceGroup": parts[3].casefold(),
        "namespace": parts[5].casefold(),
        "types": tuple(part.casefold() for part in resource_pairs[0::2]),
        "names": tuple(resource_pairs[1::2]),
    }


def _validate_resource_ids(handoff: dict[str, Any]) -> None:
    """Require exact Azure providers, resource types, names, and common scope."""
    resources = {
        "application": (
            handoff["application"]["resourceId"],
            ("microsoft.app", ("containerapps",)),
        ),
        "registry": (
            handoff["containerImage"]["registryResourceId"],
            ("microsoft.containerregistry", ("registries",)),
        ),
        "database": (
            handoff["database"]["resourceId"],
            (
                (
                    "microsoft.sql",
                    ("servers", "databases"),
                )
                if handoff["database"]["family"] == "azure-sql"
                else (
                    "microsoft.dbforpostgresql",
                    ("flexibleservers", "databases"),
                )
            ),
        ),
        "images": (
            handoff["images"]["resourceId"],
            (
                (
                    "microsoft.storage",
                    ("storageaccounts", "fileservices", "shares"),
                )
                if handoff["images"]["provider"] == "azure-files"
                else (
                    "microsoft.storage",
                    ("storageaccounts", "blobservices", "containers"),
                )
            ),
        ),
        "applicationInsights": (
            handoff["observability"]["applicationInsightsResourceId"],
            ("microsoft.insights", ("components",)),
        ),
        "logAnalytics": (
            handoff["observability"]["logAnalyticsWorkspaceResourceId"],
            ("microsoft.operationalinsights", ("workspaces",)),
        ),
    }
    parsed: dict[str, dict[str, Any]] = {}
    for name, (resource_id, expected) in resources.items():
        resource = _parse_resource_id(resource_id)
        if (resource["namespace"], resource["types"]) != expected:
            raise ValueError(f"{name} resource ID has the wrong provider or type")
        parsed[name] = resource

    subscriptions = {resource["subscription"] for resource in parsed.values()}
    resource_groups = {resource["resourceGroup"] for resource in parsed.values()}
    if len(subscriptions) != 1:
        raise ValueError("handoff resources span multiple subscriptions")
    if resource_groups != {handoff["application"]["resourceGroup"].casefold()}:
        raise ValueError("handoff resource IDs do not match the declared resource group")
    if parsed["application"]["names"][-1] != handoff["application"]["containerAppName"]:
        raise ValueError("container app resource ID name differs from handoff")
    registry_name = parsed["registry"]["names"][-1]
    if handoff["containerImage"]["registry"] != f"{registry_name}.azurecr.io":
        raise ValueError("registry hostname differs from registry resource ID")
    database_server_name, database_name = parsed["database"]["names"][-2:]
    if (
        not handoff["database"]["server"].casefold().startswith(
            f"{database_server_name.casefold()}."
        )
        or database_name != handoff["database"]["database"]
    ):
        raise ValueError("database resource ID names differ from handoff")
    if parsed["images"]["names"][-1] != handoff["images"]["location"]:
        raise ValueError("image location differs from image resource ID")


def validate_handoff(
    handoff_path: Path,
    contracts_directory: Path,
    repository_root: Path,
) -> dict[str, Any]:
    """Validate a handoff and all evidence required by downstream challenges.

    Raises:
        ValueError: If evidence is inconsistent across contract files.
        jsonschema.ValidationError: If a document does not match its schema.
        FileNotFoundError: If required evidence is absent.
    """
    handoff = load_json(handoff_path)
    _validate_schema(
        contracts_directory / "modernization-contract.schema.json",
        handoff,
    )
    root = repository_root.resolve()
    try:
        handoff_path.resolve().relative_to(root)
    except ValueError as error:
        raise ValueError("handoff file must be inside the repository root") from error

    report_path = _resolve_repository_path(root, handoff["acceptance"]["report"])
    report_data = load_json(report_path)
    _validate_schema(
        contracts_directory / "acceptance-report.schema.json",
        report_data,
    )
    report = AcceptanceReport.model_validate(report_data)

    telemetry_path = _resolve_repository_path(
        root, handoff["evidence"]["telemetryReport"]
    )
    telemetry = load_json(telemetry_path)
    _validate_schema(
        contracts_directory / "telemetry-evidence.schema.json",
        telemetry,
    )
    runtime_test_path = _resolve_repository_path(
        root, handoff["evidence"]["runtimeTestReport"]
    )
    runtime_tests = load_json(runtime_test_path)
    _validate_schema(
        contracts_directory / "runtime-test-evidence.schema.json",
        runtime_tests,
    )
    runtime_artifact = _resolve_repository_path(root, runtime_tests["artifact"])
    iac_path = _resolve_repository_path(root, handoff["deployment"]["iacPath"])
    runbook_path = _resolve_repository_path(root, handoff["rollback"]["runbook"])
    required_paths = [iac_path, runbook_path, runtime_artifact]
    for optional_name in ("assessment", "dependencyReport"):
        if optional_path := handoff["evidence"].get(optional_name):
            required_paths.append(_resolve_repository_path(root, optional_path))
    for required_path in required_paths:
        if not required_path.exists():
            raise FileNotFoundError(f"referenced handoff artifact is absent: {required_path}")
        _require_nonempty(required_path)
    _require_iac(iac_path, handoff["deployment"]["mechanism"])
    if not runbook_path.is_file():
        raise ValueError("rollback runbook must be a non-empty file")
    _validate_runtime_results(runtime_tests, runtime_artifact)
    _validate_telemetry_results(telemetry, contracts_directory, root)
    _validate_resource_ids(handoff)

    manifest = load_json(root / "data" / "manifest.json")
    expected_seed = {
        "schemaVersion": manifest["schemaVersion"],
        "counts": manifest["counts"],
        "hashes": manifest["hashes"],
    }

    expected_database_kind = (
        "sqlserver"
        if handoff["source"]["stack"] == "dotnet-sqlserver"
        else "postgresql"
    )
    expected_database_family = (
        "azure-sql"
        if handoff["source"]["stack"] == "dotnet-sqlserver"
        else "postgresql-flexible"
    )
    expected_service = (
        "mh-catalog-dotnet"
        if handoff["source"]["stack"] == "dotnet-sqlserver"
        else "mh-catalog-java"
    )

    inconsistencies: list[str] = []
    if report.profile != "full" or report.status != "passed":
        inconsistencies.append("acceptance evidence must be a full passing report")
    if report.database_target != "managed":
        inconsistencies.append("handoff acceptance must target a managed database")
    if report.subject is None:
        inconsistencies.append("handoff acceptance lacks immutable release identity")
    else:
        if report.subject.source_commit != handoff["source"]["commitSha"]:
            inconsistencies.append("acceptance source commit does not match handoff")
        if report.subject.image_digest != handoff["containerImage"]["digest"]:
            inconsistencies.append("acceptance image digest does not match handoff")
        if report.subject.revision_name != handoff["application"]["revisionName"]:
            inconsistencies.append("acceptance revision does not match handoff")
    if handoff["seedManifest"] != expected_seed:
        inconsistencies.append("handoff seed manifest differs from canonical manifest")
    if handoff["containerImage"]["tag"] != handoff["source"]["commitSha"]:
        inconsistencies.append("container tag must equal the immutable source commit")
    if report.database_kind != expected_database_kind:
        inconsistencies.append("acceptance database kind does not match source stack")
    if handoff["database"]["family"] != expected_database_family:
        inconsistencies.append("managed database family does not match source stack")
    expected_image_auth = (
        "aca-volume-secret"
        if handoff["images"]["provider"] == "azure-files"
        else "managed-identity"
    )
    if handoff["authentication"]["imageStore"] != expected_image_auth:
        inconsistencies.append("image-store authentication does not match its provider")
    if handoff["observability"]["serviceName"] != expected_service:
        inconsistencies.append("OpenTelemetry service name does not match source stack")
    if telemetry["service"] != expected_service:
        inconsistencies.append("telemetry evidence service does not match source stack")
    if runtime_tests["stack"] != handoff["source"]["stack"]:
        inconsistencies.append("runtime test stack does not match source stack")
    if runtime_tests["sourceCommit"] != handoff["source"]["commitSha"]:
        inconsistencies.append("runtime test commit does not match source commit")
    if telemetry["resourceAttributes"]["service.name"] != expected_service:
        inconsistencies.append("telemetry service.name does not match source stack")
    if (
        telemetry["resourceAttributes"]["service.version"]
        != handoff["observability"]["serviceVersion"]
    ):
        inconsistencies.append("telemetry service.version does not match handoff")
    if handoff["observability"]["serviceVersion"] not in (
        handoff["source"]["commitSha"],
        handoff["containerImage"]["tag"],
    ):
        inconsistencies.append("service version is not bound to the release identity")
    if (
        telemetry["resourceAttributes"]["deployment.environment"]
        != handoff["observability"]["environment"]
    ):
        inconsistencies.append("telemetry environment does not match handoff")
    if (
        telemetry["resourceAttributes"]["service.instance.id"]
        != handoff["observability"]["serviceInstanceId"]
    ):
        inconsistencies.append("telemetry service instance does not match handoff")
    if (
        telemetry["resourceAttributes"]["azure.containerapps.revision.name"]
        != handoff["observability"]["revision"]
        or handoff["observability"]["revision"]
        != handoff["application"]["revisionName"]
    ):
        inconsistencies.append("telemetry and application revisions do not match")
    if str(report.base_url).rstrip("/") != handoff["application"]["url"].rstrip("/"):
        inconsistencies.append("acceptance base URL does not match application URL")
    if handoff["application"]["healthUrl"] != (
        f'{handoff["application"]["url"].rstrip("/")}/healthz'
    ):
        inconsistencies.append("health URL does not match application URL")
    if handoff["application"]["readinessUrl"] != (
        f'{handoff["application"]["url"].rstrip("/")}/readyz'
    ):
        inconsistencies.append("readiness URL does not match application URL")
    if handoff["rollback"]["targetRevision"] == handoff["application"]["revisionName"]:
        inconsistencies.append("rollback target must differ from the deployed revision")

    expected_counts = handoff["database"]["verifiedRowCounts"]
    if (
        report.corpus.figures != expected_counts["figures"]
        or report.corpus.categories != expected_counts["categories"]
    ):
        inconsistencies.append("acceptance corpus does not match database verification")
    if report.corpus.images != handoff["images"]["verification"]["imageCount"]:
        inconsistencies.append("acceptance corpus does not match image verification")
    if expected_counts != {
        "figures": manifest["counts"]["figures"],
        "categories": manifest["counts"]["categories"],
    }:
        inconsistencies.append("database verification differs from canonical manifest")
    image_verification = handoff["images"]["verification"]
    if (
        image_verification["imageCount"] != manifest["counts"]["images"]
        or image_verification["imageBytes"] != manifest["counts"]["imageBytes"]
        or image_verification["imageSetSha256"]
        != manifest["hashes"]["imageSetSha256"]
    ):
        inconsistencies.append("image verification differs from canonical manifest")

    if inconsistencies:
        raise ValueError("; ".join(inconsistencies))
    return handoff
