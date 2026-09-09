import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { useMemo } from "react";

import { useWorkspace } from "@/auth/AuthProvider";
import { exposureTone } from "@/components/globaleye/EventPanels";
import { Page, PageBody, PageHeader, Panel } from "@/components/kit/layout";
import { Pill, formatUtc } from "@/components/kit/primitives";
import { DataTable, type Column } from "@/components/kit/table";
import { ScreenFallback } from "@/components/kit/states";
import { cn } from "@/lib/utils";
import { useCompanyFleet, useCompanyRisk } from "@/services/os-hooks";
import type { FleetVessel } from "@/types/portwatch-os";

export const Route = createFileRoute("/company/fleet")({ component: CompanyFleetScreen });

/** Every vessel, with the worst exposure the event graph found for it. */
function CompanyFleetScreen() {
  const { companyId } = useWorkspace();
  const fleet = useCompanyFleet(companyId);
  const risk = useCompanyRisk(companyId, 72);
  const navigate = useNavigate();

  const exposure = useMemo(() => {
    const map = new Map<string, number>();
    for (const row of risk.data?.rows ?? []) {
      map.set(row.vesselId, Math.max(map.get(row.vesselId) ?? 0, row.exposure));
    }
    return map;
  }, [risk.data?.rows]);

  if (fleet.isLoading || fleet.isError) {
    return (
      <ScreenFallback
        title="Fleet"
        context={<span>Every vessel, scored against the event graph</span>}
        isLoading={fleet.isLoading}
        error={fleet.error}
        retry={() => void fleet.refetch()}
        label="Loading the fleet"
      />
    );
  }

  const columns: Array<Column<FleetVessel>> = [
    {
      key: "name",
      header: "Vessel",
      sort: (row) => row.name,
      render: (row) => (
        <span className="truncate text-[11.5px] text-[var(--text)]">{row.name}</span>
      ),
    },
    {
      key: "id",
      header: "Id",
      width: 84,
      render: (row) => <span className="num text-[10.5px]">{row.vessel_id}</span>,
    },
    {
      key: "class",
      header: "Class",
      width: 106,
      sort: (row) => row.vessel_class,
      render: (row) => (
        <span className="text-[10.5px] text-[var(--text-2)]">
          {row.vessel_class.replace(/_/g, " ")}
        </span>
      ),
    },
    {
      key: "lane",
      header: "Lane",
      sort: (row) => row.laneName ?? "",
      render: (row) => (
        <span className="truncate text-[10.5px] text-[var(--text-2)]">
          {row.laneName ?? "—"}
        </span>
      ),
    },
    {
      key: "voyage",
      header: "Voyage",
      width: 118,
      render: (row) => (
        <span className="num text-[10.5px]">
          {row.origin_port} → {row.destination_port}
        </span>
      ),
    },
    {
      key: "eta",
      header: "ETA",
      width: 96,
      sort: (row) => row.eta ?? "",
      render: (row) => <span className="num text-[10.5px]">{formatUtc(row.eta)}</span>,
    },
    {
      key: "capacity",
      header: "Free",
      align: "right",
      width: 74,
      hint: "Slots still available for onward cargo",
      sort: (row) => row.available_teu,
      render: (row) => (
        <span className="num">{row.available_teu.toFixed(0)} TEU</span>
      ),
    },
    {
      key: "exposure",
      header: "Exposure",
      align: "right",
      width: 76,
      sort: (row) => exposure.get(row.vessel_id) ?? 0,
      render: (row) => {
        const value = exposure.get(row.vessel_id) ?? 0;
        return value > 0 ? (
          <span className={cn("num", `text-[var(--${exposureTone(value)})]`)}>
            {value.toFixed(2)}
          </span>
        ) : (
          <span className="num text-[var(--ok)]">clear</span>
        );
      },
    },
  ];

  return (
    <Page>
      <PageHeader
        title="Fleet"
        context={
          <span className="flex items-center gap-2">
            <span>{fleet.data?.companyName}</span>
            <Pill tone={fleet.data?.verified ? "ok" : "unc"}>
              {fleet.data?.verified ? "verified account" : "demo carrier"}
            </Pill>
          </span>
        }
        meta={
          <>
            <span className="num">{fleet.data?.vessels.length ?? 0} vessels</span>
            <span className="num">
              {risk.data?.vesselsExposed ?? 0} exposed
            </span>
          </>
        }
      />
      <PageBody>
        <Panel
          title="Vessels"
          note={fleet.data?.positionSource}
          testId="company-fleet-table"
        >
          <DataTable<FleetVessel>
            rows={fleet.data?.vessels ?? []}
            rowKey={(row) => row.vessel_id}
            columns={columns}
            initialSort="exposure"
            onRowClick={(row) =>
              void navigate({
                to: "/company/vessels/$vesselId",
                params: { vesselId: row.vessel_id },
              })
            }
          />
        </Panel>
        <p className="mt-2 px-1 text-[10px] leading-relaxed text-[var(--text-3)]">
          {fleet.data?.disclaimer}
        </p>
      </PageBody>
    </Page>
  );
}
