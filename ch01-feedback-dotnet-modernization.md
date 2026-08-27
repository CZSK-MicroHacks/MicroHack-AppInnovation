# Challenge 1, Path 1C (.NET Copilot modernization) — run feedback

**Run conditions.** macOS arm64 laptop. No Bastion, no Windows desktop, no VS Code, none of
the three pinned extensions. All modernization work was done by the **GitHub Copilot CLI
agent** in a terminal. Azure work targeted the real subscription
`7bc68c68-f434-49ad-ab3e-b883ec39da86` / `rg-user001`; the migration and handoff were driven
on `vm-dotnet-user001` through `az vm run-command invoke`, because they are IMDS-gated and
cannot run anywhere else.

Archive provenance of the source modernized: `4bf59f7ee8dae11259d73ba5a5d7cb0e3355c4af`.
Published modernized commit: `8834e25f86b833d3bb0db33b05ce5a61a763d0f2`.

This is deliberately **not** a step recap. It is weighted toward defects that produce
*wrong but plausible* results — steps where I could have generated convincing evidence that
meant nothing, and shipped it.

---

## The headline question

> Does Path 1C's value survive the loss of the IDE tooling, or was the tooling the whole
> point?

**The value survives almost entirely — and the fact that it does is itself the most
useful finding this run produced.**

Consider what the chapter actually asks Path 1C to hand in. Its path-specific evidence is
`assessment.md`, `modernization-plan.md`, `task-results.json`, `build-test-cve-summary.md`.
All four are prose and hand-authored JSON. **None of them is validated by anything.** There
is no `task-results.schema.json` in `workshop/contracts/`. No downstream step parses the
assessment. Every one of these four artifacts is exactly as forgeable as
`evidence/ide-extensions.txt` — the file I refused to write on the grounds that it was
forgeable.

Meanwhile the chapter's *required* evidence — `azure-target-output.json`,
`migration-report.json`, `acceptance-report.json`, `runtime-test-report.json`,
`telemetry-report.json`, `modernization-contract.json` — is machine-generated, and at least
one piece of it is genuinely unforgeable (see "What is well designed", below). **The
IDE-specific deliverables carry no verification weight at all.** Removing the IDE therefore
removed nothing that was being checked.

So what did produce correctness in this run? Three things:

1. Capturing the baseline by running the real test suite on the **real .NET 8 runtime**,
   rather than taking the one-line shortcut that would have run it on .NET 10.
2. Reading `infra/modules/environment.bicep` to discover the environment-variable contract
   the application must implement — which the instructions never state.
3. **Re-running** the CVE scan after the upgrade instead of trusting the assessment's
   prediction that the upgrade would clear it. It didn't.

None of those three is an IDE feature. Two of them are actively *undermined* by the
material — one by an omission, one by the absence of any instruction to verify.

And the extension's headline capability, automated framework upgrade, is the one task that
went most smoothly by hand: two build errors, both mechanical, both fixed in minutes.

**Conclusion.** The tooling was not the point, but the chapter is written as though it
were. `challenges/ch01/README.md:114-125` spends its instructional budget pinning three
extension versions and instructing the attendee to *halt* if a version differs — while
never once naming an environment variable the application must read in order to function.
The chapter guards the thing that does not matter and leaves the thing that does
undocumented. That inversion is the single most valuable observation from this run.

---

## Defects that produce wrong-but-plausible results

Ranked by how easily an attendee ships them.

### 1. The injected environment-variable contract is documented nowhere the attendee reads

**Severity: highest. This is the defect most likely to be shipped undetected.**

`infra/modules/environment.bicep:499-588` is the *only* definition of the variables the
container receives: `CATALOG_DATABASE_AUTHENTICATION`, `CATALOG_IMAGE_PROVIDER`,
`CATALOG_BLOB_SERVICE_ENDPOINT`, `CATALOG_BLOB_CONTAINER`, `AZURE_CLIENT_ID`,
`CATALOG_SEED_PATH`, `CATALOG_STARTUP_IMPORT_ENABLED`, `OTEL_SERVICE_VERSION`,
`CONTAINER_APP_REVISION`, `DEPLOYMENT_ENVIRONMENT`, `APPLICATIONINSIGHTS_CONNECTION_STRING`.

Neither `challenges/ch01/README.md`, nor the path guide, nor
`solutions/ch01-copilot-modernization/dotnet/README.md` names a single one. The runbook says
only that the image "takes database, Blob, and telemetry configuration from the
environment."

**Why this is the worst kind of defect.** An attendee modernizing by hand will invent
plausible names — `ConnectionStrings__Catalog`, `AZURE_STORAGE_ACCOUNT`,
`ApplicationInsights__ConnectionString`. The result:

- the build is clean;
- all 42 tests pass, because no test constructs `CatalogRuntimeOptions` from environment;
- the Bicep deployment **succeeds**, because the template sets its variables regardless of
  whether anything reads them;
- the application starts and reports healthy;
- managed identity and Blob Storage are silently inert.

Nothing anywhere says no. I hit this personally: my first attempt at the managed-identity
task **inferred** the auth mode from the database hostname suffix and used
`SqlAuthenticationMethod.ActiveDirectoryDefault`. That is a defensible, professional-looking
implementation. It matches no contract. I caught it only because I went and read the Bicep,
which nothing instructed me to do.

**Recommendation.** Publish the contract as a table in the challenge README, or better, as
a `workshop/contracts/application-environment.json` that a test asserts against.

### 2. The .NET 10 upgrade does not clear the CVE, and hiding it is the same size as fixing it

`evidence/assessment.md` predicted GHSA-2m69-gcr7-jv3q would clear when EF Core moved to 10.
**It did not.** EF Core 10.0.1 resolves `SQLitePCLRaw.lib.e_sqlite3` **2.1.11**, still
vulnerable. (I left the wrong prediction visible in the assessment with a correction
appended, rather than editing it away.)

