# Common Errors & Resolutions

Documenting issues encountered while implementing the data generator (Azure OpenAI Responses API + Images) and their fixes.

## 1. Unsupported parameter: `response_format` / `modalities`
**Symptom:** Exceptions when calling `client.responses.create` with `response_format` or `modalities=["text","image"]`.

**Cause:** The installed OpenAI Python SDK (Azure variant) version doesn't support those legacy / speculative parameters for the Responses API in this context.

**Resolution:** Use `client.responses.parse` with `text_format="json_schema"` and a Pydantic model to obtain structured outputs (categories + items). Removed unsupported args.

## 2. Pydantic `@validator` Deprecation Warnings
**Symptom:** Warnings about `@validator` being deprecated (Pydantic v2).

**Cause:** Pydantic v2 replaced classic validators with `@field_validator`.

**Resolution:** Migrated all validators to `@field_validator(..., mode="before"|"after")` as appropriate.

## 3. Image generation via Responses API returning HTTP 400
**Symptom:** Consistent 400 Bad Request when attempting image generation through `responses.create` (both with `modalities` and with tool definitions for image generation).

**Cause:** The SDK / deployment combination did not accept the attempted usage pattern for inline image generation (likely feature mismatch or unsupported tool contract in current API version).

**Resolution:** Switched to dedicated `client.images.generate(...)` call using the image deployment. Added simple retry with exponential backoff. This produced images reliably.

## 4. Partial image set (198/200) produced
**Symptom:** After generation, two catalog entries had no corresponding PNG files.

**Possible Causes:** Transient API errors beyond retry attempts or silent failures not surfaced (insufficient logging around failures at time of run).

**Resolution:** Implemented `prune_missing_images.py` to:
- Detect mismatch between `catalog.json` and `images/` directory
- Optionally prune missing entries (creates `catalog.json.bak` once)

## 5. Difficulty scripting PowerShell inline heredoc for Python
**Symptom:** Parser errors (`Missing file specification after redirection operator`) when trying to embed Python with `<<` in PowerShell.

**Cause:** Bash-style heredoc syntax used in PowerShell environment.

**Resolution:** Instead of heredoc, created a temporary file via `$temp = New-TemporaryFile` and wrote Python code with `Set-Content`, then executed it. Ultimately replaced need with a permanent maintenance script.

## 6. Environment variable mismatch for batch size
**Symptom:** Confusion: `.env` retained `BATCH_SIZE=50` while code defaulted to 20.

**Cause:** Documentation / implementation divergence after requirement change.

**Resolution:** Code honors explicit CLI or internal default 20; environment variable to be aligned later. (Action item.)

## 7. Missing structured output fields risk / schema drift
**Symptom:** Concern about LLM dropping required keys.

**Cause:** Prompt or schema not strictly enforced without structured parsing.

**Resolution:** Using `responses.parse` with Pydantic schema ensures automatic validation; invalid outputs raise early exceptions.

## 8. Minimal logging for failed image attempts
**Symptom:** Hard to diagnose why two images failed.

**Cause:** Retry loop only printed generic messages; failures not persisted.

**Resolution (Planned):** Enhance `_generate_single_image` to log error details (status codes, messages) and record to a `failed_images.json` for post-run analysis.

## 9. Pydantic core build fails under Python 3.14
**Symptom:** `uv sync` attempts to compile `pydantic-core` and fails because its PyO3 version supports Python only through 3.13.

**Cause:** An unconstrained `requires-python = ">=3.12"` selected a locally installed Python 3.14 interpreter for the acceptance harness.

**Resolution:** Pin `tests/acceptance/.python-version` to Python 3.12 and constrain the project to `>=3.12,<3.14`. This selects published Pydantic wheels and keeps local and container validation consistent.

## 10. The .NET solution reports no projects to restore
**Symptom:** `dotnet build dotnet/LegoCatalog.sln` succeeds immediately with `Unable to find a project to restore`.

**Cause:** The solution file contained literal `\t` text instead of tab indentation in its `GlobalSection` records, so the SDK did not parse the project configuration.

**Resolution:** Recreated the solution with valid solution syntax and added both the application and contract test projects. The pinned .NET 8 SDK now restores, builds, and tests the complete solution.

## 11. EF migration tooling cannot find ASP.NET Core 8
**Symptom:** `dotnet-ef` 8.0.22 fails because only the .NET 8 runtime and ASP.NET Core 10 runtime are present.

**Cause:** EF's .NET 8 tool requires the matching ASP.NET Core shared framework; a newer SDK/runtime does not satisfy that framework roll-forward boundary.

**Resolution:** Install the frozen .NET SDK 8.0.424 in session-local or VM tool storage and run restore, build, migration, and tests with that `DOTNET_ROOT`.

