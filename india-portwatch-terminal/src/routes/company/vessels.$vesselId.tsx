import { Link, createFileRoute } from "@tanstack/react-router";

import { useWorkspace } from "@/auth/AuthProvider";
import { VesselExposureRow, exposureTone } from "@/components/globaleye/EventPanels";
import { Page, PageBody, PageHeader, Panel, Section } from "@/components/kit/layout";
import { Pill, formatUtc } from "@/components/kit/primitives";
import { EmptyState, ScreenFallback } from "@/components/kit/states";
import { cn } from "@/lib/utils";
import { useCompanyFleet, useCompanyRisk } from "@/services/os-hooks";

export const Route = createFileRoute("/company/vessels/$vesselId")({
  component: CompanyVessel,
});

/** One vessel: particulars, voyage, and every event that reaches it. */
function CompanyVessel() {
  const { vesselId } = Route.useParams();
  const { companyId } = useWorkspace();
  const fleet = useCompanyFleet(companyId);
  const risk = useCompanyRisk(companyId, 168);

  if (fleet.isLoading || fleet.isError) {
    return (
      <ScreenFallback
        title={vesselId}
        context={<span>Vessel detail</span>}
        isLoading={fleet.isLoading}
        error={fleet.error}
        retry={() => void fleet.refetch()}
        label="Loading the vessel"
      />
    );
  }

  const vessel = fleet.data?.vessels.find((v) => v.vessel_id === vesselId) ?? null;
  const exposures = (risk.data?.rows ?? []).filter((row) => row.vesselId === vesselId);
  const worst = exposures[0]?.exposure ?? 0;

  if (!vessel) {
    return (
      <Page>
        <PageHeader title={vesselId} context={<span>Vessel detail</span>} />
        <PageBody>
          <EmptyState
            title="Not in this fleet"
            detail={`${vesselId} is not a vessel on the signed-in carrier account.`}
            action={
              <Link
                to="/company/fleet"
                className="text-[11.5px] text-[var(--info)] hover:underline"
              >
                Back to the fleet
              </Link>
            }
          />
        </PageBody>
      </Page>
    );
  }

  return (
    <Page>
      <PageHeader
        title={vessel.name}
        context={
          <span className="flex items-center gap-2">
            <span className="num">{vessel.vessel_id}</span>
            <Pill tone="unc">{fleet.data?.positionSource}</Pill>
          </span>
        }
        meta={
          <>
            <span className="num">
              {vessel.origin_port} → {vessel.destination_port}
            </span>
            {vessel.eta ? <span className="num">ETA {formatUtc(vessel.eta)}</span> : null}
            <span className={cn("num", `text-[var(--${exposureTone(worst)})]`)}>
              exposure {worst.toFixed(2)}
            </span>
          </>
        }
      />
      <PageBody>
        <div className="grid gap-3 xl:grid-cols-[320px_minmax(0,1fr)]">
          <div className="space-y-3">
            <Panel title="Particulars">
              <Section title="Hull">
                <dl className="space-y-[3px]">
                  {(
                    [
                      ["Class", vessel.vessel_class.replace(/_/g, " ")],
                      ["LOA", `${vessel.loa_m.toFixed(0)} m`],
                      ["Beam", `${vessel.beam_m.toFixed(1)} m`],
                      ["Draught", `${vessel.draught_m.toFixed(1)} m`],
                      ["Capacity", `${vessel.capacity_teu.toLocaleString()} TEU`],
                      ["Reefer plugs", String(vessel.reefer_plugs)],
                      ["Service speed", `${vessel.service_speed_kn.toFixed(1)} kn`],
                      ["Flag", vessel.flag],
                      ["IMO", vessel.imo ?? "none issued"],
                    ] as Array<[string, string]>
                  ).map(([label, value]) => (
                    <div key={label} className="flex items-baseline justify-between gap-2">
                      <dt className="text-[10.5px] text-[var(--text-3)]">{label}</dt>
                      <dd className="num text-[11px] text-[var(--text)]">{value}</dd>
                    </div>
                  ))}
                </dl>
              </Section>
              <Section title="Onward capacity">
                <dl className="space-y-[3px]">
                  <div className="flex items-baseline justify-between gap-2">
                    <dt className="text-[10.5px] text-[var(--text-3)]">Free slots</dt>
                    <dd className="num text-[11px] text-[var(--text)]">
                      {vessel.available_teu.toFixed(0)} TEU
                    </dd>
                  </div>
                  <div className="flex items-baseline justify-between gap-2">
                    <dt className="text-[10.5px] text-[var(--text-3)]">Free plugs</dt>
                    <dd className="num text-[11px] text-[var(--text)]">
                      {vessel.available_reefer_plugs}
                    </dd>
                  </div>
                  <div className="flex items-baseline justify-between gap-2">
                    <dt className="text-[10.5px] text-[var(--text-3)]">IMDG certified</dt>
                    <dd className="text-[11px] text-[var(--text)]">
                      {vessel.accepts_hazardous ? "yes" : "no"}
                    </dd>
                  </div>
                  <div className="flex items-baseline justify-between gap-2">
                    <dt className="text-[10.5px] text-[var(--text-3)]">Rotation</dt>
                    <dd className="num text-[11px] text-[var(--text)]">
                      {vessel.onward_ports.join(" → ") || "none declared"}
                    </dd>
                  </div>
                </dl>
              </Section>
            </Panel>

            <Panel title="Chokepoints ahead">
              <Section title="Hours to each">
                {Object.keys(vessel.hours_to_chokepoint).length === 0 ? (
                  <p className="text-[10.5px] text-[var(--text-3)]">
                    This lane transits no chokepoint in the catalogue.
                  </p>
                ) : (
                  <dl className="space-y-[3px]">
                    {Object.entries(vessel.hours_to_chokepoint).map(([code, hours]) => (
                      <div key={code} className="flex items-baseline justify-between gap-2">
                        <dt className="num text-[10.5px] text-[var(--text-3)]">
                          {code.replace(/_/g, "-")}
                        </dt>
                        <dd
                          className={cn(
                            "num text-[11px]",
                            hours <= 0 ? "text-[var(--unc)]" : "text-[var(--text)]",
                          )}
                        >
                          {hours <= 0 ? "passed" : `${hours.toFixed(0)} h`}
                        </dd>
                      </div>
                    ))}
                  </dl>
                )}
              </Section>
            </Panel>
          </div>

          <Panel
            title="Exposure"
            note={`${exposures.length} event${exposures.length === 1 ? "" : "s"}`}
            testId="vessel-exposure"
          >
            {exposures.length === 0 ? (
              <EmptyState
                title="No live event reaches this vessel"
                detail="No disruption in the current register touches a chokepoint on this lane inside the horizon."
              />
            ) : (
              exposures.map((row) => (
                <div key={row.eventId}>
                  <div className="border-b border-[var(--line)]/40 bg-[var(--panel-2)]/40 px-2 py-1">
                    <span className="truncate text-[10.5px] text-[var(--text-2)]">
                      {row.eventTitle}
                    </span>
                  </div>
                  <VesselExposureRow row={row} />
                </div>
              ))
            )}
          </Panel>
        </div>
      </PageBody>
    </Page>
  );
}
