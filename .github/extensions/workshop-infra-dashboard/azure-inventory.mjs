import { execFile } from "node:child_process";
import { homedir } from "node:os";
import { join } from "node:path";
import { promisify } from "node:util";

const execFileAsync = promisify(execFile);
const EXPECTED_ENVIRONMENTS = 35;
const EXPECTED_VMS_PER_ENVIRONMENT = 2;
const RESOURCE_GROUP_PATTERN = /^rg-labuser-\d{4}$/i;
const AZURE_CONFIG_DIR = join(homedir(), ".azure-hack");
const ENVIRONMENT_CHECK_CONCURRENCY = 3;

let refreshPromise;
let inventoryState = {
    status: "idle",
    data: null,
    error: null,
    startedAt: null,
    completedAt: null,
    durationMs: null,
    progress: null,
};

export function getInventoryState() {
    return inventoryState;
}

async function runAz(args) {
    try {
        const { stdout } = await execFileAsync("az", args, {
            env: { ...process.env, AZURE_CONFIG_DIR },
            maxBuffer: 20 * 1024 * 1024,
            timeout: 5 * 60 * 1000,
        });
        return JSON.parse(stdout || "[]");
    } catch (error) {
        const stderr = typeof error?.stderr === "string" ? error.stderr.trim() : "";
        const message = stderr || (error instanceof Error ? error.message : String(error));
        throw new Error(message);
    }
}

async function mapWithConcurrency(items, concurrency, mapper) {
    const results = new Array(items.length);
    let nextIndex = 0;

    async function worker() {
        while (nextIndex < items.length) {
            const index = nextIndex;
            nextIndex += 1;
            results[index] = await mapper(items[index], index);
        }
    }

    await Promise.all(
        Array.from({ length: Math.min(concurrency, items.length) }, () => worker()),
    );
    return results;
}

function buildEnvironment(resourceGroup, virtualMachines) {
    const vms = virtualMachines
        .filter((vm) => vm.resourceGroup.toLowerCase() === resourceGroup.name.toLowerCase())
        .sort((left, right) => left.name.localeCompare(right.name));
    const vmCount = vms.length;

    return {
        ...resourceGroup,
        vms,
        vmCount,
        expectedVmCount: EXPECTED_VMS_PER_ENVIRONMENT,
        complete: vmCount === EXPECTED_VMS_PER_ENVIRONMENT,
        appWorkingCount: 0,
        appWarningCount: 0,
        status: vmCount === EXPECTED_VMS_PER_ENVIRONMENT
            ? "complete"
            : vmCount < EXPECTED_VMS_PER_ENVIRONMENT
                ? "incomplete"
                : "unexpected",
    };
}

function getAppTarget(vmName) {
    const normalizedName = vmName.toLowerCase();
    if (normalizedName.includes("dotnet")) {
        return { stack: "dotnet", port: 5000 };
    }
    if (normalizedName.includes("java")) {
        return { stack: "java", port: 8080 };
    }
    return null;
}

function buildAppProbeScript(target) {
    return `
$port = ${target.port}
$listeners = @(Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue)
function Invoke-AppProbe([string]$Uri) {
    try {
        $response = Invoke-WebRequest -UseBasicParsing -Uri $Uri -TimeoutSec 20
        return [int]$response.StatusCode
    }
    catch {
        return $null
    }
}
$baseUrl = "http://localhost:$port"
$rootStatus = Invoke-AppProbe "$baseUrl/"
$healthStatus = Invoke-AppProbe "$baseUrl/healthz"
$readyStatus = Invoke-AppProbe "$baseUrl/readyz"
$working = $listeners.Count -gt 0 -and
    $rootStatus -eq 200 -and
    $healthStatus -eq 200 -and
    $readyStatus -eq 200
$warning = if ($working) {
    $null
}
elseif ($listeners.Count -eq 0) {
    "No process is listening on port $port."
}
else {
    "One or more localhost HTTP probes did not return 200."
}
$result = [ordered]@{
    stack = "${target.stack}"
    port = $port
    status = if ($working) { "working" } else { "warning" }
    listenerCount = $listeners.Count
    rootStatus = $rootStatus
    healthStatus = $healthStatus
    readyStatus = $readyStatus
    warning = $warning
    checkedAt = [DateTime]::UtcNow.ToString("o")
}
Write-Output ("APP_CHECK_JSON:" + ($result | ConvertTo-Json -Compress))
`;
}