## 12. SQL Server corpus verification differs despite matching rows
**Symptom:** Full acceptance reports corpus or reset differences even though SQL Server contains the expected UUIDs and values.

**Cause:** SQL Server orders `uniqueidentifier` values by its binary GUID semantics, not by canonical UUID text. SQL Server also canonicalizes the image check expression with an extra right-hand grouping pair.

**Resolution:** Sort native-client rows by their normalized text tuples in the verifier and freeze the actual SQL Server metadata expression produced by the contract migration.

## 13. OpenTelemetry 1.12 packages report NuGet vulnerabilities
**Symptom:** Restore emits `NU1902` for `OpenTelemetry.Api` and `OpenTelemetry.Exporter.OpenTelemetryProtocol`.

**Cause:** The prior 1.12.0 packages are affected by the published `GHSA-g94r-2vxg-569j` and `GHSA-4625-4j76-fww9` advisories.

**Resolution:** Align the OpenTelemetry SDK, exporter, and instrumentations on 1.17.0, which includes the fixes, and verify the resolved dependency graph with `dotnet list package --vulnerable --include-transitive`.

## 14. Database duration telemetry uses the wrong unit
**Symptom:** `db.client.operation.duration` is emitted in milliseconds even though the standard instrument name is used.

**Cause:** The custom histogram and its call sites copied the application's millisecond timing convention instead of the OpenTelemetry database semantic convention.

**Resolution:** Declare the histogram unit as `s`, record `Stopwatch.Elapsed.TotalSeconds`, and assert the instrument unit in the native telemetry contract test.

## 15. PostgreSQL 18 reports `NOT NULL` as `CHECK`
**Symptom:** Exact constraint verification reports one unexpected `*_not_null` `CHECK` row for every non-null column even though schema nullability is correct.

**Cause:** PostgreSQL 18 stores not-null constraints in `pg_constraint` with `contype='n'` and exposes them through `information_schema.table_constraints` as `CHECK`. Earlier versions did not expose this metadata in the same way.

**Resolution:** Continue verifying nullability through `information_schema.columns`, and include only true `pg_constraint.contype='c'` checks in the normalized explicit-constraint set. Validate the result against the pinned PostgreSQL 18.6 image.

## 16. Tomcat normalizes traversal into an existing route
**Symptom:** Allowing encoded separators makes probes such as `/images/../healthz` normalize to a valid route and return 200 instead of the frozen image-path 404.

**Cause:** Connector normalization occurs before Spring MVC and the image-store validator, so validating only the mapped path is too late.

**Resolution:** Preserve the original request target, reject raw, encoded, double-encoded, and dot-segment aliases in a highest-precedence filter, and test aliases against existing routes as well as missing files.

## 17. Jackson binding accepts schema-invalid import documents
**Symptom:** A valid array followed by another JSON root, null members, numeric values coerced to strings, or duplicate product IDs can bypass POJO validation.

**Cause:** Ordinary data binding does not enforce exact token types, one-root EOF, or document-level identity uniqueness.

**Resolution:** Parse the import as a token stream with explicit root, member, field, value, EOF, and duplicate checks. Convert every document failure to the controlled validation exception before repository access.

## 18. Structured Logback records are absent from OTLP logs
**Symptom:** Traces and metrics reach the configured OpenTelemetry exporter, but required structured application logs do not appear.

**Cause:** Writing through SLF4J does not connect Logback to the OpenTelemetry SDK logger provider by itself.

**Resolution:** Attach the official OpenTelemetry Logback appender, install it on the application's single auto-configured SDK, preserve MDC attributes, emit the distinct `exception` record, and verify exported records with an in-memory SDK log exporter.

## 19. Spring Boot-managed pgJDBC version is vulnerable
**Symptom:** Dependency scanning reports HIGH-severity `CVE-2026-54291` in pgJDBC 42.7.11.

**Cause:** The managed driver version permits a SCRAM-SHA-256-PLUS downgrade.

**Resolution:** Override `postgresql.version` to fixed version 42.7.12 and verify the resolved Maven graph with a HIGH/CRITICAL vulnerability scan.

## 20. UTF-16 iteration disagrees with cross-runtime text rules
**Symptom:** Supplementary characters, spacing marks, or enclosing marks produce different slugs and length results across Python, .NET, and Java.

**Cause:** Iterating .NET `char` values splits supplementary Unicode scalars, while a single `NonSpacingMark` check omits `Mc` and `Me`. Reusing code-point counts for database maxima also ignores `nvarchar` UTF-16 storage.

**Resolution:** Iterate `Rune` values for normalization and code-point minimums, remove all `Mn`/`Mc`/`Me` categories, and validate persisted maxima separately with UTF-16 code-unit counts. Exercise exact supplementary boundaries through the shared vectors.

