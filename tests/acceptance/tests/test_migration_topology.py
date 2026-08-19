"""Live source-VM migration topology contract tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from catalog_migrate.azure import validate_migration_topology
from catalog_migrate.contracts import load_json
from catalog_migrate.errors import PreconditionError
from catalog_migrate.process import ProcessResult


class TopologyRunner:
    """Return deterministic Azure resource state for one source/target pair."""

    def __init__(self, target: dict) -> None:
        self.target = target
        self.calls: list[list[str]] = []

    def run(
        self,
        argv: list[str],
        *,
        environment: dict[str, str] | None = None,
        input_text: str | None = None,
        timeout: int = 300,
    ) -> ProcessResult:
        del environment, input_text, timeout
        self.calls.append(list(argv))
        source_vnet = self.target["network"]["migrationSourceVirtualNetworkResourceId"]
        target_vnet = self.target["network"]["virtualNetworkResourceId"]
        if argv[:2] == ["az", "version"]:
            return ProcessResult('{"azure-cli":"2.80.0"}', "")
        if argv[:3] == ["az", "vm", "show"]:
            nic_id = (
                source_vnet.rsplit("/providers/Microsoft.Network/virtualNetworks/", 1)[0]
                + "/providers/Microsoft.Network/networkInterfaces/nic-source"
            )
            return ProcessResult(nic_id, "")
        if argv[:4] == ["az", "network", "nic", "show"]:
            return ProcessResult(f"{source_vnet}/subnets/snet-vm", "")
        if argv[:3] == ["az", "resource", "show"]:
            return ProcessResult("Succeeded", "")
        if argv[:5] == ["az", "network", "vnet", "peering", "show"]:
            peering_name = argv[argv.index("--name") + 1]
            source_peering_name = self.target["network"][
                "migrationSourceToTargetPeeringResourceId"
            ].rsplit("/", 1)[-1]
            remote = (
                target_vnet
                if peering_name.casefold() == source_peering_name.casefold()
                else source_vnet
            )
            return ProcessResult(
                json.dumps(
                    {
                        "provisioningState": "Succeeded",
                        "peeringState": "Connected",
                        "remoteVirtualNetworkId": remote,
                    }
                ),
                "",
            )
        if argv[:5] == ["az", "network", "private-dns", "link", "vnet"]:
            return ProcessResult(
                json.dumps(
                    {
                        "provisioningState": "Succeeded",
                        "virtualNetworkId": source_vnet,
                        "registrationEnabled": False,
                    }
                ),
                "",
            )
        raise AssertionError(f"Unexpected command: {argv}")


def test_topology_records_live_host_subnet_peerings_and_dns(repo_root: Path) -> None:
    """Topology proof records only live reciprocal and source-linked resources."""
    target = load_json(
        repo_root / "workshop/contracts/azure-target-output.bootstrap.example.json"
    )
    runner = TopologyRunner(target)

    evidence = validate_migration_topology(
        runner,
        target,
        metadata_resource_id=lambda: target["network"]["migrationSourceVmResourceId"],
    )

    assert evidence["host"] == "source-vm"
    assert evidence["sourceSubnetResourceId"].endswith("/subnets/snet-vm")
    assert evidence["sourceToTargetPeering"]["peeringState"] == "Connected"
    assert evidence["targetToSourcePeering"]["remoteVirtualNetworkResourceId"] == (
        target["network"]["migrationSourceVirtualNetworkResourceId"]
    )
    assert len(evidence["privateDnsZoneLinks"]) == 2
    assert evidence["topologyValidated"] is True


def test_topology_rejects_a_different_imds_vm_before_azure_queries(
    repo_root: Path,
) -> None:
    """The declared source VM must exactly match the current IMDS host."""
    target = load_json(
        repo_root / "workshop/contracts/azure-target-output.bootstrap.example.json"
    )
    runner = TopologyRunner(target)

    with pytest.raises(PreconditionError, match="IMDS"):
        validate_migration_topology(
            runner,
            target,
            metadata_resource_id=lambda: (
                target["network"]["migrationSourceVmResourceId"] + "-other"
            ),
        )

    assert runner.calls == []
