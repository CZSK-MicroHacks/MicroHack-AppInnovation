"""Validate modernization handoff bundles and their referenced evidence."""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any
from uuid import UUID
from xml.etree import ElementTree

from jsonschema import Draft202012Validator, FormatChecker

from catalog_acceptance.manifest import load_json
from catalog_acceptance.models.contracts import AcceptanceReport

REQUIRED_RUNTIME_TESTS = {
    "dotnet-sqlserver": {
        "liveness-database-outage": (
            "Contract.Health.LivenessSurvivesDatabaseOutage",
            "LegoCatalog.App.Tests.HealthContractTests.LivenessSurvivesDatabaseOutage",
        ),
        "readiness-database-outage": (
            "Contract.Health.ReadinessFailsDuringDatabaseOutage",
            "LegoCatalog.App.Tests.HealthContractTests.ReadinessFailsDuringDatabaseOutage",
        ),
        "readiness-import-failure": (
            "Contract.Health.ReadinessReportsImportFailure",
            "LegoCatalog.App.Tests.HealthContractTests.ReadinessReportsImportFailure",
        ),
        "performance-database-failure": (
            "Contract.Performance.DatabaseFailureIsControlled",
            "LegoCatalog.App.Tests.PerformanceContractTests.DatabaseFailureIsControlled",
        ),
        "performance-timeout": (
            "Contract.Performance.TimeoutIsControlled",
            "LegoCatalog.App.Tests.PerformanceContractTests.TimeoutIsControlled",
        ),
        "performance-missing-key": (
            "Contract.Performance.MissingKeyReturnsUnauthorized",
            "LegoCatalog.App.Tests.PerformanceContractTests.MissingKeyReturnsUnauthorized",
        ),
        "performance-invalid-key": (
            "Contract.Performance.InvalidKeyReturnsUnauthorized",
            "LegoCatalog.App.Tests.PerformanceContractTests.InvalidKeyReturnsUnauthorized",
        ),
        "work-factor-default": (
            "Contract.Performance.MissingWorkFactorUsesDefault",
            "LegoCatalog.App.Tests.PerformanceContractTests.MissingWorkFactorUsesDefault",
        ),
        "work-factor-bounds": (
            "Contract.Performance.BoundsAreAccepted",
            "LegoCatalog.App.Tests.PerformanceContractTests.BoundsAreAccepted",
        ),
        "work-factor-invalid": (
            "Contract.Performance.InvalidWorkFactorsFailStartup",
            "LegoCatalog.App.Tests.PerformanceContractTests.InvalidWorkFactorsFailStartup",
        ),
        "normalization-conformance": (
            "Contract.Conformance.NormalizationVectors",
            "LegoCatalog.App.Tests.ConformanceVectorTests.CategorySlugMatchesSharedVectors",
        ),
        "text-validation-conformance": (
            "Contract.Conformance.TextValidationVectors",
            "LegoCatalog.App.Tests.ConformanceVectorTests.TextValidationMatchesSharedVectors",
        ),
        "final-response-status": (
            "Contract.Telemetry.FinalResponseStatus",
            "LegoCatalog.App.Tests.TelemetryContractTests.RequestLogUsesMatchedRouteAndFinalStatus",
        ),
        "rejected-document-increments-once": (
            "Contract.Telemetry.RejectedDocumentIncrementsOnce",
            "LegoCatalog.App.Tests.TelemetryContractTests.RejectedDocumentRecordsExactlyOneRejectedUnit",
        ),
    },
    "java-postgresql": {
        "liveness-database-outage": (
            "Contract.Health.LivenessSurvivesDatabaseOutage",
            "com.microsoft.microhack.catalog.RuntimeHealthContractTest#Contract.Health.LivenessSurvivesDatabaseOutage",
        ),
        "readiness-database-outage": (
            "Contract.Health.ReadinessFailsDuringDatabaseOutage",
            "com.microsoft.microhack.catalog.RuntimeHealthContractTest#Contract.Health.ReadinessFailsDuringDatabaseOutage",
        ),
        "readiness-import-failure": (
            "Contract.Health.ReadinessReportsImportFailure",
            "com.microsoft.microhack.catalog.RuntimeHealthContractTest#Contract.Health.ReadinessReportsImportFailure",
        ),
        "performance-database-failure": (
            "Contract.Performance.DatabaseFailureIsControlled",
            "com.microsoft.microhack.catalog.RuntimePerformanceContractTest#Contract.Performance.DatabaseFailureIsControlled",
        ),
        "performance-timeout": (
            "Contract.Performance.TimeoutIsControlled",
            "com.microsoft.microhack.catalog.RuntimePerformanceContractTest#Contract.Performance.TimeoutIsControlled",
        ),
        "performance-missing-key": (
            "Contract.Performance.MissingKeyReturnsUnauthorized",
            "com.microsoft.microhack.catalog.RuntimePerformanceContractTest#Contract.Performance.MissingKeyReturnsUnauthorized",
        ),
        "performance-invalid-key": (
            "Contract.Performance.InvalidKeyReturnsUnauthorized",
            "com.microsoft.microhack.catalog.RuntimePerformanceContractTest#Contract.Performance.InvalidKeyReturnsUnauthorized",
        ),
        "work-factor-default": (
            "Contract.Performance.MissingWorkFactorUsesDefault",
            "com.microsoft.microhack.catalog.RuntimePerformanceContractTest#Contract.Performance.MissingWorkFactorUsesDefault",
        ),
        "work-factor-bounds": (
            "Contract.Performance.BoundsAreAccepted",
            "com.microsoft.microhack.catalog.RuntimePerformanceContractTest#Contract.Performance.BoundsAreAccepted",
        ),
        "work-factor-invalid": (
            "Contract.Performance.InvalidWorkFactorsFailStartup",
            "com.microsoft.microhack.catalog.RuntimePerformanceContractTest#Contract.Performance.InvalidWorkFactorsFailStartup",
        ),
        "normalization-conformance": (
            "Contract.Conformance.NormalizationVectors",
            "com.microsoft.microhack.catalog.ConformanceVectorTest#Contract.Conformance.NormalizationVectors",
        ),
        "text-validation-conformance": (
            "Contract.Conformance.TextValidationVectors",
            "com.microsoft.microhack.catalog.ConformanceVectorTest#Contract.Conformance.TextValidationVectors",
        ),
        "final-response-status": (
            "Contract.Telemetry.FinalResponseStatus",
            "com.microsoft.microhack.catalog.TelemetryContractTest#Contract.Telemetry.FinalResponseStatus",
        ),
        "rejected-document-increments-once": (
            "Contract.Telemetry.RejectedDocumentIncrementsOnce",
            "com.microsoft.microhack.catalog.TelemetryContractTest#Contract.Telemetry.RejectedDocumentIncrementsOnce",
        ),
    },
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
) -> dict[tuple[str, str], list[str]]:
    """Parse results into display-name and fully qualified identity outcomes."""
    outcomes: dict[tuple[str, str], list[str]] = {}
    for result_path in _xml_files(artifact, artifact_format):
        root = ElementTree.parse(result_path).getroot()
        if artifact_format == "trx":
            definitions: dict[str, str] = {}
            for definition in root.iter():
                if definition.tag.rsplit("}", 1)[-1] != "UnitTest":
                    continue
                test_id = definition.attrib.get("id")
                method = next(
                    (
                        child
                        for child in definition.iter()
                        if child.tag.rsplit("}", 1)[-1] == "TestMethod"
                    ),
                    None,
                )
                if test_id and method is not None:
                    class_name = method.attrib.get("className")
                    method_name = method.attrib.get("name")
                    if class_name and method_name:
                        definitions[test_id] = f"{class_name}.{method_name}"
            for result in root.iter():
                if result.tag.rsplit("}", 1)[-1] != "UnitTestResult":
                    continue
                name = result.attrib.get("testName")
                identity = definitions.get(result.attrib.get("testId", ""))
                outcome = result.attrib.get("outcome")
                if name and identity and outcome:
                    outcomes.setdefault((name, identity), []).append(outcome.casefold())
        else:
            for case in root.iter():
                if case.tag.rsplit("}", 1)[-1] != "testcase":
                    continue
                name = case.attrib.get("name")
                class_name = case.attrib.get("classname")
                if not name or not class_name:
                    continue
                failed = any(
                    child.tag.rsplit("}", 1)[-1]
                    in ("failure", "error", "skipped")
                    for child in case
                )
                outcomes.setdefault((name, f"{class_name}#{name}"), []).append(
                    "failed" if failed else "passed"
                )
    return outcomes