The compounding problem: **NuGet audit is on by default from .NET 10.** An advisory that the
.NET 8 build never mentioned becomes a hard `NU1903` build failure at the exact moment the
attendee changes the target framework. The build is red, they are mid-task, and two
one-line fixes are available:

```xml
<PackageReference Include="SQLitePCLRaw.lib.e_sqlite3" Version="2.1.13" />   <!-- fixes -->
<NoWarn>$(NoWarn);NU1903</NoWarn>                                            <!-- hides -->
```

The second is faster, turns the build green, and **permanently disables a security gate for
the life of the repository**. In a diff the two are visually comparable, and both are
followed by 42/42 passing tests and a successful deployment.

The material's own success criteria ("dependency/CVE result" in the summary) are satisfied
identically by both. Nothing catches the suppression.

### 3. The baseline can be manufactured with one environment variable

`dotnet test` fails on a machine that has the .NET 10 runtime but not ASP.NET Core 8. The
obvious fix, and the one most people will reach for, is `DOTNET_ROLL_FORWARD=Major`. It
produces a green 42/42 baseline immediately.

It also runs the *pre-upgrade* suite **on the .NET 10 runtime**. The "before" and "after"
runs then share a runtime, and the comparison between them measures nothing. The resulting
`evidence/dotnet-baseline-net8.trx` is byte-plausible: same 42 tests, same names, same
green, correct filename.

I rejected the shortcut and installed SDK 8.0.424 privately to `~/.dotnet-workshop`
instead. Nothing in the material would have stopped me doing otherwise, and nothing
downstream inspects which runtime produced the baseline TRX.

### 4. `evidence/ide-extensions.txt` cannot fail — and the runbook pressures you into forging it

The three pinned versions are published in `workshop/toolchain.lock.json`.
`workshop/contracts/challenge-paths.json` lists `ide-extensions.txt` in **neither**
`requiredEvidence` nor `pathEvidence`. A perfect-looking inventory is a two-minute
transcription by someone who has never opened an IDE, and nothing downstream will ever
contradict it.

I declined to write it. **That decision breaks the runbook.**
`solutions/ch01-copilot-modernization/dotnet/README.md:162-164` includes
`evidence\ide-extensions.txt` in its `git add`, so the documented commit step fails with
`pathspec did not match any files` for anyone who does not create the file.

This is worse than an unvalidated artifact. The material *actively pressures* the attendee
to produce it, and the cheapest way past the error message is to type one out. An evidence
artifact that cannot fail is not evidence; an evidence artifact that cannot fail and whose
absence breaks your build is a trap.

### 5. Container base tags have drifted off the locked digests

`workshop/toolchain.lock.json` pins:

| Image | Locked digest | Tag resolves today to |
| --- | --- | --- |
| `sdk:10.0.400-azurelinux3.0-amd64` | `sha256:679e7b7e…` | `sha256:7a440c18…` |
| `aspnet:10.0.11-azurelinux3.0-amd64` | `sha256:d21a49ce…` | `sha256:33a753f8…` |

**Both locked digests still resolve (HTTP 200)**, so digest-pinning remains correct. But a
tag-only `FROM` now builds successfully on a base that is *not* the pinned one, with no
signal. `toolchain.lock.json:346` requires verifying the lock digest "before every installer
or archive executes" — and **no step in the .NET runbook performs that check for container
bases**. `dotnet/Dockerfile` in this delivery pins by digest.

### 6. The image traversal control is invisible to the test suite

`ImageSecurityTests` exercises `LocalImageStore.IsCanonicalImageKey` only as a **static**
method, never through the `IImageStore` seam. The blob task replaces the store entirely.

A `AzureBlobImageStore` that omitted the canonical-key check would leave **all six security
tests green**. The suite cannot detect its own most important regression. I re-applied the
check explicitly and said so in the commit message, but the control now rests on code review
alone.

### 7. Telemetry has no failing signal

No test asserts that any exporter is registered. The application is entirely healthy with
telemetry disabled. The specific trap here: `Program.cs` already had a `hasOtlpExporter`
gate, and folding the Azure Monitor exporter into it is the natural-looking edit — but the
deployment sets `APPLICATIONINSIGHTS_CONNECTION_STRING` and **no** OTLP endpoint, so the
shared gate would leave Azure Monitor permanently unconfigured while everything looked
correct. I gated it independently.

### 8. The checked-in `infra/parameters/*.bicepparam` are a trap without `C:\protected\`

