/**
 * Cargo and transshipment.
 *
 * Two audiences, one engine, and the difference is which half of the answer
 * they need:
 *
 *   A port authority commits a plan -- which box goes to which yard block and
 *   onto which ship. It needs the assignment and the yard consequence.
 *
 *   A shipping company evaluates opportunities -- can this consignment make
 *   that sailing. It needs the feasible connections ranked, without capacity
 *   being committed on its behalf.
 *
 * The unplaced list is not an error log and is given equal weight to the
 * assignments. "Missed the cut-off by 26 hours" and "MV Konkan has 131 reefer
 * plugs free and 240 are needed" are the two most useful sentences on this
 * screen, because they are the ones a planner can act on.
 */

import { useMemo, useState } from "react";

import { Page, PageBody, PageHeader, Panel, Section } from "@/components/kit/layout";
import { Pill } from "@/components/kit/primitives";
import { DataTable, type Column } from "@/components/kit/table";
import { EmptyState, ScreenFallback } from "@/components/kit/states";
import { cn } from "@/lib/utils";
import { useCargoOpportunities, useCargoPlan } from "@/services/os-hooks";
import type {
  CargoAssignment,
  CargoOpportunity,
  CargoUnplaced,
  TwinYardBlock,
} from "@/types/portwatch-os";

type Mode = "plan" | "opportunities";

const CLASS_TONE: Record<string, "info" | "warn" | "crit" | "unc" | "neutral"> = {
  dry: "neutral",
  empty: "neutral",
  reefer: "info",
  hazardous: "crit",
  oog: "warn",
};

export function CargoScreen({
  portCode,
  title,
  mode: fixedMode,
}: {
  portCode: string;
  title: string;
  /** Port authorities land on the plan; companies on opportunities. */
  mode: Mode;
}) {
  const [mode, setMode] = useState<Mode>(fixedMode);
  const plan = useCargoPlan(mode === "plan" ? portCode : null);
  const opportunities = useCargoOpportunities(
    mode === "opportunities" ? portCode : null,
    40,
  );

  const active = mode === "plan" ? plan : opportunities;

  if (active.isLoading || active.isError) {
    return (
      <ScreenFallback
        title={title}
        context={<span className="num">{portCode}</span>}
        isLoading={active.isLoading}
        error={active.error}
        retry={() => void active.refetch()}
        label="Solving the cargo assignment"
      />
    );
  }

  const disclaimer =
    (mode === "plan" ? plan.data?.disclaimer : opportunities.data?.disclaimer) ?? "";

  return (
    <Page>
      <PageHeader
        title={title}
        context={
          <span className="flex items-center gap-2">
            <span className="num">{portCode}</span>
            <Pill tone="unc">Demo cargo</Pill>
          </span>
        }
        meta={
          mode === "plan" && plan.data ? (
            <>
              <span className="num">{plan.data.placedCount} placed</span>
              <span className="num">{plan.data.unplacedCount} unplaced</span>
              <span className="num">{plan.data.totalTeu.toFixed(0)} TEU</span>
            </>
          ) : opportunities.data ? (
            <span className="num">
              {opportunities.data.opportunities.length} feasible connections
            </span>
          ) : null
        }
        actions={
          <div className="flex overflow-hidden rounded-[2px] border border-[var(--line-strong)]">
            {(
              [
                ["plan", "Assignment plan"],
                ["opportunities", "Opportunities"],
              ] as Array<[Mode, string]>
            ).map(([key, label]) => (
              <button
                key={key}
                type="button"
                aria-pressed={mode === key}
                onClick={() => setMode(key)}
                className={cn(
                  "px-2 py-[3px] text-[11px] transition-colors",
                  mode === key
                    ? "bg-[var(--panel-4)] text-[var(--text)]"
                    : "text-[var(--text-3)] hover:bg-[var(--panel-3)] hover:text-[var(--text-2)]",
                )}
              >
                {label}
              </button>
            ))}
          </div>
        }
      />

      <div className="flex shrink-0 items-start gap-2 border-b border-[var(--line)] bg-[var(--unc-dim)]/20 px-4 py-1.5">
        <p className="text-[10.5px] leading-snug text-[var(--text-2)]">
          <span className="font-semibold uppercase tracking-[0.06em] text-[var(--unc)]">
            Demo cargo flow.
          </span>{" "}
          {disclaimer}
        </p>
      </div>

      <PageBody>
        {mode === "plan" && plan.data ? (
          <div className="grid gap-3 xl:grid-cols-[minmax(0,1.35fr)_minmax(0,1fr)]">
            <Panel
              title="Assigned connections"
              note={`${plan.data.assignments.length} shipments`}
              testId="cargo-assignments"
              scroll
              className="max-h-[calc(100vh-260px)]"
            >
              {plan.data.assignments.length === 0 ? (
                <EmptyState
                  title="Nothing could be connected"
                  detail="No transshipment shipment at this port has a feasible onward sailing in the window."
                />
              ) : (
                <DataTable<CargoAssignment>
                  rows={plan.data.assignments}
                  rowKey={(row) => row.shipmentId}
                  initialSort="value"
                  columns={assignmentColumns}
                />
              )}
            </Panel>

            <div className="space-y-3">
              <Panel
                title="Unplaced"
                note={`${plan.data.unplaced.length}`}
                testId="cargo-unplaced"
                scroll
                className="max-h-[420px]"
              >
                {plan.data.unplaced.length === 0 ? (
                  <Section title="All placed">
                    <p className="text-[10.5px] text-[var(--text-3)]">
                      Every transshipment shipment found a connection.
                    </p>
                  </Section>
                ) : (
                  <div>
                    {plan.data.unplaced.map((row) => (
                      <UnplacedRow key={row.shipmentId} row={row} />
                    ))}
                  </div>
                )}
              </Panel>

              {plan.data.yardBlocks?.length ? (
                <Panel title="Yard headroom" note={`${plan.data.yardBlocks.length} blocks`}>
                  <Section title="Free capacity by block">
                    <div className="space-y-1">
                      {plan.data.yardBlocks.map((block) => (
                        <YardBar key={block.block_id} block={block} />
                      ))}
                    </div>
                  </Section>
                </Panel>
              ) : null}

              <Panel title="Method">
                <Section title="How the plan was built">
                  <p className="text-[10.5px] leading-relaxed text-[var(--text-2)]">
                    {plan.data.method}
                  </p>
                </Section>
                {plan.data.notes.length ? (
                  <Section title="Notes">
                    <ul className="space-y-1">
                      {plan.data.notes.map((note) => (
                        <li
                          key={note}
                          className="text-[10px] leading-relaxed text-[var(--text-3)]"
                        >
                          {note}
                        </li>
                      ))}
                    </ul>
                  </Section>
                ) : null}
                <Section title="Residual vessel capacity">
                  <dl className="space-y-[3px]">
                    {Object.entries(plan.data.residualCapacity)
                      .sort((a, b) => b[1] - a[1])
                      .slice(0, 8)
                      .map(([name, teu]) => (
                        <div key={name} className="flex items-baseline justify-between gap-3">
                          <dt className="truncate text-[10.5px] text-[var(--text-3)]">{name}</dt>
                          <dd className="num text-[11px] text-[var(--text)]">
                            {teu.toFixed(0)} TEU
                          </dd>
                        </div>
                      ))}
                  </dl>
                </Section>
              </Panel>
            </div>
          </div>
        ) : null}

        {mode === "opportunities" && opportunities.data ? (
          <Panel
            title="Feasible connections"
            note={`${opportunities.data.opportunities.length} of ${opportunities.data.shipmentsConsidered} shipments`}
            testId="cargo-opportunities"
            scroll
            className="max-h-[calc(100vh-220px)]"
          >
            {opportunities.data.opportunities.length === 0 ? (
              <EmptyState
                title="No feasible connection"
                detail="No shipment at this port can reach an onward sailing within its window, with the capacity and cargo-class rules satisfied."
              />
            ) : (
              <DataTable<CargoOpportunity>
                rows={opportunities.data.opportunities}
                rowKey={(row) => `${row.shipmentId}-${row.outboundVesselId}`}
                initialSort="value"
                columns={opportunityColumns}
              />
            )}
          </Panel>
        ) : null}
      </PageBody>
    </Page>
  );
}

