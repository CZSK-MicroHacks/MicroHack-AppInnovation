import { createServer } from "node:http";
import { createCanvas, joinSession } from "@github/copilot-sdk/extension";

import { renderTimer } from "./renderer.mjs";
import {
    getTimerState,
    resetTimer,
    setTimerDuration,
    setTimerEndTime,
    startTimer,
    stopTimer,
} from "./timer-state.mjs";

const DEFAULT_TIMER_ID = "main";
const DEFAULT_DURATION_SECONDS = 5 * 60;
const servers = new Map();
const instanceTimers = new Map();

/**
 * Writes a JSON response without allowing browser caches to retain timer state.
 */
function sendJson(res, statusCode, body) {
    res.writeHead(statusCode, {
        "Cache-Control": "no-store",
        "Content-Type": "application/json; charset=utf-8",
    });
    res.end(JSON.stringify(body));
}

/**
 * Reads a small JSON request body from the local timer iframe.
 */
async function readJson(req) {
    const chunks = [];
    let size = 0;

    for await (const chunk of req) {
        size += chunk.length;
        if (size > 16_384) {
            throw new Error("Request body is too large.");
        }
        chunks.push(chunk);
    }

    if (chunks.length === 0) {
        return {};
    }

    return JSON.parse(Buffer.concat(chunks).toString("utf8"));
}

/**
 * Routes timer UI requests to the state owned by the canvas domain timer ID.
 */
async function handleRequest(timerId, req, res) {
    const url = new URL(req.url ?? "/", "http://127.0.0.1");

    if (req.method === "GET" && url.pathname === "/") {
        res.writeHead(200, {
            "Cache-Control": "no-store",
            "Content-Security-Policy": "default-src 'self'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; connect-src 'self'",
            "Content-Type": "text/html; charset=utf-8",
        });
        res.end(renderTimer());
        return;
    }

    if (req.method === "GET" && url.pathname === "/api/state") {
        sendJson(res, 200, getTimerState(timerId));
        return;
    }

    if (req.method === "POST" && url.pathname === "/api/start") {
        sendJson(res, 200, startTimer(timerId));
        return;
    }

    if (req.method === "POST" && url.pathname === "/api/stop") {
        sendJson(res, 200, stopTimer(timerId));
        return;
    }

    if (req.method === "POST" && url.pathname === "/api/reset") {
        sendJson(res, 200, resetTimer(timerId));
        return;
    }

    if (req.method === "POST" && url.pathname === "/api/duration") {
        const input = await readJson(req);
        sendJson(res, 200, setTimerDuration(timerId, input.seconds));
        return;
    }

    if (req.method === "POST" && url.pathname === "/api/end-time") {
        const input = await readJson(req);
        sendJson(res, 200, setTimerEndTime(timerId, input.time));
        return;
    }

    sendJson(res, 404, { error: "Not found" });
}

/**
 * Starts one loopback renderer for a timer canvas instance.
 */
async function startServer(instanceId, timerId) {
    const server = createServer((req, res) => {
        handleRequest(timerId, req, res).catch((error) => {
            const message = error instanceof Error ? error.message : String(error);
            sendJson(res, 400, { error: message });
        });
    });

    await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
    const address = server.address();
    const port = typeof address === "object" && address ? address.port : 0;
    return { instanceId, server, timerId, url: `http://127.0.0.1:${port}/` };
}

/**
 * Resolves the stable timer ID associated with an open canvas instance.
 */
function getInstanceTimerId(instanceId) {
    return instanceTimers.get(instanceId) ?? DEFAULT_TIMER_ID;
}

await joinSession({
    canvases: [
        createCanvas({
            id: "timer",
            displayName: "Timer",
            description: "Minimal large-screen countdown timer with an animated remaining-time orbit.",
            inputSchema: {
                type: "object",
                properties: {
                    timerId: {
                        type: "string",
                        minLength: 1,
                        maxLength: 80,
                        pattern: "^[A-Za-z0-9][A-Za-z0-9._-]*$",
                    },
                    initialSeconds: {
                        type: "integer",
                        minimum: 1,
                        maximum: 359999,
                    },
                },
                additionalProperties: false,
            },
            actions: [
                {
                    name: "get_state",
                    description: "Return the current timer duration, remaining time, and running state.",
                    inputSchema: {
                        type: "object",
                        properties: {},
                        additionalProperties: false,
                    },
                    handler: (ctx) => getTimerState(getInstanceTimerId(ctx.instanceId)),
                },
                {
                    name: "set_duration",
                    description: "Set the timer duration in seconds and stop the countdown.",
                    inputSchema: {
                        type: "object",
                        properties: {
                            seconds: {
                                type: "integer",
                                minimum: 1,
                                maximum: 359999,
                            },
                        },
                        required: ["seconds"],
                        additionalProperties: false,
                    },
                    handler: (ctx) => setTimerDuration(
                        getInstanceTimerId(ctx.instanceId),
                        ctx.input.seconds,
                    ),
                },
                {
                    name: "set_end_time",
                    description: "Set and immediately start a timer that finishes at a future local time today.",
                    inputSchema: {
                        type: "object",
                        properties: {
                            time: {
                                type: "string",
                                pattern: "^([01]\\d|2[0-3]):[0-5]\\d$",
                                description: "Local end time in 24-hour HH:MM format.",
                            },
                        },
                        required: ["time"],
                        additionalProperties: false,
                    },
                    handler: (ctx) => setTimerEndTime(
                        getInstanceTimerId(ctx.instanceId),
                        ctx.input.time,
                    ),
                },
                {
                    name: "start",
                    description: "Start or resume the countdown.",
                    inputSchema: {
                        type: "object",
                        properties: {},
                        additionalProperties: false,
                    },
                    handler: (ctx) => startTimer(getInstanceTimerId(ctx.instanceId)),
                },
                {
                    name: "stop",
                    description: "Stop the countdown at its current remaining time.",
                    inputSchema: {
                        type: "object",
                        properties: {},
                        additionalProperties: false,
                    },
                    handler: (ctx) => stopTimer(getInstanceTimerId(ctx.instanceId)),
                },
                {
                    name: "reset",
                    description: "Reset the countdown to its configured duration and stop it.",
                    inputSchema: {
                        type: "object",
                        properties: {},
                        additionalProperties: false,
                    },
                    handler: (ctx) => resetTimer(getInstanceTimerId(ctx.instanceId)),
                },
            ],
            open: async (ctx) => {
                const timerId = ctx.input?.timerId ?? DEFAULT_TIMER_ID;
                const initialSeconds = ctx.input?.initialSeconds ?? DEFAULT_DURATION_SECONDS;
                getTimerState(timerId, initialSeconds);
                instanceTimers.set(ctx.instanceId, timerId);

                let entry = servers.get(ctx.instanceId);
                if (!entry) {
                    entry = await startServer(ctx.instanceId, timerId);
                    servers.set(ctx.instanceId, entry);
                }

                return {
                    title: "Timer",
                    status: "Set, start, stop, and reset",
                    url: entry.url,
                };
            },
            onClose: async (ctx) => {
                const entry = servers.get(ctx.instanceId);
                instanceTimers.delete(ctx.instanceId);
                if (!entry) {
                    return;
                }

                servers.delete(ctx.instanceId);
                await new Promise((resolve) => entry.server.close(resolve));
            },
        }),
    ],
});
