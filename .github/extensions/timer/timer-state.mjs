const MAX_DURATION_SECONDS = 359999;
const timers = new Map();

/**
 * Validates and converts a duration in seconds to milliseconds.
 */
function durationToMilliseconds(seconds) {
    if (!Number.isInteger(seconds) || seconds < 1 || seconds > MAX_DURATION_SECONDS) {
        throw new Error(`Duration must be a whole number from 1 to ${MAX_DURATION_SECONDS} seconds.`);
    }
    return seconds * 1000;
}

/**
 * Creates timer state on first access and otherwise returns the existing state.
 */
function getTimer(timerId, initialSeconds = 300) {
    let timer = timers.get(timerId);
    if (!timer) {
        const durationMs = durationToMilliseconds(initialSeconds);
        timer = {
            durationMs,
            endsAt: null,
            remainingMs: durationMs,
            running: false,
        };
        timers.set(timerId, timer);
    }
    return timer;
}

/**
 * Applies elapsed wall-clock time and returns a client-safe state snapshot.
 */
function snapshot(timer) {
    const serverNow = Date.now();

    if (timer.running && timer.endsAt !== null) {
        timer.remainingMs = Math.max(0, timer.endsAt - serverNow);
        if (timer.remainingMs === 0) {
            timer.running = false;
            timer.endsAt = null;
        }
    }

    return {
        durationMs: timer.durationMs,
        endsAt: timer.endsAt,
        remainingMs: timer.remainingMs,
        running: timer.running,
        serverNow,
    };
}

/**
 * Returns the current state for a stable timer domain ID.
 */
export function getTimerState(timerId, initialSeconds = 300) {
    return snapshot(getTimer(timerId, initialSeconds));
}

/**
 * Replaces a timer duration and leaves it stopped at the new full duration.
 */
export function setTimerDuration(timerId, seconds) {
    const durationMs = durationToMilliseconds(seconds);
    const timer = getTimer(timerId, seconds);
    timer.durationMs = durationMs;
    timer.remainingMs = durationMs;
    timer.running = false;
    timer.endsAt = null;
    return snapshot(timer);
}

/**
 * Sets and starts a timer that finishes at a future local time today.
 */
export function setTimerEndTime(timerId, time) {
    const match = /^([01]\d|2[0-3]):([0-5]\d)$/.exec(time);
    if (!match) {
        throw new Error("End time must use the HH:MM format.");
    }

    const now = new Date();
    const target = new Date(now);
    target.setHours(Number(match[1]), Number(match[2]), 0, 0);
    if (target <= now) {
        throw new Error("Choose an end time later today.");
    }

    const timer = getTimer(timerId);
    timer.durationMs = target.getTime() - now.getTime();
    timer.remainingMs = timer.durationMs;
    timer.running = true;
    timer.endsAt = target.getTime();
    return snapshot(timer);
}

/**
 * Starts or resumes a timer, resetting a completed timer before starting it.
 */
export function startTimer(timerId) {
    const timer = getTimer(timerId);
    snapshot(timer);
    if (timer.remainingMs === 0) {
        timer.remainingMs = timer.durationMs;
    }
    if (!timer.running) {
        timer.running = true;
        timer.endsAt = Date.now() + timer.remainingMs;
    }
    return snapshot(timer);
}

/**
 * Stops a timer while preserving its current remaining time.
 */
export function stopTimer(timerId) {
    const timer = getTimer(timerId);
    snapshot(timer);
    timer.running = false;
    timer.endsAt = null;
    return snapshot(timer);
}

/**
 * Returns a timer to its configured duration and leaves it stopped.
 */
export function resetTimer(timerId) {
    const timer = getTimer(timerId);
    timer.remainingMs = timer.durationMs;
    timer.running = false;
    timer.endsAt = null;
    return snapshot(timer);
}
