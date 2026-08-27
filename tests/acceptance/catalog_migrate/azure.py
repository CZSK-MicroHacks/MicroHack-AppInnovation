"""Live Azure topology and release verification."""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from typing import Any

import httpx

from catalog_migrate.database import azure_environment, check_tool_versions
from catalog_migrate.errors import InvalidInputError, PreconditionError, VerificationError
from catalog_migrate.process import CommandRunner

IMDS_RESOURCE_ID_ENDPOINT = (
    "http://169.254.169.254/metadata/instance/compute/resourceId"
    "?api-version=2021-02-01&format=text"
)


def _resource_id_parts(resource_id: str) -> dict[str, Any]:
    """Parse the bounded Azure resource IDs emitted by the target contract."""
    parts = resource_id.strip("/").split("/")
    try:
        subscription_index = parts.index("subscriptions")
        resource_group_index = parts.index("resourceGroups")
        provider_index = parts.index("providers")
        resource_parts = parts[provider_index + 2 :]
        if len(resource_parts) % 2:
            raise ValueError
        return {
            "subscription": parts[subscription_index + 1],
            "resourceGroup": parts[resource_group_index + 1],
            "namespace": parts[provider_index + 1],
            "types": resource_parts[0::2],
            "names": resource_parts[1::2],
        }
    except (ValueError, IndexError) as error:
        raise InvalidInputError(f"malformed Azure resource ID: {resource_id}") from error


def _metadata_resource_id() -> str:
    """Read the current Azure VM resource ID without honoring proxy variables."""
    try:
        with httpx.Client(trust_env=False, timeout=5.0) as client:
            response = client.get(
                IMDS_RESOURCE_ID_ENDPOINT,
                headers={"Metadata": "true"},
            )
            response.raise_for_status()
    except httpx.HTTPError as error:
        raise PreconditionError("Azure IMDS host identity could not be read") from error
    resource_id = response.text.strip()
    if not resource_id:
        raise PreconditionError("Azure IMDS returned an empty host identity")
    return resource_id


_TRANSIENT_PROVISIONING_STATES = frozenset({"Creating", "Migrating", "Updating"})


def _resource_provisioning_state(
    runner: CommandRunner,
    resource_id: str,
    subscription_id: str,
) -> str:
    """Read one live Azure resource's provisioning state."""
    return runner.run(
        [
            "az",
            "resource",
            "show",
            "--ids",
            resource_id,
            "--subscription",
            subscription_id,
            "--query",
            "properties.provisioningState",
            "--output",
            "tsv",
        ],
        environment=azure_environment(),
    ).stdout.strip()


def _require_resource_state(
    runner: CommandRunner,
    resource_id: str,
    subscription_id: str,
    *,
    attempts: int = 5,
    retry_seconds: float = 20.0,
    sleep: Callable[[float], None] = time.sleep,
) -> None:
    """Require one live Azure resource to have completed provisioning.

    A resource under platform maintenance reports ``Updating`` while remaining
    entirely healthy: Azure flips a virtual machine's provisioning state for the
    duration of every guest patch assessment, and nothing about that state says the
    machine is the wrong host or that its network topology has changed, which is all
    this validation is asking. A single point-in-time read therefore fails a correct
    migration for a reason unrelated to what it verifies, and it does so at second
    zero of an operation that takes many minutes. Known-transient states are retried
    for a bounded window; a terminal state such as ``Failed`` still fails at once.

    The observed state is named in the failure. "Is not provisioned" describes a
    resource that was never created, which is almost never what actually happened,
    and a caller who cannot see the difference between ``Updating`` and ``Failed``
    cannot tell "wait" apart from "stop".
    """
    state = ""
    for attempt in range(max(attempts, 1)):
        state = _resource_provisioning_state(runner, resource_id, subscription_id)
        if state == "Succeeded":
            return
        if state not in _TRANSIENT_PROVISIONING_STATES:
            break
        if attempt + 1 < max(attempts, 1):
            sleep(retry_seconds)
    raise PreconditionError(
        f"Azure resource is not provisioned: {resource_id} "
        f"(provisioningState={state or 'unavailable'})"
    )


def _load_json_output(value: str, description: str) -> dict[str, Any]:
    """Parse one Azure CLI object result."""
    try:
        document = json.loads(value)
    except json.JSONDecodeError as error:
        raise VerificationError(f"{description} output is not valid JSON") from error
    if not isinstance(document, dict):
        raise VerificationError(f"{description} output must be an object")
    return document


