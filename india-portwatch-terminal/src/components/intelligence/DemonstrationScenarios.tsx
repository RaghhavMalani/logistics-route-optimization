import { useEffect, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useAuth } from "@/auth/AuthProvider";
import { getJson, postJson } from "@/services/api";
import { Button } from "@/components/ui/button";
import type { DecisionOption, DecisionProblem } from "@/types/decisions";

type Scenario = {
  id: string;
  title: string;
  status: string;
  missingInputs?: string;
  basis: string;
};
type Result = {
  scenarioId: string;
  status: string;
  missingInputs?: string;
  problem?: DecisionProblem;
  inputs?: unknown;
};

export function DemonstrationScenarios({
  onDecision,
  onShowRoute,
}: {
  onDecision?: (problem: DecisionProblem) => void;
  onShowRoute?: (option: DecisionOption) => void;
}) {
  const { session, identityHeaders } = useAuth();
  const client = useQueryClient();
  const [id, setId] = useState("");
  const [ack, setAck] = useState(false);
  const [showComparison, setShowComparison] = useState(false);
  const [requestId, setRequestId] = useState(() => crypto.randomUUID());
  const q = useQuery({
    queryKey: ["demonstration-catalogue", identityHeaders],
    queryFn: ({ signal }) =>
      getJson<{ scenarios: Scenario[] }>(
        "/demonstrations/scenarios",
        identityHeaders,
        { signal },
      ),
    enabled: session?.mode === "demo",
  });
  const select = useMutation({
    mutationFn: () =>
      postJson<Result>(
        "/demonstrations/select",
        { scenarioId: id, requestId, acknowledged: ack },
        identityHeaders,
      ),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ["demonstration-selection"] });
      void client.invalidateQueries({ queryKey: ["port-context"] });
      void client.invalidateQueries({ queryKey: ["fleet-decision-triage"] });
      setRequestId(crypto.randomUUID());
    },
  });
  const advance = useMutation({
    mutationFn: () =>
      postJson(
        "/demonstrations/advance-source",
        { acknowledged: true },
        identityHeaders,
      ),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ["port-context"] });
      void client.invalidateQueries({ queryKey: ["fleet-decision-triage"] });
    },
  });
  const resultCard = useRef<HTMLDivElement>(null);
  const inline = Boolean(onShowRoute);
  useEffect(() => {
    if (inline && select.data) {
      resultCard.current?.scrollIntoView({ block: "start" });
    }
  }, [inline, select.data]);
  if (session?.mode !== "demo" || session.user.role !== "SHIPPING_COMPANY")
    return null;
  const chosen = q.data?.scenarios.find((s) => s.id === id);
  const examples = [
    [
      "S06",
      "Compare a reroute",
      "See the route available before the branch point.",
    ],
    [
      "S15",
      "Check missing weather",
      "See what happens when forecast coverage ends too early.",
    ],
    [
      "S16",
      "Rehearse a cargo handoff",
      "Compare the arrival plan against a loading cutoff.",
    ],
  ].filter(([code]) =>
    q.data?.scenarios.some((scenario) => scenario.id === code),
  );
  function choose(code: string, useFictionalInputs = false) {
    setId(code);
    setAck(useFictionalInputs);
    setShowComparison(false);
    select.reset();
  }
  const result = select.data;
  const problem = result?.problem;
  const recommendation = problem?.recommendation;
  const recommended = problem?.options.find(
    (option) => option.optionId === recommendation?.optionId,
  );
  const reroute = problem?.options.find(
    (option) =>
      option.action.toLowerCase() === "reroute" &&
      option.feasible &&
      option.geometry?.length,
  );
  const mapped =
    (result?.scenarioId === "S06" ? reroute : null) ??
    (recommended?.geometry?.length ? recommended : null) ??
    problem?.options.find(
      (option) => option.feasible && option.geometry?.length,
    );
  const words = recommendation
    ? {
        ACT: "Act",
        KEEP_CURRENT_PLAN: "Keep current plan",
        WAIT_FOR_MORE_INFORMATION: "Wait for more information",
      }[recommendation.kind]
    : "Recommendation unavailable";
  const label = (value: string) => {
    const [first, ...rest] = value.toLowerCase().split("_");
    return [first ? first[0].toUpperCase() + first.slice(1) : "", ...rest].join(
      " ",
    );
  };
  function metrics(option: DecisionOption) {
    const evaluation = option.evaluation;
    const eta = evaluation?.objectives.eta?.value;
    const wait = evaluation?.objectives.port_wait?.value;
    const money = evaluation?.financial;
    const known =
      money?.components.filter(
        (component) => component.state === "KNOWN" && component.money,
      ) ?? [];
    return (
      <dl className="grid gap-1 text-xs">
        <div>
          <dt className="inline font-medium">ETA shift </dt>
          <dd className="inline">
            {eta == null
              ? "Unavailable"
              : `${eta > 0 ? "+" : ""}${eta.toFixed(1)} h`}
          </dd>
        </div>
        <div>
          <dt className="inline font-medium">Anchorage wait </dt>
          <dd className="inline">
            {wait == null ? "Unavailable" : `${wait.toFixed(1)} h`}
          </dd>
        </div>
        <div>
          <dt className="inline font-medium">Known cost components </dt>
          <dd className="inline">
            {known.length
              ? known
                  .map(
                    (component) =>
                      `${component.label}: ${component.money?.currency} ${component.money?.amount.toLocaleString()}${component.isAssumption ? " (assumption)" : ""}`,
                  )
                  .join(" · ")
              : "Unavailable"}
          </dd>
        </div>
      </dl>
    );
  }
  function exportResult() {
    const url = URL.createObjectURL(
      new Blob([JSON.stringify(result, null, 2)], { type: "application/json" }),
    );
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `portwatch-${result?.scenarioId}-illustrative.json`;
    anchor.click();
    URL.revokeObjectURL(url);
  }
  return (
    <section
      aria-label="Shipping demonstrations"
      className="grid gap-2 p-3 text-xs"
      data-testid="demonstration-scenarios"
    >
      <p className="text-[var(--text-2)] font-semibold uppercase tracking-wide">
        Isolated demo
      </p>
      <h3 className="text-base font-semibold">Shipping scenarios</h3>
      <p className="my-2">
        Start a fictional voyage and compare its options. Saved evidence stays
        available, and scenario results stay outside real archives and scoring.
      </p>
      {q.isPending ? (
        <p role="status">Loading the scenario catalogue…</p>
      ) : null}
      {examples.length ? (
        <div className="grid gap-1.5" aria-label="Suggested scenarios">
          {examples.map(([code, title, description]) => (
            <Button
              key={code}
              size="sm"
              variant="outline"
              aria-pressed={id === code}
              disabled={select.isPending}
              className="h-auto min-h-10 justify-start whitespace-normal px-2 py-1.5 text-left"
              onClick={() => choose(code, true)}
            >
              <span>
                <strong className="block">{title}</strong>
                <span className="block text-[var(--text-2)]">
                  {description}
                </span>
              </span>
            </Button>
          ))}
        </div>
      ) : null}
      <label className="block">
        All scenarios{" "}
        <select
          aria-label="Shipping demonstration scenario"
          className="block w-full bg-[var(--panel)] p-2"
          value={id}
          disabled={q.isPending || q.isError || select.isPending}
          onChange={(e) => choose(e.target.value)}
        >
          <option value="">Select a scenario</option>
          {q.data?.scenarios.map((s) => (
            <option key={s.id} value={s.id}>
              {s.id} · {s.title}
            </option>
          ))}
        </select>
      </label>
      {chosen && (
        <p>
          {chosen.basis} {chosen.missingInputs}
        </p>
      )}
      <label className="my-2 flex items-start gap-2">
        <input
          type="checkbox"
          checked={ack}
          onChange={(e) => setAck(e.target.checked)}
        />
        Use these fictional inputs in my isolated demo.
      </label>
      <Button
        size="sm"
        disabled={!id || !ack || select.isPending}
        onClick={() => select.mutate()}
      >
        {select.isPending ? "Calculating…" : "Calculate selected demonstration"}
      </Button>
      {q.isError ? (
        <div>
          <p role="alert">Scenario catalogue unavailable.</p>
          <Button variant="outline" size="sm" onClick={() => void q.refetch()}>
            Retry catalogue
          </Button>
        </div>
      ) : null}
      {select.error && <p role="alert">{select.error.message}</p>}
      {result && (
        <div
          ref={resultCard}
          className="mt-3 border-t border-[var(--line)] pt-2"
        >
          <p className="text-[var(--text-2)]">
            Simulated · illustrative inputs
          </p>
          <h4 className="my-1 text-sm font-semibold">{words}</h4>
          <p className="my-1">
            {recommendation?.statement ||
              recommendation?.why ||
              result.missingInputs ||
              "No supported recommendation for these inputs."}
          </p>
          {recommended ? metrics(recommended) : null}
          <p className="my-2 text-[var(--text-2)]">
            {result.scenarioId} ·{" "}
            {result.status === "RUNNABLE_SIMULATED"
              ? "Runnable · simulated"
              : label(result.status)}
          </p>
          {problem ? (
            <div className="mb-2 flex flex-wrap gap-1">
              {onShowRoute ? (
                <Button
                  size="sm"
                  disabled={!mapped}
                  onClick={() => mapped && onShowRoute(mapped)}
                >
                  Show on map
                </Button>
              ) : null}
              <Button
                size="sm"
                variant="outline"
                aria-expanded={showComparison}
                onClick={() =>
                  onDecision
                    ? onDecision(problem)
                    : setShowComparison(!showComparison)
                }
              >
                See full comparison
              </Button>
              {onShowRoute ? (
                <Button size="sm" variant="outline" disabled>
                  Propose to port
                </Button>
              ) : null}
            </div>
          ) : null}
          {onShowRoute && problem ? (
            <p className="mb-2 text-[var(--text-2)]">
              {mapped
                ? `Map route: ${mapped.label}.`
                : "This comparison has no mapped route."}{" "}
              Port proposals from this panel are pending handoff work.
            </p>
          ) : null}
          {showComparison && problem ? (
            <ul className="my-2 grid gap-2">
              {problem.options.map((option) => (
                <li
                  key={option.optionId}
                  className="border-t border-[var(--line)] pt-2"
                >
                  <strong>
                    {option.label} · {label(option.status)}
                  </strong>
                  {metrics(option)}
                  {option.rejectedBy.map((constraint) => (
                    <p key={constraint.key}>{constraint.detail}</p>
                  ))}
                </li>
              ))}
            </ul>
          ) : null}
          <Button variant="outline" size="sm" onClick={exportResult}>
            Export inputs and result
          </Button>
          {result.scenarioId === "S03" && (
            <div className="mt-2">
              <Button
                size="sm"
                variant="outline"
                onClick={() => advance.mutate()}
              >
                Explicit fixture update: ready rows 4 → 7
              </Button>
              <p>
                Software revision only. Review the exact changed metric and
                create an explicit successor; saved approvals remain unchanged.
              </p>
              {advance.isSuccess && <p>Illustrative revision retained.</p>}
              {advance.error && <p role="alert">{advance.error.message}</p>}
            </div>
          )}
        </div>
      )}
    </section>
  );
}

export function DemonstrationBadge() {
  const { session, identityHeaders } = useAuth();
  const q = useQuery({
    queryKey: ["demonstration-selection", identityHeaders],
    queryFn: ({ signal }) =>
      getJson<{ selection?: { id: string; title: string } }>(
        "/demonstrations/selection",
        identityHeaders,
        { signal },
      ),
    enabled: session?.mode === "demo",
    refetchInterval: 15000,
  });
  if (!q.data?.selection) return null;
  return (
    <div
      className="pointer-events-none absolute left-3 top-12 z-20 max-w-[75%] rounded border border-amber-500/60 bg-[var(--panel)] px-2 py-1 text-[10px] font-semibold text-[var(--text)]"
      data-testid="illustrative-scenario-badge"
    >
      {q.data.selection.id} · ILLUSTRATIVE INPUTS · fictional call, not observed
      operations
    </div>
  );
}
