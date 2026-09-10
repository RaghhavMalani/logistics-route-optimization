import { createFileRoute } from "@tanstack/react-router";
import { useState } from "react";

import { useWorkspace } from "@/auth/AuthProvider";
import { VesselExposureRow, exposureTone } from "@/components/globaleye/EventPanels";
import { Page, PageBody, PageHeader, Panel, Section } from "@/components/kit/layout";
import { Pill, formatUtc } from "@/components/kit/primitives";
import { EmptyState, ScreenFallback } from "@/components/kit/states";
import { cn } from "@/lib/utils";
import { useCompanyRisk } from "@/services/os-hooks";

export const Route = createFileRoute("/company/risk")({ component: CompanyRisk });

const HORIZONS = [24, 48, 72, 168];

/**
 * Exposure windows and the deadlines attached to them.
 *
 * The list is split by whether an action is still available, not by severity. A
 * high-exposure vessel that has already passed the strait is a worse *outcome*
 * than a moderate one that has not, and a worse *use of attention*.
 */
function CompanyRisk() {
  const { companyId } = useWorkspace();
  const [horizon, setHorizon] = useState(72);
  const query = useCompanyRisk(companyId, horizon);

  if (query.isLoading || query.isError) {
    return (
      <ScreenFallback
        title="Risk"
        context={<span>Exposure windows and diversion deadlines</span>}
        isLoading={query.isLoading}
        error={query.error}
        retry={() => void query.refetch()}
        label="Computing exposure"
      />
    );
  }

  const actionRequired = query.data?.actionRequired ?? [];
  const monitorOnly = query.data?.monitorOnly ?? [];
  const ports = Object.values(query.data?.portRisk ?? {}).sort((a, b) => b.risk - a.risk);

  return (
    <Page>
      <PageHeader
        title="Risk"
        context={
          <span>
            {query.data?.vesselsExposed ?? 0} of {query.data?.fleetSize ?? 0} vessels
            exposed
          </span>
        }
        actions={
          <div className="flex overflow-hidden rounded-[2px] border border-[var(--line-strong)]">
            {HORIZONS.map((hours) => (
              <button
                key={hours}
                type="button"
                aria-pressed={horizon === hours}
                onClick={() => setHorizon(hours)}
                className={cn(
                  "num px-2 py-[3px] text-[11px] transition-colors",
                  horizon === hours
                    ? "bg-[var(--panel-4)] text-[var(--text)]"
                    : "text-[var(--text-3)] hover:bg-[var(--panel-3)] hover:text-[var(--text-2)]",
                )}
              >
                {hours}h
              </button>
            ))}
          </div>
        }
      />
      <PageBody>
        <div className="grid gap-3 xl:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_300px]">
          <Panel
            title="Action required"
            note={`${actionRequired.length}`}
            testId="risk-action-required"
            scroll
            className="max-h-[calc(100vh-190px)]"
          >
            {actionRequired.length === 0 ? (
              <EmptyState
                title="Nothing requires intervention"
                detail={`No vessel is exposed with an action still available inside ${horizon} hours.`}
              />
            ) : (
              actionRequired.map((row) => (
                <VesselExposureRow key={`${row.vesselId}-${row.eventId}`} row={row} />
              ))
            )}
          </Panel>

          <Panel
            title="Monitor only"
            note={`${monitorOnly.length}`}
            scroll
            className="max-h-[calc(100vh-190px)]"
          >
            {monitorOnly.length === 0 ? (
              <EmptyState
                title="No vessel is committed"
                detail="No vessel has entered an exposed area."
              />
            ) : (
              <>
                <p className="border-b border-[var(--line)] px-2 py-1.5 text-[10px] leading-snug text-[var(--text-3)]">
                  These vessels are inside the exposed water. The diversion option has
                  closed, so no routing action is offered — they are listed so they are
                  not mistaken for safe.
                </p>
                {monitorOnly.map((row) => (
                  <VesselExposureRow key={`${row.vesselId}-${row.eventId}`} row={row} />
                ))}
              </>
            )}
          </Panel>

          <Panel title="Destination ports" note={`${ports.length}`}>
            <Section title="Event risk at arrival">
              {ports.length === 0 ? (
                <p className="text-[10.5px] text-[var(--text-3)]">
                  No destination port carries measurable event risk.
                </p>
              ) : (
                <div className="space-y-1">
                  {ports.map((port) => (
                    <div key={port.portCode}>
                      <div className="flex items-baseline gap-2">
                        <span className="num w-[46px] shrink-0 text-[10.5px] text-[var(--text-2)]">
                          {port.portCode}
                        </span>
                        <span className="min-w-0 flex-1 truncate text-[10.5px] text-[var(--text)]">
                          {port.portName}
                        </span>
                        <span
                          className={cn(
                            "num shrink-0 text-[11px]",
                            `text-[var(--${exposureTone(port.risk)})]`,
                          )}
                        >
                          {port.risk.toFixed(2)}
                        </span>
                      </div>
                      {port.arrivalShiftHours ? (
                        <div className="num text-[9.5px] text-[var(--text-3)]">
                          arrivals shift +{port.arrivalShiftHours.toFixed(1)} h
                        </div>
                      ) : null}
                    </div>
                  ))}
                </div>
              )}
            </Section>
            <Section title="What this does not say">
              <p className="text-[10px] leading-relaxed text-[var(--text-3)]">
                {query.data?.note}
              </p>
            </Section>
          </Panel>
        </div>
      </PageBody>
    </Page>
  );
}