async function checkVirtualMachineApp(subscriptionId, vm) {
    const target = getAppTarget(vm.name);
    if (!target) {
        return {
            stack: "unknown",
            port: null,
            status: "warning",
            listenerCount: 0,
            rootStatus: null,
            healthStatus: null,
            readyStatus: null,
            warning: "The VM name does not identify a supported workshop stack.",
            checkedAt: new Date().toISOString(),
        };
    }

    try {
        const messages = await runAz([
            "vm",
            "run-command",
            "invoke",
            "--subscription",
            subscriptionId,
            "--resource-group",
            vm.resourceGroup,
            "--name",
            vm.name,
            "--command-id",
            "RunPowerShellScript",
            "--scripts",
            buildAppProbeScript(target),
            "--query",
            "value[].message",
            "-o",
            "json",
            "--only-show-errors",
        ]);
        const markerLine = messages
            .flatMap((message) => String(message).split(/\r?\n/))
            .find((line) => line.startsWith("APP_CHECK_JSON:"));

        if (!markerLine) {
            throw new Error("The VM probe returned no application status payload.");
        }

        return JSON.parse(markerLine.slice("APP_CHECK_JSON:".length));
    } catch (error) {
        return {
            stack: target.stack,
            port: target.port,
            status: "warning",
            listenerCount: null,
            rootStatus: null,
            healthStatus: null,
            readyStatus: null,
            warning: error instanceof Error ? error.message : String(error),
            checkedAt: new Date().toISOString(),
        };
    }
}

async function attachApplicationChecks(subscriptions, onProgress) {
    const targets = subscriptions.flatMap((subscription) =>
        subscription.environments.map((environment) => ({ subscription, environment })),
    );
    let completedEnvironmentCount = 0;

    onProgress(completedEnvironmentCount, targets.length, null);
    await mapWithConcurrency(targets, ENVIRONMENT_CHECK_CONCURRENCY, async (target) => {
        await Promise.all(
            target.environment.vms.map(async (vm) => {
                vm.app = await checkVirtualMachineApp(target.subscription.id, vm);
            }),
        );
        completedEnvironmentCount += 1;
        onProgress(completedEnvironmentCount, targets.length, target.environment.name);
    });

    for (const subscription of subscriptions) {
        for (const environment of subscription.environments) {
            environment.appWorkingCount = environment.vms.filter(
                (vm) => vm.app?.status === "working",
            ).length;
            environment.appWarningCount = environment.vms.filter(
                (vm) => vm.app?.status === "warning",
            ).length;
        }
        subscription.appWorkingCount = subscription.environments.reduce(
            (total, environment) => total + environment.appWorkingCount,
            0,
        );
        subscription.appWarningCount = subscription.environments.reduce(
            (total, environment) => total + environment.appWarningCount,
            0,
        );
    }
}

async function loadSubscription(subscription) {
    try {
        const [resourceGroups, virtualMachines] = await Promise.all([
            runAz([
                "group",
                "list",
                "--subscription",
                subscription.id,
                "--query",
                "[].{name:name,location:location,provisioningState:properties.provisioningState,id:id}",
                "-o",
                "json",
                "--only-show-errors",
            ]),
            runAz([
                "vm",
                "list",
                "-d",
                "--subscription",
                subscription.id,
                "--query",
                "[].{name:name,resourceGroup:resourceGroup,location:location,powerState:powerState,provisioningState:provisioningState,vmSize:hardwareProfile.vmSize,privateIps:privateIps,publicIps:publicIps,id:id}",
                "-o",
                "json",
                "--only-show-errors",
            ]),
        ]);

        const workshopGroups = resourceGroups
            .filter((group) => RESOURCE_GROUP_PATTERN.test(group.name))
            .sort((left, right) => left.name.localeCompare(right.name));
        const workshopVms = virtualMachines.filter((vm) => RESOURCE_GROUP_PATTERN.test(vm.resourceGroup));
        const environments = workshopGroups.map((group) => buildEnvironment(group, workshopVms));

        return {
            ...subscription,
            environments,
            environmentCount: environments.length,
            vmCount: environments.reduce((total, environment) => total + environment.vmCount, 0),
            completeEnvironmentCount: environments.filter((environment) => environment.complete).length,
            appWorkingCount: 0,
            appWarningCount: 0,
            error: null,
        };
    } catch (error) {
        return {
            ...subscription,
            environments: [],
            environmentCount: 0,
            vmCount: 0,
            completeEnvironmentCount: 0,
            appWorkingCount: 0,
            appWarningCount: 0,
            error: error instanceof Error ? error.message : String(error),
        };
    }
}