## 21. Nullable JSON array members bypass C# annotations
**Symptom:** Importing `[null]` throws `NullReferenceException` and returns HTTP 500 instead of the controlled invalid-catalog 400 response.

**Cause:** `System.Text.Json` permits null array entries at runtime even when the generic element type is annotated non-null.

**Resolution:** Deserialize array elements as nullable, reject each null member explicitly before field access, and cover the case in the native whole-document validation test.

## 22. Exception telemetry disagrees with a committed HTTP response
**Symptom:** A request commits one status, then throws, while the span, metric, or completion log reports a synthetic 500 that was never sent.

**Cause:** Exception handling treated failure status as an override even after the server could no longer mutate the response. Completion logging outside a `finally` block could also disappear entirely when an exception propagated.

**Resolution:** Set 500 only while a response remains uncommitted, always record the response's resulting wire status, and emit completion telemetry from `finally`. Keep exception/span error status separate from the HTTP response-status attribute.

## 23. Native test names and exported counters provide false evidence
**Symptom:** A handoff can satisfy a requirement with an unrelated test sharing the same display name, or reject valid cumulative counter output because its value is greater than one.

**Cause:** TRX/JUnit validation ignored class and method identity, while a per-event instrumentation rule was incorrectly applied to an exported aggregate.

**Resolution:** Bind TRX results through `testId` to `TestMethod` class and method, bind JUnit cases to `classname` plus display name, and require exact stack-specific identities. Prove one-unit increments in native SDK tests; validate exported rejected-counter values as positive integral aggregates.

## 24. Azure Retail Prices returns no Premium managed-disk result
**Symptom:** A P10 OS-disk cost preflight returns an empty `Items` array even though Premium SSD is available in the selected region.

**Cause:** The Retail Prices API uses the singular ARM SKU `Premium_SSD_Managed_Disk_P10`, not `Premium_SSD_Managed_Disks_P10`. A SKU-only query can also select the low-cost disk-mount meter instead of the disk capacity meter. Likewise, sorting Windows VM rates without an exact `skuName` selects Spot or Low Priority pricing.

**Resolution:** Map the requested disk size to its Premium tier, filter on the singular ARM SKU, require the exact `<tier> LRS Disk` meter name, and match the ordinary VM `skuName` exactly. The corrected P10 Sweden Central query returns one monthly capacity price and excludes Spot/Low Priority compute rates.

## 25. Protected extension settings still expose secrets in local process commands
**Symptom:** Terraform stores a Custom Script Extension command in `protectedSettings`, but generated database and API credentials still appear as reversible command arguments to the launched PowerShell and database installer/client processes.

**Cause:** Control-plane protection prevents ARM deployment-history disclosure but does not remove command-line arguments from the Windows process model or local telemetry.

**Resolution:** Bootstrap the generated values from ACL-restricted VM custom data into an ACL-restricted local payload, then scrub the executable copy and `CustomData.bin`. Keep the extension command secret-free, use protected SQL Server/PostgreSQL response files, authenticate clients with `SQLCMDPASSWORD`/`PGPASSWORD`, and pass password-changing SQL through protected temporary input files removed in `finally`.

## 26. Windows PowerShell adds a BOM to installer response files
**Symptom:** SQL Server or PostgreSQL unattended setup can reject or ignore the first option in an otherwise valid protected response file.

**Cause:** Windows PowerShell 5.1 `Set-Content -Encoding UTF8` writes a UTF-8 byte-order mark that strict INI/option-file parsers can treat as part of the first token.

**Resolution:** Write protected text with `System.Text.UTF8Encoding(false)` so SQL Server configuration files, PostgreSQL option files, and database input files are UTF-8 without a BOM.

## 27. A secret-bearing comment is still PowerShell source
**Symptom:** A secret is absent from process arguments but is appended as a comment to a script that PowerShell parses before the script removes it.

**Cause:** PowerShell Script Block Logging records processed source, including comments; stripping the payload from inside the provisioner happens too late.

**Resolution:** Treat custom data as a versioned data bundle. Run a secret-free bootstrap that separates the payload and clean script, applies SYSTEM/Administrators-only ACLs, clears the original bundle, and only then launches a new PowerShell process on the clean script.

## 28. Task retries and interrupted swaps can race reprovisioning
**Symptom:** A scheduled task can relaunch while source/output is changing, or an interrupted directory swap can delete the only rollback copy on its next attempt.

**Cause:** Stopping only a currently Running task leaves Ready retry state enabled, while unconditional `.previous` cleanup ignores the absent-destination recovery state.

**Resolution:** Disable the exact stack task before stopping it and re-enable only after registration. Restore `.previous` whenever the destination is absent, then retain that rollback until the staged move succeeds.

