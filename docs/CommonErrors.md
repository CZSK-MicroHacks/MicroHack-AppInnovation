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
**Symptom:** The pinned SqlPackage NuGet tool installs but cannot start on the .NET VM because its required .NET runtime is newer than the source VM runtime.

**Cause:** The global-tool package is framework-dependent; installing the locked .NET 8 SDK alone does not satisfy the newer tool runtime.

**Resolution:** Provision the exact self-contained Windows SqlPackage archive instead. Verify its SHA-256, verify the extracted executable's Authenticode publisher and version, and add that fixed directory to machine PATH.

## 41. Azure Files OAuth operations require backup intent
**Symptom:** Azure Files list, upload, or download fails despite login authentication and the privileged file-data role.

**Cause:** Azure CLI Files data-plane OAuth requires both `--auth-mode login` and `--backup-intent` for this role-backed migration path.

**Resolution:** Add both options to every Files list, upload, and download command. Do not add the Files-only option to Blob commands.

## 42. A fixed target VNet overlaps a participant source VNet
**Symptom:** Peering creation fails or private routes are ambiguous for the participant whose source VNet falls inside the target range.

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
**Symptom:** The Challenge 1 .NET modernization path requires the frozen GitHub Copilot modernization extension, but only the Java VM reports it as installed.

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

**Cause:** The consumer inferred a descriptive rule name instead of reading the authoritative Azure Bicep producer.

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

## 70. Repository-relative evidence arguments are written as working-directory paths
**Symptom:** A published shared-challenge renderer or validator command fails even when run from the documented `tests/acceptance` directory.

**Cause:** The command uses `../../evidence` while the CLI also prepends `--repository-root`, or a second CLI preserves lexical `..` components during containment checks. The two tools silently implement different path conventions.

**Resolution:** Freeze all shared-challenge CLI inputs as repository-root-relative (`evidence/...` and `workshop/contracts`) and resolve them exactly once against `--repository-root`. Keep `--repository-root ../..` as the only working-directory-relative argument. Execute the exact registry command strings from a synthetic `tests/acceptance` directory in acceptance tests.

## 71. A PostgreSQL database child is used as the server metric scope
**Symptom:** `az monitor metrics list` or raw normalization cannot obtain `cpu_percent` for the PostgreSQL resource ID from the modernization handoff.

**Cause:** The handoff identifies `Microsoft.DBforPostgreSQL/flexibleServers/databases`, while `cpu_percent` is exposed by the parent `Microsoft.DBforPostgreSQL/flexibleServers` resource.

**Resolution:** Preserve the database-child resource ID in the evidence subject, derive its exact flexible-server parent for the PostgreSQL metric capture and normalized observation, and validate that parent-child relationship. Azure SQL continues using its handoff database resource directly.

## 72. A malformed handoff bypasses the renderer's JSON error boundary
**Symptom:** `catalog-render-load-evidence` prints a Python traceback instead of one machine-readable failed result.

**Cause:** A required handoff field is indexed after partial validation omitted it, raising `KeyError`, while the CLI intentionally catches only operational and validation errors.

**Resolution:** Validate every handoff field before indexing it. In particular, require a nonempty `sliceId` alongside the nested source, application, database, and image fields, and retain a CLI regression that removes it and expects JSON failure.

## 73. One selected VM is mistaken for subscription-wide Defender coverage
**Symptom:** Defender for Servers P2 is enabled and evidence proves only the migration source VM, leaving the retained sibling workload outside the demonstrated challenge scope.

**Cause:** A selected handoff resource is not a complete inventory, and subscription pricing without `enforce: "True"` can still be overridden at descendant scopes.

**Resolution:** Require subscription-enforced `VirtualMachines` Standard/P2, derive both retained VM names from the selected source VM's participant suffix, and preserve digest-bound successful ARM responses for the .NET and Java VMs. Restore and verify the prior `enforce` value during cleanup.

## 74. Live Defender queries are used as deterministic workshop findings
**Symptom:** A correct workshop run fails because recommendations, Secure Score, MCSB, or image subassessments have not populated yet, or an empty response is presented as the expected learning example.

**Cause:** Defender findings are asynchronous and may legitimately be empty during the challenge window.

**Resolution:** Grade current live evidence on exact query attempt and provenance, with asynchronous results optional. Separately require a digest-bound pre-warmed snapshot captured earlier from distinct artifacts, with nonempty recommendation coverage, an unhealthy finding, Secure Score, MCSB control, and matching image subassessment.

## 75. A Defender operation and scope identify the wrong nested collection
**Symptom:** An empty image or compliance response passes provenance checks even though the request used another assessment key or regulatory standard.

**Cause:** The parent ACR or subscription, operation label, API version, and timestamp do not identify nested path parameters such as `assessmentName` or `regulatoryComplianceStandardName`.

**Resolution:** Preserve and validate the exact request `resourcePath`. Bind image records to the requested assessment collection and MCSB control IDs to the requested standard, for both current and pre-warmed evidence.

## 76. Equal timestamps impersonate later cleanup verification
**Symptom:** Cleanup completion, restored pricing, post-cleanup inventory, and cost evidence share a timestamp but are reported as an ordered restoration proof.

**Cause:** A less-than chronology check permits equality, which establishes no before/after relationship.

**Resolution:** Require cleanup completion strictly after paid-plan enablement, both restoration observations strictly after cleanup, and Cost Management verification strictly after both observations. Keep equality-boundary regressions for every transition.

## 77. Argparse failures escape a JSON CLI boundary
**Symptom:** A missing or unknown command argument prints argparse usage text and exits with `SystemExit(2)` instead of returning the documented machine-readable failure object.

**Cause:** `parse_args()` runs before the command's exception boundary and argparse handles errors by writing directly to stderr.

**Resolution:** Use an argument parser whose `error()` raises a validation exception, invoke it inside the command's JSON failure boundary, and test empty and malformed renderer and validator invocations.

## 78. Defender attack paths are modeled as a direct ARM GET
**Symptom:** An empty `Microsoft.Security/attackPaths` response is accepted even though no supported request produced it.

**Cause:** Defender for Cloud documents attack-path retrieval through Azure Resource Graph, not a direct Defender resource-list endpoint.

**Resolution:** POST one exact subscription-bound `securityresources` query to `Microsoft.ResourceGraph/resources`, preserve the complete raw request and response, reject truncation or pagination, and bind every returned attack-path ID, type, and subscription to the selected subscription. Include its query time in the pre-warmed/current evidence chronology.

## 79. One cleanup Resource Graph query claims unsupported resource types
**Symptom:** A cleanup inventory fixture contains Defender settings or monitoring associations that its declared ARG tables cannot return, so before/after equality can succeed on fabricated evidence.

**Cause:** Azure Resource Graph exposes VM and Arc extensions through `Resources`, DCR associations through `InsightResources`, Defender pricings through `SecurityResources`, and policy assignments through `PolicyResources`. Defender auto-provisioning and subscription settings require their dedicated ARM list APIs. Projecting only `properties` also hides policy-assignment identity or location changes.

**Resolution:** Use one exact four-table ARG producer for supported types plus bounded subscription ARM GET envelopes for `autoProvisioningSettings` and `settings`. Bind every endpoint, API version, subscription, response ID, timestamp, and pagination state. Preserve `identity` and `location` in the ARG projection and compare the complete normalized composite before and after cleanup.

## 80. Flattened role assignments are wrapped as native ARM evidence
**Symptom:** A Defender evidence bundle appears to contain `.value[].properties.principalId` and `.value[].properties.roleDefinitionId`, but those fields were synthesized around `az role assignment list` output rather than returned by the declared producer.

**Cause:** `az role assignment list` emits a flattened CLI-specific shape. Wrapping that array with `jq '{value: .}'` does not recreate the native `Microsoft.Authorization/roleAssignments` ARM response and can hide producer/consumer divergence.

**Resolution:** Capture the native list with `az rest` at `<acr-resource-id>/providers/Microsoft.Authorization/roleAssignments?api-version=2022-04-01&$filter=atScope() and assignedTo('<principal-id>')`. Preserve the raw `.value[].properties` objects, and require both the capture command and common renderer to reject a non-null `nextLink` before proving exactly one ACR-scoped AcrPull assignment for the workload principal.

## 81. Terraform tries to delete subscription-scoped Defender pricing
**Symptom:** Disabling the Defender foundation or destroying its Terraform state attempts to delete `Microsoft.Security/pricings` resources, fails, and can leave paid plans active while the operator assumes teardown completed.

**Cause:** The Defender pricing DELETE operation is valid only for supported resource scopes. Subscription pricing must be restored with an update, not deleted.

**Resolution:** Protect subscription pricing instances with `prevent_destroy`. Complete the authorized, evidence-validated pricing restoration first, then detach only `azapi_resource.defender_pricing` from Terraform state. The remaining reviewed plan may remove the workshop budget without issuing unsupported pricing DELETE requests.

## 82. Paid Defender plans can race ahead of a failed budget
**Symptom:** A Terraform apply accepts an RFC 3339 budget start timestamp that Azure rejects, while independent pricing resources can still enable paid Defender plans.

**Cause:** Azure requires a budget start date on the first day of a month and enforces additional service-side date constraints. Without a dependency, Terraform may create the budget and paid pricing concurrently.

**Resolution:** Validate the documented first-of-month midnight-UTC boundary and require the start month to be the current month through twelve months ahead at plan time. Make every paid pricing resource depend on successful budget creation so any remaining service-side failure stops before a paid plan change.

## 83. A reviewed rollback is mistaken for an investigated incident
**Symptom:** An SRE Agent report proves that a fixed rollback was reviewed and approved, but it can pass without establishing why the incident occurred or whether rollback is appropriate.

**Cause:** Approval chronology proves authorization, not diagnosis. A narrative hypothesis can also be fabricated unless it is derived from preserved producer responses.

**Resolution:** Capture complete Container App revision history, revision-bound request failures and exceptions, database dependency failures, and selected-database availability before the AgentResponse. Derive the hypothesis, rejected alternatives, blast radius, verification plan, and final assessment from those exact captures, and reject any mismatch.

## 84. Equal audit and investigation timestamps imply false causality
**Symptom:** Investigation evidence is reported as following the alert-bound agent snapshot even though the first capture has the same timestamp.

**Cause:** A non-strict chronology comparison establishes ordering only syntactically; equal timestamps do not prove the agent observed the incident before collecting diagnostic evidence.

**Resolution:** Require the first investigation observation to be strictly later than `IncidentActivitySnapshot`, and retain an equality-boundary regression that moves the snapshot to the first capture time.

## 85. Operational tags make a live agent differ from its evidence contract
**Symptom:** The SRE Agent deploys successfully, but its native ARM GET cannot pass the frozen foundation validator because it contains additional workload tags.

**Cause:** General resource tags were unioned into the agent even though its exact evidence shape permits only the hidden Application Insights link.

**Resolution:** Keep workload, participant, and challenge tags on the dedicated resource group, identity, workspace, and Application Insights component. Set the agent's tags to exactly its hidden Application Insights link, and test the agent resource block independently from the other tagged resources.

## 86. A documented audit query is never rendered
**Symptom:** A guide enables `set -u` and then aborts at `$PREFLIGHT_QUERY` or `$AGENT_AUDIT_QUERY`, so required audit evidence is never captured.

**Cause:** Prose says to render a registry query, but the executable block does not assign every input or replace every placeholder.

**Resolution:** Require the captured window, agent, and thread inputs explicitly. Render the exact registry template with all placeholders into a shell variable before `az rest`, and derive the dedicated agent Application Insights ID from the validated foundation artifact rather than discovery.

## 87. Azure Monitor alert ingestion conflicts with a no-subscription-role rule
**Symptom:** The SRE Agent foundation appears least-privilege compliant, but Azure Monitor alerts never reach its incident scanner.

**Cause:** Azure SRE Agent requires its managed identity to have Monitoring Contributor on the subscription for Azure Monitor alert ingestion, while the original plan prohibited every subscription-wide permission.

**Resolution:** Treat this as a blocking product decision rather than silently broadening access. The approved SRE Agent plan now permits exactly one UAMI Monitoring Contributor assignment for alert ingestion; all other reads remain participant-resource-group scoped and the only workload write remains the exact-Container-App rollback role.

## 88. Application Insights ARM queries use an unsupported API version
**Symptom:** Resource-centric KQL examples post to `Microsoft.Insights/components/<name>/query` but fail before returning telemetry.

**Cause:** The examples used a control-plane-era version that is not the version in the official resource-query Swagger.

**Resolution:** Freeze `2018-04-20` in the shared SRE Agent registry and render every application and agent Application Insights query endpoint from that value.

## 89. Container App revision listing uses unsupported `--ids`
**Symptom:** `az containerapp revision list` exits at argument parsing during seed or recovery capture.

**Cause:** That command requires `--name` and `--resource-group`; it has no `--ids` argument.

**Resolution:** Use the exact Container Apps ARM revisions list at `<container-app-id>/revisions?api-version=2025-01-01`, preserving its complete, non-paginated response.

## 90. Evidence validates shape without binding the intended parent or baseline
**Symptom:** Connectors under another agent, or a retained revision using the drill-invalid database host, can satisfy otherwise valid evidence.

**Cause:** Child resources and changed fields were checked independently without comparing them to the validated agent and handoff identities.

**Resolution:** Require each connector ID to be the expected child of the exact agent, and require the retained revision's `CATALOG_DATABASE_HOST` to equal the selected handoff database server before comparing the bounded drill differences.

## 91. Recovery and cleanup conclusions are self-asserted
**Symptom:** A report can claim HTTP 200 recovery or no post-deletion billing without deriving either result from captured producer output.

**Cause:** Recovery used hand-written URL/status/timestamp fields, while the cleanup flag was not compared with Cost Management rows.

**Resolution:** Capture machine-generated curl transfer JSON with redirects disabled and validate its exit code, status, effective URL, and timestamp envelope. Derive the billing flag from every Azure SRE Agent `UsageDate` row and reject positive usage on a UTC date after deletion.

## 92. Drill revision creation adds an unaccounted incident write
**Symptom:** The Activity Log validator permits only a facilitator traffic seed and approved rollback, but creating the bad revision during the incident necessarily emits a third Container App write.

**Cause:** Revision creation and traffic seeding were treated as one logical drill action even though Azure records them as separate resource writes.

**Resolution:** Create the same-digest drill revision at zero traffic before recording `incidentStart`. Capture its ARM creation time and require it to precede the incident. Keep exactly two in-window writes: facilitator traffic shift and correlation-bound UAMI rollback.

## 93. Revision traffic evidence uses a synthetic flattened shape
**Symptom:** A captured `az rest` revisions list cannot satisfy evidence fields such as top-level `trafficWeight`, or a hand-authored flattened object passes while hiding the real ARM response.

**Cause:** Container Apps returns traffic under `value[].properties.trafficWeight`; the consumer modeled CLI-like flattened revisions instead.

**Resolution:** Preserve an exact GET request plus native non-paginated response from `<container-app-id>/revisions?api-version=2025-01-01`. Bind every revision ID/type to the app, read nested `properties.active` and `properties.trafficWeight`, and reject flattened or paginated captures.

## 94. Cost evidence omits the request body or flattens the response
**Symptom:** Cleanup claims a meter and timeframe but cannot prove what Cost Management queried, or stores `columns` and `rows` at the top level even though the API returns them under `properties`.

**Cause:** The evidence contract represented query intent as descriptive fields instead of the native `2023-03-01` POST envelope.