def _peering_evidence(
    runner: CommandRunner,
    resource_id: str,
    expected_remote_id: str,
    subscription_id: str,
) -> dict[str, Any]:
    """Verify one live peering and return schema-shaped evidence."""
    parts = _resource_id_parts(resource_id)
    result = runner.run(
        [
            "az",
            "network",
            "vnet",
            "peering",
            "show",
            "--resource-group",
            parts["resourceGroup"],
            "--vnet-name",
            parts["names"][-2],
            "--name",
            parts["names"][-1],
            "--subscription",
            subscription_id,
            "--query",
            (
                "{provisioningState:provisioningState,"
                "peeringState:peeringState,"
                "remoteVirtualNetworkId:remoteVirtualNetwork.id}"
            ),
            "--output",
            "json",
        ],
        environment=azure_environment(),
    )
    observed = _load_json_output(result.stdout, "VNet peering")
    if (
        observed.get("provisioningState") != "Succeeded"
        or observed.get("peeringState") != "Connected"
        or str(observed.get("remoteVirtualNetworkId", "")).casefold()
        != expected_remote_id.casefold()
    ):
        raise PreconditionError("migration VNet peering is not reciprocal and connected")
    return {
        "resourceId": resource_id,
        "remoteVirtualNetworkResourceId": expected_remote_id,
        "provisioningState": "Succeeded",
        "peeringState": "Connected",
    }


def _dns_link_evidence(
    runner: CommandRunner,
    resource_id: str,
    source_vnet_id: str,
    subscription_id: str,
) -> dict[str, Any]:
    """Verify one private-DNS link targets the source VNet without registration."""
    parts = _resource_id_parts(resource_id)
    result = runner.run(
        [
            "az",
            "network",
            "private-dns",
            "link",
            "vnet",
            "show",
            "--resource-group",
            parts["resourceGroup"],
            "--zone-name",
            parts["names"][-2],
            "--name",
            parts["names"][-1],
            "--subscription",
            subscription_id,
            "--query",
            (
                "{provisioningState:provisioningState,"
                "virtualNetworkId:virtualNetwork.id,"
                "registrationEnabled:registrationEnabled}"
            ),
            "--output",
            "json",
        ],
        environment=azure_environment(),
    )
    observed = _load_json_output(result.stdout, "private DNS link")
    if (
        observed.get("provisioningState") != "Succeeded"
        or observed.get("registrationEnabled") is not False
        or str(observed.get("virtualNetworkId", "")).casefold()
        != source_vnet_id.casefold()
    ):
        raise PreconditionError("migration private-DNS link does not target the source VNet")
    return {
        "resourceId": resource_id,
        "virtualNetworkResourceId": source_vnet_id,
        "provisioningState": "Succeeded",
        "registrationEnabled": False,
    }