## 29. Encoded Custom Script Extension bootstrap exceeds `cmd.exe` limits
**Symptom:** A secret-free PowerShell bootstrap is valid but the Windows VM extension cannot launch its approximately 14,330-character `-EncodedCommand`.

**Cause:** Windows Custom Script Extension launches through the command shell, whose 8,191-character limit is smaller than the encoded maintained bootstrap.

**Resolution:** Gzip the secret-free bootstrap with Terraform `base64gzip`, decode/decompress it inside a compact PowerShell 5.1 wrapper, and dot-source the resulting script block before invoking it with non-secret metadata. Build the entire command in one local and reject lengths above 7,800 characters.

## 30. Azure Files mounts conflict with disabled shared-key policy
**Symptom:** An Azure Container Apps SMB storage definition is valid, but the mounted share cannot authenticate after policy disables Storage shared-key access.

**Cause:** Container Apps environment storage for a classic Azure Files SMB share uses the storage account key. Managed identity can authorize Blob SDK access, but it does not replace the account-key field for this mount path.

**Resolution:** Use Blob-backed images with managed identity as the policy-compatible default. Keep Azure Files as the compatibility path only where the workshop subscription permits shared-key access or has an explicit exemption; do not report it as live-validated in a subscription that enforces the conflicting policy.

## 31. Parallel integrity probes assign hashes to the wrong packages
**Symptom:** Every dependency digest is valid, but each hash is recorded beside a different package coordinate.

**Cause:** Concurrent download commands return independently, and unlabeled output is associated by display order instead of by artifact name.

**Resolution:** Recompute integrity values with the coordinate printed beside each result, then freeze exact coordinate-to-hash assertions in the contract suite. Never infer package ownership from parallel command completion order.

## 32. Valid examples do not freeze deployment behavior
**Symptom:** Approved examples use the intended region, IaC mechanism, resource types, and endpoint shape, while alternative or unrelated values still validate.

**Cause:** Examples demonstrate one valid document but do not constrain other documents. Cross-file equality can also make two consistently wrong producer outputs appear compatible.

**Resolution:** Encode fixed decisions as schema constants, validate typed Azure IDs and common scope, and add executable cross-field checks for values JSON Schema cannot relate directly, such as Container App FQDNs, revision names, workload principals, and toolchain versions.

## 33. A PostgreSQL password administrator cannot bootstrap Entra principals
**Symptom:** Flexible Server accepts password-authenticated restore operations, but managed-identity application setup cannot create the mapped Entra database role.

**Cause:** Only a configured Microsoft Entra administrator can create or enable Entra principals. `pgaadauth_create_principal` or `pgaadauth_create_principal_with_oid` must be invoked by that administrator against the `postgres` database.

**Resolution:** Provision a distinct non-secret Entra administrator identity in addition to the local password administrator. Verify the migration caller is that declared identity, acquire an ephemeral `oss-rdbms` token, pass it only through the child `psql` environment, and create the workload principal on `postgres` with `isAdmin=false` and `isMfa=false` before granting application privileges.

## 34. Target runtimes cannot use source-runtime container pins
**Symptom:** The runtime matrix requires .NET 10 and Java 21, but the only locked application images contain .NET 8 and Java 17, so a digest-pinned target Dockerfile is impossible.

**Cause:** Application container entries were copied from the source baseline while target runtime versions were frozen separately.

**Resolution:** Treat application containers as target artifacts. Resolve each exact target tag, record the labeled linux/amd64 manifest digest, pull by `tag@digest`, execute the image to prove its runtime version, and assert the complete coordinate-to-digest mapping in the contract suite before implementation starts.

## 35. Container Apps managed Application Insights drops metrics
**Symptom:** Traces and logs reach Application Insights from Azure Container Apps, but required OpenTelemetry metrics are absent.

**Cause:** The managed Container Apps Application Insights destination supports traces and logs, not metrics.

**Resolution:** Do not configure the managed destination. Use locked direct Azure Monitor OpenTelemetry exporters for traces, metrics, and logs in Container Apps while retaining OTLP export for local execution.

## 36. Resource IDs do not prove private migration connectivity
**Symptom:** Migration output names the expected VM, VNet, peerings, and private-DNS links, but the source VM still cannot reach private target endpoints.

**Cause:** Correctly shaped resource IDs and `Succeeded` provisioning states do not prove the command is running on that VM or that peerings and DNS links reference the intended reciprocal networks.

**Resolution:** Match the current host to the declared VM through Azure Instance Metadata Service, derive its live VNet from its NIC subnet, require both peerings to be `Connected` with reciprocal remote-VNet IDs, and require every target private-DNS link to reference the source VNet with registration disabled. Preserve those observations in migration evidence.

