# Implementation log

## 2026-09-29 - Large-screen timer canvas

- Add a project-scoped **Timer** Copilot canvas with an intentionally minimal full-screen
  layout for workshop rooms, presentations, and other big-screen countdowns.
- Use a shrinking circular orbit as the primary remaining-time indicator, with responsive
  tabular digits, restrained controls, visible focus states, and reduced-motion support.
- Keep countdown time authoritative in the extension process so stopping, resuming, iframe
  polling, and multiple views of the same timer remain synchronized.
- Support setting hours, minutes, and seconds in the canvas, plus Start, Stop, Reset,
  `Space` start/stop, and `R` reset controls.
- Expose matching agent actions for reading state, setting duration, starting, stopping,
  and resetting the timer without adding package dependencies.
- Render the large countdown with the app's tabular monospaced font, including its
  distinctive slashed-zero convention.
- Bound countdown typography by both viewport width and height, with a 10 rem ceiling, so
  maximized wide-screen panels retain the balanced spacing of the normal panel view.
- Add an **End at** mode that accepts a future local time today, calculates the exact
  countdown duration in the extension process, starts immediately, and rejects past times
  rather than silently rolling them into tomorrow.
- Show the calculated end time in the running status and expose the same behavior through
  the `set_end_time` canvas action.
- Add an accessible **Duration** / **End at** segmented switch so only the selected timer
  entry method is visible, preserving the canvas's minimal control layout.
- Apply a smaller responsive type scale whenever hours are visible so `HH:MM:SS` remains
  fully contained by the orbit while the shorter `MM:SS` display stays prominent.

## 2026-09-28 - Azure workshop infrastructure dashboard

- Add a project-scoped Copilot canvas for facilitator deployment reporting across all
  enabled subscriptions available through the isolated `$HOME/.azure-hack` Azure CLI
  profile.
- Inventory only deployed workshop `rg-labuser-NNNN` resource groups and their virtual machines, with a
  target of 35 environments and exactly two VMs per environment.
- Query subscriptions with bounded concurrency, retain partial results when an individual
  subscription fails, and expose manual refresh through both the dashboard and a canvas
  action.
- Add summary progress, readiness and issue counts, filtering, and clickable
  subscription → resource group → VM drill-down without introducing package dependencies.
- Probe the hosted application inside every VM with bounded Azure Run Command concurrency:
  .NET on port 5000 and Java on port 8080, including root, liveness, and readiness checks.
  Display failed application probes as warnings separate from infrastructure completeness.
- Publish live refresh progress after both application checks for each environment finish,
  and poll that state in the canvas so the user sees `x / 35 environments checked`.

## 2026-09-24 - template-aligned workshop layout

- Flatten challenge guides to `challenges/<challenge>.md`, with the two ch01-A stack
  variants at `challenges/ch01-A-dotnet.md` and `challenges/ch01-A-java.md`.
- Rename `solutions/` to `walkthrough/` without flattening the solution artifact folders
  or changing the other top-level folder layout. Update navigation, screenshots, and
  relative links for the new locations.
- Accept both flat and legacy ch01 challenge layouts in facilitator and VM source-archive
  checks so previously pinned workshop commits continue to provision. Re-pin the source
  archive to publish the new layout on VMs.

## 2026-09-23 - ch00 VM navigation

- Replace the dense VM connection bullet with a numbered participant walkthrough that
  preserves the JIT-only access requirement and the Defender for Cloud fallback.
- Add four annotated screenshots for opening the VM connection page, requesting JIT
  access, confirming port 3389 is available, and opening the catalog on `localhost`.
- Give the selected screenshots stable `ch00-*` filenames and explain that the pictured
  .NET VM is representative of both stack paths.
- After review, use the supplied `17.57.51` screenshot in the first image slot and move
  the former first VM Connect screenshot to the final image slot without reordering the
  surrounding steps.

## 2026-09-23 - ch01-A participant guidance

- Add a stack-specific Step 0 to both ch01-A variants so participants first use Copilot
  Chat to understand the application, its entry point, configuration, data access, and
  tests before making modernization changes.
- Use Copilot Chat directly for the required framework upgrade. Move the GitHub Copilot
  app modernization extension to an explicitly post-challenge bonus comparison so it is
  not used to complete the core exercise.
- Add copy-and-paste local database environment variables to both variants and explain how
  they map the application to the database container. The Java container now creates the
  same database and user named in the application variables.
- Make both Step 2 Copilot prompts continue beyond Bicep authoring: confirm the Azure
  target, validate and preview the template, deploy it, verify the deployment, and return
  the application connection details without exposing secrets.
- Add a three-screen Codespaces walkthrough covering the repository **Code** button,
  creating a codespace, and resuming one. The repository screenshot is captured from the
  public workshop repository; the creation and resume screenshots come from GitHub Docs
  under CC BY 4.0 with attribution in both challenge guides.

## 2026-09-09 - ch01-A Java walkthrough

- Follow the six steps in `walkthrough/ch01-A/java.md`; leave ch00 VMs and the legacy
  root `java/` application untouched. Store modernized application overlays and Bicep
  under `walkthrough/ch01-A/java/`, matching the existing .NET solution convention.
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
