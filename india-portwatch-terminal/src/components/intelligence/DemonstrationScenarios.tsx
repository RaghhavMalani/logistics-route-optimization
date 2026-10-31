import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useAuth } from "@/auth/AuthProvider";
import { getJson, postJson } from "@/services/api";
import { Button } from "@/components/ui/button";
import type { DecisionProblem } from "@/types/decisions";

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
}: {
  onDecision?: (problem: DecisionProblem) => void;
}) {
  const { session, identityHeaders } = useAuth();
  const client = useQueryClient();
  const [id, setId] = useState("");
  const [ack, setAck] = useState(false);
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
  if (session?.mode !== "demo" || session.user.role !== "SHIPPING_COMPANY")
    return null;
  const chosen = q.data?.scenarios.find((s) => s.id === id);
  const result = select.data;
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
    <details
      className="mb-3 border border-[var(--line)] p-3"
      data-testid="demonstration-scenarios"
    >
      <summary className="cursor-pointer">
        Shipping demonstrations · explicit fictional inputs
      </summary>
      <p className="my-2">
        Presets begin a distinct owned demo call. Earlier evidence is retained.
        The ordinary engines calculate the results; no real closure, booking,
        observed outcome or safety benefit is asserted.
      </p>
      <label className="block">
        Scenario{" "}
        <select
          aria-label="Shipping demonstration scenario"
          className="block w-full bg-[var(--panel)] p-2"
          value={id}
          onChange={(e) => {
            setId(e.target.value);
            setAck(false);
            select.reset();
          }}
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
        <p className="my-2">
          {chosen.basis} {chosen.missingInputs}
        </p>
      )}
      <label className="my-2 flex items-start gap-2">
        <input
          type="checkbox"
          checked={ack}
          onChange={(e) => setAck(e.target.checked)}
        />
        I explicitly select fictional voyage/source assumptions in my isolated
        DEMO world. No source fixture enters real archives or scoring.
      </label>
      <Button
        size="sm"
        disabled={!id || !ack || select.isPending}
        onClick={() => select.mutate()}
      >
        Calculate selected demonstration
      </Button>
      {q.error && <p role="alert">{q.error.message}</p>}
      {select.error && <p role="alert">{select.error.message}</p>}
      {result && (
        <div className="mt-3 border-t border-[var(--line)] pt-2">
          <strong>
            {result.scenarioId} · {result.status}
          </strong>
          <p>{result.missingInputs}</p>
          {result.problem && (
            <>
              <p>{result.problem.headline}</p>
              <Button size="sm" onClick={() => onDecision?.(result.problem!)}>
                Inspect calculated comparison
              </Button>
            </>
          )}{" "}
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
    </details>
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
      className="pointer-events-none absolute left-3 top-12 z-20 max-w-[75%] rounded border border-amber-500/60 bg-[var(--panel)] px-2 py-1 text-[10px] text-amber-200"
      data-testid="illustrative-scenario-badge"
    >
      {q.data.selection.id} · ILLUSTRATIVE INPUTS · fictional call, not observed
      operations
    </div>
  );
}