## 37. Azure Monitor autoconfigure conflicts with pinned OpenTelemetry
**Symptom:** Java compiles with Azure Monitor autoconfigure, but telemetry initialization fails or silently loses signals at runtime.

**Cause:** `azure-monitor-opentelemetry-autoconfigure` 1.6.0 requires OpenTelemetry 1.58.0 while the application directly pins 1.54.1; Maven dependency management selects the incompatible older graph.

**Resolution:** Lock and use OpenTelemetry core 1.58.0 with instrumentation 2.24.0-alpha, which is the matching instrumentation release, and verify the effective Maven dependency graph before runtime validation.

## 38. Incompatible user `uv.toml` blocks repository tests
**Symptom:** `uv run` exits before resolving the project because a user-level `~/.config/uv/uv.toml` contains a setting unsupported by the installed `uv`.

**Cause:** User configuration is parsed before the repository command and can be newer than the active `uv` binary.

**Resolution:** Leave user configuration untouched and run the repository gate with `uv --no-config run ...`; use `uv --no-config lock --check --offline` for the matching lock gate.

## 39. SqlPackage ignores an invented password environment variable
**Symptom:** BACPAC export reaches SqlPackage without a password even though `SQLPACKAGE_SOURCEPASSWORD` is set.

**Cause:** SqlPackage does not define that environment variable as a source-password input. Its supported non-interactive input surface includes response files.

**Resolution:** Read the password only from the declared migration environment, write `/SourcePassword:<value>` to a newly created ACL-restricted response file, pass only `@<path>` in argv, register the value separately for error redaction without forwarding it to the child environment, and overwrite/remove the file in `finally`.

## 40. The SqlPackage global tool requires a newer .NET runtime
**Symptom:** The pinned SqlPackage NuGet tool installs but cannot start on the P3 .NET VM because its required .NET runtime is newer than the source VM runtime.

**Cause:** The global-tool package is framework-dependent; installing the locked .NET 8 SDK alone does not satisfy the newer tool runtime.

**Resolution:** Provision the exact self-contained Windows SqlPackage archive instead. Verify its SHA-256, verify the extracted executable's Authenticode publisher and version, and add that fixed directory to machine PATH.

## 41. Azure Files OAuth operations require backup intent
**Symptom:** Azure Files list, upload, or download fails despite login authentication and the privileged file-data role.

**Cause:** Azure CLI Files data-plane OAuth requires both `--auth-mode login` and `--backup-intent` for this role-backed migration path.

**Resolution:** Add both options to every Files list, upload, and download command. Do not add the Files-only option to Blob commands.

## 42. A fixed target VNet overlaps a participant source VNet
**Symptom:** Peering creation fails or private routes are ambiguous for the participant whose P3 VNet falls inside the target range.

**Cause:** The former target `10.42.0.0/16` contains participant `user042`'s deterministic `10.42.0.0/22` source range.

**Resolution:** Use non-overlapping stack-specific target ranges: `172.20.0.0/16` for .NET and `172.21.0.0/16` for Java, with deterministic subnets inside each range.

## 43. Truncating before redaction leaks a long secret prefix
**Symptom:** A typed JSON error omits the complete secret but exposes its first 1,024 characters.

**Cause:** The formatter normalizes and truncates the raw tool message before replacing the full secret, so the truncated prefix no longer equals the redaction token.

**Resolution:** Replace every complete known secret in the raw message first, then normalize whitespace and apply the message-length bound.

## 44. SQL authentication cannot verify an Entra-only Azure SQL target
**Symptom:** Managed .NET acceptance reaches Azure SQL but every `sqlcmd` operation fails authentication even though migration and the deployed application succeed.

**Cause:** The target disables SQL authentication, while the acceptance harness supplies `-U` and `SQLCMDPASSWORD`.

**Resolution:** Acquire a transient Azure SQL token through the isolated facilitator profile, supply it only as `SQLCMDACCESS_TOKEN`, invoke `sqlcmd -G` without `-U`, and use that same authentication path for corpus verification, import-state comparisons, and acceptance-fixture cleanup. Keep username/password authentication limited to local SQL Server and PostgreSQL.

## 45. Homebrew `psql` is installed but not discoverable
**Symptom:** Java database acceptance fails with `psql is required for database verification` even though Homebrew `libpq` is installed.

**Cause:** Homebrew installs keg-only `libpq` clients under `/opt/homebrew/opt/libpq/bin`, which may not be on `PATH`.

**Resolution:** Prepend `/opt/homebrew/opt/libpq/bin` to `PATH` for the acceptance process. The verifier carries the resulting `PATH` into its minimal child environment without forwarding unrelated host secrets.