def _validate_runtime_results(runtime_tests: dict[str, Any], artifact: Path) -> None:
    """Require every frozen runtime test ID to map to a native passing result."""
    mapping = {
        test["id"]: (test["testName"], test["testIdentity"])
        for test in runtime_tests["tests"]
    }
    expected = REQUIRED_RUNTIME_TESTS[runtime_tests["stack"]]
    if len(mapping) != len(runtime_tests["tests"]) or mapping != expected:
        raise ValueError(
            "runtime evidence differs from the exact stack requirement mapping"
        )
    outcomes = _runtime_test_outcomes(artifact, runtime_tests["artifactFormat"])
    failures = [
        f"{name} ({identity})"
        for name, identity in mapping.values()
        if (name, identity) not in outcomes
        or not outcomes[(name, identity)]
        or any(outcome != "passed" for outcome in outcomes[(name, identity)])
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
    route_probe = {
        "http.request.method": "GET",
        "http.route": "/figure/{id}",
        "http.response.status_code": 200,
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
            if query_id == "metrics":
                expected_unit = behavior["metricUnits"][signal_name]
                if row["unit"] != expected_unit:
                    raise ValueError(
                        f"telemetry metric {signal_name} unit differs from contract"
                    )
        if query_id == "metrics":
            rejected = [
                measurement
                for measurement in rows["catalog.import.records"]["measurements"]
                if measurement["attributes"].get("catalog.import.outcome")
                == "rejected"
            ]
            if not rejected or any(
                type(item.get("value")) not in (int, float)
                or not math.isfinite(float(item["value"]))
                or item["value"] <= 0
                or not float(item["value"]).is_integer()
                for item in rejected
            ):
                raise ValueError(
                    "catalog import rejected measurements must contain positive integral aggregates"
                )
        if query_id == "traces":
            route_observations = rows["http.server"]["observations"]
        elif query_id == "metrics":
            route_observations = rows["http.server.request.duration"]["measurements"]
        else:
            route_observations = rows["http.server.request"]["observations"]
        if not any(
            all(
                observation["attributes"].get(key) == value
                for key, value in route_probe.items()
            )
            for observation in route_observations
        ):
            raise ValueError(
                f"telemetry {query_id} lacks matched route-template value evidence"
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
