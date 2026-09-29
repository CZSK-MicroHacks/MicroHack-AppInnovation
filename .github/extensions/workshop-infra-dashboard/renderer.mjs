export function renderDashboard() {
    return `<!doctype html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Workshop infrastructure</title>
    <style>
        :root {
            color-scheme: light dark;
            --success: var(--true-color-green, #1a7f37);
            --success-muted: var(--true-color-green-muted, #dafbe1);
            --warning: var(--true-color-yellow, #9a6700);
            --warning-muted: var(--true-color-yellow-muted, #fff8c5);
            --danger: var(--true-color-red, #cf222e);
            --danger-muted: var(--true-color-red-muted, #ffebe9);
            --accent: var(--true-color-blue, #0969da);
            --accent-muted: var(--true-color-blue-muted, #ddf4ff);
        }
        * { box-sizing: border-box; }
        body {
            margin: 0;
            background: var(--background-color-default, #f6f8fa);
            color: var(--text-color-default, #1f2328);
            font-family: var(--font-sans, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif);
            font-size: var(--text-body-medium, 14px);
            line-height: var(--leading-body-medium, 20px);
        }
        button, input { font: inherit; }
        .shell { max-width: 1180px; margin: 0 auto; padding: 28px; }
        header {
            display: flex;
            align-items: flex-start;
            justify-content: space-between;
            gap: 24px;
            margin-bottom: 22px;
        }
        .eyebrow {
            color: var(--accent);
            font-size: 12px;
            font-weight: var(--font-weight-semibold, 600);
            letter-spacing: .08em;
            text-transform: uppercase;
        }
        h1 {
            margin: 5px 0 6px;
            font-family: var(--font-sans-display, var(--font-sans, sans-serif));
            font-size: var(--text-title-large, 26px);
            line-height: var(--leading-title-large, 32px);
        }
        .subtitle, .muted { color: var(--text-color-muted, #656d76); }
        .actions { display: flex; align-items: center; gap: 12px; }
        .refresh {
            border: 1px solid var(--border-color-default, #d0d7de);
            border-radius: 8px;
            padding: 8px 14px;
            background: var(--accent);
            color: var(--color-white, #fff);
            cursor: pointer;
            font-weight: var(--font-weight-semibold, 600);
        }
        .refresh:disabled { cursor: wait; opacity: .65; }
        .cards {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
            gap: 12px;
            margin-bottom: 16px;
        }
        .card, .panel, details {
            border: 1px solid var(--border-color-default, #d0d7de);
            background: var(--background-color-default, #fff);
            border-radius: 10px;
        }
        .card { padding: 16px; min-height: 105px; }
        .card-label {
            color: var(--text-color-muted, #656d76);
            font-size: 12px;
            font-weight: var(--font-weight-semibold, 600);
            text-transform: uppercase;
        }
        .card-value { margin-top: 8px; font-size: 28px; font-weight: 700; line-height: 34px; }
        .card-detail { margin-top: 3px; color: var(--text-color-muted, #656d76); font-size: 12px; }
        .panel { padding: 16px; margin-bottom: 16px; }
        .progress-row { display: flex; justify-content: space-between; gap: 16px; margin-bottom: 8px; }
        .progress-track {
            height: 10px;
            overflow: hidden;
            border-radius: 999px;
            background: var(--border-color-default, #d0d7de);
        }
        .progress-bar { height: 100%; background: var(--success); transition: width .25s ease; }
        .refresh-progress .progress-bar { background: var(--accent); }
        .toolbar { display: flex; gap: 12px; align-items: center; margin: 18px 0 12px; }
        .search {
            width: 100%;
            border: 1px solid var(--border-color-default, #d0d7de);
            border-radius: 8px;
            padding: 8px 10px;
            background: var(--background-color-default, #fff);
            color: var(--text-color-default, #1f2328);
        }
        .status {
            display: inline-flex;
            align-items: center;
            border-radius: 999px;
            padding: 2px 8px;
            font-size: 12px;
            font-weight: var(--font-weight-semibold, 600);
            white-space: nowrap;
        }
        .status.complete, .status.running { color: var(--success); background: var(--success-muted); }
        .status.incomplete, .status.starting { color: var(--warning); background: var(--warning-muted); }
        .status.unexpected, .status.error, .status.stopped { color: var(--danger); background: var(--danger-muted); }
        .status.warning { color: var(--warning); background: var(--warning-muted); }
        .status.neutral { color: var(--accent); background: var(--accent-muted); }
        .subscription-list { display: grid; gap: 10px; }
        details { overflow: hidden; }
        summary {
            display: flex;
            align-items: center;
            gap: 12px;
            padding: 13px 15px;
            cursor: pointer;
            list-style: none;
        }
        summary::-webkit-details-marker { display: none; }
        summary::before { content: "›"; color: var(--text-color-muted, #656d76); font-size: 22px; transition: transform .15s; }
        details[open] > summary::before { transform: rotate(90deg); }
        .summary-main { min-width: 0; flex: 1; }
        .summary-title { overflow: hidden; text-overflow: ellipsis; font-weight: var(--font-weight-semibold, 600); white-space: nowrap; }
        .summary-meta { color: var(--text-color-muted, #656d76); font-size: 12px; }
        .details-body { border-top: 1px solid var(--border-color-default, #d0d7de); padding: 12px; }
        .environment-list { display: grid; gap: 8px; }
        .environment { border-radius: 8px; }
        .vm-list { display: grid; gap: 8px; }
        .vm {
            display: grid;
            grid-template-columns: minmax(180px, 1.5fr) repeat(3, minmax(90px, 1fr));
            gap: 10px;
            align-items: center;
            padding: 10px;
            border: 1px solid var(--border-color-default, #d0d7de);
            border-radius: 7px;
        }
        .vm-name { font-weight: var(--font-weight-semibold, 600); }
        .vm-label { color: var(--text-color-muted, #656d76); font-size: 11px; text-transform: uppercase; }
        code {
            font-family: var(--font-mono, "SFMono-Regular", Consolas, monospace);
            font-size: var(--text-code-inline, 12px);
            word-break: break-all;
        }
        .resource-id { grid-column: 1 / -1; border-top: 1px solid var(--border-color-default, #d0d7de); padding-top: 8px; }
        .app-warning {
            grid-column: 1 / -1;
            color: var(--warning);
            background: var(--warning-muted);
            border-radius: 6px;
            padding: 7px 9px;
        }
        .empty, .error-box {
            padding: 18px;
            border: 1px dashed var(--border-color-default, #d0d7de);
            border-radius: 8px;
            color: var(--text-color-muted, #656d76);
            text-align: center;
        }
        .error-box { color: var(--danger); background: var(--danger-muted); text-align: left; }
        .loading { animation: pulse 1.2s ease-in-out infinite; }
        @keyframes pulse { 50% { opacity: .55; } }
        @media (max-width: 800px) {
            .shell { padding: 18px; }
            header { flex-direction: column; }
            .cards { grid-template-columns: repeat(2, minmax(0, 1fr)); }
            .vm { grid-template-columns: 1fr 1fr; }
            .resource-id { grid-column: 1 / -1; }
        }
    </style>
</head>
<body>
    <main class="shell">
        <header>
            <div>
                <div class="eyebrow">Azure deployment report</div>
                <h1>Workshop infrastructure</h1>
                <div class="subtitle">Live readiness across 35 participant environments</div>
            </div>
            <div class="actions">
                <span id="last-updated" class="muted">Waiting for Azure</span>
                <button id="refresh" class="refresh" type="button">Refresh Azure</button>
            </div>
        </header>
        <section id="content" aria-live="polite">
            <div class="panel loading">Loading subscriptions, resource groups, and virtual machines…</div>
        </section>
    </main>
    <script>
        const content = document.getElementById("content");
        const refreshButton = document.getElementById("refresh");
        const lastUpdated = document.getElementById("last-updated");
        const escapeHtml = (value) => String(value ?? "")
            .replaceAll("&", "&amp;")
            .replaceAll("<", "&lt;")
            .replaceAll(">", "&gt;")
            .replaceAll('"', "&quot;")
            .replaceAll("'", "&#039;");

        function powerClass(powerState) {
            const value = String(powerState || "").toLowerCase();
            if (value.includes("running")) return "running";
            if (value.includes("starting") || value.includes("deallocating")) return "starting";
            if (value.includes("stopped") || value.includes("deallocated")) return "stopped";
            return "neutral";
        }

        function renderVm(vm) {
            const app = vm.app || {
                status: "warning",
                warning: "Application check has not completed.",
                port: null,
                rootStatus: null,
                healthStatus: null,
                readyStatus: null
            };
            const appLabel = app.status === "working" ? "Working" : "Warning";
            const appWarning = app.status === "warning"
                ? '<div class="app-warning"><strong>Application warning:</strong> ' +
                    escapeHtml(app.warning || "The application probes did not pass.") + '</div>'
                : '';
            return '<div class="vm">' +
                '<div><div class="vm-label">Virtual machine</div><div class="vm-name">' + escapeHtml(vm.name) + '</div></div>' +
                '<div><div class="vm-label">Power</div><span class="status ' + powerClass(vm.powerState) + '">' + escapeHtml(vm.powerState || "Unknown") + '</span></div>' +
                '<div><div class="vm-label">Provisioning</div><div>' + escapeHtml(vm.provisioningState || "Unknown") + '</div></div>' +
                '<div><div class="vm-label">Size</div><div>' + escapeHtml(vm.vmSize || "Unknown") + '</div></div>' +
                '<div><div class="vm-label">Hosted app</div><span class="status ' + app.status + '">' + appLabel + '</span></div>' +
                '<div><div class="vm-label">Expected port</div><code>' + escapeHtml(app.port || "—") + '</code></div>' +
                '<div><div class="vm-label">HTTP / health / ready</div><code>' +
                    escapeHtml((app.rootStatus || "—") + " / " + (app.healthStatus || "—") + " / " + (app.readyStatus || "—")) +
                '</code></div>' +
                '<div><div class="vm-label">Checked</div><div>' +
                    escapeHtml(app.checkedAt ? new Date(app.checkedAt).toLocaleTimeString() : "—") + '</div></div>' +
                '<div><div class="vm-label">Private IP</div><code>' + escapeHtml(vm.privateIps || "—") + '</code></div>' +
                '<div><div class="vm-label">Public IP</div><code>' + escapeHtml(vm.publicIps || "—") + '</code></div>' +
                '<div><div class="vm-label">Region</div><div>' + escapeHtml(vm.location || "Unknown") + '</div></div>' +
                appWarning +
                '<div class="resource-id"><div class="vm-label">Resource ID</div><code>' + escapeHtml(vm.id) + '</code></div>' +
            '</div>';
        }

        function renderEnvironment(environment, subscriptionName) {
            const vms = environment.vms.length
                ? '<div class="vm-list">' + environment.vms.map(renderVm).join("") + '</div>'
                : '<div class="empty">No virtual machines found yet.</div>';
            return '<details class="environment" data-search="' +
                escapeHtml(subscriptionName + " " + environment.name + " " + environment.vms.map((vm) => vm.name).join(" ")) + '">' +
                '<summary><div class="summary-main"><div class="summary-title">' + escapeHtml(environment.name) +
                '</div><div class="summary-meta">' + escapeHtml(environment.location) + ' · ' +
                escapeHtml(environment.provisioningState || "Unknown") + '</div></div>' +
                '<span class="status ' + environment.status + '">' + environment.vmCount + ' / ' +
                environment.expectedVmCount + ' VMs</span>' +
                (environment.appWarningCount
                    ? '<span class="status warning">' + environment.appWarningCount + ' app warning' +
                        (environment.appWarningCount === 1 ? '' : 's') + '</span>'
                    : '<span class="status complete">Apps working</span>') +
                '</summary>' +
                '<div class="details-body">' + vms + '</div></details>';
        }

        function renderSubscription(subscription) {
            const searchableResources = subscription.environments.map((environment) =>
                environment.name + " " + environment.vms.map((vm) => vm.name).join(" ")
            ).join(" ");
            const environments = subscription.environments.length
                ? '<div class="environment-list">' + subscription.environments.map((environment) =>
                    renderEnvironment(environment, subscription.name)
                ).join("") + '</div>'
                : '<div class="empty">No workshop resource groups found in this subscription.</div>';
            const error = subscription.error
                ? '<div class="error-box">' + escapeHtml(subscription.error) + '</div>'
                : environments;
            return '<details class="subscription" data-search="' +
                escapeHtml(subscription.name + " " + searchableResources) + '">' +
                '<summary><div class="summary-main"><div class="summary-title">' + escapeHtml(subscription.name) +
                (subscription.isDefault ? ' <span class="status neutral">default</span>' : '') +
                '</div><div class="summary-meta"><code>' + escapeHtml(subscription.id) + '</code></div></div>' +
                '<span class="status ' + (subscription.error ? "error" : "neutral") + '">' +
                subscription.environmentCount + ' environments · ' + subscription.vmCount + ' VMs</span>' +
                (subscription.appWarningCount
                    ? '<span class="status warning">' + subscription.appWarningCount + ' warnings</span>'
                    : '<span class="status complete">Apps working</span>') +
                '</summary>' +
                '<div class="details-body">' + error + '</div></details>';
        }

        function renderRefreshProgress(state) {
            if (state.status !== "loading") return "";
            const progress = state.progress || {};
            const hasTotal = Number.isFinite(progress.total) && progress.total > 0;
            const percent = hasTotal ? Math.round((progress.completed / progress.total) * 100) : 0;
            const count = hasTotal
                ? progress.completed + " / " + progress.total + " environments checked"
                : "Reading Azure inventory";
            return '<section class="panel refresh-progress loading">' +
                '<div class="progress-row"><strong>Refreshing from Azure</strong><span>' + escapeHtml(count) + '</span></div>' +
                '<div class="progress-track"><div class="progress-bar" style="width:' + percent + '%"></div></div>' +
                '<div class="card-detail">' + escapeHtml(progress.message || "Working…") + '</div>' +
            '</section>';
        }

        function renderState(state) {
            refreshButton.disabled = state.status === "loading";
            refreshButton.textContent = state.status === "loading" ? "Refreshing…" : "Refresh Azure";

            if (state.status === "loading" && state.progress) {
                const progress = state.progress;
                lastUpdated.textContent = progress.total
                    ? progress.completed + " / " + progress.total + " environments"
                    : "Reading Azure…";
            } else if (state.completedAt) {
                const duration = state.durationMs ? " · " + Math.round(state.durationMs / 1000) + "s" : "";
                lastUpdated.textContent = "Updated " + new Date(state.completedAt).toLocaleTimeString() + duration;
            }

            if (state.status === "error" && !state.data) {
                content.innerHTML = '<div class="error-box"><strong>Azure refresh failed.</strong><br>' +
                    escapeHtml(state.error) + '</div>';
                return;
            }
            if (!state.data) {
                content.innerHTML = renderRefreshProgress(state) ||
                    '<div class="panel loading">Loading subscriptions, resource groups, and virtual machines…</div>';
                return;
            }

            const summary = state.data.summary;
            const infrastructureIssueCount = summary.missingEnvironmentCount + summary.incompleteEnvironmentCount +
                summary.unexpectedEnvironmentCount + summary.failedSubscriptionCount;
            content.innerHTML =
                renderRefreshProgress(state) +
                '<section class="cards">' +
                    '<div class="card"><div class="card-label">Subscriptions</div><div class="card-value">' + summary.subscriptionCount +
                    '</div><div class="card-detail">' + summary.failedSubscriptionCount + ' query errors</div></div>' +
                    '<div class="card"><div class="card-label">Environments</div><div class="card-value">' + summary.environmentCount +
                    ' / ' + summary.expectedEnvironmentCount + '</div><div class="card-detail">' + summary.missingEnvironmentCount + ' not created</div></div>' +
                    '<div class="card"><div class="card-label">Virtual machines</div><div class="card-value">' + summary.vmCount +
                    ' / ' + summary.expectedVmCount + '</div><div class="card-detail">' + summary.missingVmCount + ' remaining</div></div>' +
                    '<div class="card"><div class="card-label">Complete teams</div><div class="card-value">' + summary.completeEnvironmentCount +
                    '</div><div class="card-detail">Exactly 2 VMs available</div></div>' +
                    '<div class="card"><div class="card-label">Infrastructure issues</div><div class="card-value">' + infrastructureIssueCount +
                    '</div><div class="card-detail">Missing, incomplete, extra, or failed</div></div>' +
                    '<div class="card"><div class="card-label">Apps working</div><div class="card-value">' + summary.appWorkingCount +
                    ' / ' + summary.appCheckedCount + '</div><div class="card-detail">' + summary.appWarningCount + ' warnings</div></div>' +
                '</section>' +
                '<section class="panel"><div class="progress-row"><strong>Environment readiness</strong><span>' +
                    summary.completionPercent + '%</span></div><div class="progress-track"><div class="progress-bar" style="width:' +
                    summary.completionPercent + '%"></div></div>' +
                    '<div class="progress-row" style="margin-top:14px"><strong>Hosted application readiness</strong><span>' +
                    summary.appCompletionPercent + '%</span></div><div class="progress-track"><div class="progress-bar" style="width:' +
                    summary.appCompletionPercent + '%"></div></div></section>' +
                '<div class="toolbar"><input id="search" class="search" type="search" placeholder="Filter subscriptions, resource groups, or VMs…"></div>' +
                '<section class="subscription-list">' + state.data.subscriptions.map(renderSubscription).join("") + '</section>';

            document.getElementById("search").addEventListener("input", (event) => {
                const query = event.target.value.trim().toLowerCase();
                document.querySelectorAll("[data-search]").forEach((element) => {
                    element.hidden = query && !element.dataset.search.toLowerCase().includes(query);
                });
            });
        }

        async function loadState() {
            const response = await fetch("/api/state", { cache: "no-store" });
            const state = await response.json();
            renderState(state);
            if (state.status === "loading") {
                window.setTimeout(loadState, 1500);
            }
        }

        refreshButton.addEventListener("click", () => {
            refreshButton.disabled = true;
            refreshButton.textContent = "Refreshing…";
            lastUpdated.textContent = "Reading Azure…";
            fetch("/api/refresh", { method: "POST" })
                .then((response) => response.json())
                .then(renderState)
                .catch((error) => {
                    content.innerHTML = '<div class="error-box">' + escapeHtml(error.message) + '</div>';
                    refreshButton.disabled = false;
                    refreshButton.textContent = "Refresh Azure";
                });
            window.setTimeout(loadState, 250);
        });

        loadState().catch((error) => {
            content.innerHTML = '<div class="error-box">' + escapeHtml(error.message) + '</div>';
        });
    </script>
</body>
</html>`;
}
