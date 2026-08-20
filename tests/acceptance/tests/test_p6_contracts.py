"""Executable contract freeze for the shared P6 workshop challenges."""

from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path, PurePosixPath
import subprocess
from typing import Any

import pytest
from jsonschema import Draft202012Validator, FormatChecker
from jsonschema.exceptions import ValidationError as JsonSchemaValidationError

from catalog_acceptance.manifest import load_json
from catalog_acceptance import shared_challenges


def _validate(schema: dict, instance: object) -> None:
    """Validate one P6 contract instance with strict format checking."""
    Draft202012Validator(schema, format_checker=FormatChecker()).validate(instance)


def _contracts(repo_root: Path) -> Path:
    """Return the repository contract directory."""
    return repo_root / "workshop/contracts"


def _commit_control_handoff(repository_root: Path, handoff_path: Path) -> str:
    """Commit the synthetic handoff and return its immutable control SHA."""
    subprocess.run(
        ["git", "-C", str(repository_root), "init", "--quiet"],
        check=True,
    )
    subprocess.run(
        [
            "git",
            "-C",
            str(repository_root),
            "add",
            str(handoff_path.relative_to(repository_root)),
        ],
        check=True,
    )
    subprocess.run(
        [
            "git",
            "-C",
            str(repository_root),
            "-c",
            "user.name=Contract Test",
            "-c",
            "user.email=contract-test@example.invalid",
            "commit",
            "--quiet",
            "-m",
            "Add control handoff",
        ],
        check=True,
    )
    return subprocess.run(
        ["git", "-C", str(repository_root), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _write_json(path: Path, value: dict[str, Any]) -> None:
    """Write one deterministic JSON fixture."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _write_declared_files(value: Any, repository_root: Path) -> None:
    """Materialize every declared evidence or implementation file."""
    if isinstance(value, dict):
        for key, child in value.items():
            if key.lower().endswith("file") and isinstance(child, str):
                path = repository_root / child
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("fixture\n", encoding="utf-8")
            else:
                _write_declared_files(child, repository_root)
    elif isinstance(value, list):
        for child in value:
            _write_declared_files(child, repository_root)


def _serialized_workbook(evidence: dict[str, Any]) -> str:
    """Build the exact deployed workbook payload used by synthetic observations."""
    return json.dumps(
        {
            "version": "Notebook/1.0",
            "items": [
                {
                    "type": 3,
                    "name": panel["id"],
                    "content": {
                        "version": "KqlItem/1.0",
                        "queryType": 0,
                        "resourceType": "microsoft.operationalinsights/workspaces",
                        "query": panel["query"],
                    },
                }
                for panel in evidence["panels"]
            ],
        },
        separators=(",", ":"),
        sort_keys=True,
    )


def _normalized_observations(
    kind: str,
    evidence: dict[str, Any],
    handoff: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    """Build normalized observations for one schema-valid P6 example."""
    version = {"schemaVersion": "1.1.0"}
    if kind == "load":
        return {
            evidence["testRun"]["resultFile"]: {
                **version,
                "resourceId": evidence["testRun"]["resourceId"],
                "testRunId": evidence["testRun"]["testRunId"],
                "testId": evidence["testRun"]["testId"],
                "applicationUrl": evidence["testRun"]["applicationUrl"],
                "targetUrl": evidence["testRun"]["targetUrl"],
                "revisionName": handoff["application"]["revisionName"],
                "performancePath": "/perftest/catalog",
                "configurationFile": evidence["testRun"]["configurationFile"],
                "configurationSha256": evidence["testRun"]["configurationSha256"],
                "jmeterFile": evidence["testRun"]["jmeterFile"],
                "jmeterSha256": evidence["testRun"]["jmeterSha256"],
                "status": "DONE",
                "startedAt": evidence["testRun"]["startedAt"],
                "completedAt": evidence["testRun"]["completedAt"],
                "totalRequests": 1200,
                "failedRequests": 0,
                "virtualUsers": evidence["testRun"]["virtualUsers"],
                "durationSeconds": evidence["testRun"]["durationSeconds"],
                "capturedAt": evidence["capturedAt"],
            },
            evidence["scaleConfiguration"]["resultFile"]: {
                **version,
                "source": "azure-resource-manager",
                "containerAppResourceId": handoff["application"]["resourceId"],
                "revisionName": handoff["application"]["revisionName"],
                "minimumReplicas": 1,
                "maximumReplicas": 3,
                "ruleName": "http",
                "ruleType": "http",
                "concurrentRequests": 50,
                "provisioningState": "Succeeded",
                "etag": "W/\"scale-config-000001\"",
                "observedAt": evidence["scaleConfiguration"]["observedAt"],
            },
            evidence["replicas"]["resultFile"]: {
                **version,
                "resourceId": handoff["application"]["resourceId"],
                "metric": "Replicas",
                "aggregation": "Maximum",
                "startTime": "2026-08-20T11:50:00Z",
                "endTime": "2026-08-20T12:15:00Z",
                "points": [
                    {"timestamp": "2026-08-20T11:59:00Z", "value": 1},
                    {"timestamp": "2026-08-20T12:01:00Z", "value": 2},
                    {"timestamp": "2026-08-20T12:03:00Z", "value": 3},
                    {"timestamp": "2026-08-20T12:10:00Z", "value": 1},
                ],
            },
            evidence["databaseSignal"]["resultFile"]: {
                **version,
                "resourceId": handoff["database"]["resourceId"],
                "metric": "app_cpu_billed",
                "aggregation": "Total",
                "startTime": "2026-08-20T11:50:00Z",
                "endTime": "2026-08-20T12:15:00Z",
                "points": [
                    {
                        "timestamp": "2026-08-20T11:59:00Z",
                        "value": evidence["databaseSignal"]["baseline"],
                    },
                    {
                        "timestamp": "2026-08-20T12:03:00Z",
                        "value": evidence["databaseSignal"]["peak"],
                    },
                ],
            },
            evidence["recovery"]["resultFile"]: {
                **version,
                "healthUrl": handoff["application"]["healthUrl"],
                "readinessUrl": handoff["application"]["readinessUrl"],
                "revisionName": handoff["application"]["revisionName"],
                "observedAt": evidence["windows"]["recoveryEnd"],
                "healthStatus": 200,
                "readinessStatus": 200,
            },
        }
    if kind == "cicd":
        image_reference = evidence["image"]["reference"]
        previous = evidence["revisions"]["previous"]
        candidate = evidence["revisions"]["candidate"]
        run_binding = {
            **version,
            "runId": int(evidence["workflow"]["runId"]),
            "runAttempt": evidence["workflow"]["runAttempt"],
            "githubRepository": evidence["workflow"]["repository"],
            "workflowPath": evidence["workflow"]["file"],
            "headSha": evidence["workflow"]["headSha"],
            "ref": evidence["workflow"]["ref"],
        }

        def traffic(
            previous_weight: int,
            candidate_weight: int,
            observed_at: str,
        ) -> dict[str, Any]:
            """Build one normalized two-revision traffic observation."""
            return {
                **run_binding,
                "containerAppResourceId": handoff["application"]["resourceId"],
                "previousRevision": previous,
                "candidateRevision": candidate,
                "previousWeight": previous_weight,
                "candidateWeight": candidate_weight,
                "previousActive": True,
                "candidateActive": True,
                "previousHealthState": "Healthy",
                "candidateHealthState": "Healthy",
                "applicationUrl": handoff["application"]["url"],
                "healthUrl": handoff["application"]["healthUrl"],
                "readinessUrl": handoff["application"]["readinessUrl"],
                "healthStatus": 200,
                "readinessStatus": 200,
                "observedAt": observed_at,
            }

        return {
            evidence["workflow"]["resultFile"]: {
                **run_binding,
                "status": "completed",
                "conclusion": "success",
                "event": "workflow_dispatch",
                "jobs": [
                    {
                        "jobId": evidence["workflow"]["jobs"][environment]["jobId"],
                        "name": environment,
                        "environment": environment,
                        "status": "completed",
                        "conclusion": "success",
                        "startedAt": evidence["workflow"]["jobs"][environment][
                            "startedAt"
                        ],
                        "completedAt": evidence["workflow"]["jobs"][environment][
                            "completedAt"
                        ],
                    }
                    for environment in ("staging", "production")
                ],
                "capturedAt": "2026-08-20T13:31:00Z",
            },
            evidence["identity"]["resultFile"]: {
                **run_binding,
                "identityKind": "user-assigned-managed-identity",
                "resourceId": evidence["identity"]["resourceId"],
                "clientId": evidence["identity"]["clientId"],
                "principalId": evidence["identity"]["principalId"],
                "stagingFederatedSubject": evidence["identity"][
                    "stagingFederatedSubject"
                ],
                "productionFederatedSubject": evidence["identity"][
                    "productionFederatedSubject"
                ],
                "acrRoleDefinitionId": evidence["identity"]["acrRoleDefinitionId"],
                "acrScope": evidence["identity"]["acrScope"],
                "containerAppRoleDefinitionId": evidence["identity"][
                    "containerAppRoleDefinitionId"
                ],
                "containerAppScope": evidence["identity"]["containerAppScope"],
                "clientSecretUsed": False,
                "registryAdminUsed": False,
                "roleAssignmentEnumeration": evidence["identity"][
                    "roleAssignmentEnumeration"
                ],
                "federatedCredentials": [
                    {
                        "environment": environment,
                        "resourceId": evidence["identity"][
                            "federatedCredentialResourceIds"
                        ][environment],
                        "subject": evidence["identity"][
                            f"{environment}FederatedSubject"
                        ],
                        "issuer": "https://token.actions.githubusercontent.com",
                        "audiences": ["api://AzureADTokenExchange"],
                    }
                    for environment in ("staging", "production")
                ],
                "roleAssignments": [
                    {
                        "resourceId": (
                            f"{evidence['identity']['acrScope']}/providers/"
                            "Microsoft.Authorization/roleAssignments/"
                            "00000000-0000-0000-0000-000000000005"
                        ),
                        "principalId": evidence["identity"]["principalId"],
                        "roleDefinitionId": evidence["identity"][
                            "acrRoleDefinitionId"
                        ],
                        "scope": evidence["identity"]["acrScope"],
                    },
                    {
                        "resourceId": (
                            f"{evidence['identity']['containerAppScope']}/providers/"
                            "Microsoft.Authorization/roleAssignments/"
                            "00000000-0000-0000-0000-000000000006"
                        ),
                        "principalId": evidence["identity"]["principalId"],
                        "roleDefinitionId": evidence["identity"][
                            "containerAppRoleDefinitionId"
                        ],
                        "scope": evidence["identity"]["containerAppScope"],
                    },
                ],
                "observedAt": evidence["identity"][
                    "roleAssignmentEnumeration"
                ]["performedAt"],
            },
            evidence["image"]["resultFile"]: {
                **run_binding,
                "sourceCommit": handoff["source"]["commitSha"],
                "registryResourceId": handoff["containerImage"]["registryResourceId"],
                "repository": evidence["image"]["repository"],
                "tag": evidence["image"]["tag"],
                "digest": evidence["image"]["digest"],
                "reference": image_reference,
                "completedAt": "2026-08-20T12:35:00Z",
                "status": "success",
            },
            evidence["revisions"]["resultFile"]: {
                **run_binding,
                "containerAppResourceId": handoff["application"]["resourceId"],
                "revisionName": candidate,
                "imageReference": image_reference,
                "active": True,
                "healthState": "Healthy",
                "trafficWeight": 0,
                "label": "candidate",
                "labelUrl": evidence["revisions"]["candidateUrl"],
                "observedAt": "2026-08-20T12:40:00Z",
            },
            evidence["smoke"]["resultFile"]: {
                **run_binding,
                "candidateUrl": evidence["smoke"]["candidateUrl"],
                "healthUrl": evidence["smoke"]["healthUrl"],
                "readinessUrl": evidence["smoke"]["readinessUrl"],
                "revisionName": candidate,
                "imageReference": image_reference,
                "observedAt": "2026-08-20T12:45:00Z",
                "healthStatus": 200,
                "readinessStatus": 200,
            },
            evidence["approval"]["resultFile"]: {
                **run_binding,
                "environment": "production",
                "reviewer": evidence["approval"]["reviewer"],
                "approvedAt": evidence["approval"]["approvedAt"],
                "state": "approved",
            },
            evidence["traffic"]["before"]["resultFile"]: traffic(
                100, 0, evidence["traffic"]["before"]["observedAt"]
            ),
            evidence["traffic"]["promotion"]["resultFile"]: traffic(
                0, 100, evidence["traffic"]["promotion"]["observedAt"]
            ),
            evidence["traffic"]["rollback"]["resultFile"]: traffic(
                100, 0, evidence["traffic"]["rollback"]["observedAt"]
            ),
            evidence["traffic"]["safety"]["resultFile"]: {
                **run_binding,
                **{
                    key: value
                    for key, value in evidence["traffic"]["safety"].items()
                    if key != "resultFile"
                },
            },
        }
    serialized_data = _serialized_workbook(evidence)
    observations: dict[str, dict[str, Any]] = {
        evidence["metricsExport"]["resultFile"]: {
            **version,
            "containerAppResourceId": handoff["application"]["resourceId"],
            "workspaceResourceId": handoff["observability"][
                "logAnalyticsWorkspaceResourceId"
            ],
            "diagnosticSettingName": "all-metrics-to-workspace",
            "metricCategory": "AllMetrics",
            "destinationTable": "AzureMetrics",
            "enabled": True,
            "observedAt": evidence["metricsExport"]["deployedAt"],
        },
        evidence["workbook"]["resultFile"]: {
            **version,
            "workbookResourceId": evidence["workbook"]["resourceId"],
            "applicationInsightsResourceId": handoff["observability"][
                "applicationInsightsResourceId"
            ],
            "logAnalyticsWorkspaceResourceId": handoff["observability"][
                "logAnalyticsWorkspaceResourceId"
            ],
            "sourceId": handoff["observability"][
                "logAnalyticsWorkspaceResourceId"
            ],
            "apiVersion": "2023-06-01",
            "sourceCommit": handoff["source"]["commitSha"],
            "revisionName": handoff["application"]["revisionName"],
            "templateSha256": evidence["workbook"]["templateSha256"],
            "queriesSha256": evidence["workbook"]["queriesSha256"],
            "serializedData": serialized_data,
            "serializedDataSha256": hashlib.sha256(
                serialized_data.encode("utf-8")
            ).hexdigest(),
            "deployedAt": evidence["workbook"]["deployedAt"],
            "capturedAt": evidence["workbook"]["deployedAt"],
        }
    }
    for panel in evidence["panels"]:
        row: dict[str, Any] = {
            "timestamp": "2026-08-20T13:50:00Z",
            "value": 1,
        }
        if panel["id"] == "error-rate":
            row.update({"totalRequests": 100, "failedRequests": 1})
        observations[panel["resultFile"]] = {
            **version,
            "queryId": panel["id"],
            "resultKind": panel["resultKind"],
            "applicationInsightsResourceId": handoff["observability"][
                "applicationInsightsResourceId"
            ],
            "logAnalyticsWorkspaceResourceId": handoff["observability"][
                "logAnalyticsWorkspaceResourceId"
            ],
            "sourceCommit": handoff["source"]["commitSha"],
            "revisionName": handoff["application"]["revisionName"],
            "serviceName": handoff["observability"]["serviceName"],
            "query": panel["query"],
            "querySha256": panel["querySha256"],
            "windowStart": evidence["window"]["startTime"],
            "windowEnd": evidence["window"]["endTime"],
            "capturedAt": "2026-08-20T13:55:00Z",
            "rows": [row],
        }
    return observations


def _materialize_load_capture(
    repository_root: Path,
    evidence: dict[str, Any],
    handoff: dict[str, Any],
    observations: dict[str, dict[str, Any]],
) -> None:
    """Create raw Azure responses and their digest-bound capture manifest."""
    raw_directory = repository_root / "evidence/load/raw"
    run = observations[evidence["testRun"]["resultFile"]]
    scale = observations[evidence["scaleConfiguration"]["resultFile"]]
    replicas = observations[evidence["replicas"]["resultFile"]]
    database = observations[evidence["databaseSignal"]["resultFile"]]

    raw_documents = {
        "test-run.json": {
            "testRunId": run["testRunId"],
            "testId": run["testId"],
            "status": "DONE",
            "executionStartDateTime": run["startedAt"],
            "executionEndDateTime": run["completedAt"],
            "duration": run["durationSeconds"] * 1000,
            "virtualUsers": run["virtualUsers"],
            "testRunStatistics": {
                "Total": {
                    "sampleCount": run["totalRequests"],
                    "errorCount": run["failedRequests"],
                }
            },
        },
        "container-app.json": {
            "id": handoff["application"]["resourceId"],
            "type": "Microsoft.App/containerApps",
            "etag": scale["etag"],
            "properties": {
                "provisioningState": scale["provisioningState"],
                "latestReadyRevisionName": handoff["application"]["revisionName"],
                "template": {
                    "scale": {
                        "minReplicas": scale["minimumReplicas"],
                        "maxReplicas": scale["maximumReplicas"],
                        "rules": [
                            {
                                "name": scale["ruleName"],
                                "http": {
                                    "metadata": {
                                        "concurrentRequests": str(
                                            scale["concurrentRequests"]
                                        )
                                    }
                                },
                            }
                        ],
                    }
                },
            },
        },
    }

    def metric_response(
        observation: dict[str, Any],
        unit: str,
        revision_name: str | None = None,
    ) -> dict[str, Any]:
        """Build one representative Azure Monitor metric response."""
        metric = observation["metric"]
        aggregation = observation["aggregation"].casefold()
        metadata = (
            [
                {
                    "name": {
                        "value": "revisionName",
                        "localizedValue": "Revision Name",
                    },
                    "value": revision_name,
                }
            ]
            if revision_name is not None
            else []
        )
        return {
            "cost": 1,
            "timespan": (
                f"{observation['startTime']}/{observation['endTime']}"
            ),
            "interval": "PT1M",
            "value": [
                {
                    "id": (
                        f"{observation['resourceId']}/providers/"
                        f"Microsoft.Insights/metrics/{metric}"
                    ),
                    "type": "Microsoft.Insights/metrics",
                    "name": {
                        "value": metric,
                        "localizedValue": metric,
                    },
                    "unit": unit,
                    "timeseries": [
                        {
                            "metadatavalues": metadata,
                            "data": [
                                {
                                    "timeStamp": point["timestamp"],
                                    aggregation: point["value"],
                                }
                                for point in observation["points"]
                            ],
                        }
                    ],
                }
            ],
        }

    raw_documents["replicas.json"] = metric_response(
        replicas,
        "Count",
        handoff["application"]["revisionName"],
    )
    raw_documents["database.json"] = metric_response(
        database,
        "Count"
        if evidence["databaseSignal"]["unit"] == "count"
        else "Percent",
    )
    raw_hashes: dict[str, str] = {}
    for name, value in raw_documents.items():
        path = raw_directory / name
        _write_json(path, value)
        raw_hashes[name] = hashlib.sha256(path.read_bytes()).hexdigest()

    capture = {
        "schemaVersion": "1.0.0",
        "capturedAt": evidence["capturedAt"],
        "baselineStart": evidence["windows"]["baselineStart"],
        "testRun": {
            "file": "evidence/load/raw/test-run.json",
            "sha256": raw_hashes["test-run.json"],
            "resourceId": evidence["testRun"]["resourceId"],
        },
        "scaleConfiguration": {
            "file": "evidence/load/raw/container-app.json",
            "sha256": raw_hashes["container-app.json"],
            "observedAt": evidence["scaleConfiguration"]["observedAt"],
        },
        "replicas": {
            "file": "evidence/load/raw/replicas.json",
            "sha256": raw_hashes["replicas.json"],
            "resourceId": handoff["application"]["resourceId"],
            "metricName": "Replicas",
            "aggregation": "Maximum",
            "interval": "PT1M",
            "start": replicas["startTime"],
            "end": replicas["endTime"],
            "revisionName": handoff["application"]["revisionName"],
        },
        "databaseSignal": {
            "file": "evidence/load/raw/database.json",
            "sha256": raw_hashes["database.json"],
            "resourceId": handoff["database"]["resourceId"],
            "metricName": database["metric"],
            "aggregation": database["aggregation"],
            "interval": "PT1M",
            "start": database["startTime"],
            "end": database["endTime"],
        },
        "recovery": {
            "observedAt": evidence["windows"]["recoveryEnd"],
            "healthUrl": evidence["recovery"]["healthUrl"],
            "healthStatus": evidence["recovery"]["healthStatus"],
            "readinessUrl": evidence["recovery"]["readinessUrl"],
            "readinessStatus": evidence["recovery"]["readinessStatus"],
        },
        "artifacts": {
            "configurationFile": evidence["testRun"]["configurationFile"],
            "configurationSha256": evidence["testRun"][
                "configurationSha256"
            ],
            "jmeterFile": evidence["testRun"]["jmeterFile"],
            "jmeterSha256": evidence["testRun"]["jmeterSha256"],
        },
    }
    capture_path = repository_root / evidence["capture"]["manifestFile"]
    _write_json(capture_path, capture)
    evidence["capture"]["manifestSha256"] = hashlib.sha256(
        capture_path.read_bytes()
    ).hexdigest()


def _materialize_cicd_raw_captures(
    repository_root: Path,
    evidence: dict[str, Any],
    handoff: dict[str, Any],
    observations: dict[str, dict[str, Any]],
) -> None:
    """Create raw RBAC and revision-list responses for CI/CD validation."""
    identity = observations[evidence["identity"]["resultFile"]]
    enumeration = evidence["identity"]["roleAssignmentEnumeration"]
    role_path = repository_root / enumeration["rawResultFile"]
    role_rows = [
        {
            "id": assignment["resourceId"],
            "principalId": assignment["principalId"],
            "roleDefinitionId": (
                f"/subscriptions/{enumeration['subscriptionId']}/providers/"
                "Microsoft.Authorization/roleDefinitions/"
                f"{assignment['roleDefinitionId']}"
            ),
            "scope": assignment["scope"],
        }
        for assignment in identity["roleAssignments"]
    ]
    role_path.parent.mkdir(parents=True, exist_ok=True)
    role_path.write_text(
        json.dumps(role_rows, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    role_sha256 = hashlib.sha256(role_path.read_bytes()).hexdigest()
    enumeration["rawResultSha256"] = role_sha256
    identity["roleAssignmentEnumeration"]["rawResultSha256"] = role_sha256

    previous = evidence["revisions"]["previous"]
    candidate = evidence["revisions"]["candidate"]
    application_id = handoff["application"]["resourceId"]
    previous_image = (
        f"{handoff['containerImage']['registry']}/"
        f"{handoff['containerImage']['repository']}@"
        f"{handoff['containerImage']['digest']}"
    )
    candidate_image = evidence["image"]["reference"]
    for stage in ("before", "promotion", "rollback"):
        declaration = evidence["traffic"][stage]
        observation = observations[declaration["resultFile"]]
        raw_revisions = [
            {
                "id": f"{application_id}/revisions/{previous}",
                "name": previous,
                "properties": {
                    "active": observation["previousActive"],
                    "healthState": observation["previousHealthState"],
                    "trafficWeight": observation["previousWeight"],
                    "template": {
                        "containers": [{"image": previous_image}]
                    },
                },
            },
            {
                "id": f"{application_id}/revisions/{candidate}",
                "name": candidate,
                "properties": {
                    "active": observation["candidateActive"],
                    "healthState": observation["candidateHealthState"],
                    "trafficWeight": observation["candidateWeight"],
                    "template": {
                        "containers": [{"image": candidate_image}]
                    },
                },
            },
        ]
        raw_path = repository_root / declaration["rawResultFile"]
        raw_path.parent.mkdir(parents=True, exist_ok=True)
        raw_path.write_text(
            json.dumps(raw_revisions, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        declaration["rawResultSha256"] = hashlib.sha256(
            raw_path.read_bytes()
        ).hexdigest()


def _prepare_validator_bundle(
    kind: str,
    tmp_path: Path,
    repo_root: Path,
) -> tuple[Path, Path, dict[str, Any], dict[str, Any], dict[str, dict[str, Any]]]:
    """Create one complete repository-local evidence bundle for validator tests."""
    handoff = deepcopy(
        load_json(_contracts(repo_root) / "modernization-contract.example.json")
    )
    name = {
        "load": "load-test",
        "cicd": "cicd",
        "observability": "observability",
    }[kind]
    evidence = deepcopy(
        load_json(_contracts(repo_root) / f"{name}-evidence.example.json")
    )
    subject = evidence["subject"]
    subject["sliceId"] = handoff["sliceId"]
    subject["sourceCommit"] = handoff["source"]["commitSha"]
    subject["revisionName"] = handoff["application"]["revisionName"]
    subject["containerAppResourceId"] = handoff["application"]["resourceId"]

    if kind == "load":
        subject["stack"] = handoff["source"]["stack"]
        subject["databaseFamily"] = handoff["database"]["family"]
        subject["databaseResourceId"] = handoff["database"]["resourceId"]
        subject["imageDigest"] = handoff["containerImage"]["digest"]
        evidence["replicas"]["resourceId"] = handoff["application"]["resourceId"]
        evidence["scaleConfiguration"]["containerAppResourceId"] = handoff[
            "application"
        ]["resourceId"]
        evidence["scaleConfiguration"]["revisionName"] = handoff["application"][
            "revisionName"
        ]
        evidence["databaseSignal"]["resourceId"] = handoff["database"]["resourceId"]
        evidence["testRun"]["applicationUrl"] = handoff["application"]["url"]
        evidence["testRun"]["targetUrl"] = (
            f"{handoff['application']['url'].rstrip('/')}/perftest/catalog"
        )
        evidence["recovery"]["healthUrl"] = handoff["application"]["healthUrl"]
        evidence["recovery"]["readinessUrl"] = handoff["application"]["readinessUrl"]
    elif kind == "cicd":
        subject["stack"] = handoff["source"]["stack"]
        subject["imageDigest"] = handoff["containerImage"]["digest"]
        evidence["identity"]["acrScope"] = handoff["containerImage"][
            "registryResourceId"
        ]
        evidence["identity"]["containerAppScope"] = handoff["application"][
            "resourceId"
        ]
        evidence["image"]["repository"] = (
            f"{handoff['containerImage']['registry']}/"
            f"{handoff['containerImage']['repository']}"
        )
        evidence["image"]["reference"] = (
            f"{evidence['image']['repository']}@{evidence['image']['digest']}"
        )
        evidence["revisions"]["previous"] = handoff["application"]["revisionName"]
        candidate_url = shared_challenges._revision_label_url(
            handoff["application"]["url"],
            evidence["revisions"]["candidateLabel"],
        )
        evidence["revisions"]["candidateUrl"] = candidate_url
        evidence["smoke"]["candidateUrl"] = candidate_url
        evidence["smoke"]["healthUrl"] = f"{candidate_url}/healthz"
        evidence["smoke"]["readinessUrl"] = f"{candidate_url}/readyz"
    else:
        subject["serviceName"] = handoff["observability"]["serviceName"]
        evidence["telemetryReport"] = handoff["evidence"]["telemetryReport"]
        evidence["source"] = {
            "applicationInsightsResourceId": handoff["observability"][
                "applicationInsightsResourceId"
            ],
            "logAnalyticsWorkspaceResourceId": handoff["observability"][
                "logAnalyticsWorkspaceResourceId"
            ],
            "serviceName": handoff["observability"]["serviceName"],
            "serviceNamespace": handoff["observability"]["serviceNamespace"],
            "environment": handoff["observability"]["environment"],
            "directAzureMonitorExporter": True,
        }
        evidence["metricsExport"]["containerAppResourceId"] = handoff["application"][
            "resourceId"
        ]
        evidence["metricsExport"]["workspaceResourceId"] = handoff["observability"][
            "logAnalyticsWorkspaceResourceId"
        ]
        evidence["workbook"]["sourceId"] = handoff["observability"][
            "logAnalyticsWorkspaceResourceId"
        ]
        rendered_queries = shared_challenges.render_observability_queries(
            evidence,
            handoff,
            _contracts(repo_root),
        )
        for panel in evidence["panels"]:
            panel.update(rendered_queries[panel["id"]])

    repository_root = tmp_path / "repository"
    evidence_path = repository_root / "evidence" / f"{name}-report.json"
    handoff_path = repository_root / "evidence/modernization-contract.json"
    _write_declared_files(evidence, repository_root)
    _write_json(handoff_path, handoff)
    if kind == "cicd":
        evidence["workflow"]["headSha"] = _commit_control_handoff(
            repository_root,
            handoff_path,
        )
        evidence["workflow"]["handoffSha256"] = hashlib.sha256(
            handoff_path.read_bytes()
        ).hexdigest()
    if kind == "observability":
        query_contract = load_json(
            _contracts(repo_root) / "observability-queries.json"
        )
        _write_json(
            repository_root / evidence["workbook"]["templateFile"],
            {
                "version": "Notebook/1.0",
                "items": [
                    {
                        "type": 3,
                        "name": declaration["id"],
                        "content": {
                            "version": "KqlItem/1.0",
                            "queryType": 0,
                            "resourceType": (
                                "microsoft.operationalinsights/workspaces"
                            ),
                            "query": declaration["template"],
                        },
                    }
                    for declaration in query_contract["queries"]
                ],
            },
        )
        (
            repository_root / evidence["workbook"]["queriesFile"]
        ).write_text(
            shared_challenges.render_observability_query_source(
                _contracts(repo_root)
            ),
            encoding="utf-8",
        )
    if kind == "load":
        for file_key, digest_key in (
            ("configurationFile", "configurationSha256"),
            ("jmeterFile", "jmeterSha256"),
        ):
            evidence["testRun"][digest_key] = hashlib.sha256(
                (repository_root / evidence["testRun"][file_key]).read_bytes()
            ).hexdigest()
    elif kind == "observability":
        for file_key, digest_key in (
            ("templateFile", "templateSha256"),
            ("queriesFile", "queriesSha256"),
        ):
            evidence["workbook"][digest_key] = hashlib.sha256(
                (repository_root / evidence["workbook"][file_key]).read_bytes()
            ).hexdigest()
        evidence["workbook"]["serializedDataSha256"] = hashlib.sha256(
            _serialized_workbook(evidence).encode("utf-8")
        ).hexdigest()
    observations = _normalized_observations(kind, evidence, handoff)
    if kind == "load":
        _materialize_load_capture(
            repository_root,
            evidence,
            handoff,
            observations,
        )
    elif kind == "cicd":
        _materialize_cicd_raw_captures(
            repository_root,
            evidence,
            handoff,
            observations,
        )
    for path, observation in observations.items():
        _write_json(repository_root / path, observation)
    _write_json(evidence_path, evidence)
    return repository_root, evidence_path, evidence, handoff, observations


def test_p6_registry_and_examples_match_frozen_schemas(repo_root: Path) -> None:
    """The P6 registry and all three evidence examples remain executable."""
    contracts = _contracts(repo_root)
    registry = load_json(contracts / "shared-challenges.json")
    assert registry["schemaVersion"] == "1.2.0"
    _validate(load_json(contracts / "shared-challenges.schema.json"), registry)
    query_contract = load_json(contracts / "observability-queries.json")
    assert query_contract["schemaVersion"] == "1.1.0"
    _validate(
        load_json(contracts / "observability-queries.schema.json"),
        query_contract,
    )

    for name in ("load-test", "cicd", "observability"):
        example = load_json(contracts / f"{name}-evidence.example.json")
        expected_version = "1.1.0"
        assert example["schemaVersion"] == expected_version
        _validate(
            load_json(contracts / f"{name}-evidence.schema.json"),
            example,
        )
    capture_example = load_json(
        contracts / "load-evidence-capture.example.json"
    )
    _validate(
        load_json(contracts / "load-evidence-capture.schema.json"),
        capture_example,
    )


def test_p6_cicd_raw_fixtures_preserve_azure_response_shapes(
    repo_root: Path,
) -> None:
    """Sanitized raw fixtures retain RBAC and revision transition fields."""
    fixtures = _contracts(repo_root) / "fixtures/cicd"
    assignments = json.loads(
        (fixtures / "role-assignments.json").read_text(encoding="utf-8")
    )
    assert {
        (assignment["roleDefinitionId"], assignment["scope"])
        for assignment in assignments
    } == {
        (
            (
                "/subscriptions/00000000-0000-0000-0000-000000000000/"
                "providers/Microsoft.Authorization/roleDefinitions/"
                "8311e382-0749-4cb8-b61a-304f252e45ec"
            ),
            (
                "/subscriptions/00000000-0000-0000-0000-000000000000/"
                "resourceGroups/rg-mh-example/providers/"
                "Microsoft.ContainerRegistry/registries/acrexample"
            ),
        ),
        (
            (
                "/subscriptions/00000000-0000-0000-0000-000000000000/"
                "providers/Microsoft.Authorization/roleDefinitions/"
                "358470bc-b998-42bd-ab17-a7e34c199c0f"
            ),
            (
                "/subscriptions/00000000-0000-0000-0000-000000000000/"
                "resourceGroups/rg-mh-example/providers/"
                "Microsoft.App/containerApps/ca-mh-example"
            ),
        ),
    }
    expected_weights = {
        "before-revisions.json": (100, 0),
        "promotion-revisions.json": (0, 100),
        "rollback-revisions.json": (100, 0),
    }
    for name, weights in expected_weights.items():
        revisions = json.loads(
            (fixtures / name).read_text(encoding="utf-8")
        )
        assert tuple(
            revision["properties"]["trafficWeight"]
            for revision in revisions
        ) == weights
        assert all(
            revision["properties"]["active"]
            and revision["properties"]["healthState"] == "Healthy"
            and revision["properties"]["template"]["containers"][0]["image"]
            .startswith("acrexample.azurecr.io/")
            for revision in revisions
        )


def test_p6_registry_freezes_disjoint_artifact_ownership(repo_root: Path) -> None:
    """Load, CI/CD, and observability own exact nonoverlapping file sets."""
    registry = load_json(_contracts(repo_root) / "shared-challenges.json")
    challenges = registry["challenges"]
    assert [item["id"] for item in challenges] == [
        "load-autoscaling",
        "cicd-revisions",
        "observability",
    ]
    assert [item["number"] for item in challenges] == [2, 3, 4]

    expected = {
        "load-autoscaling": {
            "id": "load-autoscaling",
            "number": 2,
            "challenge": "challenges/ch02/README.md",
            "solution": "solutions/ch02/README.md",
            "artifacts": [
                "tests/load/catalog-load.jmx",
                "tests/load/load-test.yaml",
                "tests/acceptance/tests/test_p6_load_challenge.py",
            ],
            "captureSchema": "workshop/contracts/load-evidence-capture.schema.json",
            "captureExample": "workshop/contracts/load-evidence-capture.example.json",
            "evidenceSchema": "workshop/contracts/load-test-evidence.schema.json",
            "evidenceExample": "workshop/contracts/load-test-evidence.example.json",
            "evidenceOutput": "evidence/load-test-report.json",
            "evidenceRenderCommand": (
                "uv --no-config run catalog-render-load-evidence --capture "
                "../../evidence/load/capture.json --handoff "
                "../../evidence/modernization-contract.json --output "
                "../../evidence/load-test-report.json --repository-root ../.."
            ),
            "evidenceValidationCommand": (
                "uv --no-config run catalog-validate-challenge-evidence load "
                "../../evidence/load-test-report.json --handoff "
                "../../evidence/modernization-contract.json --contracts "
                "../../workshop/contracts --repository-root ../.."
            ),
            "validationCommand": (
                "uv --no-config run pytest -q tests/test_p6_load_challenge.py"
            ),
        },
        "cicd-revisions": {
            "id": "cicd-revisions",
            "number": 3,
            "challenge": "challenges/ch03/README.md",
            "solution": "solutions/ch03/README.md",
            "artifacts": [
                ".github/workflows/catalog-dotnet.yml",
                ".github/workflows/catalog-java.yml",
                "infra/github-cicd.bicep",
                "tests/acceptance/tests/test_p6_cicd_challenge.py",
            ],
            "evidenceSchema": "workshop/contracts/cicd-evidence.schema.json",
            "evidenceExample": "workshop/contracts/cicd-evidence.example.json",
            "evidenceOutput": "evidence/cicd-report.json",
            "evidenceValidationCommand": (
                "uv --no-config run catalog-validate-challenge-evidence cicd "
                "../../evidence/cicd-report.json --handoff "
                "../../evidence/modernization-contract.json --contracts "
                "../../workshop/contracts --repository-root ../.."
            ),
            "validationCommand": (
                "uv --no-config run pytest -q tests/test_p6_cicd_challenge.py"
            ),
        },
        "observability": {
            "id": "observability",
            "number": 4,
            "challenge": "challenges/ch04/README.md",
            "solution": "solutions/ch04/README.md",
            "artifacts": [
                "workshop/observability/queries.kql",
                "workshop/observability/workbook.json",
                "infra/observability-workbook.bicep",
                "tests/acceptance/tests/test_p6_observability_challenge.py",
            ],
            "evidenceSchema": "workshop/contracts/observability-evidence.schema.json",
            "evidenceExample": "workshop/contracts/observability-evidence.example.json",
            "evidenceOutput": "evidence/observability-report.json",
            "evidenceValidationCommand": (
                "uv --no-config run catalog-validate-challenge-evidence observability "
                "../../evidence/observability-report.json --handoff "
                "../../evidence/modernization-contract.json --contracts "
                "../../workshop/contracts --repository-root ../.."
            ),
            "validationCommand": (
                "uv --no-config run pytest -q tests/test_p6_observability_challenge.py"
            ),
        },
    }
    coordinator_owned = set(registry["coordinatorOwnedFiles"])
    assert coordinator_owned == {
        "docs/CommonErrors.md",
        "docs/ImplementationLog.md",
        "workshop/contracts/README.md",
        "workshop/contracts/shared-challenges.json",
        "workshop/contracts/shared-challenges.schema.json",
        "workshop/contracts/load-evidence-capture.schema.json",
        "workshop/contracts/load-evidence-capture.example.json",
        "workshop/contracts/load-test-evidence.schema.json",
        "workshop/contracts/load-test-evidence.example.json",
        "workshop/contracts/fixtures/cicd/before-revisions.json",
        "workshop/contracts/fixtures/cicd/promotion-revisions.json",
        "workshop/contracts/fixtures/cicd/role-assignments.json",
        "workshop/contracts/fixtures/cicd/rollback-revisions.json",
        "workshop/contracts/fixtures/load/azure-sql.json",
        "workshop/contracts/fixtures/load/container-app.json",
        "workshop/contracts/fixtures/load/postgresql.json",
        "workshop/contracts/fixtures/load/replicas.json",
        "workshop/contracts/fixtures/load/test-run.json",
        "workshop/contracts/cicd-evidence.schema.json",
        "workshop/contracts/cicd-evidence.example.json",
        "workshop/contracts/observability-evidence.schema.json",
        "workshop/contracts/observability-evidence.example.json",
        "workshop/contracts/observability-queries.schema.json",
        "workshop/contracts/observability-queries.json",
        "tests/acceptance/pyproject.toml",
        "tests/acceptance/catalog_acceptance/models/__init__.py",
        "tests/acceptance/catalog_acceptance/models/shared_challenges.py",
        "tests/acceptance/catalog_acceptance/load_evidence.py",
        "tests/acceptance/catalog_acceptance/load_evidence_cli.py",
        "tests/acceptance/catalog_acceptance/shared_challenges.py",
        "tests/acceptance/catalog_acceptance/shared_challenges_cli.py",
        "tests/acceptance/tests/test_p6_contracts.py",
        "tests/acceptance/tests/test_p6_load_renderer.py",
    }
    assert all((repo_root / path).is_file() for path in coordinator_owned)
    owned: set[str] = set()
    for challenge in challenges:
        contract = expected[challenge["id"]]
        assert challenge == contract
        for path in (
            challenge["challenge"],
            challenge["solution"],
            *challenge["artifacts"],
            challenge["evidenceSchema"],
            challenge["evidenceExample"],
            challenge["evidenceOutput"],
            *(
                [
                    challenge["captureSchema"],
                    challenge["captureExample"],
                ]
                if challenge["id"] == "load-autoscaling"
                else []
            ),
        ):
            pure_path = PurePosixPath(path)
            assert not pure_path.is_absolute()
            assert ".." not in pure_path.parts
        files = {
            challenge["challenge"],
            challenge["solution"],
            *challenge["artifacts"],
        }
        assert owned.isdisjoint(files)
        assert coordinator_owned.isdisjoint(files)
        owned.update(files)


def test_p6_registry_schema_rejects_cross_wired_stream_contracts(
    repo_root: Path,
) -> None:
    """A challenge cannot consume another stream's schema or validation command."""
    contracts = _contracts(repo_root)
    schema = load_json(contracts / "shared-challenges.schema.json")
    registry = deepcopy(load_json(contracts / "shared-challenges.json"))
    cicd = next(
        challenge
        for challenge in registry["challenges"]
        if challenge["id"] == "cicd-revisions"
    )
    cicd["evidenceSchema"] = "workshop/contracts/observability-evidence.schema.json"

    with pytest.raises(JsonSchemaValidationError):
        _validate(schema, registry)


def test_p6_cicd_schema_rejects_invalid_all_plus_scope_enumeration(
    repo_root: Path,
) -> None:
    """The Azure CLI `--all` audit cannot also declare a rejected scope."""
    contracts = _contracts(repo_root)
    schema = load_json(contracts / "cicd-evidence.schema.json")
    evidence = deepcopy(load_json(contracts / "cicd-evidence.example.json"))
    enumeration = evidence["identity"]["roleAssignmentEnumeration"]
    enumeration["scope"] = (
        "/subscriptions/00000000-0000-0000-0000-000000000000"
    )
    enumeration["command"] = enumeration["command"].replace(
        " --output json",
        f" --scope {enumeration['scope']} --output json",
    )

    with pytest.raises(JsonSchemaValidationError):
        _validate(schema, evidence)


def test_p6_identity_metrics_and_panels_are_exact(repo_root: Path) -> None:
    """Freeze OIDC role scope, dual database signals, and workbook panels."""
    registry = load_json(_contracts(repo_root) / "shared-challenges.json")
    assert registry["consumes"] == {
        "handoffSchemaVersion": "1.4.0",
        "handoffFile": "evidence/modernization-contract.json",
        "stacks": ["dotnet-sqlserver", "java-postgresql"],
        "databaseFamilies": ["azure-sql", "postgresql-flexible"],
    }
    assert registry["cicdIdentity"] == {
        "authentication": "github-oidc",
        "repositoryPermission": {"contents": "read", "id-token": "write"},
        "roles": [
            {
                "name": "AcrPush",
                "roleDefinitionId": "8311e382-0749-4cb8-b61a-304f252e45ec",
                "scope": "registry",
            },
            {
                "name": "Container Apps Contributor",
                "roleDefinitionId": "358470bc-b998-42bd-ab17-a7e34c199c0f",
                "scope": "container-app",
            },
        ],
        "federatedSubjects": [
            "repo:<owner>/<repository>:environment:staging",
            "repo:<owner>/<repository>:environment:production",
        ],
        "forbidden": [
            "client-secret",
            "registry-admin",
            "resource-group-contributor",
            "subscription-contributor",
        ],
    }
    assert registry["cicdProtocol"] == {
        "evidenceVersion": "1.1.0",
        "trigger": "workflow_dispatch",
        "workflowHead": "control-commit",
        "handoffCheckout": "workflow-head",
        "applicationCheckout": "handoff-source-commit",
        "sourceIdentity": "handoff.source.commitSha",
        "roleAudit": {
            "executionBoundary": "facilitator-session",
            "requiredPermission": "Microsoft.Authorization/roleAssignments/read",
            "minimumBuiltInRole": "Reader",
            "command": (
                "az role assignment list --all --include-inherited "
                "--assignee-object-id <principal-id> "
                "--fill-principal-name false "
                "--fill-role-definition-name false --output json"
            ),
        },
        "approvalOrdering": [
            "staging-complete",
            "production-approved",
            "production-started",
            "promotion",
            "rollback",
        ],
        "revisionStateSource": "azure-container-app-revision-list",
        "rollbackGuard": "shell-trap",
    }
    assert registry["loadSignals"] == {
        "testRun": {
            "resourceType": "Microsoft.LoadTestService/loadTests"
        },
        "replicas": {
            "resourceType": "Microsoft.App/containerApps",
            "metric": "Replicas",
            "minimum": 1,
            "scaleOutMinimum": 2,
            "maximum": 3,
            "scaleRule": {
                "name": "http",
                "type": "http",
                "concurrentRequests": 50,
            },
        },
        "azure-sql": {
            "resourceType": "Microsoft.Sql/servers/databases",
            "metric": "app_cpu_billed",
            "aggregation": "Total",
        },
        "postgresql-flexible": {
            "resourceType": "Microsoft.DBforPostgreSQL/flexibleServers",
            "metric": "cpu_percent",
            "aggregation": "Maximum",
        },
    }
    assert registry["loadEvidenceProtocol"] == {
        "captureManifestVersion": "1.0.0",
        "evidenceVersion": "1.1.0",
        "renderer": "catalog-render-load-evidence",
        "evidenceOutput": "evidence/load-test-report.json",
        "testRun": {
            "status": "DONE",
            "virtualUsers": 40,
            "durationSeconds": 300,
            "maximumErrors": 0,
        },
        "replicas": {
            "aggregation": "Maximum",
            "interval": "PT1M",
            "dimension": "revisionName",
            "requiredPhases": [
                "baseline-one-before-load",
                "scale-out-during-load",
                "recovery-one-after-load",
            ],
        },
    }
    assert registry["observabilityPanels"] == [
        "error-rate",
        "latency",
        "database-dependency-failures",
        "replica-count",
        "cold-starts",
    ]
    assert registry["observabilityMetrics"] == {
        "source": "container-app-diagnostic-setting",
        "category": "AllMetrics",
        "destination": "handoff-log-analytics-workspace",
        "destinationTable": "AzureMetrics",
        "deploymentScope": "handoff-container-app-resource-group",
        "scope": "container-app-total",
        "dimensionHandling": "flattened",
        "aggregation": "Total",
        "timeGrain": "PT1M",
        "windowReduction": "peak",
        "requiredMetric": "Replicas",
    }


def test_p6_observability_templates_bind_exact_query_inputs(repo_root: Path) -> None:
    """Every frozen KQL template requires its authoritative identity parameters."""
    contract = load_json(_contracts(repo_root) / "observability-queries.json")
    queries = {item["id"]: item["template"] for item in contract["queries"]}
    common = {
        "__START_TIME__",
        "__END_TIME__",
        "__APPLICATION_INSIGHTS_RESOURCE_ID__",
        "__SERVICE_NAME__",
        "__SOURCE_COMMIT__",
        "__REVISION_NAME__",
    }
    for query_id in (
        "error-rate",
        "latency",
        "database-dependency-failures",
        "cold-starts",
    ):
        assert all(parameter in queries[query_id] for parameter in common)
        assert "AppVersion" in queries[query_id]
        assert 'Properties["service.version"]' not in queries[query_id]
    replica = queries["replica-count"]
    assert all(
        parameter in replica
        for parameter in (
            "__START_TIME__",
            "__END_TIME__",
            "__CONTAINER_APP_RESOURCE_ID__",
        )
    )
    assert "__REVISION_NAME__" not in replica
    assert "AzureMetrics |" in replica
    assert "AzureMetricsV2" not in replica
    assert "Dimension" not in replica
    assert 'MetricName == "Replicas" and TimeGrain == "PT1M"' in replica
    assert "toint(max(Total))" in replica
    assert "Maximum" not in replica
    cold_starts = queries["cold-starts"]
    assert "where TimeGenerated <= endTime" in cold_starts
    assert cold_starts.index("summarize firstRequest=min(TimeGenerated)") < (
        cold_starts.index("where firstRequest between (startTime .. endTime)")
    )


def test_p6_examples_bind_current_subjects_and_results(repo_root: Path) -> None:
    """Examples cannot self-attest without matching source, image, and revision data."""
    contracts = _contracts(repo_root)
    load = load_json(contracts / "load-test-evidence.example.json")
    assert load["subject"]["databaseFamily"] == load["databaseSignal"]["family"]
    assert load["databaseSignal"]["peak"] > load["databaseSignal"]["baseline"]
    assert (
        load["replicas"]["baselineObserved"]
        < load["replicas"]["peakObserved"]
        <= load["replicas"]["maximumConfigured"]
    )
    assert load["scaleConfiguration"] == {
        "source": "azure-resource-manager",
        "containerAppResourceId": load["subject"]["containerAppResourceId"],
        "revisionName": load["subject"]["revisionName"],
        "minimumReplicas": 1,
        "maximumReplicas": 3,
        "ruleName": "http",
        "ruleType": "http",
        "concurrentRequests": 50,
        "observedAt": "2026-08-20T11:49:00Z",
        "resultFile": "evidence/load/scale-configuration.json",
    }

    cicd = load_json(contracts / "cicd-evidence.example.json")
    assert cicd["subject"]["sourceCommit"] == cicd["image"]["sourceCommit"]
    assert cicd["image"]["sourceCommit"] == cicd["image"]["tag"]
    assert cicd["image"]["reference"].endswith(f"@{cicd['image']['digest']}")
    assert cicd["subject"]["containerAppResourceId"] == cicd["identity"][
        "containerAppScope"
    ]
    assert cicd["revisions"]["previous"] != cicd["revisions"]["candidate"]
    assert cicd["smoke"]["candidateUrl"] == cicd["revisions"]["candidateUrl"]
    assert cicd["smoke"]["healthUrl"] == f"{cicd['revisions']['candidateUrl']}/healthz"
    assert cicd["smoke"]["readinessUrl"] == (
        f"{cicd['revisions']['candidateUrl']}/readyz"
    )
    assert cicd["identity"]["stagingFederatedSubject"].endswith(
        ":environment:staging"
    )
    assert cicd["identity"]["productionFederatedSubject"].endswith(
        ":environment:production"
    )
    assert cicd["workflow"]["resultFile"] == "evidence/cicd/workflow-run.json"
    assert cicd["workflow"]["headSha"] != cicd["subject"]["sourceCommit"]
    assert cicd["workflow"]["event"] == "workflow_dispatch"
    assert (
        cicd["approval"]["approvedAt"]
        <= cicd["workflow"]["jobs"]["production"]["startedAt"]
    )
    enumeration = cicd["identity"]["roleAssignmentEnumeration"]
    assert "scope" not in enumeration
    assert enumeration["executionBoundary"] == "facilitator-session"
    assert enumeration["minimumBuiltInRole"] == "Reader"
    assert "--all --include-inherited" in enumeration["command"]
    assert "--scope" not in enumeration["command"]
    assert all(
        transition["source"] == "azure-container-app-revision-list"
        and transition["rawResultFile"].endswith(".raw.json")
        for transition in (
            cicd["traffic"]["before"],
            cicd["traffic"]["promotion"],
            cicd["traffic"]["rollback"],
        )
    )
    assert cicd["traffic"]["safety"]["mechanism"] == "shell-trap"
    assert (
        cicd["traffic"]["safety"]["guardInstalledAt"]
        <= cicd["traffic"]["safety"]["promotionAttemptedAt"]
    )

    observability = load_json(contracts / "observability-evidence.example.json")
    assert observability["metricsExport"] == {
        "containerAppResourceId": observability["subject"]["containerAppResourceId"],
        "workspaceResourceId": observability["source"][
            "logAnalyticsWorkspaceResourceId"
        ],
        "diagnosticSettingName": "all-metrics-to-workspace",
        "metricCategory": "AllMetrics",
        "destinationTable": "AzureMetrics",
        "scope": "container-app-total",
        "dimensionHandling": "flattened",
        "deployedAt": "2026-08-20T13:40:00Z",
        "resultFile": "evidence/observability/metrics-export.json",
    }
    assert [panel["id"] for panel in observability["panels"]] == [
        "error-rate",
        "latency",
        "database-dependency-failures",
        "replica-count",
        "cold-starts",
    ]
    revision = observability["subject"]["revisionName"]
    revision_scoped_panels = [
        panel for panel in observability["panels"] if panel["id"] != "replica-count"
    ]
    replica_panel = next(
        panel
        for panel in observability["panels"]
        if panel["id"] == "replica-count"
    )
    assert all(revision in panel["query"] for panel in revision_scoped_panels)
    assert revision not in replica_panel["query"]
    assert replica_panel["resultKind"] == "container-app-peak-replica-count"
    assert all(
        hashlib.sha256(panel["query"].encode("utf-8")).hexdigest()
        == panel["querySha256"]
        for panel in observability["panels"]
    )
    cold_start_query = next(
        panel["query"]
        for panel in observability["panels"]
        if panel["id"] == "cold-starts"
    )
    assert "AppRoleInstance" in cold_start_query
    assert "cloud_RoleInstance" not in cold_start_query
    assert observability["source"]["logAnalyticsWorkspaceResourceId"] == observability[
        "workbook"
    ]["sourceId"]
    assert set(observability["workbook"]) >= {
        "templateSha256",
        "queriesSha256",
        "serializedDataSha256",
    }


@pytest.mark.parametrize(
    ("schema_name", "example_name", "mutation"),
    [
        (
            "load-test-evidence.schema.json",
            "load-test-evidence.example.json",
            ("databaseSignal", "metric", "cpu_percent"),
        ),
        (
            "cicd-evidence.schema.json",
            "cicd-evidence.example.json",
            ("identity", "clientSecretUsed", True),
        ),
        (
            "observability-evidence.schema.json",
            "observability-evidence.example.json",
            ("panels", None, None),
        ),
    ],
)
def test_p6_schemas_reject_false_success(
    repo_root: Path,
    schema_name: str,
    example_name: str,
    mutation: tuple[str, str | None, object],
) -> None:
    """Wrong database metrics, credentials, or missing panels fail validation."""
    contracts = _contracts(repo_root)
    schema = load_json(contracts / schema_name)
    instance = deepcopy(load_json(contracts / example_name))
    parent, field, value = mutation
    if field is None:
        instance[parent].pop()
    else:
        instance[parent][field] = value

    with pytest.raises(JsonSchemaValidationError):
        _validate(schema, instance)


@pytest.mark.parametrize("kind", ["load", "cicd", "observability"])
def test_p6_validator_accepts_complete_handoff_bound_evidence(
    kind: str,
    tmp_path: Path,
    repo_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Every P6 producer can satisfy the common executable validator."""
    root, evidence_path, evidence, handoff, _ = _prepare_validator_bundle(
        kind, tmp_path, repo_root
    )
    monkeypatch.setattr(
        shared_challenges,
        "validate_handoff",
        lambda *_: handoff,
    )

    assert (
        shared_challenges.validate_shared_challenge_evidence(
            kind,
            evidence_path,
            root / "evidence/modernization-contract.json",
            _contracts(repo_root),
            root,
        )
        == evidence
    )


def test_p6_load_contract_consumes_authoritative_p4_scale_rule(
    repo_root: Path,
) -> None:
    """P6 must observe the existing P4 scale rule without replacing its revision."""
    registry = load_json(_contracts(repo_root) / "shared-challenges.json")
    load_example = load_json(_contracts(repo_root) / "load-test-evidence.example.json")
    p4_environment = (repo_root / "infra/modules/environment.bicep").read_text(
        encoding="utf-8"
    )

    assert registry["loadSignals"]["replicas"]["scaleRule"] == {
        "name": "http",
        "type": "http",
        "concurrentRequests": 50,
    }
    assert load_example["scaleConfiguration"]["ruleName"] == "http"
    assert "name: 'http'" in p4_environment
    assert "concurrentRequests: '50'" in p4_environment
    assert "minReplicas: 1" in p4_environment
    assert "maxReplicas: 3" in p4_environment


def test_p6_load_validator_rejects_self_attested_scale_out(
    tmp_path: Path,
    repo_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A true scaledOut flag cannot replace measured replica growth."""
    root, evidence_path, _, handoff, observations = _prepare_validator_bundle(
        "load", tmp_path, repo_root
    )
    replica_path = "evidence/load/replicas.json"
    observations[replica_path]["points"] = [
        {"timestamp": "2026-08-20T11:59:00Z", "value": 1},
        {"timestamp": "2026-08-20T12:03:00Z", "value": 1},
        {"timestamp": "2026-08-20T12:10:00Z", "value": 1},
    ]
    _write_json(root / replica_path, observations[replica_path])
    monkeypatch.setattr(shared_challenges, "validate_handoff", lambda *_: handoff)

    with pytest.raises(ValueError, match="replica peak differs"):
        shared_challenges.validate_shared_challenge_evidence(
            "load",
            evidence_path,
            root / "evidence/modernization-contract.json",
            _contracts(repo_root),
            root,
        )


def test_p6_load_validator_rejects_unobserved_scale_configuration(
    tmp_path: Path,
    repo_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Sampled replica values cannot replace the actual ARM scale configuration."""
    root, evidence_path, evidence, handoff, observations = _prepare_validator_bundle(
        "load", tmp_path, repo_root
    )
    scale_path = evidence["scaleConfiguration"]["resultFile"]
    observations[scale_path]["maximumReplicas"] = 100
    _write_json(root / scale_path, observations[scale_path])
    monkeypatch.setattr(shared_challenges, "validate_handoff", lambda *_: handoff)

    with pytest.raises(ValueError, match="maximumReplicas|less than or equal to 3"):
        shared_challenges.validate_shared_challenge_evidence(
            "load",
            evidence_path,
            root / "evidence/modernization-contract.json",
            _contracts(repo_root),
            root,
        )


def test_p6_load_validator_rejects_boolean_scale_values(
    tmp_path: Path,
    repo_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """JSON true cannot satisfy the strict minimum-replica observation."""
    root, evidence_path, evidence, handoff, observations = _prepare_validator_bundle(
        "load", tmp_path, repo_root
    )
    scale_path = evidence["scaleConfiguration"]["resultFile"]
    observations[scale_path]["minimumReplicas"] = True
    _write_json(root / scale_path, observations[scale_path])
    monkeypatch.setattr(shared_challenges, "validate_handoff", lambda *_: handoff)

    with pytest.raises(ValueError, match="minimumReplicas"):
        shared_challenges.validate_shared_challenge_evidence(
            "load",
            evidence_path,
            root / "evidence/modernization-contract.json",
            _contracts(repo_root),
            root,
        )


def test_p6_load_validator_rejects_duration_timestamp_drift(
    tmp_path: Path,
    repo_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A declared duration must equal the observed run interval."""
    root, evidence_path, evidence, handoff, observations = _prepare_validator_bundle(
        "load", tmp_path, repo_root
    )
    run_path = evidence["testRun"]["resultFile"]
    evidence["testRun"]["durationSeconds"] = 301
    observations[run_path]["durationSeconds"] = 301
    _write_json(root / run_path, observations[run_path])
    _write_json(evidence_path, evidence)
    monkeypatch.setattr(shared_challenges, "validate_handoff", lambda *_: handoff)

    with pytest.raises(ValueError, match="duration differs from the observed run"):
        shared_challenges.validate_shared_challenge_evidence(
            "load",
            evidence_path,
            root / "evidence/modernization-contract.json",
            _contracts(repo_root),
            root,
        )


@pytest.mark.parametrize(
    "nonfinite_value",
    [float("nan"), float("inf"), float("-inf")],
)
def test_p6_load_validator_rejects_nonfinite_metric_points(
    nonfinite_value: float,
    tmp_path: Path,
    repo_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Non-standard JSON numbers cannot satisfy Azure Monitor metric evidence."""
    root, evidence_path, evidence, handoff, observations = _prepare_validator_bundle(
        "load", tmp_path, repo_root
    )
    replicas_path = evidence["replicas"]["resultFile"]
    observations[replicas_path]["points"][0]["value"] = nonfinite_value
    _write_json(root / replicas_path, observations[replicas_path])
    monkeypatch.setattr(shared_challenges, "validate_handoff", lambda *_: handoff)

    with pytest.raises(ValueError, match="non-finite JSON constant is forbidden"):
        shared_challenges.validate_shared_challenge_evidence(
            "load",
            evidence_path,
            root / "evidence/modernization-contract.json",
            _contracts(repo_root),
            root,
        )


def test_p6_load_validator_rejects_unrelated_handoff_resources(
    tmp_path: Path,
    repo_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Schema-valid load evidence for another application must fail."""
    root, evidence_path, evidence, handoff, _ = _prepare_validator_bundle(
        "load", tmp_path, repo_root
    )
    evidence["subject"]["containerAppResourceId"] = evidence["subject"][
        "containerAppResourceId"
    ].replace("ca-mh-example", "ca-other")
    _write_json(evidence_path, evidence)
    monkeypatch.setattr(shared_challenges, "validate_handoff", lambda *_: handoff)

    with pytest.raises(ValueError, match="Container App resource differs"):
        shared_challenges.validate_shared_challenge_evidence(
            "load",
            evidence_path,
            root / "evidence/modernization-contract.json",
            _contracts(repo_root),
            root,
        )


def test_p6_load_validator_rejects_unrelated_successful_run(
    tmp_path: Path,
    repo_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A successful run from another Load Testing resource cannot validate."""
    root, evidence_path, evidence, handoff, observations = _prepare_validator_bundle(
        "load", tmp_path, repo_root
    )
    run_path = evidence["testRun"]["resultFile"]
    observations[run_path]["resourceId"] = observations[run_path][
        "resourceId"
    ].replace("lt-mh-example", "lt-other")
    _write_json(root / run_path, observations[run_path])
    monkeypatch.setattr(shared_challenges, "validate_handoff", lambda *_: handoff)

    with pytest.raises(ValueError, match="load-test resource ID differs"):
        shared_challenges.validate_shared_challenge_evidence(
            "load",
            evidence_path,
            root / "evidence/modernization-contract.json",
            _contracts(repo_root),
            root,
        )


def test_p6_load_validator_rejects_non_load_testing_resource_types(
    tmp_path: Path,
    repo_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Matching declarations cannot relabel another Azure resource as a load test."""
    root, evidence_path, evidence, handoff, observations = _prepare_validator_bundle(
        "load", tmp_path, repo_root
    )
    run_path = evidence["testRun"]["resultFile"]
    arbitrary_resource = handoff["application"]["resourceId"]
    evidence["testRun"]["resourceId"] = arbitrary_resource
    observations[run_path]["resourceId"] = arbitrary_resource
    _write_json(root / run_path, observations[run_path])
    _write_json(evidence_path, evidence)
    monkeypatch.setattr(shared_challenges, "validate_handoff", lambda *_: handoff)

    with pytest.raises(JsonSchemaValidationError, match="does not match"):
        shared_challenges.validate_shared_challenge_evidence(
            "load",
            evidence_path,
            root / "evidence/modernization-contract.json",
            _contracts(repo_root),
            root,
        )


def test_p6_load_validator_rejects_changed_test_artifacts(
    tmp_path: Path,
    repo_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Recorded digests must match the exact checked-in load artifacts."""
    root, evidence_path, evidence, handoff, _ = _prepare_validator_bundle(
        "load", tmp_path, repo_root
    )
    (root / evidence["testRun"]["jmeterFile"]).write_text(
        "changed\n", encoding="utf-8"
    )
    monkeypatch.setattr(shared_challenges, "validate_handoff", lambda *_: handoff)

    with pytest.raises(ValueError, match="declared JMeter digest differs"):
        shared_challenges.validate_shared_challenge_evidence(
            "load",
            evidence_path,
            root / "evidence/modernization-contract.json",
            _contracts(repo_root),
            root,
        )


def test_p6_load_validator_recomputes_normalized_raw_capture(
    tmp_path: Path,
    repo_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Digest-valid raw changes must be reflected in normalized observations."""
    root, evidence_path, evidence, handoff, _ = _prepare_validator_bundle(
        "load", tmp_path, repo_root
    )
    raw_path = root / "evidence/load/raw/test-run.json"
    raw = load_json(raw_path)
    raw["testRunStatistics"]["Total"]["sampleCount"] += 1
    _write_json(raw_path, raw)
    capture_path = root / evidence["capture"]["manifestFile"]
    capture = load_json(capture_path)
    capture["testRun"]["sha256"] = hashlib.sha256(
        raw_path.read_bytes()
    ).hexdigest()
    _write_json(capture_path, capture)
    evidence["capture"]["manifestSha256"] = hashlib.sha256(
        capture_path.read_bytes()
    ).hexdigest()
    _write_json(evidence_path, evidence)
    monkeypatch.setattr(shared_challenges, "validate_handoff", lambda *_: handoff)

    with pytest.raises(
        ValueError,
        match="normalized load observation differs from raw capture",
    ):
        shared_challenges.validate_shared_challenge_evidence(
            "load",
            evidence_path,
            root / "evidence/modernization-contract.json",
            _contracts(repo_root),
            root,
        )


def test_p6_load_validator_rejects_report_predating_recovery(
    tmp_path: Path,
    repo_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A report cannot replay recovery evidence captured after the report."""
    root, evidence_path, evidence, handoff, observations = _prepare_validator_bundle(
        "load", tmp_path, repo_root
    )
    evidence["capturedAt"] = "2026-08-20T12:09:00Z"
    run_path = evidence["testRun"]["resultFile"]
    observations[run_path]["capturedAt"] = "2026-08-20T12:06:00Z"
    _write_json(root / run_path, observations[run_path])
    _write_json(evidence_path, evidence)
    monkeypatch.setattr(shared_challenges, "validate_handoff", lambda *_: handoff)

    with pytest.raises(ValueError, match="captured before recovery"):
        shared_challenges.validate_shared_challenge_evidence(
            "load",
            evidence_path,
            root / "evidence/modernization-contract.json",
            _contracts(repo_root),
            root,
        )


def test_p6_cicd_validator_rejects_unrelated_candidate(
    tmp_path: Path,
    repo_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A healthy candidate from another Container App cannot validate."""
    root, evidence_path, evidence, handoff, observations = _prepare_validator_bundle(
        "cicd", tmp_path, repo_root
    )
    candidate_path = evidence["revisions"]["resultFile"]
    observations[candidate_path]["containerAppResourceId"] = handoff["application"][
        "resourceId"
    ].replace("ca-mh-example", "ca-other")
    _write_json(root / candidate_path, observations[candidate_path])
    monkeypatch.setattr(shared_challenges, "validate_handoff", lambda *_: handoff)

    with pytest.raises(ValueError, match="different Container App"):
        shared_challenges.validate_shared_challenge_evidence(
            "cicd",
            evidence_path,
            root / "evidence/modernization-contract.json",
            _contracts(repo_root),
            root,
        )


def test_p6_cicd_validator_rejects_wrong_stack_workflow(
    tmp_path: Path,
    repo_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A Java workflow cannot claim a .NET handoff subject."""
    root, evidence_path, evidence, handoff, _ = _prepare_validator_bundle(
        "cicd", tmp_path, repo_root
    )
    evidence["workflow"]["file"] = ".github/workflows/catalog-java.yml"
    workflow_path = root / evidence["workflow"]["file"]
    workflow_path.parent.mkdir(parents=True, exist_ok=True)
    workflow_path.write_text("fixture\n", encoding="utf-8")
    _write_json(evidence_path, evidence)
    monkeypatch.setattr(shared_challenges, "validate_handoff", lambda *_: handoff)

    with pytest.raises(ValueError, match="workflow file differs"):
        shared_challenges.validate_shared_challenge_evidence(
            "cicd",
            evidence_path,
            root / "evidence/modernization-contract.json",
            _contracts(repo_root),
            root,
        )


def test_p6_cicd_validator_rejects_unrelated_github_run(
    tmp_path: Path,
    repo_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Relabeled local fields cannot replace immutable GitHub run metadata."""
    root, evidence_path, evidence, handoff, observations = _prepare_validator_bundle(
        "cicd", tmp_path, repo_root
    )
    workflow_path = evidence["workflow"]["resultFile"]
    observations[workflow_path]["headSha"] = "2" * 40
    _write_json(root / workflow_path, observations[workflow_path])
    monkeypatch.setattr(shared_challenges, "validate_handoff", lambda *_: handoff)

    with pytest.raises(ValueError, match="head SHA differs"):
        shared_challenges.validate_shared_challenge_evidence(
            "cicd",
            evidence_path,
            root / "evidence/modernization-contract.json",
            _contracts(repo_root),
            root,
        )


def test_p6_cicd_validator_separates_control_and_source_commits(
    tmp_path: Path,
    repo_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A workflow control commit cannot masquerade as application source."""
    root, evidence_path, evidence, handoff, observations = _prepare_validator_bundle(
        "cicd", tmp_path, repo_root
    )
    source_commit = handoff["source"]["commitSha"]
    evidence["workflow"]["headSha"] = source_commit
    for path, observation in observations.items():
        if "headSha" in observation:
            observation["headSha"] = source_commit
            _write_json(root / path, observation)
    _write_json(evidence_path, evidence)
    monkeypatch.setattr(shared_challenges, "validate_handoff", lambda *_: handoff)

    with pytest.raises(ValueError, match="control SHA must differ"):
        shared_challenges.validate_shared_challenge_evidence(
            "cicd",
            evidence_path,
            root / "evidence/modernization-contract.json",
            _contracts(repo_root),
            root,
        )


def test_p6_cicd_validator_rejects_handoff_digest_drift(
    tmp_path: Path,
    repo_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The workflow must build from the exact handoff read at its head SHA."""
    root, evidence_path, evidence, handoff, _ = _prepare_validator_bundle(
        "cicd", tmp_path, repo_root
    )
    evidence["workflow"]["handoffSha256"] = "f" * 64
    _write_json(evidence_path, evidence)
    monkeypatch.setattr(shared_challenges, "validate_handoff", lambda *_: handoff)

    with pytest.raises(ValueError, match="handoff digest differs"):
        shared_challenges.validate_shared_challenge_evidence(
            "cicd",
            evidence_path,
            root / "evidence/modernization-contract.json",
            _contracts(repo_root),
            root,
        )


def test_p6_cicd_validator_binds_handoff_to_control_commit(
    tmp_path: Path,
    repo_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A current handoff cannot be relabeled as the control commit's blob."""
    root, evidence_path, evidence, handoff, _ = _prepare_validator_bundle(
        "cicd", tmp_path, repo_root
    )
    handoff_path = root / "evidence/modernization-contract.json"
    handoff_path.write_bytes(handoff_path.read_bytes() + b"\n")
    evidence["workflow"]["handoffSha256"] = hashlib.sha256(
        handoff_path.read_bytes()
    ).hexdigest()
    _write_json(evidence_path, evidence)
    monkeypatch.setattr(shared_challenges, "validate_handoff", lambda *_: handoff)

    with pytest.raises(ValueError, match="control-commit blob"):
        shared_challenges.validate_shared_challenge_evidence(
            "cicd",
            evidence_path,
            handoff_path,
            _contracts(repo_root),
            root,
        )


def test_p6_cicd_validator_rejects_image_commit_divergence(
    tmp_path: Path,
    repo_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Matching build fields cannot replace the exact handoff commit."""
    root, evidence_path, evidence, handoff, observations = _prepare_validator_bundle(
        "cicd", tmp_path, repo_root
    )
    other_commit = "1" * 40
    evidence["image"]["sourceCommit"] = other_commit
    evidence["image"]["tag"] = other_commit
    build_path = evidence["image"]["resultFile"]
    observations[build_path]["sourceCommit"] = other_commit
    observations[build_path]["tag"] = other_commit
    _write_json(root / build_path, observations[build_path])
    _write_json(evidence_path, evidence)
    monkeypatch.setattr(shared_challenges, "validate_handoff", lambda *_: handoff)

    with pytest.raises(ValueError, match="source commit differs|exact handoff commit"):
        shared_challenges.validate_shared_challenge_evidence(
            "cicd",
            evidence_path,
            root / "evidence/modernization-contract.json",
            _contracts(repo_root),
            root,
        )


def test_p6_cicd_validator_rejects_candidate_suffix_divergence(
    tmp_path: Path,
    repo_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Candidate revision identity must derive from the handoff commit."""
    root, evidence_path, evidence, handoff, observations = _prepare_validator_bundle(
        "cicd", tmp_path, repo_root
    )
    other_candidate = "ca-mh-example--ci-111111111111"
    evidence["revisions"]["candidate"] = other_candidate
    observations[evidence["revisions"]["resultFile"]][
        "revisionName"
    ] = other_candidate
    observations[evidence["smoke"]["resultFile"]]["revisionName"] = other_candidate
    for stage in ("before", "promotion", "rollback"):
        observations[evidence["traffic"][stage]["resultFile"]][
            "candidateRevision"
        ] = other_candidate
    for path, observation in observations.items():
        _write_json(root / path, observation)
    _write_json(evidence_path, evidence)
    monkeypatch.setattr(shared_challenges, "validate_handoff", lambda *_: handoff)

    with pytest.raises(ValueError, match="candidate revision suffix differs"):
        shared_challenges.validate_shared_challenge_evidence(
            "cicd",
            evidence_path,
            root / "evidence/modernization-contract.json",
            _contracts(repo_root),
            root,
        )


def test_p6_cicd_validator_rejects_unrelated_smoke_endpoints(
    tmp_path: Path,
    repo_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Self-consistent status claims cannot target an unrelated candidate endpoint."""
    root, evidence_path, evidence, handoff, observations = _prepare_validator_bundle(
        "cicd", tmp_path, repo_root
    )
    unrelated = "https://unrelated.example.invalid"
    evidence["smoke"]["candidateUrl"] = unrelated
    evidence["smoke"]["healthUrl"] = f"{unrelated}/healthz"
    evidence["smoke"]["readinessUrl"] = f"{unrelated}/readyz"
    smoke_path = evidence["smoke"]["resultFile"]
    observations[smoke_path]["candidateUrl"] = unrelated
    observations[smoke_path]["healthUrl"] = f"{unrelated}/healthz"
    observations[smoke_path]["readinessUrl"] = f"{unrelated}/readyz"
    _write_json(root / smoke_path, observations[smoke_path])
    _write_json(evidence_path, evidence)
    monkeypatch.setattr(shared_challenges, "validate_handoff", lambda *_: handoff)

    with pytest.raises(ValueError, match="smoke candidate URL differs"):
        shared_challenges.validate_shared_challenge_evidence(
            "cicd",
            evidence_path,
            root / "evidence/modernization-contract.json",
            _contracts(repo_root),
            root,
        )


def test_p6_cicd_validator_rejects_unrelated_transition_endpoints(
    tmp_path: Path,
    repo_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Promotion checks must use the handoff health and readiness endpoints."""
    root, evidence_path, evidence, handoff, observations = _prepare_validator_bundle(
        "cicd", tmp_path, repo_root
    )
    promotion_path = evidence["traffic"]["promotion"]["resultFile"]
    observations[promotion_path]["healthUrl"] = (
        "https://unrelated.example.invalid/healthz"
    )
    _write_json(root / promotion_path, observations[promotion_path])
    monkeypatch.setattr(shared_challenges, "validate_handoff", lambda *_: handoff)

    with pytest.raises(ValueError, match="different application endpoints"):
        shared_challenges.validate_shared_challenge_evidence(
            "cicd",
            evidence_path,
            root / "evidence/modernization-contract.json",
            _contracts(repo_root),
            root,
        )


def test_p6_cicd_validator_rejects_cross_subscription_identity_enumeration(
    tmp_path: Path,
    repo_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """One subscription query cannot prove assignments in another subscription."""
    root, evidence_path, evidence, handoff, observations = _prepare_validator_bundle(
        "cicd", tmp_path, repo_root
    )
    original_subscription = "00000000-0000-0000-0000-000000000000"
    identity_subscription = "00000000-0000-0000-0000-000000000009"
    identity = evidence["identity"]
    identity["resourceId"] = identity["resourceId"].replace(
        original_subscription,
        identity_subscription,
    )
    identity["roleAssignmentEnumeration"]["subscriptionId"] = (
        identity_subscription
    )
    for environment in ("staging", "production"):
        identity["federatedCredentialResourceIds"][environment] = identity[
            "federatedCredentialResourceIds"
        ][environment].replace(original_subscription, identity_subscription)

    identity_path = identity["resultFile"]
    observations[identity_path]["resourceId"] = identity["resourceId"]
    observations[identity_path]["roleAssignmentEnumeration"][
        "subscriptionId"
    ] = (
        identity_subscription
    )
    for credential in observations[identity_path]["federatedCredentials"]:
        credential["resourceId"] = credential["resourceId"].replace(
            original_subscription,
            identity_subscription,
        )
    _write_json(root / identity_path, observations[identity_path])
    _write_json(evidence_path, evidence)
    monkeypatch.setattr(shared_challenges, "validate_handoff", lambda *_: handoff)

    with pytest.raises(ValueError, match="must share one subscription"):
        shared_challenges.validate_shared_challenge_evidence(
            "cicd",
            evidence_path,
            root / "evidence/modernization-contract.json",
            _contracts(repo_root),
            root,
        )


def test_p6_cicd_validator_rejects_roles_for_another_principal(
    tmp_path: Path,
    repo_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Correct role scopes assigned to another principal cannot validate."""
    root, evidence_path, evidence, handoff, observations = _prepare_validator_bundle(
        "cicd", tmp_path, repo_root
    )
    identity_path = evidence["identity"]["resultFile"]
    observations[identity_path]["roleAssignments"][0][
        "principalId"
    ] = "00000000-0000-0000-0000-000000000099"
    _write_json(root / identity_path, observations[identity_path])
    monkeypatch.setattr(shared_challenges, "validate_handoff", lambda *_: handoff)

    with pytest.raises(ValueError, match="include another principal"):
        shared_challenges.validate_shared_challenge_evidence(
            "cicd",
            evidence_path,
            root / "evidence/modernization-contract.json",
            _contracts(repo_root),
            root,
        )


def test_p6_cicd_validator_rejects_broader_principal_assignments(
    tmp_path: Path,
    repo_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Exhaustive principal evidence must reject inherited broader access."""
    root, evidence_path, evidence, handoff, observations = _prepare_validator_bundle(
        "cicd", tmp_path, repo_root
    )
    identity_path = evidence["identity"]["resultFile"]
    observations[identity_path]["roleAssignments"].append(
        {
            "resourceId": (
                "/subscriptions/00000000-0000-0000-0000-000000000000/providers/"
                "Microsoft.Authorization/roleAssignments/"
                "00000000-0000-0000-0000-000000000007"
            ),
            "principalId": evidence["identity"]["principalId"],
            "roleDefinitionId": "8e3af657-a8ff-443c-a75c-2fe8c4bcb635",
            "scope": "/subscriptions/00000000-0000-0000-0000-000000000000",
        }
    )
    _write_json(root / identity_path, observations[identity_path])
    monkeypatch.setattr(shared_challenges, "validate_handoff", lambda *_: handoff)

    with pytest.raises(ValueError, match="at most 2 items"):
        shared_challenges.validate_shared_challenge_evidence(
            "cicd",
            evidence_path,
            root / "evidence/modernization-contract.json",
            _contracts(repo_root),
            root,
        )


def test_p6_cicd_validator_rejects_role_ids_outside_declared_scope(
    tmp_path: Path,
    repo_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A subscription-level assignment ID cannot claim a resource-level scope."""
    root, evidence_path, evidence, handoff, observations = _prepare_validator_bundle(
        "cicd", tmp_path, repo_root
    )
    identity_path = evidence["identity"]["resultFile"]
    observations[identity_path]["roleAssignments"][0]["resourceId"] = (
        "/subscriptions/00000000-0000-0000-0000-000000000000/providers/"
        "Microsoft.Authorization/roleAssignments/"
        "00000000-0000-0000-0000-000000000005"
    )
    _write_json(root / identity_path, observations[identity_path])
    monkeypatch.setattr(shared_challenges, "validate_handoff", lambda *_: handoff)

    with pytest.raises(ValueError, match="resource ID differs from its declared scope"):
        shared_challenges.validate_shared_challenge_evidence(
            "cicd",
            evidence_path,
            root / "evidence/modernization-contract.json",
            _contracts(repo_root),
            root,
        )


def test_p6_cicd_validator_rejects_raw_role_audit_divergence(
    tmp_path: Path,
    repo_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Normalized least privilege must equal facilitator raw Azure output."""
    root, evidence_path, evidence, handoff, observations = _prepare_validator_bundle(
        "cicd", tmp_path, repo_root
    )
    enumeration = evidence["identity"]["roleAssignmentEnumeration"]
    raw_path = root / enumeration["rawResultFile"]
    raw_assignments = json.loads(raw_path.read_text(encoding="utf-8"))
    raw_assignments[0]["scope"] = (
        "/subscriptions/00000000-0000-0000-0000-000000000000"
    )
    raw_path.write_text(
        json.dumps(raw_assignments, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    raw_sha256 = hashlib.sha256(raw_path.read_bytes()).hexdigest()
    enumeration["rawResultSha256"] = raw_sha256
    identity_path = evidence["identity"]["resultFile"]
    observations[identity_path]["roleAssignmentEnumeration"][
        "rawResultSha256"
    ] = raw_sha256
    _write_json(root / identity_path, observations[identity_path])
    _write_json(evidence_path, evidence)
    monkeypatch.setattr(shared_challenges, "validate_handoff", lambda *_: handoff)

    with pytest.raises(ValueError, match="differ from facilitator raw output"):
        shared_challenges.validate_shared_challenge_evidence(
            "cicd",
            evidence_path,
            root / "evidence/modernization-contract.json",
            _contracts(repo_root),
            root,
        )


def test_p6_cicd_validator_requires_raw_role_definition_resource_ids(
    tmp_path: Path,
    repo_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Raw Azure CLI roles retain full role-definition resource IDs."""
    root, evidence_path, evidence, handoff, observations = _prepare_validator_bundle(
        "cicd", tmp_path, repo_root
    )
    enumeration = evidence["identity"]["roleAssignmentEnumeration"]
    raw_path = root / enumeration["rawResultFile"]
    raw_assignments = json.loads(raw_path.read_text(encoding="utf-8"))
    for assignment in raw_assignments:
        assignment["roleDefinitionId"] = assignment["roleDefinitionId"].rsplit(
            "/", maxsplit=1
        )[-1]
    raw_path.write_text(
        json.dumps(raw_assignments, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    raw_sha256 = hashlib.sha256(raw_path.read_bytes()).hexdigest()
    enumeration["rawResultSha256"] = raw_sha256
    identity_path = evidence["identity"]["resultFile"]
    observations[identity_path]["roleAssignmentEnumeration"][
        "rawResultSha256"
    ] = raw_sha256
    _write_json(root / identity_path, observations[identity_path])
    _write_json(evidence_path, evidence)
    monkeypatch.setattr(shared_challenges, "validate_handoff", lambda *_: handoff)

    with pytest.raises(ValueError, match="invalid role definition ID"):
        shared_challenges.validate_shared_challenge_evidence(
            "cicd",
            evidence_path,
            root / "evidence/modernization-contract.json",
            _contracts(repo_root),
            root,
        )


def test_p6_cicd_validator_rejects_hardcoded_revision_state(
    tmp_path: Path,
    repo_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Normalized health cannot disagree with the raw Azure revision list."""
    root, evidence_path, evidence, handoff, _ = _prepare_validator_bundle(
        "cicd", tmp_path, repo_root
    )
    promotion = evidence["traffic"]["promotion"]
    raw_path = root / promotion["rawResultFile"]
    raw_revisions = json.loads(raw_path.read_text(encoding="utf-8"))
    candidate = evidence["revisions"]["candidate"]
    next(
        revision for revision in raw_revisions if revision["name"] == candidate
    )["properties"]["healthState"] = "Unhealthy"
    raw_path.write_text(
        json.dumps(raw_revisions, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    promotion["rawResultSha256"] = hashlib.sha256(
        raw_path.read_bytes()
    ).hexdigest()
    _write_json(evidence_path, evidence)
    monkeypatch.setattr(shared_challenges, "validate_handoff", lambda *_: handoff)

    with pytest.raises(ValueError, match="differs from raw Azure output"):
        shared_challenges.validate_shared_challenge_evidence(
            "cicd",
            evidence_path,
            root / "evidence/modernization-contract.json",
            _contracts(repo_root),
            root,
        )


def test_p6_cicd_validator_rejects_replayed_workflow_attempt(
    tmp_path: Path,
    repo_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A traffic observation from another workflow attempt cannot validate."""
    root, evidence_path, evidence, handoff, observations = _prepare_validator_bundle(
        "cicd", tmp_path, repo_root
    )
    promotion_path = evidence["traffic"]["promotion"]["resultFile"]
    observations[promotion_path]["runAttempt"] = 2
    _write_json(root / promotion_path, observations[promotion_path])
    monkeypatch.setattr(shared_challenges, "validate_handoff", lambda *_: handoff)

    with pytest.raises(ValueError, match="differs from the observed GitHub run"):
        shared_challenges.validate_shared_challenge_evidence(
            "cicd",
            evidence_path,
            root / "evidence/modernization-contract.json",
            _contracts(repo_root),
            root,
        )


def test_p6_cicd_validator_rejects_mutable_job_name_replay(
    tmp_path: Path,
    repo_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A matching job name and window cannot replace its immutable GitHub ID."""
    root, evidence_path, evidence, handoff, observations = _prepare_validator_bundle(
        "cicd", tmp_path, repo_root
    )
    workflow_path = evidence["workflow"]["resultFile"]
    observations[workflow_path]["jobs"][0]["jobId"] = 999999
    _write_json(root / workflow_path, observations[workflow_path])
    monkeypatch.setattr(shared_challenges, "validate_handoff", lambda *_: handoff)

    with pytest.raises(ValueError, match="GitHub job ID differs"):
        shared_challenges.validate_shared_challenge_evidence(
            "cicd",
            evidence_path,
            root / "evidence/modernization-contract.json",
            _contracts(repo_root),
            root,
        )


def test_p6_cicd_validator_rejects_report_predating_rollback(
    tmp_path: Path,
    repo_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A CI/CD report cannot predate its rollback observation."""
    root, evidence_path, evidence, handoff, _ = _prepare_validator_bundle(
        "cicd", tmp_path, repo_root
    )
    evidence["capturedAt"] = "2026-08-20T13:20:00Z"
    _write_json(evidence_path, evidence)
    monkeypatch.setattr(shared_challenges, "validate_handoff", lambda *_: handoff)

    with pytest.raises(ValueError, match="captured before post-run evidence"):
        shared_challenges.validate_shared_challenge_evidence(
            "cicd",
            evidence_path,
            root / "evidence/modernization-contract.json",
            _contracts(repo_root),
            root,
        )


def test_p6_cicd_validator_rejects_promotion_before_approval(
    tmp_path: Path,
    repo_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Timestamped observations must prove approval preceded promotion."""
    root, evidence_path, evidence, handoff, observations = _prepare_validator_bundle(
        "cicd", tmp_path, repo_root
    )
    promotion = evidence["traffic"]["promotion"]
    promotion["observedAt"] = "2026-08-20T13:05:00Z"
    observations[promotion["resultFile"]]["observedAt"] = promotion["observedAt"]
    _write_json(root / promotion["resultFile"], observations[promotion["resultFile"]])
    _write_json(evidence_path, evidence)
    monkeypatch.setattr(shared_challenges, "validate_handoff", lambda *_: handoff)

    with pytest.raises(ValueError, match="production job|violate"):
        shared_challenges.validate_shared_challenge_evidence(
            "cicd",
            evidence_path,
            root / "evidence/modernization-contract.json",
            _contracts(repo_root),
            root,
        )


def test_p6_cicd_validator_requires_approval_before_production_job(
    tmp_path: Path,
    repo_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """GitHub environment approval must precede the protected job start."""
    root, evidence_path, evidence, handoff, observations = _prepare_validator_bundle(
        "cicd", tmp_path, repo_root
    )
    evidence["approval"]["approvedAt"] = "2026-08-20T13:12:00Z"
    approval_path = evidence["approval"]["resultFile"]
    observations[approval_path]["approvedAt"] = "2026-08-20T13:12:00Z"
    _write_json(root / approval_path, observations[approval_path])
    _write_json(evidence_path, evidence)
    monkeypatch.setattr(shared_challenges, "validate_handoff", lambda *_: handoff)

    with pytest.raises(ValueError, match="approval.*out of order"):
        shared_challenges.validate_shared_challenge_evidence(
            "cicd",
            evidence_path,
            root / "evidence/modernization-contract.json",
            _contracts(repo_root),
            root,
        )


def test_p6_cicd_validator_requires_guard_before_promotion(
    tmp_path: Path,
    repo_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A rollback trap installed after promotion is not fail-safe."""
    root, evidence_path, evidence, handoff, observations = _prepare_validator_bundle(
        "cicd", tmp_path, repo_root
    )
    safety = evidence["traffic"]["safety"]
    safety["guardInstalledAt"] = "2026-08-20T13:15:00Z"
    safety_path = safety["resultFile"]
    observations[safety_path]["guardInstalledAt"] = safety["guardInstalledAt"]
    _write_json(root / safety_path, observations[safety_path])
    _write_json(evidence_path, evidence)
    monkeypatch.setattr(shared_challenges, "validate_handoff", lambda *_: handoff)

    with pytest.raises(ValueError, match="lifecycle timestamps are out of order"):
        shared_challenges.validate_shared_challenge_evidence(
            "cicd",
            evidence_path,
            root / "evidence/modernization-contract.json",
            _contracts(repo_root),
            root,
        )


def test_p6_observability_validator_rejects_arbitrary_queries(
    tmp_path: Path,
    repo_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A nonempty unrelated query cannot stand in for a required panel."""
    root, evidence_path, evidence, handoff, observations = _prepare_validator_bundle(
        "observability", tmp_path, repo_root
    )
    panel = evidence["panels"][0]
    panel["query"] = (
        "print value=1 // "
        f"{handoff['application']['revisionName']} unrelated evidence"
    )
    observations[panel["resultFile"]]["query"] = panel["query"]
    _write_json(root / panel["resultFile"], observations[panel["resultFile"]])
    _write_json(evidence_path, evidence)
    monkeypatch.setattr(shared_challenges, "validate_handoff", lambda *_: handoff)

    with pytest.raises(ValueError, match="differs from the frozen template"):
        shared_challenges.validate_shared_challenge_evidence(
            "observability",
            evidence_path,
            root / "evidence/modernization-contract.json",
            _contracts(repo_root),
            root,
        )


@pytest.mark.parametrize(
    "unsupported_shape",
    ["azure-metrics-v2", "revision-dimension", "maximum-aggregation"],
)
def test_p6_observability_validator_rejects_unsupported_aca_metric_queries(
    unsupported_shape: str,
    tmp_path: Path,
    repo_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Dimensional ACA metric queries cannot claim diagnostic-setting evidence."""
    root, evidence_path, evidence, handoff, observations = _prepare_validator_bundle(
        "observability", tmp_path, repo_root
    )
    panel = next(
        item for item in evidence["panels"] if item["id"] == "replica-count"
    )
    if unsupported_shape == "azure-metrics-v2":
        bad_query = panel["query"].replace("AzureMetrics |", "AzureMetricsV2 |", 1)
    elif unsupported_shape == "revision-dimension":
        bad_query = panel["query"].replace(
            '| where MetricName == "Replicas" and TimeGrain == "PT1M" |',
            '| where MetricName == "Replicas" and TimeGrain == "PT1M" '
            '| where tostring(Dimension["revisionName"]) == '
            f'"{handoff["application"]["revisionName"]}" |',
            1,
        )
    else:
        bad_query = panel["query"].replace(
            "toint(max(Total))",
            "toint(max(Maximum))",
            1,
        )
    panel["query"] = bad_query
    panel["querySha256"] = hashlib.sha256(bad_query.encode("utf-8")).hexdigest()
    observation = observations[panel["resultFile"]]
    observation["query"] = bad_query
    observation["querySha256"] = panel["querySha256"]
    _write_json(root / panel["resultFile"], observation)
    _write_json(evidence_path, evidence)
    monkeypatch.setattr(shared_challenges, "validate_handoff", lambda *_: handoff)

    with pytest.raises(ValueError, match="differs from the frozen template"):
        shared_challenges.validate_shared_challenge_evidence(
            "observability",
            evidence_path,
            root / "evidence/modernization-contract.json",
            _contracts(repo_root),
            root,
        )


def test_p6_observability_validator_rejects_unrelated_workbook_content(
    tmp_path: Path,
    repo_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Separate query results cannot make an empty deployed workbook valid."""
    root, evidence_path, evidence, handoff, observations = _prepare_validator_bundle(
        "observability", tmp_path, repo_root
    )
    workbook_path = evidence["workbook"]["resultFile"]
    serialized_data = '{"items":[],"version":"Notebook/1.0"}'
    serialized_digest = hashlib.sha256(serialized_data.encode("utf-8")).hexdigest()
    evidence["workbook"]["serializedDataSha256"] = serialized_digest
    observations[workbook_path]["serializedData"] = serialized_data
    observations[workbook_path]["serializedDataSha256"] = serialized_digest
    _write_json(root / workbook_path, observations[workbook_path])
    _write_json(evidence_path, evidence)
    monkeypatch.setattr(shared_challenges, "validate_handoff", lambda *_: handoff)

    with pytest.raises(ValueError, match="panels differ"):
        shared_challenges.validate_shared_challenge_evidence(
            "observability",
            evidence_path,
            root / "evidence/modernization-contract.json",
            _contracts(repo_root),
            root,
        )


def test_p6_observability_validator_rejects_cross_workspace_panels(
    tmp_path: Path,
    repo_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Exact KQL cannot use a cross-component resource outside the handoff."""
    root, evidence_path, evidence, handoff, observations = _prepare_validator_bundle(
        "observability", tmp_path, repo_root
    )
    workbook_path = evidence["workbook"]["resultFile"]
    serialized = json.loads(observations[workbook_path]["serializedData"])
    serialized["items"][0]["content"]["crossComponentResources"] = [
        "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/"
        "rg-example/providers/Microsoft.OperationalInsights/workspaces/log-other"
    ]
    serialized_data = json.dumps(serialized, separators=(",", ":"), sort_keys=True)
    serialized_digest = hashlib.sha256(serialized_data.encode("utf-8")).hexdigest()
    evidence["workbook"]["serializedDataSha256"] = serialized_digest
    observations[workbook_path]["serializedData"] = serialized_data
    observations[workbook_path]["serializedDataSha256"] = serialized_digest
    _write_json(root / workbook_path, observations[workbook_path])
    _write_json(evidence_path, evidence)
    monkeypatch.setattr(shared_challenges, "validate_handoff", lambda *_: handoff)

    with pytest.raises(ValueError, match="cross-component resources differ"):
        shared_challenges.validate_shared_challenge_evidence(
            "observability",
            evidence_path,
            root / "evidence/modernization-contract.json",
            _contracts(repo_root),
            root,
        )


def test_p6_observability_validator_rejects_nonfinite_nested_workbook_json(
    tmp_path: Path,
    repo_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A JSON string containing Infinity cannot bypass strict file decoding."""
    root, evidence_path, evidence, handoff, observations = _prepare_validator_bundle(
        "observability", tmp_path, repo_root
    )
    workbook_path = evidence["workbook"]["resultFile"]
    serialized = json.loads(observations[workbook_path]["serializedData"])
    serialized["items"][0]["content"]["threshold"] = float("inf")
    serialized_data = json.dumps(serialized, separators=(",", ":"), sort_keys=True)
    serialized_digest = hashlib.sha256(serialized_data.encode("utf-8")).hexdigest()
    evidence["workbook"]["serializedDataSha256"] = serialized_digest
    observations[workbook_path]["serializedData"] = serialized_data
    observations[workbook_path]["serializedDataSha256"] = serialized_digest
    _write_json(root / workbook_path, observations[workbook_path])
    _write_json(evidence_path, evidence)
    monkeypatch.setattr(shared_challenges, "validate_handoff", lambda *_: handoff)

    with pytest.raises(ValueError, match="non-finite JSON constant is forbidden"):
        shared_challenges.validate_shared_challenge_evidence(
            "observability",
            evidence_path,
            root / "evidence/modernization-contract.json",
            _contracts(repo_root),
            root,
        )


def test_p6_observability_validator_rejects_unrelated_workbook_source(
    tmp_path: Path,
    repo_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Matching hashes cannot make an empty checked-in workbook template valid."""
    root, evidence_path, evidence, handoff, observations = _prepare_validator_bundle(
        "observability", tmp_path, repo_root
    )
    template_path = root / evidence["workbook"]["templateFile"]
    _write_json(template_path, {"version": "Notebook/1.0", "items": []})
    template_digest = hashlib.sha256(template_path.read_bytes()).hexdigest()
    evidence["workbook"]["templateSha256"] = template_digest
    workbook_path = evidence["workbook"]["resultFile"]
    observations[workbook_path]["templateSha256"] = template_digest
    _write_json(root / workbook_path, observations[workbook_path])
    _write_json(evidence_path, evidence)
    monkeypatch.setattr(shared_challenges, "validate_handoff", lambda *_: handoff)

    with pytest.raises(ValueError, match="template differs"):
        shared_challenges.validate_shared_challenge_evidence(
            "observability",
            evidence_path,
            root / "evidence/modernization-contract.json",
            _contracts(repo_root),
            root,
        )


def test_p6_observability_validator_rejects_unrelated_kql_source(
    tmp_path: Path,
    repo_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Matching hashes cannot detach checked-in KQL from frozen templates."""
    root, evidence_path, evidence, handoff, observations = _prepare_validator_bundle(
        "observability", tmp_path, repo_root
    )
    queries_path = root / evidence["workbook"]["queriesFile"]
    queries_path.write_text("print value=1\n", encoding="utf-8")
    queries_digest = hashlib.sha256(queries_path.read_bytes()).hexdigest()
    evidence["workbook"]["queriesSha256"] = queries_digest
    workbook_path = evidence["workbook"]["resultFile"]
    observations[workbook_path]["queriesSha256"] = queries_digest
    _write_json(root / workbook_path, observations[workbook_path])
    _write_json(evidence_path, evidence)
    monkeypatch.setattr(shared_challenges, "validate_handoff", lambda *_: handoff)

    with pytest.raises(ValueError, match="KQL source differs"):
        shared_challenges.validate_shared_challenge_evidence(
            "observability",
            evidence_path,
            root / "evidence/modernization-contract.json",
            _contracts(repo_root),
            root,
        )


def test_p6_observability_validator_rejects_nested_workbook_queries(
    tmp_path: Path,
    repo_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Query panels hidden inside workbook groups cannot bypass the frozen set."""
    root, evidence_path, evidence, handoff, observations = _prepare_validator_bundle(
        "observability", tmp_path, repo_root
    )
    workbook_path = evidence["workbook"]["resultFile"]
    serialized = json.loads(observations[workbook_path]["serializedData"])
    serialized["items"].append(
        {
            "type": 12,
            "name": "hidden-group",
            "content": {
                "items": [
                    {
                        "type": 3,
                        "name": "unrelated",
                        "content": {
                            "version": "KqlItem/1.0",
                            "queryType": 0,
                            "resourceType": "microsoft.operationalinsights/workspaces",
                            "query": "print value=1",
                        },
                    }
                ]
            },
        }
    )
    serialized_data = json.dumps(serialized, separators=(",", ":"), sort_keys=True)
    serialized_digest = hashlib.sha256(serialized_data.encode("utf-8")).hexdigest()
    evidence["workbook"]["serializedDataSha256"] = serialized_digest
    observations[workbook_path]["serializedData"] = serialized_data
    observations[workbook_path]["serializedDataSha256"] = serialized_digest
    _write_json(root / workbook_path, observations[workbook_path])
    _write_json(evidence_path, evidence)
    monkeypatch.setattr(shared_challenges, "validate_handoff", lambda *_: handoff)

    with pytest.raises(ValueError, match="panels differ"):
        shared_challenges.validate_shared_challenge_evidence(
            "observability",
            evidence_path,
            root / "evidence/modernization-contract.json",
            _contracts(repo_root),
            root,
        )


def test_p6_observability_validator_rejects_invalid_workbook_query_context(
    tmp_path: Path,
    repo_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Correct KQL text cannot pass with an incompatible workbook query type."""
    root, evidence_path, evidence, handoff, observations = _prepare_validator_bundle(
        "observability", tmp_path, repo_root
    )
    workbook_path = evidence["workbook"]["resultFile"]
    serialized = json.loads(observations[workbook_path]["serializedData"])
    serialized["items"][0]["content"]["queryType"] = 1
    serialized_data = json.dumps(serialized, separators=(",", ":"), sort_keys=True)
    serialized_digest = hashlib.sha256(serialized_data.encode("utf-8")).hexdigest()
    evidence["workbook"]["serializedDataSha256"] = serialized_digest
    observations[workbook_path]["serializedData"] = serialized_data
    observations[workbook_path]["serializedDataSha256"] = serialized_digest
    _write_json(root / workbook_path, observations[workbook_path])
    _write_json(evidence_path, evidence)
    monkeypatch.setattr(shared_challenges, "validate_handoff", lambda *_: handoff)

    with pytest.raises(ValueError, match="malformed Logs query panel"):
        shared_challenges.validate_shared_challenge_evidence(
            "observability",
            evidence_path,
            root / "evidence/modernization-contract.json",
            _contracts(repo_root),
            root,
        )


def test_p6_observability_validator_rejects_boolean_workbook_query_type(
    tmp_path: Path,
    repo_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """JSON false cannot exploit Python's bool-to-zero equality."""
    root, evidence_path, evidence, handoff, observations = _prepare_validator_bundle(
        "observability", tmp_path, repo_root
    )
    workbook_path = evidence["workbook"]["resultFile"]
    serialized = json.loads(observations[workbook_path]["serializedData"])
    serialized["items"][0]["content"]["queryType"] = False
    serialized_data = json.dumps(serialized, separators=(",", ":"), sort_keys=True)
    serialized_digest = hashlib.sha256(serialized_data.encode("utf-8")).hexdigest()
    evidence["workbook"]["serializedDataSha256"] = serialized_digest
    observations[workbook_path]["serializedData"] = serialized_data
    observations[workbook_path]["serializedDataSha256"] = serialized_digest
    _write_json(root / workbook_path, observations[workbook_path])
    _write_json(evidence_path, evidence)
    monkeypatch.setattr(shared_challenges, "validate_handoff", lambda *_: handoff)

    with pytest.raises(ValueError, match="malformed Logs query panel"):
        shared_challenges.validate_shared_challenge_evidence(
            "observability",
            evidence_path,
            root / "evidence/modernization-contract.json",
            _contracts(repo_root),
            root,
        )


def test_p6_observability_validator_rejects_wrong_workbook_source_id(
    tmp_path: Path,
    repo_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Deployed ARM sourceId must be the handoff Log Analytics workspace."""
    root, evidence_path, evidence, handoff, observations = _prepare_validator_bundle(
        "observability", tmp_path, repo_root
    )
    workbook_path = evidence["workbook"]["resultFile"]
    observations[workbook_path]["sourceId"] = observations[workbook_path][
        "sourceId"
    ].replace("log-mh-example", "log-other")
    _write_json(root / workbook_path, observations[workbook_path])
    monkeypatch.setattr(shared_challenges, "validate_handoff", lambda *_: handoff)

    with pytest.raises(ValueError, match="ARM sourceId differs"):
        shared_challenges.validate_shared_challenge_evidence(
            "observability",
            evidence_path,
            root / "evidence/modernization-contract.json",
            _contracts(repo_root),
            root,
        )


def test_p6_observability_validator_rejects_scalar_zero_results(
    tmp_path: Path,
    repo_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Zero-only normalized rows do not prove exercised panel behavior."""
    root, evidence_path, evidence, handoff, observations = _prepare_validator_bundle(
        "observability", tmp_path, repo_root
    )
    panel_path = evidence["panels"][0]["resultFile"]
    observations[panel_path]["rows"][0]["value"] = 0
    _write_json(root / panel_path, observations[panel_path])
    monkeypatch.setattr(shared_challenges, "validate_handoff", lambda *_: handoff)

    with pytest.raises(ValueError, match="greater than 0"):
        shared_challenges.validate_shared_challenge_evidence(
            "observability",
            evidence_path,
            root / "evidence/modernization-contract.json",
            _contracts(repo_root),
            root,
        )


def test_p6_observability_validator_rejects_boolean_query_values(
    tmp_path: Path,
    repo_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """JSON true cannot satisfy a positive numeric query result."""
    root, evidence_path, evidence, handoff, observations = _prepare_validator_bundle(
        "observability", tmp_path, repo_root
    )
    latency_path = next(
        panel["resultFile"] for panel in evidence["panels"] if panel["id"] == "latency"
    )
    observations[latency_path]["rows"][0]["value"] = True
    _write_json(root / latency_path, observations[latency_path])
    monkeypatch.setattr(shared_challenges, "validate_handoff", lambda *_: handoff)

    with pytest.raises(ValueError, match="valid number"):
        shared_challenges.validate_shared_challenge_evidence(
            "observability",
            evidence_path,
            root / "evidence/modernization-contract.json",
            _contracts(repo_root),
            root,
        )


@pytest.mark.parametrize(
    "nonfinite_value",
    [float("nan"), float("inf"), float("-inf")],
)
def test_p6_observability_validator_rejects_nonfinite_query_values(
    nonfinite_value: float,
    tmp_path: Path,
    repo_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Non-standard JSON numbers cannot satisfy scalar workbook results."""
    root, evidence_path, evidence, handoff, observations = _prepare_validator_bundle(
        "observability", tmp_path, repo_root
    )
    latency_path = next(
        panel["resultFile"] for panel in evidence["panels"] if panel["id"] == "latency"
    )
    observations[latency_path]["rows"][0]["value"] = nonfinite_value
    _write_json(root / latency_path, observations[latency_path])
    monkeypatch.setattr(shared_challenges, "validate_handoff", lambda *_: handoff)

    with pytest.raises(ValueError, match="non-finite JSON constant is forbidden"):
        shared_challenges.validate_shared_challenge_evidence(
            "observability",
            evidence_path,
            root / "evidence/modernization-contract.json",
            _contracts(repo_root),
            root,
        )


def test_p6_observability_validator_rejects_integer_enabled_flags(
    tmp_path: Path,
    repo_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """JSON 1 cannot satisfy the strict diagnostic-setting enabled flag."""
    root, evidence_path, evidence, handoff, observations = _prepare_validator_bundle(
        "observability", tmp_path, repo_root
    )
    metrics_path = evidence["metricsExport"]["resultFile"]
    observations[metrics_path]["enabled"] = 1
    _write_json(root / metrics_path, observations[metrics_path])
    monkeypatch.setattr(shared_challenges, "validate_handoff", lambda *_: handoff)

    with pytest.raises(ValueError, match="valid boolean"):
        shared_challenges.validate_shared_challenge_evidence(
            "observability",
            evidence_path,
            root / "evidence/modernization-contract.json",
            _contracts(repo_root),
            root,
        )


def test_p6_observability_validator_rejects_rows_outside_query_window(
    tmp_path: Path,
    repo_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Workbook rows must come from the explicit post-deployment query window."""
    root, evidence_path, evidence, handoff, observations = _prepare_validator_bundle(
        "observability", tmp_path, repo_root
    )
    panel_path = evidence["panels"][0]["resultFile"]
    observations[panel_path]["rows"][0]["timestamp"] = "2026-08-20T13:40:00Z"
    _write_json(root / panel_path, observations[panel_path])
    monkeypatch.setattr(shared_challenges, "validate_handoff", lambda *_: handoff)

    with pytest.raises(ValueError, match="rows must fall within"):
        shared_challenges.validate_shared_challenge_evidence(
            "observability",
            evidence_path,
            root / "evidence/modernization-contract.json",
            _contracts(repo_root),
            root,
        )


def test_p6_validator_rejects_symlinked_observations(
    tmp_path: Path,
    repo_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Observation references cannot redirect outside their declared file identity."""
    root, evidence_path, evidence, handoff, _ = _prepare_validator_bundle(
        "load", tmp_path, repo_root
    )
    result_path = root / evidence["testRun"]["resultFile"]
    replacement = root / "evidence/load/replacement.json"
    replacement.write_text("{}\n", encoding="utf-8")
    result_path.unlink()
    result_path.symlink_to(replacement)
    monkeypatch.setattr(shared_challenges, "validate_handoff", lambda *_: handoff)

    with pytest.raises(ValueError, match="contains a symlink"):
        shared_challenges.validate_shared_challenge_evidence(
            "load",
            evidence_path,
            root / "evidence/modernization-contract.json",
            _contracts(repo_root),
            root,
        )


def test_p6_validator_rejects_symlinked_handoff_references(
    tmp_path: Path,
    repo_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The handoff validator cannot resolve a referenced report through a symlink."""
    root, evidence_path, _, handoff, _ = _prepare_validator_bundle(
        "load", tmp_path, repo_root
    )
    telemetry_path = root / handoff["evidence"]["telemetryReport"]
    telemetry_path.parent.mkdir(parents=True, exist_ok=True)
    replacement = root / "evidence/real-telemetry-report.json"
    replacement.write_text("{}\n", encoding="utf-8")
    telemetry_path.symlink_to(replacement)
    monkeypatch.setattr(shared_challenges, "validate_handoff", lambda *_: handoff)

    with pytest.raises(ValueError, match="contains a symlink"):
        shared_challenges.validate_shared_challenge_evidence(
            "load",
            evidence_path,
            root / "evidence/modernization-contract.json",
            _contracts(repo_root),
            root,
        )


def test_p6_validator_rejects_nested_handoff_symlinks(
    tmp_path: Path,
    repo_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Nested telemetry result paths receive the same component-wise protection."""
    root, evidence_path, _, handoff, _ = _prepare_validator_bundle(
        "load", tmp_path, repo_root
    )
    telemetry_path = root / handoff["evidence"]["telemetryReport"]
    _write_json(
        telemetry_path,
        {
            "queries": {
                "resources": {
                    "resultFile": "evidence/telemetry/resources.json",
                }
            }
        },
    )
    replacement = root / "evidence/real-telemetry"
    replacement.mkdir(parents=True)
    telemetry_directory = root / "evidence/telemetry"
    telemetry_directory.symlink_to(replacement, target_is_directory=True)
    monkeypatch.setattr(shared_challenges, "validate_handoff", lambda *_: handoff)

    with pytest.raises(ValueError, match="contains a symlink"):
        shared_challenges.validate_shared_challenge_evidence(
            "load",
            evidence_path,
            root / "evidence/modernization-contract.json",
            _contracts(repo_root),
            root,
        )


def test_p6_validator_rejects_symlinks_inside_runtime_artifact_directories(
    tmp_path: Path,
    repo_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Runtime result directories cannot replay symlinked test files."""
    root, evidence_path, _, handoff, _ = _prepare_validator_bundle(
        "load", tmp_path, repo_root
    )
    runtime_report_path = root / handoff["evidence"]["runtimeTestReport"]
    _write_json(
        runtime_report_path,
        {
            "artifact": "evidence/runtime-results",
        },
    )
    runtime_directory = root / "evidence/runtime-results"
    runtime_directory.mkdir(parents=True)
    external_result = root / "evidence/external-passing-result.xml"
    external_result.write_text("<testsuite failures=\"0\" />\n", encoding="utf-8")
    (runtime_directory / "TEST-catalog.xml").symlink_to(external_result)
    monkeypatch.setattr(shared_challenges, "validate_handoff", lambda *_: handoff)

    with pytest.raises(ValueError, match="contains a symlink"):
        shared_challenges.validate_shared_challenge_evidence(
            "load",
            evidence_path,
            root / "evidence/modernization-contract.json",
            _contracts(repo_root),
            root,
        )


def test_p6_validator_rejects_intermediate_symlink_components(
    tmp_path: Path,
    repo_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An intermediate evidence-directory symlink cannot bypass containment."""
    root, evidence_path, _, handoff, _ = _prepare_validator_bundle(
        "load", tmp_path, repo_root
    )
    load_directory = root / "evidence/load"
    replacement = root / "evidence/real-load"
    load_directory.rename(replacement)
    load_directory.symlink_to(replacement, target_is_directory=True)
    monkeypatch.setattr(shared_challenges, "validate_handoff", lambda *_: handoff)

    with pytest.raises(ValueError, match="contains a symlink"):
        shared_challenges.validate_shared_challenge_evidence(
            "load",
            evidence_path,
            root / "evidence/modernization-contract.json",
            _contracts(repo_root),
            root,
        )


def test_p6_validator_rejects_symlinked_top_level_report(
    tmp_path: Path,
    repo_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The selected report itself must be a regular nonsymlink file."""
    root, evidence_path, _, handoff, _ = _prepare_validator_bundle(
        "load", tmp_path, repo_root
    )
    replacement = root / "evidence/real-load-report.json"
    evidence_path.rename(replacement)
    evidence_path.symlink_to(replacement)
    monkeypatch.setattr(shared_challenges, "validate_handoff", lambda *_: handoff)

    with pytest.raises(ValueError, match="contains a symlink"):
        shared_challenges.validate_shared_challenge_evidence(
            "load",
            evidence_path,
            root / "evidence/modernization-contract.json",
            _contracts(repo_root),
            root,
        )


def test_p6_validator_rejects_substituted_contract_directories(
    tmp_path: Path,
    repo_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A caller cannot replace the checked-in schemas and query declarations."""
    root, evidence_path, _, handoff, _ = _prepare_validator_bundle(
        "load", tmp_path, repo_root
    )
    alternate_contracts = root / "alternate-contracts"
    alternate_contracts.mkdir()
    monkeypatch.setattr(shared_challenges, "validate_handoff", lambda *_: handoff)

    with pytest.raises(ValueError, match="checked-in workshop/contracts tree"):
        shared_challenges.validate_shared_challenge_evidence(
            "load",
            evidence_path,
            root / "evidence/modernization-contract.json",
            alternate_contracts,
            root,
        )


def test_p6_validator_rejects_symlinks_inside_contract_tree(
    tmp_path: Path,
    repo_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Frozen schemas and query declarations cannot traverse symlinks."""
    root, evidence_path, _, handoff, _ = _prepare_validator_bundle(
        "load", tmp_path, repo_root
    )
    package_root = tmp_path / "package-root"
    contracts = package_root / "workshop/contracts"
    contracts.mkdir(parents=True)
    external_schema = tmp_path / "substituted-schema.json"
    external_schema.write_text("{}\n", encoding="utf-8")
    (contracts / "load-test-evidence.schema.json").symlink_to(external_schema)
    monkeypatch.setattr(
        shared_challenges,
        "_PACKAGE_REPOSITORY_ROOT",
        package_root,
    )
    monkeypatch.setattr(shared_challenges, "validate_handoff", lambda *_: handoff)

    with pytest.raises(ValueError, match="contains a symlink"):
        shared_challenges.validate_shared_challenge_evidence(
            "load",
            evidence_path,
            root / "evidence/modernization-contract.json",
            contracts,
            root,
        )