They carry `sourceCommit = '0'×40`, `imageDigest = 'sha256:' + '0'×64`, and
`performanceApiKey = 'SANITIZED-SECURE-VALUE-REPLACE-FOR-WHAT-IF'`. `infra/README.md:77-80`
says they are compile-only — but neither the challenge README nor the .NET runbook repeats
that, and both assume `C:\protected\` exists. `'0'×40` satisfies the template's format
assert. The exact documented failure mode ("a placeholder that satisfied the format assert
would silently deploy the wrong source", runbook:349-352) is **checked into the repository
as a working file**.

### 9. `sourceCommit` is asserted for shape, never for existence

`infra/main.bicep:104` asserts only that `sourceCommit` is 40 lowercase hex characters. A
wrong-but-well-formed SHA therefore deploys successfully, tags the image, writes a
schema-valid handoff — and fails a chapter later in Challenge 3, which checks out that SHA
and builds `dotnet/Dockerfile` from it, with no diagnostic pointing back to Challenge 1.

**Note on a related near-miss.** The facilitator channel relayed an instruction to record
`sourceCommit` as the archive provenance `4bf59f7…` rather than the pushed modernized
commit. That is precisely the wrong-but-plausible failure above, and it would have deployed
cleanly. `challenges/ch01/README.md:195-197` in fact says the two "are never
interchangeable", which is how it was caught. The guidance was retracted. Worth recording
because the defect class this workshop teaches was reproduced *by the workshop's own
support channel*, live — which is strong evidence that the two-fields-one-shape design is
genuinely confusing rather than merely under-documented.

**Recommendation.** One line — reject a `sourceCommit` equal to the archive provenance —
converts a silent Challenge-3 failure into an immediate one.

### 10. Nothing verifies you started from the right source

This run began against commit `93887ab`, an old ancestor, because the worktree was created
from `main`. The `challenges/ch01/README.md` at that commit is a complete, well-formed brief
with Goal / Actions / Success Criteria. **Nothing in it says it is stale.** I read it and
built an entirely wrong model of the chapter. It was caught only by an out-of-band
correction; unattended, it would have run for hours and produced coherent, worthless output.

There is no preflight source-provenance check anywhere in the material. Given that two other
defects in this list concern commit provenance being recorded wrongly, a check the attendee
runs *before starting* is a conspicuous gap.

---

## Defects that block the .NET stack outright

Both were hit on the first real bootstrap deployment. Both fail loudly, which makes them
less dangerous than the section above — but the first means **Challenge 1 cannot be
completed on the .NET stack with the template as shipped**.

### A. `privatelink..database.windows.net` — the SQL private DNS zone name is malformed

`infra/modules/environment.bicep:179` built the zone name as:

```bicep
name: 'privatelink.${environment().suffixes.sqlServerHostname}'
```

`environment().suffixes.sqlServerHostname` already carries a **leading dot** —
`.database.windows.net`. The result is `privatelink..database.windows.net`, and Azure
rejects it:

```
BadRequest: The domain name 'privatelink..database.windows.net' is invalid.
```

The neighbouring storage zone at line 149 is correct, because
`environment().suffixes.storage` returns `core.windows.net` with **no** leading dot. The two
suffixes do not behave alike, and the template assumes they do.

**Why this survived review: the zone is declared `if (!isJava)`.** It exists only for the
`dotnet-sqlserver` stack. The Java/PostgreSQL path never evaluates it, so a Java track can
deploy this template end to end and report success while the .NET path is unshippable. A
green Java run is not evidence for the .NET run, and in this delivery it actively masked
the defect.

Fixed here as `'privatelink${environment().suffixes.sqlServerHostname}'`.

### B. Private DNS vnet link names collide between the two stacks

`storage-vnet` (line 155) and `sql-vnet` (line 185) were fixed string literals. The blob
zone name is also a fixed string, so **both stacks deployed into one resource group share
the same zone** — and the workshop deliberately places both legacy VMs, and therefore both
stacks, in the same `rg-user001`. The second stack to deploy fails:

```
BadRequest: Virtual network associated with the link cannot be changed.
```

Confirmed by inspection rather than inferred — the zone already carried the Java track's
link:

| Link | Virtual network |
| --- | --- |
| `migration-source-pkjpzftb` | `vnet-user001` |
| `storage-vnet` | `vnet-mh-user001-java` |

Note the first name. **The template already uniquifies the migration link on the very same
zone** (`migrationDnsLinkName`, line 63) for exactly this reason. The pattern was understood
and applied inconsistently one resource later. Fixed here by deriving a matching suffix from
the stack's own virtual network name.

---

### C. The same suffix bug also corrupts `CATALOG_DATABASE_HOST` — and this one does not fail

Defect A and this one are the *same typo* in two places, and they are worth separating because
they behave completely differently. `infra/modules/sql.bicep:84` built the server hostname the
same way:

```bicep
output serverHost string = '${server.name}.${environment().suffixes.sqlServerHostname}'
```

That output is consumed at `environment.bicep:498`, where it becomes both
`targetOutput.database.server` and the `CATALOG_DATABASE_HOST` environment variable injected
into the container app. My first bootstrap deployment **succeeded**, and emitted:

```
sql-mh-user001-dotnet-kurep3z6..database.windows.net
```

against a real server whose `fullyQualifiedDomainName` is
`sql-mh-user001-dotnet-kurep3z6.database.windows.net`. The doubled dot is not merely a wrong
name — it is not a legal name:

```
$ nslookup sql-mh-user001-dotnet-kurep3z6..database.windows.net
nslookup: '...' is not a legal name (empty label)
```

This is the most dangerous single defect I found, because of what it does *not* do:

- the deployment reports `Succeeded`;
- `evidence/azure-target-output.json` is written and is schema-valid;
- every gate in the runbook's step 5 (`deploymentStage`, `stack`, `images.provider`,
  `sourceCommit`) passes on it;
- the migration would then be pointed at a `database.resourceId` that is correct, so the
  cutover itself succeeds;
- the failure surfaces only when the container app starts and cannot resolve its database —
  in a different challenge, with a DNS error that points nowhere near a Bicep output.

An attendee would reasonably conclude their *application* code is wrong. The fix is to use the
value Azure already publishes, `server.properties.fullyQualifiedDomainName`.

Both A and C are `if (!isJava)` paths, and `postgresql.bicep:71` hardcodes its own suffix
correctly. **A completely green Java run proves nothing about either.** Anyone validating this
material on one stack will ship both.

The root cause is worth stating plainly, because it will recur:
`environment().suffixes.sqlServerHostname` returns `.database.windows.net` **with a leading
dot**, while `environment().suffixes.storage` — used correctly ten lines away — returns
`core.windows.net` **without one**. The two neighbouring, apparently parallel usages are not
parallel at all.

---

### D. `az acr build .` uploads the working tree, and the tag claims a commit it may not contain

The runbook builds the image as `catalog-dotnet:$SourceCommit` and treats that tag as
provenance: Challenge 3 checks the source out at `$SourceCommit` and rebuilds from it. But
`az acr build` tars the *working directory*, not the committed tree, and the runbook never
asks for a clean tree before step 4 — the per-task `git status --short` at line 130 belongs to
step 3 and is not repeated.

I hit this for real. My first successful image was built from a working tree that contained two
uncommitted `Dockerfile` fixes. The tag named a commit that did not, and could not, produce it.
Nothing anywhere would have caught that: the digest is immutable, the tag is well-formed, the
manifest exists, and `evidence/container-registry.json` validates. The lie only surfaces in
Challenge 3, as an unreproducible build.

I resolved it the honest way — committed and pushed the fixes, then rebuilt and re-derived the
digest so the tag genuinely corresponds to its commit. One line in the runbook
(`if (git status --porcelain) { throw }` before `az acr build`) closes it permanently.

---

### E. `catalog-migrate` cannot invoke `az` on Windows at all

`catalog_migrate/process.py:77` runs child processes with `subprocess.run(list(argv), ...)`,
`shell=False`, and sixteen call sites pass `"az"` as `argv[0]`. On Windows the Azure CLI is
installed **only** as `az.cmd`; there is no `az.exe`. Python's `subprocess` uses
`CreateProcess`, which searches `PATH` and appends `.exe` but never consults `PATHEXT`, so
`"az"` cannot be executed. Measured on the provisioned VM:

```
shutil.which("az") = C:\Program Files\Microsoft SDKs\Azure\CLI2\wbin\az.CMD
az     : OSError -> FileNotFoundError: [WinError 2] The system cannot find the file specified
az.cmd : returncode=0
az.exe : OSError -> FileNotFoundError: [WinError 2] The system cannot find the file specified
```

This is not a portability problem. It is broken on the exact platform the material mandates,
for every migration subcommand. Note that `shutil.which("az")` — already imported nowhere, but
one line away — resolves it correctly, so the fix is `shutil.which(argv[0]) or argv[0]`.

The diagnostic makes it much worse. `process.py:87` collapses every `OSError` into
`external tool could not complete: az` and discards the exception, so the attendee is told a
tool "could not complete" with no errno, no path, and no indication that the executable was
never found. I only identified it by reproducing the `subprocess` call by hand.

I worked around it by compiling a ten-line C# forwarder named `az.exe` and putting it ahead of
the real CLI on `PATH`.

---

### F. The two migration guard-rails are mutually exclusive, so the migration cannot be automated

This is the finding I would act on first, because it is structural rather than a typo.

`catalog-migrate` protects the cutover with two independent preconditions, both applied to
`export`, `import`, `images copy`, `verify` **and `render-handoff`**:

1. `azure.py:208-210` — the host's own IMDS identity must equal `migrationSourceVmResourceId`.
   IMDS is read with `trust_env=False`, so it cannot be proxied. **The migration must run on
   the source VM.**
2. `azure.py:81` — that VM's `provisioningState` must be `Succeeded`.

Individually both are sound. Together they are unsatisfiable for any non-interactive delivery,
because the only headless way onto a VM with no Bastion, no public IP and no desktop is
`az vm run-command invoke` — **and run-command puts the VM into `Updating` for the duration of
the invocation.** Measured from the laptop while a run-command slept:

```
IDLE   state: Succeeded
DURING run-command: Updating
DURING run-command (2nd sample): Updating
AFTER  run-command: Succeeded
```

So gate 1 forces the code onto the VM, and the only mechanism that can put it there trips
gate 2. Driven through run-command, `catalog-migrate` fails with
`precondition-failed: Azure resource is not provisioned` **100% of the time**, regardless of
the VM's actual health.

The material never states that an interactive desktop session on the source VM is a hard
requirement, but it is one, and this delivery has no Bastion host to provide it. I worked
around it by having run-command register a Windows scheduled task and exit, so the migration
executes while the VM is idle and genuinely `Succeeded`.

Two things follow for the authors:

- If headless operation is ever intended, gate 2 must exclude the running operation — check
  `PowerState/running`, or the VM's health, rather than `provisioningState`.
- The error text is actively misleading. `Azure resource is not provisioned` describes a VM
  that failed to deploy. The observed VM was running, healthy, and had been serving the
  workshop for hours. An attendee who trusts that message will go and investigate a VM that
  has nothing wrong with it.

---

### G. Path 1C never authenticates the isolated Azure CLI profile it depends on

`catalog_migrate/database.py:36` pins every child `az` invocation to a private profile:

```python
AZURE_CONFIG = str(Path.home() / ".azure-365")
```

and `azure_environment()` injects it into all sixteen call sites. `AZURE_CONFIG_DIR` is also
absent from `process.py`'s inherited-environment allowlist, so the caller cannot influence it.
That isolation is deliberate and reasonable.

But the Copilot runbook sets `AZURE_CONFIG_DIR` exactly **once, at line 456** — inside the
acceptance step, which runs *after* the migration (step 5, line 249) and after both
application deployments (step 6, line 382). Neither the Copilot runbook nor the manual one
ever contains an `az login` at all. The manual runbook at least sets the variable at line 123,
before it is first needed; Path 1C sets it 200 lines too late.

The failure this produces is the reason it belongs in this section rather than the loud one:

```
external tool failed: az: WARNING: Subscription '7bc68c68-...' not recognized.
ERROR: Please run 'az login' to setup account.
```

The message tells you to run `az login`. Doing so populates the **default** profile, which the
migration CLI has explicitly arranged never to read. The remedy the error recommends does not
work, and the attendee has no way to know that the tool is looking somewhere else. You must
know to run `az login` with `AZURE_CONFIG_DIR` already pointing at `~/.azure-365` — which no
attendee-facing document says.

---

### H. The Copilot path is missing the bootstrap deployment entirely

Step 5 of `solutions/ch01-copilot-modernization/dotnet/README.md` opens with:

> The bootstrap output must already exist at `evidence/azure-target-output.json`.

Nothing in that runbook ever produces it. It contains exactly two
`az deployment group create` invocations, at lines 382 and 391, and both are application-stage
(`baseline` and `release`); the only write of `azure-target-output.json` is the release one at
line 400, which the text itself describes as *replacing* the bootstrap document. There is no
bootstrap deployment anywhere on the path.

Both manual runbooks have it — `solutions/ch01-manual/dotnet/README.md:219` is the missing
block. Both Copilot-path runbooks, .NET and Java, omit it. This is a whole-path defect, not a
stack-specific one.

It is mostly a loud failure, but it has one quiet way to go wrong: an attendee blocked at step 5
will find the manual runbook's bootstrap block sitting in the same repository and adapt it —
and that block reads `C:\protected\manual-dotnet-bootstrap.json`, a *different* protected
parameter file, from a different path with a different `applicationRevisionRole`. Following the
nearest available instructions deploys the wrong slice.


### I. The migration harness decodes `sqlcmd` output with the Windows ANSI codepage, so export always fails

This one stops the .NET stack dead, on the intended VM, for every attendee, and no document
mentions it.

`catalog-migrate sql export` verifies the source database against the canonical corpus before
it exports anything. The verification compares full row *content*, not just counts
(`catalog_acceptance/database.py:741`). The rows come back from `sqlcmd` through
`CommandRunner.run`, which does this:

```python
completed = subprocess.run(list(argv), check=False, capture_output=True, text=True, ...)
```

`tests/acceptance/catalog_migrate/process.py:81`, and identically at
`catalog_acceptance/database.py:91`. **`text=True` with no `encoding=`** decodes the child's
bytes using `locale.getpreferredencoding(False)`. Measured on `vm-dotnet-user001`:

```
PY= 3.12.10
STDIO_ENC= cp1252   PREFERRED= cp1252
```

`sqlcmd -C` emits UTF-8. So every non-ASCII byte sequence is silently mojibaked. The canonical
corpus contains exactly one such character — U+2019, a curly apostrophe, in the description of
figure `83e9d76a-…` ("A steady hand in the ship's kitchen"). Its UTF-8 bytes `E2 80 99` decode
under cp1252 to `â€™`:

```
DB_FIGURES= 198  CANON= 198
DB_CATS= 20      CANON= 20
ONLY_IN_DB= 1    ONLY_IN_CANON= 1
CATS_MATCH= True
DB_CODEPOINTS=    ['0xe2', '0x20ac', '0x2122']
CANON_CODEPOINTS= ['0x2019']
```

Everything is correct — 198 figures, 20 categories, categories match exactly — and the command
still fails, with:

```
{"command": "sql export", "error": {"code": "verification-failed",
 "message": "database figure rows differ from the canonical corpus"}, "exitCode": 5}
