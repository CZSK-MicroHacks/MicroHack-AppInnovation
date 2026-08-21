# Challenge 0: compare and select a baseline

## Objective

Verify both facilitator-provisioned legacy applications against the same observable
baseline, select one stack for the workshop, and deallocate the unselected VM only after
facilitator approval. This challenge changes no application or database content.

You will compare:

| Stack ID | VM | Runtime and database | Local URL |
| --- | --- | --- | --- |
| `dotnet-sqlserver` | `vm-dotnet-userNNN` | .NET 8 and SQL Server 2022 Express | `http://localhost:5000` |
| `java-postgresql` | `vm-java-userNNN` | Microsoft OpenJDK 17 and PostgreSQL 18 | `http://localhost:8080` |

Both applications must expose the same catalog behavior. Runtime, framework, database,
and implementation details are valid selection criteria; observable contract drift is
not.

## Facilitator start gate

Before you begin, the facilitator must provide:

- the exact participant resource group and both VM names;
- Azure Bastion access to both private VMs;
- the immutable repository commit used to provision them;
- confirmation that both VM provisioning states succeeded; and
- a decision on whether you may deallocate the unselected VM yourself.

Stop if either VM is unavailable or if you can see another participant's resource group.
Do not repair provisioning during this challenge.

## 1. Verify the .NET baseline

Connect to the .NET VM through Azure Bastion, open PowerShell in the repository root,
and run:

```powershell
$stack = 'dotnet'
$baseUrl = 'http://localhost:5000'
$expectedSourceCommit = '<facilitator-provided-40-character-lowercase-commit>'
$markerPath = "C:\MicroHack\status\$stack-smoke.json"
$marker = Get-Content $markerPath -Raw | ConvertFrom-Json

if (
  $expectedSourceCommit -cnotmatch '^[0-9a-f]{40}$' -or
  $marker.stack -ne $stack -or
  $marker.sourceCommit -cne $expectedSourceCommit -or
  $marker.healthRoute -ne '/healthz' -or
  $marker.readinessRoute -ne '/readyz' -or
  $marker.canonicalImage -notmatch '^/images/[0-9a-f-]{36}\.png$' -or
  $marker.figures -ne 198 -or
  $marker.categories -ne 20 -or
  $marker.images -ne 198
) {
  throw 'The .NET provisioning marker does not match the frozen baseline.'
}

$health = Invoke-WebRequest "$baseUrl/healthz" -UseBasicParsing
$ready = Invoke-WebRequest "$baseUrl/readyz" -UseBasicParsing
$catalog = Invoke-WebRequest "$baseUrl/" -UseBasicParsing
$image = Invoke-WebRequest "$baseUrl$($marker.canonicalImage)" -UseBasicParsing

if (
  $health.StatusCode -ne 200 -or
  $ready.StatusCode -ne 200 -or
  $catalog.StatusCode -ne 200 -or
  $image.StatusCode -ne 200 -or
  $image.Headers.'Content-Type' -notlike 'image/png*'
) {
  throw 'The .NET baseline HTTP checks failed.'
}

New-Item evidence -ItemType Directory -Force | Out-Null
$marker | ConvertTo-Json -Depth 10 |
  Set-Content evidence/ch00-dotnet-baseline.json -Encoding utf8
```

Record the full `sourceCommit` and `verifiedAtUtc` values. Do not edit the copied marker.
The source marker is `C:\MicroHack\status\dotnet-smoke.json`.

## 2. Verify the Java baseline

Connect to the Java VM and repeat the same check with only these two values changed:

```powershell
$stack = 'java'
$baseUrl = 'http://localhost:8080'
```

Write the copied marker to `evidence/ch00-java-baseline.json`. The expected corpus and
routes are identical to the .NET check. The source marker is
`C:\MicroHack\status\java-smoke.json`. Use the same facilitator-provided
`$expectedSourceCommit`; do not substitute the current branch or a short SHA.

## 3. Compare implementation boundaries

Review both applications before choosing:

| Decision area | .NET/SQL Server | Java/PostgreSQL |
| --- | --- | --- |
| Legacy runtime | .NET 8 | Microsoft OpenJDK 17 |
| Legacy database | SQL Server 2022 Express | PostgreSQL 18 |
| Modernized runtime | .NET 10 | Microsoft OpenJDK 21 |
| Azure database | Azure SQL Database | Azure Database for PostgreSQL Flexible Server |
| Application directory | `dotnet/` | `java/` |
| Target stack ID | `dotnet-sqlserver` | `java-postgresql` |

