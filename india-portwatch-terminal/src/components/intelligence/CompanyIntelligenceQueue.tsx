import { useEffect, useState } from "react";
import { useRouterState } from "@tanstack/react-router";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useAuth } from "@/auth/AuthProvider";
import { formatUtc, Pill } from "@/components/kit/primitives";
import {
  FLEET_TRIAGE_CATEGORIES,
  fleetReviewHash,
  getFleetDecisionTriage,
  reviewHash,
  type FleetDecisionRow,
  type FleetTriageCategory,
} from "@/services/rolling-intelligence";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogClose,
  DialogDescription,
  DialogOverlay,
  DialogPortal,
  DialogTitle,
} from "@/components/ui/dialog";
import * as DialogPrimitive from "@radix-ui/react-dialog";

const LABELS: Record<FleetTriageCategory, string> = {
  CURRENT_CONDITIONAL_FAILURE: "Current conditional failure",
  REASSESSMENT: "Reassessment needed",
  COMPANY_ACTION: "Company action",
  WAITING_OTHER_ROLE: "Waiting on another role",
  INCOMPLETE_ASSESSMENT: "Incomplete assessment",
  MONITORED: "Monitored within assessed scope",
};
const ROLE_LABELS: Record<string, string> = {
  SHIPPING_COMPANY: "Company",
  PORT_AUTHORITY: "Port",
  VESSEL_OPERATOR: "Vessel",
  NATIONAL_ADMIN: "Admin",
};
const PAGE_SIZE = 6;

function signedHours(value: number | null | undefined) {
  return value != null && Number.isFinite(value)
    ? `${value > 0 ? "+" : ""}${Number(value.toFixed(2))} h`
    : "Unknown";
}

function TriageCard({
  row,
  selected,
  onOpen,
}: {
  row: FleetDecisionRow;
  selected: boolean;
  onOpen: () => void;
}) {
  const current = row.currentPlan;
  const action = row.navigation;
  const target = `/company/global-eye#${fleetReviewHash(action)}`;
  return (
    <article
      className={`min-w-0 space-y-2 rounded border border-[var(--line)] p-3 [overflow-wrap:anywhere] ${selected ? "bg-[var(--panel-2)]" : ""}`}
      data-testid="fleet-triage-row"
      data-row-id={row.id}
      data-selected={selected}
    >
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <strong className="text-sm">
          {row.vessel.name} → {row.destinationPort ?? "destination unknown"}
        </strong>
        <Pill
          tone={
            row.primaryCategory === "CURRENT_CONDITIONAL_FAILURE"
              ? "crit"
              : row.primaryCategory === "MONITORED"
                ? "info"
                : "warn"
          }
        >
          {LABELS[row.primaryCategory]}
        </Pill>
      </div>
      <p>
        {row.reasons[0]?.text ??
          "Assessment basis is unavailable; no conclusion about operational readiness."}
      </p>
      <p className="text-[var(--text-2)]">
        Plan:{" "}
        {current.basis === "BASELINE_NOT_APPROVED"
          ? "BASELINE / NOT APPROVED"
          : current.basis.replaceAll("_", " ")}
        {current.optionId ? ` · option ${current.optionId}` : ""}
      </p>
      <p>
        Journey: {row.workflow.stage.replaceAll("_", " ")} · Next:{" "}
        {row.workflow.nextRole
          ? (ROLE_LABELS[row.workflow.nextRole] ?? row.workflow.nextRole)
          : "No pending role action identified"}
      </p>
      <p>Evidence: {row.freshness.status.replaceAll("_", " ")}</p>
      {row.deadline ? (
        <p>
          {row.deadline.kind.replaceAll("_", " ")}: {formatUtc(row.deadline.at)}{" "}
          · {signedHours(row.deadline.hoursRemaining)} remaining
          {row.deadline.hoursRemaining < 0
            ? " (overdue scheduled time; no actual execution inferred)"
            : ""}
        </p>
      ) : (
        <p className="text-[var(--text-2)]">
          Applicable action deadline unknown.
        </p>
      )}
      {row.cargo ? (
        <p>
          {row.cargo.mustMeet ? "Required" : "Optional"} cargo ·{" "}
          {row.cargo.status.replaceAll("_", " ")} · cutoff{" "}
          {row.cargo.cutoffAt ? formatUtc(row.cargo.cutoffAt) : "unknown"} ·
          signed slack {signedHours(row.cargo.slackHours)} under declared
          assumptions
        </p>
      ) : null}
      <a
        href={target}
        onClick={onOpen}
        className="inline-block rounded border border-[var(--line-strong)] px-2 py-1 underline underline-offset-2 focus-visible:outline focus-visible:outline-2 focus-visible:outline-[var(--accent)]"
        data-testid="fleet-triage-action"
      >
        {action.kind === "SAVED_COMPARISON"
          ? "Open saved comparison"
          : "Review current inputs"}
      </a>
      <details>
        <summary className="cursor-pointer focus-visible:outline focus-visible:outline-2">
          Reasons and retained plan basis
        </summary>
        <div className="mt-2 space-y-2 text-[var(--text-2)]">
          {row.reasons.map((reason, index) => (
            <p key={`${reason.code}-${index}`}>
              <strong>{reason.code.replaceAll("_", " ")}</strong>: {reason.text}{" "}
              Basis: {reason.basis}
              {reason.evidenceId ? ` · evidence ${reason.evidenceId}` : ""}
            </p>
          ))}
          {row.freshness.reasons.map((reason, index) => (
            <p key={`fresh-${reason.code}-${index}`}>
              {reason.text} Basis: {reason.basis}
            </p>
          ))}
          <p>
            Company comparison: {current.decisionId ?? "not established"};
            option: {current.optionId ?? "not established"}. Approval:{" "}
            {current.approvalStatus ?? "not established"}.
          </p>
          <p>
            Call: {row.episode?.id ?? "missing current-call basis"}; voyage leg:{" "}
            {row.episode?.voyageLegId ?? "unavailable"}.
          </p>
          <p>
            Engine recommendation:{" "}
            {row.recommendation?.optionId ?? "unavailable"}. A recommendation or
            highlighted alternative does not identify the approved current plan.
          </p>
          {row.deadline ? <p>Time basis: {row.deadline.basis}</p> : null}
          {row.cargo ? <p>Cargo basis: {row.cargo.basis}</p> : null}
          {row.missingCoverage.length ? (
            <p>Missing coverage: {row.missingCoverage.join("; ")}</p>
          ) : null}
          {row.candidateComparisons.length ? (
            <div>
              <p>Separate retained candidates; none is silently adopted:</p>
              {row.candidateComparisons.map((candidate) => (
                <p key={candidate.decisionId}>
                  <a
                    className="underline"
                    href={`/company/global-eye#${fleetReviewHash({ kind: "SAVED_COMPARISON", vesselId: row.vessel.id, episodeId: row.episode?.id, decisionId: candidate.decisionId, optionId: candidate.optionId })}`}
                  >
                    Inspect candidate {candidate.decisionId}
                  </a>{" "}
                  · {candidate.basis ?? candidate.workflow ?? "Requires review"}
                </p>
              ))}
            </div>
          ) : null}
          <p>
            Projection: {formatUtc(row.asOf)}. No alert establishes a safe
            route, terminal readiness, confirmed connection, booking or real
            outcome.
          </p>
        </div>
      </details>
    </article>
  );
}