def validate_migration_topology(
    runner: CommandRunner,
    target: dict[str, Any],
    *,
    metadata_resource_id: Callable[[], str] = _metadata_resource_id,
) -> dict[str, Any]:
    """Prove the command runs on the declared source VM with live target reachability."""
    network = target["network"]
    source_vm_id = network["migrationSourceVmResourceId"]
    source_vnet_id = network["migrationSourceVirtualNetworkResourceId"]
    target_vnet_id = network["virtualNetworkResourceId"]
    observed_vm_id = metadata_resource_id().strip()
    if observed_vm_id.casefold() != source_vm_id.casefold():
        raise PreconditionError("Azure IMDS host identity differs from the source VM")

    source_parts = _resource_id_parts(source_vm_id)
    subscription_id = source_parts["subscription"]
    check_tool_versions(runner, azure=True)
    _require_resource_state(runner, source_vm_id, subscription_id)
    _require_resource_state(runner, source_vnet_id, subscription_id)
    nic_output = runner.run(
        [
            "az",
            "vm",
            "show",
            "--ids",
            source_vm_id,
            "--subscription",
            subscription_id,
            "--query",
            "networkProfile.networkInterfaces[].id",
            "--output",
            "tsv",
        ],
        environment=azure_environment(),
    ).stdout
    nic_ids = [line.strip() for line in nic_output.splitlines() if line.strip()]
    if len(nic_ids) != 1:
        raise PreconditionError("source VM must have exactly one network interface")
    nic_id = nic_ids[0]
    _require_resource_state(runner, nic_id, subscription_id)
    subnet_output = runner.run(
        [
            "az",
            "network",
            "nic",
            "show",
            "--ids",
            nic_id,
            "--subscription",
            subscription_id,
            "--query",
            "ipConfigurations[].subnet.id",
            "--output",
            "tsv",
        ],
        environment=azure_environment(),
    ).stdout
    subnet_ids = [line.strip() for line in subnet_output.splitlines() if line.strip()]
    if len(subnet_ids) != 1:
        raise PreconditionError("source VM NIC must have exactly one subnet")
    source_subnet_id = subnet_ids[0]
    observed_vnet_id = source_subnet_id.rsplit("/subnets/", 1)[0]
    if observed_vnet_id.casefold() != source_vnet_id.casefold():
        raise PreconditionError("source VM subnet is outside the declared source VNet")

    source_peering = _peering_evidence(
        runner,
        network["migrationSourceToTargetPeeringResourceId"],
        target_vnet_id,
        subscription_id,
    )
    target_peering = _peering_evidence(
        runner,
        network["migrationTargetToSourcePeeringResourceId"],
        source_vnet_id,
        subscription_id,
    )
    dns_links = sorted(
        (
            _dns_link_evidence(runner, resource_id, source_vnet_id, subscription_id)
            for resource_id in network["migrationPrivateDnsZoneLinkResourceIds"]
        ),
        key=lambda item: item["resourceId"],
    )
    return {
        "host": "source-vm",
        "hostVmResourceId": source_vm_id,
        "sourceVirtualNetworkResourceId": source_vnet_id,
        "sourceSubnetResourceId": source_subnet_id,
        "sourceToTargetPeering": source_peering,
        "targetToSourcePeering": target_peering,
        "privateDnsZoneLinks": dns_links,
        "topologyValidated": True,
    }


def validate_release(
    runner: CommandRunner,
    target: dict[str, Any],
    rollback_revision: str,
) -> None:
    """Verify the immutable ACR tag and exact healthy inactive baseline revision."""
    if target["applicationRevisionRole"] != "release":
        raise InvalidInputError("handoff requires a release-role target output")
    application = target["application"]
    image = target["containerImage"]
    if application is None or image is None:
        raise InvalidInputError("handoff requires application-stage image output")
    expected_rollback = (
        f"{application['containerAppName']}--baseline-{target['sourceCommit'][:12]}"
    )
    if rollback_revision != expected_rollback:
        raise InvalidInputError("rollback revision is not the deterministic baseline")
    if rollback_revision == application["revisionName"]:
        raise InvalidInputError("rollback revision must differ from the release revision")

    check_tool_versions(runner, azure=True)
    resource_group_parts = target["resourceGroup"]["resourceId"].strip("/").split("/")
    try:
        subscription_id = resource_group_parts[
            resource_group_parts.index("subscriptions") + 1
        ]
    except (ValueError, IndexError) as error:
        raise InvalidInputError("target resource-group ID is malformed") from error
    registry_name = target["containerRegistry"]["loginServer"].split(".", 1)[0]
    observed_digest = runner.run(
        [
            "az",
            "acr",
            "manifest",
            "show-metadata",
            "--registry",
            registry_name,
            "--name",
            f"{image['repository']}:{image['tag']}",
            "--subscription",
            subscription_id,
            "--query",
            "digest",
            "--output",
            "tsv",
        ],
        environment=azure_environment(),
    ).stdout.strip()
    if observed_digest != image["digest"]:
        raise VerificationError("ACR commit tag does not resolve to the release digest")

    observed = _load_json_output(
        runner.run(
            [
                "az",
                "containerapp",
                "revision",
                "show",
                "--resource-group",
                target["resourceGroup"]["name"],
                "--name",
                application["containerAppName"],
                "--revision",
                rollback_revision,
                "--subscription",
                subscription_id,
                "--query",
                (
                    "{active:properties.active,"
                    "health:properties.healthState,"
                    "error:properties.provisioningError,"
                    "images:properties.template.containers[].image}"
                ),
                "--output",
                "json",
            ],
            environment=azure_environment(),
        ).stdout,
        "rollback revision",
    )
    expected_image = (
        f"{target['containerRegistry']['loginServer']}/"
        f"{image['repository']}@{image['digest']}"
    )
    if (
        observed.get("active") is not False
        or observed.get("health") != "Healthy"
        or observed.get("error") not in (None, "")
        or observed.get("images") != [expected_image]
    ):
        raise VerificationError("rollback revision is not the healthy inactive baseline")
