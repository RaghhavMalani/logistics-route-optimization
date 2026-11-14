import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useAuth } from "@/auth/AuthProvider";
import { postJson } from "@/services/api";
import { CARGO_STUDY_SEED, type RiskReport, type RiskResponse, type Rule } from "./types";

function shadowReport(response: RiskResponse | undefined): RiskReport | undefined {
  return response?.status === "SHADOW" ? response : undefined;
}

function change(value: number, unit: (amount: number) => string, measure: string, precision: number) {
  if (Math.abs(value) < precision) return `keeps ${measure} the same`;
  return `${value > 0 ? "adds" : "saves"} ${unit(Math.abs(value))} in ${measure}`;
}

function Tradeoff({ cost, tail }: { cost: RiskReport; tail: RiskReport | undefined }) {
  const choice = cost.options.find((option) => option.id === cost.decision.optionId);
  const keep = cost.options.find((option) => option.id === cost.keepOptionId);
  if (!choice || !keep || !choice.cost.knownSubtotal || !keep.cost.knownSubtotal) {
    return <p>Cost-first · {cost.decision.reason}</p>;
  }
  const price = (value: number) => `${cost.currency} ${value.toLocaleString("en-US", { maximumFractionDigits: 0 })}`;
  const time = (value: number) => `${value.toFixed(1)} h`;
  const costChange = choice.cost.knownSubtotal.expected - keep.cost.knownSubtotal.expected;
  const timeChange = choice.arrival.mean.estimate - keep.arrival.mean.estimate;
  const alternative = tail?.inputHash === cost.inputHash && tail.decision.optionId !== choice.id
    ? tail.options.find((option) => option.id === tail.decision.optionId)
    : undefined;
  const alternativeCost = alternative?.cost.knownSubtotal;
  return (
    <>
      <p data-testid="company-cost-first">
        <strong>Cost-first (R1) · {choice.label}</strong>
        {choice.id === keep.id ? " keeps the current plan." : (
          <> {change(costChange, price, "expected cost", 0.5)} and {change(timeChange, time, "mean delivery time", 0.05)} versus the current plan.</>
        )}
      </p>
      {alternative && alternativeCost ? (
        <p data-testid="company-tail-alternative">
          <strong>Tail-cost rule (R3) · {alternative.label}.</strong>{" "}
          Versus R1, {change(alternativeCost.cvar95 - choice.cost.knownSubtotal.cvar95, price, "mean cost across the worst 5% of modelled futures", 0.5)}
          {" and "}{change(alternativeCost.expected - choice.cost.knownSubtotal.expected, price, "expected cost", 0.5)}.
        </p>
      ) : null}
      <p className="text-[var(--text-3)]">{choice.cost.scope} · {cost.scope}</p>
    </>
  );
}

export function DecisionTradeoff({ problemId }: { problemId: string }) {
  const { identityHeaders, session } = useAuth();
  const [enabled, setEnabled] = useState(false);
  const path = `/commercial/comparisons/${encodeURIComponent(problemId)}/cargo-risk`;
  const run = (rule: Rule, signal: AbortSignal) => postJson<RiskResponse>(
    path, { rule, seed: CARGO_STUDY_SEED }, identityHeaders, { signal, timeoutMs: 45_000 },
  );
  const scope = session?.user.id;
  const r1 = useQuery({ queryKey: ["company-tradeoff", scope, problemId, "R1"],
    queryFn: ({ signal }) => run("R1", signal), enabled, staleTime: Infinity, retry: false });
  const cost = shadowReport(r1.data);
  const r3 = useQuery({ queryKey: ["company-tradeoff", scope, problemId, "R3"],
    queryFn: ({ signal }) => run("R3", signal), enabled: enabled && Boolean(cost?.decision.optionId),
    staleTime: Infinity, retry: false });
  return (
    <section aria-label="Modelled cargo trade-off" className="space-y-1 border-b border-[var(--line)] px-2 py-2 text-xs">
      <p className="eyebrow">Company private · Modelled shadow study</p>
      {cost ? <Tradeoff cost={cost} tail={shadowReport(r3.data)} /> : null}
      {r1.data?.status === "UNAVAILABLE" ? <p>{r1.data.reason}</p> : null}
      {r1.isFetching || r3.isFetching ? <p role="status">Comparing modelled cargo costs…</p> : null}
      {r1.isError || r3.isError ? <p role="status">{r1.isError ? "The cost-first study is unavailable." : "The tail-cost study is unavailable."}</p> : null}
      {!enabled ? (
        <button type="button" onClick={() => setEnabled(true)} className="underline underline-offset-2">
          Compare cost-first and tail-cost rules
        </button>
      ) : null}
    </section>
  );
}
