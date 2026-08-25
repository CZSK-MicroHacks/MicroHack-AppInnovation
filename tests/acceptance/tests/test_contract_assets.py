"""Executable tests that freeze schemas, corpus identity, and normalization."""

from __future__ import annotations

import base64
import gzip
import io
import json
import re
import shutil
import subprocess
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
    """Require every checked-in JSON Schema to be a valid Draft 2020-12 schema."""
    contracts = repo_root / "workshop" / "contracts"
    for path in contracts.glob("*.schema.json"):
        Draft202012Validator.check_schema(load_json(path))


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


def test_p4_target_and_migration_examples_match_schemas(repo_root: Path) -> None:
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


def test_p4_migration_cli_surface_is_exact(repo_root: Path) -> None:
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


def test_p4_migration_error_protocol_is_exact(repo_root: Path) -> None:
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


def test_p4_contracts_reject_incompatible_modes(repo_root: Path) -> None:
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


def test_legacy_dotnet_tree_stays_on_the_locked_source_sdk(repo_root: Path) -> None:
    """Fail if `dotnet/` drifts off the legacy baseline participants must start from.

    The workshop's premise is that only legacy code ships in the participant-facing
    tree and participants modernize it themselves. A silent upgrade of `dotnet/` breaks
    that premise *and* the VM, which pins the source SDK with `rollForward: disable`.
    The expected framework is derived from the lock rather than hard-coded so the two
    can never disagree.
    """
    source_sdk = _lock(repo_root)["runtimes"]["dotnet"]["sourceSdk"]
    expected = f"net{source_sdk.split('.')[0]}.0"

    projects = sorted((repo_root / "dotnet").rglob("*.csproj"))
    assert projects, "the legacy .NET tree has no projects"
    for project in projects:
        text = project.read_text(encoding="utf-8")
        assert f"<TargetFramework>{expected}</TargetFramework>" in text, (
            f"{project.relative_to(repo_root)} is not on the locked source SDK "
            f"{expected}; the legacy baseline has drifted"
        )


