/**
 * The advisory register, shared by both sides of the workflow.
 *
 * A port controller sees drafts awaiting review and everything issued from their
 * facility. A company or a master sees only what has been issued to them --
 * enforced by the API, which filters on the acting principal, not by a flag
 * here. The screen renders whatever came back and says which identity it asked
 * as, so a reader can see the scope rather than infer it.
 */

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { useAuth, useWorkspace } from "@/auth/AuthProvider";
import { AdvisoryCard, advisoryLabel, advisoryTone } from "@/components/advisory/AdvisoryPanels";
import { Button, Page, PageBody, PageHeader, Panel, Section } from "@/components/kit/layout";
import { Pill } from "@/components/kit/primitives";
import { EmptyState, ScreenFallback } from "@/components/kit/states";
import { cn } from "@/lib/utils";
import { generateAdvisories } from "@/services/portwatch-os";
import { useAdvisories, useAdvisoryPolicy } from "@/services/os-hooks";
import type { AdvisoryState } from "@/types/portwatch-os";

/** Which states a given side of the workflow actually cares about seeing. */
const ISSUER_FILTERS: Array<{ key: string; label: string; states: AdvisoryState[] }> = [
  { key: "open", label: "Needs action", states: ["draft", "under_review", "queried"] },
  { key: "live", label: "Issued", states: ["issued", "acknowledged", "accepted"] },
  { key: "closed", label: "Closed", states: ["declined", "rejected", "withdrawn", "expired", "completed"] },
];

const RECIPIENT_FILTERS: Array<{ key: string; label: string; states: AdvisoryState[] }> = [
  { key: "open", label: "Awaiting response", states: ["issued", "acknowledged"] },
  { key: "answered", label: "Answered", states: ["accepted", "queried", "declined"] },
  { key: "closed", label: "Closed", states: ["withdrawn", "expired", "completed"] },
];

