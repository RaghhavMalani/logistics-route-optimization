# Reviewed report / primary-document announcement family

October 25, 2026. `GAC_EASTHAM_NOTICE_ANNOUNCEMENT_V1` extends the existing public shared-feedback ledger and six-hour reconciliation worker. It creates no scheduler, event-to-delay coefficient, operational measurement or source-weight policy.

## Sources and supported meaning

- Secondary report: [GAC Hot Port News, Upcoming lock closures](https://www.gac.com/hot-port-news/upcoming-lock-closures).
- Primary source: [Peel Ports marine catalogue](https://www.peelports.com/marine/our-ports/manchester-ship-canal/) and the existing [MNTM 2026-18 PDF](https://www.peelports.com/media/joolgbfb/mntm-2026-18-temporary-closures-of-eastham-80-lock.pdf).

The only assessed predicate is `AUTHORITY_NOTICE_ANNOUNCED_LOCK_CLOSURE`: the authority announced an Eastham 80-foot Lock closure during the explicit calendar period. Three 2026 periods are extracted separately. Calendar dates remain date-only; the authority's midnight normalization is not relabelled as a measured work-start time. GAC publication time remains unknown. Primary publication is the notice's printed date, without an invented intraday time.

`gac-eastham-announcement-v1` accepts only the pinned endpoint's reviewed lock wording, three explicit September/October/November date ranges and accompanying BST/GMT tide rows, and the unaffected-lock qualification. Missing, malformed, duplicate or cancellation-qualified article grammar fails closed with a retained diagnostic. Scripts/styles do not supply article text. A hash-verified primary PDF is reparsed with the existing notice parser, and all parsed facts plus the canonical revision hash must match its record.

Whole-canal closure prose, vessel suitability and operational-tide accuracy are not scored by this family. Actual closure and shipping consequences remain separate unresolved questions. In particular, the existing November numerical-planning exclusion remains: the notice's withdrawal instant precedes its first stated operational tide. Announcement corroboration does not override that calculation guard.

## Lineage, availability and revisions

GAC and the notice share the originating lineage `Peel Ports:MNTM 2026-18`. They are separate documents, not independent reporting confirmations. The primary-document verification exception requires the exact reviewed family, attributed secondary role, primary-authority role, distinct report identities and original hashes, exact predicate/entity/location/period, and matching lineage. An authority's own report/revision cannot self-confirm. A successful assessment reports `independentReportingConfirmations=0` and establishes neither occurrence nor operational effect.

Original response bytes and request/product identity reuse the existing archive/receipt contract. First receipt and interpretation availability are distinct. Reinterpreting an old original becomes application knowledge at interpretation time; it is not backdated to publisher time. Exact retries reuse claims and evidence. Cosmetic article changes do not create independent targets. Semantic revisions remain distinct records under the existing explicit supersession/as-of policy; unsupported new wording is not guessed into a cancellation.

Hash-verified explicit cancellation of MNTM 2026-18 adds cancellation evidence to the exact derived announcement targets independently of GAC fetch availability. The earlier announcement can remain corroborated while applicability becomes superseded. Feed disappearance is not cancellation. No `ACTUAL_OPERATIONAL_RECORD` is created by these paths.

GAC asks for attribution to GAC Hot Port News when quoting. The retained claim uses a short attributed excerpt and extracted facts. Full-response public republication permission is not established; metadata identifies the original as a local research archive. Original-response archives and fixture/runtime ledgers are excluded from Git.

## Bounded real attempt and validation

At **2026-10-25T09:29:26Z**, the direct GAC collector request returned **HTTP 403**. An indexed readable page identified compatible announced periods, but indexed/DOM text was not relabelled as original HTTP bytes. The official PDF returned HTTP 200, 204,725 bytes, SHA-256 `04a5847e17eae7787aa2feecd017039e6ab3020f9070d314319f15d5ec63e332`; the existing parser accepted its three windows and printed publication date of July 15, 2026. These attempt artifacts remain under ignored `work/feedback-reconciliation-20261025/news-attempt/`.

Consequently this attempt supplies **no genuinely resolved GAC report/authority pair**: the secondary original is unavailable. The software path remains usable and unresolved rather than fabricating completion. Nineteen focused synthetic tests cover grammar, precision, date/role/lineage scope, source/hash binding, first receipt, retries/restart, as-of evidence, corrupt primary originals, explicit cancellation during provider failure, and the separate announcement/occurrence/operational boundary. They are software evidence, not measured news accuracy or shipping benefit.
