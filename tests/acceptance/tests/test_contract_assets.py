"""Executable tests that freeze schemas, corpus identity, and normalization."""

from __future__ import annotations

import ast
import base64
import gzip
import io
import json
import re
import shutil
import subprocess
import tempfile
from copy import deepcopy
from datetime import datetime
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, FormatChecker
from jsonschema.exceptions import ValidationError as JsonSchemaValidationError
from pydantic import ValidationError

from catalog_acceptance.handoff import (
    _runtime_test_outcomes,
    _validate_target_resource_ids,
    validate_handoff,
)
from catalog_acceptance.handoff_cli import main as handoff_cli_main
from catalog_acceptance.manifest import (
    category_slug,
    identity_is_valid,
    load_json,
    validate_seed,
)
from catalog_acceptance.models.contracts import CatalogItem, FULL_ACCEPTANCE_CHECKS


def _validate(schema: dict, instance: object) -> None:
    """Validate one instance with strict format checking."""
    Draft202012Validator(schema, format_checker=FormatChecker()).validate(instance)


def test_contract_schemas_are_valid(repo_root: Path) -> None:
    """Require every checked-in JSON Schema to be a valid Draft 2020-12 schema.

    The count is asserted because this guard has no offender list to be empty: if the
    glob stops matching, every schema in the workshop goes unchecked and the test still
    reports green.
    """
    contracts = repo_root / "workshop" / "contracts"
    checked = 0
    for path in sorted(contracts.glob("*.schema.json")):
        Draft202012Validator.check_schema(load_json(path))
        checked += 1
    assert checked >= 35, (
        f"only {checked} contract schemas were validated; the workshop has many more, "
        "so this guard is not running against the real contracts directory"
    )


def test_catalog_and_manifest_match_schemas(repo_root: Path) -> None:
    """Require the canonical corpus and manifest to match their public schemas."""
    contracts = repo_root / "workshop" / "contracts"
    data = repo_root / "data"
    _validate(load_json(contracts / "catalog.schema.json"), load_json(data / "catalog.json"))
    _validate(
        load_json(contracts / "seed-manifest.schema.json"),
        load_json(data / "manifest.json"),
    )
    _validate(
        load_json(contracts / "database-contract.schema.json"),
        load_json(contracts / "database-contract.json"),
    )


def test_handoff_example_matches_schema(repo_root: Path) -> None:
    """Require the participant handoff example to remain schema-valid."""
    contracts = repo_root / "workshop" / "contracts"
    _validate(
        load_json(contracts / "modernization-contract.schema.json"),
        load_json(contracts / "modernization-contract.example.json"),
    )
    _validate(
        load_json(contracts / "telemetry-evidence.schema.json"),
        load_json(contracts / "telemetry-evidence.example.json"),
    )


def test_challenge_path_registry_is_complete(repo_root: Path) -> None:
    """Freeze all six Challenge 1 slices on one target and exact path protocol."""
    contracts = repo_root / "workshop" / "contracts"
    registry = load_json(contracts / "challenge-paths.json")
    schema = load_json(contracts / "challenge-paths.schema.json")
    _validate(schema, registry)
    assert registry["sharedChallenge"] == "challenges/ch01/README.md"
    assert registry["sharedTarget"] == {
        "infrastructure": "infra/main.bicep",
        "migrationCommand": "catalog-migrate",
        "handoffRenderCommand": (
            "catalog-migrate render-handoff --path <path> "
            "--rollback-runbook <path>"
        ),
        "handoffValidationCommand": "python -m catalog_acceptance.handoff_cli",
        "handoffSchema": "workshop/contracts/modernization-contract.schema.json",
        "acceptanceCommand": "python -m catalog_acceptance",
    }
    slices = registry["slices"]
    assert {item["id"] for item in slices} == {
        "manual-dotnet",
        "manual-java",
        "copilot-rewrite-dotnet",
        "copilot-rewrite-java",
        "copilot-modernization-dotnet",
        "copilot-modernization-java",
    }
    by_id = {item["id"]: item for item in slices}
    assert by_id["manual-dotnet"]["tooling"] == []
    assert by_id["manual-java"]["databaseFamily"] == "postgresql-flexible"
    assert by_id["copilot-rewrite-dotnet"]["tooling"] == [
        "github.copilot",
        "github.copilot-chat",
    ]
    assert by_id["copilot-modernization-dotnet"]["tooling"] == [
        "github.copilot",
        "github.copilot-chat",
        "vscjava.migrate-java-to-azure",
    ]
    assert by_id["copilot-modernization-java"]["tooling"] == [
        "github.copilot",
        "github.copilot-chat",
        "vscjava.migrate-java-to-azure",
    ]
    assert {
        (item["challenge"], item["solution"]) for item in slices
    } == {
        (
            f"challenges/ch01-{item['path']}/README.md",
            (
                f"solutions/ch01-{item['path']}/"
                f"{'dotnet' if item['sourcePath'] == 'dotnet' else 'java'}/README.md"
            ),
        )
        for item in slices
    }
    provisioner = (repo_root / "baseInfra/scripts/provision-vm.ps1").read_text(
        encoding="utf-8"
    )
    # The registry above requires the app-modernization extension on BOTH
    # copilot-modernization slices, so the provisioner has to install it whatever
    # $Stack it was handed. Assert it sits in the unconditional $Extensions literal
    # rather than in either arm of the per-stack branch that follows it. Anchoring on
    # the literal keeps this honest even as unrelated $Stack branches come and go
    # elsewhere in the script.
    unconditional, per_stack = provisioner.split("$Extensions = @{", maxsplit=1)[
        1
    ].split("}", maxsplit=1)
    assert "'vscjava.migrate-java-to-azure'" in unconditional
    assert "'vscjava.migrate-java-to-azure'" not in per_stack.split("\n\n", maxsplit=1)[0]


@pytest.mark.parametrize(
    ("field", "invalid_value"),
    [
        ("path", "copilot-rewrite"),
        ("stack", "java-postgresql"),
        ("sourcePath", "java"),
        ("dockerfile", "java/Dockerfile"),
        ("challenge", "challenges/ch01-copilot-rewrite/README.md"),
        ("solution", "solutions/ch01-manual/java/README.md"),
        ("databaseFamily", "postgresql-flexible"),
        ("imageProvider", "azure-blob"),
        ("tooling", ["github.copilot"]),
        (
            "pathEvidence",
            [
                "evidence/characterization.md",
                "evidence/bounded-plan.md",
                "evidence/review-checklist.md",
                "evidence/decision-log.md",
            ],
        ),
    ],
)
def test_challenge_path_registry_rejects_cross_slice_mutations(
    repo_root: Path,
    field: str,
    invalid_value: object,
) -> None:
    """Path, stack, tooling, and evidence relationships cannot drift."""
    contracts = repo_root / "workshop" / "contracts"
    registry = load_json(contracts / "challenge-paths.json")
    schema = load_json(contracts / "challenge-paths.schema.json")
    mutated = deepcopy(registry)
    target = next(item for item in mutated["slices"] if item["id"] == "manual-dotnet")
    target[field] = invalid_value

    with pytest.raises(JsonSchemaValidationError):
        _validate(schema, mutated)


def test_target_and_migration_examples_match_schemas(repo_root: Path) -> None:
    """Require both target stages and database migration paths to remain valid."""
    contracts = repo_root / "workshop" / "contracts"
    target_schema = load_json(contracts / "azure-target-output.schema.json")
    migration_schema = load_json(contracts / "migration-report.schema.json")
    for name in ("bootstrap", "application"):
        target = load_json(contracts / f"azure-target-output.{name}.example.json")
        _validate(
            target_schema,
            target,
        )
        _validate_target_resource_ids(target)
    for name in ("sql", "postgresql"):
        _validate(
            migration_schema,
            load_json(contracts / f"migration-report.{name}.example.json"),
        )
    _validate(
        load_json(contracts / "migration-cli-contract.schema.json"),
        load_json(contracts / "migration-cli-contract.json"),
    )
    _validate(
        load_json(contracts / "migration-error.schema.json"),
        load_json(contracts / "migration-error.example.json"),
    )
    operation_schema = load_json(
        contracts / "migration-operation-result.schema.json"
    )
    sql_import = load_json(
        contracts / "migration-operation-result.example.json"
    )
    sql_export = json.loads(json.dumps(sql_import))
    sql_export.update(command="sql export", target=None)
    postgresql_report = load_json(
        contracts / "migration-report.postgresql.example.json"
    )
    postgresql_target = {
        "kind": "database",
        **{
            key: postgresql_report["targetDatabase"][key]
            for key in (
                "resourceId",
                "family",
                "authentication",
                "localAdministratorPrincipal",
                "entraAdministratorPrincipal",
                "applicationPrincipal",
            )
        },
    }
    postgresql_import = json.loads(json.dumps(sql_import))
    postgresql_import.update(
        command="postgresql import",
        target=postgresql_target,
        artifact=postgresql_report["databaseArtifact"],
    )
    postgresql_export = json.loads(json.dumps(postgresql_import))
    postgresql_export.update(command="postgresql export", target=None)
    images_copy = json.loads(json.dumps(sql_import))
    images_copy.update(
        command="images copy",
        target={
            "kind": "images",
            "resourceId": postgresql_report["images"]["resourceId"],
            "provider": postgresql_report["images"]["provider"],
        },
        artifact=None,
        imageVerification=postgresql_report["images"]["verification"],
    )
    for result in (
        sql_export,
        sql_import,
        postgresql_export,
        postgresql_import,
        images_copy,
    ):
        _validate(operation_schema, result)


def test_migration_cli_surface_is_exact(repo_root: Path) -> None:
    """Freeze command names, exit codes, and non-destructive safety boundaries."""
    contract = load_json(
        repo_root / "workshop" / "contracts" / "migration-cli-contract.json"
    )
    assert [command["name"] for command in contract["commands"]] == [
        "sql export",
        "sql import",
        "postgresql export",
        "postgresql import",
        "images copy",
        "verify",
        "render-handoff",
    ]
    assert [item["code"] for item in contract["exitCodes"]] == [0, 2, 3, 4, 5]
    assert contract["safety"] == {
        "sourceReadOnly": True,
        "refuseNonemptyTarget": True,
        "requireExactTargetConfirmation": True,
        "requireSourceCommitMatch": True,
        "argumentsAreExact": True,
        "deriveTargetSettingsFromTargetOutput": True,
        "secretInputsFromEnvironmentOnly": True,
        "sqlPackagePasswordTransport": "protected-transient-response-file",
        "protectedSecretFilesRemoved": True,
        "tokensInChildProcessEnvironmentOnly": True,
        "rejectUndeclaredSecrets": True,
        "stripMigrationSecretsFromChildEnvironment": True,
        "validateTargetResourceRelationships": True,
        "validateSourceDatabaseContract": True,
        "validateTargetDatabaseContract": True,
        "hashTargetImageBytes": True,
        "verifyCommitTagDigest": True,
        "requireDistinctRetainedRollbackRevision": True,
        "jsonForEveryFailure": True,
        "resourceDeletionSupported": False,
    }
    assert contract["migrationExecution"] == {
        "host": "source-vm",
        "sourceVmResourceIdSource": (
            "target-output.network.migrationSourceVmResourceId"
        ),
        "sourceVirtualNetworkResourceIdSource": (
            "target-output.network.migrationSourceVirtualNetworkResourceId"
        ),
        "hostIdentityEndpoint": (
            "http://169.254.169.254/metadata/instance/compute/resourceId"
            "?api-version=2021-02-01&format=text"
        ),
        "hostIdentityHeader": "Metadata:true",
        "requireHostIdentityMatch": True,
        "sourceVmNicCommand": (
            "az vm show --ids <sourceVmResourceId> --subscription <subscriptionId> "
            "--query networkProfile.networkInterfaces[].id --output tsv"
        ),
        "sourceNicSubnetCommand": (
            "az network nic show --ids <nicResourceId> "
            "--subscription <subscriptionId> "
            "--query ipConfigurations[].subnet.id --output tsv"
        ),
        "resourceStateCommand": (
            "az resource show --ids <resourceId> --subscription <subscriptionId> "
            "--query properties.provisioningState --output tsv"
        ),
        "peeringStateCommand": (
            "az network vnet peering show --resource-group <resourceGroup> "
            "--vnet-name <virtualNetworkName> --name <peeringName> "
            "--subscription <subscriptionId> "
            "--query {provisioningState:provisioningState,"
            "peeringState:peeringState,"
            "remoteVirtualNetworkId:remoteVirtualNetwork.id} --output json"
        ),
        "privateDnsLinkStateCommand": (
            "az network private-dns link vnet show "
            "--resource-group <resourceGroup> "
            "--zone-name <privateDnsZoneName> --name <linkName> "
            "--subscription <subscriptionId> "
            "--query {provisioningState:provisioningState,"
            "virtualNetworkId:virtualNetwork.id,"
            "registrationEnabled:registrationEnabled} --output json"
        ),
        "requiredProvisioningState": "Succeeded",
        "requiredPeeringState": "Connected",
        "requiredPrivateDnsRegistrationEnabled": False,
        "requireSourceSubnetOwnership": True,
        "requireReciprocalPeeringTargets": True,
        "requirePrivateDnsSourceVnetTargets": True,
        "requiresBidirectionalVnetPeering": True,
        "requiresPrivateDnsZoneLinks": True,
    }
    assert contract["releaseVerification"] == {
        "azureCliConfigDirectory": "$HOME/.azure-365",
        "applicationRevisionSequence": ["baseline", "release"],
        "sameContainerImageForBaselineAndRelease": True,
        "handoffTargetOutputRole": "release",
        "rollbackRevisionRole": "baseline",
        "containerImageCommand": (
            "az acr manifest show-metadata --registry <registryName> "
            "--name <repository>:<tag> --subscription <subscriptionId> "
            "--query digest --output tsv"
        ),
        "rollbackRevisionCommand": (
            "az containerapp revision show --resource-group <resourceGroup> "
            "--name <containerAppName> --revision <rollbackRevision> "
            "--subscription <subscriptionId> "
            "--query {active:properties.active,"
            "health:properties.healthState,"
            "error:properties.provisioningError,"
            "images:properties.template.containers[].image} --output json"
        ),
        "requiredRollbackHealthState": "Healthy",
        "requiredRollbackActive": False,
        "requiredRollbackContainerCount": 1,
        "requiredRollbackRevisionTemplate": (
            "<containerAppName>--baseline-<sourceCommitPrefix12>"
        ),
        "rollbackImageReferenceTemplate": "<loginServer>/<repository>@<digest>",
    }
    mutating = {
        command["name"]
        for command in contract["commands"]
        if command["mutatesTarget"]
    }
    assert mutating == {"sql import", "postgresql import", "images copy"}
    commands = {command["name"]: command for command in contract["commands"]}
    assert {
        name: command["requiredTargetOutputStage"]
        for name, command in commands.items()
    } == {
        "sql export": "bootstrap",
        "sql import": "bootstrap",
        "postgresql export": "bootstrap",
        "postgresql import": "bootstrap",
        "images copy": "bootstrap",
        "verify": "bootstrap",
        "render-handoff": "application",
    }
    assert "--target-output" in commands["sql import"]["arguments"]
    assert "--target-output" in commands["postgresql import"]["arguments"]
    for name in (
        "sql export",
        "sql import",
        "postgresql export",
        "postgresql import",
        "images copy",
        "verify",
    ):
        assert "--source-commit" in commands[name]["arguments"]
    assert contract["safety"]["requireSourceCommitMatch"] is True
    assert "--application-username" not in commands["postgresql import"][
        "arguments"
    ]
    assert "--target-authentication" not in commands["postgresql import"][
        "arguments"
    ]
    assert commands["postgresql import"]["requiredSecretEnvironment"] == [
        "MIGRATION_TARGET_ADMINISTRATOR_PASSWORD"
    ]
    assert commands["postgresql import"][
        "secretEnvironmentByTargetAuthentication"
    ]["managed-identity"] == {
        "required": [],
        "forbidden": ["MIGRATION_TARGET_APPLICATION_PASSWORD"],
    }
    assert contract["postgresqlManagedIdentityBootstrap"] == {
        "administratorSource": (
            "target-output.database.entraAdministratorPrincipal"
        ),
        "administratorPrincipalType": "user",
        "azureCliConfigDirectory": "$HOME/.azure-365",
        "azureCliPrincipalCommand": "az ad signed-in-user show",
        "tokenCommand": (
            "az account get-access-token --resource-type oss-rdbms"
        ),
        "tokenProcessEnvironment": "PGPASSWORD",
        "principalCreationDatabase": "postgres",
        "principalCreationFunction": (
            "pg_catalog.pgaadauth_create_principal_with_oid"
        ),
        "applicationPrincipalNameSource": (
            "target-output.database.applicationPrincipal.name"
        ),
        "applicationPrincipalObjectIdSource": (
            "target-output.workloadIdentity.principalId"
        ),
        "applicationPrincipalObjectType": "service",
        "applicationPrincipalIsAdmin": False,
        "applicationPrincipalIsMfa": False,
    }
    assert commands["verify"]["resultSchema"] == "migration-report.schema.json"
    assert (
        commands["render-handoff"]["resultSchema"]
        == "modernization-contract.schema.json"
    )
    assert "--rollback-revision" in commands["render-handoff"]["arguments"]
    assert "--path" in commands["render-handoff"]["arguments"]
    assert "--rollback-runbook" in commands["render-handoff"]["arguments"]
    assert contract["failureProtocol"] == {
        "schema": "migration-error.schema.json",
        "outputChannel": "stderr",
        "exactlyOneDocument": True,
        "tracebackForbidden": True,
        "secretValuesForbidden": True,
    }
    assert contract["sqlServerLegacyPrincipalCleanup"] == {
        "principalName": "catalog",
        "privilegedRole": "db_owner",
        "requiredBeforeApplicationPrincipalCreation": True,
        "verifyAbsent": True,
    }
    assert contract["schemaVersion"] == "1.4.0"
    assert contract["safety"]["secretInputsFromEnvironmentOnly"] is True
    assert (
        contract["safety"]["sqlPackagePasswordTransport"]
        == "protected-transient-response-file"
    )
    assert contract["safety"]["protectedSecretFilesRemoved"] is True

    schema = load_json(
        repo_root
        / "workshop"
        / "contracts"
        / "migration-cli-contract.schema.json"
    )
    invalid = json.loads(json.dumps(contract))
    invalid["commands"][1]["arguments"] = ["--execute"]
    with pytest.raises(JsonSchemaValidationError):
        _validate(schema, invalid)
    invalid = json.loads(json.dumps(contract))
    invalid["commands"][3]["requiredSecretEnvironment"] = []
    with pytest.raises(JsonSchemaValidationError):
        _validate(schema, invalid)
    invalid = json.loads(json.dumps(contract))
    invalid["migrationExecution"]["requireHostIdentityMatch"] = False
    with pytest.raises(JsonSchemaValidationError):
        _validate(schema, invalid)
    invalid = json.loads(json.dumps(contract))
    invalid["releaseVerification"]["rollbackImageReferenceTemplate"] = "<tag>"
    with pytest.raises(JsonSchemaValidationError):
        _validate(schema, invalid)


def test_migration_error_protocol_is_exact(repo_root: Path) -> None:
    """Require typed, single-line failures with stable exit-code mappings."""
    contracts = repo_root / "workshop" / "contracts"
    schema = load_json(contracts / "migration-error.schema.json")
    example = load_json(contracts / "migration-error.example.json")
    _validate(schema, example)

    invalid_cases = []
    wrong_exit = json.loads(json.dumps(example))
    wrong_exit["exitCode"] = 4
    invalid_cases.append(wrong_exit)
    multiline = json.loads(json.dumps(example))
    multiline["error"]["message"] = "first line\nsecret traceback"
    invalid_cases.append(multiline)
    traceback = json.loads(json.dumps(example))
    traceback["traceback"] = "forbidden"
    invalid_cases.append(traceback)
    unknown_command = json.loads(json.dumps(example))
    unknown_command["command"] = "destroy"
    invalid_cases.append(unknown_command)

    for invalid in invalid_cases:
        with pytest.raises(JsonSchemaValidationError):
            _validate(schema, invalid)


def test_contracts_reject_incompatible_modes(repo_root: Path) -> None:
    """Reject placeholder apps, SQL passwords, and mismatched storage authentication."""
    contracts = repo_root / "workshop" / "contracts"
    target_schema = load_json(contracts / "azure-target-output.schema.json")
    bootstrap = load_json(contracts / "azure-target-output.bootstrap.example.json")
    invalid_bootstrap = json.loads(json.dumps(bootstrap))
    invalid_bootstrap["application"] = {
        "resourceId": "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/rg-mh-dotnet-example/providers/Microsoft.App/containerApps/placeholder",
        "url": "https://placeholder.example.invalid",
        "healthUrl": "https://placeholder.example.invalid/healthz",
        "readinessUrl": "https://placeholder.example.invalid/readyz",
        "containerAppName": "placeholder",
        "revisionName": "placeholder--000001",
    }
    with pytest.raises(JsonSchemaValidationError):
        _validate(target_schema, invalid_bootstrap)

    invalid_sql_auth = json.loads(json.dumps(bootstrap))
    invalid_sql_auth["database"]["authentication"] = "password-secret"
    with pytest.raises(JsonSchemaValidationError):
        _validate(target_schema, invalid_sql_auth)

    invalid_blob_auth = json.loads(json.dumps(bootstrap))
    invalid_blob_auth["images"]["authentication"] = "aca-volume-secret"
    with pytest.raises(JsonSchemaValidationError):
        _validate(target_schema, invalid_blob_auth)

    invalid_scope = json.loads(json.dumps(bootstrap))
    invalid_scope["workloadIdentity"]["resourceId"] = (
        "/subscriptions/00000000-0000-0000-0000-000000000000/"
        "resourceGroups/rg-other/providers/Microsoft.ManagedIdentity/"
        "userAssignedIdentities/id-mh-dotnet-example"
    )
    with pytest.raises(ValueError, match="outside the declared scope"):
        _validate_target_resource_ids(invalid_scope)

    invalid_type = json.loads(json.dumps(bootstrap))
    invalid_type["network"]["virtualNetworkResourceId"] = bootstrap["database"][
        "resourceId"
    ]
    with pytest.raises(JsonSchemaValidationError):
        _validate(target_schema, invalid_type)

    invalid_source_type = json.loads(json.dumps(bootstrap))
    invalid_source_type["network"]["migrationSourceVmResourceId"] = bootstrap[
        "network"
    ]["migrationSourceVirtualNetworkResourceId"]
    with pytest.raises(JsonSchemaValidationError):
        _validate(target_schema, invalid_source_type)

    invalid_stack_vm = json.loads(json.dumps(bootstrap))
    invalid_stack_vm["network"]["migrationSourceVmResourceId"] = (
        "/subscriptions/00000000-0000-0000-0000-000000000000/"
        "resourceGroups/rg-mh-source-example/providers/Microsoft.Compute/"
        "virtualMachines/vm-java-user001"
    )
    with pytest.raises(JsonSchemaValidationError):
        _validate(target_schema, invalid_stack_vm)

    same_network = json.loads(json.dumps(bootstrap))
    same_network["network"]["migrationSourceVirtualNetworkResourceId"] = same_network[
        "network"
    ]["virtualNetworkResourceId"]
    same_network["network"]["migrationSourceVmResourceId"] = (
        "/subscriptions/00000000-0000-0000-0000-000000000000/"
        "resourceGroups/rg-mh-dotnet-example/providers/Microsoft.Compute/"
        "virtualMachines/vm-dotnet-user001"
    )
    with pytest.raises(ValueError, match="networks must differ"):
        _validate_target_resource_ids(same_network)

    invalid_host = json.loads(json.dumps(bootstrap))
    invalid_host["database"]["server"] = "sql-mh-dotnet-example.attacker.invalid"
    with pytest.raises(JsonSchemaValidationError):
        _validate(target_schema, invalid_host)

    invalid_location = json.loads(json.dumps(bootstrap))
    invalid_location["location"] = "northeurope"
    with pytest.raises(JsonSchemaValidationError):
        _validate(target_schema, invalid_location)

    invalid_principal = json.loads(json.dumps(bootstrap))
    invalid_principal["database"]["applicationPrincipal"]["principalId"] = (
        "00000000-0000-0000-0000-000000000099"
    )
    with pytest.raises(ValueError, match="principal differs"):
        _validate_target_resource_ids(invalid_principal)

    application = load_json(
        contracts / "azure-target-output.application.example.json"
    )
    baseline = json.loads(json.dumps(application))
    baseline["applicationRevisionRole"] = "baseline"
    baseline["application"]["revisionName"] = baseline["application"][
        "revisionName"
    ].replace("--release-", "--baseline-")
    _validate(target_schema, baseline)
    _validate_target_resource_ids(baseline)

    missing_revision_role = json.loads(json.dumps(application))
    missing_revision_role.pop("applicationRevisionRole")
    with pytest.raises(JsonSchemaValidationError):
        _validate(target_schema, missing_revision_role)
    invalid_endpoint = json.loads(json.dumps(application))
    invalid_endpoint["application"]["url"] = "https://unrelated.example.invalid"
    invalid_endpoint["application"]["healthUrl"] = (
        "https://unrelated.example.invalid/healthz"
    )
    invalid_endpoint["application"]["readinessUrl"] = (
        "https://unrelated.example.invalid/readyz"
    )
    with pytest.raises(ValueError, match="URL differs"):
        _validate_target_resource_ids(invalid_endpoint)

    invalid_revision = json.loads(json.dumps(application))
    invalid_revision["application"]["revisionName"] = "unrelated--revision"
    with pytest.raises(ValueError, match="revision differs"):
        _validate_target_resource_ids(invalid_revision)

    managed_identity_postgresql = json.loads(json.dumps(application))
    managed_identity_postgresql["database"]["authentication"] = (
        "managed-identity"
    )
    managed_identity_postgresql["database"]["applicationPrincipal"] = {
        "name": "id-mh-java-example",
        "kind": "managed-identity",
        "principalId": "00000000-0000-0000-0000-000000000002",
    }
    _validate(target_schema, managed_identity_postgresql)
    _validate_target_resource_ids(managed_identity_postgresql)
    missing_entra_administrator = json.loads(
        json.dumps(managed_identity_postgresql)
    )
    missing_entra_administrator["database"]["entraAdministratorPrincipal"] = (
        None
    )
    with pytest.raises(JsonSchemaValidationError):
        _validate(target_schema, missing_entra_administrator)

    migration_schema = load_json(contracts / "migration-report.schema.json")
    invalid_migration = load_json(contracts / "migration-report.sql.example.json")
    invalid_migration["databaseArtifact"]["exportTool"]["name"] = "pg_dump"
    with pytest.raises(JsonSchemaValidationError):
        _validate(migration_schema, invalid_migration)
    invalid_migration = load_json(contracts / "migration-report.sql.example.json")
    invalid_migration["sourceDatabase"]["engineVersion"] = "1999"
    with pytest.raises(JsonSchemaValidationError):
        _validate(migration_schema, invalid_migration)

    operation_schema = load_json(
        contracts / "migration-operation-result.schema.json"
    )
    invalid_operation = load_json(
        contracts / "migration-operation-result.example.json"
    )
    invalid_operation["artifact"] = load_json(
        contracts / "migration-report.postgresql.example.json"
    )["databaseArtifact"]
    with pytest.raises(JsonSchemaValidationError):
        _validate(operation_schema, invalid_operation)
    invalid_operation = load_json(
        contracts / "migration-operation-result.example.json"
    )
    invalid_operation["target"]["resourceId"] = (
        load_json(contracts / "migration-report.postgresql.example.json")[
            "targetDatabase"
        ]["resourceId"]
    )
    with pytest.raises(JsonSchemaValidationError):
        _validate(operation_schema, invalid_operation)

    handoff_schema = load_json(contracts / "modernization-contract.schema.json")
    invalid_handoff = load_json(contracts / "modernization-contract.example.json")
    invalid_handoff["authentication"]["database"] = "password-secret"
    with pytest.raises(JsonSchemaValidationError):
        _validate(handoff_schema, invalid_handoff)
    invalid_handoff = load_json(contracts / "modernization-contract.example.json")
    invalid_handoff["application"]["region"] = "northeurope"
    with pytest.raises(JsonSchemaValidationError):
        _validate(handoff_schema, invalid_handoff)
    invalid_handoff = load_json(contracts / "modernization-contract.example.json")
    invalid_handoff["deployment"]["mechanism"] = "terraform"
    invalid_handoff["deployment"]["iacPath"] = "infra/aca"
    with pytest.raises(JsonSchemaValidationError):
        _validate(handoff_schema, invalid_handoff)
    invalid_handoff = load_json(contracts / "modernization-contract.example.json")
    invalid_handoff["database"]["migrationMechanism"] = "unrelated"
    invalid_handoff["database"]["migrationVersion"] = "999"
    with pytest.raises(JsonSchemaValidationError):
        _validate(handoff_schema, invalid_handoff)
    invalid_handoff = load_json(contracts / "modernization-contract.example.json")
    invalid_handoff["path"] = "manual"
    with pytest.raises(JsonSchemaValidationError):
        _validate(handoff_schema, invalid_handoff)
    invalid_handoff = load_json(contracts / "modernization-contract.example.json")
    invalid_handoff["sliceId"] = "manual-dotnet"
    with pytest.raises(JsonSchemaValidationError):
        _validate(handoff_schema, invalid_handoff)
    invalid_handoff = load_json(contracts / "modernization-contract.example.json")
    invalid_handoff["evidence"]["pathEvidence"][0] = "evidence/unrelated.md"
    with pytest.raises(JsonSchemaValidationError):
        _validate(handoff_schema, invalid_handoff)


