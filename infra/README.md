# Shared Azure target

`main.bicep` is a standalone subscription-scope template for the approved
Sweden Central workshop profile. Each deployment owns one participant/team
resource group and supports:

- `.NET / Azure SQL` with Entra-only administration and workload managed identity;
- `Java / PostgreSQL` with a local restore administrator plus facilitator Entra
  administrator and either a password application role or workload managed identity;
- Blob images with workload-identity reads, or the Azure Files compatibility mount;
- ACR managed-identity pulls, a VNet-integrated Container Apps environment, private
  data endpoints, Log Analytics, Application Insights, and managed OpenTelemetry.

## Stages

`bootstrap` creates infrastructure only. It emits a schema-valid target document
whose `containerImage` and `application` fields are null. It does not create a
placeholder Container App.

`application` requires a lowercase 40-hex source commit, a full sha256 image
digest, and secure application inputs. The Container App revision suffix is the
first 12 commit characters and the URL uses the environment's actual
`defaultDomain`.

## Build

Every Azure CLI invocation must use the isolated facilitator profile:

```bash
AZURE_CONFIG_DIR="$HOME/.azure-365" az bicep version
AZURE_CONFIG_DIR="$HOME/.azure-365" az bicep build --file infra/main.bicep
for file in infra/modules/*.bicep; do
  AZURE_CONFIG_DIR="$HOME/.azure-365" az bicep build --file "$file"
done
for file in infra/parameters/*.bicepparam; do
  AZURE_CONFIG_DIR="$HOME/.azure-365" az bicep build-params --file "$file"
done
```

The checked-in parameter files contain conspicuous sanitized values and are for
template compilation only. For what-if, create a protected parameter file
outside the repository and replace every secure value:

```bash
AZURE_CONFIG_DIR="$HOME/.azure-365" az deployment sub what-if \
  --location swedencentral \
  --template-file infra/main.bicep \
  --parameters @/protected/path/scenario.json
```

Never run `az deployment sub create` as part of P4.

## Azure Files policy boundary

The Azure Files mode is deliberately limited to the Container Apps Azure Files
volume implementation. The storage key is passed only to the environment
storage resource and is never output. The approved validation subscription
denies shared-key storage, so this compatibility mode requires a policy
exemption or a different workshop subscription.

## Rollback boundary

P4 does not add rollback orchestration. Keep the prior healthy Container Apps
revision and use the workshop's existing revision traffic procedure after
explicit facilitator approval. Database artifacts and source data remain
intact; this template performs no migration or deletion.