## 46. The .NET VM is missing the unified modernization extension
**Symptom:** The P5 .NET modernization path requires the frozen GitHub Copilot modernization extension, but only the Java VM reports it as installed.

**Cause:** The extension retained its historical `vscjava.migrate-java-to-azure` identifier after adding supported .NET workflows, so stack-gated provisioning incorrectly treated it as Java-only.

**Resolution:** Install the exact locked, signed extension on both workshop VMs. Keep database cutover in `catalog-migrate`; extension assessment and transformation output remains evidence rather than proof of data migration.

## 47. PowerShell continues after a failed native command
**Symptom:** A failed Maven, acceptance, migration, or handoff command is followed by later steps that can produce success-shaped evidence.

**Cause:** `$ErrorActionPreference = 'Stop'` does not turn a native process's nonzero exit code into a terminating PowerShell error.

**Resolution:** Inspect `$LASTEXITCODE` immediately after every native command and throw before any dependent step. Wrap every `Push-Location` scope in `try/finally` so success, native failure, and protected-prompt failure all restore the caller's location.

## 48. Credential acquisition can preserve stale acceptance evidence
**Symptom:** Token acquisition or a protected credential prompt fails, but an older passing `acceptance-report.json` remains available to handoff validation.

**Cause:** The workflow removed the old report only immediately before invoking acceptance, after native tests and credential acquisition had already begun.

**Resolution:** Resolve the exact report path and remove it with fail-closed error handling before native tests, token requests, or prompts. Produce that path only from a successful current acceptance run, and inject native, token, prompt, and acceptance-process failures in executable documentation tests to prove stale evidence is absent.

## 49. Diagnostic-setting metrics are treated as dimension-preserving exports
**Symptom:** A revision-filtered Container App replica panel queries `AzureMetricsV2` but the declared `AllMetrics` diagnostic setting cannot produce the expected rows.

**Cause:** Azure Monitor diagnostic settings flatten multidimensional platform metrics and write the legacy `AzureMetrics` shape. `logAnalyticsDestinationType: Dedicated` changes eligible resource-log destinations; it does not preserve metric dimensions or move diagnostic-setting metrics to `AzureMetricsV2`. DCR metric export preserves dimensions, but Container Apps is not a supported DCR metric-export source.

**Resolution:** Keep the Container App `AllMetrics` diagnostic setting, query `AzureMetrics`, and remove the unsupported `Dimension["revisionName"]` filter. For `Replicas`, select the peak `Total` at the metric's `PT1M` grain; `Maximum` is only the largest contributing revision value, not the total across flattened revision values. Use Challenge 2's ARM and load observations as the authoritative revision-scoped scaling proof. Keep the Application Insights panels bound to `AppVersion`, the revision property, and `AppRoleInstance`; compute each instance's first request before filtering the cold-start proxy to the evidence window.

## 50. Success evidence can be relabeled to unrelated cloud resources
**Symptom:** Schema-valid load, smoke, or workbook evidence reports success even though the observed provider resource or endpoint is unrelated to the handoff.

**Cause:** A generic Azure resource-ID pattern, a single unconstrained smoke URL, or separately captured workbook query results prove only that some resource answered. Self-consistent declaration and observation fields do not establish provenance.

**Resolution:** Constrain Azure Load Testing IDs to `Microsoft.LoadTestService/loadTests`, derive the Container Apps label FQDN as `<APP_NAME>---<LABEL>.<ENVIRONMENT_SUFFIX>`, record separate exact `/healthz` and `/readyz` URLs, and bind every transition probe to the handoff endpoints. For workbooks, parse the captured ARM `serializedData` recursively, require valid Logs query execution context, and bind the observed `sourceId` to the handoff workspace.

## 51. A safe artifact directory can contain symlinked result files
**Symptom:** A repository-local runtime-results directory passes path containment while its discovered XML results resolve to external or stale files.

**Cause:** Checking only the declared directory and its parent components does not protect validators that later glob child files.

**Resolution:** Before a downstream validator recursively consumes any referenced directory, walk the complete tree without following links and reject every symlinked file or directory. Keep direct and nested report references under the same component-wise check and cover directory-child links with a negative test.

## 52. JSON booleans satisfy numeric evidence fields in Python
**Symptom:** `true` validates as one replica or one result row, or integer `1` validates as an enabled flag.

**Cause:** Python's `bool` subclasses `int`, and Pydantic's non-strict numeric and boolean parsing intentionally coerces compatible values.

**Resolution:** Use Pydantic `StrictInt`, `StrictFloat`, and `StrictBool` for normalized cloud observations. For raw workbook JSON, check that `queryType` is exactly an `int` before comparing it with zero. Keep explicit negative tests for both coercion directions.

## 53. Matching source-file hashes do not prove deployable workbook content
**Symptom:** An empty or unrelated checked-in workbook and KQL file validate because their reported hashes match, while separately reported deployed queries are correct.