/* --------------------------------------------------------------- columns -- */

const assignmentColumns: Array<Column<CargoAssignment>> = [
  {
    key: "shipment",
    header: "Shipment",
    width: 150,
    sort: (row) => row.shipmentId,
    render: (row) => (
      <span className="num text-[10.5px] text-[var(--text-2)]">{row.shipmentId}</span>
    ),
  },
  {
    key: "teu",
    header: "TEU",
    align: "right",
    width: 54,
    sort: (row) => row.teu,
    render: (row) => <span className="num">{row.teu.toFixed(0)}</span>,
  },
  {
    key: "vessel",
    header: "Onward vessel",
    sort: (row) => row.vesselName,
    render: (row) => (
      <span className="truncate text-[11px] text-[var(--text)]">{row.vesselName}</span>
    ),
  },
  {
    key: "destination",
    header: "To",
    width: 62,
    sort: (row) => row.destinationPort,
    render: (row) => <span className="num text-[10.5px]">{row.destinationPort}</span>,
  },
  {
    key: "zone",
    header: "Yard",
    width: 58,
    render: (row) => (
      <span className="num text-[10.5px] text-[var(--text-3)]">
        {row.zoneId ?? "direct"}
      </span>
    ),
  },
  {
    key: "handling",
    header: "Handling",
    align: "right",
    width: 70,
    hint: "Discharge, yard moves, overhead and load",
    sort: (row) => row.handlingHours,
    render: (row) => <span className="num">{row.handlingHours.toFixed(1)}h</span>,
  },
  {
    key: "slack",
    header: "Slack",
    align: "right",
    width: 62,
    hint: "Hours between ready and the loading cut-off",
    sort: (row) => row.slackHours ?? -1,
    render: (row) =>
      row.slackHours == null ? (
        <span className="text-[10px] text-[var(--text-3)]">n/a</span>
      ) : (
        <span
          className={cn(
            "num",
            row.slackHours < 2 ? "text-[var(--warn)]" : "text-[var(--text-2)]",
          )}
        >
          {row.slackHours.toFixed(1)}h
        </span>
      ),
  },
  {
    key: "value",
    header: "Value",
    align: "right",
    width: 62,
    sort: (row) => row.value,
    render: (row) => <span className="num text-[var(--text)]">{row.value.toFixed(1)}</span>,
  },
];

