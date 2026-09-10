# Implementation log

## 2026-09-09 - ch01-A Java walkthrough

- Follow the six steps in `solutions/ch01-A/java.md`; leave ch00 VMs and the legacy
  root `java/` application untouched. Store modernized application overlays and Bicep
  under `solutions/ch01-A/java/`, matching the existing .NET solution convention.
- Use the existing `rg-user001` and its Sweden Central location through the supplied
  Azure CLI profile. Java-specific names avoid modifying the pre-existing .NET deployment.
- Split Bicep into database, registry/identity, environment/storage, and application
  modules, coordinated by one incrementally deployed `main.bicep`.
- Stage deployment so the database can be exercised locally first; create the ACR
  identity before image pull, and populate Azure Files before starting the Container App.
- Follow the workshop's temporary public PostgreSQL networking and password-auth
  approach, enforce TLS, use secure parameters and Container Apps secret references,
  and mount seed/images read-only. Private networking remains ch07 scope.
- Complete the real Java 21 / Spring Boot 4.0.8 upgrade (no fallback), including
  Jackson 3 and modular Boot test/Flyway support. The source and container versions
  retain the catalog behavior and unchanged migration.
- Restore the baseline suite's missing, historical JSON fixtures into the isolated
  working copy, not into the legacy application. All 34 existing tests pass there.
- Run the upgraded Maven application locally against the managed PostgreSQL 16.15
  database: import 198 figures / 20 categories and observe TLS 1.3 connections.
- Preserve the required OTLP endpoint setting even with SDK export disabled; the
  application validates it before initializing telemetry.
- Remove the Dockerfile's BuildKit-only Maven cache mount after the actual ACR
  quick build rejects `RUN --mount`. Keep an ordinary multi-stage Dockerfile so the
  solution's unmodified `az acr build` command works with the default remote builder.
- ACR build `dt2` succeeded with image digest
  `sha256:c6778c0016f882dae499c142b438d1b8597f643597bd7ed6b513d6c84da8e789`.
  Populate both Azure Files shares before deploying the application; 198 images
  and the seed JSON are present.
- Deploy `ca-legocatalog-java` with a user-assigned `AcrPull` identity, no registry
  administrator credentials, 1 CPU / 2 GiB, TLS database access, HTTPS ingress,
  separate read-only seed/image mounts, and HTTP scaling from 0 to 3.
- At 21:26 UTC the Azure catalog returns all 198 canonical IDs and 20 categories.
  Name search, category slug and display-name filters, figure detail, byte-identical
  photograph, liveness, and database/import readiness all pass. PostgreSQL retains
  198 figures / 20 categories, with the app's ten connections using TLS 1.3.
- Stop the four task-created local containers after completing the local checkpoints.
  Do not stop or delete Azure resources. The existing .NET revision remains
  `ca-legocatalog--fg1cukg`; the root legacy sources and base infrastructure are unchanged.
  Final VM inventory reports both VMs deallocated; this walkthrough issued no VM
  lifecycle operations.
- Observe revision `ca-legocatalog-java--qefwk6g` reach **zero replicas at
  21:33:32 UTC**, without HTTP polling or forcing replica settings. Confirm zero
  again after ten seconds. The next readiness request returns **HTTP 200 in
  29.74 seconds**, starts a new replica, and the catalog still contains 198 figures.
  All ch01-A Java exit criteria are met.

Deployment at the end of the walkthrough:
<https://ca-legocatalog-java.thankfulbeach-450e34e1.swedencentral.azurecontainerapps.io>.
