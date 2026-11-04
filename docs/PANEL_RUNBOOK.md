# Panel runbook

The review starts at 13:30 IST on November 4, 2026. Verification only from 12:15 to 12:30 IST. Code freezes at 12:30 IST.

## How Raghhav starts it

Open PowerShell and run:

```powershell
cd 'D:/LogisticOptimization-_Capstone_168/work/panel-review-integration'
powershell -NoProfile -ExecutionPolicy Bypass -File .\start-panel.ps1
```

Wait for **READY · open http://127.0.0.1:4264/login · SHA** followed by the commit ID. Open [local login](http://127.0.0.1:4264/login). The services keep running when you close PowerShell. The local demo uses the retained replay snapshot.

To stop both services, run this from the same folder:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\stop-panel.ps1
```

The [isolated hosted preview](https://india-portwatch-ep8o88yck-flash2404s-projects.vercel.app/login) is the fallback. Chrome may prompt you to sign in to Vercel.

## Local cache-only rehearsal

Use the review checkout with the retained public cache and installed terminal dependencies.

```powershell
python -m portwatch.demo start --mode DEMO --panel --api-port 9297 --terminal-port 4262
```

Wait for `TERMINAL READY` and verify the **REPLAY** date before opening
[the local panel](http://127.0.0.1:4262/tour). The backend denies outbound socket
access and starts with the snapshot clock pinned. If a source is unavailable,
keep its status visible. The replay smoke also blocks outbound browser requests.

```powershell
cd india-portwatch-terminal
node qa/panel-smoke.mjs --replay
```

This rehearsal opens the original role workspaces and exercises the fictional
Suez case through the existing simulation API. The connected passage flow
below uses the separate explicitly illustrative S10 fixture.

## Connected S10 demonstration

1. Open the tour, then select **Company demo**. In Company Global Eye, open
   **Global intelligence → Scenarios** and calculate **S10**.
2. Select the 10 kn option in the full comparison. Review and approve it.
3. Switch to **Port Authority**. Open **Review proposal** from **Needs your
   action**. Show the frozen assumed wait and the common modeled approach
   window, then review, approve and issue the advisory.
4. Switch to **Vessel Bridge**. Open the exact advisory from **Needs your
   action**. Show the issued comparison, acknowledge it, then accept it.
5. Check **Accepted by Vessel** on Company and Port. In Port, record the
   simulated outcome and show its label.
6. Switch to **National Command** and finish on **Research**. The tour's Decide
   chapter carries the original synthetic benchmark and its source link.

Use the accepted evidence receipt for the exact SHA, preview URL and S10
anchorage figures from the captured visitor. S10's illustrative forecast uses
a time-relative window, so a new visitor can see different absolute waits.

## Room pre-flight

At 12:30 IST, check power, display resolution, mirroring, browser zoom, the
replay date and the backup slides. Record which weather, activity and
intelligence sources the retained snapshot actually has. Scheduled refreshes
that supply the panel snapshot must complete before the verification window.
The panel rehearsal does not fetch provider data.

Reset the visitor sandbox between rehearsals. If a workspace fails to open,
reload that exact role route once. Use the isolated preview only after its
frontend and backend SHA match. Keep the offline slides and film open as a
fallback and retain all DEMO, SIMULATED and REPLAY labels.
