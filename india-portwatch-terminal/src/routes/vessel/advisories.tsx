import { useState } from "react";
import { createFileRoute, useLocation } from "@tanstack/react-router";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useAuth } from "@/auth/AuthProvider";
import {
  AdvisoryActions,
  advisoryLabel,
  advisoryTone,
} from "@/components/advisory/AdvisoryPanels";
import { Page, PageBody, PageHeader } from "@/components/kit/layout";
import { formatUtc, Pill } from "@/components/kit/primitives";
import { ScreenFallback } from "@/components/kit/states";
import { fetchAdvisories } from "@/services/portwatch-os";
import type { FrozenEnvironment } from "@/services/current-inputs";
import type { Advisory, AdvisoryList } from "@/types/portwatch-os";

export const Route = createFileRoute("/vessel/advisories")({
  head: () => ({ meta: [{ title: "PortWatch X — Vessel Advisories" }] }),
  component: VesselAdvisories,
});

function numeric(value: unknown) {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function formatChange(
  before: unknown,
  after: unknown,
  digits: number,
  unit: string,
) {
  const from = numeric(before);
  const to = numeric(after);
  if (to == null) return "Unavailable";
  return `${from == null ? "" : `${from.toFixed(digits)} → `}${to.toFixed(digits)} ${unit}`;
}

function IssuedSummary({ advisory }: { advisory: Advisory }) {
  const { recommendation, evidence } = advisory;
  const passage = (evidence.currentEnvironment as FrozenEnvironment | undefined)
    ?.passageComparison?.options;
  const selected = passage?.find(
    (option) => option.optionId === evidence.optionId,
  );
  const speed = numeric(recommendation.recommendedSpeedKn);
  const wait = numeric(recommendation.anchorageWaitHours);
  const approach =
    typeof recommendation.approachClearAt === "string"
      ? recommendation.approachClearAt
      : null;
  const baseline =
    selected &&
    selected.speedKn === speed &&
    selected.anchorageWaitHours === wait &&
    selected.approachClearAt === approach
      ? passage?.[0]
      : undefined;
  const sameApproach =
    baseline?.approachClearAt != null &&
    approach != null &&
    Date.parse(baseline.approachClearAt) === Date.parse(approach);
  const action = recommendation.action;
  const headline =
    action === "SLOW_STEAM"
      ? "Reduce speed on the declared passage"
      : action === "HOLD_AND_REFER"
        ? "Hold the entry request and seek Port review"
        : advisory.kindLabel;
  return (
    <section
      aria-label="Issued recommendation"
      className="rounded border border-[var(--line-strong)] bg-[var(--panel-2)] p-4"
    >
      <p className="text-xs text-[var(--text-2)]">
        Port recommendation · {advisory.portCode}
      </p>
      <h3 className="my-1 text-lg font-semibold">{headline}</h3>
      {speed != null || wait != null || approach ? (
        <dl className="mt-3 grid gap-3 text-xs sm:grid-cols-3">
          {speed != null ? (
            <div>
              <dt>Declared speed</dt>
              <dd className="num mt-1 text-base font-semibold">
                {formatChange(baseline?.speedKn, speed, 0, "kn")}
              </dd>
            </div>
          ) : null}
          {wait != null ? (
            <div>
              <dt>Modeled anchorage wait</dt>
              <dd className="num mt-1 text-base font-semibold">
                {formatChange(baseline?.anchorageWaitHours, wait, 2, "h")}
              </dd>
            </div>
          ) : null}
          {approach ? (
            <div>
              <dt>
                {sameApproach
                  ? "Same modeled approach window"
                  : "Conditional clear approach"}
              </dt>
              <dd className="num mt-1 text-base font-semibold">
                {formatUtc(approach)}
              </dd>
            </div>
          ) : null}
        </dl>
      ) : typeof recommendation.recommendedArrival === "string" ? (
        <p className="mt-2 text-sm">
          Recommended arrival {formatUtc(recommendation.recommendedArrival)}
        </p>
      ) : null}
    </section>
  );
}

function VesselAudit({ advisory }: { advisory: Advisory }) {
  const actor = { issuer: "Port", recipient: "Bridge", system: "System" };
  return (
    <ol className="space-y-2">
      {advisory.audit.map((entry, index) => (
        <li
          key={`${entry.at}-${index}`}
          className="border-l border-[var(--line-strong)] pl-2 text-xs"
        >
          <div className="flex flex-wrap justify-between gap-x-2">
            <strong>{entry.action}</strong>
            <time dateTime={entry.at}>{formatUtc(entry.at)}</time>
          </div>
          <p className="text-[var(--text-2)]">
            {actor[entry.actor_role]} ·{" "}
            {advisoryLabel(entry.from_state as Advisory["state"])} →{" "}
            {advisoryLabel(entry.to_state as Advisory["state"])}
          </p>
          {entry.reason ? <p>{entry.reason}</p> : null}
        </li>
      ))}
    </ol>
  );
}

function VesselAdvisories() {
  const { session, identityHeaders } = useAuth();
  const client = useQueryClient();
  const search = useLocation({ select: (location) => location.searchStr });
  const linked = new URLSearchParams(search).get("advisory");
  const [selection, setSelection] = useState<string | null | undefined>(
    undefined,
  );
  const key = [
    "vessel-advisories",
    session?.demoId ?? session?.user.id,
    session?.user.role,
  ];
  const query = useQuery({
    queryKey: key,
    queryFn: () => fetchAdvisories(identityHeaders),
    enabled: Boolean(session),
    refetchInterval: 10000,
  });
  const rows = query.data?.advisories ?? [];
  const active =
    selection === undefined
      ? (linked ??
        rows.find(
          (item) => item.state === "issued" || item.state === "acknowledged",
        )?.advisoryId ??
        rows[0]?.advisoryId)
      : selection;

  function changed(next: Advisory) {
    client.setQueryData<AdvisoryList>(key, (previous) =>
      previous
        ? {
            ...previous,
            advisories: previous.advisories.map((row) =>
              row.advisoryId === next.advisoryId ? next : row,
            ),
          }
        : previous,
    );
    void client.invalidateQueries({ queryKey: ["workspace-handoffs"] });
  }

  if (query.isPending || query.isError)
    return (
      <ScreenFallback
        title="Advisories"
        isLoading={query.isPending}
        error={query.error}
        retry={() => void query.refetch()}
        label="Opening your advisory register"
      />
    );
  return (
    <Page>
      <PageHeader
        title="Advisories"
        context={<span>Issued recommendations for your assigned vessel</span>}
      />
      <PageBody className="space-y-3">
        {linked && !rows.some((row) => row.advisoryId === linked) ? (
          <p
            role="status"
            className="rounded border border-[var(--line)] p-3 text-sm"
          >
            That advisory is unavailable in this Vessel workspace.
          </p>
        ) : null}
        {rows.length === 0 ? (
          <p className="rounded border border-[var(--line)] p-3 text-sm">
            Port has not issued any advisories to this vessel.
          </p>
        ) : null}
        {rows.map((advisory) => {
          const expanded = active === advisory.advisoryId;
          const actions =
            advisory.state === "issued"
              ? {
                  ...advisory,
                  availableTransitions: advisory.availableTransitions.filter(
                    (transition) => transition.target !== "accepted",
                  ),
                }
              : advisory;
          return (
            <article
              data-testid="advisory-card"
              key={advisory.advisoryId}
              className="rounded border border-[var(--line-strong)] bg-[var(--panel)]"
            >
              <button
                type="button"
                aria-expanded={expanded}
                onClick={() =>
                  setSelection(expanded ? null : advisory.advisoryId)
                }
                className="flex w-full flex-wrap items-center justify-between gap-2 p-3 text-left"
              >
                <span>
                  <strong>{advisory.recipientVesselName}</strong> ·{" "}
                  {advisory.kindLabel}
                </span>
                <Pill tone={advisoryTone(advisory.state)}>
                  {advisoryLabel(advisory.state)}
                </Pill>
              </button>
              {expanded ? (
                <div className="grid gap-3 border-t border-[var(--line)] p-3 lg:grid-cols-[minmax(0,1fr)_minmax(250px,0.43fr)]">
                  <div className="min-w-0 space-y-3">
                    <IssuedSummary advisory={advisory} />
                    <details className="rounded border border-[var(--line)] p-3 text-xs">
                      <summary className="cursor-pointer font-semibold">
                        Reasoning and operating limits
                      </summary>
                      <p className="mt-2 break-words">{advisory.reason}</p>
                      {typeof advisory.recommendation.basis === "string" ? (
                        <p className="mt-2 break-words">
                          {advisory.recommendation.basis}
                        </p>
                      ) : null}
                      <p className="mt-2">Advisory {advisory.advisoryId}</p>
                    </details>
                  </div>
                  <aside className="min-w-0 space-y-3">
                    <section
                      aria-label="Bridge response"
                      className="rounded border border-[var(--line)] p-3 [&_[data-testid=advisory-action-acknowledged]]:bg-[var(--action)] [&_[data-testid=advisory-action-accepted]]:bg-[var(--action)] [&_[data-testid=advisory-action-acknowledged]]:!text-white [&_[data-testid=advisory-action-accepted]]:!text-white"
                    >
                      <h3 className="mb-2 text-sm font-semibold">
                        Bridge response
                      </h3>
                      {advisory.state === "issued" ? (
                        <p className="mb-2 text-xs">
                          Acknowledge receipt before accepting the
                          recommendation.
                        </p>
                      ) : null}
                      <AdvisoryActions
                        advisory={actions}
                        headers={identityHeaders}
                        onDone={changed}
                      />
                    </section>
                    <section
                      aria-label="Audit trail"
                      className="rounded border border-[var(--line)] p-3"
                    >
                      <h3 className="mb-2 text-sm font-semibold">
                        Audit trail
                      </h3>
                      <VesselAudit advisory={advisory} />
                    </section>
                  </aside>
                </div>
              ) : null}
            </article>
          );
        })}
      </PageBody>
    </Page>
  );
}
