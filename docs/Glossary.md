# Glossary

Terms used across the challenges, in alphabetical order. Every definition describes how
*this workshop* uses the word, which is not always the broadest possible meaning.

If a term below appears in a chapter you are working on, read this entry first — most
"I don't understand what it's asking for" moments are vocabulary, not difficulty.

---

**ACR (Azure Container Registry)**
The private registry that holds your container images. The workshop uses the **Basic**
tier, one registry per participant. Container Apps pulls from it by digest, not by tag.

**Agent unit**
The billing unit of the Azure SRE Agent. Each agent in this workshop runs at a fixed
capacity of **four agent units, charged hourly for as long as the agent resource exists**.
Stopping the agent does not stop the charge; only deleting the resource does.

**Application Insights**
The application-performance side of Azure Monitor: request rates, dependency calls,
failures, and traces from your container app. In this workshop it is *workspace-based*,
so its data lands in a Log Analytics workspace and is billed through that workspace's
ingestion meter.

**Baseline**
The measurement you take in Challenge 0, *before* you change anything: the legacy app's
row counts, `/healthz` and `/readyz` responses, canonical image, and the `198/20/198`
corpus check. Every later "did it get better?" claim is measured against this number, so
a missing baseline makes the wrap-up scorecard unanswerable.

**Bicep**
Microsoft's domain-specific language for Azure Resource Manager templates. The workshop's
Azure target (`infra/`) is written in Bicep. You deploy it; you do not usually edit it.

**Container Apps environment**
The shared boundary that container apps live inside: it owns the virtual network
integration, the ingress, and the Log Analytics workspace all its apps log to. One
environment can host several apps; in this workshop it hosts your catalog.

**Defender for Cloud plan**
A per-service, subscription-wide, **paid** switch in Microsoft Defender for Cloud — for
example *Defender for Servers*, *Defender for Containers*, or *Defender CSPM*. Turning
one on changes the bill and the security posture for everyone in the subscription, which
is why participants never enable a plan themselves. The facilitator enables them ahead of
the workshop; you get `Security Reader` and investigate what they found.

**Digest / SHA-256 pin**
Identifying a container image by its immutable content hash
(`myregistry.azurecr.io/catalog@sha256:abc123…`) instead of a mutable tag like `:latest`.
A tag can be repointed at different content; a digest cannot. Every deployment in this
workshop is pinned by digest so that "which build is running?" always has one answer.

**Drill revision**
The deliberately broken revision at the centre of Challenge 6: a copy of your working
revision, created at **zero traffic** before the incident window, reusing the same image
and secrets, with only the database hostname pointed at `.sre-drill.invalid` and the
readiness probe routed to `/healthz` instead of `/readyz`. The platform therefore believes
it is healthy and keeps sending it traffic while every request fails. No secret is exposed
and no real database is touched.

**Evidence**
A JSON file under `evidence/` that records what you actually observed, produced by
running commands rather than by writing prose. Chapters read each other's evidence instead
of rediscovering resources in the portal. Never hand-edit or fabricate an evidence file —
the validators are designed to catch it, and the whole chain of later chapters depends on
it being true.

**Fail-closed**
A check that treats "I could not tell" as failure rather than success. The workshop's
validators and `jq` assertions are fail-closed: a missing field, an empty array, or an
unexpected status is an error, not a shrug. This is deliberate — a green result you cannot
trust is worse than a red one.

**Golden handoff**
A prevalidated `evidence/modernization-contract.json` for a given stack, produced by the
facilitator in advance. If your Challenge 1 path runs out of time, the facilitator hands
you the golden handoff for your stack so you can rejoin the group at Challenge 2. It is a
rejoin mechanism, not a shortcut to be taken pre-emptively — and it is the *only*
legitimate way to obtain a handoff you did not build.

**Handoff contract**
The agreement between Challenge 1 and everything after it: a fixed JSON schema that names
your Azure resources, image digest, database, and telemetry. Once it validates, later
chapters read the file and stop caring how you got there — which is precisely why all six
Challenge 1 stack/path combinations converge on it.

