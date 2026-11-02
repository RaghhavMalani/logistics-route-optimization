import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useAuth } from "@/auth/AuthProvider";
import { getJson, postJson } from "@/services/api";
import type { DecisionProblem } from "@/types/decisions";
import { formatUtc } from "@/components/kit/primitives";
import { PanelTabs } from "@/components/command/panels";

interface Shipment {
  id: string;
  goodsClass: string;
  destinationPort: string;
  event: string;
  deadline?: string;
  required: boolean;
  deliveryOffsetHours?: string;
  offsetBasis?: string;
  quantity?: string;
  quantityUnit?: string;
  [key: string]: unknown;
}
interface Draft {
  decisionId: string;
  voyageId: string;
  objectiveParty: string;
  currency: string;
  accountingScope: string;
  consignments: Shipment[];
  [key: string]: unknown;
}
interface Statistics {
  mean: number;
  median: number;
  p05: number;
  p95: number;
  cvar: number;
  numericalMeanStdError: number | null;
  convergence: { absoluteDrift: number };
}
interface Result {
  recordId: string;
  createdAt: string;
  contextHash: string;
  consumedEvidenceHash: string;
  context: Draft;
  evaluation: {
    version: string;
    policyVersion: string;
    decision: string;
    commercialPick: string | null;
    incumbentPick: string | null;
    currency: string;
    options: {
      optionId: string;
      label: string;
      status: string;
      comparableTotal: string | null;
      supportedComponentTotal: string;
      missingComponents: string[];
      reasons: string[];
      consignments: {
        shipmentId: string;
        event: string;
        eventAt: string | null;
        slackHours: number | null;
        status: string;
      }[];
    }[];
    insurance: {
      policies: {
        id: string | null;
        cover: string | null;
        status: string;
        issues: string[];
      }[];
      meaning: string;
    };
  };
  uncertainty?: {
    mode: string;
    status: string;
    reason?: string;
    seed: number;
    draws: number;
    worldSampleHash: string;
    alpha: number;
    tailPreference: number;
    conditionalShadowPick: string | null;
    options?: {
      optionId: string;
      supportedCost: Statistics | null;
      conditionalConstraintFailureFrequency: number;
      pairedDeltaVsCurrent: Statistics | null;
      missingBasis: boolean;
    }[];
    sensitivity?: {
      handlingDelayHours: number;
      conditionalPick: string | null;
    }[];
  };
  resourceConflicts: { resourceId: string; status: string }[];
}
type View = "cargo" | "impact" | "insurance" | "uncertainty";

