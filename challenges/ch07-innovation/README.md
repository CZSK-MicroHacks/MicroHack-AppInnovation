# Optional Challenge 7: grounded AI catalog experience

## Objective

Add a grounded catalog discovery experience to either validated stack without changing
the required catalog contract. The experience may recommend figures, answer catalog
questions, or combine natural-language discovery with the existing exact search.

Supported starting points:

- `.NET/SQL Server` with Azure SQL Database; and
- `Java/PostgreSQL` with Azure Database for PostgreSQL Flexible Server.

This is an optional paid-service extension. Obtain facilitator approval for Azure AI
Search, model deployment, content-safety, and evaluation capacity before creating
resources.

## Architecture constraints

- The canonical 198-figure corpus remains the only source of product truth.
- Existing routes, identity rules, import transaction, health, performance, and
  telemetry behavior remain unchanged.
- Generated answers must cite canonical product IDs and links that exist in the
  validated catalog.
- Azure AI Search is the shared retrieval boundary; use keyword plus vector hybrid
  retrieval and keep the index key equal to canonical `productId`.
- Model and search access use managed identity and least-privilege data-plane roles.
  Do not place keys in source, browser code, prompts, logs, or evidence.
- Grounding, model response, and UI failure must not make `/readyz` fail for the
  existing catalog.
- Treat prompt text, retrieved descriptions, and model output as untrusted content.

## Stack adapters

Keep one application-facing use case and implement only the selected adapter:

| Stack | Backend integration |
| --- | --- |
| `.NET/SQL Server` | Add a bounded .NET service that reads canonical catalog DTOs, queries Azure AI Search, invokes the approved model, and emits existing OpenTelemetry resource identity |
| `Java/PostgreSQL` | Add the equivalent Spring service with the same request/response and grounding rules; database-specific repositories remain behind the existing catalog boundary |

The AI index is derived, not authoritative. Rebuild it from the validated catalog rather
than writing model output or embeddings back into the primary database.

If you add a separate chat frontend, use React with `assistant-ui` and call only a
server-side API. The browser must never receive Azure credentials or direct model/search
access. Reusing the existing server-rendered UI is also valid.

## Tasks

### 1. Define the grounded contract

Specify:

- user question and optional filters;
- maximum input/output size and timeout;
- retrieval query and maximum documents;
- response text, canonical citations, and abstention reason;
- stable error responses for unavailable retrieval/model services; and
- prompt-injection and unsupported-request handling.

Require at least one citation for every catalog claim. When evidence is insufficient,
return a clear abstention rather than model knowledge.

### 2. Build the index

Map only canonical fields required for discovery: product ID, name, description,
category name/slug, and image route. Record source commit, corpus digest, embedding
deployment identity, index schema/version, document count, and index time.

Use deterministic chunking for this small catalog. Do not index secrets, operational
logs, participant prompts, or derived model answers.

### 3. Implement retrieval and generation

Combine text and vector retrieval, apply filters server-side, and pass only returned
canonical records into the generation prompt. Validate every model citation against the
retrieved set before returning it.

Use bounded retries only for transient service responses. Propagate explicit dependency
failure; do not return a success-shaped fallback that lacks verified grounding.

### 4. Add responsible-AI controls

Document threat cases for prompt injection, malicious catalog text, unsafe user input,
unsafe output, hallucinated products, sensitive-data disclosure, denial of service, and
cross-user leakage. Apply the approved content-safety policy at the server boundary and
retain privacy-appropriate audit metadata without raw secrets or unnecessary prompt
content.

### 5. Evaluate

Create a sanitized evaluation set covering:

- answerable exact-product and category questions;
- ambiguous questions;
- questions outside the catalog;
- prompt-injection attempts;
- requests for nonexistent figures;
- unsafe input; and
- retrieval or model unavailability.

Measure retrieval relevance, citation precision, grounded-answer rate, abstention
correctness, safety behavior, latency, and cost. Pin the model/deployment and evaluation
dataset versions so results are comparable.

### 6. Observe and isolate

Emit dependency spans and bounded metrics for retrieval, model calls, citation
validation, abstention, token use, latency, and safety outcomes while preserving the
existing service namespace/environment/version/revision attributes. Never log secrets,
full credentials, or unreviewed sensitive prompt content.

Use a feature flag or separate route so the original catalog remains available when the
AI extension is disabled.

## Deliverables

1. Architecture and trust-boundary diagram.
2. Stack-neutral API contract and selected .NET or Java adapter.
3. Versioned AI Search index definition and deterministic indexing process.
4. Managed-identity/RBAC matrix.
5. Grounding prompt, citation validator, and abstention behavior.
6. Threat model and content-safety configuration.
7. Sanitized evaluation dataset, thresholds, and actual results.
8. Telemetry queries, cost estimate, disable path, and cleanup inventory.
9. Evidence that the unchanged required catalog acceptance and handoff validators still
   pass.

## Success criteria

- Every catalog claim is supported by a canonical citation returned by retrieval.
- Hallucinated or unretrieved product IDs are rejected before the response reaches the
  user.
- Both the common API design and selected stack adapter are documented.
- Managed identity is used end to end; no browser or repository secret is introduced.
- The evaluation meets facilitator-approved relevance, grounding, safety, latency, and
  cost thresholds.
- Disabling the extension restores the exact required workshop application without data
  migration or evidence changes.
