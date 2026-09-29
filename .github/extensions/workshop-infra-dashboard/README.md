# Workshop infrastructure dashboard

This Copilot canvas reports deployment progress for the facilitator's 35 workshop
environments. It inventories enabled Azure subscriptions, `rg-labuser-NNNN` resource groups,
and the two expected virtual machines in each group. It also runs read-only localhost
checks inside each VM for the stack's root page, liveness endpoint, and readiness endpoint.

## Run

1. Sign in with the workshop Azure CLI profile:
   `AZURE_CONFIG_DIR="$HOME/.azure-hack" az account list`
2. Reload Copilot extensions after changing the canvas.
3. Open the **Workshop infrastructure** canvas.

The **Refresh Azure** button queries every enabled subscription and invokes a bounded set
of VM run commands to check .NET on port 5000 and Java on port 8080. A refresh can take
several minutes. An unavailable hosted application is reported as a warning and does not
change the environment's infrastructure-completeness result. Subscription-level failures
are shown without discarding successful results from other subscriptions. While checks
are running, the dashboard reports progress as completed environments out of the total 35.