```

That message names the right symptom and gives the attendee no way at all to reach the cause.
The counts match. The data is fine. One apostrophe, in one description, out of 198 rows, and
the only diagnostic offered is "rows differ".

**The fix requires no change to any workshop code.** Python honours UTF-8 mode as an
environment setting:

```powershell
$env:PYTHONUTF8 = '1'
```

Re-running the identical comparison with it set:

```
STDIO_ENC= utf-8   PREFERRED= utf-8
DB_FIGURES= 198  CANON= 198
ONLY_IN_DB= 0    ONLY_IN_CANON= 0
CATS_MATCH= True
```

Zero differences. This is how I unblocked the run.

Three things worth separating here:

1. **The bug is one keyword.** `encoding="utf-8"` on both `subprocess.run` calls fixes it
   permanently and cannot regress. Python 3.15 makes UTF-8 mode the default, so this defect
   has a shelf life — but the workshop pins 3.12, so today it is universal.
2. **It is stack-asymmetric, and that is why it survived review.** `psql` on the Java stack
   respects `PGCLIENTENCODING` and the Java track's canonical corpus is reached through a
   different client path. A green Java run does not exercise this at all. This is the *third*
   defect I have found in this chapter that is invisible to the Java stack (see A, B, C) —
   the pattern is now strong enough to be a process finding in its own right: **anything
   guarded only by `if (!isJava)` or reached only through the SQL Server client is
   effectively untested.**
3. **The error message is the real defect.** A verifier that compares 198×7 fields and reports
   "rows differ" is not much better than one that reports nothing. It knows exactly which row
   and which field mismatched. Printing the first differing tuple — even truncated, even
   redacted — converts a two-hour dead end into a ten-second fix. I only diagnosed it by
   importing the harness's own internals on the VM and diffing the two sets by hand, which is
   not a reasonable ask of an attendee.

**Recommended:** add `encoding="utf-8"` at both call sites; make the mismatch message include
the first differing row's identity and field name; and until then, put `PYTHONUTF8=1` in both
.NET runbooks next to the `AZURE_CONFIG_DIR` export.

### J. The verifier compares row *content*, and that is the only reason a corrupted `product_id` did not migrate

This is the counter-example to almost everything else in this document, and it deserves to be
recorded as a success rather than a defect — but it also exposes how narrow the margin was.

While diagnosing I, I ran the same comparison through `catalog_acceptance`'s *default*
executor rather than the migration runner. That executor passes `env=environment` where
`environment` is only `{"SQLCMDPASSWORD": …}` — so the child gets no `USERPROFILE`. Under that
environment `go-sqlcmd` writes a diagnostic **to standard output**, not standard error:

```
Error getting user's home directory: %userprofile% is not defined, will use current
directory "C:\MicroHack\source\tests\acceptance" as default
```

`_parse_rows` (`catalog_acceptance/database.py:108`) splits stdout on newlines and tabs. The
banner has no tab, so it does not change the column count — instead it is glued onto the front
of the first data row's first column. The resulting figure identity was:

```
Error getting user's home directory: %userprofile% is not defined, will use current
directory "C:\MicroHack\source\tests\acceptance" as default17d84a22-2f5e-4097-82dd-0066a23c84ff
```

A tool's error message became a primary key.

The row count was still exactly 198. The category count was still exactly 20. **Every
count-based check passes on this data.** If the verifier had compared `SELECT COUNT(*)` — which
is what most people write, and what the runbook's own success criterion ("198 figures, 20
categories, 198 images") invites you to check by hand — this would have exported clean,
imported clean, and put a corrupted identity into Azure SQL, where it would surface much later
as a 404 on one figure and nothing else.

It was caught only because `verify_database_connection` compares the full seven-field tuple of
all 198 rows. That is good engineering and it should be called out as such in the material,
because right now the design is invisible: the runbook presents the row counts as the success
criterion, which teaches exactly the weaker check that would have missed this.

Two follow-ups regardless:

- `catalog_acceptance/database.py:80-105` should pass through `USERPROFILE` the way
  `catalog_migrate/process.py:25-44` already does — the migration runner allowlists it, the
  acceptance runner does not, and they are used against the same client.
- `_parse_rows` should reject or skip lines that do not have exactly `width` tab-separated
  fields *before* treating them as data, rather than relying on the column count of a
  concatenated line coincidentally matching.

**Why this one matters most.** Every other finding in this document is a thing that broke.
This is a thing that *nearly didn't* — a corrupted database that satisfies every documented
success criterion. It is the cleanest illustration in the whole delivery of the difference
between checking that the numbers look right and checking that the data is right, and the
workshop currently teaches the first while its harness quietly does the second.

### K. `sqlcmd` reports T-SQL errors on stdout with exit code 0, and the harness parses them as rows

Immediately behind the encoding defect sits a second deterministic blocker, and it is a
sharper instance of the same underlying mistake.

Once the corpus comparison passed, export failed with:

```
{"command": "sql export", "error": {"code": "verification-failed",
 "message": "database client returned an unexpected row shape"}, "exitCode": 5}
