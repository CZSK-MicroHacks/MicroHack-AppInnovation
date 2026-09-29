/**
 * Renders the self-contained large-screen timer application.
 */
export function renderTimer() {
    return `<!doctype html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <meta name="color-scheme" content="light dark">
    <title>Timer</title>
    <style>
        :root {
            --accent: var(--true-color-blue, #218bff);
            --accent-muted: var(--true-color-blue-muted, #b6dcff);
            --surface: var(--background-color-default, #ffffff);
            --text: var(--text-color-default, #1f2328);
            --muted: var(--text-color-muted, #656d76);
            --border: var(--border-color-default, #d0d7de);
            --focus: var(--color-focus-outline, #0969da);
        }

        * {
            box-sizing: border-box;
        }

        html,
        body {
            min-height: 100%;
        }

        body {
            margin: 0;
            overflow: hidden;
            background: var(--surface);
            color: var(--text);
            font-family: var(--font-sans, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif);
        }

        button,
        input {
            font: inherit;
        }

        .app {
            min-height: 100vh;
            display: grid;
            grid-template-rows: auto minmax(0, 1fr) auto;
            padding: clamp(20px, 3vw, 48px);
        }

        .topline {
            display: flex;
            align-items: center;
            justify-content: space-between;
            color: var(--muted);
            font-size: var(--text-body-small, 12px);
            font-weight: var(--font-weight-semibold, 600);
            letter-spacing: 0.16em;
            text-transform: uppercase;
        }

        .status {
            display: inline-flex;
            align-items: center;
            gap: 9px;
        }

        .status-dot {
            width: 8px;
            height: 8px;
            border-radius: 50%;
            background: var(--muted);
            transition: background 180ms ease, box-shadow 180ms ease;
        }

        .is-running .status-dot {
            background: var(--accent);
            box-shadow: 0 0 0 6px color-mix(in srgb, var(--accent) 14%, transparent);
        }

        .stage {
            min-height: 0;
            display: grid;
            place-items: center;
            padding: clamp(12px, 2vh, 28px) 0;
        }

        .dial {
            --progress: 1;
            position: relative;
            width: min(68vh, 76vw);
            aspect-ratio: 1;
            display: grid;
            place-items: center;
            isolation: isolate;
        }

        .dial::before,
        .dial::after {
            content: "";
            position: absolute;
            inset: 0;
            border-radius: 50%;
        }

        .dial::before {
            background:
                conic-gradient(
                    from -90deg,
                    var(--accent) calc(var(--progress) * 1turn),
                    color-mix(in srgb, var(--border) 58%, transparent) 0
                );
            -webkit-mask: radial-gradient(farthest-side, transparent calc(100% - clamp(8px, 1.1vw, 15px)), #000 0);
            mask: radial-gradient(farthest-side, transparent calc(100% - clamp(8px, 1.1vw, 15px)), #000 0);
            transition: filter 220ms ease;
        }

        .dial::after {
            inset: 8%;
            background: radial-gradient(circle, color-mix(in srgb, var(--accent) 9%, transparent), transparent 68%);
            opacity: 0;
            transform: scale(0.88);
            transition: opacity 300ms ease, transform 300ms ease;
            z-index: -1;
        }

        .is-running .dial::before {
            filter: drop-shadow(0 0 12px color-mix(in srgb, var(--accent) 42%, transparent));
        }

        .is-running .dial::after {
            opacity: 1;
            transform: scale(1);
            animation: breathe 3.2s ease-in-out infinite;
        }

        .time {
            display: flex;
            align-items: baseline;
            font-family: var(--font-mono, "SFMono-Regular", Consolas, monospace);
            font-size: clamp(4.5rem, min(15vw, 18vh), 10rem);
            font-variant-numeric: tabular-nums;
            font-weight: var(--font-weight-semibold, 600);
            letter-spacing: -0.075em;
            line-height: 0.8;
            transform: translateX(-0.03em);
        }

        .time.has-hours {
            font-size: clamp(3.5rem, min(10vw, 12vh), 7rem);
            letter-spacing: -0.06em;
        }

        .colon {
            color: var(--accent);
            display: inline-block;
            transform: translateY(-0.08em);
        }

        .controls {
            width: min(1280px, 100%);
            margin: 0 auto;
            display: grid;
            grid-template-columns: minmax(260px, 1fr) auto;
            gap: 18px;
            align-items: end;
        }

        .timer-entry {
            display: grid;
            gap: 12px;
            justify-items: start;
        }

        .set-time,
        .end-time {
            display: flex;
            align-items: end;
            gap: 10px;
        }

        .mode-switch {
            display: inline-flex;
            padding: 3px;
            border: 1px solid var(--border);
            border-radius: 9px;
            background: color-mix(in srgb, var(--text) 3%, transparent);
        }

        .mode-button {
            min-width: 88px;
            height: 32px;
            padding: 0 12px;
            border: 0;
            border-radius: 6px;
            background: transparent;
            color: var(--muted);
            cursor: pointer;
            font-size: var(--text-body-small, 12px);
            font-weight: var(--font-weight-semibold, 600);
        }

        .mode-button[aria-selected="true"] {
            background: var(--surface);
            color: var(--text);
            box-shadow: 0 1px 3px color-mix(in srgb, var(--text) 16%, transparent);
        }

        .field {
            display: grid;
            gap: 7px;
        }

        .field label {
            color: var(--muted);
            font-size: var(--text-body-small, 12px);
            font-weight: var(--font-weight-semibold, 600);
            letter-spacing: 0.08em;
            text-transform: uppercase;
        }

        .field input {
            width: clamp(68px, 7vw, 90px);
            height: 50px;
            border: 1px solid var(--border);
            border-radius: 10px;
            background: transparent;
            color: var(--text);
            font-family: var(--font-mono, "SFMono-Regular", Consolas, monospace);
            font-size: 18px;
            font-variant-numeric: tabular-nums;
            text-align: center;
        }

        .field input[type="time"] {
            width: 132px;
        }

        .actions {
            display: flex;
            gap: 10px;
        }

        .button {
            min-width: 108px;
            height: 50px;
            border: 1px solid var(--border);
            border-radius: 10px;
            background: transparent;
            color: var(--text);
            cursor: pointer;
            font-weight: var(--font-weight-semibold, 600);
            transition: transform 120ms ease, background 120ms ease, border-color 120ms ease;
        }

        .button:hover {
            background: color-mix(in srgb, var(--text) 5%, transparent);
        }

        .button:active {
            transform: translateY(1px);
        }

        .button.primary {
            border-color: var(--accent);
            background: var(--accent);
            color: var(--color-white, #ffffff);
        }

        .button.primary:hover {
            background: color-mix(in srgb, var(--accent) 88%, var(--text));
        }

        :focus-visible {
            outline: 3px solid var(--focus);
            outline-offset: 3px;
        }

        .error {
            position: fixed;
            top: 20px;
            left: 50%;
            max-width: min(560px, calc(100vw - 40px));
            padding: 10px 14px;
            border: 1px solid var(--true-color-red, #cf222e);
            border-radius: 8px;
            background: var(--surface);
            color: var(--true-color-red, #cf222e);
            font-size: var(--text-body-small, 12px);
            transform: translateX(-50%);
        }

        [hidden] {
            display: none !important;
        }

        @keyframes breathe {
            0%, 100% { opacity: 0.42; transform: scale(0.94); }
            50% { opacity: 0.9; transform: scale(1.03); }
        }

        @media (max-width: 1180px) {
            .controls {
                grid-template-columns: 1fr;
            }

            .actions,
            .timer-entry {
                justify-content: center;
            }

            .timer-entry {
                justify-items: center;
            }
        }

        @media (max-width: 760px), (max-height: 640px) {
            .app {
                padding: 18px;
            }

            .dial {
                width: min(56vh, 90vw);
            }

            .actions,
            .set-time,
            .end-time {
                justify-content: center;
            }

            .button {
                min-width: 88px;
            }
        }

        @media (prefers-reduced-motion: reduce) {
            *,
            *::before,
            *::after {
                animation-duration: 0.01ms !important;
                animation-iteration-count: 1 !important;
                scroll-behavior: auto !important;
                transition-duration: 0.01ms !important;
            }
        }
    </style>
</head>
<body>
    <main class="app" id="app">
        <header class="topline">
            <span>Countdown</span>
            <span class="status"><span class="status-dot"></span><span id="statusText">Ready</span></span>
        </header>

        <section class="stage" aria-live="polite" aria-atomic="true">
            <div class="dial" id="dial">
                <div class="time" id="time" aria-label="5 minutes remaining">
                    <span id="hours" hidden>00</span><span class="colon" id="hourColon" hidden>:</span><span id="minutes">05</span><span class="colon">:</span><span id="seconds">00</span>
                </div>
            </div>
        </section>

        <footer class="controls">
            <div class="timer-entry">
                <div class="mode-switch" role="tablist" aria-label="Timer input mode">
                    <button class="mode-button" id="durationModeButton" type="button" role="tab" aria-selected="true" aria-controls="durationForm">Duration</button>
                    <button class="mode-button" id="endTimeModeButton" type="button" role="tab" aria-selected="false" aria-controls="endTimeForm">End at</button>
                </div>

                <form class="set-time" id="durationForm">
                    <div class="field">
                        <label for="hoursInput">Hours</label>
                        <input id="hoursInput" type="number" min="0" max="99" value="0" inputmode="numeric">
                    </div>
                    <div class="field">
                        <label for="minutesInput">Minutes</label>
                        <input id="minutesInput" type="number" min="0" max="59" value="5" inputmode="numeric">
                    </div>
                    <div class="field">
                        <label for="secondsInput">Seconds</label>
                        <input id="secondsInput" type="number" min="0" max="59" value="0" inputmode="numeric">
                    </div>
                    <button class="button" type="submit">Set time</button>
                </form>

                <form class="end-time" id="endTimeForm" hidden>
                    <div class="field">
                        <label for="endTimeInput">End at</label>
                        <input id="endTimeInput" type="time" required step="60">
                    </div>
                    <button class="button" type="submit">Start to end</button>
                </form>
            </div>

            <div class="actions">
                <button class="button primary" id="startButton" type="button">Start</button>
                <button class="button" id="stopButton" type="button">Stop</button>
                <button class="button" id="resetButton" type="button">Reset</button>
            </div>
        </footer>
    </main>
    <div class="error" id="error" role="alert" hidden></div>

    <script>
        const app = document.getElementById("app");
        const dial = document.getElementById("dial");
        const time = document.getElementById("time");
        const hours = document.getElementById("hours");
        const hourColon = document.getElementById("hourColon");
        const minutes = document.getElementById("minutes");
        const seconds = document.getElementById("seconds");
        const statusText = document.getElementById("statusText");
        const error = document.getElementById("error");
        const durationForm = document.getElementById("durationForm");
        const endTimeForm = document.getElementById("endTimeForm");
        const durationModeButton = document.getElementById("durationModeButton");
        const endTimeModeButton = document.getElementById("endTimeModeButton");
        const hoursInput = document.getElementById("hoursInput");
        const minutesInput = document.getElementById("minutesInput");
        const secondsInput = document.getElementById("secondsInput");
        const endTimeInput = document.getElementById("endTimeInput");
        const startButton = document.getElementById("startButton");
        const stopButton = document.getElementById("stopButton");
        const resetButton = document.getElementById("resetButton");

        let timerState = null;
        let receivedAt = 0;
        let renderedDuration = null;

        function showError(message) {
            error.textContent = message;
            error.hidden = !message;
        }

        function setEntryMode(mode) {
            const showDuration = mode === "duration";
            durationForm.hidden = !showDuration;
            endTimeForm.hidden = showDuration;
            durationModeButton.setAttribute("aria-selected", String(showDuration));
            endTimeModeButton.setAttribute("aria-selected", String(!showDuration));
        }

        async function request(path, options = {}) {
            const response = await fetch(path, {
                ...options,
                headers: { "Content-Type": "application/json", ...(options.headers ?? {}) },
            });
            const body = await response.json();
            if (!response.ok) {
                throw new Error(body.error ?? "Timer request failed.");
            }
            applyState(body);
            showError("");
            return body;
        }

        function applyState(nextState) {
            timerState = nextState;
            receivedAt = Date.now();
            app.classList.toggle("is-running", nextState.running);
            statusText.textContent = nextState.running && nextState.endsAt
                ? "Ends " + new Intl.DateTimeFormat([], { hour: "numeric", minute: "2-digit" }).format(new Date(nextState.endsAt))
                : nextState.remainingMs === 0 ? "Finished" : "Ready";
            startButton.textContent = nextState.remainingMs > 0 && nextState.remainingMs < nextState.durationMs ? "Resume" : "Start";

            if (renderedDuration !== nextState.durationMs && !durationForm.contains(document.activeElement)) {
                const totalSeconds = Math.round(nextState.durationMs / 1000);
                hoursInput.value = Math.floor(totalSeconds / 3600);
                minutesInput.value = Math.floor((totalSeconds % 3600) / 60);
                secondsInput.value = totalSeconds % 60;
                renderedDuration = nextState.durationMs;
            }
        }

        function currentRemainingMs() {
            if (!timerState) {
                return 0;
            }
            if (!timerState.running) {
                return timerState.remainingMs;
            }
            return Math.max(0, timerState.remainingMs - (Date.now() - receivedAt));
        }

        function render() {
            if (!timerState) {
                request("/api/state").catch((requestError) => showError(requestError.message));
                return;
            }

            const remainingMs = currentRemainingMs();
            const totalSeconds = Math.ceil(remainingMs / 1000);
            const hourValue = Math.floor(totalSeconds / 3600);
            const minuteValue = Math.floor((totalSeconds % 3600) / 60);
            const secondValue = totalSeconds % 60;
            const showHours = hourValue > 0;
            const progress = timerState.durationMs === 0 ? 0 : remainingMs / timerState.durationMs;

            hours.hidden = !showHours;
            hourColon.hidden = !showHours;
            time.classList.toggle("has-hours", showHours);
            hours.textContent = String(hourValue).padStart(2, "0");
            minutes.textContent = String(minuteValue).padStart(2, "0");
            seconds.textContent = String(secondValue).padStart(2, "0");
            dial.style.setProperty("--progress", String(Math.max(0, Math.min(1, progress))));

            const label = [
                hourValue ? hourValue + " hours" : "",
                minuteValue ? minuteValue + " minutes" : "",
                secondValue + " seconds remaining",
            ].filter(Boolean).join(", ");
            time.setAttribute("aria-label", label);
            document.title = (showHours ? String(hourValue).padStart(2, "0") + ":" : "")
                + String(minuteValue).padStart(2, "0") + ":"
                + String(secondValue).padStart(2, "0") + " · Timer";

            requestAnimationFrame(render);
        }

        durationForm.addEventListener("submit", (event) => {
            event.preventDefault();
            const totalSeconds = Number(hoursInput.value) * 3600
                + Number(minutesInput.value) * 60
                + Number(secondsInput.value);
            request("/api/duration", {
                method: "POST",
                body: JSON.stringify({ seconds: totalSeconds }),
            }).catch((requestError) => showError(requestError.message));
        });

        endTimeForm.addEventListener("submit", (event) => {
            event.preventDefault();
            request("/api/end-time", {
                method: "POST",
                body: JSON.stringify({ time: endTimeInput.value }),
            }).catch((requestError) => showError(requestError.message));
        });

        durationModeButton.addEventListener("click", () => setEntryMode("duration"));
        endTimeModeButton.addEventListener("click", () => setEntryMode("end-time"));

        startButton.addEventListener("click", () => {
            request("/api/start", { method: "POST", body: "{}" })
                .catch((requestError) => showError(requestError.message));
        });
        stopButton.addEventListener("click", () => {
            request("/api/stop", { method: "POST", body: "{}" })
                .catch((requestError) => showError(requestError.message));
        });
        resetButton.addEventListener("click", () => {
            request("/api/reset", { method: "POST", body: "{}" })
                .catch((requestError) => showError(requestError.message));
        });

        document.addEventListener("keydown", (event) => {
            if (event.target instanceof HTMLInputElement) {
                return;
            }
            if (event.code === "Space") {
                event.preventDefault();
                request(timerState?.running ? "/api/stop" : "/api/start", { method: "POST", body: "{}" })
                    .catch((requestError) => showError(requestError.message));
            }
            if (event.key.toLowerCase() === "r") {
                request("/api/reset", { method: "POST", body: "{}" })
                    .catch((requestError) => showError(requestError.message));
            }
        });

        setInterval(() => {
            request("/api/state").catch((requestError) => showError(requestError.message));
        }, 1000);

        const suggestedEnd = new Date(Date.now() + 30 * 60 * 1000);
        endTimeInput.value = String(suggestedEnd.getHours()).padStart(2, "0")
            + ":" + String(suggestedEnd.getMinutes()).padStart(2, "0");
        request("/api/state")
            .then(() => requestAnimationFrame(render))
            .catch((requestError) => showError(requestError.message));
    </script>
</body>
</html>`;
}