def test_sanitized_fixtures_cover_atomic_rejection_inputs(repo_root: Path) -> None:
    """Require valid prefixes followed by either frozen invalid record to fail."""
    contracts = repo_root / "workshop" / "contracts"
    fixtures = repo_root / "tests" / "acceptance" / "fixtures"
    _validate(
        load_json(contracts / "catalog.schema.json"),
        load_json(fixtures / "catalog.valid.json"),
    )
    mixed_items = load_json(fixtures / "catalog.invalid.json")
    CatalogItem.model_validate(mixed_items[0])
    with pytest.raises(ValidationError):
        CatalogItem.model_validate(mixed_items[1])
    empty_slug_items = load_json(fixtures / "catalog.invalid-empty-slug.json")
    CatalogItem.model_validate(empty_slug_items[0])
    with pytest.raises(ValidationError):
        CatalogItem.model_validate(empty_slug_items[1])


def test_normalization_vectors(repo_root: Path) -> None:
    """Require Python normalization to match every cross-runtime vector."""
    vectors = load_json(
        repo_root / "workshop" / "contracts" / "normalization-vectors.json"
    )
    for vector in vectors["vectors"]:
        assert category_slug(vector["input"]) == vector["expected"]
    for vector in vectors["invalidVectors"]:
        assert category_slug(vector["input"]) == ""


def test_text_validation_vectors(repo_root: Path) -> None:
    """Require storage-safe text vectors to pass or fail exactly."""
    vectors = load_json(
        repo_root / "workshop" / "contracts" / "text-validation-vectors.json"
    )
    base = {
        "productId": "10000000-0000-4000-8000-000000000099",
        "name": "Contract Figure",
        "description": "A representative figure used for text validation.",
        "category": "Contract Figures",
        "filename": "10000000-0000-4000-8000-000000000099.png",
        "imagePrompt": "Photorealistic construction-toy figure on a clean background.",
    }
    for vector in vectors["vectors"]:
        candidate = dict(base)
        candidate[vector["field"]] = vector["fragment"] * vector["repeat"]
        if vector["valid"]:
            CatalogItem.model_validate(candidate)
        else:
            with pytest.raises(ValidationError):
                CatalogItem.model_validate(candidate)


def test_runtime_evidence_schema_freezes_requirement_names(repo_root: Path) -> None:
    """Reject a passing but unrelated native test name."""
    contracts = repo_root / "workshop" / "contracts"
    evidence = load_json(contracts / "runtime-test-evidence.example.json")
    evidence["tests"][0]["testName"] = "Contract.Unrelated.Passes"
    with pytest.raises(JsonSchemaValidationError):
        _validate(
            load_json(contracts / "runtime-test-evidence.schema.json"),
            evidence,
        )
    duplicate = load_json(contracts / "runtime-test-evidence.example.json")
    duplicate["tests"] = [duplicate["tests"][0]] * 14
    with pytest.raises(JsonSchemaValidationError):
        _validate(
            load_json(contracts / "runtime-test-evidence.schema.json"),
            duplicate,
        )
    unqualified = load_json(contracts / "runtime-test-evidence.example.json")
    unqualified["tests"][0]["testIdentity"] = "UnqualifiedTest"
    with pytest.raises(JsonSchemaValidationError):
        _validate(
            load_json(contracts / "runtime-test-evidence.schema.json"),
            unqualified,
        )


def test_junit_runtime_evidence_uses_class_and_display_name(tmp_path: Path) -> None:
    """Bind JUnit evidence to its package-qualified class and display name."""
    reports = tmp_path / "surefire-reports"
    reports.mkdir()
    name = "Contract.Telemetry.FinalResponseStatus"
    class_name = "com.microsoft.microhack.catalog.TelemetryContractTest"
    (reports / "TEST-telemetry.xml").write_text(
        (
            "<testsuite>"
            f'<testcase name="{name}" classname="{class_name}" />'
            "</testsuite>"
        ),
        encoding="utf-8",
    )

    assert _runtime_test_outcomes(reports, "junit") == {
        (name, f"{class_name}#{name}"): ["passed"]
    }


def test_identity_vectors(repo_root: Path) -> None:
    """Require identity validation to match every cross-runtime vector."""
    vectors = load_json(
        repo_root / "workshop" / "contracts" / "identity-vectors.json"
    )
    for vector in vectors["vectors"]:
        assert (
            identity_is_valid(vector["productId"], vector["filename"])
            is vector["valid"]
        )


def test_canonical_seed_manifest(repo_root: Path) -> None:
    """Require all 198 records, 20 categories, and 198 images to match the manifest."""
    manifest = validate_seed(repo_root / "data")
    assert manifest.counts.figures == 198
    assert manifest.counts.categories == 20
    assert manifest.counts.images == 198


def test_behavior_contract_has_unique_routes(repo_root: Path) -> None:
    """Require the frozen route table to avoid ambiguous method/path pairs."""
    behavior = load_json(
        repo_root / "workshop" / "contracts" / "behavior-contract.json"
    )
    routes = [(route["method"], route["path"]) for route in behavior["routes"]]
    assert len(routes) == len(set(routes))
    assert behavior["performance"]["apiKeyEnvironmentVariable"] == "PERFTEST_API_KEY"


def test_toolchain_matrix_is_exact(repo_root: Path) -> None:
    """Require source/target runtimes and modernization extension versions to be pinned."""
    toolchain = load_json(repo_root / "workshop" / "toolchain.lock.json")
    _validate(
        load_json(repo_root / "workshop" / "contracts" / "toolchain-lock.schema.json"),
        toolchain,
    )
    assert toolchain["runtimes"]["dotnet"]["sourceSdk"] == "8.0.424"
    assert toolchain["runtimes"]["dotnet"]["targetSdk"] == "10.0.400"
    assert toolchain["runtimes"]["java"]["sourceSpringBoot"] == "3.5.16"
    assert toolchain["runtimes"]["java"]["targetSpringBoot"] == "4.0.7"
    assert toolchain["applicationContainers"]["dotnetBuild"] == {
        "image": (
            "mcr.microsoft.com/dotnet/sdk:"
            "10.0.400-azurelinux3.0-amd64"
        ),
        "digest": (
            "sha256:679e7b7e9d0315ad34438bee49b4fb0658c4c42a3aa08ae8557d1bd03f49c28b"
        ),
        "platform": "linux/amd64",
        "runtimeVersion": "10.0.11",
    }
    assert toolchain["applicationContainers"]["dotnetRuntime"] == {
        "image": (
            "mcr.microsoft.com/dotnet/aspnet:"
            "10.0.11-azurelinux3.0-amd64"
        ),
        "digest": (
            "sha256:d21a49ce9556f5e50afc5a33cc45ec7a40b5739f10397368810193666e559a79"
        ),
        "platform": "linux/amd64",
        "runtimeVersion": "10.0.11",
    }
    assert toolchain["applicationContainers"]["javaBuildRuntime"] == {
        "image": "mcr.microsoft.com/openjdk/jdk:21-azurelinux",
        "digest": (
            "sha256:06ec8d4b09883cb695aa37e3ae85d1188f124b6dbcfeff97eeb09a926f7c389f"
        ),
        "platform": "linux/amd64",
        "runtimeVersion": "21.0.12+8",
    }
    assert toolchain["hosts"]["workshopVm"]["azureImage"]["version"] != "latest"
    assert toolchain["databases"]["sqlserver"]["client"]["installer"]["version"] == "1.7.0"
    assert toolchain["provisioning"]["mutableRefsForbidden"] is True
    assert "{commitSha}" in toolchain["provisioning"]["sourceArchiveTemplate"]
    assert toolchain["databases"]["sqlserver"]["localContainer"][
        "indexDigest"
    ].startswith("sha256:")
    assert toolchain["databases"]["postgresql"]["localContainer"][
        "indexDigest"
    ].startswith("sha256:")
    assert toolchain["tools"]["sqlPackage"]["version"] == "170.4.83"
    assert toolchain["tools"]["git"] == {
        "version": "2.55.0.windows.5",
        "architecture": "x64",
        "url": (
            "https://github.com/git-for-windows/git/releases/download/"
            "v2.55.0.windows.5/Git-2.55.0.5-64-bit.exe"
        ),
        "sha256": (
            "d065a4e23c3d9a6b5073d609b5be0830"
            "227ec3ca053c083ba385061ddfaf94c6"
        ),
        "signaturePublisher": "Johannes Schindelin",
    }
    assert toolchain["schemaVersion"] == "1.2.0"
    assert toolchain["tools"]["sqlPackage"]["windowsStandalone"] == {
        "version": "170.4.83.3",
        "architecture": "x64",
        "url": (
            "https://download.microsoft.com/download/"
            "46a13f8c-5548-42fb-b547-7e69ebc3fcca/"
            "sqlpackage-win-x64-en-170.4.83.3.zip"
        ),
        "sha256": (
            "f1c80c38a6c4e55fe2b8787de9119ee5"
            "2313b900a05873be9d0084102344666a"
        ),
        "signaturePublisher": "Microsoft Corporation",
    }
    assert toolchain["azureSdk"]["dotnet"]["azureIdentity"]["version"] == "1.21.0"
    assert (
        toolchain["azureSdk"]["dotnet"]["azureStorageBlobs"]["version"] == "12.29.1"
    )
    assert toolchain["azureSdk"]["dotnet"][
        "azureMonitorOpenTelemetryExporter"
    ] == {
        "package": "Azure.Monitor.OpenTelemetry.Exporter",
        "version": "1.8.3",
        "source": (
            "https://www.nuget.org/packages/"
            "Azure.Monitor.OpenTelemetry.Exporter/1.8.3"
        ),
        "sha512": (
            "hZ35hXxiRuJcT67u970iqqJ+z2ol3Sg23/m1wwNNh8uzK/"
            "48uB9iJ3va9PQ7gXn6kij6wzowUe5olPPfObkEug=="
        ),
        "integrity": "NuGet repository signature and package SHA-512 are required",
    }
    assert toolchain["azureSdk"]["java"]["azureIdentity"]["version"] == "1.18.4"
    assert (
        toolchain["azureSdk"]["java"]["azureStorageBlob"]["version"] == "12.35.1"
    )
    assert (
        toolchain["azureSdk"]["java"]["azureIdentityExtensions"]["version"]
        == "1.2.9"
    )
    assert toolchain["azureSdk"]["java"][
        "azureMonitorOpenTelemetryAutoconfigure"
    ]["version"] == "1.6.0"
    assert toolchain["azureSdk"]["java"]["openTelemetryApi"]["version"] == "1.58.0"
    assert toolchain["azureSdk"]["java"]["openTelemetryLogbackAppender"][
        "version"
    ] == "2.24.0-alpha"
    assert toolchain["azureSdk"]["java"]["azureIdentity"]["sha256"] == (
        "fd947ab1d6b1a8519d377e8509f34fdf70215aaa11e84826dbe017e962acb2a0"
    )
    assert toolchain["azureSdk"]["java"]["azureStorageBlob"]["sha256"] == (
        "087bd34819f9d443cb9f745318e38548d5377f664959481f8acffa72f194e7d0"
    )
    assert toolchain["azureSdk"]["java"]["azureIdentityExtensions"]["sha256"] == (
        "38193a31810c64e0f7b7daf69f82b2cfd0425bd0a0c9f1ebede380a0dae7114e"
    )
    assert toolchain["azureSdk"]["java"][
        "azureMonitorOpenTelemetryAutoconfigure"
    ]["sha256"] == (
        "287a594fea0f2ad6bbb280c92d57f63f6e5917cd838b9a46e57e33e207763b28"
    )
    assert toolchain["databases"]["postgresql"]["migrationTools"] == {
        "exportTool": "pg_dump",
        "importTool": "pg_restore",
        "version": "18.6",
        "source": "bundled-with-postgresql-installer",
    }
    operation_defs = load_json(
        repo_root
        / "workshop"
        / "contracts"
        / "migration-operation-result.schema.json"
    )["$defs"]
    assert operation_defs["sqlArtifact"]["allOf"][1]["properties"][
        "exportTool"
    ]["properties"]["version"]["const"] == toolchain["tools"]["sqlPackage"][
        "version"
    ]
    assert operation_defs["postgresqlArtifact"]["allOf"][1]["properties"][
        "exportTool"
    ]["properties"]["version"]["const"] == toolchain["databases"][
        "postgresql"
    ]["migrationTools"]["version"]
    for container in toolchain["applicationContainers"].values():
        assert container["platform"] == "linux/amd64"
        assert container["digest"].startswith("sha256:")
        assert ":latest" not in container["image"]
    assert toolchain["extensions"]["vscjava.migrate-java-to-azure"]
    assert toolchain["extensions"]["vscjava.vscode-java-upgrade"]
    assert toolchain["extensions"]["ms-dotnettools.vscode-dotnet-modernize"]
    assert toolchain["extensions"]["ms-dotnettools.upgrade-agent"]


