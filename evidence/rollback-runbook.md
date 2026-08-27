# Rollback runbook — LEGO catalog (.NET / Azure SQL)

Restores the previous container revision without redeploying or rebuilding. The
rollback target is an existing, retained revision, so recovery is a traffic shift
and needs no image build, no migration, and no template deployment.

## Release identity

| Field | Value |
| --- | --- |
| Subscription | `7bc68c68-f434-49ad-ab3e-b883ec39da86` |
| Resource group | `rg-user001` |
| Container app | `ca-mh-user001-dotnet` |
| Current (release) revision | `ca-mh-user001-dotnet--release-47acf263d332` |
| Rollback (baseline) revision | `ca-mh-user001-dotnet--baseline-47acf263d332` |
| Source commit | `47acf263d3320fa3bb41d5469fc3c7428a393fca` |
| Image digest | `sha256:647e2500591da30fcedc831ea787ed682aa7b5bd4389fbebdd041f034fe089ee` |
| Application URL | `https://ca-mh-user001-dotnet.gentlemushroom-0b2a9e18.swedencentral.azurecontainerapps.io` |

Both revisions run the **same image digest**. The baseline revision differs only in
its deployment stage configuration, so a rollback changes serving configuration, not
application code.

## Reachability precondition

The Container Apps environment is internal (`containerAppsEnvironmentInternal=true`),
so the application URL resolves only inside the peered virtual network. Every probe
below must run from `vm-dotnet-user001`, not from a workstation. A timeout from
outside the VNet is a name-resolution result, not a rollback failure — treat it as
inconclusive and re-probe from the VM.

## Trigger conditions

Roll back when any of the following holds after a release:

- `/readyz` does not return `{"status":"ready"}` within 5 minutes of the revision
  reaching `Running`.
- `/healthz` returns a non-200 status on three consecutive probes 30 seconds apart.
- The catalog root page returns fewer than the 198 verified figures, or images fail
  to resolve from blob storage.
- Request failure rate in Application Insights exceeds the pre-release baseline for
  10 minutes.

Do **not** roll back for symptoms explained by database credential or network
topology changes — a rollback re-runs the same image and will not fix them.

## Procedure

1. Confirm the rollback target still exists and is healthy.

   ```powershell
   az containerapp revision show `
     --resource-group rg-user001 `
     --name ca-mh-user001-dotnet `
     --revision ca-mh-user001-dotnet--baseline-47acf263d332 `
     --query "{name:name, active:properties.active, health:properties.healthState, image:properties.template.containers[0].image}"
   ```

   `az containerapp revision list` hides inactive revisions unless `--all` is passed;
   query the revision by name so the result does not depend on that flag.

2. Activate the rollback revision.

   ```powershell
   az containerapp revision activate `
     --resource-group rg-user001 `
     --name ca-mh-user001-dotnet `
     --revision ca-mh-user001-dotnet--baseline-47acf263d332
   ```

3. Shift all traffic to it.

   ```powershell
   az containerapp ingress traffic set `
     --resource-group rg-user001 `
     --name ca-mh-user001-dotnet `
     --revision-weight ca-mh-user001-dotnet--baseline-47acf263d332=100
   ```

4. Verify from inside the VNet, on `vm-dotnet-user001`:

   ```powershell
   $base = 'https://ca-mh-user001-dotnet.gentlemushroom-0b2a9e18.swedencentral.azurecontainerapps.io'
   Invoke-WebRequest "$base/healthz" -UseBasicParsing | Select-Object -ExpandProperty Content
   Invoke-WebRequest "$base/readyz"  -UseBasicParsing | Select-Object -ExpandProperty Content
   ```

   Require `/readyz` to return `{"status":"ready", ...}`. Container status is not a
   substitute: a container can report healthy while readiness returns 503.

5. Confirm the serving revision.

   ```powershell
   az containerapp ingress traffic show `
     --resource-group rg-user001 --name ca-mh-user001-dotnet
   ```

## Data considerations

The rollback does **not** touch Azure SQL or blob storage. The migrated corpus — 198
figures, 20 categories, 198 images — is shared by both revisions. No schema change
was introduced between them, so no data rollback is required or safe to attempt.

## Return to the release revision

```powershell
az containerapp ingress traffic set `
  --resource-group rg-user001 `
  --name ca-mh-user001-dotnet `
  --revision-weight ca-mh-user001-dotnet--release-47acf263d332=100
```

Re-run step 4 afterwards.

## Known constraint

Container Apps revision suffixes are immutable and derived from the first 12
characters of the source commit. A failed revision keeps its suffix, so redeploying a
corrected image at the same commit fails with "revision with suffix … already
exists". Recovery from that state requires deleting the container app, which is a
redeployment, not a rollback — another reason to prefer the traffic shift above.