**Resolution:** Preserve the exact custom `Usage` body with daily granularity, `UsageQuantity` sum, Meter grouping, and Azure SRE Agent Meter filter. Preserve native `properties.columns`, `properties.rows`, and `properties.nextLink`; reject pagination, map row values by returned column name, and derive post-deletion billing from those rows.

## 95. Exact-resource Container App write is mistaken for field-level RBAC
**Symptom:** A custom role is described as traffic-only even though it grants `Microsoft.App/containerApps/write`, which can update other mutable parent-resource properties.

**Cause:** Azure RBAC authorizes ARM actions at resource scope; it cannot restrict a write action to `properties.configuration.ingress.traffic`.

**Resolution:** State the authorization limitation explicitly. Scope the role to the exact Container App, require Review mode and facilitator inspection of the exact command, and compare native before/after state to reject every change except traffic. Do not claim the role itself is JSON-field-scoped.

## 96. Activity Log URL encoding differs between guide and validator
**Symptom:** Following the guide produces an Activity Log request with `%24filter`, encoded quotes, colons, and slashes, while the evidence validator requires a different URL representation.

**Cause:** Applying `jq @uri` to the entire filter encodes more than the frozen producer contract, including the parameter name when `%24filter` is used.

**Resolution:** Build one canonical relative URL with a literal `$filter`, encode only spaces as `%20`, use that same value for `az rest`, and preserve it unchanged in the request envelope.

## 97. Raw Container App snapshots omit evidence-envelope metadata
**Symptom:** Before/after rollback response JSON exists, but validation cannot establish when or how either snapshot was captured.

**Cause:** The guide wrote only the ARM response while the consumer requires `observedAt`, exact request method/URL, and response.

**Resolution:** Capture each raw response, immediately record UTC observation time, and wrap it with the exact GET request. Compare only the two envelope responses after removing ingress traffic; do not fabricate request or timestamp fields during later assembly.

## 98. Repository-root Markdown links pass on a website but fail locally
**Symptom:** A challenge link such as `/solutions/ch02/README.md` opens on one hosted site but resolves to the filesystem root during local validation.

**Cause:** A leading slash is URL-root-relative, not repository-relative.

**Resolution:** Use the correct file-relative path from the source document and run the repository-wide link gate across every active challenge, solution, facilitator, and component guide.

## 99. Documentation tests check words but not executable semantics
**Symptom:** Reconciliation tests stay green after a contract assignment, deallocation target, authentication claim, or chapter row is changed unsafely.

**Cause:** Presence-only assertions prove that a token exists somewhere, not that the operative command or table uses it correctly.

**Resolution:** Read the authoritative contract version, parse the exact fenced command, require the complete chapter/solution target map, assert positive mode-specific statements, and reject stale assets and alternate power-state producers across the whole active-guide surface.

## 100. A selected stack is not bound to its VM and source commit
**Symptom:** Challenge 0 can select .NET while naming the Java VM, or accept a healthy marker produced from an unapproved source commit.

**Cause:** Distinct VM names, valid counts, and a 40-character SHA shape do not prove stack identity or provenance.

**Resolution:** Derive `vm-dotnet-userNNN` and `vm-java-userNNN` from the validated `rg-userNNN` plus selected stack. Compare both smoke markers case-exactly with the same facilitator-provided full commit, carry that commit into the selection record, and revalidate it before the only deallocation command.

## 101. Maven finds a JRE, then containerized Testcontainers cannot find Docker
**Symptom:** Maven reports that no compiler is available on macOS; after moving the build into a JDK container, the PostgreSQL integration test reports no valid Docker environment.

**Cause:** The host resolves a legacy JRE without `javac`, and a test process inside a container cannot control Docker Desktop or reach sibling containers without the documented boundary. Underneath both: `workshop/toolchain.lock.json` gives a macOS host **no pinned way to acquire either language runtime**. All five of its installer keys — `runtimes.dotnet.windowsSourceSdkInstaller`, `runtimes.java.windowsSourceRuntimeInstaller`, and the three under `databases.*` — are Windows `x64`. The sharp part is not that they are uniformly Windows. It is that the lock provisions a **database** for this host and not a **runtime**: `databases.postgresql.localContainer.platforms` pins a `linux/arm64` digest, and the only `arm64` host the file declares is `hosts.coordinator` (macOS >= 13.0, Docker Desktop 4.37.1 / Engine 27.4.0 pinned to the patch version). An `arm64` image serves an `arm64` host, so the file contemplates this machine running the application's database — while offering it no way to build the application that would use it. So acquiring a JDK by hand off the VM is the **expected** path here, not a workaround for a defect — worth stating, because a reader who cannot tell which one they are doing also cannot tell whether to report it.

**Resolution:** Use the exact digest-pinned Microsoft OpenJDK build image. Mount Docker Desktop's VM `/var/run/docker.sock`, set `TESTCONTAINERS_DOCKER_SOCKET_OVERRIDE=/var/run/docker.sock` and `TESTCONTAINERS_HOST_OVERRIDE=host.docker.internal`, and mount the checkout at the same absolute path. Do not install an unpinned JDK or skip the integration test. Here "unpinned" means *not digest-pinned* and scopes the build image; it does not by itself settle whether a version-pinned host install is acceptable. If you cannot run the container build, see the non-TTY cask entry below, which pins the version explicitly.

## 102. Markdown backticks break a PowerShell checker regex
**Symptom:** A checker intended to parse fenced PowerShell blocks fails with `Missing ')' in method call` before reading any guide.

**Cause:** PowerShell treats backticks as escape characters inside an expandable double-quoted regex.

**Resolution:** Put the Markdown-fence regex in a literal single-quoted PowerShell string, where backticks are ordinary characters, then compile each extracted block with `[scriptblock]::Create`.

## 103. Stripping single-quoted spans with a regex misreads the `'\''` idiom
**Symptom:** A shell-variable checker reports `$principal` in `workshop/sre-agent/README.md` as unbound, when it is a jq `--arg` name inside a single-quoted program that bash never expands.

**Cause:** The extractor removed quoted spans with `'[^']*'`. That pattern cannot represent the close-escape-reopen idiom used to embed a literal quote inside a single-quoted string, so it terminates the span early and stays mis-aligned for the rest of the line, exposing quoted text as if it were shell.

**Resolution:** Scan for quote *state* rather than matching quoted *spans*. Walk the string tracking whether you are inside single quotes, and treat a backslash outside them as escaping the next character — which also removes the need for a hand-written exception for the correctly escaped `\$filter` OData parameter in `solutions/ch06-sre-agent/README.md`. Settle a suspected false positive by binding the name to a sentinel in a real shell and checking whether the sentinel reaches the output. Do not settle it by reading the line.

## 104. A guard's trigger encodes an assumption about which tool fails
**Symptom:** A guard passes for seven review rounds while instances of exactly the defect it describes ship in the repository.

**Cause:** Its trigger is narrower than its contract. Requiring the literal string `az deployment`, and then merely loosening that to any block running `az`, asserts that only the Azure CLI can be broken by an unbound variable. `ARM_SERIALIZED_DATA` in `solutions/ch04/README.md` is expanded in a block containing nothing but `jq`, `printf` and `shasum`; unbound, it hashes the empty string and prints a digest that can never match the workbook.

**Resolution:** State the contract in one sentence and scan everything it covers. If a trigger is genuinely required, name the condition that makes the defect possible, never the tool you expect to be running. Widening the threshold on a wrong trigger only makes the wrong question louder.

## 105. A placeholder detector only reports on spellings its character class admits
**Symptom:** A placeholder guard is described as the strictest check in the repository and reports nothing, while `<identityResourceId>` and `<path-to-ch00-selection.json>` sit unresolved inside its own declared scope.

**Cause:** The detector matched `<[a-z][a-z0-9-]*>` — no uppercase, dot, pipe, slash, underscore or space. It could only ever find placeholders written the way its author writes them. `solutions/ch00/README.md` carried two conventions on adjacent lines and the guard saw only the conforming one.

**Resolution:** Make the detector permissive and the acceptance rule strict: match any angle-bracketed token, then require that token to name who supplies the value. Verify the widening by planting each spelling you failed to anticipate — camelCase, dots, pipes, and whole English sentences in angle brackets — and confirming every one is now reported.

## 106. A non-recursive glob stops covering files as the tree grows
**Symptom:** A guard's coverage shrinks as a proportion of the repository without any test failing, and documents added later are never checked at all.

**Cause:** A non-recursive pattern such as `docs/*.md` matches only the top level, so anything under a new subdirectory is invisible to it. Any hand-maintained scope list has the same failure mode after a rename, and both fail silently because finding nothing looks identical to finding no defects.

**Resolution:** Derive scope from the version-control index with `git ls-files`, adding untracked-but-not-ignored files where the guard must also see work in progress, and assert a floor on how many files and blocks it actually found. A guard that silently scans less is indistinguishable from one that passes.

## 107. A validator step cannot be reached by mutating the field its name mentions
**Symptom:** Writing a defect-injection test for `golden-dryrun`'s `stack-match` step, the obvious mutation — editing `/source/stack` in the handoff — never reaches it. The run fails one step earlier, at `contract-fields`.

**Cause:** The stack is not an independent field. Changing it puts it in disagreement with `sliceId`, and the schema check ordered before `stack-match` catches that disagreement first. The step's name describes the two things it *compares*, not the defect that can actually arrive at it: `_step_stack_match` compares the contract's stack against the **bundle directory name**, so the only input that reaches it is an internally consistent contract filed in the wrong stack directory.

**Resolution:** When a step cannot be reached by the obvious mutation, that is information about ordering rather than evidence of a dead step. Find the input that does reach it and assert that the failure lands on *that* step and no earlier one — a defect-injection test that only checks for a non-zero exit proves nothing about which check caught it. If no reachable input exists, the step really is dead and should be removed rather than left as decoration.

## 108. Introducing a variable converts only the uses you edited, not the instruction that described them
**Symptom:** A documented command block that worked before a "safety" refactor now dies partway through. In `docs/Demo.md` step 4, binding `CICD=evidence/cicd-report.json` and switching two of the step's three `jq` blocks to `"$CICD"` left the third on the literal path: rehearsing with `CICD=workshop/contracts/cicd-evidence.example.json` resolves the first two blocks correctly and then exits `2` with `jq: error: Could not open file evidence/cicd-report.json`.

**Cause:** Before the change, every read was a literal path and one instruction — "substituted for the path above" — covered the whole step. Introducing the variable for *some* reads split the step into two substitution mechanisms while leaving one instruction that now describes half of it. The document still reads correctly to an author who knows which half they edited, and the surviving literal is the *original*, correct-looking value, so nothing looks wrong on the page.

**Resolution:** When you introduce a variable into a document, the unit of change is every use in its scope **plus every sentence that told the reader how to substitute the old form**. Convert all uses or none, then reword the instruction so exactly one substitution point exists. Verify by execution, setting only the variable and running the whole scope end to end — a partial conversion passes any check that reads the block you edited. This is the same class as a guard whose scope quietly stops covering the tree: the edit was right and its blast radius was one line wider.

## 109. A subtotal computed from unrounded values is correct and unreproducible at the same time
**Symptom:** A reader adds a column to check the work and it does not add. `docs/CostEstimate.md` claimed a `× 30` base subtotal of $2,017.23 where the five visible rows summed to $2,016.90 and 30 × the displayed $67.24 gave $2,017.20 — reconciling by neither route a reader has.

**Cause:** Computing totals from unrounded intermediates is right, and rounding line items to cents for display is right, but doing both silently removes the operand that connects them. The true derivation was 30 × $67.2409, and "67.2409" appeared nowhere on the page. A penny reads as rounding and is forgiven; a third of a dollar that reconciles by nothing reads as an error, and it spends the credibility that the exactly-right lines earned. The reviewer who found it had detected the same gap twice in earlier rounds and ruled it benign both times, because the test applied was "is the total correct?" rather than "can the person this is written for reproduce it from what they can see?".

**Resolution:** Do not re-derive the figures — the arithmetic is not what is wrong, and a numeric rewrite is a fresh chance to introduce drift. Publish the missing operand where the row already has a place for it, and state the convention once *with* the promise that anything wider than rounding shows its arithmetic in the row. A bare "totals are computed from unrounded values" disclaimer is worse than nothing: it converts an apparent slip into unverifiable-by-design. Then mechanise the rule, because the next drift will not be one anybody remembers to check by eye: assert that a claimed total sits within a cent per summed row of the rows a reader can see, or that the row explains itself. Any finding you are about to classify as a "display artifact" deserves the audience test, not the author test.

---
**Planned Mitigations / Enhancements:**
- Add regeneration mode (`--repair-missing-images`) to attempt image creation for still-missing entries before pruning.
- Persist structured error diagnostics for image failures.
- Add lightweight tests to cover pruning and schema validation.

## `AuthorizationFailed` on the first Challenge 1 deployment

**Symptom:** `az deployment ... create` fails immediately with
`AuthorizationFailed`, for every participant at once, before any resource is created.

**Cause:** The deployment was run at subscription scope. Participants hold Owner on their
own resource group only — the one the facilitator created at T-1 with their two legacy
VMs — and hold nothing at subscription scope.

**Fix:** Deploy into the resource group you already own:
`az deployment group create --resource-group <your-rg> --template-file infra\main.bicep ...`.
`infra/main.bicep` is resource-group-scoped and asserts that its `resourceGroupName`
parameter matches the group it is deployed into, so a parameter file pointing somewhere
else fails at compile time rather than deploying into the wrong place. Do not add
`--location`; a resource-group deployment inherits the group's location.

`infra/sre-agent.bicep` is the one template that is still subscription-scoped, because it
defines a custom role. It is facilitator-only and no participant runs it.

## Challenge 3's workflow cannot find the source it is told to build

**Symptom:** The catalog workflow fails at checkout or at `docker build`, reporting that
`handoff.source.commitSha` does not exist, or that
`application-source/<stack>/Dockerfile` is missing.

**Cause:** The workflow checks the application source out **from GitHub** at the commit
recorded in the handoff. Work that was committed only on the VM does not exist on GitHub,
and a local `git init` commit can never reproduce an upstream commit SHA.

**Fix:** Every Challenge 1 path must push its work to the participant's own GitHub
repository before Challenge 3, and record `git rev-parse HEAD` after the push as the
handoff's source commit. This applies to the manual path too — it authors a Dockerfile,
so it has work to publish. Keep `evidence/` tracked: the workflow reads `HANDOFF_FILE`
from the committed control commit, so gitignoring evidence breaks the same chain from the
other end.

## Re-provisioning a VM wipes a participant's commits

**Symptom:** A facilitator re-runs provisioning to repair one VM, and participants on
other VMs lose a morning of work.

**Cause:** `Install-SourceArchive` used to replace `C:\MicroHack\source` unconditionally.

**Fix:** Provisioning now returns early when the tree is already a Git repository at the
requested source commit, and the previous tree is preserved rather than deleted. If you
genuinely need a clean tree, move the existing one aside yourself so the loss is a
deliberate act rather than a side effect.

## `bash`, `curl`, `sha256sum`, or `jq` not recognized on the VM

**Symptom:** A documented command fails with "not recognized as the name of a cmdlet".

**Cause:** Provisioning used to add only `Git\cmd` to PATH, leaving the Unix tools that
ship with Git for Windows unreachable, and `jq` was not installed at all.

**Fix:** Both are provisioned now — `Git\usr\bin` is on the machine PATH and jq 1.7.1 is
pinned in `workshop/toolchain.lock.json`. If a VM predates this, re-provision it. Note
that jq ships unsigned upstream, so it is pinned by SHA-256 alone; do not "fix" the lock
by adding a `signaturePublisher`, because the binary has no certificate table to check
it against.

## The first `git status --porcelain` gate fails on a fresh .NET VM