/** Derived worklist over the original chart. Provider leads remain separate. */
export function CompanyIntelligenceQueue() {
  const { session, identityHeaders } = useAuth();
  const path = useRouterState({ select: (state) => state.location.pathname });
  const visible =
    session?.mode === "demo" &&
    session.user.role === "SHIPPING_COMPANY" &&
    path === "/company/overview";
  const visitorKey = session?.demoId ?? session?.issuedAt ?? "no-session";
  const storageKey = `portwatch:fleet-triage-view:v1:${visitorKey}`;
  const [open, setOpen] = useState(false);
  const [filter, setFilter] = useState<FleetTriageCategory | "ALL">("ALL");
  const [page, setPage] = useState(0);
  const [selectedRow, setSelectedRow] = useState("");
  const [restored, setRestored] = useState(false);
  const queries = useQueryClient();
  const q = useQuery({
    queryKey: ["fleet-decision-triage", visitorKey],
    queryFn: ({ signal }) => getFleetDecisionTriage(identityHeaders, signal),
    enabled: visible,
    retry: false,
    staleTime: 0,
    refetchOnMount: "always",
    refetchInterval: visible ? 30000 : false,
  });
  useEffect(() => {
    try {
      const saved = JSON.parse(
        sessionStorage.getItem(storageKey) ?? "null",
      ) as {
        open?: boolean;
        filter?: string;
        page?: number;
        selectedRow?: string;
      } | null;
      setOpen(Boolean(saved?.open) || window.location.hash === "#fleet-queue");
      setFilter(
        saved?.filter &&
          FLEET_TRIAGE_CATEGORIES.includes(saved.filter as FleetTriageCategory)
          ? (saved.filter as FleetTriageCategory)
          : "ALL",
      );
      setPage(
        Number.isInteger(saved?.page) && (saved?.page ?? -1) >= 0
          ? saved!.page!
          : 0,
      );
      setSelectedRow(
        typeof saved?.selectedRow === "string" ? saved.selectedRow : "",
      );
    } catch {
      /* Blocked storage only loses UI context, never decision records. */
    }
    setRestored(true);
  }, [storageKey]);
  useEffect(() => {
    if (!restored) return;
    try {
      sessionStorage.setItem(
        storageKey,
        JSON.stringify({ open, filter, page, selectedRow }),
      );
    } catch {
      /* Optional view preference. */
    }
  }, [storageKey, open, filter, page, selectedRow, restored]);
  useEffect(() => {
    const refresh = () => {
      void queries.invalidateQueries({
        queryKey: ["fleet-decision-triage", visitorKey],
      });
    };
    const close = () => setOpen(false);
    window.addEventListener("portwatch:workflow-changed", refresh);
    window.addEventListener("portwatch:focus-constraint", close);
    return () => {
      window.removeEventListener("portwatch:workflow-changed", refresh);
      window.removeEventListener("portwatch:focus-constraint", close);
    };
  }, [queries, visitorKey]);
  if (!visible) return null;
  const rows = q.data?.rows ?? [];
  const filtered =
    filter === "ALL"
      ? rows
      : rows.filter((row) => row.primaryCategory === filter);
  const pages = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
  const displayedPage = Math.min(page, pages - 1);
  const shown = filtered.slice(
    displayedPage * PAGE_SIZE,
    (displayedPage + 1) * PAGE_SIZE,
  );
  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <section
        className="pointer-events-auto absolute bottom-[190px] right-3 z-30 max-w-[calc(100%-24px)]"
        aria-label="Company fleet review queue"
      >
        <Button
          size="sm"
          variant="outline"
          data-fleet-triage-trigger
          aria-expanded={open}
          onClick={() => setOpen(true)}
        >
          Fleet review queue ·{" "}
          {q.isPending
            ? "checking"
            : q.data
              ? `${q.data.coverage.ownedVoyages} voyages`
              : "unavailable"}
        </Button>
      </section>
      <DialogPortal>
        <DialogOverlay className="z-[100]" />
        <DialogPrimitive.Content
          className="pointer-events-auto fixed inset-x-[4vw] top-[6vh] bottom-[6vh] z-[101] flex min-w-0 flex-col rounded border border-[var(--line-strong)] bg-[var(--panel)] text-xs shadow-2xl [overflow-wrap:anywhere]"
          data-testid="company-fleet-triage"
          onCloseAutoFocus={(event) => {
            event.preventDefault();
            document
              .querySelector<HTMLElement>("[data-fleet-triage-trigger]")
              ?.focus();
          }}
          onOpenAutoFocus={(event) => {
            const target = selectedRow
              ? document.querySelector<HTMLElement>(
                  `[data-row-id="${CSS.escape(selectedRow)}"] [data-testid="fleet-triage-action"]`,
                )
              : null;
            if (target) {
              event.preventDefault();
              target.focus();
            }
          }}
        >
          <div className="flex shrink-0 items-start justify-between gap-3 border-b border-[var(--line)] p-3">
            <div className="min-w-0">
              <DialogTitle className="text-sm">
                Fleet decision review
              </DialogTitle>
              <DialogDescription>
                Current-call plans, evidence and the next responsible role.
                Read-only review order; no probability, loss estimate or
                automatic approval.
              </DialogDescription>
            </div>
            <DialogClose asChild>
              <Button size="sm" variant="ghost" className="shrink-0">
                Close fleet review
              </Button>
            </DialogClose>
          </div>
          <div
            className="min-h-0 space-y-3 overflow-y-auto p-3"
            data-testid="fleet-triage-scroll"
          >
            <div className="flex flex-wrap items-center gap-2">
              <label className="min-w-0">
                Show{" "}
                <select
                  className="max-w-full rounded border border-[var(--line)] bg-[var(--panel-2)] p-1"
                  aria-label="Fleet review category"
                  value={filter}
                  onChange={(event) => {
                    setFilter(event.target.value as typeof filter);
                    setPage(0);
                  }}
                >
                  <option value="ALL">All current voyages</option>
                  {FLEET_TRIAGE_CATEGORIES.map((category) => (
                    <option key={category} value={category}>
                      {LABELS[category]} ({q.data?.counts[category] ?? "—"})
                    </option>
                  ))}
                </select>
              </label>
              <Button
                size="sm"
                variant="outline"
                disabled={q.isFetching}
                onClick={() => void q.refetch()}
              >
                Refresh retained state
              </Button>
            </div>
            {q.isPending ? (
              <p role="status">Reading retained fleet and workflow records…</p>
            ) : null}
            {q.isFetching && q.data ? (
              <p role="status">
                Refreshing retained state. Results below remain the previous
                projection from {formatUtc(q.data.asOf)}.
              </p>
            ) : null}
            {q.isError ? (
              <p role="alert">
                Fleet projection unavailable: {q.error.message}
                {q.data
                  ? ` Retaining the previous results from ${formatUtc(q.data.asOf)}; they are not newly verified.`
                  : " No fleet-clear conclusion is available."}
              </p>
            ) : null}
            {q.data ? (
              <>
                <p>
                  Projected {formatUtc(q.data.asOf)} ·{" "}
                  {q.data.coverage.ownedVoyages} owned voyages ·{" "}
                  {q.data.coverage.currentCalls} identified current calls ·{" "}
                  {q.data.coverage.assessedCurrentPlans} assessed current plans
                  · {q.data.coverage.retainedComparisons} retained comparisons
                  inspected.
                </p>
                {!q.data.coverage.snapshotConsistent ? (
                  <p role="status">
                    Linked records are updating or incomplete. Inspect the
                    reported basis; this is not a clear-fleet result.
                  </p>
                ) : null}
                <p className="text-[var(--text-2)]">
                  Category counts cover the full owned fleet; each voyage
                  appears once. A card can carry additional overlapping reasons.
                  Policy {q.data.policyVersion}.
                </p>
                <p>
                  Showing {shown.length ? displayedPage * PAGE_SIZE + 1 : 0}–
                  {Math.min((displayedPage + 1) * PAGE_SIZE, filtered.length)}{" "}
                  of {filtered.length} voyages in this filter.
                </p>
                <div className="grid min-w-0 gap-3 lg:grid-cols-2">
                  {shown.map((row) => (
                    <TriageCard
                      key={row.id}
                      row={row}
                      selected={selectedRow === row.id}
                      onOpen={() => {
                        setSelectedRow(row.id);
                        try {
                          sessionStorage.setItem(
                            storageKey,
                            JSON.stringify({
                              open: true,
                              filter,
                              page: displayedPage,
                              selectedRow: row.id,
                            }),
                          );
                        } catch {
                          /* Optional view context. */
                        }
                      }}
                    />
                  ))}
                </div>
                {!filtered.length ? (
                  <p>
                    No retained rows in this filter. Unassessed voyages and
                    missing coverage remain visible in All current voyages; no
                    safe-route or readiness conclusion follows.
                  </p>
                ) : null}
                <div
                  className="flex flex-wrap items-center gap-2"
                  aria-label="Fleet review pages"
                >
                  <Button
                    size="sm"
                    variant="outline"
                    disabled={displayedPage === 0}
                    onClick={() => setPage(displayedPage - 1)}
                  >
                    Previous page
                  </Button>
                  <span>
                    Page {displayedPage + 1} of {pages}
                  </span>
                  <Button
                    size="sm"
                    variant="outline"
                    disabled={displayedPage + 1 >= pages}
                    onClick={() => setPage(displayedPage + 1)}
                  >
                    Next page
                  </Button>
                </div>
                <details>
                  <summary className="cursor-pointer">
                    Retained source leads · separate from current-plan triage
                  </summary>
                  <div className="mt-2 space-y-2">
                    <p>
                      {q.data.sourceLeadCoverage?.reason ??
                        "Source leads have independent coverage. They do not establish route crossings or calculated delay."}
                    </p>
                    <p>
                      {q.data.sourceLeads?.length ?? 0} retained relations;
                      heuristic lead priority is not combined with cargo slack
                      or money.
                    </p>
                    {q.data.sourceLeads?.map((lead) => (
                      <div
                        key={`${lead.noticeId}-${lead.vesselId}`}
                        className="border-t border-[var(--line)] py-2"
                      >
                        <a
                          className="underline"
                          href={`/company/global-eye#${reviewHash(lead.noticeId, lead.vesselId)}`}
                        >
                          {lead.vesselName} · {lead.title}
                        </a>
                        <p>
                          {lead.status} · source{" "}
                          {lead.sourceValidity ?? lead.sourceStatus} ·{" "}
                          {lead.calculationReason}
                        </p>
                      </div>
                    ))}
                    <a
                      href="/company/global-eye#intelligence-review"
                      className="underline"
                    >
                      Inspect all discovered events and voyage relations
                    </a>
                  </div>
                </details>
              </>
            ) : null}
          </div>
        </DialogPrimitive.Content>
      </DialogPortal>
    </Dialog>
  );
}