```

I isolated it by running each verification query individually on the VM:

```
_table_names:     OK n=3
_schema_rows:     OK n=10
_constraint_rows: OK n=7
_index_rows:      OK n=6
_migration_rows:  OK n=1
_tls_detail:      FAIL ValueError: database client returned an unexpected row shape
```

`_tls_detail` (`catalog_acceptance/database.py:635-653`) queries
`sys.dm_exec_connections`, which requires `VIEW SERVER STATE`. The seeded `catalog` login
does not have it. The raw response:

```
Msg 300, Level 14, State 1, Server dotnet-u001\SQLEXPRESS, Line 1
VIEW SERVER PERFORMANCE STATE permission was denied on object 'server', database 'master'.
Msg 297, Level 16, State 1, Server dotnet-u001\SQLEXPRESS, Line 1
The user does not have permission to perform this action.
```

Two separable defects.

**K1 — the seed grants the wrong permissions.** The provisioning that creates the `catalog`
login gives it enough to read the catalog tables but not enough to satisfy a check the export
performs unconditionally. Nothing in the material mentions `VIEW SERVER STATE`. Every attendee
on the .NET stack hits this, on the intended VM, at the same step. I unblocked it with:

```sql
GRANT VIEW SERVER STATE TO [catalog];
```

issued as `NT AUTHORITY\SYSTEM`, which is `sysadmin` on this Express instance. That is a
permission grant only — it touches no catalog data and cannot affect the migrated corpus.

**K2 — and this is the one that matters — `sqlcmd` exited 0.** Neither `_run_client`
(`check=True`) nor `CommandRunner.run` (`returncode != 0`) raised, because `go-sqlcmd` does not
set a non-zero exit code for T-SQL errors unless `-b` is passed, and the connection built at
`catalog_acceptance/database.py:325-337` does not pass it:

```python
connection = ["sqlcmd", "-S", server, "-d", database, "-U", username, "-h", "-1", "-W", "-C"]
```

So a *server error message* was returned to the caller as if it were a successful result set,
and `_parse_rows` treated those four lines as candidate data rows. It rejected them only
because none of them happened to contain exactly one tab.

That is luck, not a check. `_parse_rows` accepts any line whose tab-separated field count
matches the expected width. A T-SQL error whose text happens to split into the right number of
fields is indistinguishable from data. This is the identical mechanism to finding J — where
`go-sqlcmd`'s missing-`%USERPROFILE%` banner was glued onto a `product_id` — arriving through a
different door. Twice in one command path, tool output that is not data was consumed as data.

**Recommended:** add `-b` to the sqlcmd argument vector so T-SQL errors become non-zero exits
and surface as `ToolError` with the server's own message, which would have made both K and J
diagnose themselves in one line. Add `VIEW SERVER STATE` to the seed grants, or drop the TLS
check for `target == "source"` where it is not asserted on anyway (`_tls_detail` only enforces
encryption when `target == "managed"`, so for the source database it is a pure read whose
result is discarded into a display string). And treat "the client's diagnostics land in the
same stream as its data" as a systemic property of this harness rather than three separate
bugs — every `_parse_rows` call site inherits it.

### L. The SQL logical server has no managed identity, so the import always fails *after* it has already imported the data

This is the most consequential finding in the chapter, and its failure mode is the worst kind:
the command reports failure after it has already made an irreversible change, and the state it
leaves behind cannot be recovered by re-running it.

`catalog-migrate sql import` does two things in sequence. First it runs SqlPackage to import the
bacpac. Then it grants the application's managed identity access
(`tests/acceptance/catalog_migrate/database.py:551-580`):

```sql
CREATE USER [id-mh-user001-dotnet] FROM EXTERNAL PROVIDER
  WITH OBJECT_ID='92355f34-9b47-461c-afe8-bfa26c020bb1';