**Symptom:** A .NET Copilot path reports a dirty worktree before the participant has
changed anything.

**Cause:** `global.json` is written into the source tree by provisioning, after the
baseline commit.

**Fix:** It is ignored in `.gitignore`. Do not commit it, and do not delete it — the
pinned SDK selection depends on it.

## `dotnet test` aborts with "You must install or update .NET to run this application"

**Symptom:** The .NET test run never starts. The host prints
`Framework: 'Microsoft.AspNetCore.App', version '8.0.0'`, lists only a newer framework as
found, and ends with `Test Run Aborted.`

**Cause:** The projects target `net8.0`, and running their tests needs the ASP.NET Core
**8** runtime specifically. An SDK of a later major can *build* them but cannot *run*
them. This bites when the SDK major and the target framework drift apart.

**Fix:** Install the runtime matching the target framework rather than a newer one. The
participant VM pins .NET SDK 8.0.424 for exactly this reason, and
`.github/workflows/catalog-dotnet.yml` now pins the same 8.0.424 instead of a later major.
It previously requested 10.0.400 and passed only because the hosted runner happened to
preinstall 8.0.424 as well — an undeclared dependency that would have broken every
participant's Challenge 3 pipeline the day that image dropped .NET 8.
`test_ci_builds_on_the_same_toolchain_the_vm_pins` now fails if the two ever diverge again.

## `PipeWriter 'ResponseBodyPipeWriter' does not implement PipeWriter.UnflushedBytes`

**Symptom:** Several `Contract.Health.*` and `Contract.Performance.*` tests fail with this
`InvalidOperationException` thrown from `System.Text.Json`. No assertion actually fails.

**Cause:** The `net8.0` test host was forced onto a newer runtime — for example with
`DOTNET_ROLL_FORWARD=LatestMajor` — so ASP.NET Core 8's `TestHost` is paired with a
`System.Text.Json` from a later major that requires an API it does not implement.

**Fix:** Do not force roll-forward to work around a missing runtime; install the ASP.NET
Core 8 runtime instead. The symptom is a version pairing artifact, not a defect in the
application: on the pinned runtime the same suite passes. Use it as a diagnostic — if you
see this exception, your runtime does not match `<TargetFramework>`.

## `Access is denied` reading `C:\protected\*.json` on the workshop VM

**Symptom.** In Challenge 1, `az deployment group create --parameters '@C:\protected\manual-dotnet-bootstrap.json'`
fails immediately with `Access is denied`, or `Get-Content` on the same path throws
`UnauthorizedAccessException` — even though `whoami /groups` shows the account in
`BUILTIN\Administrators`.

**Cause.** `C:\protected` is written with inheritance disabled and explicit ACEs. Being *a
member of* Administrators is not the same as *running elevated*: because the VM's admin
account is a custom one (`azureuser`, not the built-in RID-500 `Administrator` that Windows
Server exempts), UAC Admin Approval Mode gives an ordinary shell a filtered token whose
Administrators SID is deny-only. The ACL check fails before any Azure call is made, so the
error looks like an `az` or credentials problem and sends you to `az login`.

**Fix.** The provisioner grants the admin account Read on `C:\protected` and on each file it
writes there (`Set-ProtectedAcl -ReadPrincipal`). If you see this error the grant did not
land — most often because the VM was provisioned before that change, or `adminUsername` was
missing from the custom-data payload, which the provisioner rejects at startup. Re-provision,
or as a one-off unblock open PowerShell with **Run as administrator** and re-run the
deployment. Verify the fix the way a participant experiences it, from a *non-elevated*
prompt: `(Get-ChildItem C:\protected\*-<stack>-*.json).Count` must return `9`.

**Do not** work around this by relaxing `Set-ProtectedAcl` globally. `C:\MicroHack\secrets`
holds the database passwords and must stay administrators-only; an acceptance guard fails if
that call ever acquires a `-ReadPrincipal`.

## `pytest -q tests/test_contract_assets.py` fails on the rewrite path with two empty lists

**Symptom.** You are on Challenge 1 Path 1B. You have edited a Java or .NET source file, or
you have just authored the `Dockerfile` that checkpoint 4 asks for, and
`test_reference_tree_differs_from_legacy_only_where_the_workshop_teaches` fails. In the
Dockerfile case both diagnostic lines print `[]`, so the failure names nothing at all. The
test suggests adding your file to `MODERNIZATION_SURFACE`.

**Cause.** That guard protects *repository authoring* integrity, not your application. It
compares `java/` (or `dotnet/`) against `solutions/reference/…` and permits differences only
in the nine files the **modernization** path teaches — a set derived from a different path
than the one you are walking. On the rewrite path, 42 of 50 Java source files are outside
that set. Separately, the guard asserts that the reference tree's *added* files are exactly
its declared additions, and `Dockerfile` is one of them; creating your own `java/Dockerfile`
removes it from the difference and empties both sides of the comparison, which is why the
diagnostics are blank.

**Fix.** Run the file with that one test deselected, which is what both rewrite runbooks now
prescribe:

```bash
cd tests/acceptance
uv --no-config run pytest -q tests/test_contract_assets.py \
  --deselect tests/test_contract_assets.py::test_reference_tree_differs_from_legacy_only_where_the_workshop_teaches
cd ../..
```

**Do not** follow the test's own advice and edit `MODERNIZATION_SURFACE`. `tests/acceptance`
is a frozen interface for participants; changing the oracle to fit the code is the exact
move the challenge's review checklist exists to prevent. Everything else in the file is a
real gate and must stay green.

## Two macOS setup failures are already answered here — but not where a participant looks

**Symptom.** Off the provisioned VM the Java baseline stops twice: Maven reports that no
compiler is available, and `catalog_acceptance --profile full` aborts with `psql is required
for database verification`.

**Cause.** Both are already documented in this file — the JDK case as entry 101, the `psql`
case as entry 45. Neither is reachable *directly* from the material a participant is handed.
Every challenge README routes troubleshooting to `docs/Troubleshooting.md`
(`challenges/ch01-copilot-rewrite/README.md:300`), which contains no mention of `javac`, a
JDK, or a JRE, and no file under `challenges/` references this registry at all. One hop back
does exist — `docs/Troubleshooting.md:211` links here — but it is the last content line of
that file, it calls this registry "resolved implementation pitfalls" rather than answers to
errors you are about to hit, and the following sentence caveats the use it just enabled.

**Fix.** Follow the entries that already exist rather than inventing a route:

- **No compiler / legacy JRE — entry 101.** Build inside the digest-pinned Microsoft OpenJDK
  image with the documented Testcontainers socket overrides, and do not skip the integration
  test. Entry 101 also says *do not install an unpinned JDK*; that sentence sits in a
  container-build context, where "unpinned" means *not digest-pinned*, so read it as
  governing the build image. It does not by itself settle whether a version-pinned host
  install is acceptable. If you do install on the host, pin the version explicitly, and see
  the non-TTY cask entry below.
- **`psql` missing — entry 45.** Prepend `/opt/homebrew/opt/libpq/bin` to `PATH`.

The `psql` crash is safe to recover from: it happens before any write, and the corpus was
verified still at 198 figures afterwards. Re-run the profile from the start.

## `brew install --cask microsoft-openjdk@17` fails when you are not at an interactive terminal

**Symptom.** The cask aborts with a sudo/password error. Common in an agent session, a CI
step, or any non-TTY shell.

**Cause.** The cask runs a `.pkg` installer, which needs an interactive `sudo` prompt.

**Fix.** Use the tarball, which needs no elevation at all:

```bash
mkdir -p ~/.local/jdk && cd ~/.local/jdk
curl -sSL -o msjdk17.tar.gz \
  "https://aka.ms/download-jdk/microsoft-jdk-17.0.20-macos-aarch64.tar.gz"
tar xzf msjdk17.tar.gz
export JAVA_HOME=~/.local/jdk/jdk-17.0.20+8/Contents/Home
```

This is the host-install route. Prefer entry 101's container build; if you take this route,
note the tarball URL pins 17.0.20 explicitly, which is what "pinned" means for a host install.

**Do not add a third entry for either symptom.** Both were re-derived from scratch during the
rewrite walkthrough and written up here as new findings, because the walkthrough searched the
runbook it was executing and never searched this registry. Search this file before adding to
it. The duplicate JDK entry was first removed on the grounds that it *contradicted* entry
101; on review that was an overreach — entry 101's prohibition is scoped to the build image,
so the host-install route above is a legitimate companion to it, not a competitor. Two
entries answering adjacent symptoms are fine so long as each says which case it is for.

## Do not infer a document's silence from a filtered search

**Symptom.** You conclude "the material never documents X", having established it with a
targeted `grep`.

**What actually happens.** The pattern you searched for often *cannot* match the text that
would refute you. Searching `java/README.md` for `CATALOG_` returns only `CATALOG_*` rows —
so it can never reveal the `OTEL_*`, `DEPLOYMENT_ENVIRONMENT` and `CONTAINER_APP_REVISION`
rows sitting four lines further down the same table. The output looks like evidence about
the document; it is evidence about the filter.

**Rule.** A claim of the form *"the material is silent on X"* may not rest on a grep. Back it
with a full read of the named file, or an exhaustive diff of code against documentation:

```bash
# every env var the code reads, versus every env var the README tabulates
python3 - <<'PY'
import re
code = set(re.findall(r'"([A-Z][A-Z0-9_]{3,})"', open('java/src/main/java/com/microsoft/microhack/catalog/config/CatalogRuntimeOptions.java').read()))
code |= set(re.findall(r'\$\{([A-Z][A-Z0-9_]{3,})', open('java/src/main/resources/application.properties').read()))
doc  = set(re.findall(r'\|\s*`([A-Z][A-Z0-9_]{3,})`\s*\|', open('java/README.md').read()))
print("in code, undocumented:", sorted(code - doc) or "none")
PY
```

Run against the baseline this reports `none` — the table is exactly complete, 15 for 15.

**Why it is worth a rule.** Silence claims are unfalsifiable from inside the search that
produced them, so they survive review that a positive claim would not. The generalized form
of the mistake is verifying your own query instead of the artifact.

**The harder variant: a well-formed filter answering the wrong question.** The rule above
catches a filter that *could not* have matched the counter-evidence. It does not catch a
filter that would have worked perfectly — for a question you did not ask. Searching
`docs/Troubleshooting.md` for `javac|JDK|JRE` returns zero, and that is a correct answer to
*does this file discuss JDKs*. It was then used to support *therefore it does not link the
error registry* — a different claim, refuted by one hit for `CommonErrors` in that same file
(`docs/Troubleshooting.md:211`). Nothing was wrong with the query; the question was
substituted underneath it.

> **Search for the thing being denied, not for the subject matter around it.**

Write the denied proposition down first, then write the query that would return its
counter-example. If your claim is *no handoff instance declares a rewrite path*, the query
is `"path"\s*:\s*"[^"]*rewrite` over **every** file — not a filename glob for `*handoff*`,
which cannot see an instance that is named something else. Run against the baseline that
search returns only `workshop/contracts/challenge-paths.json`, and the sharper true statement
falls out of it: seven JSON files *enumerate* `copilot-rewrite` as a legal value and none is
an instance of one.

A corollary, learned by making the mistake: **counting a filter's hits is not reading them.**
A three-term search that returns 1, 7 and 2 has not been read until all ten rows have been.

**A second corollary, and the one that has actually bitten: a non-zero exit is not a zero
result.** A silence claim must distinguish *the query ran and matched nothing* from *the query
never ran*. Both print no rows, and a shell construct will happily convert the second into a
confident negative. Two mechanisms, both observed on this repo while verifying the rule above:

```bash
# A. flag conflict swallowed by a pipe: -l and -n are incompatible in git grep
git grep -lin 'copilot-rewrite' 4bf59f7 | wc -l     # prints 0; git exited 129

# B. the same broken query behind a || fallback
git grep -lin 'copilot-rewrite' 4bf59f7 || echo "no matches"   # prints "no matches"

git grep -li  'copilot-rewrite' 4bf59f7 | wc -l     # 28. the true answer, exit 0
```

The discriminator is the exit code, and for `git grep` it separates a broken *invocation*
from a real negative:

| exit | meaning | rows printed |
| --- | --- | --- |
| `0` | ran, found matches | some |
| `1` | matched nothing — **or the pathspec matched no file at all** | none |
| `129` | usage error, **never searched** | none |

**The `1` row is not safe on its own, and this is the one case exit codes cannot rescue.**
Scope a search to a path that does not exist and `git grep` reports **exit 1, silently** —
byte-identical to a genuine negative, no error on stdout or stderr:

```bash
git grep -li 'handoff' 4bf59f7 -- 'workshop/catalog_migrate/handoff.py'   # exit 1, no output
git grep -li 'handoff' 4bf59f7 -- 'tests/acceptance/catalog_migrate/handoff.py'  # exit 0, a hit
```

The first path does not exist at that commit; the second is the real one. Neither
`set -o pipefail` nor `${PIPESTATUS[0]}` helps here, because the exit status is *genuinely*
`1` — the query ran, over nothing. **So assert the file exists before claiming it is silent:**

```bash
path='tests/acceptance/catalog_migrate/handoff.py'
git cat-file -e "4bf59f7:$path" 2>/dev/null || { echo "no such file at that rev: $path"; exit 1; }
```

Plain `grep` is kinder — a missing file exits `2` and says so — but only until a pipeline
swallows stderr, at which point it prints `0` and exits `0` like everything else.

So never let a bare pipe or `||` stand between a silence claim and its query.

**And surfacing an exit code is worthless unless it is the exit code of the command whose
silence you are claiming.** Both `$?` and `||` bind to the **last stage of a pipeline**, so
they are safe only when the query *is* the last stage. Interpose `| wc -l`, `| sed`, `| head`
and each silently reports on the wrong command — in opposite directions:

```bash
git grep -li 'zzz-nothing' HEAD | sed 's/^/hit: /'; echo $?   # 0 — sed's success, not the miss
git grep -lin 'copilot-rewrite' HEAD | wc -l; echo $?         # 0 — though git grep exited 129
git grep -lin 'copilot-rewrite' HEAD | wc -l || echo 'none'   # fallback never fires at all

set -o pipefail; git grep -lin … | wc -l; echo $?             # 129 — correct
git grep -lin … | wc -l; echo "${PIPESTATUS[0]}"              # 129 — correct
```

Note the two failures are inverses. **Without** a pipe, a broken query makes `||` fire and you
publish a false *negative*. **With** a pipe, the same broken query stops `||` firing at all and
you publish a false *positive* — the query looks like it succeeded. Same construct, opposite
guarantee, decided by whether a pipe is present.

Use `set -o pipefail`, or read `${PIPESTATUS[0]}`, or put nothing after the query at all. A
bare `cmd || echo` is genuinely safe — `||` binds to `cmd` when there is no pipeline — which
is why the safe and unsafe forms look nearly identical on the page.

Mechanism A and mechanism B are different bugs that produce a byte-identical artifact, and in
every recorded instance the claim they would have supported was not merely unproven but **the
exact opposite of the truth** — zero versus 28, or a document said to be silent that is not.

### Mechanism D — the right query, at the wrong commit

Every remedy above checks that the query *ran* and that the file *exists*. None of them checks
**which version of the file was searched**, and that is a separate way to publish a confident
inversion.

Two sub-cases, both verified here:

**Rev-skew.** A claim is made against one commit and checked against another. `docs/CommonErrors.md`
is silent on `PIPESTATUS` at the workshop baseline `4bf59f7` and discusses it at this file's later
revisions — same path, same query, opposite answers, and `git cat-file -e` passes at both because
the file exists in each:

```bash
git grep -c 'PIPESTATUS' 4bf59f7 -- docs/CommonErrors.md   # no output — silent here
git grep -c 'PIPESTATUS' HEAD    -- docs/CommonErrors.md   # matches — not silent here
```

No hit count is quoted above on purpose: this entry keeps changing that number, so a count written
here would be stale by the commit that records it. **That is the mechanism, operating on the
sentence describing it.**

Checking a report's claim at your own tip is the common form. A finding filed at `d5325e8` and
adjudicated at `9c14770` — **38 commits later** — reads as false when it was true when written.

**Tree-vs-commit.** Omit the rev and `git grep` searches the **working tree** — including
uncommitted edits — which is not any commit at all, and therefore not an object a reader can
reproduce your result from:

```bash
git grep -c 'some-token' -- docs/CommonErrors.md        # working tree, uncommitted edits included
git grep -c 'some-token' HEAD -- docs/CommonErrors.md   # the commit; can differ from the line above
```

The rule this yields is about adjudication, not shell:

> **A claim about a commit can only be checked at that commit.** State the rev in the claim,
> name it in the query, and when testing someone else's claim use *their* rev, not your tip.

Absence of a rev in a `git grep` is therefore not a neutral default. It silently selects the one
object that no one else can see.

**Corollary — when two parties quote the same file differently, diff the revs before diffing the
quote.** The rule above tells you to use the other party's rev. It does not tell you what to do at
the moment the disagreement appears, and the tempting move is to explain the *difference in the
text* — they abbreviated, they truncated, they quoted selectively. Every one of those explanations
is about the reader. The cheapest one is about the file.

Measured here, on `workshop/observability/queries.kql`, where one party read four query predicates
ending at `== "__REVISION_NAME__"` and the other read the same four with `or AppRoleInstance
startswith "__REVISION_NAME__"` appended:

```bash
for rev in 4bf59f7 HEAD origin/rewrite-integration; do
  n=$(git grep -c 'AppRoleInstance startswith' "$rev" -- workshop/observability/queries.kql \
      | awk -F: '{s+=$NF} END{print s+0}')
  c=$(git grep -c 'query-id' "$rev" -- workshop/observability/queries.kql \
      | awk -F: '{s+=$NF} END{print s+0}')
  echo "$rev  fallback=$n  control=$c"
done
```

`4bf59f7` and `HEAD` report `fallback=0`; `origin/rewrite-integration` reports `4`. The control
returns 5 at all three, so the zeros are genuine absences and not a query that never worked. The
clause was added by a later commit. **Neither party misquoted anything.** Only the second count
depends on a moving ref, so re-measure rather than trusting the number written here — the immutable
one is `4bf59f7`, which is the base every reader starts from.

> Before explaining why someone quoted an artifact differently, check whether they were reading a
> different artifact. One command settles it, and it comes first because "you truncated" is an
> accusation while "our revs differ" is a fact.

This matters most in the direction that feels safest. Finding *more* text at your own tip and
concluding the other party cut it is the same inversion as finding *less* and concluding they
invented it — the extra text is evidence about your rev, not about their honesty.

It also changes the disposition of the underlying claim. A claim true at the base and false at the
tip is **superseded, not refuted**, and those are different facts about a deliverable: one says the
report was wrong, the other says the tree moved. Only the second tells a reader starting from the
base what they will actually see.

### Mechanism E — the substrate cannot tell you a finding was closed

Mechanism D asks *which version did you search*. This one asks *which artifact carries the
fix*, and it survives doing D perfectly.

**A finding is closed by its remedy, not by its symptom's substrate.** When the remedy is a
document, a reclassification, or a procedure, the code the symptom lives in is **byte-identical
whether or not the finding was fixed**. Re-reading it returns a confident answer that carries no
information.

Worked instance, from this arm's own ledger. A blocking finding said: checkpoint 4 has the
participant author `<stack>/Dockerfile`, `MODERNIZATION_ADDITIONS` already names `Dockerfile`,
so the equality in the reference-tree guard breaks. Verified by reading the constant. Recorded
as open.

The constant is identical at this branch and at `origin/rewrite-integration`. The finding is
nonetheless **fixed** there, by `ff70fac`, which changed neither:

- it **reclassifies** the guard as repository-authoring rather than a participant gate —
  a participant who does the homework puts the name on both sides, so nothing is undeclared;
- it **requires** both rewrite runbooks to `--deselect` it, enforced by a new test, while the
  modernization runbooks keep running it in full.

Re-reading the constant reports "unchanged, still open" in both worlds. **Note the direction:
the common warning is against a finding recorded as fixed that isn't. This is the mirror — a
finding recorded as open that was closed — and the mechanism is the same, because closure was
never a property of the substrate.**

So: **check the remedy, not the symptom.** If you cannot name what the fix would change, you
cannot verify the finding's status by reading anything.

**Corollary — the corpus you can list is not the corpus that runs.** Sweeping every tracked
`.json` in a tree for prose-in-a-JSON found 138 files, 0 defective, which looks like proof the
class is extinct. It is not: the artifact that actually carried that defect was a *generated*
bundle, assembled at test time and invisible to `git ls-files`. The sweep was clean because it
could not see the thing it was looking for. Confirming the class was remediated meant reading
the **generator** — which writes prose only into `.md` members and real JSON into `.json` ones —
not the tree it never writes to.

This mechanism is also the first in the family that **propagates**. A–D produce a wrong answer
in one terminal. E produces a wrong *status*, which is then published, cited, and built upon.

It is also, by the criterion below, **unmechanisable**: the defect class is "clause still
present", and every clause in a codebase is a legitimate instance. There is no corpus to scope
and no exemption list to write, because the check requires knowing what the remedy was — which
lives in the ledger, not in the tree.

### When to mechanise this rule instead of documenting it

Four rounds of this entry were caught by a person noticing at the right moment. The fifth was
caught by `test_every_bash_block_binds_every_variable_it_expands`, which failed an unbound
`$path` in the remedy directly above. **A test needs nobody to be paying attention**, so the
obvious conclusion is to mechanise the rest of the rule too.

That was measured over this repo's markdown corpus and **it does not work**, which is worth
recording so nobody spends the afternoon again. After discarding the extractor's own
artifacts — `VAR=value` assignments read as paths, and links that resolve relative to their
own document rather than the repo root — **573** path citations remain, **239** of them
unresolvable. They partition cleanly, and the partition is the point:

- **participant outputs** (`evidence/…`) — **219** — absent *by design* until a run;
- **historical changelog entries** in `docs/ImplementationLog.md` — **18** — describing a
  tree shape that has since been restructured; accurate when written, not defects now;
- **generated directories** — **1** — `data_seed/`, the data generator's default `OUTPUT_DIR`;
- **imprecise but resolvable** — **1** — `docs/Facilitator.md:917` cites
  `modules/environment.bicep`; the file is at `infra/modules/environment.bicep` and the same
  sentence names `infra/main.bicep` two lines above, so a reader resolves it. Cosmetic.

Genuine broken references: **zero**. **238 of 239 are correct documentation** and the last is
a shortened prefix in a sentence that supplies the prefix.

The difference is not that one rule is more important. **An unbound variable has no
legitimate instances in a shell script, so any occurrence is a defect. A path that does not
exist has many legitimate instances in documentation, so occurrence proves nothing.** That is
the criterion:

> A verification rule can be mechanised when its defect class has **no legitimate instances**
> in the corpus it guards. Otherwise a guard is only an exemption list, and the exemptions are
> where the real defects will hide.

Documenting the rule is not the weaker option here; it is the only correct one, because the
judgement the rule needs — *is this path absent because it is wrong, or because it has not
been produced yet?* — is exactly what a guard cannot make.

## A test that cannot skip will fail instead, and where the hook runs decides which

`PostgreSqlIntegrationTest` is `@Testcontainers` with a `@Container` field. The workshop VM
has no Docker daemon by design and the prescribed verification command is a bare `mvnw test`,
so the class errored on the mandated path. Reproduced here by redirecting the JVM's home so
the socket disappears — note that `HOME=… ` is *not* enough, because Testcontainers resolves
`~/.docker/run/docker.sock` from the `user.home` system property, not the environment
variable, and the run passes while looking like it was isolated:

```bash
# looks isolated, is not: falls back to the socket and passes
env HOME=/tmp/nohome DOCKER_HOST=tcp://127.0.0.1:1 ./mvnw -Dtest=PostgreSqlIntegrationTest test

# genuinely without Docker
DOCKER_HOST=tcp://127.0.0.1:1 ./mvnw -DargLine="-Duser.home=/tmp/nohome" \
  -Dtest=PostgreSqlIntegrationTest test
```

The obvious remedy — asserting Docker availability inside the class — does not work, and the
reason generalises past Testcontainers. `TestcontainersExtension` implements **both**
`BeforeAllCallback` and `ExecutionCondition`. JUnit evaluates conditions first and runs
`BeforeAllCallback` second, and the container is started from the callback. An
`assumeTrue(...)` in a `@BeforeAll` body is therefore ordered *after* the failure it is meant
to avoid: the container start has already thrown, and the run errors rather than skipping.
The working form is the condition-time flag, `@Testcontainers(disabledWithoutDocker = true)`.

Measured, same tree, one flag apart:

| | without Docker | with Docker |
| --- | --- | --- |
| `@Testcontainers` | `tests=1 errors=1`, BUILD FAILURE | 34 run, 0 skipped |
| `@Testcontainers(disabledWithoutDocker = true)` | 6 skipped, BUILD SUCCESS | 34 run, 0 skipped |

**The general rule: a guard only guards if it runs before the thing it guards against.** A
remedy placed after the failing step is not a weaker fix, it is not a fix — it never
executes. Before writing a skip, find out which lifecycle phase starts the resource and put
the guard in an earlier one.

The corollary for reporting: publish the skip count with the pass count. `34 run / 0 skipped`
and `28 run / 6 skipped` are both green, and only the pair tells a reader which environment
produced them. A bare pass count cannot distinguish a skipped suite from a complete one.

## Accepting the better duplicate can leave zero copies on the branch that ships

Two people fix the same defect independently. One compares the two, finds the other's version
better, and drops their own as redundant. That is the right call on the merits and it can
still end with **no fix anywhere that matters**, because the surviving copy is on a different
branch from the discarded one. Each party believes the defect is closed; the integration
branch has neither fix.

It happened here. Both parties reached `@Testcontainers(disabledWithoutDocker = true)`
independently. The duplicate was dropped as redundant, and the survivor sits on a topic
branch:

```bash
# the fix, at the branch that would ship
git grep -n "disabledWithoutDocker" origin/rewrite-integration \
  || echo ">>> absent (exit $?)"

# positive control: the same query, same shape, where it does exist
git grep -c "disabledWithoutDocker" origin/michalmar-ch01-java-rewrite-walkthrough
```

The first prints `absent (exit 1)`; the second returns three files. **Run the control.** A bare
`exit 1` cannot distinguish "not there" from "query never worked", and this is a silence claim
about the state of a deliverable — the most expensive kind to get wrong. Check the files exist
at that rev too, with `git cat-file -e "<rev>:<path>"`, or a moved file reads as a missing fix.

**The rule: a supersession is not complete until the surviving copy is on the branch the
discarded one was on.** "Yours is better, I'm dropping mine" is a statement about two patches;
shipping is a statement about one branch. Before dropping a duplicate fix, verify the
replacement is reachable from the ref that ships — and if it is not, the correct order is
land first, drop second.

This is the mirror of the substrate mechanism above: there, a finding recorded as open was
already fixed; here, a finding recorded as fixed is live everywhere it counts.

## The same attribute name under two signal types, at the lines you correctly cited

Every other inversion in this file comes from reading the **wrong** artifact: the wrong rev, the
wrong branch, a filter that could not have returned the counter-evidence. This one comes from
reading the **right** artifact — the right file, at the right lines — incompletely. No substrate
check catches it, because the substrate was never in question.

The claim was that `db.system.name` is emitted equivalently on both tracks, cited to
`solutions/reference/dotnet/src/LegoCatalog.App/Services/CatalogTelemetry.cs:67` and `:113`. Both
line numbers are correct. Both lines contain the string. The conclusion is still wrong, because
the string is all that was read:

```bash
F=solutions/reference/dotnet/src/LegoCatalog.App/Services/CatalogTelemetry.cs
git grep -n 'db\.system\.name' HEAD -- "$F"          # :67 and :113 — the name is there

git grep -n -E '\.(SetTag|AddTag)\(' HEAD -- "$F" \
  || echo ">>> no span attribute set in this file (exit $?)"

# positive control: the same API, same tree, where it does exist
git grep -c -E '\.(SetTag|AddTag)\(' HEAD -- solutions/reference/dotnet
```

The second command exits 1; the control returns 11 across three sibling services, so the absence
is real. Reading what encloses each line settles it — `:67` is a `KeyValuePair` argument to
`_databaseDuration.Record(...)`, a **metric tag**; `:113` is a key in the dictionary passed to
`logger.BeginScope(...)`, a **log scope**. On the Java track the same name reaches
`span.setAttribute` on a `CLIENT` span. Same identifier, three signal types, one of which is a
span attribute and two of which are not.

**Telemetry attribute names are deliberately identical across signals** — that is what a semantic
convention is for. So the name is the one part of the line that cannot tell you which signal
carries it, and grepping for it returns a hit of exactly equal confidence in all three cases.

> An identifier is not an emission. Grep locates the name; only the **call it is passed to** says
> which signal it lands on, and therefore which table can ever be queried for it.

The consequence is a query that is unsatisfiable rather than merely empty. A dashboard reading
`AppDependencies` for an attribute emitted as a metric tag returns no rows in every window, and
when the panel ends in `| where value > 0` that renders as a healthy window with nothing wrong —
the same silent-green shape as a filter that never matched. Empty because nothing happened and
empty because nothing could are indistinguishable at the panel.

The general form is the one this audit hit most often, in its most literal instance: **a claim of
the form "X is the same as Y" has two operands, and here both were opened, to the correct lines,
and only one attribute of each was compared.** "Check the substrate" does not catch this. The
check that does is naming, before concluding, which property of each operand the claim actually
depends on — here the API, not the name — and confirming that property was the one read.

For the case where the two operands are the **same line number in two different files**, see
*A line number is not an address when the file has two homes* below.

## A line number is not an address when the file has two homes

The entry above is about reading the right file incompletely. This one is about reading a file
that was never the one under discussion — while every check you run says it was.

Two parties disagreed over where `AddSqlClientInstrumentation()` sits in `Program.cs`. One said
`:86`, the other `:107`. **Both were right**, because the application exists in two trees:

```bash
# before re-reading a disputed line, ask how many homes the file has
git ls-tree -r --name-only HEAD | grep '/Program\.cs$'

# dotnet/src/LegoCatalog.App/Program.cs                    117 lines
# solutions/reference/dotnet/src/LegoCatalog.App/Program.cs 148 lines
```

`:86` is `.AddSqlClientInstrumentation()` in the first and `.AddAspNetCoreInstrumentation()` in
the second. **Both are real OpenTelemetry registrations of the same family.** So each party
opened a file, found instrumentation at the cited line, and confirmed. Re-reading either copy
more carefully never surfaces the problem, because neither copy is wrong.

The population is large and mostly benign, which is what makes the exceptions hard to see:
**81 tracked sources under `solutions/reference/`, 75 with a path-identical twin, 64 of those
byte-identical, 11 drifted.** For the 64 a line number resolves the same either way. The whole
hazard is the 11 — and one of them, `TomcatPathConfiguration.java`, **drifts at an identical
line count**, so even a length sanity-check matches. Its single differing line is an `import`.