**Cause:** Hash validation proves file identity but not that the file implements the frozen templates or produced the deployed panel set.

**Resolution:** Parse the checked-in workbook and require the exact frozen query-template map and Logs execution context; require `queries.kql` to equal one deterministic rendering of the same contract. Independently parse captured ARM `serializedData` and require the exact rendered query map and workspace source.

## 54. A downstream load contract renames an existing scale rule
**Symptom:** The challenge contract requires a scale rule that is not present in the handoff revision, so compliant evidence would require an unowned infrastructure change.

**Cause:** The consumer inferred a descriptive rule name instead of reading the authoritative P4 Bicep producer.

**Resolution:** Consume the existing `http` rule with min 1, max 3, and `concurrentRequests` 50. Add an executable cross-file assertion tying the registry and evidence example to `infra/modules/environment.bicep`; do not create a replacement revision.

## 55. A role assignment can claim a narrower scope than its resource ID
**Symptom:** An observed subscription-level role-assignment ID passes while its separate `scope` field claims the handoff ACR or Container App.

**Cause:** Validating role and scope as self-attested fields does not prove where Azure Resource Manager placed the assignment.

**Resolution:** Split every assignment ID at `/providers/Microsoft.Authorization/roleAssignments/` and require the preceding resource ID to equal the declared scope after resource-ID normalization. Continue matching the expected principal and exact least-privilege role.

## 56. Python JSON parsing accepts non-finite evidence values
**Symptom:** A metric or query result containing `NaN` or `Infinity` can reach numeric validation even though those constants are not valid JSON.

**Cause:** Python's default `json.load` accepts `NaN`, `Infinity`, and `-Infinity`, while unconstrained floating-point models can preserve them.

**Resolution:** Make every JSON load fail through `parse_constant`, configure normalized Pydantic models with `allow_inf_nan=False`, and retain negative metric-point and scalar-query tests for all three constants.

## 57. Strict outer JSON can hide permissive nested workbook JSON
**Symptom:** A valid observation file contains `serializedData` as a string, and that inner workbook document still accepts `Infinity`.

**Cause:** Strict parsing applies only to the outer file when nested JSON strings are decoded later with a separate permissive `json.loads`.

**Resolution:** Reuse the same rejecting `parse_constant` callback for every nested workbook decode and test a non-finite value inside `serializedData`.

## 58. A caller can substitute a permissive contract directory
**Symptom:** Evidence validates against alternate schemas or query templates supplied through the CLI.

**Cause:** Repository evidence paths are contained and symlink-audited, but the separately supplied contracts directory is only resolved.

**Resolution:** Require the exact checked-in `workshop/contracts` path derived from the running package, recursively reject symlinks in that tree, and pass only that validated path to handoff, schema, and query validation.

## 59. A filtered RBAC result can hide broader workflow access
**Symptom:** The expected ACR and Container App assignments validate even though the same principal also has Contributor or Owner at an ancestor scope, or the audit command fails before returning evidence.

**Cause:** A two-row normalized result does not prove that the Azure assignment query was complete. In addition, Azure CLI rejects `az role assignment list --all --scope ...`, and the deployment UAMI's two least-privilege roles do not include subscription-level `Microsoft.Authorization/roleAssignments/read`.

**Resolution:** Run the audit from a separate facilitator session with `Microsoft.Authorization/roleAssignments/read` (`Reader` is the minimum matching built-in role), select the handoff subscription, and execute `az role assignment list --all --include-inherited --assignee-object-id <principal-id> --fill-principal-name false --fill-role-definition-name false --output json` without `--scope`. Preserve each raw subscription-scoped `roleDefinitionId` ARM resource ID, normalize only its terminal GUID, and require the digest-bound raw and normalized forms to contain exactly the two expected resource-scoped assignments.

## 60. Workbook KQL can silently query a second workspace
**Symptom:** Exact frozen query text validates while a panel's `crossComponentResources` redirects execution to an unrelated workspace.

**Cause:** Query text and workbook `sourceId` validation do not constrain each panel's optional cross-component execution context.

**Resolution:** Recursively inspect every panel and allow `crossComponentResources` only when absent, empty, or exactly the handoff Log Analytics workspace.

## 61. Load duration can disagree with run timestamps
**Symptom:** Declaration and normalized observation agree on `durationSeconds`, but their `startedAt` and `completedAt` interval proves a different duration.

**Cause:** Comparing duplicated duration fields checks consistency, not the underlying timestamp evidence.

**Resolution:** Derive the interval from the observed start and completion timestamps and require it to equal the declared duration exactly.

