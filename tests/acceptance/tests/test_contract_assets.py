"""Executable tests that freeze schemas, corpus identity, and normalization."""

from __future__ import annotations

import json
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
        "argumentsAreExact": True,
        "deriveTargetSettingsFromTargetOutput": True,
        "secretsInEnvironmentOnly": True,
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
    assert contract["failureProtocol"] == {
        "schema": "migration-error.schema.json",
        "outputChannel": "stderr",
        "exactlyOneDocument": True,
        "tracebackForbidden": True,
        "secretValuesForbidden": True,
    }

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
    (evidence / "rollback.md").write_text("rollback fixture\n", encoding="utf-8")
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
        "schemaVersion": "1.1.0",
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

    rollback = evidence / "rollback.md"
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
