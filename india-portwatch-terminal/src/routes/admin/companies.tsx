import { createFileRoute } from "@tanstack/react-router";

import { exposureTone } from "@/components/globaleye/EventPanels";
import { Page, PageBody, PageHeader, Panel, Section } from "@/components/kit/layout";
import { Pill, formatUtc } from "@/components/kit/primitives";
import { DataTable, type Column } from "@/components/kit/table";
import { ScreenFallback } from "@/components/kit/states";
import { cn } from "@/lib/utils";
import { useCompanyFleet, useCompanyRisk } from "@/services/os-hooks";
import type { FleetVessel } from "@/types/portwatch-os";
import { useMemo } from "react";

export const Route = createFileRoute("/admin/companies")({ component: AdminCompanies });

/**
 * Carrier accounts, from national command.
 *
 * One account is configured in this deployment and it is a demo carrier. The
 * screen says so at the top rather than presenting a fictional fleet as a
 * customer list -- the `verified` flag comes from the provider, and nothing is
 * marked verified unless a provider asserted it.
 */
function AdminCompanies() {
  const fleet = useCompanyFleet(null);
  const risk = useCompanyRisk(null, 72);

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
        title="Companies"
        context={<span>Carrier accounts and their fleets</span>}
        isLoading={fleet.isLoading}
        error={fleet.error}
        retry={() => void fleet.refetch()}
        label="Loading carrier accounts"
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
      key: "class",
      header: "Class",
      width: 112,
      sort: (row) => row.vessel_class,
      render: (row) => (
        <span className="text-[10.5px] text-[var(--text-2)]">
          {row.vessel_class.replace(/_/g, " ")}
        </span>
      ),
    },
    {
      key: "flag",
      header: "Flag",
      width: 52,
      render: (row) => <span className="num text-[10.5px]">{row.flag}</span>,
    },
    {
      key: "capacity",
      header: "Capacity",
      align: "right",
      width: 86,
      sort: (row) => row.capacity_teu,
      render: (row) => (
        <span className="num">{row.capacity_teu.toLocaleString()} TEU</span>
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
      key: "eta",
      header: "ETA",
      width: 96,
      sort: (row) => row.eta ?? "",
      render: (row) => <span className="num text-[10.5px]">{formatUtc(row.eta)}</span>,
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
        title="Companies"
        context={<span>Carrier accounts registered with this deployment</span>}
        meta={<span className="num">1 account</span>}
      />
      <PageBody>
        <div className="grid gap-3 xl:grid-cols-[minmax(0,1fr)_320px]">
          <Panel
            title={fleet.data?.companyName ?? "Fleet"}
            note={`${fleet.data?.vessels.length ?? 0} vessels`}
            testId="admin-companies-table"
          >
            <DataTable<FleetVessel>
              rows={fleet.data?.vessels ?? []}
              rowKey={(row) => row.vessel_id}
              columns={columns}
              initialSort="exposure"
            />
          </Panel>

          <div className="space-y-3">
            <Panel title="Account">
              <Section title={fleet.data?.companyId ?? ""}>
                <dl className="space-y-[3px]">
                  <div className="flex items-baseline justify-between gap-2">
                    <dt className="text-[10.5px] text-[var(--text-3)]">Verified</dt>
                    <dd>
                      <Pill tone={fleet.data?.verified ? "ok" : "unc"}>
                        {fleet.data?.verified ? "yes" : "no — demo carrier"}
                      </Pill>
                    </dd>
                  </div>
                  <div className="flex items-baseline justify-between gap-2">
                    <dt className="text-[10.5px] text-[var(--text-3)]">Position source</dt>
                    <dd className="num text-[11px] text-[var(--text)]">
                      {fleet.data?.positionSource}
                    </dd>
                  </div>
                  <div className="flex items-baseline justify-between gap-2">
                    <dt className="text-[10.5px] text-[var(--text-3)]">Vessels exposed</dt>
                    <dd className="num text-[11px] text-[var(--text)]">
                      {risk.data?.vesselsExposed ?? 0}
                    </dd>
                  </div>
                </dl>
              </Section>
              <Section title="What this is">
                <p className="text-[10px] leading-relaxed text-[var(--text-3)]">
                  {fleet.data?.disclaimer}
                </p>
              </Section>
            </Panel>

            <Panel title="Adding a real carrier">
              <Section title="Integration">
                <p className="text-[10px] leading-relaxed text-[var(--text-3)]">
                  Set <span className="num">PORTWATCH_FLEET_PROVIDER</span> to a provider
                  payload and the account interface is populated from it instead. Every
                  downstream surface — exposure, cargo, advisories — reads the same
                  interface, so a real integration changes no screen in this workspace.
                </p>
              </Section>
            </Panel>
          </div>
        </div>
      </PageBody>
    </Page>
  );
}
