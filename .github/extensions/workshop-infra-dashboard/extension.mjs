import { createServer } from "node:http";
import { createCanvas, joinSession } from "@github/copilot-sdk/extension";

import { getInventoryState, refreshInventory } from "./azure-inventory.mjs";
import { renderDashboard } from "./renderer.mjs";

const servers = new Map();

function sendJson(res, statusCode, body) {
    res.writeHead(statusCode, {
        "Cache-Control": "no-store",
        "Content-Type": "application/json; charset=utf-8",
    });
    res.end(JSON.stringify(body));
}

async function handleRequest(req, res) {
    const url = new URL(req.url ?? "/", "http://127.0.0.1");

    if (req.method === "GET" && url.pathname === "/") {
        res.writeHead(200, {
            "Cache-Control": "no-store",
            "Content-Type": "text/html; charset=utf-8",
        });
        res.end(renderDashboard());
        return;
    }

    if (req.method === "GET" && url.pathname === "/api/state") {
        sendJson(res, 200, getInventoryState());
        return;
    }

    if (req.method === "POST" && url.pathname === "/api/refresh") {
        sendJson(res, 200, await refreshInventory());
        return;
    }

    sendJson(res, 404, { error: "Not found" });
}

async function startServer(instanceId) {
    const server = createServer((req, res) => {
        handleRequest(req, res).catch((error) => {
            sendJson(res, 500, { error: error instanceof Error ? error.message : String(error) });
        });
    });

    await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
    const address = server.address();
    const port = typeof address === "object" && address ? address.port : 0;
    return { instanceId, server, url: `http://127.0.0.1:${port}/` };
}

await joinSession({
    canvases: [
        createCanvas({
            id: "workshop-infra-dashboard",
            displayName: "Workshop infrastructure",
            description: "Live Azure deployment progress for 35 workshop environments and their virtual machines.",
            inputSchema: {
                type: "object",
                properties: {},
                additionalProperties: false,
            },
            actions: [
                {
                    name: "refresh_inventory",
                    description: "Reload all workshop subscriptions, resource groups, and virtual machines from Azure.",
                    inputSchema: {
                        type: "object",
                        properties: {},
                        additionalProperties: false,
                    },
                    handler: async () => {
                        const state = await refreshInventory();
                        return {
                            status: state.status,
                            summary: state.data?.summary ?? null,
                            completedAt: state.completedAt,
                            error: state.error,
                        };
                    },
                },
                {
                    name: "get_summary",
                    description: "Return the latest workshop infrastructure deployment summary.",
                    inputSchema: {
                        type: "object",
                        properties: {},
                        additionalProperties: false,
                    },
                    handler: async () => {
                        const state = getInventoryState();
                        return {
                            status: state.status,
                            summary: state.data?.summary ?? null,
                            completedAt: state.completedAt,
                            error: state.error,
                        };
                    },
                },
            ],
            open: async (ctx) => {
                let entry = servers.get(ctx.instanceId);
                if (!entry) {
                    entry = await startServer(ctx.instanceId);
                    servers.set(ctx.instanceId, entry);
                }

                if (getInventoryState().status === "idle") {
                    void refreshInventory();
                }

                return {
                    title: "Workshop infrastructure",
                    status: "35 environments / 70 VMs expected",
                    url: entry.url,
                };
            },
            onClose: async (ctx) => {
                const entry = servers.get(ctx.instanceId);
                if (!entry) {
                    return;
                }

                servers.delete(ctx.instanceId);
                await new Promise((resolve) => entry.server.close(resolve));
            },
        }),
    ],
});
