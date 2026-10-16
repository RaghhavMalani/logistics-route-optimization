import { useState } from "react";
import { useRouterState } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { useAuth } from "@/auth/AuthProvider";
import {
  getRollingIntelligence,
  reviewHash,
} from "@/services/rolling-intelligence";
import { Button } from "@/components/ui/button";

/** Additive queue entry over the original Company chart; no second fleet or workflow. */
export function CompanyIntelligenceQueue() {
  const { session, identityHeaders } = useAuth();
  const path = useRouterState({ select: (s) => s.location.pathname });
  const visible =
    session?.mode === "demo" &&
    session.user.role === "SHIPPING_COMPANY" &&
    path === "/company/overview";
  const [open, setOpen] = useState(false);
  const q = useQuery({
    queryKey: ["navigation-restrictions", identityHeaders],
    queryFn: ({ signal }) => getRollingIntelligence(identityHeaders, signal),
    enabled: visible,
    staleTime: 60000,
    refetchInterval: visible ? 60000 : false,
  });
  if (!visible) return null;
  const rows = (q.data?.exposureQueue ?? []).filter((r) => r.assetId);
  const actionable = rows.filter((r) => r.calculable).length;
  return (
    <section
      className="absolute bottom-[190px] right-3 z-30 max-w-[calc(100%-24px)] pointer-events-auto"
      aria-label="Company sourced review queue"
    >
      <Button
        size="sm"
        variant="outline"
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
      >
        Sourced review queue ·{" "}
        {q.isPending ? "checking" : `${actionable} calculable`}
      </Button>
      {open ? (
        <div className="mt-1 w-80 max-w-full max-h-[50vh] overflow-auto border border-[var(--line)] bg-[var(--panel)] p-3 text-[11px]">
          <p>
            Heuristic review order · declared exposure, time and source status.
            This does not estimate disruption probability.
          </p>
          {q.isError ? (
            <p role="alert">Source queue unavailable: {q.error.message}</p>
          ) : null}
          {rows.slice(0, 8).map((r) => (
            <div
              key={`${r.noticeId}-${r.vesselId}`}
              className="border-t border-[var(--line)] py-2"
            >
              <a
                href={`/company/global-eye#${reviewHash(r.noticeId, r.vesselId)}`}
                className="underline"
              >
                {r.vesselName} · {r.title}
              </a>
              <p>
                {r.status} · source {r.sourceValidity ?? r.sourceStatus}
              </p>
              <p>
                {r.calculable
                  ? "Review conditional passage comparison"
                  : r.calculationReason}
              </p>
            </div>
          ))}
          {!q.isPending && !q.isError && rows.length === 0 ? (
            <p>
              No reviewed asset relation available. Missing source coverage does
              not prove a clear route.
            </p>
          ) : null}
          <a
            href="/company/global-eye#intelligence-review"
            className="underline"
          >
            Inspect all discovered events and voyage relations
          </a>
        </div>
      ) : null}
    </section>
  );
}
