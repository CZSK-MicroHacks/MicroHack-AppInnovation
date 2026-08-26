"""Cross-layer checks for the refrozen Azure implementation."""

from __future__ import annotations

from pathlib import Path

from catalog_migrate.contracts import load_json


def test_bicep_emits_refrozen_topology_and_direct_exporter_configuration(
    repo_root: Path,
) -> None:
    """IaC creates the migration path and avoids ACA managed telemetry routing."""
    main = (repo_root / "infra/main.bicep").read_text(encoding="utf-8")
    environment = (
        repo_root / "infra/modules/environment.bicep"
    ).read_text(encoding="utf-8")

    assert "migrationSourceVirtualNetworkResourceId" in main
    assert "migrationSourceVmResourceId" in main
    assert "applicationRevisionRole" in main
    assert "source-peering.bicep" in main
    assert "Microsoft.Network/virtualNetworks/virtualNetworkPeerings" in environment
    assert "migrationPrivateDnsZoneLinkResourceIds" in environment
    assert "schemaVersion: '1.2.0'" in environment
    assert "applicationRevisionRole:" in environment
    assert "APPLICATIONINSIGHTS_CONNECTION_STRING" in environment
    assert "secretRef: 'application-insights-connection-string'" in environment
    assert "appInsightsConfiguration" not in environment
    assert "openTelemetryConfiguration" not in environment
    assert "'172.20.0.0/16'" in environment
    assert "'172.21.0.0/16'" in environment
    assert "'10.42.0.0/16'" not in environment


def test_dotnet_exports_all_signals_to_azure_monitor_without_losing_otlp(
    repo_root: Path,
) -> None:
    """The .NET runtime selects Azure Monitor in ACA and OTLP locally."""
    project = (
        repo_root
        / "solutions/reference/dotnet/src/LegoCatalog.App/LegoCatalog.App.csproj"
    ).read_text(encoding="utf-8")
    program = (
        repo_root / "solutions/reference/dotnet/src/LegoCatalog.App/Program.cs"
    ).read_text(encoding="utf-8")

    assert (
        'PackageReference Include="Azure.Monitor.OpenTelemetry.Exporter" '
        'Version="1.8.3"' in project
    )
    assert "AddAzureMonitorTraceExporter" in program
    assert "AddAzureMonitorMetricExporter" in program
    assert "AddAzureMonitorLogExporter" in program
    assert "AddOtlpExporter" in program
    assert "cannot both be configured" in " ".join(program.split())


def test_java_uses_the_locked_azure_monitor_autoconfigure_versions(
    repo_root: Path,
) -> None:
    """The Java runtime uses one compatible SDK for Azure Monitor or local OTLP."""
    pom = (repo_root / "solutions/reference/java/pom.xml").read_text(encoding="utf-8")
    application = (
        repo_root
        / "solutions/reference/java/src/main/java/com/microsoft/microhack/"
        "catalog/CatalogApplication.java"
    ).read_text(encoding="utf-8")
    options = (
        repo_root
        / "solutions/reference/java/src/main/java/com/microsoft/microhack/"
        "catalog/config/CatalogRuntimeOptions.java"
    ).read_text(encoding="utf-8")

    assert "<opentelemetry.version>1.58.0</opentelemetry.version>" in pom
    assert (
        "<opentelemetry.instrumentation.version>"
        "2.24.0-alpha</opentelemetry.instrumentation.version>"
    ) in pom
    assert "<artifactId>azure-monitor-opentelemetry-autoconfigure</artifactId>" in pom
    assert "<version>1.6.0</version>" in pom
    assert "AzureMonitorAutoConfigure.customize" in application
    assert "APPLICATIONINSIGHTS_CONNECTION_STRING" in options
    assert "cannot both be configured" in " ".join(options.split())


def test_dotnet_vm_installs_the_locked_self_contained_sqlpackage(
    repo_root: Path,
) -> None:
    """The source VM has a runtime-independent, digest-pinned BACPAC tool."""
    tool = load_json(repo_root / "workshop/toolchain.lock.json")["tools"][
        "sqlPackage"
    ]["windowsStandalone"]
    provisioner = (
        repo_root / "baseInfra/scripts/provision-vm.ps1"
    ).read_text(encoding="utf-8")

    assert tool["url"] in provisioner
    assert tool["sha256"] in provisioner
    assert tool["signaturePublisher"] in provisioner
    assert "SqlPackage.exe" in provisioner
    assert "Add-MachinePath -Path $SqlPackageRoot" in provisioner
