# GDELT BigQuery — blocked, not adopted

Licence evidence: `gdelt-bigquery-gkg` in the catalogue and generated docs/DATA_SOURCES.md. Scope is GKG index dates/document links, excluding article bodies and any inference that a news mention is a confirmed incident. The official partitioned table is `gdelt-bq.gdeltv2.gkg_partitioned`.

Prepared: explicit partition and 24-hour index-time predicates; dry-run estimate; maximum bytes billed; a durable atomic daily byte reservation shared across restarts. LIMIT bounds returned rows, not query cost. Failed submitted queries retain their reservation conservatively. This cap covers this collector, not other jobs in the billing project; an account-level quota should also be set.

No paid query or 48-hour trial has started. Missing: billing project, approved daily cost/byte cap and workload credentials. Coverage and lag are unmeasured. Decision is pending those prerequisites and the full trial; the timing-out API has not been replaced with an untested billed feed.
