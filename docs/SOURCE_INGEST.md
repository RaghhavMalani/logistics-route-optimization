# Source ingest and trials

The standalone ingest worker writes a dated snapshot and its successful
attempt in one Postgres transaction. A failed fetch records the failure class
and preserves the last good snapshot. Each source has its own schedule,
exponential retry delays and a circuit breaker that survives a worker restart.
The worker takes a Postgres advisory lock per trial and product.

The Sources page and the Data now summary read retained metadata. The public
endpoint only serves health metrics and can read the published snapshot scope
for a product after publication approval. Private trial records stay in a
separate scope and should use a separate database. Existing retained Paradip
port activity supplies the IMF data date and age during the migration.

## Run and inspect a trial

1. Check the exact product and its retention rights in
   [the licence catalogue](DATA_SOURCES.md).
2. Set `PORTWATCH_SOURCE_SNAPSHOT_URL` to the dedicated Postgres trial
   database. A local SQLite file is supported for development and single-worker
   trials. The worker creates its own journal table. The API can use a
   read-only database role.
3. Pick a unique trial name and record the UTC start time with its offset.
   Run `python -m scripts.source_ingest run <product> --trial <name> --start <ISO-UTC-start>`.
   The process ends at start plus 48 hours. Reuse the same values to resume.
4. Run `python -m scripts.source_ingest report <product> --trial <name> --start <ISO-UTC-start>`
   and save the JSON under `work/sources/`. Use `probe` for one due attempt.
   The report lists successful attempts, coverage, lag basis and the longest
   gap between attempts. A trial with incomplete coverage needs review even
   if its wall-clock window has elapsed.
5. Record a human adopt or reject decision with the trial report, terms and
   attribution. Require the [decision policy gate](DECISION_POLICY_GATE.md)
   before using any new input to change a decision.

Trial collectors are currently available for NHO warning metadata, ECB reference
rates via Frankfurter, and GDELT discovery links. Forecast valid times, HTTP
receipts and issue times describe different things. For date-only products, the
report measures from UTC midnight on the reference date and labels the basis.
GDELT lag uses the index-seen timestamp. A source without a qualified timestamp
has unmeasured lag. A successful poll with zero qualifying rows remains visible
as zero coverage.

### AIS acceptance

After the provider confirms retention and display rights, set the server-side
key and use `python scripts/verify_live_ais.py --coastal --wait 120` in the
reviewed licence mode. The four fixed boxes include the approaches and
anchorages at JNPA, Mundra, Chennai and Paradip. The acceptance script prints
distinct hulls, qualified report counts and per-port median lag without hull
identifiers. This short acceptance check precedes the 48-hour trial. The
trial needs a separate collection session and a coverage review against the
replay before any observed layer can be published.
