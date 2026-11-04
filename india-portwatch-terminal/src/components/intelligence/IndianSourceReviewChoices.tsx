import { useEffect } from "react";
import { useQuery } from "@tanstack/react-query";
import { useAuth } from "@/auth/AuthProvider";
import {
  getRollingIntelligence,
  type NavigationNotice,
} from "@/services/rolling-intelligence";
import { formatUtc } from "@/components/kit/primitives";

export type IndianReviewSelection = {
  noticeId: string;
  revisionId: string;
  acknowledged: true;
};
export type FrozenIndianReview = {
  noticeId: string;
  revisionId: string;
  availableAt: string;
  sourceSnapshot: Record<string, unknown>;
  declaration: { id: string; areaId: string; passageAt: string };
  originalSha256: string;
  productAsOfDate: string;
};

export function IndianSourceReviewChoices({
  vesselId,
  previous,
  value,
  onChange,
}: {
  vesselId: string;
  previous?: FrozenIndianReview[];
  value: IndianReviewSelection[];
  onChange: (next: IndianReviewSelection[]) => void;
}) {
  const { session, identityHeaders } = useAuth();
  const q = useQuery({
    queryKey: ["navigation-restrictions", identityHeaders],
    queryFn: ({ signal }) => getRollingIntelligence(identityHeaders, signal),
    enabled: session?.mode === "demo",
    retry: false,
    staleTime: 30000,
  });
  useEffect(() => onChange([]), [vesselId, onChange]);
  const voyage = q.data?.voyages.find((v) => v.id === vesselId);
  const relevant = (q.data?.notices ?? []).filter(
    (n) =>
      n.sourceFamily === "NHO_NAVAREA_VIII" &&
      (previous?.some((old) => old.noticeId === n.noticeId) ||
        (n.areaId && voyage?.declaredPassages?.[n.areaId])),
  );
  if (!relevant.length && !previous?.length && !q.isError) return null;
  const fields = [
    "status",
    "areaId",
    "portCodes",
    "coordinates",
    "providerIssueAt",
    "extractionStatus",
    "extractionVersion",
    "semanticId",
    "restriction",
  ];
  const changed = (old: FrozenIndianReview, n: NavigationNotice) =>
    fields.filter(
      (field) =>
        JSON.stringify(old.sourceSnapshot[field]) !== JSON.stringify(n[field]),
    );
  return (
    <fieldset
      className="space-y-2 border border-[var(--line)] p-3"
      data-testid="indian-review-choices"
    >
      <legend className="px-1 font-semibold">
        Indian-source review · separate from weather calculation
      </legend>
      <p>
        No source is silently adopted. Explicitly review each consumed identity
        before creating a successor. These notices add no delay, fuel, cost or
        safety benefit.
      </p>
      {q.isError ? (
        <p role="alert">
          Retained source check unavailable: {q.error.message}. Prior approvals
          remain saved; do not assume the route is clear.
        </p>
      ) : null}
      {previous
        ?.filter((old) => !relevant.some((n) => n.noticeId === old.noticeId))
        .map((old) => (
          <p key={old.noticeId} role="alert">
            Consumed identity {old.noticeId} is unavailable in the current
            retained view. It cannot be silently removed.
          </p>
        ))}
      {relevant.map((notice) => {
        const old = previous?.find((r) => r.noticeId === notice.noticeId);
        const eligible =
          notice.sourceStatus === "CURRENT_PRODUCT_DATE" &&
          notice.extractionStatus === "CONTEXT_METADATA" &&
          ["REVIEW_CONTEXT", "SOURCE_NOTICE_CANCELLED"].includes(
            notice.status ?? "",
          ) &&
          !!notice.revisionId;
        const selected = value.some(
          (r) =>
            r.noticeId === notice.noticeId &&
            r.revisionId === notice.revisionId,
        );
        return (
          <div
            key={notice.noticeId}
            className="space-y-2 border-t border-[var(--line)] pt-2 [overflow-wrap:anywhere]"
          >
            <p>
              {notice.title} · {notice.sourceStatus} / {notice.status}. Product
              as-of {notice.productAsOfDate ?? "unknown"} (date only).
            </p>
            {old ? (
              <details open={old.revisionId !== notice.revisionId}>
                <summary>Consumed revision → retained revision</summary>
                <p>
                  {old.revisionId} → {notice.revisionId ?? "unavailable"}
                </p>
                <p>
                  First available {formatUtc(old.availableAt)} →{" "}
                  {formatUtc(notice.availableAt ?? null)}.
                </p>
                <p>
                  Changed fields:{" "}
                  {changed(old, notice).join(", ") ||
                    "No structured source fields changed"}
                  .{" "}
                  {old.revisionId !== notice.revisionId
                    ? "The revised lineage requires fresh review."
                    : "Receipt validity and declaration are checked separately."}
                </p>
              </details>
            ) : (
              <p>This source has not been consumed by the opened comparison.</p>
            )}
            <label className="flex items-start gap-2">
              <input
                type="checkbox"
                disabled={!eligible}
                checked={selected}
                onChange={(event) =>
                  onChange([
                    ...value.filter((r) => r.noticeId !== notice.noticeId),
                    ...(event.target.checked
                      ? [
                          {
                            noticeId: notice.noticeId,
                            revisionId: notice.revisionId!,
                            acknowledged: true as const,
                          },
                        ]
                      : []),
                  ])
                }
              />
              I reviewed this exact source revision/status as context for my
              declared named-aid passage. I am not asserting an actual crossing
              or operational benefit.
            </label>
            {!eligible ? (
              <p>
                Active review binding is unavailable for historical,
                cancelled-unqualified, unsupported or missing evidence.
                Numerical consequences are unavailable.
              </p>
            ) : null}
          </div>
        );
      })}
    </fieldset>
  );
}
