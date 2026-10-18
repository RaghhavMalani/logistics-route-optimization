# MPA OCEANS-X arrival API qualification

Reviewed 16 October 2026. Status: **DOCS_REVIEWED_AUTHENTICATED_RESPONSE_UNVERIFIED**. The arrival and due-arrival products remain disabled candidates. They are not a replacement restriction feed and have supplied no real operational outcomes to PortWatch.

## Public documentation inspected

| Product | Catalogue | Reviewed operation | Documented clock |
| --- | --- | --- | --- |
| Vessel Arrivals by Date | [Arrival catalogue](https://oceans-x.mpa.gov.sg/marketplace/apis/48bf4958-5970-4d53-932d-10f552bda64e/overview) | `GET https://oceans-x.mpa.gov.sg/api/v1/vessel/arrivals/1.0.0/date/{date}` | `arrivedTime` |
| Vessels Due to Arrive by Date | [Due-arrival catalogue](https://oceans-x.mpa.gov.sg/marketplace/apis/2228f8a0-6184-4d2d-a293-01ec2941752e/overview) | `GET https://oceans-x.mpa.gov.sg/api/v1/vessel/duetoarrive/1.0.0/date/{date}` | `duetoArriveTime` |

The catalogue's Try Out links expose the [arrival console](https://oceans-x.mpa.gov.sg/marketplace/apis/5c869260-a46c-4a39-accc-254e84077aad/api-console?sourceApiId=48bf4958-5970-4d53-932d-10f552bda64e) and [due-arrival console](https://oceans-x.mpa.gov.sg/marketplace/apis/9abacbec-f8f8-48b6-bb11-3a0e9cd2e16a/api-console?sourceApiId=2228f8a0-6184-4d2d-a293-01ec2941752e). Their public OpenAPI describes an `apikey` header, requests within three days before or after the current Singapore date, and hourly updates. This is advertised cadence, not a measured collection guarantee.

Both documented payloads contain an array of vessel particulars (`vesselName`, `callSign`, `imoNumber`, `flag`), a naive timestamp, `locationFrom` and `locationTo`. They do not document a stable port-call identifier, response timestamp offset, publication/first-availability clock, revision history or an all-fast event. PortWatch preserves the naive timestamp and leaves its normalized instant unknown. A valid layout or IMO checksum does not establish the event definition or entitlement.

## Access and permitted use

The [FAQ](https://oceans-x.mpa.gov.sg/faq) describes registration, an application subscription to the chosen API and issued credentials. No account was created, subscription purchased or credential requested during this qualification. The implementation does not activate collection.

The [API Terms of Service](https://oceans-x.mpa.gov.sg/api-terms-of-service) describe dataset use, adaptation and distribution subject to conditions, including conspicuous source/access-date attribution and a link to the latest terms. They reserve additional product conditions and third-party/personal-data rights. Credentials must remain confidential. These API-specific terms do not establish permission to republish unrelated MPA website articles or marine notices. Permitted public fields and any product-specific conditions remain subject to account-owner review before activation.

## Actual anonymous receipt

At **2026-10-16T12:34:54.361225+00:00**, an anonymous GET to the arrival operation for `2026-10-16` returned **HTTP 401**, JSON content type, **226 bytes**, SHA-256 **c7880eb5900fcb6518512730a7f9e93ba4a44ed0ce1d356c8ea572dae9ba5050**. This verifies the unauthenticated access barrier; it does not verify an authenticated payload, coverage or operational suitability. The request used no API key.

The ignored local review directory `work/oceans-x-qualification-20261016/` retains the access-check metadata, original anonymous response, public OpenAPI responses and inspected terms text. It contains qualification evidence rather than visitor/session records; runtime artifacts are not included in the source commit.

## Implemented boundary and next dependency

`src/portwatch_os/intelligence/oceans_x.py` provides a safe public qualification DTO, a backend-only credential-presence diagnostic, a bounded documented request builder and a strict response-layout validator. The builder does not send network requests. Unknown products, out-of-window dates, missing/invalid private headers, excessive payloads, schema changes and ambiguous timestamp-format changes fail closed. Schema candidates remain ineligible for real outcomes and numerical decisions.

The precise missing dependency is an account owner's authorized application subscription and privately configured backend `OCEANS_X_API_KEY`, followed by an actual authenticated receipt and review of timezone, arrival boundary, due/actual identity, revision clocks, quotas and permitted display fields. A key alone does not qualify the source. If qualified later, arrival evidence must be associated with a declared voyage using verified identity and passage/port context; it cannot establish a restriction or all-fast time by inference.

Focused tests use explicitly synthetic records. They exercise request bounds, Singapore date rollover, secret non-disclosure, schema drift, raw-clock preservation and the disabled outcome boundary; passing tests are not evidence that live access works.