**KQL (Kusto Query Language)**
The query language for Log Analytics and Application Insights. Challenge 4 gives you five
frozen KQL queries; you prove they return the expected shape against your own telemetry.

**Log Analytics workspace**
The store that holds your logs and metrics. It is billed by **gigabytes ingested**, not by
uptime, so a chatty application costs more than an idle one regardless of how long it
runs.

**Managed identity**
An Azure identity attached to a resource so that the resource can authenticate to other
Azure services **without a secret in configuration**. *System-assigned* identities live and
die with their resource; *user-assigned* identities are standalone and can be shared. This
is what replaces the connection-string password you find in the legacy application.

**`modernization-contract.json`**
The concrete file that carries the handoff contract, written to `evidence/` at the end of
Challenge 1 and validated by the shared handoff validator. If this file does not validate,
Challenges 2 through 6 have nothing to read.

**MTTR (mean time to recovery)**
How long it takes to get back to a working state after a failure. Challenge 6 measures a
real one: from the alert firing on the drill revision to traffic being back on the healthy
revision.

**OIDC (OpenID Connect)**
The way the GitHub Actions workflow in Challenge 3 authenticates to Azure: GitHub presents
a short-lived token, Azure validates it against a *federated credential* registered on a
managed identity, and no client secret is ever stored in the repository.

**Pipeline lead time**
How long a release takes from the moment the pipeline is dispatched to the moment the new
revision serves traffic — *dispatch to live*. It is deliberately not measured from the
commit: this workshop never observes how long a change waited before somebody dispatched
it, so a commit-anchored figure would claim an interval it did not record. In the wrap-up
you put it next to the legacy release you counted in Challenge 0 — its `manualDeploySteps`
and the out-of-hours window they needed — against the Challenge 3 number, which is one
pipeline run plus one approval. Older notes may call this *deployment lead time*.

**RDP (Remote Desktop Protocol)**
How you get a Windows desktop on your legacy VM. Each VM has its own public IP address,
but port 3389 is **closed** until you request **Just-in-Time (JIT) access** for your own
address in [Challenge 0, step 2](../challenges/ch00/README.md). Standing rules that hold
3389 open are deleted automatically by tenant governance, so JIT — which opens the port
for a few hours and then closes it — is the way in that lasts. After that you connect with
any Remote Desktop client using the administrator credentials your facilitator hands out.
The catalog application listens on the VM's loopback interface, so the browser you use to
view it is the one *inside* the VM.

**Revision**
An immutable snapshot of a Container App's configuration and image. Changing the image or
a setting creates a *new* revision rather than mutating the running one, which is what
makes both traffic splitting and instant rollback possible.

**Slice**
One bounded unit of rewrite work in the Copilot-assisted path: plan it, let Copilot
generate it, review the diff yourself, run the tests, commit — then take the next one. The
registered slices are listed in `workshop/contracts/challenge-paths.json`. Slicing exists
so that a failed generation costs you one small diff instead of a day.

**SRE Agent (Azure SRE Agent)**
The Azure service in Challenge 6 that investigates an incident from your telemetry and
proposes a remediation. In this workshop it runs in **Review** mode: it may read
everything, but it may not change anything until a human with the Administrator role
approves the proposed action.

**Terraform**
The infrastructure-as-code tool used for the *facilitator-owned* base infrastructure in
`baseInfra/` — the participant VMs, network, public IPs, and Entra users. Participants do not
run it; the Azure target you deploy is Bicep.

**Traffic split**
The percentages that decide how much live traffic each revision of a Container App
receives. `100/0` means all traffic to the current revision; shifting to `0/100` is how
Challenge 3 promotes and how Challenge 6 rolls back.

**Validator**
An executable check — a `pytest` gate or a `jq` assertion — that decides whether your
evidence is acceptable. Validators are fail-closed and are the arbiter of chapter
completion, so "it looks right to me" is never the pass condition.