> A line number is an address only when the basename is unique. Here it is a **relative** offset
> into whichever of two files you happened to open, and both resolve.

Two properties make this worse than an ordinary ambiguity. First, it is **silent** — there is no
failed lookup, no exit 1, no empty result to notice. Second, the drift is not cosmetic: the
reference tree is a **Spring Boot major version ahead** (`4.0.7`/`release 21` against
`3.5.16`/`release 17`), so the differing lines are package relocations. A claim verified in one
tree can be false in the other while every quoted identifier still matches.

The guard is one command, run **before** re-reading anything:

```bash
# the question is not "what is at line N" but "how many files could line N be in"
git ls-tree -r --name-only HEAD | grep '/CatalogRuntimeOptions\.java$'
```

If the basename has two homes, the disagreement is about **addressing**, not content, and no
amount of re-reading either operand will resolve it. Cite the tree with the line, always.

Two counting notes, recorded together so neither is later quoted against the other. The `11`
above is *both stacks, tracked sources only*; a Java-tree-only, all-file-types comparison gives
`diff -rq java solutions/reference/java` → **9 differing files**, which is the number the Java
runbook states and it is exact. Same state, two populations — the same trap one level up, so
**re-run both counts at one revision before attributing a disagreement to either party.**

A third note, because the absolute figures and the finding have different lifetimes. Line-count
pairs are **rev-sensitive**: `PostgreSqlIntegrationTest.java` is `340/342` at the workshop
baseline and `345/347` once the `disabledWithoutDocker` fix lands, because that commit adds five
lines to *each* tree. The drift **delta** is `+2` at both revisions. So:

> When the claim is about drift, quote the **delta**, which survives edits to both copies. Quote
> an absolute pair only alongside the revision that produced it. A pair quoted bare will read as
> a discrepancy to the next person, who is measuring somewhere else.

The author of this entry had already committed two instances of the defect into the document
describing it: two adjacent bullets citing `CatalogApplication.java:33` in one tree and
`Program.cs:80` in the other. Naming the hazard did not confer immunity from it; the mechanical
sweep above is what found them. Independently and in the same hour, the party who authored the
corresponding finding ran the sweep against their own report and found **19** unprefixed
citations in it. **Two parties, each holding a freshly-written description of the trap, both
still in it.** Awareness was not merely insufficient — it was maximal and simultaneous, and only
the mechanical check found either set.

### How wide should the guard be

The obvious next move is to narrow it. Of 95 ambiguous basenames in the tree, 15 were cited; of
those, 4 sit on pairs that actually differ and 11 resolve to identical bytes either way. So the
narrow trigger is *ambiguous **and** drifted*, and it fires 4 times instead of 15. The argument
for narrowing is alert fatigue: 11 alerts that need dismissing by hand is the reliable way to get
a reviewer to stop running the check.

**That cost model is imported from a different kind of guard and does not transfer here.** It
holds when the remedy is an investigation, because dismissing a false positive costs a human
decision. This guard's remedy is a mechanical edit — prepend the tree to the citation — which is
correct whether or not the pair currently differs, needs no judgement, and cannot be wrong. Eleven
harmless prefixes is not eleven investigations. Breadth is nearly free exactly when the fix is.

**Narrowing also carries an unstated precondition: that the check is re-run.** The 11 identical
pairs are harmless *at one revision*. A citation on an identical pair becomes a wrong citation the
moment a commit touches one copy and not the other, and the narrow guard is silent until then — so
it is only sound if something runs it continuously. Whether that holds is measurable, not
assumable:

```bash
# how often does a commit touch one tree but not its twin?
git log --format=%h workshop-baseline..shipping-tip | while read -r sha; do
  git show --name-only --format= "$sha" | grep -qE '^(java|dotnet)/' && echo "$sha app"
  git show --name-only --format= "$sha" | grep -q  '^solutions/reference/'  && echo "$sha ref"
done | sort | uniq -c
```

Measured over this repository's shipping range: **3 of 3** commits touching either tree touched
exactly one of them; **none touched both.** One-sided edits are not the exception here, they are
the whole population — so the mechanism that converts a harmless citation into a wrong one is the
normal way this repository changes.

**But no pair actually flipped from identical to drifted in that range (0 of 64), and the honest
statement keeps both halves.** The nearest miss is `b7fc289`, which edits `CatalogApplication.java`
in the reference tree only — a genuine one-sided edit to a twinned file that happened to land on a
pair which was *already* drifted, so it deepened existing drift instead of creating new drift. The
hazard's mechanism has fired; the dice were kind about where. Claiming more than that would be the
same over-reach this entry exists to catch.

One precision note on the same figures. *Harmful* is a strict subset of *observable*, not a synonym
for it: of the 4 drifted citations, one resolved silently to a different plausible call, two failed
loudly, and one was simply correct in the tree it named. The sound direction is one-way — a
citation that is undetectable is harmless, because identical bytes cannot mislead. The converse
does not follow, so a narrow guard's 4 hits are not 4 defects either.

Finally, line count cuts both ways and is not a check. `TomcatPathConfiguration.java` differs
across trees at an identical 22/22, so a length comparison **conceals** that drift. In the other
direction, a citation to `handoff.py:1008` is unambiguous despite two files having that basename,
because one of them is 255 lines long and cannot hold line 1008 — arithmetic **reveals** the tree
there. Neither behaviour is a property you can rely on; both are accidents of the files involved.

### A regex is not an inventory of a structured file

The installer count in the JDK entry above was first published as **2** and is actually **5**. The
instrument was `grep -o '"[a-zA-Z]*Installer"' … | sort -u`, and it under-counted for two
independent reasons, both silent:

- **case** — the pattern requires a capital `I`, so the three keys literally named `installer`
  never matched;
- **deduplication by name rather than by path** — `sort -u` collapses three distinct
  `databases.*.installer` keys into one, because they share a key name while living at different
  paths.

Either defect alone hides keys. Together they turned five into two, and nothing in the output said
so: a grep that finds fewer things looks exactly like a file that contains fewer things.

Walk the structure instead, and report **paths**, not names:

```python
import json
hits = []
def walk(node, path=""):
    if isinstance(node, dict):
        for key, value in node.items():
            here = f"{path}.{key}" if path else key
            if "installer" in key.lower():
                hits.append(here)
            walk(value, here)
    elif isinstance(node, list):
        for index, value in enumerate(node):
            walk(value, f"{path}[{index}]")
walk(json.load(open("workshop/toolchain.lock.json")))
print(len(hits))
```

**The correction also changed the finding, in the direction neither party expected.** The natural
reading of "all five installers are Windows" is that the lockfile is a Windows artifact — and that
reading is refutable from the same file, which pins a `linux/arm64` PostgreSQL digest for a host
that has no runtime. So a bigger number produced a *weaker* claim. **A count is not a finding;
check what the larger number does to the argument before adopting it.**

> **Withdrawn, and left here because the withdrawal is the point.** This paragraph originally
> read *"cross-platform acquisition is solved twice in this file, for a tool and for a
> database"*, citing a `darwin/arm64` Terraform download alongside the PostgreSQL digest.
> Terraform's platforms are `darwin/arm64` and `darwin/amd64` — **one OS family, macOS only**.
> See *Cross-architecture is not cross-platform* below for the measurement, and
> *An absent key may be a differently-spelled key* for what replaced the argument.
>
> It survived here for three commits **after** being withdrawn 64 lines below, because I corrected
> the two homes I remembered and did not sweep for a third. The rule against exactly that is in
> this document too. **A withdrawal is not complete until `git grep` says so** — search for the
> claim, not for the file you think contains it.

### A token every instrument agrees on is a false control

The same entry published four integrity figures as one list — `27` `sha256`, `5` `sha512`,
`6` `digest`, `16` `signature` — and they came from **three different instruments**:

| token | published | what actually yields that number |
|---|---|---|
| `sha256` | 27 | raw string occurrences, counting the `sha256:` prefix inside every digest **value** |
| `sha512` | 5 | raw, exact-key and name-contains **all agree** |
| `digest` | 6 | occurrences of a key named exactly `digest` |
| `signature` | 16 | key names *containing* `signature`: 6 `signature` + 10 `signaturePublisher` |

Exact-key counts are `19 / 5 / 6 / 6`. Not one of the three published non-`sha512` figures is
wrong *as a measurement* — each is the correct output of some defensible instrument. **The list
is wrong because it is four answers to four different questions, presented as four answers to
one.**

**What let it survive is the token that agreed with itself.** `sha512` is 5 under every
instrument, so any spot-check that happened to land on it confirmed the list. A reviewer sampling
one figure has a 1-in-4 chance of drawing the only one that cannot fail. So:

> When several figures are presented as a set, **state the instrument once and derive all of them
> with it**. If a figure disagrees under a second instrument, the disagreement is the finding.
> And do not treat a token where instruments agree as evidence about the others — agreement there
> is a property of that token, not of the method.

The general form is the one this document keeps arriving at from new directions: a check returned
a true signal about an adjacent question. Here the adjacent question was *"how many times does
this string appear"* standing in for *"how many integrity assertions does this file make"*.

### A charitable reading is an unverified claim too

Late in the same review, a reviewer declined to chase a correction with: *"if you'd rather leave
that entry as-is that's defensible, since your sentence is true of `runtimes.*`."* The sentence
was **"its complete installer set is"** those two keys. That is not true of `runtimes.*`; it is
an unscoped claim about the file, and it is false. **The charitable reading rescued it by
supplying a qualifier the text did not contain.**

This is the mirror of the rule recorded earlier about self-accusation. Both are ordinary
assertions about a measurable artifact, and both escape checking for social rather than technical
reasons:

| direction | why it survives |
|---|---|
| self-accusation | costly to the speaker, so it reads as credible, and nobody argues |
| charitable reading | costly to contest, since disputing it means insisting you were *more* wrong |

**Neither is a new class of error and neither needs a new technique.** They are the same
verification everything else gets, applied to two cases that quietly exempt themselves — the
remedy is removing the exemption, not adding a rule. In this instance the correct response was to
refuse the charity and confirm the sentence had been wrong as written.

The same reviewer had already been unable to see the fix, having read the branch two commits
behind tip — so the charity was offered about a defect that no longer existed, on the strength of
a reading of text that had already been replaced. **Stale read, then generous inference, and the
two failures compose: neither alone would have produced a wrong conclusion about the artifact.**

### Cross-architecture is not cross-platform

A claim in this document read *"cross-platform acquisition is solved twice, for a tool and for a
database."* Half of it was false, and the disproof was in the command output it was written from:

```
tools.terraform.platforms            darwin/arm64, darwin/amd64          <- one OS family
databases.postgresql localContainer  linux/amd64, linux/arm64            <- one OS family
                     windowsService  installer (.exe)                    <- second family
```

**Terraform is macOS-only.** Two entries that differ in *architecture* look, at a glance, exactly
like two entries that differ in *platform* — `darwin/arm64` and `darwin/amd64` sit in the same
shape of list as `linux/amd64` and `windows/amd64` would. The reader supplies "cross-platform"
because the list has two members.

The database half survives, and only because a **second acquisition route** exists: an installer
in one OS family and a container image in another. **Plurality within one route is not coverage
across families.** When a claim is about reach, count *families*, and count them per component
rather than across the file.

The same measurement then produced a better finding than the claim it refuted. `postgresql` pins
a `linux/arm64` digest; the only host in the file declaring `arm64` is `hosts.coordinator`, and
`hosts.workshopVm` declares `architecture: "x64"` — singular key, so it is explicitly excluded
from `arm64` rather than silently unstated. An `arm64` image serves an `arm64`
host, so the file provisions the application's **database** for the coordinator and no **runtime**
for it. That is not a scope decision about an unsupported platform, and it is not answered by
"nothing here is cross-platform" — **the file expects that host to run the database and gives it
no way to build the application.**

### An absent key may be a differently-spelled key

`.get("architectures")` on `hosts.workshopVm` returns `None`. I published that as *"declares no
`architectures` key at all"* and built an argument on the silence. The host declares its
architecture plainly, under the singular key:

```
hosts.workshopVm.architecture   = "x64"          <- singular scalar
hosts.coordinator.architectures = ["arm64","x86_64"]  <- plural list
```

**`None` from a dictionary lookup is two different facts wearing one face:** the property is
absent, or the property is present under a name you did not ask for. A lookup cannot tell them
apart, and only the first supports an argument from silence. **Enumerate the keys before concluding
one is missing** — `sorted(obj.keys())` costs nothing and answers both.

The divergence is the file's, not the reader's, and it is lopsided enough to be a trap:

```
"architecture"  (singular) : 12 objects, every value "x64"
"architectures" (plural)   :  1 object,  hosts.coordinator, value ["arm64","x86_64"]
```

The plural exists because the coordinator is the only object with more than one value — a local
decision that silently created a second spelling of the same property. The **values** diverged with
it: `x64` in all 12, `x86_64` in the one. A consumer comparing a host to a tool by string equality
gets a false mismatch, because `hosts.coordinator` never says `x64`. `tools.uv` carries both
spellings inside a single object — `architecture: "x64"` beside a URL named
`uv-x86_64-pc-windows-msvc.zip`.

**Why nothing caught it:** the frozen suite pins the majority form (`tools.git.architecture ==
"x64"`) and reads `hosts.workshopVm.azureImage.version`, but contains **no reference to
`hosts.coordinator` anywhere**. The one object that departs from the convention is the one object
the tests never touch. That is not a coincidence to be corrected by adding an assertion — it is the
general shape: **a convention is enforced where it is already followed, and the outlier is outside
the guard because being outside is what made it an outlier.**

Ask of a structured file *"which spellings of this property exist"*, not *"what is this property's
value"*, and check the minority spelling first — it is where the exception lives.

### One function has four valid addresses, and none of them says which

The duplicate-basename trap has a third scale below the file. A reviewer described four citations
into one module as competing claims: a range `234-325`, a point `:234`, a "correct" `:270` that was
retired in favour of it, and a `:300` that had been measured but not filed. Resolved against the
tree, they are not competing:

```
$ python3 -c "import ast; ..."          # AST, not grep
_validate_telemetry_results: lines 234-325
   234 INSIDE    270 INSIDE    300 INSIDE    325 INSIDE
```

**`234-325` is the function's exact extent. `:234` is its `def` line. `:270` and `:300` are lines
inside it.** All four are correct addresses for the same function. Nothing was fabricated and
nothing was fused — and "retiring `:270` in favour of `:234`" is not a correct citation replaced by
a wrong one, it is a **precise address replaced by a containing one**, which reads identically in
prose.

So the address ambiguity runs at three scales, and the notation is the same at all three:

| scale | collision | example |
|---|---|---|
| tree | one basename, two trees | `Program.cs:86` |
| repository | one basename, two directories | `handoff.py:270` |
| **function** | **one function, four addresses** | **`:234` vs `234-325` vs `:270`** |

A `def` line and a line of interest are both written `file.py:N`. **A citation carries a number but
not a granularity**, so a container's address is indistinguishable from a claim about its contents.
That is why the disagreement looked substantive: two parties citing the same function at different
granularities appear to disagree about *where* the defect is.

Resolve with the parser, not the line number:

```python
import ast
tree = ast.parse(open(path).read())
for n in ast.walk(tree):
    if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.lineno <= LINE <= n.end_lineno:
        print(n.name, n.lineno, n.end_lineno)
```

If two citations land in the same node, they are the same claim at different zoom levels — reconcile
them before treating either as a correction of the other. `grep -n` cannot tell you this; it reports
lines, and the unit of the argument is a function.

