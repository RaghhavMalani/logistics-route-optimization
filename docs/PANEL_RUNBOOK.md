# Panel runbook

Verified production release: 6 November 2026 IST. Open [the main terminal](https://india-portwatch.vercel.app/login) first. Production Vercel and Railway both serve SHA `7bdeb9690b7c501ef147ad36cf04f4f173900c0f`. The complete role handoff path passed at 1366×768 and 1280×720, including Tour, Research and the ×60 split twin. Release evidence and rollback commands are in `work/integration/RESEARCH_RELEASE_STATUS.md` and `work/integration/ROLLBACK.md`.

## How Raghhav starts it

Open PowerShell and run:

```powershell
cd 'D:/LogisticOptimization-_Capstone_168/work/integrated-20261104'
powershell -NoProfile -ExecutionPolicy Bypass -File .\start-panel.ps1
```

Wait for **READY · open http://127.0.0.1:4264/login · SHA** followed by the commit ID. Open [local login](http://127.0.0.1:4264/login). The services keep running when you close PowerShell. The local demo uses the retained replay snapshot.

To stop both services, run this from the same folder:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\stop-panel.ps1
```

The [isolated hosted preview](https://india-portwatch-58inua1ac-flash2404s-projects.vercel.app/login) and [local login](http://127.0.0.1:4264/login) are fallbacks. Chrome may prompt you to sign in to Vercel for the preview. The preview remains isolated at SHA `2e43af315d75faa5d138830b274dc6406ef4df1c`; the local rehearsal checkout reports `e33068c58183b8adee0d6ce6b86f60997337d1ad` and stays running as detached processes.

## Demo click path

1. Open **Company demo**. In Fleet Command, open **Scenarios**, select **S10 · Slow steaming to the same approach window**, tick the fictional-input checkbox, and choose **Calculate selected demonstration**. This saves the comparison for the fresh visitor.
2. In the same tab, open **Fleet intelligence → Fleet review queue → PW Meridian → Open saved comparison**. Select the **10 kn** alternative, then **Continue to Decide → Mark reviewed → Approve**. If you return to Fleet Command to show **Waiting on Port**, choose **Close fleet review** before switching roles.
3. Use the **Demo role** menu to switch to **Port Authority**. Open **Needs your action → Review proposal**, then **Review Company weather proposal → Continue to Decide → Mark reviewed → Approve → Hand into advisory boundary**. In **Needs action**, open the PW Meridian advisory and choose **Open for review → Approve and issue**. The card stays open between the two actions.
4. Switch to **Vessel Bridge**. Choose **Needs your action → Open advisory → Acknowledge receipt → Accept**.
5. Switch to **Port Authority**. From **Needs your action**, open **Review accepted proposal**. Show the **Decide** tab and choose **Run frozen demo outcome**.
6. Switch to **Fleet Command** and show **Outcome completed**. **Open advisory** goes to the exact record.
7. Switch to **National Command**, then open [Research](http://127.0.0.1:4264/research) and show the **Decision policy benchmark**.

S10 is a fictional comparison. Both options reach the same modeled approach window, and the illustrative anchorage wait differs by 4.00 h. The local clock is pinned to the retained replay snapshot. The hosted fixture uses a time-relative window and may show different absolute waits.

## Release and fallback

The launcher prints the local release SHA. The release receipt in the main project's work/panel/final/hosted-binding.json records the exact hosted frontend and backend SHA and deployment IDs. The dated copy of this runbook in work/panel/PANEL_RUNBOOK.md records the verified URL.

Open work/panel/backup/slides.html offline. Use Left or Right to move one slide and Home or End to jump. The existing backup film is in the same directory.

## Rehearsal checks

Run from the review checkout after starting the panel:

```powershell
$env:PORTWATCH_PANEL_ORIGIN = 'http://127.0.0.1:4264'
$env:PORTWATCH_PANEL_API = 'http://127.0.0.1:9299/api'
Set-Location india-portwatch-terminal
node qa/panel-smoke.mjs --panel --headed
node qa/panel-smoke.mjs --replay
```

Before presenting, check projector size, browser zoom, the REPLAY badge and offline slides.
