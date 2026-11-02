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
      data-testid="fleet-triage-detail"
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
      {row.portContext ? (
        <details className="border-l-2 border-[var(--line)] pl-2">
          <summary>
            Paradip destination context · {row.portContext.status}
            {row.portContext.reviewRequired ? " · Company source review" : ""}
          </summary>
          <p>
            {row.portContext.reportDate ?? "Report date unavailable"}.{" "}
            {row.portContext.reason}
          </p>
          {row.portContext.metric ? (
            <p>
              {row.portContext.metric.id}:{" "}
              {row.portContext.metric.value ?? "Unavailable"}{" "}
              {row.portContext.metric.unit} ·{" "}
              {row.portContext.metric.eligibility}. Operator review threshold ≥{" "}
              {row.portContext.rule?.threshold ?? "not declared"}.
            </p>
          ) : null}
          <a
            className="underline"
            href={`/company/global-eye#intelligence-review?vesselId=${encodeURIComponent(row.vessel.id)}`}
          >
            Inspect daily port context and audit
          </a>
          <p>
            This source-review responsibility is separate from the workflow next
            role.
          </p>
        </details>
      ) : null}
      {row.sourceReviews?.length ? (
        <div className="space-y-2 border-l-2 border-[var(--line-strong)] pl-2">
          <strong>Separate source review · Company</strong>
          <p>
            The advisory workflow still belongs to the next role shown above.
          </p>
          {row.sourceReviews.map((review) => (
            <p key={review.noticeId}>
              <a
                className="underline"
                href={`/company/global-eye#${reviewHash(review.noticeId, row.vessel.id)}`}
                onClick={onOpen}
              >
                Inspect {review.title}
              </a>{" "}
              · {review.sourceStatus}. {review.reason}
            </p>
          ))}
        </div>
      ) : null}
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
          {row.freshness.sourceChanges?.map((change) => (
            <section
              key={`${change.noticeId}-${change.code}`}
              className="space-y-2 border border-[var(--line)] p-2"
              aria-label="Consumed source changes"
            >
              <strong>
                {change.noticeId} · {change.code.replaceAll("_", " ")}
              </strong>
              <p>{change.text}</p>
              <p>
                Consumed revision {change.consumedRevisionId ?? "unavailable"} →
                retained revision {change.currentRevisionId ?? "unavailable"}.
              </p>
              <p>
                First availability{" "}
                {formatUtc(change.consumedAvailableAt ?? null)} →{" "}
                {formatUtc(change.currentAvailableAt ?? null)}.
              </p>
              <dl>
                {change.changes.map((field, index) => (
                  <div key={`${field.field}-${index}`} className="mt-2">
                    <dt className="font-semibold">{field.field}</dt>
                    <dd>
                      Consumed: {JSON.stringify(field.before) ?? "Unavailable"}
                    </dd>
                    <dd>
                      Retained: {JSON.stringify(field.after) ?? "Unavailable"}
                    </dd>
                  </div>
                ))}
              </dl>
              <p>
                {change.unknown} {change.nextAction}
              </p>
            </section>
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
  const [search, setSearch] = useState("");
  const [expanded, setExpanded] = useState(false);
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
        search?: string;
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
      setSearch(
        typeof saved?.search === "string" ? saved.search.slice(0, 100) : "",
      );
    } catch {
      /* Blocked storage only loses UI context, never decision records. */
    }
    setRestored(true);
  }, [storageKey]);
  useEffect(() => {
    const openFromLink = () => {
      if (window.location.hash === "#fleet-queue") setOpen(true);
    };
    window.addEventListener("hashchange", openFromLink);
    return () => window.removeEventListener("hashchange", openFromLink);
  }, []);
  useEffect(() => {
    if (!restored) return;
    try {
      sessionStorage.setItem(
        storageKey,
        JSON.stringify({ open, filter, page, selectedRow, search }),
      );
    } catch {
      /* Optional view preference. */
    }
  }, [storageKey, open, filter, page, selectedRow, search, restored]);
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
  const term = search.trim().toLocaleLowerCase();
  const filtered = rows.filter(
    (row) =>
      (filter === "ALL" || row.primaryCategory === filter) &&
      (!term ||
        `${row.vessel.name} ${row.destinationPort ?? ""} ${row.reasons.map((reason) => reason.text).join(" ")}`
          .toLocaleLowerCase()
          .includes(term)),
  );
  const pages = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
  const displayedPage = Math.min(page, pages - 1);
  const shown = filtered.slice(
    displayedPage * PAGE_SIZE,
    (displayedPage + 1) * PAGE_SIZE,
  );
  const selected = shown.find((row) => row.id === selectedRow) ?? shown[0];
  const remember = (row: FleetDecisionRow) => {
    setSelectedRow(row.id);
    try {
      sessionStorage.setItem(
        storageKey,
        JSON.stringify({
          open: true,
          filter,
          search,
          page: displayedPage,
          selectedRow: row.id,
        }),
      );
    } catch {
      /* Optional view state; canonical decisions stay server-owned. */
    }
  };
  return (
    <Dialog
      open={open}
      onOpenChange={(nextOpen) => {
        setOpen(nextOpen);
        if (!nextOpen && window.location.hash === "#fleet-queue") {
          window.history.replaceState(
            window.history.state,
            "",
            window.location.pathname + window.location.search,
          );
        }
      }}
      modal={false}
    >
      <section
        className="pointer-events-auto shrink-0"
        aria-label="Company fleet review queue"
      >
        <Button
          size="sm"
          variant="outline"
          className="min-h-10 w-full justify-between"
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
          <span aria-hidden>↗</span>
        </Button>
      </section>
      <DialogPortal>
        <DialogPrimitive.Content
          className="pw-worklist pointer-events-auto"
          data-expanded={expanded}
          data-testid="company-fleet-triage"
          onInteractOutside={(event) => event.preventDefault()}
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
              : document.querySelector<HTMLElement>(
                  'input[aria-label="Search fleet review"]',
                );
            if (target) {
              event.preventDefault();
              target.focus();
            }
          }}
        >
          <header className="pw-worklist-header">
            <div className="min-w-0 flex-1">
              <DialogTitle>Fleet decision review</DialogTitle>
              <DialogDescription>
                Current plans, specific review reasons and the next responsible
                role.
              </DialogDescription>
            </div>
            <Button
              size="sm"
              variant="ghost"
              onClick={() => setExpanded(!expanded)}
            >
              {expanded ? "Compact review" : "Expand review"}
            </Button>
            <DialogClose asChild>
              <Button size="sm" variant="ghost">
                Close fleet review
              </Button>
            </DialogClose>
          </header>
          <div className="pw-worklist-toolbar">
            <input
              type="search"
              aria-label="Search fleet review"
              placeholder="Search vessel, port or reason"
              value={search}
              maxLength={100}
              onChange={(event) => {
                setSearch(event.target.value);
                setPage(0);
              }}
            />
            <select
              aria-label="Fleet review category"
              value={filter}
              onChange={(event) => {
                setFilter(event.target.value as typeof filter);
                setPage(0);
              }}
            >
              <option value="ALL">
                All current voyages ({q.data?.coverage.ownedVoyages ?? "—"})
              </option>
              {FLEET_TRIAGE_CATEGORIES.map((category) => (
                <option key={category} value={category}>
                  {LABELS[category]} ({q.data?.counts[category] ?? "—"})
                </option>
              ))}
            </select>
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
            <p className="p-3" role="status">
              Reading retained fleet and workflow records…
            </p>
          ) : null}
          {q.isFetching && q.data ? (
            <p className="px-4 py-2 text-xs" role="status">
              Refreshing retained state. Previous projection:{" "}
              {formatUtc(q.data.asOf)}.
            </p>
          ) : null}
          {q.isError ? (
            <p className="px-4 py-2 text-xs" role="alert">
              Fleet projection unavailable: {q.error.message}
              {q.data
                ? ` Retaining the previous results from ${formatUtc(q.data.asOf)}; they are not newly verified.`
                : " No fleet-clear conclusion is available."}
            </p>
          ) : null}
          {q.data ? (
            <>
              <div className="pw-worklist-coverage border-b border-[var(--line)] px-4 py-2">
                <span>{q.data.coverage.ownedVoyages} owned voyages</span>
                <span>
                  {q.data.coverage.assessedCurrentPlans} assessed current plans
                </span>
                <span>
                  {q.data.coverage.retainedComparisons} retained comparisons
                  inspected
                </span>
                {!q.data.coverage.snapshotConsistent ? (
                  <span role="status">
                    Linked records are updating or incomplete; no clear-fleet
                    conclusion.
                  </span>
                ) : null}
              </div>
              <div
                className="pw-worklist-layout"
                data-testid="fleet-triage-scroll"
              >
                <div
                  className="pw-worklist-list"
                  aria-label="Current voyage review list"
                >
                  <div className="pw-fleet-columns" aria-hidden>
                    <span>Voyage / current plan</span>
                    <span>Review reason / timing</span>
                    <span>Next role</span>
                  </div>
                  {shown.map((row) => (
                    <button
                      type="button"
                      key={row.id}
                      className="pw-fleet-row"
                      data-testid="fleet-triage-row"
                      data-row-id={row.id}
                      data-selected={selected?.id === row.id}
                      aria-pressed={selected?.id === row.id}
                      aria-label={`Inspect review for ${row.vessel.name}`}
                      onClick={() => remember(row)}
                    >
                      <span>
                        <strong>{row.vessel.name}</strong>
                        <small>
                          → {row.destinationPort ?? "Destination unknown"}
                        </small>
                        <small>
                          {row.currentPlan.basis === "BASELINE_NOT_APPROVED"
                            ? "Baseline · not approved"
                            : row.currentPlan.basis === "APPROVED"
                              ? "Approved current plan"
                              : row.currentPlan.basis === "AMBIGUOUS"
                                ? "Conflicting current plans"
                                : "No saved current plan"}
                        </small>
                      </span>
                      <span>
                        {row.reasons[0]?.text ?? "Assessment basis unavailable"}
                        <small>{LABELS[row.primaryCategory]}</small>
                        {row.cargo?.slackHours != null ? (
                          <small>
                            Cutoff slack {signedHours(row.cargo.slackHours)}
                          </small>
                        ) : row.deadline ? (
                          <small>
                            {signedHours(row.deadline.hoursRemaining)} remaining
                          </small>
                        ) : (
                          <small>Applicable action deadline unknown.</small>
                        )}
                      </span>
                      <span>
                        {row.workflow.nextRole
                          ? (ROLE_LABELS[row.workflow.nextRole] ??
                            row.workflow.nextRole)
                          : "No pending role"}
                        <small>{row.workflow.stage.replaceAll("_", " ")}</small>
                      </span>
                    </button>
                  ))}
                  {!shown.length ? (
                    <p className="p-4 text-sm">
                      No retained rows in this filter. Unassessed voyages remain
                      in All current voyages; no safe-route or readiness
                      conclusion follows.
                    </p>
                  ) : null}
                </div>
                <aside
                  className="pw-worklist-detail"
                  aria-label="Selected voyage review"
                >
                  {selected ? (
                    <TriageCard
                      row={selected}
                      selected
                      onOpen={() => remember(selected)}
                    />
                  ) : (
                    <p className="p-4 text-sm text-[var(--text-3)]">
                      Select a voyage to inspect its exact plan, evidence and
                      permitted action.
                    </p>
                  )}
                </aside>
              </div>
              <footer className="pw-worklist-footer">
                <span className="mr-auto">
                  Showing {shown.length ? displayedPage * PAGE_SIZE + 1 : 0}–
                  {Math.min((displayedPage + 1) * PAGE_SIZE, filtered.length)}{" "}
                  of {filtered.length} voyages in this filter.
                </span>
                <div
                  className="flex items-center gap-2"
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
                    {displayedPage + 1} / {pages}
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
                <details className="w-full">
                  <summary className="cursor-pointer">
                    Coverage, policy and separate source leads
                  </summary>
                  <div className="max-h-40 overflow-y-auto py-2">
                    <p>
                      Projected {formatUtc(q.data.asOf)} ·{" "}
                      {q.data.coverage.currentCalls} identified current calls.
                      Category counts cover the full owned fleet; each voyage
                      appears once. Policy {q.data.policyVersion}. Read-only
                      order; no probability, loss estimate or automatic
                      approval.
                    </p>
                    <p>
                      {q.data.sourceLeadCoverage?.reason ??
                        "Source leads have independent coverage; they do not establish route crossings or calculated delay."}
                    </p>
                    {(q.data.sourceLeads ?? []).map((lead) => (
                      <p key={`${lead.noticeId}-${lead.vesselId}`}>
                        <a
                          className="underline"
                          href={`/company/global-eye#${reviewHash(lead.noticeId, lead.vesselId)}`}
                        >
                          {lead.vesselName} · {lead.title}
                        </a>{" "}
                        · {lead.status} · source{" "}
                        {lead.sourceValidity ?? lead.sourceStatus} ·{" "}
                        {lead.calculationReason}
                      </p>
                    ))}
                    <a
                      className="underline"
                      href="/company/global-eye#intelligence-review"
                    >
                      Inspect all discovered events and voyage relations
                    </a>
                  </div>
                </details>
              </footer>
            </>
          ) : null}
        </DialogPrimitive.Content>
      </DialogPortal>
    </Dialog>
  );
}