**The corollary matters more than the rule.** Every earlier instance in this document was a citation
that resolved to the *wrong* thing. This one resolves to the *right* thing four different ways, and
still produced a disagreement, a withdrawal of a true reading, and a filed finding. **Ambiguity does
not require an error to do damage.**

### In wrapped prose, a longer search pattern is not narrower - it is broken

The sweep that found the contradiction above nearly did not. Measured against the revision that
carried it, with the defect definitely present in the file:

```
"solved twice in"                          -> 1   <- the fragment actually used
"cross-platform acquisition is solved twice" -> 2
"solved twice in this file"                -> 0   MISS
"acquisition is solved twice in this file" -> 0   MISS
```

The claim is hard-wrapped: `solved twice in` ends one line and `this file,` begins the next.
`git grep` matches within a line, so **every pattern long enough to span the wrap returns zero.**

**This inverts the usual intuition about search.** A longer pattern is normally just more specific -
fewer hits, same reliability. Here it is not narrower, it is **non-functional**, and it fails
silently with the most reassuring output a sweep can produce. Worse, the failure is correlated with
diligence: **a reviewer who pastes the full sentence they just withdrew is the one guaranteed to
miss it**, while a careless three-word fragment finds it. Precision is anti-correlated with recall.
42% of the non-blank markdown lines in this repository fall in the 70-100 character band, so this
applies to the whole documentation set, not one paragraph.

Sweep on normalized whitespace, not on lines:

```python
import re, pathlib, subprocess
flat = lambda p: re.sub(r"\s+", " ", pathlib.Path(p).read_text(errors="replace"))
for f in subprocess.run(["git","ls-files","*.md"],capture_output=True,text=True).stdout.split():
    if CLAIM in flat(f):
        print(f)
```

**`git grep` reports lines; the unit of a claim is a sentence; in wrapped prose a sentence is not a
line.** Same mismatch as citing a function by a line number - the tool's unit is finer than the
argument's unit, and nothing in the output says so.

### The re-run is only a control if the instrument changes

Three instruments failed inside ten minutes while *verifying* the entry above, all silently:

1. `grep -c` for the wrapped phrase - returned the **exact inverse** of the truth, reporting the
   claim absent from both revisions that carried it and present only in the commit that fixed it.
   Acting on it would have meant telling a correct reviewer their correction was wrong.
2. A "was it marked as withdrawn" heuristic with a 170-character context window and a hand-listed
   set of marker phrases - raised a false positive because the list omitted *"I published that as"*.
3. The original sweep, which succeeded only because the fragment happened to fit on one line.

The lesson is not *re-run the check*. **I did re-run it, and the re-run carried the same blind spot,
because it was the same kind of instrument asking the same kind of question.** A repeated
measurement confirms a defective instrument as readily as a sound one.

> **Re-running a check is a control only when the second run uses a different instrument.** Same
> tool, same unit, same assumption - a second run buys nothing but confidence.

Cheapest way to satisfy this: make the second instrument structural where the first was textual.
Parse where you grepped; walk keys where you pattern-matched; resolve a line to an AST node where
you read a number. Every recovery recorded in this document came from changing the instrument, not
from repeating the measurement.

### An AST resolution is exact and still revision-relative

Two parties resolved the same symbol in the same file with the same tool and got contradictory
answers. Both were correct:

```
rev                          file    validate_handoff   _validate_structured_path_evidence
4bf59f7 (baseline)           1288    1010-1288          ABSENT
origin/rewrite-integration   1313    1033-1313          1010-1030
```

The shipped fix inserts a new function at line 1010 - **exactly where `validate_handoff` began in
the baseline** - displacing it to 1033. So `:1145` lands inside `validate_handoff` in one tree and
the ranges disagree by a constant offset in the other, and neither party had stated which revision
they measured.

**This happened immediately after both parties agreed that a citation must carry a granularity.**
We fixed the granularity and both dropped the `ref`. Worse, the parse *conceals* the omission:
`file.py:270` at least looks like it might be revision-sensitive, whereas
`_validate_telemetry_results` reads like a stable name and returns an authoritative-sounding answer
either way. **Adding precision to an address does not reduce its dependence on the revision - it
disguises that dependence**, because a parser's output carries no visible coordinate for the tree it
parsed.

**And the failure mode was an absence, for the third time in this document.** Resolving
`_validate_structured_path_evidence` against the tree that lacks the fix returns `NO SUCH FUNCTION`.
I had the name right, from a diff of the shipped tree, and was one step from reporting that I had
invented it. That is the same shape as `.get("architectures")` returning `None` - **an instrument
reporting absence when it was pointed at the wrong object** - and it is the shape that recurs most
in this audit, because absence is the one answer that looks identical no matter why it was produced.

Quote the rev with the symbol, exactly as with a line:

```
_validate_structured_path_evidence @ origin/rewrite-integration  (1010-1030)
```

A symbol name is an address. It has the same components as any other, and `ref` is the one that
looks least necessary and is least often supplied.

### Markdown is not text, and every layer of it emits its own zero

Verifying the sweep above required four instruments. Each was built to escape the previous one's
blind spot, and each had its own:

| # | instrument | defeated by | symptom |
|---|---|---|---|
| 1 | `git grep` on lines | hard wraps | `0` |
| 2 | collapse whitespace | inline emphasis - `` `architectures` `` splits the phrase | `0` |
| 3 | + strip emphasis | blockquote `>` continuation markers | `0` |
| 4 | + strip `>` | fenced code blocks quoting the claim as **data** | false **positive** |
| 5 | + drop fences | - | clean |

Measured on this repository, for the plain-English claim *declares no architectures key*:

```
whitespace-normalized only : 0        <- reads as "absent"
markdown-aware             : 2
```

**Instrument 2 reported the claim absent while it was present twice**, because the sentence is
written `declares no ` + backtick + `architectures` + backtick + ` key`. To a reader that is one
sentence; to every textual instrument it is a different byte string. The earlier sweep that got this
right did so only because its pattern happened to place wildcards where the backticks are - **the
third consecutive time an instrument here succeeded by luck rather than by design.**

Note the asymmetry in the table. Layers 1-3 fail by emitting **zero**; layer 4 fails by emitting a
**false positive**. Only the false positive announces itself. **Every markup layer that can hide a
phrase reports its failure as absence**, which is the same shape as `.get("architectures")`
returning `None` and as resolving a symbol against the wrong revision. Absence is the answer that
looks identical regardless of why it was produced, and it is the delivery's most repeated defect
by a wide margin.

**The stopping condition is therefore not "I used a different instrument."** Instruments 1-2, 2-3
and 3-4 each *disagreed* with their predecessor. A disagreement means the run is not finished; a
single different instrument is only the first of an unknown number of layers.

> **Keep changing the instrument until two of different kinds agree. One disagreement means keep
> going; the first agreement is the result. A lone zero is unverified no matter which tool produced
> it.**

Working normalization for a claim sweep over markdown prose, in the order the layers were found:

```python
def norm(t):
    t = re.sub(r"(?ms)^```.*?^```", "", t)   # code fences: text there is data, not assertion
    t = re.sub(r"(?m)^\s*>\s?", "", t)       # blockquote markers are not whitespace
    t = re.sub(r"[*_`]", "", t)              # inline emphasis splits phrases invisibly
    return re.sub(r"\s+", " ", t)            # hard wraps
```

### Absence from a branch that lacks the substrate proves nothing

A remedy was checked for on the default branch to decide whether it had shipped. It was absent, and
the conclusion drawn was that the fix had not been delivered. Measured:

```
merge-base(main, 4bf59f7)  = main itself
main..4bf59f7              = 52 commits
4bf59f7..main              =  0 commits          <- main is a strict ancestor

on main:  workshop/toolchain.lock.json ABSENT   tests/acceptance ABSENT
          java ABSENT                           infra ABSENT
```

**`main` is not a divergent line, it is an old one** - 52 commits behind the frozen baseline, and it
contains none of the substrate the defect lives in. The acceptance suite is not there; neither is
the module holding the gate the remedy is about. So *"the remedy is absent from `main`"* is true and
carries no information: **everything is absent from `main`.** A check that cannot distinguish
"withheld" from "nothing here yet" has not measured delivery.

**The verdict was still right, and the evidence for it was one ref away.** The remedy is also absent
from `4bf59f7` - the frozen baseline every artifact is required to record as its `sourceCommit`, and
therefore the tree participants actually receive. That is the ref that decides the question, it was
already the project's stated convention, and it supports the same conclusion soundly.

Two rules, and the second is the one that is easy to miss:

- **Before reading absence as a decision, confirm the ref contains the thing the artifact belongs
  to.** Probe for a sibling that must be present - here, the module the remedy edits. If the sibling
  is missing too, the instrument is pointed at the wrong tree and its zero means nothing.
- **A correct verdict reached on unsound evidence is not a smaller error than a wrong verdict.** It
  survives review because the conclusion checks out, and the defective reasoning is what gets reused
  on the next question, where it will not happen to be right.

This is the fourth distinct mechanism in this document whose failure mode is an indistinguishable
`ABSENT`: a lookup under a differently-spelled key, a symbol resolved against the wrong revision, a
phrase hidden by markup, and now a path checked on a tree that predates it. **Absence is never
self-explanatory. Every one of these produced a confident conclusion from a zero, and in three of
the four the zero was an artifact of the instrument rather than a fact about the world.**

### The claim you never verify is the one that costs nothing to accept

This arm reproduced every contested claim it was sent before responding to it, across an entire
engagement. It never once checked the claim that *defined its own scope* - a restriction to a
no-deploy boundary, justified by a citation that turned out to be wrong twice.

The citation, and what is actually there at every relevant revision:

```
cited   environment.bicep    uniqueString(resourceGroup().id, stackName)
actual  infra/modules/environment.bicep
        infra/main.bicep     uniqueString(resourceGroup().id, stack, imageProvider)
```

- `infra/environment.bicep` **does not exist** at the baseline, at this branch, or at the integration
  branch. Verifying the path as written returns `ABSENT` - which reads as *deleted*, not as
  *mis-addressed*. Fifth instance in this document of an instrument reporting absence while pointed
  at the wrong object.
- The expression names a parameter that does not exist (`stackName`; it is `stack`) and omits a
  third argument (`imageProvider`).

**And the conclusion it supports is correct anyway.** `imageProvider` is
`@allowed(['azure-blob','azure-files'])` with a **default**, so two same-stack deployments collide on
names unless one is deliberately overridden; and the address space is selected by
`isJava ? '172.21.0.0/16' : '172.20.0.0/16'`, which no parameter can vary. The restriction was
sound. Both of its stated coordinates were wrong.

The reason this went unexamined for the whole engagement is not that it was hard to check - it was
two `git cat-file` calls, run here in under a minute:

> **A claim that reduces your obligations does not present itself as a claim.** Scope restrictions,
> charitable readings, granted permissions and conceded points all share the property that accepting
> them is free, so no moment arrives at which verifying them feels necessary. Contested claims get
> checked because someone is pushing; **uncontested ones that happen to favour you get checked by
> nobody.**

This is distinct from a guard that is not re-run after its author believes the work is done. **That
guard ran once. This premise never ran at all** - and the same reviewer who refused a charitable
reading on the grounds that charity is not evidence had, at that moment, been operating for hours
inside an unverified restriction.

Practical form: **verify the premises that shrink the work with the same instrument you would use on
a premise that grows it** - and note that a wrong path in such a premise fails silently, because
nobody re-derives the boundary they have already agreed to work inside.

### A positive control proves the instrument sees the corpus, not that it sees the defect

The guard adopted for absence answers - *pair every zero with a positive control* - was tested here
against the defect it was written for. It does not close it. Measured across this repository's
markdown, with instrument A collapsing whitespace only and instrument B markdown-aware:

```
probe                                   A       B      verdict
plain control   "address"               26      26     AGREE
plain control   "instrument"            69      69     AGREE
target phrase (carries backticks)        1       3     *** DISAGREE ***
```

**The plain controls pass under both instruments.** They certify instrument A as able to read the
files, while instrument A is blind to two of the three occurrences of the actual target - because
the target is written with inline emphasis inside it and the controls are not. **A control that does
not carry the property responsible for the failure cannot detect that failure.** Plain text has no
emphasis to be split by, so it can never exercise emphasis-splitting.

And choosing a valid one is not free: an emphasis-bearing candidate tried here returned `0` under
both instruments - it simply was not in the corpus. **A control must be known-present *and*
failure-shaped, and the second requirement is what makes people settle for the first.**

**The sibling probe has the same structure, one level down.** It disambiguates an absence by asking
whether a file that must exist, exists - using `cat-file`, which reports its own failures as
absence:

```
sibling candidate at 4bf59f7            4bf59f7    integration branch
tests/acceptance/catalog_acceptance/
  handoff.py                            present    present        <- valid
workshop/toolchain.lock.json            present    present        <- valid
docs/TelemetryFaultInjection.md         ABSENT     present        <- FALSE ALARM
```

A sibling added *after* the audited revision reads `ABSENT` for an entirely innocent reason, and the
probe then reports that the instrument is pointed at the wrong tree when it is pointed correctly.
**The check that resolves absence emits absence.**

So the guard needs its own qualifier, and it is not recursive without one:

> **A positive control terminates the regress only when its presence is established by something
> other than the instrument under test, and when it carries the property that would cause that
> instrument to fail.** For a revision probe, establish the sibling was added at or before the
> audited revision (`git log --diff-filter=A`) - do not infer it from the same `cat-file` you are
> trying to validate.

The general form, which is why this family has been so persistent: **every guard proposed against
absence has itself been an instrument capable of returning absence.** Terminating it requires a step
of a different kind, not a more careful step of the same kind.

### The author of a citation rule wrote six citations that break it

A criterion arrived from another track: *a guard is legitimate only when its defect class has zero
legitimate instances; otherwise it is an exemption list.* Applied here to this document's own
duplicate-basename rule, against this delivery's own prose.

The first measurement used the wrong unit and had to be discarded:

```
basenames in the tree with >1 home    121 / 592  (20.4%)   <- WRONG UNIT
```

The guard does not fire on files, it fires on **citations**. Re-measured on the population that
exists:

```
bare basename:line citations written        11
   whose basename has more than one home     6   (54.5%)
   distinct offenders: CatalogApplication.java, handoff.py,
                       HealthController.java, CatalogResourceIdentity.java
