<#
.SYNOPSIS
Checks the doubled facilitator VM quota and estimates its monthly compute and OS-disk cost.

.DESCRIPTION
Reads the selected VM SKU and current regional Azure compute usage, then fails when the
requested two-VM-per-participant footprint exceeds regional or VM-family vCPU quota.
It queries the public Azure Retail Prices API for a Windows consumption rate and Premium
SSD managed-disk rate, prints the exact footprint, and can enforce a facilitator cost ceiling.
#>

[CmdletBinding()]
param(
    [Parameter(Mandatory)]
    [ValidatePattern('^[0-9a-fA-F-]{36}$')]
    [string]$SubscriptionId,

    [Parameter(Mandatory)]
    [ValidateNotNullOrEmpty()]
    [string[]]$Locations,

    [Parameter(Mandatory)]
    [ValidateRange(1, 254)]
    [int]$ParticipantCount,

    [string]$VmSize = 'Standard_D2as_v5',

    [ValidateRange(127, 32768)]
    [int]$OsDiskSizeGiB = 127,

    [ValidateRange(0.01, 1000000)]
    [decimal]$MaximumEstimatedMonthlyCostUsd
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'

function Invoke-AzureCliJson {
    param(
        [Parameter(Mandatory)]
        [string[]]$Arguments
    )

    $Output = & az @Arguments --only-show-errors --output json
    if ($LASTEXITCODE -ne 0) {
        throw "Azure CLI command failed: az $($Arguments -join ' ')"
    }
    return $Output | ConvertFrom-Json
}

function Get-RetailPrice {
    param(
        [Parameter(Mandatory)]
        [string]$Filter
    )

    $EncodedFilter = [uri]::EscapeDataString($Filter)
    $Uri = "https://prices.azure.com/api/retail/prices?currencyCode=USD&`$filter=$EncodedFilter"
    $Response = Invoke-RestMethod -Uri $Uri
    $Price = @($Response.Items | Where-Object {
            $_.type -eq 'Consumption' -and $_.retailPrice -gt 0
        } | Sort-Object retailPrice | Select-Object -First 1)
    if ($Price.Count -ne 1) {
        throw "Azure Retail Prices returned no consumption price for filter: $Filter"
    }
    return $Price[0]
}

function Get-PremiumDiskSku {
    param(
        [Parameter(Mandatory)]
        [int]$SizeGiB
    )

    $Tiers = @(
        @{ MaximumGiB = 64; Name = 'P6' },
        @{ MaximumGiB = 128; Name = 'P10' },
        @{ MaximumGiB = 256; Name = 'P15' },
        @{ MaximumGiB = 512; Name = 'P20' },
        @{ MaximumGiB = 1024; Name = 'P30' },
        @{ MaximumGiB = 2048; Name = 'P40' },
        @{ MaximumGiB = 4096; Name = 'P50' },
        @{ MaximumGiB = 8192; Name = 'P60' },
        @{ MaximumGiB = 16384; Name = 'P70' },
        @{ MaximumGiB = 32768; Name = 'P80' }
    )
    $Tier = $Tiers | Where-Object { $SizeGiB -le $_.MaximumGiB } | Select-Object -First 1
    if ($null -eq $Tier) {
        throw "No Premium SSD tier supports an operating-system disk of $SizeGiB GiB."
    }
    return $Tier.Name
}

$null = Invoke-AzureCliJson -Arguments @(
    'account',
    'show',
    '--subscription',
    $SubscriptionId
)

$TotalVmCount = $ParticipantCount * 2
$TotalDiskCount = $ParticipantCount * 2
$TotalDiskGiB = $TotalDiskCount * $OsDiskSizeGiB
$MonthlyHours = 730
$RegionalResults = @()
$TotalMonthlyCompute = [decimal]0
$TotalMonthlyDisks = [decimal]0
$PremiumDiskSku = Get-PremiumDiskSku -SizeGiB $OsDiskSizeGiB

foreach ($Location in @($Locations | Select-Object -Unique)) {
    $Sku = @(
        Invoke-AzureCliJson -Arguments @(
            'vm',
            'list-skus',
            '--subscription',
            $SubscriptionId,
            '--location',
            $Location,
            '--size',
            $VmSize,
            '--all'
        ) | Where-Object {
            $_.name -eq $VmSize -and
            -not ($_.restrictions | Where-Object { $_.reasonCode -eq 'NotAvailableForSubscription' })
        } | Select-Object -First 1
    )
    if ($Sku.Count -ne 1) {
        throw "$VmSize is unavailable for subscription $SubscriptionId in $Location."
    }

    $VcpuCapability = $Sku[0].capabilities |
        Where-Object { $_.name -eq 'vCPUs' } |
        Select-Object -First 1
    if ($null -eq $VcpuCapability) {
        throw "Azure did not return a vCPU capability for $VmSize in $Location."
    }
    $VcpusPerVm = [int]$VcpuCapability.value
    $Family = [string]$Sku[0].family
    $ParticipantsInRegion = @(
        for ($Index = 0; $Index -lt $ParticipantCount; $Index++) {
            if ($Locations[$Index % $Locations.Count] -eq $Location) {
                $Index
            }
        }
    ).Count
    $RegionVmCount = $ParticipantsInRegion * 2
    $RequiredVcpus = $RegionVmCount * $VcpusPerVm

    $Usage = Invoke-AzureCliJson -Arguments @(
        'vm',
        'list-usage',
        '--subscription',
        $SubscriptionId,
        '--location',
        $Location
    )
    $RegionalQuota = $Usage |
        Where-Object { $_.name.value -eq 'cores' } |
        Select-Object -First 1
    $FamilyQuota = $Usage |
        Where-Object {
            $_.name.value -eq $Family -or
            $_.name.localizedValue -match [regex]::Escape($Family)
        } |
        Select-Object -First 1
    $VmQuota = $Usage |
        Where-Object { $_.name.value -eq 'virtualMachines' } |
        Select-Object -First 1
    $DiskQuota = $Usage |
        Where-Object { $_.name.value -eq 'PremiumStorageManagedDisks' } |
        Select-Object -First 1
    if ($null -eq $RegionalQuota -or $null -eq $FamilyQuota -or
        $null -eq $VmQuota -or $null -eq $DiskQuota) {
        throw "Azure quota data did not include regional cores, $Family, virtual machines, and Premium managed disks in $Location."
    }
    $RegionalAvailable = [int]$RegionalQuota.limit - [int]$RegionalQuota.currentValue
    $FamilyAvailable = [int]$FamilyQuota.limit - [int]$FamilyQuota.currentValue
    $VirtualMachinesAvailable = [int]$VmQuota.limit - [int]$VmQuota.currentValue
    $PremiumDisksAvailable = [int]$DiskQuota.limit - [int]$DiskQuota.currentValue
    if ($RequiredVcpus -gt $RegionalAvailable) {
        throw "$Location requires $RequiredVcpus vCPUs but only $RegionalAvailable regional vCPUs are available."
    }
    if ($RequiredVcpus -gt $FamilyAvailable) {
        throw "$Location requires $RequiredVcpus $Family vCPUs but only $FamilyAvailable are available."
    }
    if ($RegionVmCount -gt $VirtualMachinesAvailable) {
        throw "$Location requires $RegionVmCount VMs but only $VirtualMachinesAvailable are available."
    }
    if ($RegionVmCount -gt $PremiumDisksAvailable) {
        throw "$Location requires $RegionVmCount Premium OS disks but only $PremiumDisksAvailable are available."
    }

    $ArmLocation = [string]$Sku[0].locations[0]
    $VmPrice = Get-RetailPrice -Filter (
        "serviceName eq 'Virtual Machines' and armRegionName eq '$ArmLocation' " +
        "and armSkuName eq '$VmSize' and priceType eq 'Consumption' " +
        "and skuName eq '$VmSize' and contains(productName, 'Windows')"
    )
    $DiskPrice = Get-RetailPrice -Filter (
        "serviceName eq 'Storage' and armRegionName eq '$ArmLocation' " +
        "and armSkuName eq 'Premium_SSD_Managed_Disk_$PremiumDiskSku' " +
        "and meterName eq '$PremiumDiskSku LRS Disk' and priceType eq 'Consumption'"
    )
    $MonthlyCompute = [decimal]$VmPrice.retailPrice * $MonthlyHours * $RegionVmCount
    $MonthlyDisks = [decimal]$DiskPrice.retailPrice * $RegionVmCount
    $TotalMonthlyCompute += $MonthlyCompute
    $TotalMonthlyDisks += $MonthlyDisks

    $RegionalResults += [pscustomobject]@{
        location                = $Location
        participants           = $ParticipantsInRegion
        virtualMachines        = $RegionVmCount
        vmFamily               = $Family
        vcpusPerVm             = $VcpusPerVm
        requiredVcpus          = $RequiredVcpus
        regionalVcpusAvailable = $RegionalAvailable
        familyVcpusAvailable   = $FamilyAvailable
        virtualMachinesAvailable = $VirtualMachinesAvailable
        premiumDisksAvailable  = $PremiumDisksAvailable
        premiumDiskSku         = $PremiumDiskSku
        monthlyComputeUsd      = [math]::Round($MonthlyCompute, 2)
        monthlyOsDiskUsd       = [math]::Round($MonthlyDisks, 2)
    }
}

$TotalMonthly = $TotalMonthlyCompute + $TotalMonthlyDisks
$Result = [pscustomobject]@{
    subscriptionId           = $SubscriptionId
    participants             = $ParticipantCount
    virtualMachines          = $TotalVmCount
    vmSize                   = $VmSize
    vcpusPerVm               = $RegionalResults[0].vcpusPerVm
    osDisks                  = $TotalDiskCount
    osDiskGiB                = $TotalDiskGiB
    estimatedMonthlyComputeUsd = [math]::Round($TotalMonthlyCompute, 2)
    estimatedMonthlyOsDiskUsd  = [math]::Round($TotalMonthlyDisks, 2)
    estimatedMonthlyTotalUsd   = [math]::Round($TotalMonthly, 2)
    sharedFoundationExcluded = @('Azure Bastion', 'NAT Gateway', 'public IP addresses')
    regions                  = $RegionalResults
}

$Result | ConvertTo-Json -Depth 5
if ($PSBoundParameters.ContainsKey('MaximumEstimatedMonthlyCostUsd') -and
    $TotalMonthly -gt $MaximumEstimatedMonthlyCostUsd) {
    throw "Estimated monthly VM and OS-disk cost $TotalMonthly USD exceeds the configured ceiling $MaximumEstimatedMonthlyCostUsd USD."
}
