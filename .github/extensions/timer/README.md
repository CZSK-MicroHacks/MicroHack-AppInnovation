# Timer canvas

This project-scoped Copilot canvas provides a minimal large-screen countdown timer. Use the
**Duration** / **End at** switch to choose an entry mode, then use **Start**, **Stop**, or
**Reset**. End-time timers calculate the required duration and start immediately. The
remaining-time orbit shrinks continuously as the countdown runs.

## Run and test

1. Reload Copilot extensions after changing files in this directory.
2. Open the **Timer** canvas.
3. Set a duration and verify Start, Stop, Reset, `Space` (start/stop), and `R` (reset).
4. Switch to **End at**, set a future time, and verify the timer starts immediately; past
   times should show an error instead of rolling over to tomorrow.

The agent-facing canvas actions can also read state, set a duration in seconds, set a
future local end time for today, start, stop, and reset the current timer.