```

**The document that filed the one-basename-two-directories finding then committed it six times.**
Not through disagreement with the rule - the rule is stated three of those six times, in the very
sentences that are bare.

And that is the answer to the criterion, because those three are **legitimate**: a citation being
discussed as an example of ambiguity must be shown ambiguous. Two more are disambiguated in the same
clause. **Three were genuine defects** and are now fixed with a path prefix. So:

> A mechanical duplicate-basename guard would have flagged 6 and been right about 3. **By the
> criterion, it is an exemption list, not a rule** - the same verdict the absent-from-main guard got
> on its first live test. Two guards proposed in one hour, both rejected by their first real
> population.

The most instructive of the three is the one that already carried a revision:

```
before   CatalogResourceIdentity.java:20 at origin/rewrite-integration    ref stated, path omitted
after    java/.../config/CatalogResourceIdentity.java:20 at origin/...    both
```

Elsewhere in this audit the complementary error was made by the other party: **path stated, revision
omitted.** Same address, opposite halves, and each party supplied precisely the component the other
had spent the preceding hour insisting on. **Knowing which component is missing is not the same
capability as noticing that one is** - the first is knowledge, the second is a habit, and only the
second fires while you are writing.

### Recording the evidence changed the corpus the evidence described

A figure published in this document - *"138 `.json` files, 0 defective"* - was written as `137`. The
count had not drifted afterwards. It was already wrong when published:

```
f166e20  publish the measured signal map            -> 137   <- measured here
216433e  commit the runtime evidence artifacts      -> 138   <- my own commit
f20058e  publish "137 files, 0 defective"           -> 138   <- stale on arrival
```

The file that broke it is `evidence/runtime-test-report.json` - **the artifact committed to
evidence the finding.** It parses as JSON, so `0 defective` still holds and the conclusion is
untouched; only the denominator was stale.

> **A count is a measurement at a revision, and publishing it at a later one makes it stale with
> zero elapsed intent.** Here the interval contained a single commit, authored by the same person,
> for the purpose of supporting the very claim the count appears in. **The act of recording evidence
> made the evidence a member of the population it describes.**

Right conclusion, wrong figure - the pattern this document filed against another party an hour
earlier, committed here in its own text, in the entry that warns about corpora nobody checked were
the right corpus.

### Your own memory is an instrument, and it fails by absence

A message arrived crediting this arm with a sweep it did not recognise: a `.json` enumeration, a
generated-bundle argument, a constant it had never seen. Checked against recollection, all of it
read as **absent**, and the conclusion forming was that another track's work had been misattributed
- which would have been an accusation, not merely an error.

The repository disagreed:

```
f20058e   docs: record that a tracked-file sweep cannot see a generated artifact   <- mine
CommonErrors.md:1235   the sweep, the count, the corollary                        <- mine
```

**It was this arm's own work, from earlier in a long session.** The only reason nothing was sent is
a standing rule to reproduce before writing - a rule adopted for other people's claims, which
happened to cover this one.

> **In a long session the least-audited instrument in use is your own recollection, because it does
> not present itself as an instrument.** Every other tool here announces that it is one. Memory
> returns absence in the same undifferentiated form as `cat-file`, `.get()` and `grep` - and that
> absence is indistinguishable from *never happened*.

This is the seventh absence in this document and the only one whose output would have been a claim
about another party's conduct rather than a wrong technical figure. **The failure mode does not get
gentler as the stakes rise; it gets quieter, because a memory of not-doing-something feels like
knowledge rather than a measurement awaiting a control.**

### Evidence you found needs my corpus; evidence you built needs nothing

The finding that a plain positive control certifies an instrument blind to its target was published
here with real numbers measured against this repository. A correspondent could not reproduce it:

```
their tree   plain "address"      A=11  B=11  AGREE
             plain "instrument"   A=17  B=17  AGREE
             target w/ backticks  A= 0  B= 0  AGREE     <- "no disagreement exists"
```

Their `AGREE` was correct and meant nothing: **the target phrase exists only in this branch's
prose.** They declined to confirm or dispute, which was the right call and left a true finding
unverified on the strength of who happened to own the file.

The defect was not in either instrument. It was that the evidence was **found** rather than
**constructed** - anchored to a corpus one party did not have. The same property demonstrates in two
lines with no repository at all:

```python
doc = "The address is stable.\nThe `architectures` key is absent.\n"
ws = lambda t: re.sub(r"\s+", " ", t)                        # whitespace only
md = lambda t: re.sub(r"\s+", " ", re.sub(r"[*_`]", "", t))  # markdown-aware

"address"                  ws=1  md=1   AGREE   <- control certifies ws
"The architectures key"    ws=0  md=1   DISAGREE
```

The plain control passes under both instruments and licenses `ws`; `ws` cannot see the target.
**No corpus, no revision, no ownership, and nothing to take on trust.**

> **Evidence drawn from a corpus establishes that something happened. Evidence constructed from the
> mechanism establishes that it must.** The first is defeated by a correspondent holding a different
> tree - and every claim in this audit that failed to reproduce failed exactly that way, not because
> it was wrong.

The practical consequence is cheap and was available the whole time: **when a finding is about a
mechanism rather than about this repository, ship the minimal construction alongside the
measurement.** The measurement shows it is real here; the construction shows it is real anywhere,
and it survives being read by someone with a different checkout, a different branch, or no checkout
at all.

### The normalization that is correct for one question is wrong for the next

The five-layer markdown normalizer built earlier in this document drops fenced code blocks, because
for the question *"is this claim asserted in prose?"* a fence contains quoted data, not an
assertion. It was then reused, unchanged, for a different question - *"does this claim have a home
in the repository?"* - and returned three false negatives:

```
claim                      fences dropped   fences kept   truth
positive-control numbers          0              1        in a code fence
6-of-11 citation figures          0              1        in a code fence
two-line construction             0              1        in a code fence
```

For the second question, **a fence is exactly where the evidence lives** - tables of measurements
and runnable fixtures are fenced by construction. Same instrument, same corpus, same author, one
question later, and the normalization that made it correct made it blind.

> **A normalizer encodes the question it was built for.** Reusing it silently re-asks that question
> instead of the new one, and the answer is returned in the vocabulary of the new question. This is
> not a wrong corpus, a wrong revision or a wrong unit - **it is the right instrument aimed at the
> right data, answering something you are no longer asking.**

Ninth absence instance here, produced by the check written to audit the author's own discipline.

### The unversioned corpus is the one nobody sweeps

The same check, once corrected, found one claim with **no tracked home at all**: a six-item
enumeration asserting that every non-reproduction in this audit failed by corpus anchoring rather
than by being wrong. It was composed directly in correspondence and never committed.

The standing rule here was *commit before messaging*, and it held for every claim but the last -
because the last was not a report of work already done, it was **a new synthesis written in the
channel.** That is the case the rule does not cover: it guards claims that summarise commits, not
claims that are born in a message.

> **A message stream is a corpus with no revisions, no sweep and no reader who audits it - and it is
> quoted into artifacts that do have all three.** Every propagation guard in this document operates
> on tracked files. None of them can see the place where the most general claims were first stated.

Worse on inspection, the untracked claim was also **over-scoped**: it asserted six non-reproductions
when only four were verified here and two were reported by a correspondent whose tree this author
cannot read. The claim that escaped the sweep is the one that needed it - not by coincidence, but
because **a synthesis is exactly the kind of claim that outruns its evidence**, and committing it is
what would have forced the count.

Recorded in its honest form: **four verified, two reported**, and the pattern holds across the four.

### Naming the ref does not repair `git log --diff-filter=A`

The prescribed terminator for absence checks was "establish the file with `git log --diff-filter=A`
rather than with the `cat-file` under test," later amended to "and name the ref explicitly, because
`git log -- path` silently resolves to HEAD." The amendment is necessary and **not sufficient.**
Constructed in a four-commit throwaway repository, no corpus required:

```
file present at HEAD:                                      PRESENT
git log --diff-filter=A -- target.json      (implicit)     0 commits
git log --diff-filter=A HEAD -- target.json (EXPLICIT)     0 commits   <- amendment does not help
  + --full-history                                         0 commits   <- nor does the usual remedy
  + --diff-merges=first-parent                             8 commits   <- finds it, and 7 others
```

`git log` does not diff merge commits by default. A file that first enters a tree through a **merge
resolution** therefore has no add-commit at any ref, and the two obvious repairs - naming the ref,
and `--full-history` - both still return zero. The only flag that finds it makes the instrument
over-report by diffing every merge.

> **A guard can have two independent failure modes that produce the identical output, and fixing the
> one you found leaves the other in place, still silent.** The amendment is correct about the defect
> it names and provides no protection at all against the one beside it.

### A constructed mechanism is not a live defect, and saying so is the discipline

Having proved the above, the honest next question is whether it happens **here**:

```
tracked files at HEAD ......................... 771
with no add-commit via --diff-filter=A ........   0
positive control (known-present, failure-shaped)  1 commit   <- instrument works
```

**Zero live instances.** This history contains no merge that introduces a file, so the residual
failure mode is latent, not active - and for the case actually in dispute the amendment *is*
sufficient in practice.

This corrects a rule stated earlier in this document. Constructed evidence was described there as
strictly stronger than found evidence, because it establishes that a defect *must* occur rather than
merely that it *did*. That is over-stated. They answer different questions, and neither answers the
one that decides whether to act:

| evidence | question it answers |
|---|---|
| found in a corpus | did this happen? |
| constructed from the mechanism | can this happen at all? |
| population survey | is it happening **here**, and how often? |

> **A construction proves possibility and says nothing about incidence.** Reporting a constructed
> mechanism without its population count is how a latent defect gets filed with the urgency of a
> live one - the same over-claim as reporting a single found instance as if it were a pattern,
> arrived at from the opposite direction.

### The remediation pattern could not see the citations it was meant to fix

An earlier entry audited ambiguous citations in these documents, found six of eleven naming a
basename with more than one home, fixed three and declared the class handled. The audit pattern was
`basename:line`. Re-checked against the same basename from a different direction:

```
handoff.py at 4bf59f7
  tests/acceptance/catalog_acceptance/handoff.py   1288 lines
  tests/acceptance/catalog_migrate/handoff.py       253 lines
  bare `4bf59f7:handoff.py`                        ABSENT   <- resolves at the repository root
```

**Mentions carrying no line number were structurally invisible to the audit.** The pattern required
a colon; a bare `handoff.py` in prose or in a table cell has none, so the remediation swept a subset
defined by its own syntax and reported the class closed. Same aggregation-unit defect as the one
this document already files - committed inside the fix for it.

One real defect was found this way: a sibling-probe evidence table recorded the row `handoff.py
present present` while its two neighbours carried full paths. **The path as written resolves ABSENT
if executed literally** - a table asserting a successful presence check, containing a probe that
would fail. Corrected to the full path.

### The measurement that raised the alarm was attributed to the wrong mechanism

The same check reported five bare mentions. The instrument was `grep -o 'handoff\.py'`:

```
unanchored  handoff\.py                        7
anchored    (^|[^A-Za-z_/])handoff\.py         4
```

Both figures are **correct at the revision where they were taken**. The published explanation was
not. It read: *`handoff.py` is a substring of `test_migration_handoff.py`, so an unqualified pattern
matches a different file three times.* Decomposed exhaustively at that same revision:

```
e16f24a   docs/CommonErrors.md   total 7   substring confounder 0   path-qualified 3   bare 4  (sums)
e16f24a   REPO-WIDE              total 8   substring confounder 1   path-qualified 3
```

🔴 **The scope line above was added later and it changes the charge.** The published figure named no
file. **Within `docs/CommonErrors.md` there are zero substring matches; repo-wide there is one**
(`docs/ImplementationLog.md:1274`). So the correspondent's stated mechanism was **real in the corpus
they had** and absent only in a narrower one this document never disclosed. **The charge is
downgraded from a fabricated cause to a scope disagreement**, and the original wording is left below
so the downgrade can be checked against it.

**Zero substring matches** *in this file*. All three excluded items were **path-qualified citations** - the exact
practice this document spends its length demanding. The anchor `[^A-Za-z_/]` excludes `/`, so it
discards `catalog_acceptance/handoff.py` for the same reason it discards an accident, and the two
land in one indistinguishable bucket. **That half stands unaffected by the scope correction:** the
anchor does discard the good practice, at either scope.

> **The gap was real and the number was right.** The mechanism named for it was **partly** right -
> it accounts for one exclusion of four, not zero of four, and only outside this file. A correct
> measurement with a wrong cause is harder to catch than a wrong measurement, because the arithmetic
> checks out and the explanation is the part nobody re-derives. **A correct measurement whose scope
> is unstated is harder still, because it can convict the other party of inventing something that is
> sitting in a file you did not search.**

Of the four bare mentions, three are legitimate - the citation is the subject of the sentence, shown
ambiguous on purpose - leaving one defect, which stands.

> **A basename pattern with no boundary anchor matches every filename that ends with it** - a real
> mechanism, and simply not the one operating here. Absence has dominated this document because it
> is silent; this is the loud failure, and it is more persuasive: a spurious non-zero reads as
> confirmation, and nobody re-derives a count that agrees with their suspicion.

### Writing this entry doubled the population it reports on

```
e16f24a  (before the entry)   total  7   bare 4
76eade9  (after  the entry)   total 15   bare 9
```

The entry above names the file it counts, in prose and in fenced examples, eight further times.
**Anyone re-deriving the figure from the document that states it gets 15, and the document says 7.**

Second occurrence of a mechanism already filed here for a JSON file count, and the first was not
enough to prevent the second - because the rule was written as a fact about that one artifact rather
than as a property of **any measurement published into the corpus it measures.** Both figures are
therefore recorded with the revision that produces them, which is the only form in which either is
checkable.

### "Measured:" is not a measurement

A correspondent filed a CRITICAL against themselves for writing *"I checked your accounting and it
holds"* when no check had occurred. Sweeping this delivery for the same class found one instance in
the shipped deliverable - a paragraph opening `Measured:` and then asserting two facts with no
command, no output and no numbers beside them.

Re-run tonight, the claim turned out to be **true**:

```
30c5a05   1 file   evidence/ch01-feedback-java-rewrite.md   ancestor of published tip: YES
fb74cf2   1 file   evidence/ch01-feedback-java-rewrite.md   ancestor of published tip: YES
```

So this is the benign half of that CRITICAL, and the pair is the point:

> **A verification that happened but left no evidence, and a verification that never happened, are
> the same document.** The reader cannot separate them. The careful author receives no credit for
> the work and the careless one pays no penalty for skipping it - and the only thing distinguishing
> them is a memory, which this document has already recorded as an instrument that fails by absence.

It is the absence family one level up. Every earlier instance was a missing *object* - a key, a
file, a phrase, a revision. This is a missing *record of an act*, and it fails identically: silently,
and in the direction that flatters the author.

The remedy is mechanical and costs one paste: **the word `Measured:` must be followed by the
measurement.** Where it is not, the claim is an assertion in the register of evidence, which is the
most persuasive form an unbacked claim can take.

Sweep result for this delivery: 1 instance, true, now backed. The population is small because the
house style is to paste output; the instance that escaped is the one where the output was three
short facts that felt too small to fence - **the same reason the untracked synthesis escaped, and
the same size threshold.**

### Reproducing the symptom cannot identify the mechanism when the symptom is absence

A correspondent, having had a construction model the wrong mechanism, filed the remedy: *a
construction must reproduce the reported symptom before it is permitted to refute anything.* The
rule is right about refutation and **cannot work for this defect family.** Both modes, built side by
side in one throwaway repository:

```
MODE 1  file on a side branch, probed from a branch that lacks it
   implicit ref                 0
   explicit ref                 1     <- naming the ref REPAIRS it

MODE 2  file created during a merge resolution, present at HEAD
   implicit ref                 0
   explicit ref                 0     <- naming the ref does NOT repair it
   control (ordinary add)       1     <- instrument not blind
```

**The reported symptom in both cases is `0`.** A construction of mode 2 aimed at a mode 1 report
reproduces the symptom perfectly and models the wrong thing - which is precisely the error the rule
was written to prevent. Reproducing absence proves only that you built something that also emits
absence.

> **A symptom-match control requires a discriminating symptom, and this family has exactly one
> output.** It is the same result as before, one level higher: every guard proposed against absence
> has itself been an instrument capable of returning absence - and now so is the guard proposed
> against *constructions* of absence.

The repair is available and it is in the table above: the two modes differ not in the symptom but in
**what changes the symptom.** Naming the ref moves mode 1 from `0` to `1` and leaves mode 2 at `0`.

> **A construction identifies its mechanism when it exhibits a manipulation under which the symptom
> changes, and the report exhibits the same response.** The discriminator identifies the mechanism;
> the symptom never could.

### And the honest accounting of this arm's own construction

Applying that standard backwards, the merge-resolution construction filed here **did not reproduce
the reported symptom** - the field case was mode 1, and mode 2 is a different mechanism with the
same output. It was legitimate only because it was offered as an *extension* rather than a
refutation, which is the scope the correspondent's rule correctly carves out.

Its incidence should be stated plainly rather than left flattering:

```
tracked files surveyed, two independent trees   1525
instances of mode 2 found                          0
field observations of mode 2 anywhere              0
```

**Mode 1 has been observed; mode 2 has only been built.** Possibility, incidence zero, no field case
- and a construction with no field case is the weakest form of real evidence there is, easily
mistaken for the strongest because it executes.

### The instance ordinal was never derived from anything

Across this audit the absence-family instances were numbered by hand - *"seventh instance"*, *"ninth
and tenth"*, *"eleventh"* - each incremented in correspondence at the moment of writing. A
correspondent has now published **eleven instances** in a versioned report, sourced from those
messages. Swept here for the first time:

```
"instance(s)" in the tracked corpus                      39
   of those, carrying an ordinal                          4     -> 4th, 5th, 9th
   gaps in the sequence 1..9                              1,2,3,6,7,8
