import { createFileRoute } from "@tanstack/react-router";

import { useWorkspace } from "@/auth/AuthProvider";
import { exposureTone } from "@/components/globaleye/EventPanels";
import { Page, PageBody, PageHeader, Panel, Section } from "@/components/kit/layout";
import { Pill } from "@/components/kit/primitives";
import { EmptyState, ScreenFallback } from "@/components/kit/states";
import { cn } from "@/lib/utils";
import { useCompanyRoutes } from "@/services/os-hooks";

export const Route = createFileRoute("/company/routes")({ component: CompanyRoutes });

/**
 * Lane-level exposure across the fleet.
 *
 * A lane with no alternative routing is the finding that matters most here, so
 * it is called out in the strongest available tone rather than left as a null.
 */
function CompanyRoutes() {
  const { companyId } = useWorkspace();
  const query = useCompanyRoutes(companyId);

  if (query.isLoading || query.isError) {
    return (
      <ScreenFallback
        title="Routes"
        context={<span>Lane exposure across the fleet</span>}
        isLoading={query.isLoading}
        error={query.error}
        retry={() => void query.refetch()}
        label="Scoring the lanes"
      />
    );
  }

  const lanes = query.data?.lanes ?? [];

  return (
    <Page>
      <PageHeader
        title="Routes"
        context={<span>Trade lanes this fleet runs, and what threatens them</span>}
        meta={<span className="num">{lanes.length} lanes</span>}
      />
      <PageBody>
        {lanes.length === 0 ? (
          <EmptyState
            title="No lane in scope"
            detail="No vessel in this fleet is assigned to a lane in the catalogue."
          />
        ) : (
          <div className="grid gap-3 lg:grid-cols-2 2xl:grid-cols-3">
            {lanes.map((lane) => (
              <Panel
                key={lane.laneCode}
                title={lane.laneName}
                note={
                  <span
                    className={cn("num", `text-[var(--${exposureTone(lane.exposure)})]`)}
                  >
                    {lane.exposure.toFixed(2)}
                  </span>
                }
              >
                <Section title="Routing">
                  <p className="text-[10.5px] leading-relaxed text-[var(--text-3)]">
                    {lane.description}
                  </p>
                  <dl className="mt-1.5 space-y-[3px]">
                    <div className="flex items-baseline justify-between gap-2">
                      <dt className="text-[10.5px] text-[var(--text-3)]">Primary</dt>
                      <dd className="num text-[11px] text-[var(--text)]">
                        {lane.primaryNm.toLocaleString()} nm
                      </dd>
                    </div>
                    <div className="flex items-baseline justify-between gap-2">
                      <dt className="text-[10.5px] text-[var(--text-3)]">Alternative</dt>
                      <dd className="text-right text-[11px]">
                        {lane.alternative ? (
                          <span className="text-[var(--text)]">
                            {lane.alternative}
                            <span className="num ml-1 text-[10px] text-[var(--text-3)]">
                              +{lane.detourNm?.toLocaleString()} nm
                            </span>
                          </span>
                        ) : (
                          <span className="text-[var(--crit)]">none exists</span>
                        )}
                      </dd>
                    </div>
                    <div className="flex items-baseline justify-between gap-2">
                      <dt className="text-[10.5px] text-[var(--text-3)]">Chokepoints</dt>
                      <dd className="num text-[10.5px] text-[var(--text-2)]">
                        {lane.chokepoints.length
                          ? lane.chokepoints.join(", ").replace(/_/g, "-")
                          : "none"}
                      </dd>
                    </div>
                  </dl>
                </Section>

                <Section title={`Vessels · ${lane.vessels.length}`}>
                  <ul className="space-y-[3px]">
                    {lane.vessels.map((vessel) => (
                      <li
                        key={vessel.vesselId}
                        className="flex items-baseline gap-2 text-[10.5px]"
                      >
                        <span className="min-w-0 flex-1 truncate text-[var(--text-2)]">
                          {vessel.name}
                        </span>
                        <span className="num shrink-0 text-[9.5px] text-[var(--text-3)]">
                          → {vessel.destination}
                        </span>
                      </li>
                    ))}
                  </ul>
                </Section>

                {lane.events.length ? (
                  <Section title="Events on this lane">
                    <ul className="space-y-1">
                      {lane.events.map((event) => (
                        <li key={event.eventId} className="flex items-baseline gap-2">
                          <span className="min-w-0 flex-1 truncate text-[10px] text-[var(--text-2)]">
                            {event.title}
                          </span>
                          <span
                            className={cn(
                              "num shrink-0 text-[10px]",
                              `text-[var(--${exposureTone(event.exposure)})]`,
                            )}
                          >
                            {event.exposure.toFixed(2)}
                          </span>
                        </li>
                      ))}
                    </ul>
                  </Section>
                ) : (
                  <Section title="Events">
                    <p className="text-[10.5px] text-[var(--ok)]">
                      No live event reaches this lane.
                    </p>
                  </Section>
                )}
              </Panel>
            ))}
          </div>
        )}
      </PageBody>
    </Page>
  );
}