const opportunityColumns: Array<Column<CargoOpportunity>> = [
  {
    key: "shipment",
    header: "Shipment",
    width: 150,
    sort: (row) => row.shipmentId,
    render: (row) => (
      <span className="num text-[10.5px] text-[var(--text-2)]">{row.shipmentId}</span>
    ),
  },
  {
    key: "class",
    header: "Class",
    width: 88,
    sort: (row) => row.cargoClass,
    render: (row) => (
      <Pill tone={CLASS_TONE[row.cargoClass] ?? "neutral"}>{row.cargoClass}</Pill>
    ),
  },
  {
    key: "teu",
    header: "TEU",
    align: "right",
    width: 54,
    sort: (row) => row.teu,
    render: (row) => <span className="num">{row.teu.toFixed(0)}</span>,
  },
  {
    key: "vessel",
    header: "Onward vessel",
    sort: (row) => row.vesselName,
    render: (row) => (
      <span className="truncate text-[11px] text-[var(--text)]">{row.vesselName}</span>
    ),
  },
  {
    key: "destination",
    header: "To",
    width: 62,
    render: (row) => <span className="num text-[10.5px]">{row.destinationPort}</span>,
  },
  {
    key: "saved",
    header: "Saved",
    align: "right",
    width: 64,
    hint: "Hours earlier than the next sailing to the same destination",
    sort: (row) => row.hoursSaved ?? 0,
    render: (row) =>
      row.hoursSaved == null || row.hoursSaved <= 0 ? (
        <span className="text-[10px] text-[var(--text-3)]">—</span>
      ) : (
        <span className="num text-[var(--ok)]">{row.hoursSaved.toFixed(0)}h</span>
      ),
  },
  {
    key: "slack",
    header: "Slack",
    align: "right",
    width: 62,
    sort: (row) => row.window.slackHours ?? -1,
    render: (row) =>
      row.window.slackHours == null ? (
        <span className="text-[10px] text-[var(--text-3)]">n/a</span>
      ) : (
        <span className="num">{row.window.slackHours.toFixed(1)}h</span>
      ),
  },
  {
    key: "value",
    header: "Value",
    align: "right",
    width: 62,
    sort: (row) => row.value,
    render: (row) => <span className="num text-[var(--text)]">{row.value.toFixed(1)}</span>,
  },
];

/* ------------------------------------------------------------------ rows -- */

function UnplacedRow({ row }: { row: CargoUnplaced }) {
  return (
    <div className="border-b border-[var(--line)]/60 px-2 py-1.5 last:border-0">
      <div className="flex items-baseline gap-2">
        <span className="num text-[10.5px] text-[var(--text-2)]">{row.shipmentId}</span>
        <Pill tone={CLASS_TONE[row.cargoClass] ?? "neutral"}>{row.cargoClass}</Pill>
        <span className="num ml-auto text-[10.5px] text-[var(--text-3)]">
          {row.teu.toFixed(0)} TEU → {row.destinationPort}
        </span>
      </div>
      <ul className="mt-1 space-y-0.5">
        {row.reasons.slice(0, 3).map((reason) => (
          <li key={reason} className="text-[9.5px] leading-snug text-[var(--text-3)]">
            {reason}
          </li>
        ))}
      </ul>
      {row.shortfallHours != null ? (
        <div className="num mt-[3px] text-[9.5px] text-[var(--warn)]">
          Nearest option {row.nearestVessel} — short by {row.shortfallHours.toFixed(1)} h
        </div>
      ) : null}
    </div>
  );
}

function YardBar({ block }: { block: TwinYardBlock }) {
  const pct = Math.min(100, block.utilisation * 100);
  return (
    <div>
      <div className="flex items-baseline justify-between gap-2">
        <span className="text-[10px] text-[var(--text-2)]">{block.name}</span>
        <span className="num text-[9.5px] text-[var(--text-3)]">
          {block.occupied_teu.toFixed(0)} / {block.capacityTeu.toFixed(0)} TEU
        </span>
      </div>
      <div className="mt-[2px] h-[5px] overflow-hidden rounded-[1px] bg-[var(--panel-3)]">
        <div
          className="h-full rounded-[1px]"
          style={{
            width: `${pct}%`,
            background:
              pct > 95 ? "var(--crit)" : pct > 80 ? "var(--warn)" : "var(--ok)",
          }}
        />
      </div>
    </div>
  );
}