"### " sections exhibiting an absence mechanism          23     (keyword-derived)

positive controls, phrasings used in correspondence
   "Ninth and tenth instances"                             0
   "instance eleven"                                       0
   "Eleventh"                                              0
```

**Three populations - 4, 11, 23 - and no instrument produces 11.** The ordinal was not measured from
the tracked corpus, from the section headings, or from any enumeration that exists. It was a running
count held in the author's head and published one increment at a time into a corpus with no
revisions.

> 🔴 **The final clause of this paragraph was struck.** It read *"and the controls confirm the tree
> never carried the sequence at all."* **That is false, and the controls do not support it.** The
> phrase `Ninth and tenth instances` was present in this file from `76eade9` through `813b1cc` and
> was removed by the author at `a4135dc` - one commit before the control was run at `5e64a26`. The
> `0` is a true reading at the ref probed; the conclusion drawn from it was about the whole history,
> which the measurement never touched. **The withdrawal itself stands** - no instrument produces 11
> - but one of its stated grounds was a correct measurement with a false cause, which is the defect
> this document charges most often. See the two entries below.

The figures above were taken in `docs/CommonErrors.md` while this entry was being drafted; at
`5e64a26` the same instrument returns **38**, not 39, and repo-wide **99**. The block is left as
published with its scope and ref now named, because the discrepancy is the subject of the next entry.

> **An ordinal is a claim about the size of a population, stated without ever naming the
> population.** It is the most citable form a figure can take - compact, confident, and carrying an
> implied enumeration that no reader can ask to see - and it is the form least likely to have been
> derived from anything.

The reader of this repository sees a 4th, a 5th and a 9th instance with nothing between them, and
cannot reconstruct the six missing members because they were never written down here.

**Position, recorded so it can be cited against this document:** the eleven is withdrawn. The
tracked corpus supports *at least* four numbered instances and twenty-three sections exhibiting the
mechanism, by two instruments that disagree; **neither is offered as the count, and no single figure
should be quoted for this family.** The pattern is established by the mechanisms individually, each
of which carries its own measurement - which is the only part of this that was ever checkable.

This is the same defect the correspondent filed against their own headline figure, arrived at from
the opposite direction: theirs was measured with an instrument blind to two-thirds of the
population; **mine was measured with no instrument at all**, and travelled further because a number
nobody derived is also a number nobody re-derives.

### A user error and an instrument defect can share an output

A correspondent, reproducing the two `git log --diff-filter=A` failure modes, found the cheap
discriminator and with it the reason the two had been confused for a fortnight of rounds. Pair the
add-count with **presence at the ref actually being asked about**:

```
MODE 1  side branch, probed from a branch lacking it   (ABSENT, 0)
MODE 2  born in a merge resolution, present at HEAD    (PRESENT, 0)
```

> **Mode 1 is not an instrument failure. `0` is a true answer about a ref where the file genuinely
> is not** - the defect is in the reader, who asked about one ref and concluded about another.
> **Mode 2 is a real instrument defect:** the file is present and the tool still reports no add.

So these were never two failure modes of one guard. They are **a user error and an instrument defect
that happen to share an output**, which is exactly why symptom-matching could not separate them -
they are not the same kind of thing. **The single output made a taxonomic difference look like a
severity gradient**, and both parties read it that way for two rounds.

The consequence is uncomfortable in both directions and is recorded that way: **the only genuine
instrument defect in the pair is the one never observed in any tree, and the one observed repeatedly
was never a defect at all.**

### A negative result is an absence claim and answers to the same rules

The binary above invites a third member: a file **present** at the probed ref that the tool reports
no add for, from some cause other than a merge. The obvious candidate is a rename - a file that
never existed under its current name. Built:

```
old.json -> git mv -> new.json,  present at HEAD
  add-count new.json  (plain)      1
  add-count new.json  --follow     1
  control   base.txt               1     <- instrument not blind
  pair -> (PRESENT, 1)   NOT a third mode
```

Git reports the rename commit as an add of the new path, so the pair separates correctly and **the
two-class taxonomy survives.** No third member was found.

That sentence is an absence claim, so it carries what this document requires of one:

> **A negative result must state the instrument and the space searched, or it is indistinguishable
> from not having looked.** Searched: rename, and root-commit files by way of the control. Not
> searched: shallow or grafted history, submodules, symlinks.

It is the first negative result reported in this audit, and it is subject to every rule filed
against the positive ones - which is the point at which the family stops being about `git` at all.

### Correcting a document before measuring it deflates the population you then report on

A correspondent filed the inflating case: **a measurement published into the corpus it measures is
falsified by its own publication.** Their decomposition went `45 -> 53` purely from writing it down,
and among the new confounders was the clause documenting the confounder.

Run against this tree, the same class appears **with the sign reversed**, which is the more dangerous
half because it manufactures evidence of absence:

```
phrase "Ninth and tenth instances" in docs/CommonErrors.md
  b230edb 0 | e16f24a 0 | 76eade9 1 | def1efe 1 | 813b1cc 1 | a4135dc 0 | 5e64a26 1
                          ^ written                            ^ struck    ^ control ran here
control at 5e64a26 = 0    <- TRUE at that ref
conclusion drawn = "the tree never carried the sequence at all"   <- FALSE
```

The phrase lived in this file for three commits. **The author removed it at `a4135dc` and measured at
`5e64a26`**, then read the resulting zero as evidence about the original state.

> **A measurement taken after your own correction can read the correction as evidence about what was
> there before it.** The absence is real, the ref is right, the control is sound - and the answer is
> to a question the measurement never asked.

It is the same shape as the inflating case and invisible for the same reason: **the number is correct
at the ref.** It is also mode 1 of the `git log` pair - a true answer about one ref, generalised by
the reader to a scope the probe never covered - now with **history** as the scope rather than a branch.

**Remedy, and it is not ref-citation alone:** a claim about whether something *ever* existed is a
claim over a range of refs and must be measured over one - `git log -S` across the range, not
`git grep` at a point. A point probe cannot answer a historical question no matter which point it names.

### A ref-cited figure that fails to reproduce indicts the instrument, not the corpus

Testing whether the ref-citation remedy actually protects, the two ref-carrying figures in this
document behave differently, and the difference is the useful part:

```
.json @4bf59f7      published 130   re-derived now 130 130 130   REPRODUCES
handoff.py @e16f24a published 7/0/3/4  re-derived now 8/1/3      DOES NOT
tree sha of e16f24a fixed: e01f5d5b...   -> the corpus CANNOT have changed
```

Since the tree at a named ref is immutable, **a ref-cited figure that fails to reproduce cannot be
corpus drift.** It is necessarily the instrument. Scoping resolved it at once:

```
@e16f24a  docs/CommonErrors.md      total 7  confounder 0  path-q 3   <- the published figure, exact
          docs/ImplementationLog.md total 1  confounder 1  path-q 0
controls: known-present = 1   failure-shaped = 0
```

> **Naming the ref does not make a figure reproducible; it makes irreproducibility diagnostic.** A
> bare figure that fails to reproduce is ambiguous between corpus drift and instrument change. A
> ref-cited one that fails can only be the instrument.

🔴 **And the finding is against the author.** The figure was correct - for one file. It was published
as a statement about the corpus with the file never named, and used to charge a correspondent with
**fabricating** a cause on the ground that *"zero substring matches existed."* Repo-wide at that ref
**one exists** (`docs/ImplementationLog.md:1274`), so their stated cause was real in the scope they
had and false only in the undisclosed narrower one. **The charge is downgraded from fabrication to a
scope disagreement**, and it is this document's own most-filed defect - an undisclosed corpus -
landing on the single most severe accusation it makes.

### The verification of a strike was blind to the way this document wraps

A correspondent reported asserting a strike without running it. Run here, the strike **was** run - and
the instrument could not see the failure mode, which is the worse outcome:

```
phrase struck last commit: "controls confirm the tree never carried the sequence at all"
  git grep -F  @HEAD    0     <- reads as a clean strike
  normalized   @HEAD    1     <- STILL PRESENT, quoted inside the correction
controls: known-present raw 1 / norm 1   failure-shaped raw 0 / norm 0
```

This file is hard-wrapped near 100 characters, so the quoted clause is split by a newline and a raw
`grep` cannot match it. **The strike removed the assertion; the text remains, and the check said
otherwise.**

> **A verification that runs and returns the answer you wanted is not better than an unrun one when
> the instrument cannot see the failure mode. It is worse** - it converts an unchecked claim into a
> checked one while adding no information, and the record now says someone looked.

The aggravating detail is that this document **already contains** the entry prescribing whitespace
normalization before searching prose, written by the same author for the same reason. A finding
scoped to the instance that produced it does not generalise on its own; it has to be applied.

### Quoting a struck claim is correct practice and is indistinguishable from asserting it

The correspondent's inverse of the drift finding - **a correction can manufacture the instances it
reports absent** - reproduces here in the same commit that filed it:

```
"fabricat"        @5e64a26 12  ->  @HEAD 14     (+2, both inside the downgrade)
"fabricated cause" @5e64a26  1  ->  @HEAD  1     (struck as an assertion, retained as a quotation)
```

The downgrade of a charge quotes the charge, so the phrase survives at the same count. **This is not
a defect to remove.** Leaving the original wording beside a correction is what makes the correction
checkable, and this document demands it everywhere else.

> **Occurrence counting cannot distinguish an assertion from a quotation of one.** Any count of a
> withdrawn phrase is therefore uninterpretable without reading every hit - and a withdrawal, done
> properly, *raises* that count. The remedy for one defect is the cause of the other, and the only
> resolution is to stop treating the count as the evidence.

### An ordinal fed by several families is not one sequence

The correspondent found nine families sharing one ordinal namespace in their report - "eighth absence
instance", "eighth code instance" and "eighth instance" being three different eighths, each locally
valid, letting a counter advance indefinitely on work that never belongs to the same sequence twice.

Measured here it fires, more weakly, and the re-measurement is the finding:

```
ordinal+instance collocations   7      distinct ordinals   4
  ninth    n=4   families [absence, bare]   <-- AMBIGUOUS
  fifth    n=1   [bare]      seventh n=1 [bare]      first n=1 [bare]
```

One ordinal of four is ambiguous. But this is now the **third** count of the same population in this
document - 4 ordinal-carrying instances, then 4 with different members, now 7 collocations - each
from a slightly different instrument, none reconciling.

> **That a population yields a new size every time it is measured is itself the proof that it was
> never well-ordered.** The disagreement is not noise around a true value; there is no true value to
> be noisy around.

### The CI/CD evidence gate rejects every honest capture, not just the honest one

A correspondent reported that the workshop ships Container Apps in `Single` revision mode while the
CI/CD evidence schema requires `"multiple"`, so an attendee who reports their environment honestly
fails the gate. **Reproduced here, and the defect is one step worse than reported.**

Substrate, all in this tree:

```
infra/modules/environment.bicep:667        activeRevisionsMode: 'Single'
infra/main.json:919 / environment.json:661 "activeRevisionsMode": "Single"
workshop/contracts/cicd-evidence.schema.json:332   "mode": { "const": "multiple" }
   ... 'mode' is required, and 'revisions' is a top-level required property
workshop/contracts/fixtures/sre-agent/incident.json:725   "activeRevisionsMode": "Multiple"
```

Validated with `jsonschema` against the shipped schema:

```
shipped example (mode="multiple")                    PASS
honest attendee on shipped infra ("Single")          FAIL   'multiple' was expected
attendee who FIXED the mode, az casing ("Multiple")  FAIL   'multiple' was expected
```

**Two independent defects, not one.** The first is the mode disagreement. The second is **case**: the
ARM enum is `Single`/`Multiple` capitalized - as this repository's own Bicep and its own ARM-shaped
fixture both spell it - while the evidence schema demands lowercase `multiple`.

> **There is no honest capture that satisfies this gate.** The true value fails, and the corrected
> true value fails. **The only passing document is one whose observed value has been edited**, so the
> gate does not merely permit inaccurate transcription - it requires it.

**Why the frozen suite is green anyway:** the suite validates the *shipped example* against the
schema, and the example was authored by hand at `"multiple"` rather than captured from a deployment.
The single document that satisfies the contract is the one that never touched Azure.

> **An example authored to satisfy a schema cannot test whether the schema can be satisfied by
> reality.** It certifies that the two files agree with each other, which is the one thing never in
> doubt.

Out of scope for the Challenge 1 rewrite path and recorded here rather than in that path's
deliverable; handed to the integration branch, which owns the cross-challenge report.

### An integration measured on one commit does not describe integrating the branch

A correspondent measured the cherry-pick of `0879b2f` onto their branch and reported the accurate
handoff as **"one docs hunk to resolve by hand, nothing else"**, with both Java runbooks clean. The
commit description verifies exactly: 5 files, +67/-2, nothing under `infra/` or `.github/workflows/`.

But the operator will not cherry-pick one commit; they will integrate the branch. Measured at the
current tip with the same read-only tool:

```
merge-tree --write-tree HEAD origin/rewrite-integration        exit 1
CONFLICT  docs/CommonErrors.md
CONFLICT  docs/ImplementationLog.md
CONFLICT  java/README.md                                    <- reported CLEAN for the cherry-pick
CONFLICT  solutions/ch01-copilot-rewrite/java/README.md      <- reported CLEAN for the cherry-pick
control: self-merge exit 0 | ch01-copilot-modernization/java/README.md auto-merged, 0 conflicts
worktree dirty count before and after: 0 / 0
```

**One conflict became four, and two of the new ones are the runbooks reported clean.** Both
statements are correct measurements of different operations, which is the whole defect: **a merge
result is a property of `(source, target, operation)` and is not portable across any of the three.**

**The load-bearing half is good news and had to be measured separately.** Inspecting the merged tree
rather than the conflict list:

```
merged tree 089376e
  java/.../PostgreSqlIntegrationTest.java              disabledWithoutDocker  2   markers 0
  solutions/reference/java/.../PostgreSqlIntegrationTest.java  same           2   markers 0
```

**The fix itself integrates with no operator decision at all.** Every conflict is prose.

> 🔴 **And that is the hazard, not the reassurance.** Three of the four conflicting files carry the
> Docker remedy text - `java/README.md` 7 mentions, the rewrite runbook 21, the implementation log
> 33. A careless resolution that takes either side wholesale keeps the working guard and drops the
> instructions explaining it. **The result compiles, passes, and silently stops telling the attendee
> why the test skips** - the absence family again, this time produced by the integration step rather
> than by any measurement.

**Accurate handoff, stated for the operation the operator will actually perform:** code clean, four
prose conflicts, three of which must be resolved by union rather than by choosing a side.