export function AdvisoryScreen({
  title,
  context,
  side,
}: {
  title: string;
  context: string;
  side: "issuer" | "recipient";
}) {
  const { identityHeaders } = useAuth();
  const { portCode } = useWorkspace();
  const scope = side === "issuer" ? { portCode } : {};
  const query = useAdvisories(identityHeaders, scope);
  const policy = useAdvisoryPolicy();
  const [filter, setFilter] = useState("open");
  const [expanded, setExpanded] = useState<string | null>(null);
  const queryClient = useQueryClient();

  /**
   * Ask the decision engine for drafts.
   *
   * The controller pulls rather than the engine pushing. A queue that filled
   * itself would be one more thing to dismiss; a controller asking "what would
   * you recommend right now?" is a decision they made.
   */
  const generate = useMutation({
    mutationFn: () => generateAdvisories(identityHeaders, portCode),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["advisories"] });
      setFilter("open");
    },
  });

  const filters = side === "issuer" ? ISSUER_FILTERS : RECIPIENT_FILTERS;
  const active = filters.find((f) => f.key === filter) ?? filters[0];

  if (!identityHeaders["X-PortWatch-Actor"]) {
    return (
      <Page>
        <PageHeader title={title} context={<span>{context}</span>} />
        <PageBody>
          <EmptyState
            title="This role cannot act on advisories"
            detail="Advisories are issued by a port authority and answered by a carrier or a master. The signed-in role sits on neither side of that exchange."
          />
        </PageBody>
      </Page>
    );
  }

  if (query.isLoading || query.isError) {
    return (
      <ScreenFallback
        title={title}
        context={<span>{context}</span>}
        isLoading={query.isLoading}
        error={query.error}
        retry={() => void query.refetch()}
        label="Loading the advisory register"
      />
    );
  }

  const all = query.data?.advisories ?? [];
  const rows = all.filter((a) => active.states.includes(a.state));
  const counts = query.data?.counts ?? {};

  return (
    <Page>
      <PageHeader
        title={title}
        context={
          <span className="flex flex-wrap items-center gap-2">
            <span>{context}</span>
            <Pill tone="neutral">
              as {query.data?.principal.actor} ({query.data?.principal.role})
            </Pill>
            {query.data?.principal.isAdmin ? <Pill tone="unc">admin scope</Pill> : null}
          </span>
        }
        actions={
          <>
            {side === "issuer" ? (
              <Button
                variant="default"
                disabled={generate.isPending}
                onClick={() => generate.mutate()}
              >
                {generate.isPending ? "Running the twin…" : "Draft from the engine"}
              </Button>
            ) : null}
            <div className="flex overflow-hidden rounded-[2px] border border-[var(--line-strong)]">
            {filters.map((option) => {
              const count = all.filter((a) => option.states.includes(a.state)).length;
              return (
                <button
                  key={option.key}
                  type="button"
                  aria-pressed={filter === option.key}
                  onClick={() => setFilter(option.key)}
                  className={cn(
                    "px-2 py-[3px] text-[11px] transition-colors",
                    filter === option.key
                      ? "bg-[var(--panel-4)] text-[var(--text)]"
                      : "text-[var(--text-3)] hover:bg-[var(--panel-3)] hover:text-[var(--text-2)]",
                  )}
                >
                  {option.label}
                  <span className="num ml-1 text-[9.5px] text-[var(--text-3)]">{count}</span>
                </button>
              );
            })}
            </div>
          </>
        }
      />

      {generate.data ? (
        <div className="shrink-0 border-b border-[var(--line)] bg-[var(--panel-2)]/50 px-4 py-1.5">
          <p className="text-[10.5px] leading-snug text-[var(--text-2)]">
            The engine considered {generate.data.callsThatWaited} calls that waited and
            drafted {generate.data.created.length}
            {generate.data.refused.length
              ? `; the Critic refused ${generate.data.refused.length}: ${generate.data.refused[0].reasons[0]}`
              : ""}
            . {generate.data.note}
          </p>
        </div>
      ) : null}

      <PageBody>
        <div className="grid gap-3 xl:grid-cols-[minmax(0,1fr)_320px]">
          <Panel
            title={active.label}
            note={`${rows.length} advisor${rows.length === 1 ? "y" : "ies"}`}
            testId="advisory-register"
          >
            {rows.length === 0 ? (
              <EmptyState
                title={`Nothing ${active.label.toLowerCase()}`}
                detail={
                  side === "issuer"
                    ? "The decision engine has raised no draft for this facility, and nothing issued is awaiting a response."
                    : "No port authority has issued an advisory to this account. A draft advisory is never visible until a controller issues it."
                }
              />
            ) : (
              <div>
                {rows.map((advisory) => (
                  <AdvisoryCard
                    key={advisory.advisoryId}
                    advisory={advisory}
                    headers={identityHeaders}
                    expanded={expanded === advisory.advisoryId}
                    onToggle={() =>
                      setExpanded(
                        expanded === advisory.advisoryId ? null : advisory.advisoryId,
                      )
                    }
                  />
                ))}
              </div>
            )}
          </Panel>

          <div className="space-y-3">
            <Panel title="Register">
              <Section title="By state">
                <dl className="space-y-[3px]">
                  {Object.entries(counts).length === 0 ? (
                    <p className="text-[10.5px] text-[var(--text-3)]">
                      The register is empty.
                    </p>
                  ) : (
                    Object.entries(counts).map(([state, count]) => (
                      <div key={state} className="flex items-baseline justify-between gap-2">
                        <dt>
                          <Pill tone={advisoryTone(state as AdvisoryState)}>
                            {advisoryLabel(state as AdvisoryState)}
                          </Pill>
                        </dt>
                        <dd className="num text-[11.5px] text-[var(--text)]">{count}</dd>
                      </div>
                    ))
                  )}
                </dl>
              </Section>
            </Panel>

            <Panel title="How this works">
              <Section title="Rules">
                <ul className="space-y-1.5">
                  {(policy.data?.rules ?? []).map((rule) => (
                    <li
                      key={rule}
                      className="text-[10.5px] leading-relaxed text-[var(--text-2)]"
                    >
                      {rule}
                    </li>
                  ))}
                </ul>
              </Section>
              {policy.data?.identity ? (
                <Section title="Identity">
                  <p className="text-[10px] leading-relaxed text-[var(--text-3)]">
                    {policy.data.identity.note}
                  </p>
                  <div className="mt-1.5">
                    <Pill tone={policy.data.identity.verified ? "ok" : "unc"}>
                      {policy.data.identity.verified ? "verified" : "asserted, not verified"}
                    </Pill>
                  </div>
                </Section>
              ) : null}
            </Panel>
          </div>
        </div>
      </PageBody>
    </Page>
  );
}