ALTER ROLE db_datareader ADD MEMBER [id-mh-user001-dotnet];
ALTER ROLE db_datawriter ADD MEMBER [id-mh-user001-dotnet];
```

`FROM EXTERNAL PROVIDER` makes the logical server resolve the principal against Microsoft Entra.
That requires the server to have a managed identity, and that identity to hold the Entra
**Directory Readers** role. `infra/modules/sql.bicep` has no `identity:` block at all — the
server is created without one:

```
{"command": "sql import", "error": {"code": "tool-failed", "message":
 "external tool failed: sqlcmd: Msg 33134 … Principal '92355f34-…' could not be resolved.
  Error message: 'Server identity is not configured. …'"}, "exitCode": 4}
```

I assigned a system-assigned identity to the server myself (`262348b2-…`) and the error moved on
to the second half of the prerequisite:

```
Msg 37353, Level 16, State 1
Server identity does not have the Microsoft Entra Directory Readers permission.
```

Granting Directory Readers needs Privileged Role Administrator. The delivery account holds
Global Reader, so:

```
Authorization_RequestDenied: Insufficient privileges to complete the operation.
```

**Neither half of the prerequisite is created by the template, and neither is mentioned in any
document.** The template threads `workloadIdentityName` and `workloadIdentityPrincipalId`
through three module boundaries (`sql.bicep:6-7`) purely to echo them into
`output applicationPrincipal` — the value the import later tries, and fails, to turn into a real
grant.

**Why the failure mode is the dangerous part.** SqlPackage runs first and succeeds. I confirmed
from the VM, after the command reported `exitCode: 4`:

```
sys.tables      → __EFMigrationsHistory, Categories, Figures
COUNT(*) Figures    → 198
COUNT(*) Categories → 20
```

The migration is *done*. All 198 figures and 20 categories are in Azure SQL. The tool says it
failed. And the command is not idempotent — re-running it now aborts on its own
not-empty precondition, so the documented recovery ("fix the error, run it again") cannot work.
An attendee is left with a populated target database, a red exit code, no
`evidence/migration-report.json`, and no instruction that covers the state they are actually in.
The plausible response — dropping and recreating the database to get a clean run — destroys a
correct migration to chase an error in a step that has nothing to do with the data.

**The workaround, and why it is worth recording.** A contained user for a managed identity does
not need a directory lookup if you supply the SID yourself. The SID is the identity's *client*
ID in little-endian GUID byte order — `2b4a56de-7d44-4725-921f-0b0a26b8be17` becomes
`0xDE564A2B447D2547921F0B0A26B8BE17`:

```sql
CREATE USER [id-mh-user001-dotnet] WITH SID = 0xDE564A2B447D2547921F0B0A26B8BE17, TYPE = E;
ALTER ROLE db_datareader ADD MEMBER [id-mh-user001-dotnet];
ALTER ROLE db_datawriter ADD MEMBER [id-mh-user001-dotnet];
```

Verified afterwards:

```
id-mh-user001-dotnet  db_datareader
id-mh-user001-dotnet  db_datawriter
```

That is byte-for-byte the end state the tool intends, reached without Directory Readers and
without any elevated Entra role. **The template should use this form**, or the tool should fall
back to it — it removes an entire class of tenant-permission dependency from the workshop, and
the client ID is already in `targetOutput.workloadIdentity.clientId`.

**A second, separate access gap.** The migration must run on `vm-dotnet-user001` (finding F), so
it authenticates as *that* VM's managed identity — which is also not a database principal, and
which the template also never grants. `sql.bicep:15-22` configures exactly one Entra
administrator, `principalType: 'User'`, the facilitator, with `azureADOnlyAuthentication: true`
so there is no password fallback. Azure SQL permits one administrator, so making the VM identity
usable means **displacing** the facilitator:

```bash
az sql server ad-admin update -g rg-user001 -s sql-mh-user001-dotnet-kurep3z6 \
  --display-name vm-dotnet-user001 --object-id 8cc6db41-36da-4d9c-8134-2b5e70284db6
```

I did that, completed the migration, and restored the original administrator afterwards. It is a
destructive workaround for a missing grant and no attendee should be improvising it.

**Stack asymmetry, again.** `postgresql.bicep` has the same missing workload-identity grant, but
it also emits `localAdministratorPrincipal` with password authentication and takes
`authentication` as a parameter, so the Java stack retains a credential path that does not depend
on any of this. `sql.bicep:89` hardcodes `output authentication string = 'managed-identity'` and
line 21 disables password auth outright. The .NET stack has no fallback at all. Counting A, B,
C, I and L, that is five defects in this chapter that a green Java run cannot see.

**Recommended:** assign a system-assigned identity to the SQL server in `sql.bicep`; switch the
tool's `CREATE USER` to the `WITH SID … TYPE = E` form so Directory Readers is never needed;
create a principal for the migration identity rather than requiring the single admin slot to be
hijacked; and — independent of all of the above — **split the import into two commands, or make
the principal grant idempotent and re-runnable**, so that a failure in the grant step cannot
strand a successful data import behind a non-idempotent precondition.

---

### M. The migration's storage grant is made to a principal that the migration cannot run as

`catalog-migrate images copy` failed with:

```
external tool failed: az: ERROR: You do not have the required permissions needed to perform this
operation. Depending on your operation, you may need to be assigned one of the following roles:
"Storage Blob Data Owner" "Storage Blob Data Contributor" "Storage Blob Data Reader" ...
```

The template is not careless here — it anticipates this exactly. `environment.bicep:373-381`
declares a role assignment literally named `facilitatorBlobMigration`:

```bicep
resource facilitatorBlobMigration 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (isBlob) {
  scope: blobContainer
  properties: {
    principalId: facilitatorPrincipalObjectId
    principalType: 'User'
    roleDefinitionId: blobDataContributorRole
  }
}
```

Data-plane write access on the image container, granted to a **`principalType: 'User'`**, purely so
the migration can run. The application's own identity gets only `blobDataReaderRole`
(`:363-371`) — correctly, since it only reads. The separation is deliberate and right.

**The problem is that finding F makes that principal unusable.** `validate_migration_topology`
requires the migration to execute *on* `vm-dotnet-user001`, verified through IMDS with
`trust_env=False`. On that VM, in a delivery with no Bastion and no desktop, the only non-interactive
credential available is `az login --identity` — the VM's own system-assigned managed identity. And
the template grants that identity nothing.

So the two constraints are individually reasonable and jointly unsatisfiable:

| Constraint | Source | Requires |
| --- | --- | --- |
| Must run on the source VM | `catalog_migrate/azure.py:208-210` | IMDS host identity match |
| Must have blob data-plane write | `environment.bicep:373` | the *facilitator user* principal |

The only way to satisfy both simultaneously is an **interactive** `az login` on the VM desktop as the
facilitator user — which is precisely the capability this delivery does not have, and which
`challenges/ch01/README.md` never identifies as load-bearing. It reads as a convenience ("you'll be
signed in already"), not as the sole route through a hard gate.

**And `sql.bicep` makes the identical assumption.** Its single Entra administrator is
`principalType: 'User'`, the same facilitator object ID. Findings L and M are therefore one design
decision seen twice: **the migration is designed to be performed by a signed-in human on the VM
desktop.** Remove the desktop and the entire migration identity model collapses — both stores, both
independently.

**Why this costs so much time to diagnose.** The VM's managed identity is **Owner on
`rg-user001`**, so the natural conclusion — "the identity is Owner, it can do anything" — is wrong
in the most expensive possible way. Owner carries `Microsoft.Storage/storageAccounts/*` at the
control plane and **no blob data-plane permission at all**; Azure's data-plane RBAC is a disjoint
role set. Every control-plane probe you run while diagnosing succeeds. `az storage account show`
works. `az storage container list --auth-mode key` works. Only the specific data-plane call fails,
and the error names six roles without saying which principal lacks them or on which resource.

**Workaround:**

```bash
az role assignment create --assignee-object-id <vm-mi-principal-id> \
  --assignee-principal-type ServicePrincipal --role "Storage Blob Data Contributor" \
  --scope /subscriptions/…/storageAccounts/stuser001dotnekurep3z6
```

That requires **User Access Administrator or Owner at the scope** — a right the facilitator has
already established attendees do not hold (it is why the Challenge 2 prerequisites had to be
facilitator-deployed). The workaround for the missing grant needs the same elevated permission the
workshop assumes is unavailable. An attendee hitting this alone is stopped.

**Recommendation.** `migrationSourceVmResourceId` is already a required parameter, so the VM's
managed identity principal is derivable at deploy time with a single `existing` reference. Grant
**that** principal Storage Blob Data Contributor alongside the facilitator user, and add it as a
database principal alongside the Entra admin. It costs four lines, removes the desktop dependency
from the migration entirely, and makes `az login --identity` a complete answer rather than a
partial one.

---

## Defects that fail loudly (lower value, but real)

- **Toolchain host pins are unreachable.** `workshop/toolchain.lock.json` pins SDK
  `10.0.400` / runtime `10.0.11`. Neither exists; the highest published .NET 10 SDK is
  `10.0.101`. Only the container digests are still obtainable.
- **The entire migration is IMDS-gated to the source VM.**
  `tests/acceptance/catalog_migrate/azure.py:42-56` reads IMDS with `trust_env=False` and
  requires host identity to equal `migrationSourceVmResourceId`. This gates `export`,
  `import`, `images copy`, `verify` **and `render-handoff`** (`cli.py` lines 160, 179, 205,
  259, 283). It is documented behaviour, not a defect — but it means no part of Challenge 1
  after the code work can be executed off the VM, including producing
  `evidence/modernization-contract.json`. Any delivery model that assumes otherwise is
  wrong for this chapter specifically.
- **`az vm run-command` mangles quoting.** Every runbook block is written for an interactive
  shell this delivery cannot obtain, and there is no `RunShellScript` on Windows. Reliable
  invocation requires base64-encoding the script and decoding it in-guest. This is a
  material-rewrite-sized issue for any non-desktop delivery, not a workaround.
- **`Conflict: Run command extension execution is in progress`** is usually transient
  serialization between consecutive invocations and clears on retry. A genuine wedge is
  different: it persisted ~55 minutes and was cleared only by `az vm deallocate` +
  `az vm start`. `az vm extension delete` hangs on the same wedge it is meant to clear, and
  `az vm restart` makes it worse by re-triggering the CSE.
- **Public IP allocation is denied subscription-wide**, so the frozen
  `internal: false` in `infra/modules/environment.bicep:423` fails deployment outright with
  `SubscriptionNotRegisteredForFeature … AllowBringYourOwnPublicIpAddress`. Patched here
  with an opt-in `containerAppsEnvironmentInternal` parameter defaulting to `false`, leaving
  the frozen template unchanged for a normal subscription. Consequence: with the internal
  environment, `applicationUrl` is VNet-private, so a laptop `curl` timeout is **not** a
  deployment failure — recording it as one would manufacture a false negative.
- **`az resource list -g rg-user001` returned `[]`** while Resource Graph returned 12
  resources in the same group. Graph is authoritative. An attendee trusting the empty list
  would conclude their environment was never provisioned.
- **No Bastion host exists** in this delivery, so the documented access route for the whole
  chapter is absent; and **`workshop/golden/dotnet-sqlserver/` is empty**, so the documented
  15:15 rejoin path does not exist either. A blocked participant has no fallback.

---

## What is well designed, and worth protecting

The contrast here is sharp and instructive.

**`evidence/runtime-test-report.json` is genuinely unforgeable.** The schema requires exactly
14 tests; the `id` values are a fixed enum; each id is pinned to an exact `testIdentity`
through a canonical map in `tests/acceptance/catalog_acceptance/handoff.py:20-75`; and
`handoff.py:211-228` **re-parses the TRX** and rejects the handoff unless every one of those
identities is present with outcome `passed`. You cannot hand-write it, and you cannot pass it
without actually having run the tests.

That is what a good evidence artifact looks like, and the workshop already contains one. The
gap is not that the authors don't know how — it is that the path-specific evidence for
Path 1C was never held to the same standard as the shared evidence.

**Recommendation.** Apply the `runtime-test-report.json` design to at least
`task-results.json` — a schema, plus one machine-checkable field (for example, the commit
SHA each task's validation actually ran against) would move it from "prose anyone can write"
to "claim that can be contradicted".

---

## Summary recommendation

If only one change is made to Challenge 1, publish the environment-variable contract in the
challenge README. It is the difference between a modernization that works and one that
merely deploys — and today, nothing in the attendee-facing material lets you tell those two
outcomes apart.
