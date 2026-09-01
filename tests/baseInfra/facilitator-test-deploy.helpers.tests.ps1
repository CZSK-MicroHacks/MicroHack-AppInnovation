#!/usr/bin/env pwsh
<#
.SYNOPSIS
Checks the pure helper functions in baseInfra/scripts/facilitator-test-deploy.ps1.

.DESCRIPTION
Loads only the function definitions out of the deployment script's AST, so the interactive
body never runs, then asserts the HCL rendering and password rules that the generated
tfvars file depends on. Exits non-zero when any expectation fails.

.EXAMPLE
pwsh tests/baseInfra/facilitator-test-deploy.helpers.tests.ps1
#>

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$scriptPath = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../../baseInfra/scripts/facilitator-test-deploy.ps1'))

$parseErrors = $null
$tokens = $null
$ast = [System.Management.Automation.Language.Parser]::ParseFile($scriptPath, [ref]$tokens, [ref]$parseErrors)

if ($parseErrors) {
    $parseErrors | ForEach-Object {
        Write-Host "PARSE ERROR line $($_.Extent.StartLineNumber): $($_.Message)" -ForegroundColor Red
    }
    exit 1
}

$functions = $ast.FindAll(
    { param($node) $node -is [System.Management.Automation.Language.FunctionDefinitionAst] },
    $true)
foreach ($function in $functions) {
    . ([scriptblock]::Create($function.Extent.Text))
}

$failures = 0

function Assert-Equal {
    param(
        [Parameter(Mandatory)][string]$Label,
        $Actual,
        $Expected
    )

    if ("$Actual" -ceq "$Expected") {
        Write-Host "ok   $Label"
    }
    else {
        Write-Host "FAIL $Label" -ForegroundColor Red
        Write-Host "     actual   : $Actual"
        Write-Host "     expected : $Expected"
        $script:failures++
    }
}

Assert-Equal 'ConvertTo-HclList renders a quoted list' `
    (ConvertTo-HclList @('swedencentral', 'westeurope')) `
    '["swedencentral", "westeurope"]'

Assert-Equal 'ConvertTo-HclList renders an empty list' (ConvertTo-HclList @()) '[]'

Assert-Equal 'ConvertTo-HclString quotes a plain value' (ConvertTo-HclString 'azureuser') '"azureuser"'

# Windows state paths reach HCL through this helper, so backslashes must be escaped.
Assert-Equal 'ConvertTo-HclString escapes backslashes' `
    (ConvertTo-HclString 'C:\Users\fac\state.tfstate') `
    '"C:\\Users\\fac\\state.tfstate"'

Assert-Equal 'ConvertTo-HclString escapes quotes' (ConvertTo-HclString 'a"b') '"a\"b"'

Assert-Equal 'suggested test password is accepted' `
    (Test-WindowsPasswordComplexity 'MicroHack!Test2026') 'True'

Assert-Equal 'short password is rejected' (Test-WindowsPasswordComplexity 'Ab1!x') 'False'
Assert-Equal 'two character classes are rejected' `
    (Test-WindowsPasswordComplexity 'abcdefghijklmnop') 'False'
Assert-Equal 'three character classes are accepted' `
    (Test-WindowsPasswordComplexity 'abcdefghijkl1A') 'True'

Write-Host ''
if ($failures -gt 0) {
    Write-Host "$failures check(s) failed." -ForegroundColor Red
    exit 1
}

Write-Host 'All helper checks passed.' -ForegroundColor Green
