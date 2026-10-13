import { useNavigate } from "@tanstack/react-router";
import {
  Page,
  PageHeader,
  PageBody,
  Panel,
  Section,
} from "@/components/kit/layout";
import { useDemoWorkspace, useDemoAction } from "@/services/demo";
import { formatUtc } from "@/components/kit/primitives";

/** Focused route contracts, with missing evidence kept missing. */
export function DemoCompanyData({
  view,
}: {
  view: "routes" | "cargo" | "advisories";
}) {
  const query = useDemoWorkspace(),
    action = useDemoAction(),
    navigate = useNavigate(),
    data = query.data;
  if (!data)
    return (
      <p role={query.isError ? "alert" : "status"}>
        {query.error?.message ?? "Loading visitor records…"}
      </p>
    );
  const world = data.world;
  return (
    <Page>
      <PageHeader
        title={
          view === "routes"
            ? "Routes"
            : view === "cargo"
              ? "Cargo connections"
              : "Advisories"
        }
        context={
          <span>
            {view === "routes"
              ? "Assigned lanes and preserved voyage comparisons"
              : view === "cargo"
                ? "Declared demo cargo; connection evidence is unavailable"
                : "Visitor-owned port recommendations"}
          </span>
        }
      />
      <PageBody>
        {view === "routes" ? (
          <div className="grid gap-3 lg:grid-cols-2">
            {data.scene.routes
              .filter((r) => world.fleet.some((v) => v.laneCode === r.id))
              .map((r) => (
                <Panel key={r.id} title={r.name} note={r.id}>
                  <Section title="Routing">
                    <p className="text-xs text-[var(--text-3)]">{r.meaning}</p>
                    <p className="mt-2 text-xs">
                      Chokepoints: {r.chokepoints.join(", ")}
                    </p>
                  </Section>
                  <Section title="Assigned vessels">
                    {world.fleet
                      .filter((v) => v.laneCode === r.id)
                      .map((v) => (
                        <button
                          key={v.id}
                          className="command-row"
                          onClick={() =>
                            void action
                              .mutateAsync({
                                path: "/demo/selection",
                                body: { vesselId: v.id },
                              })
                              .then(() => navigate({ to: "/company/overview" }))
                          }
                        >
                          {v.name}
                          <span>Inspect voyage →</span>
                        </button>
                      ))}
                  </Section>
                  <Section title="Comparisons">
                    <p className="text-xs text-[var(--text-3)]">
                      {
                        world.comparisons.filter(
                          (c) =>
                            world.fleet.find((v) => v.id === c.vesselId)
                              ?.laneCode === r.id,
                        ).length
                      }{" "}
                      immutable visitor comparisons. Select a vessel to inspect
                      option geometry and constraints.
                    </p>
                  </Section>
                </Panel>
              ))}
          </div>
        ) : null}
        {view === "cargo" ? (
          <Panel
            title="Declared cargo and arrival plan"
            note="Fictional demonstration"
          >
            <div className="overflow-auto">
              <table className="w-full text-left text-xs">
                <thead>
                  <tr>
                    {[
                      "Vessel",
                      "Declared cargo",
                      "Planned arrival",
                      "Readiness / connection",
                    ].map((t) => (
                      <th className="border-b border-[var(--line)] p-3" key={t}>
                        {t}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {world.fleet.map((v) => (
                    <tr key={v.id}>
                      <td className="border-b border-[var(--line)] p-3">
                        {v.name}
                      </td>
                      <td className="border-b border-[var(--line)] p-3">
                        {v.cargo}
                      </td>
                      <td className="border-b border-[var(--line)] p-3">
                        {formatUtc(
                          new Date(
                            Date.parse(world.epoch) + v.etaHours * 3600000,
                          ).toISOString(),
                        )}
                      </td>
                      <td className="border-b border-[var(--line)] p-3 text-[var(--text-3)]">
                        Cutoff, booking and readiness unavailable
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <Section title="Evidence needed">
              <p className="text-xs text-[var(--text-3)]">
                A declared cargo description does not establish a confirmed
                onward booking. Connection windows, reefer charges and
                missed-service costs are withheld. Voyage comparisons retain
                their original inputs and do not score cargo savings.
              </p>
            </Section>
          </Panel>
        ) : null}
        {view === "advisories" ? (
          <Panel
            title="Port → Company → Vessel"
            note={`${world.advisories.length} records`}
          >
            <Section title="Proposal">
              <p className="text-xs">
                {world.proposal
                  ? `${world.proposal.vesselId} · ${world.proposal.state} · ${formatUtc(world.proposal.createdAt)}`
                  : "No proposal. Compare a voyage in Fleet Command to begin."}
              </p>
            </Section>
            {world.advisories.map((a) => (
              <Section key={a.id} title={`${a.proposal.vesselId} · ${a.state}`}>
                <p className="text-xs">
                  Issued {formatUtc(a.issuedAt)} · {a.portPlan.policy}
                </p>
                <p className="mt-2 text-xs text-[var(--text-3)]">{a.meaning}</p>
                {a.state === "ISSUED" ? (
                  <button
                    className="command-primary"
                    onClick={() =>
                      void action.mutateAsync({
                        path: `/demo/advisories/${a.id}/ack`,
                      })
                    }
                  >
                    Acknowledge advisory
                  </button>
                ) : null}
                {a.outcome ? (
                  <p className="mt-2 text-xs">
                    {a.outcome.reportedWaitingHours}h · {a.outcome.meaning}
                  </p>
                ) : null}
              </Section>
            ))}
          </Panel>
        ) : null}
        {action.isError ? <p role="alert">{action.error.message}</p> : null}
      </PageBody>
    </Page>
  );
}