function summarize(subscriptions) {
    const environmentCount = subscriptions.reduce(
        (total, subscription) => total + subscription.environmentCount,
        0,
    );
    const vmCount = subscriptions.reduce((total, subscription) => total + subscription.vmCount, 0);
    const completeEnvironmentCount = subscriptions.reduce(
        (total, subscription) => total + subscription.completeEnvironmentCount,
        0,
    );
    const unexpectedEnvironmentCount = subscriptions.reduce(
        (total, subscription) =>
            total + subscription.environments.filter((environment) => environment.status === "unexpected").length,
        0,
    );
    const incompleteEnvironmentCount = subscriptions.reduce(
        (total, subscription) =>
            total + subscription.environments.filter((environment) => environment.status === "incomplete").length,
        0,
    );
    const failedSubscriptionCount = subscriptions.filter((subscription) => subscription.error).length;
    const appWorkingCount = subscriptions.reduce(
        (total, subscription) => total + subscription.appWorkingCount,
        0,
    );
    const appWarningCount = subscriptions.reduce(
        (total, subscription) => total + subscription.appWarningCount,
        0,
    );

    return {
        subscriptionCount: subscriptions.length,
        failedSubscriptionCount,
        expectedEnvironmentCount: EXPECTED_ENVIRONMENTS,
        environmentCount,
        missingEnvironmentCount: Math.max(EXPECTED_ENVIRONMENTS - environmentCount, 0),
        completeEnvironmentCount,
        incompleteEnvironmentCount,
        unexpectedEnvironmentCount,
        expectedVmCount: EXPECTED_ENVIRONMENTS * EXPECTED_VMS_PER_ENVIRONMENT,
        vmCount,
        missingVmCount: Math.max(
            EXPECTED_ENVIRONMENTS * EXPECTED_VMS_PER_ENVIRONMENT - vmCount,
            0,
        ),
        completionPercent: Math.round((completeEnvironmentCount / EXPECTED_ENVIRONMENTS) * 100),
        appWorkingCount,
        appWarningCount,
        appCheckedCount: appWorkingCount + appWarningCount,
        appCompletionPercent: vmCount > 0 ? Math.round((appWorkingCount / vmCount) * 100) : 0,
    };
}

async function loadInventory() {
    const accounts = await runAz([
        "account",
        "list",
        "--all",
        "--query",
        "[?state=='Enabled'].{id:id,name:name,state:state,isDefault:isDefault,tenantId:tenantId}",
        "-o",
        "json",
        "--only-show-errors",
    ]);
    const subscriptions = await mapWithConcurrency(
        accounts.sort((left, right) => left.name.localeCompare(right.name)),
        3,
        loadSubscription,
    );
    await attachApplicationChecks(
        subscriptions,
        (completed, total, resourceGroup) => {
            inventoryState = {
                ...inventoryState,
                progress: {
                    phase: "applications",
                    completed,
                    total,
                    message: resourceGroup
                        ? `Checked ${resourceGroup}`
                        : "Starting hosted application checks",
                },
            };
        },
    );

    return {
        azureConfigDir: AZURE_CONFIG_DIR,
        expectedVmCountPerEnvironment: EXPECTED_VMS_PER_ENVIRONMENT,
        summary: summarize(subscriptions),
        subscriptions,
    };
}

export async function refreshInventory() {
    if (refreshPromise) {
        return refreshPromise;
    }

    const startedAt = new Date();
    inventoryState = {
        ...inventoryState,
        status: "loading",
        error: null,
        startedAt: startedAt.toISOString(),
        progress: {
            phase: "inventory",
            completed: 0,
            total: null,
            message: "Loading subscriptions, resource groups, and virtual machines",
        },
    };

    refreshPromise = (async () => {
        try {
            const data = await loadInventory();
            inventoryState = {
                status: "ready",
                data,
                error: null,
                startedAt: startedAt.toISOString(),
                completedAt: new Date().toISOString(),
                durationMs: Date.now() - startedAt.getTime(),
                progress: {
                    phase: "complete",
                    completed: data.summary.environmentCount,
                    total: data.summary.environmentCount,
                    message: "Refresh complete",
                },
            };
        } catch (error) {
            inventoryState = {
                ...inventoryState,
                status: "error",
                error: error instanceof Error ? error.message : String(error),
                completedAt: new Date().toISOString(),
                durationMs: Date.now() - startedAt.getTime(),
                progress: {
                    ...inventoryState.progress,
                    phase: "failed",
                    message: "Refresh failed",
                },
            };
        } finally {
            refreshPromise = undefined;
        }

        return inventoryState;
    })();

    return refreshPromise;
}