def test_handoff_bundle_cross_file_consistency(
    repo_root: Path, tmp_path: Path
) -> None:
    """Require handoff, acceptance, and telemetry evidence to agree."""
    contracts = repo_root / "workshop" / "contracts"
    handoff = load_json(contracts / "modernization-contract.example.json")
    evidence = tmp_path / "evidence"
    evidence.mkdir()
    iac_directory = tmp_path / "infra"
    iac_directory.mkdir(parents=True)
    (iac_directory / "main.bicep").write_text(
        "metadata contractFixture = true\n",
        encoding="utf-8",
    )
    data_directory = tmp_path / "data"
    data_directory.mkdir()
    (data_directory / "manifest.json").write_text(
        (repo_root / "data" / "manifest.json").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    (evidence / "rollback-runbook.md").write_text(
        "rollback fixture\n",
        encoding="utf-8",
    )
    for relative_path in handoff["evidence"]["pathEvidence"]:
        path = tmp_path / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("path evidence fixture\n", encoding="utf-8")
    runtime_example = load_json(contracts / "runtime-test-evidence.example.json")
    runtime_results = "\n".join(
        f'<UnitTestResult testId="runtime-{index}" '
        f'testName="{test["testName"]}" outcome="Passed" />'
        for index, test in enumerate(runtime_example["tests"])
    )
    runtime_definitions = "\n".join(
        (
            f'<UnitTest id="runtime-{index}" name="{test["testName"]}">'
            f'<TestMethod className="{test["testIdentity"].rsplit(".", 1)[0]}" '
            f'name="{test["testIdentity"].rsplit(".", 1)[1]}" />'
            "</UnitTest>"
        )
        for index, test in enumerate(runtime_example["tests"])
    )
    (evidence / "runtime-tests.trx").write_text(
        (
            f"<TestRun><Results>{runtime_results}</Results>"
            f"<TestDefinitions>{runtime_definitions}</TestDefinitions></TestRun>\n"
        ),
        encoding="utf-8",
    )
    handoff_path = evidence / "modernization-contract.json"
    handoff_path.write_text(
        json.dumps(handoff),
        encoding="utf-8",
    )
    report = {
        "schemaVersion": "1.0.0",
        "profile": "full",
        "status": "passed",
        "startedAt": "2026-08-18T00:00:00Z",
        "finishedAt": "2026-08-18T00:01:00Z",
        "baseUrl": handoff["application"]["url"],
        "databaseKind": "sqlserver",
        "corpus": {
            "figures": 198,
            "categories": 20,
            "images": 198,
        },
        "databaseTarget": "managed",
        "subject": {
            "sourceCommit": handoff["source"]["commitSha"],
            "imageDigest": handoff["containerImage"]["digest"],
            "revisionName": handoff["application"]["revisionName"],
        },
        "checks": [
            {
                "name": name,
                "status": "passed",
                "detail": "fixture",
                "required": True,
            }
            for name in FULL_ACCEPTANCE_CHECKS
        ],
    }
    (evidence / "acceptance-report.json").write_text(
        json.dumps(report),
        encoding="utf-8",
    )
    (evidence / "telemetry-report.json").write_text(
        (contracts / "telemetry-evidence.example.json").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    telemetry = load_json(contracts / "telemetry-evidence.example.json")
    signal_contract = load_json(contracts / "behavior-contract.json")["telemetry"]
    telemetry_directory = evidence / "telemetry"
    telemetry_directory.mkdir()
    for query_id, query in telemetry["queries"].items():
        rows = []
        for signal_name in query["expectedSignalNames"]:
            observed_attributes = (
                list(telemetry["resourceAttributes"])
                if query_id == "resources"
                else signal_contract[query_id][signal_name]
            )
            row = {
                "signalName": signal_name,
                "recordCount": 1,
                "observedAttributes": observed_attributes,
            }
            if query_id == "resources":
                row["resourceAttributes"] = telemetry["resourceAttributes"]
            if query_id == "metrics":
                row["unit"] = signal_contract["metricUnits"][signal_name]
                row["measurements"] = [
                    {
                        "value": (
                            3
                            if signal_name == "catalog.import.records"
                            else 1
                        ),
                        "attributes": (
                            {
                                "http.request.method": "GET",
                                "http.route": "/figure/{id}",
                                "http.response.status_code": 200,
                            }
                            if signal_name == "http.server.request.duration"
                            else (
                                {"catalog.import.outcome": "rejected"}
                                if signal_name == "catalog.import.records"
                                else {}
                            )
                        ),
                    }
                ]
            if query_id in ("traces", "logs"):
                is_http = signal_name in ("http.server", "http.server.request")
                row["observations"] = [
                    {
                        "attributes": (
                            {
                                "http.request.method": "GET",
                                "http.route": "/figure/{id}",
                                "http.response.status_code": 200,
                            }
                            if is_http
                            else {}
                        )
                    }
                ]
            rows.append(row)
        result_path = tmp_path / query["resultFile"]
        result_path.write_text(
            json.dumps(
                {
                    "schemaVersion": "1.0.0",
                    "queryId": query_id,
                    "rows": rows,
                    "workspaceId": "/subscriptions/s/resourceGroups/r/providers/Microsoft.OperationalInsights/workspaces/w",
                    "capturedAt": "2026-08-27T22:05:00Z",
                    "queryText": "AppTraces | summarize count() by OperationName",
                }
            ),
            encoding="utf-8",
        )
    (evidence / "runtime-test-report.json").write_text(
        (contracts / "runtime-test-evidence.example.json").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    target_output = {
        "schemaVersion": "1.2.0",
        "deploymentStage": "application",
        "applicationRevisionRole": "release",
        "sourceCommit": handoff["source"]["commitSha"],
        "stack": handoff["source"]["stack"],
        "location": handoff["application"]["region"],
        "resourceGroup": {
            "name": handoff["application"]["resourceGroup"],
            "resourceId": "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/rg-mh-example",
        },
        "network": {
            "virtualNetworkResourceId": "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/rg-mh-example/providers/Microsoft.Network/virtualNetworks/vnet-mh-example",
            "migrationSourceVirtualNetworkResourceId": "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/rg-mh-source-example/providers/Microsoft.Network/virtualNetworks/vnet-mh-source-example",
            "migrationSourceVmResourceId": "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/rg-mh-source-example/providers/Microsoft.Compute/virtualMachines/vm-dotnet-user001",
            "migrationSourceToTargetPeeringResourceId": "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/rg-mh-source-example/providers/Microsoft.Network/virtualNetworks/vnet-mh-source-example/virtualNetworkPeerings/to-vnet-mh-example",
            "migrationTargetToSourcePeeringResourceId": "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/rg-mh-example/providers/Microsoft.Network/virtualNetworks/vnet-mh-example/virtualNetworkPeerings/to-vnet-mh-source-example",
            "migrationPrivateDnsZoneLinkResourceIds": [
                "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/rg-mh-example/providers/Microsoft.Network/privateDnsZones/privatelink.database.windows.net/virtualNetworkLinks/vnet-mh-source-example",
                "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/rg-mh-example/providers/Microsoft.Network/privateDnsZones/privatelink.blob.core.windows.net/virtualNetworkLinks/vnet-mh-source-example",
            ],
        },
        "containerRegistry": {
            "resourceId": handoff["containerImage"]["registryResourceId"],
            "loginServer": handoff["containerImage"]["registry"],
        },
        "workloadIdentity": {
            "resourceId": "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/rg-mh-example/providers/Microsoft.ManagedIdentity/userAssignedIdentities/id-mh-example",
            "clientId": "00000000-0000-0000-0000-000000000001",
            "principalId": "00000000-0000-0000-0000-000000000002",
        },
        "containerAppsEnvironmentResourceId": "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/rg-mh-example/providers/Microsoft.App/managedEnvironments/cae-mh-example",
        "containerAppsEnvironmentDefaultDomain": "example.swedencentral.azurecontainerapps.io",
        "database": {
            "resourceId": handoff["database"]["resourceId"],
            "family": handoff["database"]["family"],
            "server": handoff["database"]["server"],
            "database": handoff["database"]["database"],
            "authentication": handoff["authentication"]["database"],
            "localAdministratorPrincipal": None,
            "entraAdministratorPrincipal": None,
            "applicationPrincipal": handoff["database"]["applicationPrincipal"],
        },
        "images": {
            "resourceId": handoff["images"]["resourceId"],
            "provider": handoff["images"]["provider"],
            "location": handoff["images"]["location"],
            "authentication": handoff["authentication"]["imageStore"],
        },
        "observability": {
            "applicationInsightsResourceId": handoff["observability"][
                "applicationInsightsResourceId"
            ],
            "logAnalyticsWorkspaceResourceId": handoff["observability"][
                "logAnalyticsWorkspaceResourceId"
            ],
        },
        "containerImage": {
            "repository": handoff["containerImage"]["repository"],
            "tag": handoff["containerImage"]["tag"],
            "digest": handoff["containerImage"]["digest"],
        },
        "application": {
            key: handoff["application"][key]
            for key in (
                "resourceId",
                "url",
                "healthUrl",
                "readinessUrl",
                "containerAppName",
                "revisionName",
            )
        },
    }
    (evidence / "azure-target-output.json").write_text(
        json.dumps(target_output),
        encoding="utf-8",
    )
    migration_report = load_json(contracts / "migration-report.sql.example.json")
    migration_report["sourceCommit"] = handoff["source"]["commitSha"]
    migration_report["targetDatabase"] = target_output["database"]
    migration_report["images"] = {
        **target_output["images"],
        "verification": {
            key: handoff["images"]["verification"][key]
            for key in (
                "imageCount",
                "imageBytes",
                "imageSetSha256",
                "seedManifestVersion",
            )
        },
    }
    (evidence / "migration-report.json").write_text(
        json.dumps(migration_report),
        encoding="utf-8",
    )
    assert validate_handoff(handoff_path, contracts, tmp_path) == handoff
    assert (
        handoff_cli_main(
            [
                str(handoff_path),
                "--contracts",
                str(contracts),
                "--repository-root",
                str(tmp_path),
            ]
        )
        == 0
    )
    first_path_evidence = tmp_path / handoff["evidence"]["pathEvidence"][0]
    path_evidence_contents = first_path_evidence.read_text(encoding="utf-8")
    first_path_evidence.unlink()
    with pytest.raises(FileNotFoundError, match="referenced handoff artifact is absent"):
        validate_handoff(handoff_path, contracts, tmp_path)
    first_path_evidence.mkdir()
    (first_path_evidence / "placeholder").write_text(
        "not the required file\n", encoding="utf-8"
    )
    with pytest.raises(ValueError, match="nonempty regular file"):
        validate_handoff(handoff_path, contracts, tmp_path)
    (first_path_evidence / "placeholder").unlink()
    first_path_evidence.rmdir()
    first_path_evidence.write_text(path_evidence_contents, encoding="utf-8")

    target_output_path = evidence / "azure-target-output.json"
    passing_target_output = load_json(target_output_path)
    invalid_target_output = json.loads(json.dumps(passing_target_output))
    invalid_target_output["database"]["server"] = "other.database.windows.net"
    target_output_path.write_text(json.dumps(invalid_target_output), encoding="utf-8")
    with pytest.raises(ValueError, match="target database names differ"):
        validate_handoff(handoff_path, contracts, tmp_path)
    target_output_path.write_text(json.dumps(passing_target_output), encoding="utf-8")

    baseline_target_output = json.loads(json.dumps(passing_target_output))
    baseline_target_output["applicationRevisionRole"] = "baseline"
    baseline_target_output["application"]["revisionName"] = baseline_target_output[
        "application"
    ]["revisionName"].replace("--release-", "--baseline-")
    target_output_path.write_text(
        json.dumps(baseline_target_output),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="not the release application revision"):
        validate_handoff(handoff_path, contracts, tmp_path)
    target_output_path.write_text(json.dumps(passing_target_output), encoding="utf-8")

    migration_report_path = evidence / "migration-report.json"
    passing_migration_report = load_json(migration_report_path)
    invalid_migration_report = json.loads(json.dumps(passing_migration_report))
    invalid_migration_report["migrationExecution"]["hostVmResourceId"] = (
        invalid_migration_report["migrationExecution"]["hostVmResourceId"].replace(
            "vm-dotnet-user001",
            "vm-dotnet-user999",
        )
    )
    migration_report_path.write_text(
        json.dumps(invalid_migration_report),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="execution path differs"):
        validate_handoff(handoff_path, contracts, tmp_path)
    migration_report_path.write_text(
        json.dumps(passing_migration_report),
        encoding="utf-8",
    )

    invalid_migration_report = json.loads(json.dumps(passing_migration_report))
    invalid_migration_report["databaseVerification"]["migrationHistory"] = [
        "unrelated migration"
    ]
    migration_report_path.write_text(
        json.dumps(invalid_migration_report),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="history differs"):
        validate_handoff(handoff_path, contracts, tmp_path)
    migration_report_path.write_text(
        json.dumps(passing_migration_report),
        encoding="utf-8",
    )
    invalid_migration_report = json.loads(json.dumps(passing_migration_report))
    invalid_migration_report["databaseArtifact"]["importTool"]["version"] = "999.0"
    migration_report_path.write_text(
        json.dumps(invalid_migration_report),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="tools differ"):
        validate_handoff(handoff_path, contracts, tmp_path)
    migration_report_path.write_text(
        json.dumps(passing_migration_report),
        encoding="utf-8",
    )

    metrics_path = tmp_path / telemetry["queries"]["metrics"]["resultFile"]
    passing_metrics = load_json(metrics_path)
    invalid_metrics = json.loads(json.dumps(passing_metrics))
    invalid_metrics["rows"][0]["unit"] = "ms"
    metrics_path.write_text(json.dumps(invalid_metrics), encoding="utf-8")
    with pytest.raises(ValueError, match="unit differs"):
        validate_handoff(handoff_path, contracts, tmp_path)
    invalid_metrics = json.loads(json.dumps(passing_metrics))
    import_row = next(
        row
        for row in invalid_metrics["rows"]
        if row["signalName"] == "catalog.import.records"
    )
    import_row["measurements"][0]["value"] = 1.5
    metrics_path.write_text(json.dumps(invalid_metrics), encoding="utf-8")
    with pytest.raises(ValueError, match="positive integral aggregate"):
        validate_handoff(handoff_path, contracts, tmp_path)
    metrics_path.write_text(json.dumps(passing_metrics), encoding="utf-8")

    runtime_artifact = evidence / "runtime-tests.trx"
    passing_runtime_results = runtime_artifact.read_text(encoding="utf-8")
    runtime_artifact.write_text(
        passing_runtime_results.replace('outcome="Passed"', 'outcome="Failed"', 1),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="lacks passing"):
        validate_handoff(handoff_path, contracts, tmp_path)
    runtime_artifact.write_text(passing_runtime_results, encoding="utf-8")
    runtime_artifact.write_text(
        passing_runtime_results.replace(
            'className="LegoCatalog.App.Tests.HealthContractTests"',
            'className="LegoCatalog.App.Tests.UnrelatedTests"',
            1,
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="lacks passing"):
        validate_handoff(handoff_path, contracts, tmp_path)
    runtime_artifact.write_text(passing_runtime_results, encoding="utf-8")

    invalid_handoff = json.loads(json.dumps(handoff))
    invalid_handoff["seedManifest"]["hashes"]["imageSetSha256"] = "0" * 64
    handoff_path.write_text(json.dumps(invalid_handoff), encoding="utf-8")
    with pytest.raises(ValueError, match="canonical manifest"):
        validate_handoff(handoff_path, contracts, tmp_path)
    handoff_path.write_text(json.dumps(handoff), encoding="utf-8")

    invalid_handoff = json.loads(json.dumps(handoff))
    invalid_handoff["rollback"]["targetRevision"] = (
        "ca-mh-example--baseline-111111111111"
    )
    handoff_path.write_text(json.dumps(invalid_handoff), encoding="utf-8")
    with pytest.raises(ValueError, match="not the deterministic baseline revision"):
        validate_handoff(handoff_path, contracts, tmp_path)
    handoff_path.write_text(json.dumps(handoff), encoding="utf-8")

    rollback = evidence / "rollback-runbook.md"
    rollback.write_text("", encoding="utf-8")
    with pytest.raises(ValueError, match="artifact is empty"):
        validate_handoff(handoff_path, contracts, tmp_path)
    rollback.write_text("rollback fixture\n", encoding="utf-8")

    iac_file = iac_directory / "main.bicep"
    iac_file.write_text("", encoding="utf-8")
    with pytest.raises(ValueError, match="artifact is empty"):
        validate_handoff(handoff_path, contracts, tmp_path)
    iac_file.write_text("metadata contractFixture = true\n", encoding="utf-8")
    wrong_extension = iac_file.with_suffix(".tf")
    iac_file.rename(wrong_extension)
    with pytest.raises(ValueError, match=r"no non-empty .*\.bicep"):
        validate_handoff(handoff_path, contracts, tmp_path)
    wrong_extension.rename(iac_file)

    report["profile"] = "smoke"
    (evidence / "acceptance-report.json").write_text(
        json.dumps(report),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="full passing"):
        validate_handoff(handoff_path, contracts, tmp_path)


def test_provisioner_installs_git_exactly_as_the_lock_pins_it(
    repo_root: Path,
) -> None:
    """Bind the VM provisioner to the frozen Git pin so the two cannot drift apart.

    Both GitHub Copilot Challenge 1 paths commit their work and read it back with
    `git rev-parse HEAD`, so Git is a load-bearing part of the toolchain rather than a
    convenience. A pin that the provisioner does not actually install would reintroduce
    exactly the unpinned-dependency drift the lock exists to prevent.
    """
    git = load_json(repo_root / "workshop" / "toolchain.lock.json")["tools"]["git"]
    script = (repo_root / "baseInfra" / "scripts" / "provision-vm.ps1").read_text(
        encoding="utf-8"
    )

    for pinned in (git["version"], git["url"], git["sha256"],
                   git["signaturePublisher"]):
        assert pinned in script

    # The archive is not a clone, so the provisioner must seed a working tree itself.
    assert "Initialize-SourceRepository" in script
    assert "init --initial-branch=workshop" in script
    # Upstream provenance stays distinct from the participant's own commit.
    assert ".source-commit" in script


def test_provisioner_powershell_parses(repo_root: Path) -> None:
    """Parse the provisioner so a syntax error cannot reach a delivery.

    The provisioning script only ever executes on a freshly created Azure VM, where a
    parse error surfaces as an opaque extension failure after several minutes. Parsing it
    here turns that into an immediate, local failure.
    """
    pwsh = shutil.which("pwsh")
    if pwsh is None:
        pytest.skip("pwsh is not installed on this machine")

    script = repo_root / "baseInfra" / "scripts" / "provision-vm.ps1"
    command = (
        "$errors = $null; "
        "$null = [System.Management.Automation.Language.Parser]::ParseFile("
        f"'{script}', [ref]$null, [ref]$errors); "
        "if ($errors) { $errors | ForEach-Object { $_.Message }; exit 1 }"
    )
    completed = subprocess.run(
        [pwsh, "-NoProfile", "-NonInteractive", "-Command", command],
        capture_output=True,
        text=True,
        timeout=180,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr


def _provisioner(repo_root: Path) -> str:
    return (repo_root / "baseInfra" / "scripts" / "provision-vm.ps1").read_text(
        encoding="utf-8"
    )


def _lock(repo_root: Path) -> dict:
    return load_json(repo_root / "workshop" / "toolchain.lock.json")


def _committed_text(repo_root: Path, relative: str) -> str:
    """Return a file's contents as committed at ``HEAD``, ignoring the working tree.

    Guards that watch the *shipped* baseline for maintainer drift have to read what the
    repository ships, not what is currently on disk. The working tree under `java/` and
    `dotnet/` is precisely where a participant does Challenge 1, so a baseline guard
    that reads from disk stops describing the workshop and starts failing the exercise.
    """
    return subprocess.run(
        ["git", "show", f"HEAD:{relative}"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=True,
    ).stdout


def _committed_paths(repo_root: Path, directory: str) -> list[str]:
    """Return repository-relative paths committed at ``HEAD`` under ``directory``."""
    listing = subprocess.run(
        ["git", "ls-tree", "-r", "-z", "--name-only", "HEAD", f"{directory}/"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    return [entry for entry in listing.split("\0") if entry]


def test_legacy_dotnet_tree_stays_on_the_locked_source_sdk(repo_root: Path) -> None:
    """Fail if `dotnet/` drifts off the legacy baseline participants must start from.

    The workshop's premise is that only legacy code ships in the participant-facing
    tree and participants modernize it themselves. A silent upgrade of `dotnet/` breaks
    that premise *and* the VM, which pins the source SDK with `rollForward: disable`.
    The expected framework is derived from the lock rather than hard-coded so the two
    can never disagree.

    Read from ``HEAD`` rather than from disk, because the drift this guards against is
    the maintainer's and the working tree belongs to the participant. Challenge 1 asks
    every path to retarget the application -- on the rewrite path that is the first
    slice -- and the runbook re-runs this suite after each one. Reading the working tree
    turned a guard on what the workshop ships into a guard on the participant doing the
    exercise, red from slice one onward, with a message about a drifted baseline that
    names neither the challenge nor any way forward.
    """
    source_sdk = _lock(repo_root)["runtimes"]["dotnet"]["sourceSdk"]
    expected = f"net{source_sdk.split('.')[0]}.0"

    projects = sorted(
        path
        for path in _committed_paths(repo_root, "dotnet")
        if path.endswith(".csproj")
    )
    assert projects, "the legacy .NET tree has no projects"
    for project in projects:
        text = _committed_text(repo_root, project)
        assert f"<TargetFramework>{expected}</TargetFramework>" in text, (
            f"{project} is not on the locked source SDK "
            f"{expected}; the legacy baseline has drifted"
        )


def test_legacy_java_tree_stays_on_the_locked_source_spring_boot(
    repo_root: Path,
) -> None:
    """Fail if `java/` drifts off the legacy Spring Boot and JDK baseline.

    Read from ``HEAD`` for the same reason as the .NET guard above: this watches the
    shipped baseline for maintainer drift, and the working tree is where the participant
    does the exercise.
    """
    java = _lock(repo_root)["runtimes"]["java"]
    boot = java["sourceSpringBoot"]
    jdk_major = java["sourceRuntime"].split(".")[0]

    pom = _committed_text(repo_root, "java/pom.xml")
    assert f"<version>{boot}</version>" in pom, (
        f"java/pom.xml is not on the locked source Spring Boot {boot}"
    )
    assert f"<java.version>{jdk_major}</java.version>" in pom
    assert f"<maven.compiler.release>{jdk_major}</maven.compiler.release>" in pom


def test_provisioner_installs_jq_exactly_as_the_lock_pins_it(repo_root: Path) -> None:
    """Bind the provisioner to the frozen jq pin.

    The evidence blocks in Challenges 2, 3, 5 and 6 are written in `jq`, so it has to be
    on the VM. Upstream ships it unsigned, which is why it is pinned by hash alone.
    """
    jq = _lock(repo_root)["tools"]["jq"]
    assert "signaturePublisher" not in jq, (
        "jq ships unsigned upstream; pinning a publisher would fail on the VM"
    )
    script = _provisioner(repo_root)
    for pinned in (jq["version"], jq["url"], jq["sha256"]):
        assert pinned in script
    assert "jq version verification failed" in " ".join(script.split())


def test_provisioner_puts_git_bash_utilities_on_path(repo_root: Path) -> None:
    """`usr\\bin` carries bash, curl and the coreutils the later chapters call.

    Git for Windows installs them but only adds `cmd` to PATH, so without this the
    documented `sha256sum` and `bash` blocks fail on the mandated host.
    """
    script = _provisioner(repo_root)
    assert "Add-MachinePath -Path (Join-Path $GitRoot 'usr\\bin')" in script


def test_source_archive_guard_rejects_a_stale_commit(repo_root: Path) -> None:
    """A stale pin must fail loudly during provisioning, not silently succeed.

    The historical pin still contains `data`, `dotnet` and `java`, so a content guard
    naming only those would install the wrong tree without complaint.
    """
    script = _provisioner(repo_root)
    assert "infra\\main.bicep" in script
    assert "catalog-migrate" in script


def test_reprovisioning_preserves_participant_git_history(repo_root: Path) -> None:
    """Re-running provisioning is the facilitator's first repair step.

    After the Git pin, the participant's Challenge 1 commits live only on that VM, and
    the image tags and handoff bind to them. Replacing the tree would destroy them.
    """
    script = _provisioner(repo_root)
    assert "leaving participant work untouched" in " ".join(script.split())
    assert "$Previous is deliberately kept" in script


def test_terraform_requires_an_explicit_source_commit(repo_root: Path) -> None:
    """No default, and the known-stale pin is rejected outright."""
    stale = "fd298de6ded4e55b5208fe3f6d8e81fbcdf836c9"
    variables = (repo_root / "baseInfra" / "terraform" / "variables.tf").read_text(
        encoding="utf-8"
    )
    block = variables.split('variable "source_commit"', 1)[1].split("\nvariable ", 1)[0]
    assignments = [
        line.strip()
        for line in block.splitlines()
        if re.match(r"\s*default\s*=", line)
    ]
    assert not assignments, f"source_commit must not ship a default: {assignments}"
    assert f'var.source_commit != "{stale}"' in block

    example = (
        repo_root / "baseInfra" / "terraform" / "config.tfvars.example"
    ).read_text(encoding="utf-8")
    assert stale not in example, "the example tfvars still pre-fills the stale pin"


CH01_SOLUTION_RUNBOOKS = (
    "ch01-manual/dotnet",
    "ch01-manual/java",
    "ch01-copilot-modernization/dotnet",
    "ch01-copilot-modernization/java",
    "ch01-copilot-rewrite/dotnet",
    "ch01-copilot-rewrite/java",
)


def test_every_challenge_one_path_publishes_its_work_to_github(
    repo_root: Path,
) -> None:
    """Challenge 3 builds the participant's own Dockerfile out of their repository.

    `.github/workflows/catalog-*.yml` checks the application source out of GitHub at
    the handoff's `sourceCommit` and builds `application-source/<stack>/Dockerfile`.
    Both are things the participant creates on the VM, so unless every path pushes its
    work and records the pushed commit, Challenge 3 cannot build for anyone: the
    checkout either fails outright or lands on a tree with no Dockerfile.
    """
    for path in CH01_SOLUTION_RUNBOOKS:
        text = (repo_root / "solutions" / path / "README.md").read_text(
            encoding="utf-8"
        )
        assert "git push" in text, f"{path} never publishes the participant's work"
        assert "git remote" in text, f"{path} never points the tree at a remote"
        assert "git rev-parse HEAD" in text, (
            f"{path} must bind the handoff to the commit it pushed"
        )
        # The archive marker names an upstream commit GitHub has never seen.
        assert ".source-commit' -Raw" not in text, (
            f"{path} still derives the source identity from the archive marker, "
            "which Challenge 3 cannot check out"
        )


def test_challenge_one_tells_participants_to_publish(repo_root: Path) -> None:
    """The participant-facing chapter must own the handoff to Challenge 3."""
    text = (repo_root / "challenges" / "ch01" / "README.md").read_text(
        encoding="utf-8"
    )
    assert "git push" in text


def test_every_markdown_local_link_resolves(repo_root: Path) -> None:
    """Catch dangling cross-references anywhere, not just in the navigation set.

    The narrower navigation link check does not cover ``docs/`` or ``workshop/``, which
    is how a reference to a directory that had never been created reached the facilitator
    day-of checklist.
    """
    skipped_roots = {".git", "node_modules", ".venv", "__pycache__"}
    broken: list[str] = []
    checked = 0

    for document in sorted(repo_root.rglob("*.md")):
        if any(part in skipped_roots for part in document.parts):
            continue
        checked += 1
        relative = document.relative_to(repo_root).as_posix()
        for match in re.finditer(r"\]\(([^)]+)\)", document.read_text(encoding="utf-8")):
            target = match.group(1).split("#")[0].strip()
            if not target or target.startswith(("http://", "https://", "mailto:")):
                continue
            # Placeholders such as ``<stack>`` are instructions, not paths.
            if "<" in target or "{" in target or "$" in target:
                continue
            if not (document.parent / target).resolve().exists():
                broken.append(f"{relative} -> {target}")

    assert checked >= 50, f"only {checked} documents scanned; the walk is not running"
    assert not broken, "unresolved local links:\n" + "\n".join(broken)


def test_golden_handoff_location_exists_and_is_not_committed(repo_root: Path) -> None:
    """The rejoin path must name a real place and must not ship a stale contract."""
    golden = repo_root / "workshop" / "golden"
    assert (golden / "README.md").is_file()
    for stack in ("dotnet-sqlserver", "java-postgresql"):
        assert (golden / stack).is_dir(), stack
        contract = golden / stack / "evidence" / "modernization-contract.json"
        assert not contract.exists(), (
            f"{stack} ships a golden handoff; its Azure resource IDs and image digest "
            "are dead the moment that environment is torn down"
        )

    ignore = (repo_root / ".gitignore").read_text(encoding="utf-8")
    # A bundle is its own validation root, so the whole evidence directory is ignored,
    # not just the contract that names it.
    assert "workshop/golden/*/evidence/" in ignore


def test_participant_template_is_resource_group_scoped(repo_root: Path) -> None:
    """Participants hold Owner on one resource group and nothing above it.

    A subscription-scoped participant deployment fails with ``AuthorizationFailed`` for
    the whole room at once, so the scope is asserted here rather than discovered live.
    """
    template = (repo_root / "infra" / "main.bicep").read_text(encoding="utf-8")
    assert "targetScope = 'resourceGroup'" in template
    assert "resource resourceGroup 'Microsoft.Resources/resourceGroups" not in template
    assert "resourceGroup().name" in template, (
        "the template must assert that resourceGroupName matches the group it is "
        "deployed into, or a stale parameter file deploys into the wrong place"
    )

    offenders: list[str] = []
    checked = 0
    for document in sorted(repo_root.rglob("*.md")):
        if any(part in {".git", "node_modules", ".venv"} for part in document.parts):
            continue
        checked += 1
        text = document.read_text(encoding="utf-8")
        for match in re.finditer(r"az deployment sub ", text):
            window = text[match.start():match.start() + 400]
            if "main.bicep" in window:
                offenders.append(document.relative_to(repo_root).as_posix())

    assert checked >= 50, f"only {checked} documents scanned; the walk is not running"
    assert not offenders, (
        "subscription-scope deployment of the participant template:\n"
        + "\n".join(sorted(set(offenders)))
    )


def test_facilitator_owns_the_repository_url_participants_are_told_to_use(
    repo_root: Path,
) -> None:
    """Every runbook asks for a facilitator-provided URL, so a facilitator must own it.

    The workshop's recurring failure mode is a prerequisite that participant text depends
    on and no facilitator document supplies.
    """
    runbooks = [
        repo_root / "solutions" / stack / language / "README.md"
        for stack in (
            "ch01-manual",
            "ch01-copilot-rewrite",
            "ch01-copilot-modernization",
        )
        for language in ("dotnet", "java")
    ]
    for runbook in runbooks:
        text = runbook.read_text(encoding="utf-8")
        assert "git push" in text, runbook
        assert "facilitator-provided" in text, runbook

    facilitator = (repo_root / "docs" / "Facilitator.md").read_text(encoding="utf-8")
    assert "repository HTTPS URL" in facilitator
    assert "A test push succeeds from one VM" in facilitator
    assert "not from the VM" not in facilitator, (
        "participants now push from the VM; the old guidance is false"
    )


CH01_RUNBOOKS = (
    "solutions/ch01-manual/dotnet/README.md",
    "solutions/ch01-manual/java/README.md",
    "solutions/ch01-copilot-rewrite/dotnet/README.md",
    "solutions/ch01-copilot-rewrite/java/README.md",
    "solutions/ch01-copilot-modernization/dotnet/README.md",
    "solutions/ch01-copilot-modernization/java/README.md",
)

PROTECTED_PATH = re.compile(r"C:\\protected\\[^\s'\"`]+", re.IGNORECASE)


def test_protected_parameter_paths_contain_no_unresolved_placeholder(
    repo_root: Path,
) -> None:
    """Reject a runbook that prints a template placeholder as a real filename.

    Two runbooks shipped ``C:\\protected\\<path>-<stage>.json`` verbatim, which
    throws the moment a participant runs it.
    """
    offenders: list[str] = []
    seen = 0
    for relative in CH01_RUNBOOKS:
        for match in PROTECTED_PATH.findall((repo_root / relative).read_text()):
            seen += 1
            if "<" in match or ">" in match:
                offenders.append(f"{relative}: {match}")
    # 28 paths match today. A regex that quietly stops matching would leave this
    # guard reporting success over an empty enumeration, which is the exact way
    # the placeholder it was written to catch reached participants in the first place.
    assert seen >= PROTECTED_PATH_FLOOR, (
        f"only {seen} protected parameter paths were examined across "
        f"{len(CH01_RUNBOOKS)} runbooks; the pattern has stopped matching"
    )
    assert not offenders, (
        "protected parameter paths must be literal, not placeholders: "
        + "; ".join(offenders)
    )


def test_protected_parameter_files_have_a_producer(repo_root: Path) -> None:
    """Bind the runbooks' protected parameter files to the script that writes them.

    Every runbook deploys with ``--parameters '@C:\\protected\\...json'``. If nothing
    creates those files, Challenge 1 cannot start on any path.
    """
    referenced = {
        match
        for relative in CH01_RUNBOOKS
        for match in PROTECTED_PATH.findall((repo_root / relative).read_text())
        if match.lower().endswith(".json")
    }
    assert referenced, "expected the runbooks to reference protected parameter files"

    provisioner = (repo_root / "baseInfra/scripts/provision-vm.ps1").read_text()
    assert "protected" in provisioner.lower()
    for token in ("resourceGroupName", "performanceApiKey", "facilitatorPrincipalObjectId"):
        assert token in provisioner, (
            f"the provisioner must write {token} into the protected parameter file; "
            "the template requires it and no participant can supply it"
        )


def test_performance_api_key_is_documented_somewhere(repo_root: Path) -> None:
    """Require the hard-asserted application secret to be explained where it is needed.

    ``infra/main.bicep`` fails the application stage outright when
    ``performanceApiKey`` is empty, so a parameter nobody documents is a stop.

    "Somewhere" used to mean any Markdown file in the repository, which the internal
    build log satisfies on its own -- the guard would stay green while every reader-facing
    document lost the parameter. The facilitator supplies the value and the Challenge 1
    runbooks pass it, so those are the documents that must carry it.
    """
    # The build log records what was done, not what a reader must do; it can never be
    # the thing that satisfies a documentation requirement.
    internal = {"docs/ImplementationLog.md", "docs/RewritePlan.md"}

    required = ["docs/Facilitator.md", "infra/README.md"] + [
        f"solutions/{chapter}/{stack}/README.md"
        for chapter in (
            "ch01-manual",
            "ch01-copilot-rewrite",
            "ch01-copilot-modernization",
        )
        for stack in ("dotnet", "java")
    ]
    missing = [
        relative
        for relative in required
        if "performanceApiKey" not in (repo_root / relative).read_text(encoding="utf-8")
    ]
    assert not missing, (
        "infra/main.bicep asserts performanceApiKey is present for the application "
        "stage, but these reader-facing documents never mention it: "
        + ", ".join(missing)
    )

    documented = {
        path.relative_to(repo_root).as_posix()
        for path in repo_root.rglob("*.md")
        if not set(path.parts) & {".git", ".venv", "node_modules"}
        and "performanceApiKey" in path.read_text(encoding="utf-8")
    }
    assert documented - internal, "only internal build documents mention it"


def test_recovery_time_lands_in_an_evidence_file(repo_root: Path) -> None:
    """Require the workshop's headline MTTR figure to persist, not just print.

    Challenge 6 calls it "the most persuasive single number this workshop
    produces"; a number that only reaches stdout cannot be aggregated.
    """
    for relative in (
        "challenges/ch06-sre-agent/README.md",
        "solutions/ch06-sre-agent/README.md",
    ):
        content = (repo_root / relative).read_text()
        assert "minutesToRecovery" in content
        assert "ch06-mttr.json" in content, (
            f"{relative} must write the recovery figure to evidence/ch06-mttr.json"
        )


def test_recovery_clock_endpoints_are_both_derived(repo_root: Path) -> None:
    """Reject a recovery block that computes one endpoint and abandons the other."""
    solution = (repo_root / "solutions/ch06-sre-agent/README.md").read_text()
    assert "RECOVERED_AT=" in solution, (
        "solutions/ch06-sre-agent guards RECOVERED_AT but never assigns it, so the "
        "block aborts as printed"
    )


def test_lead_time_label_names_what_it_measures(repo_root: Path) -> None:
    """Reject the DORA label on a clock that starts after the trigger.

    Challenge 3 binds the timer to a job start under ``workflow_dispatch``. Calling
    that "commit to live" misstates a term with a specific definition.
    """
    content = (repo_root / "challenges/ch03/README.md").read_text()
    assert "commit to live" not in content, (
        "the pipeline clock starts at dispatch, not at a commit; label it accordingly"
    )


def test_demo_asset_exists_and_is_reachable(repo_root: Path) -> None:
    """Require a runnable demo script, and require the day-of card to point at it."""
    demo = repo_root / "docs" / "Demo.md"
    assert demo.is_file(), "docs/Demo.md must exist for anyone showing this workshop"
    content = demo.read_text()
    assert "## One slide" in content, "the demo must end with pasteable slide bullets"
    day_of = (repo_root / "docs" / "DayOfCard.md").read_text()
    assert "Demo.md" in day_of, "docs/DayOfCard.md schedules a demo and must link to it"


BANNED_CHAPTER_MAP_PHRASES = (
    "prove five frozen queries",
    "without creating attack traffic",
    "verify cleanup billing",
)


def test_chapter_map_describes_participant_outcomes(repo_root: Path) -> None:
    """Keep the most-read table in the participant's voice and free of contradictions.

    "verify cleanup billing" contradicts Challenge 6, which assigns teardown to the
    facilitator.
    """
    readme = (repo_root / "README.md").read_text().lower()
    for phrase in BANNED_CHAPTER_MAP_PHRASES:
        assert phrase not in readme, (
            f"the chapter map still reads as validator language: {phrase!r}"
        )


SCOPE_PROSE = re.compile(r"subscription[- ]scope", re.IGNORECASE)


def test_no_document_describes_the_participant_template_as_subscription_scoped(
    repo_root: Path,
) -> None:
    """Catch normative prose left behind by the resource-group conversion.

    Converted commands are not enough: a paragraph that still defines the old model
    is the design contract, and anyone who trusts it reinstates the blocker.
    """
    offenders: list[str] = []
    for relative in (
        ".azure/deployment-plan.md",
        "infra/README.md",
        "README.md",
        "challenges/ch01-manual/README.md",
        "challenges/ch01-copilot-rewrite/README.md",
        "challenges/ch01-copilot-modernization/README.md",
        "challenges/ch01/README.md",
    ):
        path = repo_root / relative
        if not path.is_file():
            continue
        for number, line in enumerate(path.read_text().splitlines(), start=1):
            if SCOPE_PROSE.search(line) and "sre-agent" not in line.lower():
                offenders.append(f"{relative}:{number}: {line.strip()}")
    assert not offenders, (
        "main.bicep is resource-group scoped; only the sre-agent custom role is a "
        "subscription-scope exception:\n" + "\n".join(offenders)
    )


def test_participant_chapters_name_the_resource_group_parameter(repo_root: Path) -> None:
    """Require every chapter that deploys the template to name the parameter it asserts.

    ``infra/main.bicep`` asserts ``resourceGroupName`` matches the group it is deployed
    into, so a participant who never sees the parameter meets that assertion as an
    error message. Each Challenge 1 path deploys, so each must name it -- checking that
    *some* chapter does would let three of the four paths go silent.
    """
    deploying = sorted(
        path
        for path in (repo_root / "challenges").glob("ch01*/README.md")
    )
    assert len(deploying) == 4, (
        f"expected the four Challenge 1 paths, found {len(deploying)}: "
        f"{[path.parent.name for path in deploying]}"
    )
    silent = [
        path.relative_to(repo_root).as_posix()
        for path in deploying
        if "resourceGroupName" not in path.read_text(encoding="utf-8")
    ]
    assert not silent, (
        "infra/main.bicep requires and asserts resourceGroupName, but these chapters "
        "never mention it: " + ", ".join(silent)
    )


def test_template_binds_migration_source_to_the_participant_group(
    repo_root: Path,
) -> None:
    """Require peering to be provably confined to the participant's own group."""
    template = (repo_root / "infra" / "main.bicep").read_text()
    assert "migratesFromTheParticipantResourceGroup" in template, (
        "without this assert a copied resource id would peer into another "
        "participant's environment"
    )


# Thirteen chapter READMEs today. A floor, not an equality: adding a chapter must not
# fail the build, but losing the walk must.
CHAPTER_README_FLOOR = 13


def _chapter_readmes(repo_root: Path) -> list[Path]:
    """Return every participant-facing chapter README, in stable order.

    The floor is the point of this helper. Both callers assert the *absence* of a
    defect across the chapters, and an enumeration that returns nothing satisfies an
    absence trivially: rename ``challenges/`` and the two guards protecting the
    bash-in-PowerShell class -- blocking when it was found -- both go green while
    checking nothing at all.
    """
    readmes = sorted((repo_root / "challenges").rglob("README.md"))
    assert len(readmes) >= CHAPTER_README_FLOOR, (
        f"found {len(readmes)} chapter READMEs, expected at least {CHAPTER_README_FLOOR}; "
        "the chapters have moved and every guard built on this walk is now vacuous"
    )
    return readmes


def test_chapters_using_bash_state_which_shell_to_use(repo_root: Path) -> None:
    """Require any chapter with a bash block to say where that bash runs.

    Challenge 1 puts the participant in PowerShell on the Windows VM. Nothing
    implicitly moves them to Git Bash, and in PowerShell ``curl`` is an alias for
    Invoke-WebRequest, so an unlabelled bash block fails as a broken application
    rather than as a wrong shell.
    """
    silent = []
    for path in _chapter_readmes(repo_root):
        content = path.read_text()
        if "```bash" not in content:
            continue
        if "where you work" not in content.lower():
            silent.append(path.relative_to(repo_root).as_posix())
    assert not silent, (
        "these chapters give bash commands without telling the participant which "
        f"shell to run them in: {silent}"
    )


def test_powershell_chapters_carry_no_bash_line_continuations(
    repo_root: Path,
) -> None:
    """Reject bash ``\\`` continuations in chapters that mandate PowerShell.

    PowerShell continues a line with a backtick. A bash continuation pasted into
    the shell the chapter told the reader to open silently splits into several
    commands, and the first one runs with no arguments.
    """
    offenders = []
    for path in _chapter_readmes(repo_root):
        content = path.read_text()
        mandates_powershell = "```powershell" in content
        if not mandates_powershell:
            continue
        for block in re.findall(r"```bash\n(.*?)```", content, re.DOTALL):
            if any(line.rstrip().endswith("\\") for line in block.splitlines()):
                offenders.append(path.relative_to(repo_root).as_posix())
                break
    assert not offenders, (
        "these chapters instruct the participant to use PowerShell but contain a "
        f"bash-continuation block that breaks when pasted there: {offenders}"
    )


def test_ci_declares_an_sdk_for_every_framework_a_participant_can_ship(
    repo_root: Path,
) -> None:
    """Require CI to declare an SDK for both legitimate handoff frameworks.

    The handoff contract does not pin a target framework, so the manual and
    copilot-rewrite paths ship the source framework while copilot-modernization
    retargets. ``dotnet test`` cannot run a target framework whose runtime is
    absent, so declaring only one major leaves the job depending on whatever the
    hosted runner happens to preinstall.
    """
    workflow = (repo_root / ".github" / "workflows" / "catalog-dotnet.yml").read_text()
    declared = set(re.findall(r"(\d+)\.\d+\.\d+", _dotnet_version_block(workflow)))

    source_tfms = {
        match.group(1)
        for path in _committed_paths(repo_root, "dotnet")
        if path.endswith(".csproj")
        for match in [
            re.search(r"<TargetFramework>net(\d+)\.0<", _committed_text(repo_root, path))
        ]
        if match
    }
    target_tfms = {
        match.group(1)
        for path in _committed_paths(repo_root, "solutions/reference/dotnet")
        if path.endswith(".csproj")
        for match in [
            re.search(r"<TargetFramework>net(\d+)\.0<", _committed_text(repo_root, path))
        ]
        if match
    }
    required = source_tfms | target_tfms
    assert required, "no .NET project declares a TargetFramework"
    missing = required - declared
    assert not missing, (
        f"catalog-dotnet.yml declares .NET {sorted(declared)} but a participant can "
        f"legitimately hand off net{sorted(missing)}; dotnet test would abort unless "
        "the runner image happens to preinstall it"
    )


def _dotnet_version_block(workflow: str) -> str:
    """Return the dotnet-version value, whether scalar or a multi-line block."""
    match = re.search(r"dotnet-version:\s*(\|?)([^\n]*)\n((?:\s{10,}\S+\n)*)", workflow)
    return "" if not match else match.group(2) + match.group(3)


def test_participants_can_read_the_protected_parameter_files_unelevated(repo_root):
    """The deployment parameter files must be readable without elevation.

    C:\\protected is written with inheritance disabled and explicit ACEs. The VM's admin
    account is a *custom* local administrator (the terraform variable forbids reserved
    names), so UAC hands an ordinary PowerShell a filtered token. With a
    SYSTEM/Administrators-only ACL the very first `az deployment group create` of
    Challenge 1 fails with `Access is denied` in a session nobody suspects is
    under-privileged, and no participant document tells them to elevate. So the
    provisioner must also grant the admin account Read on that folder and its files.

    This is not a loosening: the account can already elevate and read them. The database
    passwords under the secrets root must NOT get the same grant, which is what pins the
    grant to an opt-in parameter rather than a change to the shared helper's defaults.
    """
    provisioner = (repo_root / "baseInfra/scripts/provision-vm.ps1").read_text(
        encoding="utf-8"
    )
    # The account name has to travel from terraform, so it must be a validated payload
    # field rather than a guess such as $env:USERNAME (the provisioner runs as SYSTEM).
    assert "'adminUsername'," in provisioner
    assert "$AdminUsername = [string]$ProvisioningSecrets.adminUsername" in provisioner

    protected_dir_acl = re.search(
        r"Set-ProtectedAcl -Path \$ProtectedRoot -Directory[^\n]*", provisioner
    )
    assert protected_dir_acl, "C:\\protected must have its ACL set explicitly"
    assert "-ReadPrincipal $AdminUsername" in protected_dir_acl.group(0)

    # Save-ProtectedConfiguration re-ACLs every file it writes, so the nine parameter
    # files need the grant too or the directory ACE is undone file by file.
    params_write = re.search(
        r"\$File = Join-Path \$ProtectedRoot[^\n]*\n[^\n]*", provisioner
    )
    assert params_write and "-ReadPrincipal $AdminUsername" in params_write.group(0)

    # The secrets root holds database passwords and must stay administrators-only.
    secret_acl = re.search(r"Set-ProtectedAcl -Path \$SecretRoot[^\n]*", provisioner)
    assert secret_acl and "-ReadPrincipal" not in secret_acl.group(0)

    payload = (
        repo_root / "baseInfra/terraform/modules/user_environment/locals.tf"
    ).read_text(encoding="utf-8")
    assert "adminUsername" in payload and "var.admin_username" in payload

    # A facilitator who verifies this from an elevated shell proves nothing about the
    # session Challenge 1 actually runs in.
    facilitator = (repo_root / "docs/Facilitator.md").read_text(encoding="utf-8")
    assert "non-elevated" in facilitator
    assert "participants read them from an elevated session" not in facilitator


def test_protected_folder_is_read_only_for_participants(repo_root):
    """No runbook may write into C:\\protected, and every file it reads must have a producer.

    C:\\protected is facilitator-supplied: the provisioner writes it as SYSTEM before anyone
    logs in, and participants get Read. Two failure modes follow, and the repository had
    both.

    Writing there cannot work. `catalog-migrate ... export --artifact <path>` writes the
    database artifact, so pointing --artifact at C:\\protected fails on the participant's
    own environment -- and one path also named a subdirectory nothing ever created.

    Reading a file nobody writes cannot work either. This is the same defect class as the
    missing deployment parameter files: a runbook copied the bootstrap deployment output
    from C:\\protected\\azure-target-output.json, which no code path has ever produced. That
    file is written by the participant's own step-5 deployment, into evidence/.

    So: the only C:\\protected paths any runbook may name are the nine-per-stack parameter
    files the provisioner actually writes.
    """
    runbooks = sorted((repo_root / "solutions").glob("ch01-*/*/README.md"))
    assert len(runbooks) == 6

    produced = {
        f"{path}-{stack}-{stage}.json"
        for path in ("manual", "copilot-rewrite", "copilot-modernization")
        for stack in ("dotnet", "java")
        for stage in ("bootstrap", "baseline", "release")
    }
    for runbook in runbooks:
        text = runbook.read_text(encoding="utf-8")
        rel = runbook.relative_to(repo_root)

        referenced = {
            name
            for name in re.findall(r"C:\\protected\\([^'\"`\s\\]+)", text)
            # A glob is prose about the folder as a whole, not a concrete file.
            if "*" not in name
        }
        orphans = referenced - produced
        assert not orphans, (
            f"{rel} names C:\\protected files nothing produces: {sorted(orphans)}"
        )

        # The export destination must be somewhere the participant can write.
        for match in re.finditer(
            r"\$(?:Database)?Artifact\s*=\s*'([^']+)'", text
        ):
            destination = match.group(1)
            assert not destination.startswith("C:\\protected"), (
                f"{rel} exports the database artifact into read-only {destination}"
            )
            # A path whose parent is never created fails just as hard as a read-only one.
            parent_created = (
                "New-Item -ItemType Directory -Force (Split-Path $Artifact)" in text
                or "New-Item -ItemType Directory -Force (Split-Path $DatabaseArtifact)"
                in text
            )
            assert parent_created, f"{rel} never creates the parent of {destination}"

CH01_CHAPTERS = (
    "ch01",
    "ch01-manual",
    "ch01-copilot-rewrite",
    "ch01-copilot-modernization",
)


def _fenced_blocks(text: str) -> list[tuple[str, str]]:
    """Return (language, body) for every fenced block in a Markdown document."""
    return re.findall(r"```([A-Za-z0-9_-]*)\n(.*?)```", text, re.S)


def _prose(text: str) -> str:
    """The document with every fenced block removed, so prose claims can be read."""
    return re.sub(r"```.*?```", "", text, flags=re.S)


def test_ch01_chapters_document_the_source_commit_override(repo_root):
    """The two parameters the protected files deliberately omit must be documented.

    `sourceCommit` and `imageDigest` are not knowable when the provisioner writes
    the protected parameter files at T-1, and a placeholder would satisfy the
    template's 40-hex format assert while silently deploying the wrong source. So
    the files omit them and every runbook supplies them as `--parameters`
    overrides on the command line.

    A chapter that instead tells the participant the files *record* `sourceCommit`
    sends them to the facilitator's desk for an edit that cannot be made, on the
    workshop's centrepiece challenge.
    """
    for slug in CH01_CHAPTERS:
        chapter = repo_root / "challenges" / slug / "README.md"
        assert chapter.is_file(), f"missing chapter {slug}"
        normalized = chapter.read_text(encoding="utf-8").lower()
        rel = chapter.relative_to(repo_root)

        assert "sourcecommit" in normalized, (
            f"{rel} never mentions sourceCommit, so a participant meets the "
            "override for the first time as an ARM rejection"
        )
        assert "--parameters sourcecommit=" in normalized, (
            f"{rel} never shows the --parameters sourceCommit= override form"
        )

        # The only true statement about `protected` and `sourceCommit` together is
        # that the field is absent on purpose. Any sentence pairing them must say so.
        sentences = re.findall(r"[^.\n]*sourcecommit[^.\n]*", normalized)
        assert len(sentences) >= SOURCE_COMMIT_SENTENCE_FLOOR, (
            f"{slug}: only {len(sentences)} sentences mention sourcecommit; the "
            "sentence split has stopped finding the prose it audits"
        )
        for sentence in sentences:
            if "protected" not in sentence:
                continue
            assert re.search(
                r"\b(not|no|never|omit|absent|without|missing|deliberately)\b", sentence
            ), f"{rel} implies the protected files carry sourceCommit: {sentence.strip()!r}"


def test_source_commit_override_has_a_symptom_route(repo_root):
    """A participant who forgets the override must be able to self-serve the fix."""
    troubleshooting = (repo_root / "docs" / "Troubleshooting.md").read_text(
        encoding="utf-8"
    ).lower()
    assert "sourcecommit" in troubleshooting, (
        "docs/Troubleshooting.md has no entry for the most likely Challenge 1 failure"
    )

    for slug in CH01_CHAPTERS:
        normalized = (
            (repo_root / "challenges" / slug / "README.md")
            .read_text(encoding="utf-8")
            .lower()
        )
        # The symptom belongs in the chapter's own failure table, not only in prose.
        rows = [line for line in normalized.splitlines() if line.startswith("|")]
        assert any("sourcecommit" in row for row in rows), (
            f"challenges/{slug}/README.md documents the override but its "
            "'If it goes wrong' table has no row for forgetting it"
        )


def test_acceptance_suite_blocks_are_self_contained(repo_root):
    """A block that runs the acceptance suite must establish its own working directory.

    Stating the directory in the surrounding prose is not enough: participants copy the
    block, not the paragraph. The repository has three separate uv projects, so a suite
    command run from the repo root does not merely fail — `uv` resolves a *different*
    project, and the error names a missing script rather than a wrong `cd`.

    The suite is invoked far more often through its console scripts than through pytest,
    so the entry points are read from the packaging metadata rather than hardcoded here.
    """
    scripts = re.findall(
        r"^([a-z-]+) = \"",
        (repo_root / "tests/acceptance/pyproject.toml")
        .read_text(encoding="utf-8")
        .split("[project.scripts]", maxsplit=1)[1]
        .split("\n[", maxsplit=1)[0],
        re.M,
    )
    assert len(scripts) >= 7, "acceptance console scripts not found"
    invocation = re.compile(r"\bpytest\b|\b(?:" + "|".join(scripts) + r")\b")
    # PowerShell runbooks write `cd tests\acceptance` or the idiomatic
    # `Push-Location tests\acceptance`; bash ones use `cd` and a forward slash.
    establishes_cwd = re.compile(
        r"^\s*(?:cd|Push-Location)\s+\S*tests[\\/]acceptance", re.M | re.I
    )
    # Only fences that a participant can actually execute.
    executable = {"bash", "sh", "shell", "console", "powershell", "pwsh", ""}

    offenders: list[str] = []
    examined = 0
    for markdown in sorted(repo_root.rglob("*.md")):
        parts = markdown.relative_to(repo_root).parts
        if set(parts) & {".git", "node_modules", ".venv", "bin", "obj", "target"}:
            continue
        # Documents inside the suite are already there.
        if parts[0] == "tests":
            continue

        for language, body in _fenced_blocks(markdown.read_text(encoding="utf-8")):
            if language.lower() not in executable:
                continue
            examined += 1
            if not invocation.search(body):
                continue
            if establishes_cwd.search(body):
                continue
            offenders.append(f"{'/'.join(parts)} ({language or 'plain'})")

    assert examined >= 40, (
        f"only {examined} executable fences examined; the fence filter is stale and "
        "this guard would pass on a repository full of uncd'd suite invocations"
    )
    assert not offenders, (
        "these blocks invoke the acceptance suite without a cd inside the block: "
        + ", ".join(offenders)
    )


def test_facilitator_and_demo_name_their_host_shell(repo_root):
    """Both facilitator-facing documents must say which shell they are written for.

    `docs/Demo.md` is the first ten minutes of day one on a projector, and
    `docs/Facilitator.md` is consulted under time pressure with a room waiting.
    Neither can afford the reader guessing between Git Bash and PowerShell.
    """
    for rel in ("docs/Facilitator.md", "docs/Demo.md"):
        text = (repo_root / rel).read_text(encoding="utf-8")
        opening = _prose(text)[:4000].lower()
        assert re.search(r"git bash|powershell|pwsh|\bbash\b", opening), (
            f"{rel} never names the shell its blocks are written for"
        )


def test_shell_specific_blocks_declare_their_language(repo_root):
    """Mixed-host documents are fine; undeclared mixed-host documents are not.

    A `\\`-continuation is a parse error in PowerShell and `ConvertFrom-Json` does
    not exist in bash, so a document carrying both forms must label each block.
    """
    powershell_only = re.compile(
        r"\b(ConvertFrom-Json|ConvertTo-Json|Invoke-WebRequest|Invoke-RestMethod"
        r"|New-Item|Test-Path|Resolve-Path|Get-Content|Set-Content|Write-Host)\b"
    )
    inspected = 0
    for rel in ("docs/Facilitator.md", "docs/Demo.md"):
        text = (repo_root / rel).read_text(encoding="utf-8")
        for index, (language, body) in enumerate(_fenced_blocks(text)):
            inspected += 1
            lowered = language.lower()
            if powershell_only.search(body):
                assert lowered in {"powershell", "pwsh"}, (
                    f"{rel} block {index} uses PowerShell cmdlets but is fenced "
                    f"as {language or 'plain'!r}"
                )
            # A continuation is a backslash preceded by whitespace. A backslash
            # that ends a Windows path (`evidence\\runtime-tests\\`) is not one.
            if re.search(r"(?<=\s)\\\r?\n", body) and lowered in {"powershell", "pwsh"}:
                raise AssertionError(
                    f"{rel} block {index} is fenced as {language} but uses "
                    "backslash line continuations, which PowerShell cannot parse"
                )
    assert inspected >= FENCED_BLOCK_FLOOR, (
        f"only {inspected} fenced blocks were inspected across the two mixed-host "
        "documents; the fence parser has stopped seeing them"
    )


def test_lead_time_is_labelled_as_the_interval_it_measures(repo_root):
    """The workshop measures from workflow dispatch, so it must not claim commit.

    `docs/Demo.md` already says "dispatch to live" in four places. The front door
    and the glossary — the two most-read statements of the metric — must agree,
    or the workshop is quoting an interval it never timed.
    """
    for rel in ("README.md", "docs/Glossary.md"):
        normalized = (repo_root / rel).read_text(encoding="utf-8").lower()
        assert "from commit to running revision" not in normalized, (
            f"{rel} still labels deployment lead time as starting at the commit"
        )
        assert "committed change to reach production" not in normalized, (
            f"{rel} still defines deployment lead time as starting at the commit"
        )


def test_modernization_chapter_makes_no_unsourced_productivity_multiple(repo_root):
    """A claim shown to customers must be sourced, reproducible, or qualitative."""
    chapter = repo_root / "challenges" / "ch01-copilot-modernization" / "README.md"
    normalized = chapter.read_text(encoding="utf-8").lower()
    assert "a week per application" not in normalized, (
        "the ~40x productivity multiple is still asserted with no citation"
    )


def test_modernization_chapter_names_its_differentiator(repo_root):
    """The chapter that performs the flagship upgrade must say that it does.

    The README sells path 1C on the framework upgrade; the chapter that performs
    it never mentions the target framework, so the one capability that separates
    it from the other two paths goes unnamed where it is demonstrated.
    """
    normalized = (
        (repo_root / "challenges" / "ch01-copilot-modernization" / "README.md")
        .read_text(encoding="utf-8")
        .lower()
    )
    assert ".net 10" in normalized or "net10.0" in normalized, (
        "the modernization chapter never names the .NET 10 target it upgrades to"
    )


def test_demo_shows_the_upgrade_running_forwards(repo_root):
    """.NET 8 is the legacy source; the modernization path targets .NET 10."""
    normalized = (repo_root / "docs" / "Demo.md").read_text(encoding="utf-8").lower()
    assert "retarget the runtime to .net 8" not in normalized, (
        "the demo script shows the framework upgrade going backwards, to the "
        "version the workshop starts from"
    )


def test_demo_is_reachable_from_the_agenda(repo_root):
    """The sales asset must be linked from the document facilitators plan against."""
    agenda = (repo_root / "docs" / "Agenda.md").read_text(encoding="utf-8")
    assert "Demo.md" in agenda, (
        "docs/Agenda.md names the opening demo but never links docs/Demo.md"
    )


def test_workflows_pin_their_runner_image(repo_root):
    """A workshop about pinned, reproducible toolchains cannot float its own runner."""
    workflows = sorted((repo_root / ".github" / "workflows").glob("*.y*ml"))
    assert workflows, "no workflows found"
    floating = [
        wf.relative_to(repo_root).as_posix()
        for wf in workflows
        if re.search(r"runs-on:\s*ubuntu-latest", wf.read_text(encoding="utf-8"))
    ]
    assert not floating, f"these workflows float their runner image: {floating}"


def test_manual_deploy_steps_is_captured_as_a_field(repo_root):
    """Every scorecard cell must name a file and a field, including this one.

    The wrap-up table promises "the file, field, or step each value comes from,
    so no cell needs a guess". The manual-deploy baseline was the last value a
    participant had to remember rather than read back.
    """
    ch00 = (repo_root / "challenges" / "ch00" / "README.md").read_text(encoding="utf-8")
    assert "manualDeploySteps" in ch00, (
        "challenges/ch00 asks participants to count manual deploy steps but "
        "never captures the number in the measurement object"
    )


def test_every_deployable_template_has_a_runnable_command(repo_root: Path) -> None:
    """Each infra template the docs deploy must ship a command supplying every required parameter.

    A template described only in prose leaves the reader to invent the invocation, and
    these templates assert the shape of the resource IDs they receive, so an invented
    command fails at deploy time rather than at review time.
    """
    templates = sorted(repo_root.glob("infra/*.bicep"))
    assert templates, "no infra templates found"

    required: dict[str, set[str]] = {}
    for template in templates:
        body = template.read_text(encoding="utf-8")
        required[template.name] = {
            match.group(1)
            for match in re.finditer(r"^param\s+(\w+)\s+[\w\[\]]+(.*)$", body, re.M)
            # A parameter carrying `= <default>` need not be supplied by the caller.
            if "=" not in match.group(2)
        }

    # A parameter file supplies whatever it declares, so credit its contents to the block.
    parameter_files = {
        path.name: set(re.findall(r'"(\w+)"\s*:\s*\{\s*"value"', path.read_text(encoding="utf-8")))
        | set(re.findall(r"^param\s+(\w+)\s*=", path.read_text(encoding="utf-8"), re.M))
        for path in list(repo_root.rglob("*.bicepparam"))
        + list(repo_root.rglob("workshop/**/*.example.json"))
    }

    invoked: set[str] = set()
    gaps: list[str] = []
    for markdown in sorted(repo_root.rglob("*.md")):
        if set(markdown.relative_to(repo_root).parts) & {".git", "node_modules", ".venv"}:
            continue
        for _, block in _fenced_blocks(markdown.read_text(encoding="utf-8")):
            for match in re.finditer(r"--template-file\s+\S*?([\w.-]+\.bicep)", block):
                name = match.group(1)
                if name not in required:
                    continue
                invoked.add(name)
                # `--parameters a=1 b=2` groups several assignments onto one line, so
                # match every `name=` token rather than only line-leading ones.
                supplied = set(re.findall(r"(?:^|\s)(\w+)=", block, re.M))
                if "<parameter file>" in block or re.search(r"@?<[\w\s-]+>", block):
                    # A schematic showing the shape of the command, not a runnable one.
                    continue
                for referenced in re.findall(r"--parameters\s+'?@?\S*?([\w.-]+\.json)", block):
                    supplied |= parameter_files.get(referenced, set())
                    # The provisioner writes protected parameter files at T-1, so their
                    # contents cannot be read here; credit them with everything but the
                    # overrides the runbooks deliberately pass on the command line.
                    if referenced not in parameter_files:
                        supplied |= required[name] - {"sourceCommit", "imageDigest"}
                missing = sorted(required[name] - supplied)
                if missing:
                    rel = markdown.relative_to(repo_root)
                    gaps.append(f"{rel} deploys {name} without {missing}")

    assert not gaps, "incomplete deployment commands: " + "; ".join(gaps)

    described = {
        name
        for name in required
        if any(
            name in path.read_text(encoding="utf-8")
            for path in list(repo_root.rglob("challenges/**/*.md"))
            + list(repo_root.rglob("solutions/**/*.md"))
            + list(repo_root.rglob("workshop/**/*.md"))
        )
    }
    prose_only = sorted(described - invoked)
    assert not prose_only, (
        "these templates are described to participants but never shown as a runnable "
        f"command: {prose_only}"
    )


def test_the_three_path_debrief_is_on_the_day_one_clock(repo_root: Path) -> None:
    """The comparison of the three paths must be scheduled while all three are live.

    The debrief is the only place the workshop harvests its own premise. A day-2 slot
    makes the comparison a day cold, so both facilitator clocks must carry a day-1 hit
    that links the questions themselves.
    """
    anchor = "challenges/ch01/README.md#debrief-compare-the-three-paths"
    heading = (repo_root / "challenges" / "ch01" / "README.md").read_text(encoding="utf-8")
    assert re.search(r"^#+\s*Debrief: compare the three paths", heading, re.M | re.I), (
        "the debrief heading the schedules link to no longer exists"
    )

    for relative in ("docs/Agenda.md", "docs/DayOfCard.md"):
        content = (repo_root / relative).read_text(encoding="utf-8")
        rows = [
            line
            for line in content.splitlines()
            if "debrief" in line.lower() and anchor in line
        ]
        assert rows, f"{relative} does not schedule the Challenge 1 debrief against {anchor}"
        assert any("15:15" in row for row in rows), (
            f"{relative} schedules the debrief, but not in the day-1 15:15 slot"
        )
        assert any("never cut" in row.lower() for row in rows), (
            f"{relative} does not mark the debrief as unskippable"
        )


def test_ci_explains_why_it_builds_with_a_daemon(repo_root: Path) -> None:
    """Challenge 3 must reconcile its `docker build` with Challenge 1's `az acr build`.

    Challenge 1 teaches the no-daemon rule seven times and tells participants to reject a
    proposed local Docker build. Challenge 3 then runs one, so it has to say why.
    """
    content = (repo_root / "challenges" / "ch03" / "README.md").read_text(encoding="utf-8")
    normalized = content.lower()
    assert "docker build" in normalized, "challenge 3 no longer mentions the docker build"
    assert "daemon" in normalized, (
        "challenge 3 runs `docker build` after challenge 1 forbade it, without explaining "
        "that the rule is 'build where a daemon exists'"
    )
    assert "az acr build" in normalized, (
        "challenge 3's explanation does not name the challenge 1 command it differs from"
    )
    assert "ubuntu-24.04" in normalized, (
        "challenge 3 does not name the runner that supplies the daemon"
    )


#: Floors for the repo-wide Markdown walk. A glob list was tried first and rejected: it
#: silently stopped covering anything that moved, and `docs/*.md` would not have
#: followed `docs/` gaining a subdirectory. Asking git for every Markdown file it knows
#: about cannot go stale that way.
PLACEHOLDER_DOCUMENT_FLOOR = 50
PLACEHOLDER_BLOCK_FLOOR = 240


def test_every_command_block_placeholder_names_who_supplies_it(repo_root: Path) -> None:
    """A placeholder in a runnable block must say who supplies the value.

    An angle-bracket placeholder fails at the point a reader is least able to recover --
    mid-migration, after the deployment and the image build. Most values these blocks
    need are already reachable from the provisioned environment, so a placeholder is
    usually a gap. The ones that are genuinely unknowable share a single convention:
    they lead with the party who supplies them, or they name a secret that would be a
    worse bug to print literally. Anything else is an unfinished sentence.

    The detector is deliberately wider than the convention it enforces. An earlier
    version matched only lowercase, hyphenated names, which made it blind to a
    placeholder carrying a capital letter, a dot, a pipe or a slash -- and two such
    placeholders were living inside the very tree it claimed to protect. A guard that
    can only see compliant spellings is a guard that reports on itself.
    """
    placeholder = re.compile(r"<[A-Za-z][A-Za-z0-9._|/ -]*>")
    permitted = re.compile(
        r"<(?:facilitator|your|owner)[\w|./ -]*>|<[\w|./ -]*(?:key|password|secret|token|user)>",
        re.I,
    )
    # A pipe-separated placeholder is an enumeration, not a blank: it prints every legal
    # value at the point of use, so the failure this guard exists to prevent -- a reader
    # facing a value they cannot determine -- cannot happen. Naming a supplier instead
    # would remove information. The pipe is mandatory, so this can never match a
    # single-token blank.
    choice = re.compile(r"<[A-Za-z0-9][A-Za-z0-9._/-]*(?:\|[A-Za-z0-9][A-Za-z0-9._/-]*)+>")

    listing = subprocess.run(
        ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard", "*.md"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=True,
    ).stdout

    offenders: list[str] = []
    documents = 0
    blocks = 0
    for relative in [path for path in listing.split("\0") if path]:
        try:
            content = (repo_root / relative).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        documents += 1
        for language, block in _fenced_blocks(content):
            if language.lower() not in {"bash", "sh", "shell", "powershell", "pwsh"}:
                continue
            blocks += 1
            for line in block.splitlines():
                # Here-strings, redirections and comparisons are not placeholders.
                if "<<" in line or "-lt" in line or "->" in line:
                    continue
                remaining = choice.sub("", permitted.sub("", line))
                for found in placeholder.findall(remaining):
                    offenders.append(f"{relative}: {found} in `{line.strip()[:70]}`")

    assert documents >= PLACEHOLDER_DOCUMENT_FLOOR, (
        f"only {documents} Markdown documents were read, below the floor of "
        f"{PLACEHOLDER_DOCUMENT_FLOOR}; this guard is not looking where it claims to"
    )
    assert blocks >= PLACEHOLDER_BLOCK_FLOOR, (
        f"only {blocks} command fences were examined, below the floor of "
        f"{PLACEHOLDER_BLOCK_FLOOR}; the language filter is stale"
    )
    assert not offenders, (
        "every placeholder in a runnable block must name who supplies the value -- lead "
        "with `facilitator-`, `your-` or `owner-`, name a secret, or list the legal "
        "values pipe-separated; these do none of those: "
        + "; ".join(sorted(set(offenders)))
    )


def test_demo_steps_claimed_cold_runnable_have_a_checked_in_fixture(repo_root: Path) -> None:
    """Every evidence path the demo reads must exist, or have a named substitute.

    `docs/Demo.md` sells the workshop to someone who has never delivered it, and its
    honesty table promises which steps run from checked-in data. A step that reads the
    empty `evidence/` directory dies on its first line in front of a prospect.
    """
    demo = (repo_root / "docs" / "Demo.md").read_text(encoding="utf-8")

    referenced: set[str] = set()
    for _, block in _fenced_blocks(demo):
        referenced |= set(re.findall(r"(evidence/[\w./-]+\.json)", block))
    assert referenced, "the demo no longer reads any evidence file"

    missing = sorted(path for path in referenced if not (repo_root / path).exists())
    named_fixtures = sorted(
        set(re.findall(r"workshop/contracts/[\w./-]+\.json", demo))
    )
    absent = [name for name in named_fixtures if not (repo_root / name).exists()]
    assert not absent, f"the demo names substitute fixtures that do not exist: {absent}"
    # Counting fixtures against gaps lets five unrelated fixtures "cover" five unrelated
    # gaps, so each missing path must be matched by name. One fixture is deliberately
    # renamed on the way into the SRE Agent bundle; that alias is declared, not inferred.
    # The pattern above deliberately does not require a ``fixtures/`` path segment: it
    # used to, which made the substitute named beside step 4 invisible and left this
    # guard passing on the strength of an unrelated name several steps later.
    fixture_aliases = {"cicd-report.json": "cicd-evidence.json"}
    substitutes = {name.rsplit("/", 1)[-1] for name in named_fixtures}
    unsubstituted = [
        path
        for path in missing
        if fixture_aliases.get(path.rsplit("/", 1)[-1], path.rsplit("/", 1)[-1])
        not in substitutes
    ]
    assert not unsubstituted, (
        "demo steps read evidence files that do not exist and name no substitute: "
        + ", ".join(unsubstituted)
    )

    for name in ("ch00-pain-dotnet.json", "ch06-mttr.json"):
        fixture = repo_root / "workshop" / "contracts" / "fixtures" / "wrapup" / name
        assert fixture.exists(), f"the scorecard fixture {name} is missing"
        payload = json.loads(fixture.read_text(encoding="utf-8"))
        assert payload, f"{name} is empty"

    pain = json.loads(
        (repo_root / "workshop/contracts/fixtures/wrapup/ch00-pain-dotnet.json").read_text(
            encoding="utf-8"
        )
    )
    mttr = json.loads(
        (repo_root / "workshop/contracts/fixtures/wrapup/ch06-mttr.json").read_text(
            encoding="utf-8"
        )
    )
    # The documented sample output must stay true of the fixtures that produce it.
    assert f"{pain['catalogMedianMs']} ms" in demo, (
        "the demo's printed catalog median no longer matches its fixture"
    )
    assert f"{mttr['minutesToRecovery']} min" in demo, (
        "the demo's printed minutes-to-recovery no longer matches its fixture"
    )
    assert mttr["minutesToRecovery"] == int(
        (
            datetime.fromisoformat(mttr["recoveredAt"].replace("Z", "+00:00"))
            - datetime.fromisoformat(mttr["detectedAt"].replace("Z", "+00:00"))
        ).total_seconds()
        // 60
    ), "the mttr fixture's minutesToRecovery disagrees with its own timestamps"


# Every PowerShell command the provisioner invokes must resolve. These are the external
# cmdlets it is allowed to rely on; anything else must be a function defined in the file.
# A typo in an internal helper name is not a parse error, so the pwsh parse gate cannot
# see it -- the script fails at run time, on the VM, during provisioning.
PROVISIONER_EXTERNAL_CMDLETS = frozenset(
    {
        "Add-Content", "Add-Type", "Copy-Item", "Disable-ScheduledTask",
        "Enable-ScheduledTask", "Expand-Archive", "Get-AuthenticodeSignature",
        "Get-ChildItem", "Get-CimInstance", "Get-Content", "Get-Date", "Get-FileHash",
        "Get-Item", "Get-ItemProperty", "Get-ScheduledTask", "Get-Service",
        "Invoke-WebRequest", "Join-Path", "Move-Item", "New-Item", "New-Object",
        "New-ScheduledTaskAction", "New-ScheduledTaskPrincipal",
        "New-ScheduledTaskSettingsSet", "New-ScheduledTaskTrigger", "New-TimeSpan",
        "Out-Null", "Pop-Location", "Push-Location", "Register-ScheduledTask",
        "Remove-Item", "Restart-Service", "Select-Object", "Select-String", "Set-Acl",
        "Set-Content", "Set-ItemProperty", "Set-Service", "Set-StrictMode",
        "Sort-Object", "Split-Path", "Start-Process", "Start-ScheduledTask",
        "Start-Service", "Start-Sleep", "Stop-Process", "Stop-ScheduledTask",
        "Test-Path", "Where-Object", "Write-Host",
    }
)


def test_provisioner_invokes_only_commands_that_resolve(repo_root: Path) -> None:
    """Every Verb-Noun the provisioner calls is defined in-file or a known cmdlet."""
    script = repo_root / "baseInfra" / "scripts" / "provision-vm.ps1"
    source = script.read_text(encoding="utf-8")

    defined = set(re.findall(r"(?m)^\s*function\s+([A-Za-z]+-[A-Za-z]+)", source))
    assert len(defined) >= PROVISIONER_FUNCTION_FLOOR, (
        f"only {len(defined)} functions were parsed out of the provisioner; the "
        "declaration pattern has stopped matching and every call below would "
        "resolve against an empty set"
    )
    assert "Write-ProvisionLog" in defined, (
        "the provisioner's own logging helper is missing -- this guard is "
        "reading the wrong file or the naming convention changed"
    )

    invoked = {
        match.group(1)
        for match in re.finditer(
            r"(?m)(?:^|[|(){}&]|\s)\s*([A-Z][a-z]+-[A-Z][A-Za-z]+)\b", source
        )
    }
    unresolved = sorted(invoked - defined - PROVISIONER_EXTERNAL_CMDLETS)

    assert not unresolved, (
        "provision-vm.ps1 invokes commands that are neither defined in the file nor "
        f"known cmdlets: {unresolved}. If one is a real cmdlet, add it to "
        "PROVISIONER_EXTERNAL_CMDLETS; otherwise it is a typo that would only surface "
        "on the VM, mid-provisioning."
    )


def _persisted_catalog_variables(repo_root: Path) -> set[str]:
    """Names the provisioner persists at Machine scope, read live from the script."""
    source = (repo_root / "baseInfra" / "scripts" / "provision-vm.ps1").read_text(
        encoding="utf-8"
    )
    persisted: set[str] = set()
    for block in re.finditer(
        r"Set-CatalogEnvironmentForParticipants\s+-Settings\s+@\{(.*?)\n\s*\}",
        source,
        re.DOTALL,
    ):
        persisted.update(re.findall(r"(CATALOG_[A-Z_]+)\s*=", block.group(1)))
    return persisted


def test_ch01_runbooks_read_only_catalog_variables_that_exist(repo_root: Path) -> None:
    """Every $env:CATALOG_* a ch01 runbook reads is set locally or by the provisioner."""
    persisted = _persisted_catalog_variables(repo_root)
    assert persisted, (
        "no Machine-scope CATALOG_* persistence found in provision-vm.ps1 -- "
        "participant shells would see none of these variables"
    )

    offenders: list[str] = []
    runbooks = sorted(repo_root.glob("solutions/ch01-*/*/README.md"))
    assert runbooks, "no ch01 runbooks found"

    for runbook in runbooks:
        content = runbook.read_text(encoding="utf-8")
        assigned_at: dict[str, int] = {}
        for match in re.finditer(r"(?m)^\s*\$env:(CATALOG_[A-Z_]+)\s*=", content):
            assigned_at.setdefault(match.group(1), match.start())

        for match in re.finditer(r"\$env:(CATALOG_[A-Z_]+)", content):
            name = match.group(1)
            if name in persisted:
                continue
            first_assignment = assigned_at.get(name)
            if first_assignment is not None and first_assignment <= match.start():
                continue
            line = content[: match.start()].count("\n") + 1
            offenders.append(
                f"{runbook.relative_to(repo_root)}:{line} reads $env:{name}"
            )

    assert not offenders, (
        "ch01 runbooks read catalog variables that are neither assigned earlier in the "
        "same file nor persisted at Machine scope by provision-vm.ps1, so they expand "
        "to empty in a participant's shell:\n  " + "\n  ".join(offenders)
    )


# Variables the shell or the Azure CLI session provides; a deployment block may read
# these without binding them itself.
AMBIENT_SHELL_VARIABLES = frozenset(
    {"HOME", "PATH", "PWD", "USER", "SHELL", "TMPDIR", "RANDOM", "HOSTNAME"}
)

#: Floors for the repo-wide walk, matching the placeholder guard's scope. Widened twice:
#: from `az deployment` blocks in `solutions/**` (three blocks), then from blocks calling
#: `az` at all (thirty-two), which still could not see an unbound variable in a block of
#: three `shasum` lines. The rule a reader actually relies on has nothing to do with the
#: Azure CLI: a block must give a value to everything it expands.
VARIABLE_BINDING_DOCUMENT_FLOOR = 50
VARIABLE_BINDING_BLOCK_FLOOR = 140


def _outside_single_quotes(body: str) -> str:
    """Return only the text bash would expand, with single-quoted spans removed.

    Bash expands nothing inside `'…'`, and there is no escaping *inside* those quotes:
    the `'\\''` idiom that jq programs use everywhere is a close, an escaped literal
    quote, and a reopen. Stripping `'[^']*'` with a regex mis-aligns on that idiom and
    starts reading quoted spans as unquoted -- which reports a jq `--arg` name as an
    unbound shell variable, and calls a correct block a defect. Scanning the quote
    state directly is the only way to get it right. A backslash outside the quotes
    escapes the next character, which is how `\\$filter` stays an OData parameter.
    """
    kept: list[str] = []
    quoted = False
    index = 0
    while index < len(body):
        character = body[index]
        if quoted:
            quoted = character != "'"
        elif character == "'":
            quoted = True
        elif character == "\\" and index + 1 < len(body):
            index += 2
            continue
        else:
            kept.append(character)
        index += 1
    return "".join(kept)


def _shell_expansions(body: str) -> set[str]:
    """Variables bash would actually expand in this block."""
    return set(
        re.findall(r"\$\{?([A-Za-z_][A-Za-z0-9_]*)\}?", _outside_single_quotes(body))
    )


def _shell_bindings(body: str) -> set[str]:
    """Every name this block gives a value, by any form the runbooks actually use."""
    bound = set(re.findall(r"(?:^|\s)([A-Za-z_][A-Za-z0-9_]*)=", body))
    # The `: "${VAR:?why}"` guard idiom, and `${VAR:-default}`.
    bound |= set(re.findall(r"\$\{([A-Za-z_][A-Za-z0-9_]*):[?-]", body))
    bound |= set(re.findall(r"(?m)^\s*export\s+([A-Za-z_][A-Za-z0-9_]*)", body))
    # `while IFS= read -r nic_id` and `for query_name in …` both bind a loop variable.
    bound |= set(re.findall(r"\bread\s+(?:-r\s+)?([A-Za-z_][A-Za-z0-9_]*)", body))
    bound |= set(re.findall(r"\bfor\s+([A-Za-z_][A-Za-z0-9_]*)\s+in\b", body))
    return bound


def test_every_bash_block_binds_every_variable_it_expands(repo_root: Path) -> None:
    """No bash block expands a variable its document never gives a value.

    An unbound variable does not announce itself. `--ids ""` fails inside Azure with a
    message about the service rather than about the runbook, and an unbound value fed to
    a query *time window* is worse still: it returns a plausible, wrong answer instead of
    an error, which is the one outcome a chapter about reasoning from evidence cannot
    afford. Neither of those is an Azure CLI problem, which is why the trigger is every
    bash block rather than the ones that happen to call `az`.

    Bindings accumulate across the blocks of a single document, because a runbook is one
    shell session read top to bottom, not a set of independent scripts.
    """
    listing = subprocess.run(
        ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard", "*.md"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=True,
    ).stdout

    offenders: list[str] = []
    documents = 0
    blocks = 0
    for relative in [path for path in listing.split("\0") if path]:
        try:
            content = (repo_root / relative).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        documents += 1
        bound: set[str] = set()
        for block in re.finditer(r"```bash\n(.*?)```", content, re.DOTALL):
            body = block.group(1)
            bound |= _shell_bindings(body)
            blocks += 1
            line = content[: block.start()].count("\n") + 1
            for name in sorted(_shell_expansions(body) - bound - AMBIENT_SHELL_VARIABLES):
                offenders.append(
                    f"{relative} (block at line {line}) expands ${name} without binding it"
                )

    assert documents >= VARIABLE_BINDING_DOCUMENT_FLOOR, (
        f"only {documents} Markdown documents were read, below the floor of "
        f"{VARIABLE_BINDING_DOCUMENT_FLOOR}; this guard is not looking where it claims to"
    )
    assert blocks >= VARIABLE_BINDING_BLOCK_FLOOR, (
        f"only {blocks} bash blocks were examined, below the floor of "
        f"{VARIABLE_BINDING_BLOCK_FLOOR}; the fence filter is stale"
    )

    assert not offenders, (
        "these blocks expand variables nothing binds, so they submit empty values and "
        "fail inside Azure instead of failing with a sentence:\n  "
        + "\n  ".join(offenders)
        + "\n\nBind it from the handoff, or guard it with the house idiom: "
        ': "${VAR:?what the reader should supply}"'
    )


def test_pain_fixture_counts_match_the_real_corpus(repo_root: Path) -> None:
    """The wrap-up pain fixture reports the corpus that actually ships."""
    actual_images = len(list((repo_root / "data" / "images").glob("*.png")))
    assert actual_images, "no catalog images found on disk"

    fixture_path = (
        repo_root / "workshop" / "contracts" / "fixtures" / "wrapup" / "ch00-pain-dotnet.json"
    )
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))

    assert fixture["imageFilesOnDisk"] == actual_images, (
        f"{fixture_path.relative_to(repo_root)} claims "
        f"{fixture['imageFilesOnDisk']} images but {actual_images} ship in data/images. "
        "The demo narrates this number as a fact about the real application."
    )

    # The same count is asserted in prose; a fixture that drifts from the chapters
    # makes the facilitator contradict the participant's own screen.
    for doc in ("challenges/ch00/README.md", "solutions/ch00/README.md"):
        content = (repo_root / doc).read_text(encoding="utf-8")
        assert str(actual_images) in content, (
            f"{doc} no longer states the real corpus size of {actual_images}"
        )


# Azure decodes osProfile.customData into a binary array of at most 65,535 bytes.
AZURE_CUSTOM_DATA_LIMIT_BYTES = 65_535


def test_provisioner_custom_data_fits_azure_limit(repo_root: Path) -> None:
    """The gzipped provisioner still fits in Azure's customData budget.

    This repository has already shipped a payload of 65,584 bytes -- 49 over -- and the
    only symptom was a failed deployment at T-1. Terraform cannot catch it, because the
    limit is enforced by the Azure API, not by the provider.
    """
    module = repo_root / "baseInfra" / "terraform" / "modules" / "user_environment"
    locals_tf = (module / "locals.tf").read_text(encoding="utf-8")

    script = (repo_root / "baseInfra" / "scripts" / "provision-vm.ps1").read_bytes()
    # mtime=0 so the digest is reproducible; terraform's base64gzip is the same
    # deflate stream, and the header is a fixed 10 bytes either way.
    buffer = io.BytesIO()
    with gzip.GzipFile(fileobj=buffer, mode="wb", mtime=0) as handle:
        handle.write(script)
    script_gzip_base64 = base64.b64encode(buffer.getvalue()).decode("ascii")

    # Rebuild the wrapper from locals.tf itself, so the guard tracks edits to it.
    wrapper_lines = re.search(
        r"provisioner_wrapper\s*=\s*join\(\"\\n\",\s*\[(.*?)\n\s*\]\)",
        locals_tf,
        re.DOTALL,
    )
    assert wrapper_lines, "could not locate provisioner_wrapper in locals.tf"
    wrapper = wrapper_lines.group(1)
    wrapper = wrapper.replace("${base64gzip(file(local.provisioner_path))}", script_gzip_base64)
    wrapper_bytes = len(wrapper.encode("utf-8"))

    # Nine fields of bounded length; model them at their realistic maximum so the guard
    # errs toward failing early rather than passing a payload that Azure will reject.
    worst_case_payload = json.dumps(
        {
            "databasePassword": "x" * 64,
            "performanceApiKey": "x" * 64,
            "facilitatorPrincipalName": "x" * 128,
            "facilitatorPrincipalObjectId": "0" * 36,
            "resourceGroupName": "x" * 90,
            "teamName": "x" * 64,
            "adminUsername": "x" * 64,
            "migrationSourceVirtualNetworkResourceId": "/subscriptions/" + "x" * 200,
            "migrationSourceVmResourceId": "/subscriptions/" + "x" * 200,
        }
    )
    payload_bytes = len(base64.b64encode(worst_case_payload.encode("utf-8")))

    markers = len("MICROHACK_CUSTOM_DATA_V2\n") + len("\nMICROHACK_PROVISIONER_START\n")
    total = wrapper_bytes + payload_bytes + markers
    headroom = AZURE_CUSTOM_DATA_LIMIT_BYTES - total

    assert total < AZURE_CUSTOM_DATA_LIMIT_BYTES, (
        f"customData would be {total:,} bytes, {-headroom:,} over Azure's "
        f"{AZURE_CUSTOM_DATA_LIMIT_BYTES:,}-byte limit. provision-vm.ps1 is "
        f"{len(script):,} bytes raw and {len(script_gzip_base64):,} gzipped+base64. "
        "Move work out of the provisioner and into the source archive it downloads."
    )
    print(f"customData: {total:,} bytes, {headroom:,} bytes of headroom")


def _source_tree_writes(script: str) -> list[tuple[int, str]]:
    """(offset, repo-relative path) for every file the provisioner writes into $SourceRoot."""
    # Splice out backtick line continuations so a single cmdlet call is one line, keeping
    # byte offsets identical so the caller can still resolve them to line numbers.
    script = re.sub(
        r"`\n(\s*)", lambda match: " " * (2 + len(match.group(1))), script
    )

    # $Var = Join-Path $SourceRoot 'a\b'   and one level of indirection through those vars.
    variables: dict[str, str] = {}
    for match in re.finditer(
        r"\$(\w+)\s*=\s*Join-Path\s+\$SourceRoot\s+'([^']+)'", script
    ):
        variables[match.group(1)] = match.group(2).replace("\\", "/")

    writes: list[tuple[int, str]] = []

    def record(offset: int, path: str) -> None:
        writes.append((offset, path.replace("\\", "/").lstrip("/")))

    # -Path (Join-Path $Var 'name') on a writing cmdlet
    for match in re.finditer(
        r"(Set-Content|Out-File|Copy-Item)\b[^\n]*?\s-(?:Path|Destination|LiteralPath)\s+"
        r"\(Join-Path\s+\$(\w+)\s+'([^']+)'\)",
        script,
        re.DOTALL,
    ):
        base = match.group(2)
        if base == "SourceRoot":
            record(match.start(), match.group(3))
        elif base in variables:
            record(match.start(), f"{variables[base]}/{match.group(3)}")

    # -Path $Var, where $Var was itself built from $SourceRoot
    for match in re.finditer(
        r"(?:Set-Content|Out-File|Copy-Item)\b[^\n]*?\s-(?:Path|Destination|LiteralPath)\s+\$(\w+)\b",
        script,
    ):
        name = match.group(1)
        target = re.search(
            rf"\${name}\s*=\s*Join-Path\s+\$SourceRoot\s+'([^']+)'", script
        )
        if target:
            record(match.start(), target.group(1))

    return writes


def test_provisioner_written_files_cannot_dirty_the_participant_worktree(
    repo_root: Path,
) -> None:
    """Anything written into the source tree after the baseline commit must be ignored.

    Challenge 1's first executable gate on both Copilot paths asserts a clean worktree.
    `Initialize-SourceRepository` runs `git add --all`, so files written *before* it are
    inside the baseline commit and harmless. Files written *after* it are untracked, and
    every one of them fails that gate before the participant has done anything.
    """
    script = _provisioner(repo_root)

    baseline = script.find("Initialize-SourceRepository -SourceCommit")
    assert baseline > 0, "the baseline commit call site moved or was removed"

    writes = _source_tree_writes(script)
    assert writes, "no source-tree writes detected -- this guard has stopped working"
    assert any(path.endswith("global.json") for _, path in writes), (
        "the provisioner no longer writes global.json; if that is intentional, this "
        "guard's known-offender check needs updating"
    )

    offenders: list[str] = []
    for offset, path in writes:
        if offset < baseline:
            continue
        ignored = subprocess.run(
            ["git", "check-ignore", "-q", path],
            cwd=repo_root,
            capture_output=True,
            check=False,
        )
        if ignored.returncode != 0:
            line = script[:offset].count("\n") + 1
            offenders.append(f"provision-vm.ps1:{line} writes {path}")

    assert not offenders, (
        "the provisioner writes these into the source tree after the baseline commit, "
        "so `git status --porcelain` is non-empty and Challenge 1's cleanliness gate "
        "fails on a freshly provisioned VM:\n  " + "\n  ".join(offenders)
        + "\n\nAdd each to .gitignore, or write it outside the source tree."
    )


def test_bash_fences_in_powershell_chapters_name_their_shell(repo_root: Path) -> None:
    """A bash block on a PowerShell-mandated VM says which shell it needs.

    The workshop VM runs PowerShell by default and gets `bash` only from the pinned Git
    for Windows install. A bare ```bash fence in a chapter whose "Where you work" section
    mandates the VM reads as "paste this into the terminal you already have open", which
    fails with a syntax error that has nothing to do with the participant's real problem.
    """
    offenders: list[str] = []
    checked = 0

    documents = sorted(
        {
            *repo_root.glob("challenges/**/README.md"),
            *repo_root.glob("solutions/**/README.md"),
        }
    )
    for document in documents:
        content = document.read_text(encoding="utf-8")
        if "Where you work" not in content:
            continue
        # Only chapters that actually mandate PowerShell somewhere.
        if "```powershell" not in content:
            continue
        checked += 1

        lines = content.splitlines()
        for index, line in enumerate(lines):
            if line.strip() != "```bash":
                continue
            # The ten lines above must tell the reader this needs a different shell.
            window = "\n".join(lines[max(0, index - 10) : index]).lower()
            if "bash" in window:
                continue
            offenders.append(f"{document.relative_to(repo_root)}:{index + 1}")

    assert checked, "no PowerShell-mandating chapters found -- guard is not running"
    assert not offenders, (
        "these ```bash fences sit in chapters that mandate PowerShell on the VM, with "
        "no mention of Git Bash in the ten lines above them, so a participant pastes "
        "bash into a PowerShell prompt:\n  " + "\n  ".join(offenders)
    )


# Steps that cannot run until the participant's commit exists on their own remote.
PUBLISHED_COMMIT_CONSUMERS = ("--source-commit", "az acr build", "imageDigest=")


def _fenced_regions(content: str) -> list[tuple[int, int]]:
    """(start, end) offsets of every fenced code block, so prose can be ignored."""
    fences = [match.start() for match in re.finditer(r"(?m)^```", content)]
    return list(zip(fences[::2], fences[1::2]))


def test_publish_gate_precedes_every_published_commit_consumer(repo_root: Path) -> None:
    """The push that publishes the commit comes before anything that consumes it.

    `az acr build`, `--source-commit` and `imageDigest=` all identify an image by a
    commit that must already exist on the participant's remote. A chapter that reorders
    the push below them reads fine and fails on the day, so the ordering is asserted
    rather than trusted.
    """
    checked = 0
    offenders: list[str] = []

    for runbook in sorted(repo_root.glob("solutions/ch01-*/*/README.md")):
        content = runbook.read_text(encoding="utf-8")
        regions = _fenced_regions(content)

        def first_in_code(needle: str) -> int | None:
            for start, end in regions:
                index = content.find(needle, start, end)
                if index != -1:
                    return index
            return None

        publish = first_in_code("git push")
        if publish is None:
            continue
        checked += 1

        for consumer in PUBLISHED_COMMIT_CONSUMERS:
            found = first_in_code(consumer)
            if found is not None and found < publish:
                offenders.append(
                    f"{runbook.relative_to(repo_root)}: `{consumer}` at line "
                    f"{content[:found].count(chr(10)) + 1} runs before the publish gate "
                    f"at line {content[:publish].count(chr(10)) + 1}"
                )

    assert checked, "no ch01 runbook with a publish gate found -- guard is not running"
    assert not offenders, (
        "these runbooks consume a published commit before publishing it:\n  "
        + "\n  ".join(offenders)
    )


# Build-phase codes are internal planning vocabulary. `docs/RewritePlan.md` and
# `docs/ImplementationLog.md` are the historical record and keep them by design.
PHASE_CODE_HISTORY = (
    "docs/RewritePlan.md",
    "docs/ImplementationLog.md",
    ".azure/deployment-plan.md",
)

# Azure ships real product identifiers shaped exactly like phase codes: Defender for
# Servers Plan 2, and the Premium SSD disk tiers. They are allowed per file and per
# token, so a genuine phase code in one of these same files still fails the guard.
AZURE_P_IDENTIFIERS = {
    "challenges/ch05-defender/README.md": {"P2"},
    "docs/CommonErrors.md": {"P2", "P10"},
    "docs/CostEstimate.md": {"P1", "P2", "P10"},
    "tests/acceptance/catalog_acceptance/defender_evidence.py": {"P2", "p2"},
    "tests/acceptance/tests/test_ch05_defender_contracts.py": {"P2"},
    "tests/acceptance/tests/test_contract_assets.py": {"P2"},
    "solutions/ch05-defender/README.md": {"P2"},
    "workshop/contracts/defender-evidence.example.json": {"p2"},
}

# An entry in the table above is necessary but not sufficient. The occurrence must also
# sit near words that only appear when the subject really is an Azure product, so that
# adding a file and token to the table cannot by itself silence a genuine leak.
#
# Purely contextual exemption -- dropping the table and trusting these words alone --
# was measured and rejected. The generic members of any such vocabulary are ordinary
# English: this repository's own planning record is named for the word "plan", and
# "tier" and "disk" appear throughout the cost and infrastructure prose. A leak sitting
# anywhere near that vocabulary would be exempted silently, everywhere, with nothing in
# review to notice. Requiring both means a new Azure identifier costs one reviewable
# table line, and the failure message below dictates that line verbatim.
AZURE_IDENTIFIER_CONTEXT = (
    "defender",
    "premium",
    "ssd",
    "disk",
    "sku",
    "pricing",
    "plan 2",
    "enforced",
    "enablement",
    "coverage",
)

#: How far either side of the token the Azure vocabulary may sit. Wide, because the
#: table is the primary gate and this is the second of two locks, not the only one.
AZURE_CONTEXT_BEFORE = 200
AZURE_CONTEXT_AFTER = 80

# Upper case is always a phase code. Lower case is only a phase code when it is welded
# into an identifier -- a snake_case test name, a hyphenated Azure deployment name, or
# a container image tag. A bare lower-case percentile such as the ninety-fifth is
# latency notation, which challenges 2 and 4 use correctly and constantly, so matching
# case-blind would bury the guard in noise.
PHASE_CODE_PATTERN = re.compile(r"\bP\d+\b|(?<=[_\-:])p\d+\b|\bp\d+(?=[_\-:])")

# The scan saw 530 decodable files when this floor was set. A floor rather than a bare
# non-empty check: both of this guard's past truncations still saw plenty of files --
# 172 under index-only listing, and 293 under the six-extension pathspec -- so ``> 0``
# would have reported green through either one.
PHASE_CODE_SCAN_FLOOR = 450

# Every repository-walking guard enumerates with this argv. The floors above cannot
# defend it: the index alone already clears them, so dropping ``--others`` would leave
# untracked work invisible while the count stayed green. The two guards below pin the
# argv's behaviour and its adoption instead of its size.
GIT_ENUMERATION_ARGV = ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"]
GIT_ENUMERATION_CALL_SITE_FLOOR = 8
# Two guards ask about trackedness itself -- "is this committed?" and "which files under
# this tree are stray?" -- so a bare listing is correct there. The count is pinned rather
# than forbidden: a narrowed walk elsewhere shows up as a third site.
GIT_TRACKED_ONLY_CALL_SITES = 2


def test_the_repository_enumeration_sees_files_that_are_not_yet_committed() -> None:
    """The shared argv reports untracked work, not just the index.

    A file a facilitator has written but not committed is exactly the file most likely
    to break a run, so every walking guard must see it. Proved against a scratch
    repository because the real one has no untracked files to prove it with.
    """
    with tempfile.TemporaryDirectory() as scratch:
        root = Path(scratch)
        (root / "committed.md").write_text("committed\n", encoding="utf-8")
        (root / "never-added.md").write_text("untracked\n", encoding="utf-8")
        for argv in (
            ["git", "init", "-q"],
            ["git", "add", "committed.md"],
            ["git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "seed"],
        ):
            subprocess.run(argv, cwd=root, check=True, capture_output=True)
        listed = subprocess.run(
            GIT_ENUMERATION_ARGV, cwd=root, check=True, capture_output=True, text=True
        ).stdout.split("\0")
        seen = {entry for entry in listed if entry}
    assert seen == {"committed.md", "never-added.md"}, (
        f"the shared enumeration argv reported {sorted(seen)}; a guard using it would "
        "not see uncommitted work"
    )


def test_every_repository_walk_uses_the_enumeration_that_sees_uncommitted_work() -> None:
    """The proven argv is the one the guards actually call.

    Pairs with the behavioural guard above: that one proves the argv is right, this one
    proves no call site has quietly reverted to a narrower listing.
    """
    source = Path(__file__).read_text(encoding="utf-8")
    adopted = source.count('"--cached", "--others", "--exclude-standard"')
    narrower = re.findall(r'"git",\s*"ls-files"(?![^\]]*--others)[^\]]*\]', source)
    assert adopted >= GIT_ENUMERATION_CALL_SITE_FLOOR, (
        f"only {adopted} call sites enumerate with the proven argv, below "
        f"{GIT_ENUMERATION_CALL_SITE_FLOOR}; a walk has been narrowed"
    )
    assert len(narrower) <= GIT_TRACKED_ONLY_CALL_SITES, (
        f"{len(narrower)} call sites enumerate without --others, above the "
        f"{GIT_TRACKED_ONLY_CALL_SITES} that ask about trackedness on purpose; a walk "
        f"has been narrowed and would miss uncommitted work: {narrower}"
    )


PARTICIPANT_WRITABLE_ROOTS = ("dotnet", "java", "evidence")

_PARTICIPANT_LITERAL_PATH = re.compile(
    r"/\s*[\"'](?:" + "|".join(PARTICIPANT_WRITABLE_ROOTS) + r")[\"']"
)

# The two sites that legitimately compose such a path: a pytest `tmp_path` scratch
# directory and the golden-fixture root. Neither asserts anything about what the
# workshop ships.
PARTICIPANT_LITERAL_EXEMPT_SITES = 2


def test_no_new_shipped_baseline_assertion_reads_the_working_tree() -> None:
    """Stop the fifth instance of a defect class this file produced four times.

    Four tests asserted a property the workshop *ships* -- a locked SDK, a pinned Spring
    Boot, the shape of the reference tree, the frameworks CI must declare -- while
    resolving that assertion against `dotnet/`, `java/` or `evidence/`, which is exactly
    where a participant is told to work. Challenge 1 mandates retargeting the runtime and
    authoring a Dockerfile, so each guard turned from a statement about the workshop into
    a failure of doing the workshop. Three went red with messages that named no cause; the
    fourth silently stopped requiring the source framework of CI, which is worse.

    The route in never mattered. Two used `git ls-files`, two used `rglob` and
    `read_text`, so an audit that searched for a *mechanism* cleared the file while two
    instances were still in it. This searches for the *question* instead: a literal
    participant-writable segment composed into a path. Verified against the pre-fix tree,
    where it catches the SDK-pin guard's hardcoded reach into the .NET stack at authorship.

    Composing the path from a variable is fine and deliberately not matched -- the
    reference-shape guard's `repo_root / stack` feeds `_committed_files_under`, which
    reads `HEAD`. What is being caught is the hardcoded reach into a participant's tree.
    """
    source = Path(__file__).read_text(encoding="utf-8")
    assert len(source) >= 100_000, (
        f"only {len(source)} characters read from this module; the scan did not happen "
        "and an empty read would report no offenders"
    )
    hits = _PARTICIPANT_LITERAL_PATH.findall(source)
    assert len(hits) <= PARTICIPANT_LITERAL_EXEMPT_SITES, (
        f"{len(hits)} sites compose a path with a literal participant-writable segment "
        f"({', '.join(PARTICIPANT_WRITABLE_ROOTS)}), above the "
        f"{PARTICIPANT_LITERAL_EXEMPT_SITES} exempt scratch and fixture sites. If this is "
        "an assertion about what the workshop ships, read the committed tree with "
        "_committed_paths, _committed_text or _committed_files_under instead -- otherwise "
        "it will fail the participant for doing the exercise. If it genuinely asks about "
        f"the working tree, raise the ceiling and say which category it is. Hits: {hits}"
    )


def test_participant_writable_roots_cover_every_stack_the_workshop_teaches() -> None:
    """Keep the guard above honest when a third stack is added.

    `PARTICIPANT_WRITABLE_ROOTS` is a hand-maintained tuple, so a new stack would be
    modernized by participants while the guard quietly declined to watch it.
    """
    missing = sorted(set(MODERNIZATION_SURFACE) - set(PARTICIPANT_WRITABLE_ROOTS))
    assert not missing, (
        f"these stacks are modernized by participants but are not listed in "
        f"PARTICIPANT_WRITABLE_ROOTS, so shipped-baseline assertions against them are "
        f"unguarded: {missing}"
    )


def test_no_build_phase_codes_reach_a_reader(repo_root: Path) -> None:
    """Nothing a participant or facilitator reads refers to a build phase by number.

    Phase codes name the order this repository was built in, not anything a reader can
    see. They had leaked into runbooks, contract guides, test filenames, Azure
    deployment names, container image tags, and the error strings the evidence
    validators print, where they explain nothing.

    Every file git knows about is scanned, tracked or not, and the file types are not
    filtered. This guard carried two truncations, one at a time and a round apart: it
    listed only the git index, and later it filtered to a six-extension pathspec that
    showed it 293 of 737 files, hiding every ``.java`` and ``.cs`` in the repository
    while it reported green.
    """
    listing = subprocess.run(
        ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    candidates = [path for path in listing.split("\0") if path]

    offenders: list[str] = []
    exercised: dict[str, set[str]] = {}
    scanned = 0
    for relative in candidates:
        if relative in PHASE_CODE_HISTORY:
            continue
        try:
            content = (repo_root / relative).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue  # Binary, or a symlink git lists but the tree does not hold.
        scanned += 1
        for match in PHASE_CODE_PATTERN.finditer(content):
            before = content[max(0, match.start() - 24) : match.start()]
            after = content[match.end() : match.end() + 1]
            if before.endswith(("'", '"')) and after in ("'", '"'):
                continue  # A quoted literal is naming the token, not using it.

            line = content[: match.start()].count(chr(10)) + 1
            if match.group(0) in AZURE_P_IDENTIFIERS.get(relative, ()):
                # Recorded before the context check, so that a listed token which does
                # occur is never also reported as stale. The two failures have different
                # remedies and must not be able to masquerade as one another.
                exercised.setdefault(relative, set()).add(match.group(0))
                window = content[
                    max(0, match.start() - AZURE_CONTEXT_BEFORE) : match.end()
                    + AZURE_CONTEXT_AFTER
                ].lower()
                if any(word in window for word in AZURE_IDENTIFIER_CONTEXT):
                    continue
                offenders.append(
                    f"{relative}:{line}: {match.group(0)} is listed as an Azure "
                    "identifier but nothing within "
                    f"{AZURE_CONTEXT_BEFORE} characters names an Azure product, so the "
                    "listing is doing the work a phase code would need it to do"
                )
                continue
            offenders.append(f"{relative}:{line}: {match.group(0)}")

    assert scanned >= PHASE_CODE_SCAN_FLOOR, (
        f"only {scanned} files were scanned, below the floor of "
        f"{PHASE_CODE_SCAN_FLOOR}; this guard is not looking where it claims to"
    )
    # A listing that exempts nothing is a listing nobody can evaluate. Left in place it
    # becomes the obvious hiding spot: pre-declare a token, add the leak later, and the
    # guard never objects. Every entry has to be earning its place right now.
    stale = sorted(
        f"{document} -> {token}"
        for document, tokens in AZURE_P_IDENTIFIERS.items()
        for token in tokens
        if token not in exercised.get(document, set())
    )
    assert not stale, (
        "these Azure-identifier exemptions no longer match anything and must be "
        "deleted:\n  " + "\n  ".join(stale)
    )
    assert not offenders, (
        "build-phase codes are reader-visible; name the challenge or the component "
        "instead. If one of these is a genuine Azure product identifier, add it to "
        "AZURE_P_IDENTIFIERS as `\"<path>\": {\"<token>\"}` -- the surrounding prose "
        "must already name the product:\n  " + "\n  ".join(offenders[:20])
    )


def test_participant_catalog_variables_match_the_application_values(repo_root: Path) -> None:
    """What a participant's shell reports must be what the application actually uses.

    The values are stated twice: once inside the here-string that becomes the scheduled
    task's start script, and once in the Machine-scope set that participant shells read.
    Nothing binds the two copies, so a change to one silently makes every runbook that
    echoes a variable print a value the running application does not have.
    """
    script = (repo_root / "baseInfra/scripts/provision-vm.ps1").read_text(encoding="utf-8")
    marker = "Set-CatalogEnvironmentForParticipants -Settings @{"
    assert script.count(marker) == 2, "expected one persisted set per stack"

    mismatches: list[str] = []
    for index, chunk in enumerate(script.split(marker)[1:], start=1):
        persisted = dict(
            re.findall(r"(CATALOG_\w+)\s*=\s*'([^']*)'", chunk.split("}", 1)[0])
        )
        assert persisted, f"stack {index} persists nothing"
        assert "CATALOG_DATABASE_PASSWORD" not in persisted, (
            "the database password must not be persisted to Machine scope"
        )
        # The start script is the text immediately above, back to its own function.
        preceding = script.split(marker)[index - 1]
        start_script = preceding[preceding.rfind("\nfunction ") :]
        applied = dict(re.findall(r"\$env:(CATALOG_\w+)\s*=\s*'([^']*)'", start_script))
        for name, value in sorted(persisted.items()):
            if name not in applied:
                continue  # Participant-only conveniences are checked below.
            if applied[name] != value:
                mismatches.append(
                    f"stack {index}: {name} is {value!r} for participants but "
                    f"{applied[name]!r} for the application"
                )

    # CATALOG_BASE_URL is not in either start script; the provisioner derives the same
    # URL for its own smoke test, and that is the one the application actually answers on.
    ports = re.search(
        r"\$Port\s*=\s*if\s*\(\$Stack -eq 'dotnet'\)\s*\{\s*(\d+)\s*\}\s*else\s*\{\s*(\d+)\s*\}",
        script,
    )
    assert ports, "the provisioner no longer derives a smoke-test port"
    for index, expected in enumerate(ports.groups(), start=1):
        chunk = script.split(marker)[index].split("}", 1)[0]
        found = re.search(r"CATALOG_BASE_URL\s*=\s*'([^']*)'", chunk)
        assert found, f"stack {index} persists no base URL"
        if not found.group(1).endswith(f":{expected}"):
            mismatches.append(
                f"stack {index}: participants are told {found.group(1)} but the smoke "
                f"test uses port {expected}"
            )

    assert not mismatches, "participant and application values disagree:\n  " + "\n  ".join(
        mismatches
    )


def test_no_generated_python_metadata_is_tracked(repo_root):
    """Generated packaging metadata must not be committed.

    ``*.egg-info`` is rewritten by every ``uv run`` that touches an editable
    install, so tracking it hands each facilitator a dirty working tree they did
    not cause and a merge conflict they cannot resolve meaningfully.
    """
    tracked = subprocess.run(
        ["git", "ls-files"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.splitlines()

    # Bare ``ls-files`` is correct here -- "is it tracked" is a question about the
    # index, unlike the phase-code guard which must also see untracked work. The floor
    # guards the other failure mode: an empty listing would pass this vacuously.
    assert len(tracked) >= 400, (
        f"git lists only {len(tracked)} tracked files; this guard is not running "
        "against the real repository"
    )
    generated = sorted(
        path
        for path in tracked
        if "/__pycache__/" in path
        or path.endswith(".pyc")
        or re.search(r"(^|/)[^/]+\.egg-info/", path)
    )
    assert not generated, "generated metadata is tracked in git:\n  " + "\n  ".join(
        generated
    )


# Every challenge chapter is exempt from nothing here except the wrap-up, which is a
# debrief rather than a challenge and so has no goal of its own to state.
TEACHING_CONTRACT_HEADINGS = (
    "## Your goal",
    "## The concept",
    "## Success criteria",
    "## Hints",
    "## If it goes wrong",
)
CHALLENGE_CHAPTER_COUNT = 12


def test_every_challenge_keeps_the_microhack_teaching_contract(repo_root: Path) -> None:
    """The pedagogy is a contract, not a habit -- so it is enforced like one.

    Every chapter states a goal, teaches a concept before asking for work, offers a
    graduated ladder of exactly three hints, says what done looks like, and says what to
    do when it breaks. That shape is what makes this a MicroHack rather than a lab
    script: a participant who is stuck can buy exactly as much help as they need and no
    more, which is impossible if the hints collapse into a single answer or vanish.

    Until this guard existed the entire structure was held together by memory. Deleting a
    chapter's ``## Hints`` section wholesale, or replacing every hint body with "None.",
    both left the suite fully green -- the tests guarded the fixes, not the teaching.
    """
    chapters = sorted(
        path
        for path in repo_root.glob("challenges/*/README.md")
        if path.parent.name != "wrapup"
    )
    assert len(chapters) == CHALLENGE_CHAPTER_COUNT, (
        f"expected {CHALLENGE_CHAPTER_COUNT} challenge chapters, found "
        f"{len(chapters)}; update this guard deliberately when the workshop changes "
        "shape, so that adding a chapter cannot silently skip the contract"
    )

    offenders: list[str] = []
    for chapter in chapters:
        name = chapter.parent.name
        text = chapter.read_text(encoding="utf-8")

        for heading in TEACHING_CONTRACT_HEADINGS:
            if heading not in text:
                offenders.append(f"{name}: missing `{heading}`")
        if "## Hints" not in text or "## Success criteria" not in text:
            continue  # Already reported; the slices below would be meaningless.

        hints = text.split("## Hints", 1)[1].split("\n## ", 1)[0]
        ladder = re.findall(r"<summary>(.*?)</summary>(.*?)</details>", hints, re.S)
        if len(ladder) != 3:
            offenders.append(
                f"{name}: {len(ladder)} hints, expected a ladder of 3 "
                "(a nudge, the approach, nearly the answer)"
            )
        for index, (summary, body) in enumerate(ladder, start=1):
            # 200 characters is well under the 281 of the shortest real hint, so this
            # catches gutting rather than policing house style.
            if len(body.strip()) < 200:
                offenders.append(
                    f"{name}: hint {index} ({summary.strip()[:40]!r}) is "
                    f"{len(body.strip())} characters -- too short to help anyone"
                )
        if len({summary.strip().lower() for summary, _ in ladder}) != len(ladder):
            offenders.append(f"{name}: hint summaries repeat, so the ladder is flat")

        criteria = text.split("## Success criteria", 1)[1].split("\n## ", 1)[0]
        if len(criteria.strip()) < 200:
            offenders.append(
                f"{name}: success criteria are {len(criteria.strip())} characters -- "
                "a participant cannot tell whether they are done"
            )

    assert not offenders, (
        "the MicroHack teaching contract is broken in these chapters:\n  "
        + "\n  ".join(offenders)
    )


# Every PowerShell script in the repository, not just the ones under baseInfra/scripts.
# Pinned as a count so that adding a script is a deliberate act: an unreferenced script
# is one nobody runs, and one nobody runs is one nobody has proved works.
PROVISIONING_SCRIPT_COUNT = 5

# Build output and tool caches are untracked, so including them makes the walk
# non-deterministic: a developer checkout finds documents a clean clone cannot.
WALK_EXCLUDED_DIRECTORIES = {
    ".git",
    ".venv",
    "node_modules",
    ".terraform",
    "bin",
    "obj",
    "target",
    "__pycache__",
    ".pytest_cache",
}


def test_every_provisioning_script_is_reachable_from_a_document(repo_root: Path) -> None:
    """A script no document names is a script no facilitator will ever run.

    This repository shipped a 571-line Defender seeding script that was referenced by
    exactly zero files. It implemented a documented part of the plan, it was written
    carefully, and it was unreachable -- the facilitator instead had a manual procedure
    to perform by hand. Dead automation is worse than no automation, because it looks
    like the job is done.

    The enumeration is asserted to equal a known count rather than merely be non-empty.
    A glob that silently stops matching is the failure mode this guard is most likely to
    suffer, and a non-empty check would not notice it.

    It enumerates by asking git, not by globbing one directory. Globbing
    ``baseInfra/scripts`` hid ``baseInfra/terraform/import_existing_providers.ps1`` --
    the same scope-blindness this guard exists to end, one directory over.
    """
    scripts = sorted(
        repo_root / line
        for line in subprocess.run(
            ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard", "*.ps1"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.split("\0")
        if line
    )
    assert len(scripts) == PROVISIONING_SCRIPT_COUNT, (
        f"expected {PROVISIONING_SCRIPT_COUNT} PowerShell scripts, found "
        f"{len(scripts)}: {[path.name for path in scripts]}"
    )

    readable = [
        path
        for path in repo_root.rglob("*")
        if path.suffix in {".md", ".ps1", ".json", ".yml", ".yaml"}
        and path.is_file()
        and not set(path.relative_to(repo_root).parts) & WALK_EXCLUDED_DIRECTORIES
    ]
    assert len(readable) >= 150, (
        f"only {len(readable)} documents searched; the walk is not running"
    )

    unreachable: list[str] = []
    for script in scripts:
        mentions = [
            document
            for document in readable
            if document != script and script.name in document.read_text(
                encoding="utf-8", errors="ignore"
            )
        ]
        if not mentions:
            unreachable.append(script.name)

    assert not unreachable, (
        "these scripts are named by no document, so no facilitator will run them; "
        "wire them into a runbook or delete them: " + ", ".join(unreachable)
    )


# The files Challenge 1 actually changes. Everything else present in both the legacy
# tree and the reference tree must stay byte-identical, because the reference is meant
# to be *the legacy app after modernization* -- not a parallel application that happens
# to look similar.
MODERNIZATION_SURFACE = {
    "dotnet": {
        "README.md",
        "src/LegoCatalog.App/Configuration/CatalogRuntimeOptions.cs",
        "src/LegoCatalog.App/Endpoints/CatalogEndpoints.cs",
        "src/LegoCatalog.App/LegoCatalog.App.csproj",
        "src/LegoCatalog.App/Program.cs",
        "src/LegoCatalog.App/Services/LocalImageStore.cs",
        "tests/LegoCatalog.App.Tests/ImageSecurityTests.cs",
        "tests/LegoCatalog.App.Tests/LegoCatalog.App.Tests.csproj",
    },
    "java": {
        "README.md",
        "pom.xml",
        "src/main/java/com/microsoft/microhack/catalog/CatalogApplication.java",
        "src/main/java/com/microsoft/microhack/catalog/config/CatalogRuntimeOptions.java",
        "src/main/java/com/microsoft/microhack/catalog/config/TomcatPathConfiguration.java",
        "src/main/java/com/microsoft/microhack/catalog/service/LocalImageStore.java",
        "src/main/java/com/microsoft/microhack/catalog/web/ImageController.java",
        "src/main/resources/application.properties",
        "src/test/java/com/microsoft/microhack/catalog/PostgreSqlIntegrationTest.java",
    },
}
MIRRORED_FILE_FLOOR = {"dotnet": 35, "java": 40}

# The files the modernization ADDS, and the files it REMOVES. Comparing only the files
# present in both trees leaves both of these invisible: a file that exists on one side
# and not the other is simply skipped, so a deletion needs no declaration and an
# addition is never seen at all. Declaring them turns "the trees differ in shape" from
# something a reader has to notice into something the suite asserts.
MODERNIZATION_ADDITIONS = {
    "dotnet": {
        "Dockerfile",
        "src/LegoCatalog.App/Services/AzureBlobImageStore.cs",
        "tests/LegoCatalog.App.Tests/AzureConfigurationTests.cs",
    },
    "java": {
        "Dockerfile",
        "src/main/java/com/microsoft/microhack/catalog/service/AzureBlobImageStore.java",
        "src/main/java/com/microsoft/microhack/catalog/service/ImageStore.java",
        "src/test/java/com/microsoft/microhack/catalog/AzureConfigurationTest.java",
        "src/test/java/com/microsoft/microhack/catalog/service/AzureBlobImageStoreTest.java",
    },
}

# Empty on purpose, and asserted rather than assumed. The modernization currently
# removes nothing -- every legacy file survives into the reference tree, changed or not.
MODERNIZATION_DELETIONS: dict[str, set[str]] = {"dotnet": set(), "java": set()}


def _files_under(root: Path) -> set[str]:
    """Every source file below ``root``, as posix-relative strings.

    Enumerated through git rather than the filesystem so that build output is excluded
    by the same rules that decide what gets committed. A hand-listed set of directory
    names -- ``bin``, ``obj``, ``target`` -- was doing this job, and it worked only for
    as long as the list happened to be complete: running the Java suite once drops a
    hundred class files into ``target/``, and the guard's correctness depended on
    somebody having thought of that name in advance. Git already knows.
    """
    listing = subprocess.run(
        ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
        cwd=root,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    return {entry for entry in listing.split("\0") if entry}


def _committed_files_under(root: Path) -> set[str]:
    """The same listing restricted to what is committed at ``HEAD``.

    Tree *shape* is a property of what the workshop ships, so the guards that compare
    the legacy and reference trees have to read the committed tree and nothing else.
    Reading the working tree instead made those guards fire on the participant rather
    than on the maintainer: Challenge 1 requires every path to author ``<stack>/
    Dockerfile``, that file is not ignored, and the moment it exists the legacy side
    gains a name the reference side already declares as an addition. The set difference
    shrinks, the declaration no longer matches, and the assertion fails with both of its
    diagnostic lists empty -- because nothing is undeclared and nothing is absent, the
    two trees have simply stopped having the shape the comparison assumes. The only
    escape the message leaves is editing the declaration, which the challenge forbids as
    read-only. Committed listings make the guards invariant to participant work while
    still catching the maintainer drift they exist to catch.
    """
    listing = subprocess.run(
        ["git", "ls-tree", "-r", "-z", "--name-only", "HEAD", "."],
        cwd=root,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    return {entry for entry in listing.split("\0") if entry}


def _tree_shape_mismatch(
    declared: set[str],
    expected_in: set[str],
    expected_out: set[str],
) -> str:
    """Describe every way ``expected_in - expected_out`` can stop matching ``declared``.

    Four states break that equality and the callers used to report two of them. The two
    that went unreported are the ones a participant provokes rather than a maintainer,
    so the failure a participant actually saw printed two empty lists and explained
    nothing: Challenge 1 requires authoring ``<stack>/Dockerfile``, and committing it
    puts a name the reference tree declares as an addition into the legacy tree as well.
    The difference shrinks without leaving anything undeclared and without removing
    anything from the reference tree.

    Reading ``HEAD`` keeps the comparison invariant to a participant's *working* tree,
    but the workshop goes on to ask for a commit, and the guard fires again the moment
    they comply. Naming the state is what lets the reader tell "I am looking at
    maintainer drift" apart from "I am looking at my own homework".

    Only non-empty states are rendered, so a real difference can never be reported as an
    empty explanation.
    """
    states = (
        ("present but undeclared", (expected_in - expected_out) - declared),
        ("declared, but now present on both sides", declared & expected_in & expected_out),
        ("declared, but only on the opposite side", (declared & expected_out) - expected_in),
        ("declared, but in neither tree", declared - expected_in - expected_out),
    )
    return "".join(f"\n  {label}: {sorted(names)}" for label, names in states if names)



def test_reference_tree_differs_from_legacy_only_where_the_workshop_teaches(
    repo_root: Path,
) -> None:
    """The reference solution must be the legacy app modernized, not a rewrite beside it.

    A participant compares their own work against ``solutions/reference``. That
    comparison is only honest if the two trees share an origin: every file the
    modernization does not touch has to be byte-identical. Otherwise an unrelated edit
    made in one tree quietly turns into a phantom "modernization step" a participant
    cannot explain, or worse, hides a real step that no longer shows up as a difference.

    Changing the surface is allowed -- it just has to be deliberate, by editing the set
    above, rather than by drifting.

    This comparison used to walk the legacy tree alone and skip any file missing from
    the other side, which made the two trees' *shape* unguarded in both directions: a
    file deleted from the reference solution needed no declaration, and a file added to
    it was never looked at. Both sets are now asserted exactly.
    """
    for stack, surface in MODERNIZATION_SURFACE.items():
        legacy = repo_root / stack
        reference = repo_root / "solutions" / "reference" / stack
        assert reference.is_dir(), f"{reference} is missing"

        mirrored = 0
        drifted: list[str] = []
        legacy_files = _committed_files_under(legacy)
        reference_files = _committed_files_under(reference)

        assert reference_files - legacy_files == MODERNIZATION_ADDITIONS[stack], (
            f"{stack}: the files the modernization adds are not the ones declared. "
            "Walking only the legacy tree made these invisible, so a new file could "
            "appear in the reference solution and no test would mention it:"
            + _tree_shape_mismatch(
                MODERNIZATION_ADDITIONS[stack], reference_files, legacy_files
            )
        )
        assert legacy_files - reference_files == MODERNIZATION_DELETIONS[stack], (
            f"{stack}: the files the modernization removes are not the ones declared. "
            "A deletion used to require no declaration at all -- the comparison simply "
            "skipped any file missing from one side:"
            + _tree_shape_mismatch(
                MODERNIZATION_DELETIONS[stack], legacy_files, reference_files
            )
        )

        for relative in sorted(legacy_files & reference_files):
            path = legacy / relative
            twin = reference / relative
            if path.read_bytes() == twin.read_bytes():
                mirrored += 1
            elif relative not in surface:
                drifted.append(relative)

        assert mirrored >= MIRRORED_FILE_FLOOR[stack], (
            f"{stack}: only {mirrored} files are shared between the legacy and "
            "reference trees; they have stopped being the same application"
        )
        assert not drifted, (
            f"{stack}: these files differ between the legacy and reference trees but "
            "are not part of the modernization the workshop teaches; either revert the "
            "drift or add them to MODERNIZATION_SURFACE deliberately:\n  "
            + "\n  ".join(drifted)
        )

        stale = sorted(
            relative
            for relative in surface
            if (legacy / relative).is_file()
            and (reference / relative).is_file()
            and (legacy / relative).read_bytes() == (reference / relative).read_bytes()
        )
        assert not stale, (
            f"{stack}: these files are declared as modernization steps but are now "
            "identical in both trees, so the workshop no longer demonstrates them:\n  "
            + "\n  ".join(stale)
        )


def test_local_docker_builds_are_caveated_wherever_a_reader_meets_them(
    repo_root: Path,
) -> None:
    """A local ``docker build`` must say where it can run, because the VM cannot run it.

    Participants work on a Windows VM with no Docker daemon; every image they build goes
    through ``az acr build``. A ``docker build`` printed without that context is a
    command that fails on the only machine the reader has, at the point in the day when
    they have the least slack.

    Two locations are excluded deliberately, not by omission:

    * ``.github/workflows/`` builds on ``ubuntu-latest``, where a daemon is present and
      a local build is the correct thing to do.
    * ``.azure/`` is internal deployment planning that no participant or facilitator is
      routed to; it is not part of the reader-facing narrative.

    Everything else -- chapters, solutions, and the facilitator documents -- is in scope.
    """
    caveat = re.compile(
        r"no daemon|without a Docker daemon|with a Docker daemon|az acr build", re.I
    )
    invocation = re.compile(r"^\s*docker\s+(?:buildx\s+)?build\b", re.M)

    scanned = 0
    offenders: list[str] = []
    for markdown in sorted(repo_root.rglob("*.md")):
        parts = markdown.relative_to(repo_root).parts
        if set(parts) & {".git", ".venv", "node_modules"} or parts[0] in {".azure"}:
            continue
        if parts[0] == "docs" and parts[-1] in {"ImplementationLog.md", "RewritePlan.md"}:
            continue  # Build history, describing decisions rather than instructing.
        scanned += 1
        text = markdown.read_text(encoding="utf-8")
        for match in invocation.finditer(text):
            # The caveat belongs with the command, not somewhere in the document.
            window = text[max(0, match.start() - 700) : match.start()]
            if not caveat.search(window):
                offenders.append(
                    f"{'/'.join(parts)}:{text[: match.start()].count(chr(10)) + 1}"
                )

    assert scanned >= 40, f"only {scanned} documents scanned; the walk is not running"
    assert not offenders, (
        "a local docker build is printed without saying it needs a workstation daemon, "
        "so it fails on the workshop VM: " + ", ".join(offenders)
    )


def test_no_sample_credential_literals_survive_anywhere(repo_root: Path) -> None:
    """No password-shaped literal ships, not even a famous placeholder one.

    The dev container carried a well-known sample SA password for seven review rounds.
    It was never a real secret, which is exactly why it survived: every reader assumed
    somebody else had judged it harmless. A password-shaped string in a repository is
    copied far more often than it is read, and the copy lands somewhere that matters.

    The needle is assembled from fragments so that this guard does not match its own
    source and report itself as the offender.
    """
    needles = ["Your" + "Strong!Passw0rd", "P@ssw0rd" + "123", "admin" + ":admin"]

    scanned = 0
    offenders: list[str] = []
    listing = subprocess.run(
        ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    for relative in (path for path in listing.split("\0") if path):
        try:
            content = (repo_root / relative).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        scanned += 1
        for needle in needles:
            if needle in content:
                offenders.append(f"{relative}: {needle[:6]}...")

    assert scanned >= PHASE_CODE_SCAN_FLOOR, (
        f"only {scanned} files scanned; this guard is not looking where it claims to"
    )
    assert not offenders, (
        "sample credential literals are still present; source them from the host "
        "environment instead: " + ", ".join(offenders)
    )


def test_devcontainer_sources_its_database_password_from_the_host(
    repo_root: Path,
) -> None:
    """The dev container must never carry a database password of its own.

    Nothing in this repository reads ``MSSQL_SA_PASSWORD``; it is a convenience
    passthrough for a SQL Server sibling container. That is precisely why it must not
    fail the build when unset -- and equally why it must not be given a default.
    """
    devcontainer = (repo_root / ".devcontainer" / "devcontainer.json").read_text(
        encoding="utf-8"
    )
    assert '"MSSQL_SA_PASSWORD": "${localEnv:MSSQL_SA_PASSWORD}"' in devcontainer, (
        "the dev container must inherit the SA password from the contributor's own "
        "host shell, not define one"
    )


# Guards that walk the repository and then assert an offender list is empty are only as
# good as the walk. A guard proves its walk happened by asserting something *positive*:
# a count, a floor, or the truthiness of what it collected. ``assert not offenders`` is
# not such a proof, which is the whole point.
# ``re.findall``/``finditer`` earn their place here because prose is the least stable
# input in the repository: a heading can be reworded and a pattern that matched it
# yesterday silently matches nothing today, which is precisely how the round-9 golden
# README guard came to report success on an empty enumeration.
_ENUMERATION_IDIOM = re.compile(
    r"\.rglob\(|\.glob\(|ls-files|os\.walk\(|re\.findall\(|re\.finditer\(|\.findall\(|\.finditer\("
)
_PROVING_COMPARISONS = (ast.Gt, ast.GtE, ast.Eq)
_CLASSIC_IDIOM = re.compile(r"\.rglob\(|\.glob\(|ls-files|os\.walk\(")
_FINDALL_IDIOM = re.compile(r"re\.findall\(|re\.finditer\(|\.findall\(|\.finditer\(")
# One floor over a multi-arm search defends only the arm that dominates it. The
# aggregate stood at 40 over 50 guards, which looked ample and was not: deleting the
# helper arm left 42 and passed, silently dropping eight guards -- among them the two
# shell-declaration guards protecting a class that blocked delivery in round 4. Each
# arm is now floored against its own population, so headroom in one cannot pay for the
# disappearance of another.
WALKING_GUARD_FLOOR = 40
CLASSIC_ARM_FLOOR = 25
FINDALL_ARM_FLOOR = 8
HELPER_ARM_FLOOR = 6


def _enumerating_helpers(tree: ast.Module, text: str) -> set[str]:
    """Return the module-level helpers that enumerate on a caller's behalf.

    A guard that calls ``_chapter_readmes()`` is walking the repository just as surely
    as one that writes ``rglob`` inline, but the idiom is a function call away and this
    meta-guard used to look straight past it. Two such guards protected a class of
    defect that had already blocked delivery once, and neither was being audited.
    """
    return {
        node.name
        for node in tree.body
        if isinstance(node, ast.FunctionDef)
        and not node.name.startswith("test_")
        and _ENUMERATION_IDIOM.search(ast.get_source_segment(text, node) or "")
    }


def _walks_the_repository(node: ast.FunctionDef, text: str, helpers: set[str]) -> bool:
    """Return whether the guard enumerates, directly or through a helper."""
    source = ast.get_source_segment(text, node) or ""
    if _ENUMERATION_IDIOM.search(source):
        return True
    return any(
        isinstance(call.func, ast.Name) and call.func.id in helpers
        for call in ast.walk(node)
        if isinstance(call, ast.Call)
    )


def _helpers_that_prove_their_own_walk(tree: ast.Module, enumerating: set[str]) -> set[str]:
    """Return helpers that both enumerate and assert their own enumeration found something.

    ``_chapter_readmes`` carries its floor internally, so a guard calling it is already
    protected and does not need to repeat the assertion. Without this the meta-guard
    would demand ceremony that adds no safety, and guards written to satisfy noise are
    how a suite learns to ignore its own alarms.

    Asserting is not enough on its own: a helper that validates a parsed value but never
    walks the repository proves nothing about a caller's walk, and letting it vouch would
    reopen the hole this meta-guard exists to close.
    """
    return {
        node.name
        for node in tree.body
        if isinstance(node, ast.FunctionDef)
        and not node.name.startswith("test_")
        and node.name in enumerating
        and _asserts_something_positive(node)
    }


def _proves_its_walk(
    node: ast.FunctionDef, proving_helpers: set[str]
) -> bool:
    """Return whether the guard proves its walk directly or through a helper."""
    if _asserts_something_positive(node):
        return True
    return any(
        isinstance(call.func, ast.Name) and call.func.id in proving_helpers
        for call in ast.walk(node)
        if isinstance(call, ast.Call)
    )


def _asserts_something_positive(node: ast.FunctionDef) -> bool:
    """Return whether the function contains an assertion that its walk found something.

    Structure is used rather than variable names so that the check does not quietly stop
    applying the moment somebody picks a name that was not on a hardcoded list.
    """
    for statement in ast.walk(node):
        if not isinstance(statement, ast.Assert):
            continue
        test = statement.test
        if isinstance(test, ast.UnaryOp) and isinstance(test.op, ast.Not):
            continue  # ``assert not offenders`` -- the shape being guarded against.
        if isinstance(test, ast.Compare):
            # ``in``/``is`` comparisons are per-item content checks, not evidence that
            # the enumeration produced any items at all.
            if any(isinstance(op, _PROVING_COMPARISONS) for op in test.ops):
                return True
            continue
        if isinstance(test, (ast.Name, ast.BinOp)):
            return True  # ``assert workflows`` / ``assert documented - internal``
        if isinstance(test, ast.Call) and getattr(test.func, "id", None) == "len":
            return True
    return False


def test_every_walking_guard_proves_its_own_walk_happened() -> None:
    """A guard that enumerates the repository must prove the enumeration found something.

    "Collect offenders, then assert the list is empty" is the dominant shape in this
    suite, and it fails open: an empty walk produces an empty offender list, which is
    indistinguishable from a clean repository. This is not hypothetical here. The
    phase-code guard once listed only the git index and reported green while 121
    uncommitted files -- including the entire reference tree -- went unread, and the
    Defender foundation guard globbed for a filename that a rename would have silently
    orphaned.

    Every such guard now states a floor. This meta-guard exists so the next one does
    too, because the failure is invisible by construction: the suite stays green either
    way, so nothing except this test will ever notice.
    """
    suite = Path(__file__).parent
    sources = sorted(suite.glob("test_*.py"))
    assert len(sources) >= 8, f"only {len(sources)} test modules found"

    unproven: list[str] = []
    audited = 0
    by_arm = {"classic": 0, "findall": 0, "helper": 0}
    for source in sources:
        text = source.read_text(encoding="utf-8")
        tree = ast.parse(text)
        helpers = _enumerating_helpers(tree, text)
        proving = _helpers_that_prove_their_own_walk(tree, helpers)
        for node in tree.body:
            if not isinstance(node, ast.FunctionDef):
                continue
            if not node.name.startswith("test_"):
                continue
            if not _walks_the_repository(node, text, helpers):
                continue
            audited += 1
            body = ast.get_source_segment(text, node) or ""
            if _CLASSIC_IDIOM.search(body):
                by_arm["classic"] += 1
            elif _FINDALL_IDIOM.search(body):
                by_arm["findall"] += 1
            else:
                by_arm["helper"] += 1
            if not _proves_its_walk(node, proving):
                unproven.append(f"{source.name}:{node.lineno} {node.name}")

    # 50 guards walk the repository today. The floor sits above the 31 that the
    # narrower pre-round-9 detector could see, so losing the helper-aware or
    # ``findall`` arms of the search fails here instead of quietly shrinking the
    # audited set back to where two vacuous guards hid for four rounds.
    assert audited >= WALKING_GUARD_FLOOR, (
        f"only {audited} walking guards found; this meta-guard is not parsing the suite"
    )
    for arm, floor in (
        ("classic", CLASSIC_ARM_FLOOR),
        ("findall", FINDALL_ARM_FLOOR),
        ("helper", HELPER_ARM_FLOOR),
    ):
        assert by_arm[arm] >= floor, (
            f"the {arm} arm of this search reaches only {by_arm[arm]} guards "
            f"(floor {floor}); losing an arm hides guards from auditing without "
            f"moving the total enough to notice -- arms today: {by_arm}"
        )
    assert not unproven, (
        "these guards walk the repository without proving the walk found anything, so "
        "they pass just as happily on an empty enumeration:\n  " + "\n  ".join(unproven)
    )


def test_every_schema_definition_is_reachable(repo_root: Path) -> None:
    """A frozen schema must not carry rules that nothing evaluates.

    An unreferenced `$defs` entry reads exactly like a constraint that is being enforced.
    Anyone auditing the contract sees a rule; the validator sees nothing. That gap is
    worse than having no rule at all, because it buys false confidence in review.

    This is not hypothetical. A dead `$defs/challenge` in the shared challenge schema was
    removed once, no guard was added, and a second dead definition appeared afterwards in
    a different file. Deleting instances without asserting the class is how the class
    regrows.
    """
    schemas = sorted((repo_root / "workshop" / "contracts").glob("*.schema.json"))
    assert len(schemas) >= 15, (
        f"only {len(schemas)} contract schemas found -- this guard is not running"
    )

    orphans: list[str] = []
    definitions = 0
    for schema_path in schemas:
        raw = schema_path.read_text(encoding="utf-8")
        for name in json.loads(raw).get("$defs", {}):
            definitions += 1
            if f'"#/$defs/{name}"' not in raw:
                orphans.append(f"{schema_path.name}: $defs/{name}")

    assert definitions >= 20, (
        f"only {definitions} schema definitions examined -- the glob is stale"
    )
    assert not orphans, (
        "these schema definitions are never referenced, so they document a constraint "
        "the validator does not apply; wire them up or delete them:\n  "
        + "\n  ".join(orphans)
    )


def _github_heading_slug(heading: str) -> str:
    """Reduce a Markdown heading to the fragment GitHub will generate for it.

    GitHub lowercases, strips formatting, **deletes** punctuation rather than replacing
    it, and maps spaces to hyphens. The deletion is the part that catches people: a
    heading containing `go/no-go` anchors as `gono-go`, not `go-no-go`, so the spelling
    that looks correct is the one that is broken.
    """
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", heading.strip())
    text = re.sub(r"[`*_]", "", text)
    return re.sub(r"[^\w\s-]", "", text).strip().lower().replace(" ", "-")


def test_every_cross_document_anchor_resolves(repo_root: Path) -> None:
    """A link to a heading that does not exist fails silently, at the worst moment.

    A broken *file* link 404s and someone notices. A broken *fragment* silently lands the
    reader at the top of a long document, which reads as "the section moved" rather than
    "the link is wrong" -- and these links are the navigation between a facilitator's
    preflight and the gate it depends on. The one this guard was written for pointed at
    `#facilitator-go-no-go-matrix`, which is the spelling a human writes and not the one
    GitHub generates.
    """
    listing = subprocess.run(
        ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard", "*.md"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    documents = [path for path in listing.split("\0") if path]
    assert len(documents) >= 50, (
        f"only {len(documents)} Markdown documents enumerated -- this guard is not running"
    )

    slugs: dict[str, set[str]] = {}
    for relative in documents:
        try:
            content = (repo_root / relative).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        slugs[relative] = {
            _github_heading_slug(match.group(1))
            for match in re.finditer(r"^#{1,6}\s+(.*)$", content, re.MULTILINE)
        }

    broken: list[str] = []
    checked = 0
    for relative, headings in slugs.items():
        source = repo_root / relative
        content = source.read_text(encoding="utf-8")
        for match in re.finditer(r"\[[^\]]*\]\(([^)\s]+)\)", content):
            target = match.group(1)
            if target.startswith(("http://", "https://")) or "#" not in target:
                continue
            path_part, _, fragment = target.partition("#")
            if not path_part:
                available, name = headings, relative
            else:
                resolved = (source.parent / path_part).resolve()
                try:
                    name = str(resolved.relative_to(repo_root))
                except ValueError:
                    continue
                if name not in slugs:
                    continue
                available = slugs[name]
            checked += 1
            if fragment not in available:
                line = content[: match.start()].count("\n") + 1
                broken.append(f"{relative}:{line} -> {name}#{fragment}")

    assert checked >= 40, (
        f"only {checked} cross-document anchors examined -- the link pattern is stale"
    )
    assert not broken, (
        "these links point at headings that do not exist, so they land the reader at the "
        "top of the document instead:\n  " + "\n  ".join(broken)
    )


def test_the_destructive_reset_boundary_matches_the_contract(repo_root: Path) -> None:
    """The prefix that decides what may be deleted must be one value, not three copies.

    `acceptanceReset` is the only operation in this repository that deletes rows from a
    participant's database, and the single thing standing between "delete the fixture"
    and "delete their work" is a product-id prefix. The contract declares that boundary
    twice -- `behavior-contract.json` calls it `ownedProductIdPrefix`, and
    `database-contract.json` calls it `acceptanceFixtureProductIdPrefix` -- and the code
    that performs the delete hard-codes a third copy as a string literal.

    Nothing read either declaration. A repository whose thesis is contract-first had its
    most safety-critical constant living as a magic string, where narrowing the contract
    would leave the code deleting more than the contract permits and no test would say so.
    """
    behavior = json.loads(
        (repo_root / "workshop" / "contracts" / "behavior-contract.json").read_text(
            encoding="utf-8"
        )
    )
    database = json.loads(
        (repo_root / "workshop" / "contracts" / "database-contract.json").read_text(
            encoding="utf-8"
        )
    )
    declared = {
        "behavior-contract.json import.acceptanceReset.ownedProductIdPrefix": behavior[
            "import"
        ]["acceptanceReset"]["ownedProductIdPrefix"],
        "database-contract.json common.acceptanceFixtureProductIdPrefix": database[
            "common"
        ]["acceptanceFixtureProductIdPrefix"],
    }

    source = (repo_root / "tests" / "acceptance" / "catalog_acceptance" / "database.py").read_text(
        encoding="utf-8"
    )
    enforced = re.findall(r'product_id\.startswith\(\s*"([^"]+)"\s*\)', source)
    assert enforced, (
        "no product-id prefix check found in catalog_acceptance/database.py -- the "
        "destructive reset has lost its boundary, or this guard is looking in the "
        "wrong place"
    )
    for index, literal in enumerate(enforced):
        declared[f"catalog_acceptance/database.py startswith[{index}]"] = literal

    assert len(set(declared.values())) == 1, (
        "the acceptance-reset boundary disagrees across the contract and the code that "
        "enforces it, so the rows the contract protects are not the rows the delete "
        "refuses to touch:\n  "
        + "\n  ".join(f"{where} = {value!r}" for where, value in sorted(declared.items()))
    )

    # This episode is taught in two places, and the lesson is prose the rest of the
    # suite cannot see: deleting either passage, or renaming a contract key out from
    # under the passage that quotes it, would leave the teaching intact-looking and
    # false while every other guard stayed green.
    boundary = next(iter(set(declared.values())))
    taught = {
        "tests/acceptance/README.md": [
            "acceptance-reset",
            "ownedProductIdPrefix",
            "acceptanceFixtureProductIdPrefix",
            boundary,
        ],
        "challenges/ch01/README.md": [
            "A contract only earns its name if something reads it",
        ],
    }
    for relative, phrases in taught.items():
        prose = (repo_root / relative).read_text(encoding="utf-8")
        missing = [phrase for phrase in phrases if phrase not in prose]
        assert not missing, (
            f"{relative} no longer states the delete-boundary lesson it teaches "
            f"({missing}); the narrative and the guard have drifted apart"
        )


# The leading approximation mark matters: the worked example's headline is written
# "**\u2248 $2,579**", and a pattern that did not admit it left the single most quoted
# figure in the document unaudited while the guard reported success on the rows around it.
_MONEY_CELL = re.compile(r"^\*{0,2}\s*[\u2248~]?\s*\$([\d,]+(?:\.\d+)?)\*{0,2}$")
_TOTAL_ROW = re.compile(r"\b(total|subtotal)\b", re.IGNORECASE)

# Tables carrying a money total, counted when this floor was set. A floor rather than a
# non-empty check: the parser below is the part most likely to silently stop matching.
MONEY_TABLE_FLOOR = 8

# Six money rows currently show arithmetic a reader can evaluate. A floor because
# coverage here shrinks silently: thinning one Basis cell into prose dropped the most
# load-bearing figure in the cost document out of guard reach without failing anything,
# and only a critic re-deriving it by hand noticed.
EVALUABLE_BASIS_FLOOR = 17

# "the rows above are rounded to cents for display, so they visibly sum to $2,016.90"
# explains why a column does not add up to its own total. Nothing checked it, so editing
# a displayed cent left the explanation quietly wrong. Both occurrences are counted so
# the check cannot end up guarding nothing.
_VISIBLE_SUM = re.compile(r"visibly sum to \$([\d,]+(?:\.\d+)?)")
VISIBLE_SUM_FLOOR = 2

# A count cannot say *which* rows show their work: thinning one cell into prose while
# adding an evaluable cell elsewhere holds the total and passes. These rows carry the
# figures the cost story is built from, so each is named. Adding rows is welcome; losing
# one of these is a regression.
EVALUABLE_BASIS_ROWS = {
    ("docs/CostEstimate.md", "**Azure subtotal, excluding Defender and SRE Agent**"),
    ("docs/CostEstimate.md", "**Base subtotal**"),
    ("docs/CostEstimate.md", "**Modernized subtotal, 50/50 split**"),
    ("docs/CostEstimate.md", "**Legacy** — one Windows VM plus its Premium OS disk"),
    ("docs/CostEstimate.md", "**Total**"),
    ("docs/CostEstimate.md", "**Total, after the Challenge 0 deallocation**"),
    ("docs/CostEstimate.md", "Bastion Basic gateway"),
    ("docs/CostEstimate.md", "Defender for SQL, 15 participants"),
    ("docs/CostEstimate.md", "Defender for Servers P2, over the same 113 h"),
    ("docs/CostEstimate.md", "Defender for open-source relational databases, 15 participants"),
    ("docs/CostEstimate.md", "Modernized workload, .NET / Azure SQL"),
    ("docs/CostEstimate.md", "Modernized workload, Java / PostgreSQL"),
    ("docs/CostEstimate.md", "NAT gateway"),
    ("docs/CostEstimate.md", "Premium OS disks"),
    ("docs/CostEstimate.md", "SRE Agent, **one shared** agent for 8 hours"),
    ("docs/CostEstimate.md", "Standard public IPs"),
    ("docs/CostEstimate.md", "Windows VMs"),
}


def _money(cell: str) -> float | None:
    match = _MONEY_CELL.match(cell.strip())
    return float(match.group(1).replace(",", "")) if match else None


_BASIS_NUMBER = re.compile(r"\d[\d,]*(?:\.\d+)?")


def _basis_segment_values(basis: str, forbidden: float | None = None) -> list[float]:
    """Return every arithmetic result a Basis segment states.

    A cell states its work as a chain -- ``$16.14 - 24 h @ $0.184 = $16.14 - $4.42 =
    $11.72`` -- and each link is a claim about the same figure. Returning them all lets
    the caller insist that every link lands, rather than accepting the cell because one
    of them happened to.

    Returning only the *first* run that parsed was a fail-open hole: in
    ``2 x 24 h @ $0.900, roughly 4 times the 2.2075 hourly blended figure`` the prose
    tail parses and the corrupted rate in front of it never gets evaluated at all. Two
    numbers with no operator between them cannot belong to one expression, so the run is
    split there and *both* sides are evaluated.
    """
    normalised = (
        basis.replace("\u00d7", "*").replace("\u00f7", "/")
        # Only U+2212 means subtraction in these documents; en and em dashes spell
        # ranges ("5-8 hours", "$11,700-$15,900") and reading them as minus invents
        # figures like -4200 out of a correct sentence.
        .replace("\u2212", "-").replace("\u2013", " ").replace("\u2014", " ")
        # "24 h @ $0.184" is a rate times a quantity. Left unread, the whole segment
        # fails to parse and every operand inside it becomes unfalsifiable -- which is
        # how a 5x error in a VM hourly rate survived 47% operand mutation.
        .replace("@", "*")
    )
    # "$2.56/day" is a unit, not a division: reading the slash as an operator turns
    # $2.56/day x 42.5/24 into 0.0025 and would condemn an honest cell.
    normalised = re.sub(r"/\s*[A-Za-z]+", " ", normalised)
    # A hyphen inside a word is spelling, not subtraction. "vCore-hours ... auto-pause"
    # otherwise tokenises to "8 - - 24" and invents the value 32 out of prose.
    normalised = re.sub(r"(?<=[A-Za-z])-(?=[A-Za-z])", " ", normalised)
    # An unspaced hyphen between digits is a date, a version or a GUID -- "2020-01-01",
    # "18.6-1". Arithmetic in these cells is always spaced, so this cannot swallow a
    # real subtraction, and a spaced ASCII minus still reads as one.
    normalised = re.sub(r"(?<=\d)-(?=\d)", " ", normalised)
    # A cell is free to spell its operator: "24 h @ $0.184, plus $21.68/month x 24/730"
    # adds two terms, and dropping the word silently discards the first one.
    for word, symbol in (("plus", "+"), ("minus", "-"), ("times", "*")):
        normalised = re.sub(rf"\b{word}\b", symbol, normalised, flags=re.IGNORECASE)

    # An equals sign ends one step and starts the next, so "15 x ($12.90 + $4.53) =
    # $261.45" is an expression and its answer, not one run to be welded together.
    blocks: list[list[str]] = []
    for step in re.split(r"[=\u2248]", normalised):
        tokens = re.findall(r"\d[\d,]*(?:\.\d+)?|[-+*/()]", step.replace("$", ""))
        # Split where two numbers sit side by side: that junction is prose, not
        # arithmetic, and welding across it produced figures such as 1515 x 17.43 that
        # no document states. Each side is a candidate expression in its own right.
        blocks.append([])
        for previous, token in zip([None, *tokens], tokens):
            if previous is not None and previous[0].isdigit() and token[0].isdigit():
                blocks.append([])
            blocks[-1].append(token)

    values: list[float] = []
    for block in blocks:
        # Prose sits around the numbers, so trim leading fragments until the remainder
        # evaluates -- an unmatched bracket or a trailing operator is not arithmetic.
        for offset in range(len(block)):
            run = block[offset:]
            # A run without an operator is the answer restating itself, which is the
            # one thing that must never count as its own evidence.
            if not any(token in "+-*/" for token in run):
                continue
            # An operand that *is* the answer proves nothing: "$261.45 x 1", "+ 0" and
            # "/ 1" satisfy the operator rule while leaving the figure its own evidence.
            if forbidden is not None and any(
                token[0].isdigit()
                and abs(float(token.replace(",", "")) - forbidden)
                <= max(0.005, abs(forbidden) * 0.0005)
                for token in run
            ):
                continue
            candidate = "".join(token.replace(",", "") for token in run)
            if not re.fullmatch(r"[\d.+\-*/()]+", candidate):
                continue
            try:
                value = eval(candidate, {"__builtins__": {}}, {})  # noqa: S307
            except (SyntaxError, ZeroDivisionError, TypeError, NameError):
                continue
            if isinstance(value, (int, float)):
                values.append(float(value))
                break
    return values


def _lands_on(value: float, claimed: float) -> bool:
    """Return whether an evaluated step arrives at a figure the row states."""
    tolerance = max(0.02, abs(claimed) * 0.005)
    if abs(value - claimed) <= tolerance:
        return True
    return abs(claimed - round(claimed)) < 0.005 and round(value) == round(claimed)


def _basis_strays(basis: str, claims: list[float]) -> list[float]:
    """Return figures a Basis states that arrive nowhere the cell or the row accounts for.

    Accepting a cell because *one* of its steps landed let every other step be wrong: with
    ``$16.14 - 24 h @ $0.184 = $16.14 - $4.42 = $11.72``, a five-fold error in the hourly
    rate left the second step intact and the cell passed. So every step is evaluated.

    But a correct cell may show its work in stages, and an intermediate result is not
    supposed to equal the row's figure -- ``2 x $32.84 = $65.68 for both VMs, halved after
    deallocation = $32.84`` is exactly the two-stage derivation the document is trying to
    teach. A step is therefore acceptable when it lands on one of the row's figures *or*
    when the cell itself carries that value forward into another step.
    """
    parts = re.split(r"([=\u2248])", basis)
    segments = parts[::2]
    # The separator that introduces each segment, "" for the first.
    openers = ["", *parts[1::2]]
    computed = [_basis_segment_values(segment) for segment in segments]
    numbers = [
        {float(token.replace(",", "")) for token in re.findall(r"\d[\d,]*(?:\.\d+)?", segment)}
        for segment in segments
    ]

    def accounted(value: float, source: int) -> bool:
        if any(_lands_on(value, claim) for claim in claims):
            return True
        # Chain closure: an intermediate is legitimate precisely because a later step
        # picks it up. Only another step counts, or the value would vouch for itself.
        return any(
            any(_lands_on(value, seen) for seen in numbers[index])
            for index in range(len(segments))
            if index != source
        )

    strays: list[float] = []
    for index, values in enumerate(computed):
        strays.extend(value for value in values if not accounted(value, index))
    # A step that computes nothing but sits immediately after one that does is the cell
    # restating its answer, and it must not contradict the figure beside it. Read the
    # figure the step opens with: the real cells carry trailing asides such as
    # "= $11.72. That VM's compute stops". A figure further from the arithmetic is prose
    # -- a stated alternative or a rounding aside -- and is not the cell's answer.
    for index in range(1, len(segments)):
        # "~" says "the same quantity, rounded", so it must agree with what came before
        # even at the end of a restatement chain: "$3.4177 + $9.48 = $12.8977 ~ $12.90"
        # leaves the segment before the rounded figure computing nothing, and requiring
        # the *immediate* predecessor to compute let a five-fold error in it survive.
        # "=" is weaker -- it also introduces a separately labelled quantity, as in
        # "= $34.83; whole-month billing = $225.00" -- so it keeps the stricter rule.
        reached = any(computed[:index]) if openers[index] == "\u2248" else bool(computed[index - 1])
        if computed[index] or not reached:
            continue
        opening = re.match(r"\s*\$?\s*([\d,]+(?:\.\d+)?)", segments[index])
        if opening is None:
            continue
        restated = float(opening.group(1).replace(",", ""))
        if not any(_lands_on(restated, claim) for claim in claims) and not any(
            _lands_on(restated, value) for values in computed for value in values
        ):
            strays.append(restated)
    return strays


def _basis_reproduces(basis: str, claimed: float) -> bool | None:
    """Return whether a Basis cell's own arithmetic evaluates to the figure beside it.

    An earlier version accepted a cell that merely *restated* its answer, which meant
    ``15 x ($99.99 + $4.53) = $261.45`` passed: the answer was acting as its own
    evidence and the operands were never checked. ``None`` means the cell states no
    arithmetic, which is reported separately rather than treated as a pass.
    """
    values = _basis_segment_values(basis, forbidden=claimed)
    if not values:
        return None
    return any(_lands_on(value, claimed) for value in values)


def _markdown_tables(text: str) -> list[list[list[str]]]:
    """Group contiguous pipe-delimited lines into tables of split cells."""
    tables, current = [], []
    for line in text.splitlines():
        if line.strip().startswith("|"):
            current.append([cell.strip() for cell in line.strip().strip("|").split("|")])
        elif current:
            tables.append(current)
            current = []
    if current:
        tables.append(current)
    return tables


def test_every_money_total_reconciles_with_the_rows_a_reader_can_see(repo_root: Path) -> None:
    """A subtotal row promises to total the rows above it, and a reader will check.

    ``docs/CostEstimate.md`` is the one document here read adversarially, by someone
    deciding whether to spend money. It labels nearly every line **Derived**, which is a
    promise of reproducibility, and the natural act of verification is to add the column.

    Three columns did not add. Two were single pennies -- rows rounded to cents, totals
    computed from unrounded bases. The third was $0.33 and reconciled by neither route:
    not the visible column sum, and not thirty times the displayed per-participant
    figure. The operand that would explain it appeared nowhere on the page. A penny
    reads as rounding; a third of a dollar that reconciles by nothing reads as an error,
    and it spends the credibility that the honest lines earned.

    So a gap wider than rounding explains is allowed only where the row shows its
    arithmetic. Rounding drift is bounded at a cent per row summed, because that is the
    most that rounding each row to cents can accumulate.
    """
    audited = 0
    evaluable = 0
    visible_sums = 0
    evaluated_rows: set[tuple[str, str]] = set()
    offenders: list[str] = []
    documents = [
        line
        for line in subprocess.run(
            ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard", "*.md"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.split("\0")
        if line
    ]

    for relative in documents:
        text = (repo_root / relative).read_text(encoding="utf-8", errors="ignore")
        for table in _markdown_tables(text):
            segment: dict[int, list[float]] = {}
            for cells in table:
                if not cells or set(cells[0]) <= set("-: "):
                    continue
                # A summable column checks the figure but never the explanation, and
                # an ordinary row is checked by nothing at all -- so a basis could
                # state arithmetic that lands nowhere near any figure beside it and
                # no other check would object. Every money row that shows work has
                # that work evaluated. The cell is often shared by two currency
                # columns, so arriving at either is enough; arriving at neither is not.
                row_columns = [c for c, cell in enumerate(cells) if _money(cell) is not None]
                # The work is not always in the last cell. A "Quantity" column carries
                # "2 x 24 h @ $0.184" while the Basis beside it says only "Derived", so
                # reading the last cell alone left a whole column of arithmetic -- and
                # every rate inside it -- unfalsifiable.
                working_cells = [
                    cell.strip()
                    for c, cell in enumerate(cells)
                    if c and c not in row_columns and cell.strip()
                ]
                if row_columns and working_cells:
                    row_claims = [_money(cells[c]) for c in row_columns]
                    for row_basis in working_cells:
                        verdicts = [_basis_reproduces(row_basis, claim) for claim in row_claims]
                        if any(v is not None for v in verdicts):
                            evaluable += 1
                            evaluated_rows.add((relative, cells[0].strip()))
                        if any(v is not None for v in verdicts) and not any(verdicts):
                            offenders.append(
                                f"{relative}: '{cells[0]}' shows arithmetic in its basis "
                                f"({row_basis!r}) that arrives at none of the figures it "
                                f"states ({row_claims})"
                            )
                        for stray in _basis_strays(row_basis, row_claims):
                            offenders.append(
                                f"{relative}: '{cells[0]}' states a step in its basis "
                                f"({row_basis!r}) that works out to {stray:,.4f}, which "
                                f"is none of the figures on the row ({row_claims})"
                            )
                if _TOTAL_ROW.search(cells[0]):
                    money_columns = {
                        column
                        for column, cell in enumerate(cells)
                        if _money(cell) is not None
                    }
                    for column in sorted(money_columns):
                        claimed = _money(cells[column])
                        values = segment.get(column, [])
                        audited += 1
                        # The trailing cell is where this table explains itself.
                        basis = cells[-1].strip() if len(cells) > column + 1 else ""
                        # Fewer than two rows to add means the reader has no column to
                        # sum, which is not innocence -- it is a total that cannot be
                        # reproduced from the page at all unless the row shows its work.
                        unsummable = len(values) < 2
                        gap = abs(sum(values) - claimed)
                        # The claim names its column in prose ("makes the .NET column
                        # visibly sum to $6.68"), which is not machine-readable, so it is
                        # enough that some column above really does add to the figure.
                        if column == min(money_columns):
                            for shown in _VISIBLE_SUM.findall(basis):
                                visible_sums += 1
                                stated = float(shown.replace(",", ""))
                                if not any(
                                    abs(stated - sum(segment.get(other, []))) <= 0.01
                                    for other in money_columns
                                ):
                                    offenders.append(
                                        f"{relative}: '{cells[0]}' says the rows above "
                                        f"visibly sum to ${stated:,.2f}, but no column "
                                        "above it adds to that"
                                    )
                        if (unsummable or gap > 0.01 * len(values)) and basis:
                            # The row claims to show its work, so the work is checked.
                            verdict = _basis_reproduces(basis, claimed)
                            if verdict is False:
                                offenders.append(
                                    f"{relative}: '{cells[0]}' column {column} claims "
                                    f"${claimed:,.2f} but its own stated basis "
                                    f"({basis!r}) does not arrive at that figure"
                                )
                            elif verdict is None and unsummable:
                                # Prose is not arithmetic. A total with no column to
                                # add is exactly the row that has to show numbers.
                                offenders.append(
                                    f"{relative}: '{cells[0]}' column {column} claims "
                                    f"${claimed:,.2f} with no summable rows above it, "
                                    f"and its basis ({basis!r}) states no arithmetic a "
                                    "reader could follow to that figure"
                                )
                            continue
                        if (unsummable or gap > 0.01 * len(values)) and not basis:
                            offenders.append(
                                f"{relative}: '{cells[0]}' column {column} claims "
                                f"${claimed:,.2f}, the {len(values)} rows above it total "
                                f"${sum(values):,.2f} (off by ${gap:,.2f}), and the row "
                                "shows no arithmetic"
                                if not unsummable
                                else (
                                    f"{relative}: '{cells[0]}' column {column} claims "
                                    f"${claimed:,.2f} with no summable rows above it and "
                                    "no arithmetic in its Basis cell, so a reader cannot "
                                    "reproduce it from anything on the page"
                                )
                            )
                    segment = {}
                    continue
                for column, cell in enumerate(cells):
                    value = _money(cell)
                    if value is not None:
                        segment.setdefault(column, []).append(value)

    assert visible_sums >= VISIBLE_SUM_FLOOR, (
        f"only {visible_sums} display-rounding explanations were checked, below "
        f"{VISIBLE_SUM_FLOOR}; the wording changed and the check now guards nothing"
    )
    missing = sorted(EVALUABLE_BASIS_ROWS - evaluated_rows)
    assert not missing, (
        "these rows no longer show arithmetic a reader can check, so the figures beside "
        f"them are now unfalsifiable: {missing}"
    )
    assert evaluable >= EVALUABLE_BASIS_FLOOR, (
        f"only {evaluable} money rows state arithmetic a reader could follow, below "
        f"{EVALUABLE_BASIS_FLOOR}; a Basis cell has been thinned into prose and its "
        f"figure is no longer checked by anything"
    )
    assert audited >= MONEY_TABLE_FLOOR, (
        f"only {audited} money totals were audited; the table parser has stopped "
        "matching and this guard is reporting on nothing"
    )
    assert not offenders, (
        "these totals cannot be reproduced from the rows a reader can see, and do not "
        "say why:\n  " + "\n  ".join(offenders)
    )


# At least this many "git ignores X" claims must be found in workshop/golden/README.md.
# A prose regex with no floor is the same vacuous-pass bug as an unbounded filesystem
# walk: zero matches means the loop body never runs and the guard reports on nothing.
GOLDEN_IGNORE_CLAIM_FLOOR = 1


def test_the_golden_bundle_instructions_still_match_the_machine(repo_root: Path) -> None:
    """``workshop/golden/`` is empty by design, so only its README can go stale.

    A facilitator reads this file at T-4 and follows it once, one to two days of work,
    against a live subscription. Nothing they do gets checked against the repository
    until the very end, when the validator either exits 0 or does not -- so a README
    that has drifted from the code costs a day, not a minute.

    Two claims in it are load-bearing and both were checkable. The contract's path
    inside the bundle is a machine constant. And the promise that the rendered evidence
    is git-ignored is a safety claim: if it is wrong, a facilitator who commits their
    bundle publishes the resource IDs of a live environment.

    That second claim *was* wrong -- the README named
    ``workshop/golden/*/modernization-contract.json``, which git does not ignore, while
    the actual rule ignores ``workshop/golden/*/evidence/``. The protection was real and
    wider than the sentence describing it, so nothing leaked. But the sentence was
    checkable against git and nobody had checked it.
    """
    from catalog_acceptance import golden_dryrun

    readme = (repo_root / "workshop" / "golden" / "README.md").read_text(encoding="utf-8")

    assert golden_dryrun.CONTRACT_RELATIVE_PATH in readme, (
        f"the bundle layout in the README does not show {golden_dryrun.CONTRACT_RELATIVE_PATH!r}, "
        "which is where the validator requires the contract; a facilitator following the "
        "diagram would render into a path that can never exit 0"
    )

    stacks = sorted(
        path.name
        for path in (repo_root / "workshop" / "golden").iterdir()
        if path.is_dir()
    )
    assert stacks, "no stack directories under workshop/golden/ -- the guard below checks nothing"

    for stack in stacks:
        rendered = f"workshop/golden/{stack}/{golden_dryrun.CONTRACT_RELATIVE_PATH}"
        ignored = subprocess.run(
            ["git", "check-ignore", "-q", rendered], cwd=repo_root
        ).returncode == 0
        assert ignored, (
            f"{rendered} is not git-ignored, so a facilitator who renders a golden "
            "bundle and commits publishes the resource IDs of their live environment"
        )

    # Every sentence that talks about git ignoring something, in either voice. Matching
    # one phrasing -- "`X` is ignored by Git" -- meant a rewrite to "Git ignores `X`"
    # silently removed the claim from the guard's view while the suite stayed green.
    claims = {
        path
        for sentence in re.split(r"(?<=[.!?])\s+", readme)
        if "ignore" in sentence.lower() and "git" in sentence.lower()
        for path in re.findall(r"`(workshop/golden/[^`]*?)`", sentence)
    }
    assert len(claims) >= GOLDEN_IGNORE_CLAIM_FLOOR, (
        f"found {len(claims)} git-ignore claims in workshop/golden/README.md, expected at "
        f"least {GOLDEN_IGNORE_CLAIM_FLOOR}; the claim this guard exists to check has been "
        "reworded out of its reach and the loop below is now running on nothing"
    )

    for claimed in sorted(claims):
        for stack in stacks:
            probe = claimed.replace("*", stack)
            landing = probe if probe.endswith("/") else probe + "/"
            resolved = (
                landing + golden_dryrun.CONTRACT_RELATIVE_PATH.rsplit("/", 1)[-1]
                if claimed.rstrip("/").endswith("evidence")
                else probe
            )
            assert subprocess.run(
                ["git", "check-ignore", "-q", resolved], cwd=repo_root
            ).returncode == 0, (
                f"the README says {claimed!r} is ignored by Git, but git does not ignore "
                f"{resolved!r}; the sentence describes a protection that is not the one in place"
            )


# The four application trees. Everything a participant or facilitator compiles lives
# under one of these, and anything here that git does not track does not exist for
# anybody who clones the repository.
PROTECTED_PATH_FLOOR = 12
FENCED_BLOCK_FLOOR = 20
PROVISIONER_FUNCTION_FLOOR = 12
SOURCE_COMMIT_SENTENCE_FLOOR = 3
TRACKED_SOURCE_FLOOR = 20
APPLICATION_TREES = ("dotnet", "java", "solutions/reference/dotnet", "solutions/reference/java")


def test_every_application_source_file_is_tracked_by_git(repo_root: Path) -> None:
    """A test that is not committed is a test that only passes on the machine that wrote it.

    Four test files -- ``RuntimeIdentityConfigurationTests.cs`` and
    ``RuntimeIdentityConfigurationTest.java``, in both the legacy and reference trees --
    sat on disk untracked for a full review round. Locally ``dotnet test`` reported 45/45
    and ``mvn test`` reported 35/35, and both numbers were quoted as evidence. A fresh
    clone would have compiled 42 and 32. The gap is invisible precisely because the
    machine doing the checking is the machine holding the uncommitted files.

    This is not caught by the suites themselves, which read the filesystem, nor by the
    mirror guard, which enumerates with ``--others`` and so sees untracked files too.
    It needs git's own view of what would survive a clone.
    """
    stray: list[str] = []
    for tree in APPLICATION_TREES:
        assert (repo_root / tree).is_dir(), (
            f"{tree} is not a directory -- the application tree has moved and this guard "
            "is checking nothing"
        )
        listing = subprocess.run(
            ["git", "ls-files", "-z", "--others", "--exclude-standard", "--", tree],
            cwd=repo_root,
            capture_output=True,
            text=True,
            check=True,
        ).stdout
        stray.extend(entry for entry in listing.split("\0") if entry)
        tracked = subprocess.run(
            ["git", "ls-files", "--", tree],
            cwd=repo_root, capture_output=True, text=True, check=True,
        ).stdout.split()
        # Listing only untracked files means an empty answer is the pass condition,
        # so this guard cannot tell "nothing is stray" from "the tree is gone".
        assert len(tracked) >= TRACKED_SOURCE_FLOOR, (
            f"{tree} has only {len(tracked)} tracked files; this guard is being "
            "asked about a tree that is no longer there"
        )

    assert not stray, (
        "these files exist on disk but are not tracked by git, so they are absent from "
        "every clone and the local test counts overstate what anyone else can run:\n  "
        + "\n  ".join(sorted(stray))
    )


def test_no_unguarded_trim_on_native_command_output(repo_root: Path) -> None:
    """Reject `.Trim()` applied straight to a native command's output.

    A native command that prints nothing yields AutomationNull, and a pipeline
    whose output is `-replace`d yields an empty `System.Object[]`. Calling
    `.Trim()` on either raises a terminating error under
    `$ErrorActionPreference = 'Stop'`, which preempts the specific diagnostic
    the surrounding code was written to emit. Collecting into `@(...)` and
    joining first yields an empty string, so the intended check runs.
    """
    offenders: list[str] = []
    for number, line in enumerate(_provisioner(repo_root).splitlines(), start=1):
        if ".Trim()" not in line or "(&" not in line:
            continue
        if "-join" in line:
            continue
        offenders.append(f"{number}: {line.strip()}")

    assert not offenders, (
        "`.Trim()` is applied to unguarded native command output; wrap the "
        "pipeline in `(@(...) -join '')` so empty output degrades to an empty "
        "string instead of a null-reference error:\n" + "\n".join(offenders)
    )


def test_provider_import_script_checks_az_exit_status(repo_root: Path) -> None:
    """`az provider list` failing must stop the import, not report success.

    Without an exit-status check the failed call prints nothing, the provider
    list parses as empty, and the script reports "No providers need to be
    imported" and exits 0 -- a green message for a run that did nothing.
    """
    script = (
        repo_root / "baseInfra" / "terraform" / "import_existing_providers.ps1"
    ).read_text(encoding="utf-8")
    lines = script.splitlines()

    call = next(
        (index for index, line in enumerate(lines) if "az provider list" in line),
        None,
    )
    assert call is not None, "expected an `az provider list` call to guard"

    window = "\n".join(lines[call + 1 : call + 6])
    assert "$LASTEXITCODE" in window, (
        "`az provider list` is not followed by a $LASTEXITCODE check, so an "
        "authentication or permission failure is reported as success:\n"
        + "\n".join(lines[call : call + 6])
    )