The target behavior, canonical data, acceptance harness, Azure Container Apps runtime,
and downstream Challenges 2 through 6 are shared. Select based on the implementation you
want to practice, not on an expectation that one stack has a weaker success contract.

## 4. Record the selection

On the selected VM, replace the placeholders and create the selection record:

```powershell
$selectedStack = '<dotnet-sqlserver|java-postgresql>'
$selectedVm = '<selected-vm-name>'
$unselectedVm = '<unselected-vm-name>'
$resourceGroup = '<rg-userNNN>'
$expectedSourceCommit = '<same-facilitator-provided-commit>'

$selection = [ordered]@{
  schemaVersion = '1.0.0'
  selectedStack = $selectedStack
  selectedVm = $selectedVm
  unselectedVm = $unselectedVm
  resourceGroup = $resourceGroup
  sourceCommit = $expectedSourceCommit
  baselineContract = 'workshop/contracts/behavior-contract.json@1.1.0'
  checkedStacks = @('dotnet-sqlserver', 'java-postgresql')
  selectedAtUtc = (Get-Date).ToUniversalTime().ToString('o')
}

$selection | ConvertTo-Json -Depth 10 |
  Set-Content evidence/ch00-selection.json -Encoding utf8
```

Validate the machine-readable decision:

```powershell
$selection = Get-Content evidence/ch00-selection.json -Raw | ConvertFrom-Json
$allowed = @('dotnet-sqlserver', 'java-postgresql')
$expectedSourceCommit = '<same-facilitator-provided-commit>'

if ($selection.resourceGroup -notmatch '^rg-(user[0-9]{3})$') {
  throw 'Challenge 0 resource group must identify one participant.'
}
$participant = $Matches[1]
$expectedSelectedVm = if ($selection.selectedStack -eq 'dotnet-sqlserver') {
  "vm-dotnet-$participant"
} else {
  "vm-java-$participant"
}
$expectedUnselectedVm = if ($selection.selectedStack -eq 'dotnet-sqlserver') {
  "vm-java-$participant"
} else {
  "vm-dotnet-$participant"
}

if (
  $selection.schemaVersion -ne '1.0.0' -or
  $selection.selectedStack -notin $allowed -or
  $selection.selectedVm -ne $expectedSelectedVm -or
  $selection.unselectedVm -ne $expectedUnselectedVm -or
  $expectedSourceCommit -cnotmatch '^[0-9a-f]{40}$' -or
  $selection.sourceCommit -cne $expectedSourceCommit -or
  $selection.baselineContract -ne
    'workshop/contracts/behavior-contract.json@1.1.0' -or
  @($selection.checkedStacks).Count -ne 2 -or
  @($selection.checkedStacks | Sort-Object) -join ',' -ne
    'dotnet-sqlserver,java-postgresql'
) {
  throw 'Challenge 0 selection evidence is invalid.'
}
```

## 5. Deallocate the unselected VM

This is a live Azure mutation. Run it only after the facilitator authorizes your exact
resource group and VM name:

```powershell
az vm deallocate `
  --resource-group $selection.resourceGroup `
  --name $selection.unselectedVm
```

Confirm the VM reports `PowerState/deallocated`. Do not delete the VM, disk, NIC,
database, resource group, or shared network. The facilitator can restore it with
`az vm start` if a golden-stack rejoin is needed.

## Success criteria

- Both immutable provisioning markers report their correct stack and the same
  `198/20/198` corpus, and each marker's `sourceCommit` equals the same
  facilitator-provided full commit.
- Both applications return HTTP 200 for catalog, liveness, readiness, and one canonical
  PNG image.
- `evidence/ch00-selection.json` passes the validation block and names exactly one stack.
- The selected VM remains running.
- The unselected VM is deallocated with approval, or the facilitator records that
  deallocation is deferred.
- No application, database, role assignment, provider, or resource is modified beyond
  the approved VM power-state change.

Continue to [Challenge 1](../ch01/README.md) and the path chosen by the facilitator.
