# AISStream — permission blocked, replay primary

The key is configured only in the ignored local `work/live-now/.env`, under `AISSTREAM_API_KEY`. It is server-side, excluded from Git and clean deployment packages, and never named with a VITE prefix. It has not been copied to production or preview settings.

The user confirmed no retention/display permission and instructed replay to remain primary. No subscription or 48-hour AIS trial has started. The catalogue records the missing data reuse rights separately from authentication and the client code licence. `PORTWATCH_AIS_PUBLICATION_APPROVED=0` prevents the workspace client/scheduler from connecting or choosing a key-only unavailable source over replay.

Prepared acceptance path: `python scripts/verify_live_ais.py --coastal`, with JNPA, Mundra, Chennai and Paradip coastal boxes and per-port distinct hull/report counts and median qualified lag. Run only after reuse permission is recorded. A short acceptance run is not a 48-hour trial. Private durable coverage trials and a publication decision remain pending permission; there are no coverage results to report and no LIVE AIS layer is published.