/** Company-private sidecar. New studies never overwrite the passage or its approval. */
export function CommercialReview({
  problem,
  onSuccessor,
}: {
  problem: DecisionProblem;
  onSuccessor: (p: DecisionProblem) => void;
}) {
  const { identityHeaders } = useAuth();
  const qc = useQueryClient();
  const [view, setView] = useState<View>("cargo");
  const [example, setExample] = useState("CURRENT_SOURCE");
  const [description, setDescription] = useState("");
  const [draft, setDraft] = useState<Draft | null>(null);
  const [advanced, setAdvanced] = useState("");
  const [simulation, setSimulation] = useState<Record<string, unknown> | null>(
    null,
  );
  const [simulationText, setSimulationText] = useState("");
  const [ack, setAck] = useState(false);
  const [localError, setLocalError] = useState("");
  const [selected, setSelected] = useState<Result | null>(null);
  const [activeJob, setActiveJob] = useState<string | null>(null);
  const binding = problem.evidence.commercialReview as
    { recordId?: string } | undefined;
  const retained = useQuery({
    queryKey: ["commercial", problem.decisionId, binding?.recordId],
    queryFn: async () =>
      binding?.recordId
        ? [
            await getJson<Result>(
              `/commercial/records/${binding.recordId}`,
              identityHeaders,
            ),
          ]
        : (
            await getJson<{ records: Result[] }>(
              `/commercial/comparisons/${problem.decisionId}`,
              identityHeaders,
            )
          ).records,
    staleTime: 30000,
  });
  const result = selected ?? retained.data?.[0];
  const template = useMutation({
    mutationFn: () =>
      getJson<{
        context: Draft;
        simulation: Record<string, unknown>;
        description: string;
      }>(
        `/commercial/templates/${problem.decisionId}?example=${encodeURIComponent(example)}`,
        identityHeaders,
      ),
    onSuccess: (d) => {
      setDraft(d.context);
      setDescription(d.description);
      setSimulation(d.simulation);
      setSimulationText(JSON.stringify(d.simulation, null, 2));
      setAdvanced(JSON.stringify(d.context, null, 2));
      setAck(false);
      setLocalError("");
    },
  });
  const calculate = useMutation({
    mutationFn: async (withSimulation: boolean) => {
      const jobId = withSimulation ? crypto.randomUUID() : null;
      setActiveJob(jobId);
      try {
        return await postJson<Result>(
          "/commercial/evaluate",
          {
            context: draft,
            ...(withSimulation
              ? {
                  simulation: { ...simulation, acknowledgedAssumptions: ack },
                  jobId,
                }
              : {}),
          },
          identityHeaders,
          { timeoutMs: 60000 },
        );
      } finally {
        setActiveJob(null);
      }
    },
    onSuccess: (r) => {
      setSelected(r);
      void qc.invalidateQueries({ queryKey: ["commercial"] });
      setView(r.uncertainty ? "uncertainty" : "impact");
    },
  });
  const cancel = useMutation({
    mutationFn: () =>
      postJson(`/commercial/jobs/${activeJob}/cancel`, {}, identityHeaders),
  });
  const successor = useMutation({
    mutationFn: () =>
      postJson<DecisionProblem>(
        `/commercial/records/${result!.recordId}/successor`,
        {},
        identityHeaders,
      ),
    onSuccess: onSuccessor,
  });
  const editShipment = (index: number, key: string, value: unknown) =>
    setDraft((d) =>
      d
        ? {
            ...d,
            consignments: d.consignments.map((s, i) =>
              i === index ? { ...s, [key]: value } : s,
            ),
          }
        : d,
    );
  const error =
    localError ||
    template.error?.message ||
    calculate.error?.message ||
    cancel.error?.message ||
    successor.error?.message;
  return (
    <section className="pw-commercial" aria-label="Company commercial review">
      <header>
        <span className="pw-plan-kicker">
          Company private · demonstration planning
        </span>
        <h3>Cargo & commercial review</h3>
        <p>
          Frozen passage → declared commitments → supported component impact.
          Incumbent recommendation and human choice stay distinct.
        </p>
      </header>
      <PanelTabs
        value={view}
        onChange={setView}
        tabs={[
          { value: "cargo", label: "Cargo" },
          { value: "impact", label: "Impact" },
          { value: "insurance", label: "Insurance" },
          { value: "uncertainty", label: "Uncertainty" },
        ]}
      />
      {retained.isError ? (
        <p role="alert">
          Saved commercial studies unavailable. No complete-cost conclusion.
        </p>
      ) : null}
      {!draft ? (
        <div className="pw-commercial-start">
          <label>
            Explicit commercial example
            <select
              value={example}
              onChange={(e) => setExample(e.target.value)}
            >
              {[
                ["CURRENT_SOURCE", "Current frozen basis"],
                ["PERISHABLE", "Perishable commitment"],
                ["BULK", "Nonurgent bulk"],
                ["MANUFACTURING", "Critical manufacturing input"],
                ["ELECTRONICS", "Electronics: invoice / insured value"],
                ["CHOKEPOINT", "Chokepoint: strategic boundary"],
                ["INSURANCE", "Insurance review required"],
                ["MARKET", "Dated market proxy"],
                ["MEAN_TAIL", "Mean / tail preference"],
                ["MULTI", "Multiple consignments"],
                ["INCOMPLETE", "Incomplete accounting basis"],
                ["REVISION", "Revision and fresh review"],
                ["RESOURCE", "Shared resource conflict"],
              ].map(([id, label]) => (
                <option key={id} value={id}>
                  {label}
                </option>
              ))}
            </select>
          </label>
          <p>
            Use an explicit fictional template, or inspect the retained study
            below. No private commercial feed is assumed.
          </p>
          <button
            type="button"
            disabled={template.isPending}
            onClick={() => template.mutate()}
          >
            Prepare editable fictional declaration
          </button>
        </div>
      ) : null}
      {description ? <p className="pw-source-limit">{description}</p> : null}
      {view === "cargo" && draft ? (
        <div className="pw-commercial-form">
          <label>
            Whose objective?
            <input
              value={draft.objectiveParty}
              onChange={(e) =>
                setDraft({ ...draft, objectiveParty: e.target.value })
              }
            />
          </label>
          <label>
            Accounting scope
            <textarea
              value={draft.accountingScope}
              onChange={(e) =>
                setDraft({ ...draft, accountingScope: e.target.value })
              }
            />
          </label>
          <p className="pw-source-limit">
            All template fields are fictional declarations. Invoice, replacement
            and insured values remain separate; missing money is unknown.
          </p>
          {draft.consignments.map((shipment, index) => (
            <fieldset key={index}>
              <legend>Consignment {index + 1}</legend>
              <label>
                Stable shipment ID
                <input
                  value={shipment.id}
                  onChange={(e) => editShipment(index, "id", e.target.value)}
                />
              </label>
              <label>
                Goods class
                <input
                  value={shipment.goodsClass}
                  onChange={(e) =>
                    editShipment(index, "goodsClass", e.target.value)
                  }
                />
              </label>
              <label>
                Destination port
                <input
                  value={shipment.destinationPort}
                  onChange={(e) =>
                    editShipment(index, "destinationPort", e.target.value)
                  }
                />
              </label>
              <label>
                Contract event
                <select
                  value={shipment.event}
                  onChange={(e) => editShipment(index, "event", e.target.value)}
                >
                  <option value="CONDITIONAL_APPROACH">
                    Conditional clear approach
                  </option>
                  <option value="CONDITIONAL_CARGO_READY">
                    Conditional cargo ready · supported stage declaration
                    required
                  </option>
                  <option value="DECLARED_FINAL_DELIVERY">
                    Declared final delivery · assumed offset
                  </option>
                </select>
              </label>
              <label>
                Deadline · timezone required
                <input
                  value={shipment.deadline ?? ""}
                  placeholder="2026-11-04T12:00:00+05:30"
                  onChange={(e) =>
                    editShipment(index, "deadline", e.target.value || null)
                  }
                />
              </label>
              {shipment.event === "DECLARED_FINAL_DELIVERY" ? (
                <>
                  <label>
                    Assumed downstream interval (hours)
                    <input
                      type="number"
                      min="0"
                      value={shipment.deliveryOffsetHours ?? ""}
                      onChange={(e) =>
                        editShipment(
                          index,
                          "deliveryOffsetHours",
                          e.target.value || null,
                        )
                      }
                    />
                  </label>
                  <label>
                    Interval basis
                    <input
                      value={shipment.offsetBasis ?? ""}
                      onChange={(e) =>
                        editShipment(index, "offsetBasis", e.target.value)
                      }
                    />
                  </label>
                </>
              ) : null}
              <label className="pw-check">
                <input
                  type="checkbox"
                  checked={shipment.required}
                  onChange={(e) =>
                    editShipment(index, "required", e.target.checked)
                  }
                />{" "}
                Required commitment
              </label>
              <button
                type="button"
                onClick={() =>
                  setDraft({
                    ...draft,
                    consignments: draft.consignments.filter(
                      (_, i) => i !== index,
                    ),
                  })
                }
              >
                Remove this declaration
              </button>
            </fieldset>
          ))}
          <button
            type="button"
            onClick={() => {
              const first = draft.consignments[0];
              if (first)
                setDraft({
                  ...draft,
                  consignments: [
                    ...draft.consignments,
                    {
                      ...structuredClone(first),
                      id: `demo-consignment-${draft.consignments.length + 1}`,
                    },
                  ],
                });
            }}
          >
            Add fictional consignment from declared template
          </button>
        </div>
      ) : null}
      {view === "insurance" ? (
        <div>
          <h4>Insurance review</h4>
          <p>
            Policy evidence is Company-private. Listed-area context is a
            review/notification lead, never a closure, premium or finding that a
            vessel is uninsured.
          </p>
          {result?.evaluation.insurance.policies.map((p, i) => (
            <article className="pw-product-row" key={p.id ?? i}>
              <h4>
                {p.cover ?? "Policy evidence"} · {p.status.replaceAll("_", " ")}
              </h4>
              {p.issues.map((issue) => (
                <p key={issue}>{issue}</p>
              ))}
            </article>
          ))}
          <p>
            Recovery, gross insured loss and payable claims remain unavailable.
            Declare separate cargo, hull, P&I, war/strikes, loss-of-hire or
            specialist terms in the full declaration.
          </p>
          <a
            href="https://lmalloyds.com/specialist-areas/underwriting/listed-areas/"
            target="_blank"
            rel="noreferrer"
          >
            LMA/JWC published listed areas
          </a>
        </div>
      ) : null}
      {(view === "cargo" || view === "impact") && result ? (
        <div>
          <h4>{result.evaluation.decision.replaceAll("_", " ")}</h4>
          <p>
            Incumbent: {result.evaluation.incumbentPick ?? "Unavailable"} ·
            Commercial shadow:{" "}
            {result.evaluation.commercialPick ?? "No supported pick"}
          </p>
          <div
            className="pw-scroll-table"
            role="region"
            aria-label="Commercial component comparison"
            tabIndex={0}
          >
            <table>
              <thead>
                <tr>
                  <th>Plan</th>
                  <th>Supported components</th>
                  <th>Commitment / basis</th>
                </tr>
              </thead>
              <tbody>
                {result.evaluation.options.map((o) => (
                  <tr key={o.optionId}>
                    <th>
                      {o.label}
                      <small>{o.status.replaceAll("_", " ")}</small>
                    </th>
                    <td>
                      {result.evaluation.currency} {o.supportedComponentTotal}
                      <small>
                        {o.comparableTotal === null
                          ? "Incomplete / review required; total unavailable"
                          : "Complete for declared component scope only"}
                      </small>
                    </td>
                    <td>
                      {o.reasons.map((r) => (
                        <p key={r}>{r}</p>
                      ))}
                      {o.missingComponents.length ? (
                        <p>Missing: {o.missingComponents.join(", ")}</p>
                      ) : null}
                      {o.consignments.map((s) => (
                        <p key={s.shipmentId}>
                          {s.shipmentId} · {s.status} · slack{" "}
                          {s.slackHours == null
                            ? "unknown"
                            : `${s.slackHours.toFixed(2)} h`}
                          <small>
                            {s.event}: {formatUtc(s.eventAt)}
                          </small>
                        </p>
                      ))}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {result.resourceConflicts.map((r, i) => (
            <p key={i}>
              {r.resourceId}: {r.status}
            </p>
          ))}
          <p>
            Complete profit, measured savings and insurance recovery are
            unavailable.
          </p>
        </div>
      ) : null}
      {view === "uncertainty" ? (
        <div>
          <h4>Uncertainty · separate shadow study</h4>
          <p>
            V1 varies one shared additional downstream handling delay. Hourly
            gust/visibility gates, physical sailing and modeled fuel stay
            frozen. Daily weather residuals do not calibrate this distribution.
          </p>
          {simulation && draft ? (
            <>
              <label>
                Mode
                <select
                  value={String(simulation.mode)}
                  onChange={(e) =>
                    setSimulation({ ...simulation, mode: e.target.value })
                  }
                >
                  <option>ASSUMPTION_SENSITIVITY</option>
                  <option>EMPIRICAL_SHADOW</option>
                </select>
              </label>
              <label>
                Sample budget
                <input
                  type="number"
                  min="16"
                  max="4096"
                  value={Number(simulation.draws)}
                  onChange={(e) =>
                    setSimulation({
                      ...simulation,
                      draws: Number(e.target.value),
                    })
                  }
                />
              </label>
              <label>
                Seed
                <input
                  type="number"
                  min="0"
                  value={Number(simulation.seed)}
                  onChange={(e) =>
                    setSimulation({
                      ...simulation,
                      seed: Number(e.target.value),
                    })
                  }
                />
              </label>
              <label>
                Tail preference λ (0–1)
                <input
                  type="number"
                  min="0"
                  max="1"
                  step=".1"
                  value={Number(simulation.tailPreference)}
                  onChange={(e) =>
                    setSimulation({
                      ...simulation,
                      tailPreference: Number(e.target.value),
                    })
                  }
                />
              </label>
              <details>
                <summary>Distribution and dependency declaration</summary>
                <textarea
                  aria-label="Uncertainty configuration JSON"
                  rows={12}
                  value={simulationText}
                  onChange={(e) => setSimulationText(e.target.value)}
                />
                <button
                  type="button"
                  onClick={() => {
                    try {
                      setSimulation(JSON.parse(simulationText));
                      setLocalError("");
                    } catch {
                      setLocalError(
                        "Use valid JSON; the previous configuration remains retained.",
                      );
                    }
                  }}
                >
                  Apply uncertainty configuration
                </button>
                <button
                  type="button"
                  onClick={() =>
                    setSimulationText(JSON.stringify(simulation, null, 2))
                  }
                >
                  Load current sampler settings
                </button>
              </details>
              <label className="pw-check">
                <input
                  type="checkbox"
                  checked={ack}
                  onChange={(e) => setAck(e.target.checked)}
                />{" "}
                I deliberately accept these assumed hours, weights and shared
                dependency; they are not calibrated probabilities.
              </label>
              <button
                type="button"
                disabled={
                  calculate.isPending ||
                  (!ack && simulation.mode === "ASSUMPTION_SENSITIVITY")
                }
                onClick={() => calculate.mutate(true)}
              >
                Run and retain shadow study
              </button>
              {calculate.isPending && activeJob ? (
                <button
                  type="button"
                  disabled={cancel.isPending}
                  onClick={() => cancel.mutate()}
                >
                  Cancel running study
                </button>
              ) : null}
              <p className="pw-source-limit">
                One study at a time, up to 20 seconds. Cancellation keeps
                earlier retained studies.
              </p>
            </>
          ) : null}
          {result?.uncertainty ? (
            <>
              <p>
                {result.uncertainty.mode} · {result.uncertainty.status}
              </p>
              {result.uncertainty.reason ? (
                <p>{result.uncertainty.reason}</p>
              ) : (
                <>
                  <p>
                    {result.uncertainty.draws} simulated draws · seed{" "}
                    {result.uncertainty.seed} · 0 independent operational
                    targets
                  </p>
                  <div
                    className="pw-scroll-table"
                    role="region"
                    aria-label="Shadow uncertainty results"
                    tabIndex={0}
                  >
                    <table>
                      <thead>
                        <tr>
                          <th>Plan</th>
                          <th>Mean / tail loss</th>
                          <th>Paired delta / assumed failure</th>
                        </tr>
                      </thead>
                      <tbody>
                        {result.uncertainty.options?.map((o) => (
                          <tr key={o.optionId}>
                            <th>{o.optionId}</th>
                            <td>
                              {o.supportedCost ? (
                                <>
                                  {o.supportedCost.mean.toFixed(2)} / CVaR{" "}
                                  {o.supportedCost.cvar.toFixed(2)}
                                  <small>
                                    P05–P95 {o.supportedCost.p05.toFixed(2)}–
                                    {o.supportedCost.p95.toFixed(2)}{" "}
                                    {result.evaluation.currency}
                                  </small>
                                  <small>
                                    Numerical mean SE{" "}
                                    {o.supportedCost.numericalMeanStdError?.toFixed(
                                      2,
                                    ) ?? "unknown"}
                                    ; half/full drift{" "}
                                    {o.supportedCost.convergence.absoluteDrift.toFixed(
                                      2,
                                    )}
                                  </small>
                                </>
                              ) : (
                                "Material cost basis incomplete"
                              )}
                            </td>
                            <td>
                              {o.pairedDeltaVsCurrent?.mean.toFixed(2) ??
                                "Unknown"}
                              <small>
                                {(
                                  o.conditionalConstraintFailureFrequency * 100
                                ).toFixed(1)}
                                % simulated required-gate failures
                              </small>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                  <p>
                    Conditional pick:{" "}
                    {result.uncertainty.conditionalShadowPick ??
                      "No supported pick"}
                    . Input/model uncertainty is unvalidated; more draws do not
                    repair it.
                  </p>
                  <details>
                    <summary>When the declared choice changes</summary>
                    {result.uncertainty.sensitivity?.map((s) => (
                      <p key={s.handlingDelayHours}>
                        {s.handlingDelayHours} h additional handling →{" "}
                        {s.conditionalPick ??
                          "No feasible complete-scope choice"}
                      </p>
                    ))}
                  </details>
                </>
              )}
            </>
          ) : null}
        </div>
      ) : null}
      {draft ? (
        <details className="pw-commercial-advanced">
          <summary>
            Full declaration · parties, prices, policy terms, resources and
            evidence
          </summary>
          <p>
            Each material field inherits its explicit declaration basis and
            typed unit. Unknown amounts are null. Private details stay within
            Company.
          </p>
          <button
            type="button"
            onClick={() => setAdvanced(JSON.stringify(draft, null, 2))}
          >
            Load current form into JSON editor
          </button>
          <textarea
            aria-label="Commercial declaration JSON"
            rows={18}
            value={advanced}
            onChange={(e) => setAdvanced(e.target.value)}
          />
          <button
            type="button"
            onClick={() => {
              try {
                const value = JSON.parse(advanced) as Draft;
                if (
                  !value ||
                  typeof value !== "object" ||
                  value.decisionId !== problem.decisionId ||
                  !Array.isArray(value.consignments) ||
                  value.consignments.some(
                    (row) =>
                      !row ||
                      typeof row !== "object" ||
                      typeof row.id !== "string" ||
                      typeof row.goodsClass !== "string" ||
                      typeof row.destinationPort !== "string" ||
                      typeof row.event !== "string",
                  )
                )
                  throw Error(
                    "Keep this exact comparison identity and a consignment list",
                  );
                setDraft(value);
                setLocalError("");
              } catch (e) {
                setLocalError((e as Error).message);
              }
            }}
          >
            Apply edited declaration
          </button>
        </details>
      ) : null}
      {error ? <p role="alert">{error}</p> : null}
      {draft ? (
        <div className="pw-next-action">
          <button
            type="button"
            disabled={calculate.isPending}
            onClick={() => calculate.mutate(false)}
          >
            Evaluate declared components
          </button>
        </div>
      ) : null}
      {result ? (
        <>
          <p className="pw-meta">
            Retained {formatUtc(result.createdAt)} · {result.evaluation.version}{" "}
            · {result.evaluation.policyVersion}
          </p>
          <details>
            <summary>Frozen study and reproducibility hashes</summary>
            <pre className="pw-json">{JSON.stringify(result, null, 2)}</pre>
          </details>
          <button
            type="button"
            disabled={successor.isPending}
            onClick={() => successor.mutate()}
          >
            Create commercial successor for fresh review
          </button>
          <p>
            Earlier approvals remain inspectable. This explicitly creates a new
            comparison; it issues no advisory. Port and Vessel receive the plan
            and a minimal review binding, never private invoices or policy text.
          </p>
        </>
      ) : null}
    </section>
  );
}