## 62. Principal enumeration can target the wrong subscription
**Symptom:** An exhaustive assignment query for the workflow identity's subscription is paired with ACR and Container App assignments from a different subscription.

**Cause:** Each resource ID is valid independently, but the enumeration scope cannot contain assignments below another subscription.

**Resolution:** Derive the selected `subscriptionId` from the UAMI resource ID and require the ACR, Container App, and corresponding handoff resources to share it. Do not encode that subscription as `--scope` when `--all` is present.

## 63. GitHub job names and windows are replayable
**Symptom:** A later staging or production job reuses the expected name and timestamps while the evidence still appears bound to the original workflow attempt.

**Cause:** Job names and time windows are mutable metadata and do not identify GitHub's immutable job record.

**Resolution:** Record each numeric GitHub job ID in both the declared workflow evidence and normalized API observation, then bind ID, environment, name, and window together.

## 64. Cross-resource-group extension resources fail Bicep compilation
**Symptom:** A diagnostic setting targeting an existing resource in another resource group fails Bicep compilation with BCP139.

**Cause:** Extension resources must be deployed at the scope of the resource they extend. Declaring a cross-resource-group existing parent does not make an extension-resource deployment at the current scope valid.

**Resolution:** Deploy the observability Bicep at the handoff Container App's resource group, which the handoff validator already proves is shared by the Application Insights component and Log Analytics workspace. Declare those resources as same-scope `existing` resources and attach the diagnostic setting to the same-scope Container App rather than constructing a cross-scope extension resource.

## 65. Load evidence has no deterministic producer
**Symptom:** A guide can describe valid Azure Load Testing and metric output while leaving participants to hand-assemble normalized JSON that may not match the captured responses.

**Cause:** The schema and validator consume normalized observations but do not define how raw Azure responses become those observations.

**Resolution:** Capture the exact Load Testing run, Container App ARM response, replica metric, and database metric in a versioned manifest with path and SHA-256 bindings. Require the canonical capture, handoff, report, raw-response, and generated-observation paths; schema-validate the capture before rendering and the report before writing. Render through `catalog-render-load-evidence`, and have the common validator repeat the same pure transformation. Reject duplicate JSON keys, non-finite or missing values, path/symlink escapes, digest drift, and every input/output collision.

## 66. A delayed baseline metric point satisfies scale-out
**Symptom:** Recovery polling passes even though no point proves that replicas reached two or more while the load test was running.

**Cause:** A broad metric window or final maximum can mistake delayed ingestion after the run for in-load scale-out, while missing points may be treated as zero.

**Resolution:** Partition the revision-filtered `Replicas`/`Maximum`/`PT1M` series by the observed run timestamps. Require a one-replica point before load, a value from two through three during load, and a final one-replica point after load. Missing aggregation values fail instead of becoming zero.

## 67. Workflow head SHA is forced to equal application source SHA
**Symptom:** A checked-in handoff must name the commit that already contains that same handoff and workflow, creating an unsatisfiable self-reference.

**Cause:** The workflow control commit and application build source were modeled as one Git identity.

**Resolution:** Dispatch the stack workflow from a later control commit, hash and read `evidence/modernization-contract.json` there, then separately check out `handoff.source.commitSha` for build/test. During validation, read the handoff blob at `workflow.headSha` with `git cat-file` and require its SHA-256 to equal both the recorded digest and the current handoff file. Continue deriving the image tag and candidate revision suffix only from the handoff source commit.

## 68. Protected-job approval and rollback are modeled in the wrong order
**Symptom:** Evidence expects production approval after the production job starts, or promotion failure exits before rollback can run.

**Cause:** GitHub protected-environment approval gates job start, and rollback was installed only after the risky promotion path.

**Resolution:** Require staging completion, then approval, then production job start. Arm a simple shell trap before promotion, record its guard/promotion/rollback lifecycle, and validate digest-bound raw Container App revision lists for pre-promotion, promotion, and rollback so active, health, traffic, and image state cannot be hardcoded.

## 69. A corrected child still pins the previous shared registry version
**Symptom:** Cherry-picking an otherwise approved child onto a refrozen coordinator base leaves its focused test failing on the shared registry schema version.

**Cause:** The child correctly avoided editing coordinator-owned contracts but its owned consumer test still asserted the exact version from its earlier base.

**Resolution:** Recreate the child commit from the new exact coordinator base, import only its owned files, and update the owned consumer assertion to the new registry version while preserving the stream-specific contract version. Require one clean commit and rerun both the focused and full integrated acceptance gates before declaring the new base frozen.

---
**Planned Mitigations / Enhancements:**
- Add regeneration mode (`--repair-missing-images`) to attempt image creation for still-missing entries before pruning.
- Persist structured error diagnostics for image failures.
- Add lightweight tests to cover pruning and schema validation.
