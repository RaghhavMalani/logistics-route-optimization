import { useEffect, useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { useAuth } from "@/auth/AuthProvider";
import { getJson, postJson } from "@/services/api";
import {
  fleetReviewHash,
  type NavigationNotice,
  type VoyageExposure,
} from "@/services/rolling-intelligence";
import { Button } from "@/components/ui/button";
import { formatUtc } from "@/components/kit/primitives";

export function IndianNoticeReview({
  notice,
  voyage,
  relation,
  asOf,
  onChanged,
}: {
  notice: NavigationNotice;
  voyage?: { id: string; name: string; portCode: string };
  relation?: VoyageExposure;
  asOf?: string;
  onChanged: () => void;
}) {
  const { session, identityHeaders } = useAuth();
  const [passage, setPassage] = useState("");
  const [hours, setHours] = useState("");
  const [confirmed, setConfirmed] = useState(false);
  const [newCall, setNewCall] = useState(false);
  const [requestId, setRequestId] = useState(() => crypto.randomUUID());
  useEffect(() => {
    setPassage("");
    setHours("");
    setConfirmed(false);
    setNewCall(false);
    setRequestId(crypto.randomUUID());
  }, [voyage?.id, notice.noticeId]);
  const canEdit = session?.user.role === "SHIPPING_COMPANY";
  const valid =
    !!passage &&
    hours !== "" &&
    Number.isFinite(Number(hours)) &&
    Number(hours) >= 0 &&
    Number(hours) <= 720;
  const declare = useMutation({
    mutationFn: () =>
      postJson<{ plan: { operationalEpisode: { id: string } } }>(
        "/intelligence/indian-passage-plan",
        {
          vesselId: voyage?.id,
          noticeId: notice.noticeId,
          portCode: "INPRT",
          direction: "INBOUND",
          passageAt: passage + ":00Z",
          postPassageHours: Number(hours),
          declarationConfirmed: confirmed,
        },
        identityHeaders,
      ),
    onSuccess: onChanged,
  });
  const begin = useMutation({
    mutationFn: () =>
      postJson(
        "/intelligence/operational-calls",
        {
          vesselId: voyage?.id,
          requestedArrival: new Date(
            Date.parse(passage + ":00Z") + Number(hours) * 3600000,
          ).toISOString(),
          requestId,
          newCallConfirmed: newCall,
        },
        identityHeaders,
      ),
    onSuccess: () => {
      setNewCall(false);
      onChanged();
    },
  });
  const audit = useMutation({
    mutationFn: () =>
      getJson<unknown>(
        `/intelligence/indian-source-audit?${new URLSearchParams({ noticeId: notice.noticeId, ...(asOf ? { asOf } : {}) })}`,
        identityHeaders,
      ),
    onSuccess: (data) => {
      const url = URL.createObjectURL(
        new Blob([JSON.stringify(data, null, 2)], { type: "application/json" }),
      );
      const link = document.createElement("a");
      link.href = url;
      link.download = `nho-source-audit-${notice.providerNoticeId?.replaceAll("/", "-")}.json`;
      link.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    },
  });
  const episode = declare.data?.plan.operationalEpisode.id;
  return (
    <section
      className="my-3 space-y-3 border border-[var(--line)] p-3 [overflow-wrap:anywhere]"
      data-testid="indian-source-review"
    >
      <p className="font-semibold">
        {notice.title} · {notice.sourceStatus}
      </p>
      <p>
        {notice.restriction} This family has no numerical closure or waiting
        model.
      </p>
      <p>
        Original verification: {notice.originalAvailability ?? "Unavailable"}.
        Full-document download is not enabled.
      </p>
      <dl className="grid grid-cols-[auto_minmax(0,1fr)] gap-x-3 gap-y-1">
        <dt>Product as-of</dt>
        <dd>{notice.productAsOfDate ?? "Unknown"} · date only</dd>
        <dt>First receipt</dt>
        <dd>
          {formatUtc(
            notice.sourceFirstReceivedAt ?? notice.availableAt ?? null,
          )}
        </dd>
        <dt>Last successful receipt</dt>
        <dd>{formatUtc(notice.lastSuccessfulReceiptAt ?? null)}</dd>
        <dt>Last check</dt>
        <dd>{formatUtc(notice.checkedAt)}</dd>
      </dl>
      {notice.sourceStatus !== "CURRENT_PRODUCT_DATE" ? (
        <p role="status">
          This product does not establish today's in-force condition. A newer
          download does not update its document date. Current-source numerical
          acceptance remains pending.
        </p>
      ) : null}
      <p>{relation?.reason ?? "No declared exposure basis available."}</p>
      <details>
        <summary className="cursor-pointer">
          Source identity, revisions and use limits
        </summary>
        <div className="mt-2 space-y-2">
          <p>
            Issuer:{" "}
            {notice.sourceUse?.attribution ??
              "Indian Naval Hydrographic Department"}
            . Notice {notice.noticeRef}; pages{" "}
            {notice.documentPages?.join(", ") ?? "unavailable"}.
          </p>
          <p>
            Issuer DTG {formatUtc(notice.providerIssueAt ?? null)}. Publication
            instant is unavailable; product as-of remains date-only.
          </p>
          <p>
            Revision {notice.revisionId ?? "unknown"}; parser{" "}
            {notice.extractionVersion ?? "unknown"}; SHA-256{" "}
            {notice.responseSha256 ?? "unavailable"}.
          </p>
          <p>
            Latest confirming product SHA-256{" "}
            {notice.latestResponseSha256 ?? "unavailable"}; pages{" "}
            {notice.latestDocumentPages?.join(", ") ?? "unavailable"}. Product
            date and current check qualify this product separately from the
            original notice interpretation.
          </p>
          <p>{notice.coordinates?.basis ?? "Reviewed geometry unavailable."}</p>
          <p>
            {notice.sourceUse?.basis}. Actual navigation-aid condition, passage,
            delay, fuel, cost and savings remain unverified.
          </p>
        </div>
      </details>
      <div className="flex flex-wrap gap-2">
        <a
          className="underline"
          href={notice.source}
          target="_blank"
          rel="noreferrer"
        >
          Issuer document and page reference
        </a>
        <Button
          size="sm"
          variant="outline"
          disabled={audit.isPending}
          onClick={() => audit.mutate()}
        >
          Download source audit
        </Button>
      </div>
      {canEdit &&
      voyage &&
      notice.areaId === "NHO_PARADIP_DGPS" &&
      notice.extractionStatus === "CONTEXT_METADATA" ? (
        <details>
          <summary className="cursor-pointer">
            Declare this owned voyage's Paradip approach
          </summary>
          <div className="mt-3 space-y-3">
            <p>
              This explicit declaration changes {voyage.name}'s destination to
              INPRT and its ETA from your passage/continuation assumptions. It
              does not calculate NHO delay.
            </p>
            <label className="block">
              Planned named-aid passage (UTC)
              <input
                className="mt-1 block max-w-full rounded border border-[var(--line)] bg-[var(--panel-2)] p-2"
                type="datetime-local"
                aria-label="Indian passage UTC"
                value={passage}
                onChange={(e) => {
                  setPassage(e.target.value);
                  setConfirmed(false);
                }}
              />
            </label>
            <label className="block">
              Declared onward hours to requested arrival
              <input
                className="mt-1 block max-w-full rounded border border-[var(--line)] bg-[var(--panel-2)] p-2"
                type="number"
                min="0"
                max="720"
                aria-label="Indian onward hours"
                value={hours}
                onChange={(e) => {
                  setHours(e.target.value);
                  setConfirmed(false);
                }}
              />
            </label>
            <label className="flex items-start gap-2">
              <input
                type="checkbox"
                checked={confirmed}
                onChange={(e) => setConfirmed(e.target.checked)}
              />
              These are fictional operator-declared route, destination and
              timing assumptions. No observed crossing or source-predicted delay
              is asserted.
            </label>
            <Button
              size="sm"
              disabled={!valid || !confirmed || declare.isPending}
              onClick={() => declare.mutate()}
            >
              Declare fictional Paradip approach
            </Button>
            {declare.isSuccess ? (
              <p role="status">
                Declaration retained.{" "}
                <a
                  className="underline"
                  href={`/company/global-eye#${fleetReviewHash({ kind: "CURRENT_INPUTS", vesselId: voyage.id, episodeId: episode })}`}
                >
                  Review current inputs for this exact voyage
                </a>
                . Explicit source acknowledgement is available only for
                qualified current context.
              </p>
            ) : null}
            <details>
              <summary>Explicit distinct next call</summary>
              <label className="my-2 flex gap-2">
                <input
                  type="checkbox"
                  checked={newCall}
                  onChange={(e) => setNewCall(e.target.checked)}
                />
                Start a distinct call; this is not an ETA edit. Prior
                comparisons and advisories stay inspectable.
              </label>
              <Button
                size="sm"
                variant="outline"
                disabled={!valid || !newCall || begin.isPending}
                onClick={() => begin.mutate()}
              >
                Create distinct next call
              </Button>
            </details>
          </div>
        </details>
      ) : null}
      {declare.isError || begin.isError || audit.isError ? (
        <p role="alert">
          {declare.error?.message ??
            begin.error?.message ??
            audit.error?.message}
        </p>
      ) : null}
    </section>
  );
}