def test_legacy_java_tree_stays_on_the_locked_source_spring_boot(
    repo_root: Path,
) -> None:
    """Fail if `java/` drifts off the legacy Spring Boot and JDK baseline."""
    java = _lock(repo_root)["runtimes"]["java"]
    boot = java["sourceSpringBoot"]
    jdk_major = java["sourceRuntime"].split(".")[0]

    pom = (repo_root / "java" / "pom.xml").read_text(encoding="utf-8")
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
    assert "jq version verification failed" in script


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
    assert "leaving participant work untouched" in script
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

    for document in sorted(repo_root.rglob("*.md")):
        if any(part in skipped_roots for part in document.parts):
            continue
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
    for document in sorted(repo_root.rglob("*.md")):
        if any(part in {".git", "node_modules", ".venv"} for part in document.parts):
            continue
        text = document.read_text(encoding="utf-8")
        for match in re.finditer(r"az deployment sub ", text):
            window = text[match.start():match.start() + 400]
            if "main.bicep" in window:
                offenders.append(document.relative_to(repo_root).as_posix())

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
    for relative in CH01_RUNBOOKS:
        for match in PROTECTED_PATH.findall((repo_root / relative).read_text()):
            if "<" in match or ">" in match:
                offenders.append(f"{relative}: {match}")
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
    """Require the hard-asserted application secret to be explained in prose.

    ``infra/main.bicep`` fails the application stage outright when
    ``performanceApiKey`` is empty, so a parameter nobody documents is a stop.
    """
    documented = [
        path.relative_to(repo_root).as_posix()
        for path in repo_root.rglob("*.md")
        if ".git" not in path.parts and "performanceApiKey" in path.read_text()
    ]
    assert documented, (
        "infra/main.bicep asserts performanceApiKey is present for the application "
        "stage, but no Markdown document mentions it"
    )


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
    """Require the chapters to mention the parameter the template asserts on."""
    mentions = [
        path.relative_to(repo_root).as_posix()
        for path in (repo_root / "challenges").rglob("*.md")
        if "resourceGroupName" in path.read_text()
    ]
    assert mentions, (
        "infra/main.bicep requires and asserts resourceGroupName, but no participant "
        "chapter mentions it"
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


def _chapter_readmes(repo_root: Path) -> list[Path]:
    """Return every participant-facing chapter README, in stable order."""
    return sorted((repo_root / "challenges").rglob("README.md"))


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
        for path in (repo_root / "dotnet").rglob("*.csproj")
        for match in [re.search(r"<TargetFramework>net(\d+)\.0<", path.read_text())]
        if match
    }
    target_tfms = {
        match.group(1)
        for path in (repo_root / "solutions" / "reference" / "dotnet").rglob("*.csproj")
        for match in [re.search(r"<TargetFramework>net(\d+)\.0<", path.read_text())]
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
        for sentence in re.findall(r"[^.\n]*sourcecommit[^.\n]*", normalized):
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
            if not invocation.search(body):
                continue
            if establishes_cwd.search(body):
                continue
            offenders.append(f"{'/'.join(parts)} ({language or 'plain'})")

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
    for rel in ("docs/Facilitator.md", "docs/Demo.md"):
        text = (repo_root / rel).read_text(encoding="utf-8")
        for index, (language, body) in enumerate(_fenced_blocks(text)):
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


def test_reference_runbooks_contain_no_unresolved_placeholders(repo_root: Path) -> None:
    """Solution runbooks must be executable as printed, not templates to fill in.

    A `<placeholder>` inside a solution's code fence fails at the point a facilitator is
    least able to recover — mid-migration, after the deployment and image build. Every
    value these blocks need is already reachable from the provisioned environment or the
    validated target output, so a placeholder is a gap rather than a necessity.
    """
    # Two placeholders are legitimate: a value only the facilitator can know, and a
    # secret the reader must choose. Printing a literal secret would be the worse bug.
    permitted = re.compile(
        r"<(?:facilitator|your|owner)[\w-]*>|<[\w-]*(?:key|password|secret|token|user)>",
        re.I,
    )
    placeholder = re.compile(r"<[a-z][a-z0-9-]*>")

    offenders: list[str] = []
    for markdown in sorted(repo_root.glob("solutions/**/README.md")):
        for language, block in _fenced_blocks(markdown.read_text(encoding="utf-8")):
            if language.lower() not in {"bash", "sh", "shell", "powershell", "pwsh"}:
                continue
            for line in block.splitlines():
                # Redirections and comparisons are not placeholders.
                if "<<" in line or "-lt" in line or "->" in line:
                    continue
                for found in placeholder.findall(permitted.sub("", line)):
                    rel = markdown.relative_to(repo_root)
                    offenders.append(f"{rel}: {found} in `{line.strip()[:70]}`")

    assert not offenders, (
        "solution runbooks must run as printed; unresolved placeholders: "
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
        set(re.findall(r"workshop/contracts/fixtures/[\w./-]+\.json", demo))
    )
    absent = [name for name in named_fixtures if not (repo_root / name).exists()]
    assert not absent, f"the demo names substitute fixtures that do not exist: {absent}"
    # Counting fixtures against gaps lets five unrelated fixtures "cover" five unrelated
    # gaps, so each missing path must be matched by name. One fixture is deliberately
    # renamed on the way into the SRE Agent bundle; that alias is declared, not inferred.
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


def test_deployment_blocks_bind_every_variable_they_expand(repo_root: Path) -> None:
    """An `az deployment` block never expands a variable nothing in it defines."""
    offenders: list[str] = []
    checked = 0

    for runbook in sorted(repo_root.glob("solutions/**/README.md")):
        content = runbook.read_text(encoding="utf-8")
        for block in re.finditer(r"```bash\n(.*?)```", content, re.DOTALL):
            body = block.group(1)
            if "az deployment" not in body:
                continue
            checked += 1

            bound: set[str] = set()
            # Plain assignments, grouped `--parameters name=value` forms, and the
            # `: "${VAR:?explanation}"` guard idiom all count as binding.
            bound.update(re.findall(r"(?:^|\s)([A-Za-z_][A-Za-z0-9_]*)=", body))
            bound.update(re.findall(r"\$\{([A-Za-z_][A-Za-z0-9_]*):[?-]", body))
            bound.update(re.findall(r"(?m)^\s*(?:export|read)\s+([A-Za-z_][A-Za-z0-9_]*)", body))

            expanded = set(
                re.findall(r"\$\{?([A-Za-z_][A-Za-z0-9_]*)\}?", body)
            )
            unbound = sorted(expanded - bound - AMBIENT_SHELL_VARIABLES)
            for name in unbound:
                line = content[: block.start()].count("\n") + 1
                offenders.append(
                    f"{runbook.relative_to(repo_root)} (block at line {line}) "
                    f"expands ${name} without binding it"
                )

    assert checked, "no `az deployment` bash blocks found in solutions/**"
    assert not offenders, (
        "deployment blocks expand variables nothing binds, so they submit empty values "
        "and fail inside Azure instead of failing with a sentence:\n  "
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
    "tests/acceptance/catalog_acceptance/defender_evidence.py": {"P2"},
    "tests/acceptance/tests/test_ch05_defender_contracts.py": {"P2"},
    "solutions/ch05-defender/README.md": {"P2"},
}


def test_no_build_phase_codes_reach_a_reader(repo_root: Path) -> None:
    """Nothing a participant or facilitator reads refers to a build phase by number.

    Phase codes name the order this repository was built in, not anything a reader can
    see. They had leaked into runbooks, contract guides, test filenames and even the
    error strings the evidence validators print, where they explain nothing.

    Untracked-but-not-ignored files are scanned too. Listing only the index would make
    this guard pass merely because work had not been committed yet, which is exactly
    when a leak is most likely.
    """
    tracked = subprocess.run(
        [
            "git",
            "ls-files",
            "--cached",
            "--others",
            "--exclude-standard",
            "*.md",
            "*.py",
            "*.json",
            "*.ps1",
            "*.bicep",
            "*.tf",
        ],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.split()

    offenders: list[str] = []
    for relative in tracked:
        if relative in PHASE_CODE_HISTORY:
            continue
        try:
            content = (repo_root / relative).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for match in re.finditer(r"\bP\d+\b", content):
            before = content[max(0, match.start() - 24) : match.start()]
            after = content[match.end() : match.end() + 1]
            quoted = before.endswith(("'", '"')) and after in ("'", '"')
            if quoted or match.group(0) in AZURE_P_IDENTIFIERS.get(relative, ()):
                continue  # Quoted disk SKU tiers and the real Defender plan name.
            offenders.append(
                f"{relative}:{content[: match.start()].count(chr(10)) + 1}: "
                f"{match.group(0)}"
            )

    assert not offenders, (
        "build-phase codes are reader-visible; name the challenge or the component "
        "instead:\n  " + "\n  ".join(offenders[:20])
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
