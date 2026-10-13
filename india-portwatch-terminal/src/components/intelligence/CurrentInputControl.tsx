import { useState } from "react";
import { WeatherVerificationPanel } from "./WeatherVerificationPanel";
import { createPortal } from "react-dom";
import { useMutation, useQuery } from "@tanstack/react-query";
import { useAuth } from "@/auth/AuthProvider";
import { useCompanyFleet } from "@/services/os-hooks";
import { useCreateDecision } from "@/services/decisions";
import { getJson, postJson } from "@/services/api";
import type { CurrentEnvironment } from "@/services/current-inputs";
import type { DecisionProblem } from "@/types/decisions";
import { Button } from "@/components/ui/button";
import { formatUtc, Pill } from "@/components/kit/primitives";

export function CurrentInputControl({
  onDecision,
}: {
  onDecision: (problem: DecisionProblem) => void;
}) {
  const { session, identityHeaders } = useAuth();
  const [open, setOpen] = useState(false);
  const [vesselId, setVesselId] = useState("PWD-001");
  const [arrival, setArrival] = useState("");
  const [gust, setGust] = useState(15);
  const [visibility, setVisibility] = useState(5000);
  const fleet = useCompanyFleet();
  const vessel = fleet.data?.vessels.find((v) => v.vessel_id === vesselId);
  const port = vessel?.destination_port ?? "INNSA";
  const inputs = useQuery({
    queryKey: ["current-environment", port],
    queryFn: ({ signal }) =>
      getJson<CurrentEnvironment>(
        `/intelligence/current?portCode=${port}`,
        identityHeaders,
        { signal, timeoutMs: 60000 },
      ),
    enabled: open,
    staleTime: 30000,
  });
  const create = useCreateDecision(identityHeaders);
  const saved = useQuery({
    queryKey: ["saved-weather-comparisons"],
    queryFn: () =>
      getJson<{ problems: DecisionProblem[] }>(
        "/decisions/problems?limit=50",
        identityHeaders,
      ),
    enabled: session?.mode === "demo" && open,
    refetchInterval: 10000,
  });
  const resume = useMutation({
    mutationFn: (id: string) =>
      getJson<DecisionProblem>(`/decisions/problems/${id}`, identityHeaders),
    onSuccess: (problem) => {
      onDecision(problem);
      setOpen(false);
    },
  });
  const refresh = useMutation({
    mutationFn: (id: string) =>
      postJson<DecisionProblem>(
        `/decisions/problems/${id}/refresh`,
        {},
        identityHeaders,
      ),
    onSuccess: (problem) => {
      onDecision(problem);
      setOpen(false);
    },
  });
  if (session?.mode !== "demo") return null;
  const earliest = Date.parse(vessel?.eta ?? "");
  const hours = (inputs.data?.hourly ?? []).filter(
    (r) =>
      Date.parse(r.validAt) >= earliest &&
      Date.parse(r.validAt) <= earliest + 72 * 3600000,
  );
  const selected = arrival || hours[0]?.validAt || "";
  const today = new Date().toISOString().slice(0, 10);
  const fiveDay = new Date(
    Date.UTC(
      new Date().getUTCFullYear(),
      new Date().getUTCMonth(),
      new Date().getUTCDate() + 5,
    ),
  )
    .toISOString()
    .slice(0, 10);
  return (
    <div className="absolute bottom-[207px] right-3 z-40 pointer-events-auto">
      <Button variant="outline" size="sm" onClick={() => setOpen(true)}>
        Current weather decision
      </Button>
      {open
        ? createPortal(
            <div
              role="dialog"
              aria-label="Current inputs for voyage planning"
              className="pointer-events-auto fixed inset-x-[4vw] top-[8vh] bottom-[8vh] z-[100] overflow-auto rounded border border-[var(--line-strong)] bg-[var(--panel)] p-3 text-xs shadow-2xl"
            >
              <div className="flex justify-between gap-3">
                <strong>Current inputs → original voyage decision</strong>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => setOpen(false)}
                >
                  Close current inputs
                </Button>
              </div>
              <p className="my-2">
                Public forecasts refreshed independently of IMF activity. Voyage
                and operating limits below are fictional demo assumptions; this
                does not establish an observed closure.
              </p>
              {(saved.data?.problems ?? [])
                .filter(
                  (p) =>
                    p.evidence.currentEnvironment &&
                    p.actor.role === "SHIPPING_COMPANY",
                )
                .map((p) => (
                  <div
                    key={p.decisionId}
                    className="my-2 flex flex-wrap items-center gap-2 border-b border-[var(--line)] pb-2"
                  >
                    <span>
                      Saved: {p.subject.label} · {p.workflow} ·{" "}
                      {formatUtc(p.createdAt)}
                    </span>
                    <Button
                      size="sm"
                      disabled={resume.isPending}
                      onClick={() => resume.mutate(p.decisionId)}
                    >
                      Resume saved comparison
                    </Button>
                    <Button
                      size="sm"
                      variant="outline"
                      disabled={refresh.isPending}
                      onClick={() => refresh.mutate(p.decisionId)}
                    >
                      Refresh to linked comparison
                    </Button>
                  </div>
                ))}
              <p>
                Refreshing uses current forecasts and keeps the previous
                comparison, approvals and advisories. The successor needs its
                own review and approval.
              </p>
              {resume.isError || refresh.isError ? (
                <p role="alert">
                  {resume.error?.message ?? refresh.error?.message}
                </p>
              ) : null}
              <div className="flex flex-wrap items-center gap-3">
                <label>
                  Voyage{" "}
                  <select
                    aria-label="Current input voyage"
                    className="bg-[var(--panel-2)]"
                    value={vesselId}
                    onChange={(e) => {
                      setVesselId(e.target.value);
                      setArrival("");
                    }}
                  >
                    {fleet.data?.vessels.map((v) => (
                      <option key={v.vessel_id} value={v.vessel_id}>
                        {v.name}
                      </option>
                    ))}
                  </select>
                </label>
                <span>
                  {port} · earliest declared ETA{" "}
                  {formatUtc(vessel?.eta ?? null)}
                </span>
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => void inputs.refetch()}
                >
                  Check current sources
                </Button>
              </div>
              {inputs.isPending ? (
                <p className="py-3">Retrieving current provider snapshots…</p>
              ) : inputs.isError ? (
                <p role="alert">{inputs.error.message}</p>
              ) : (
                <>
                  <div className="my-3 flex flex-wrap gap-3">
                    {Object.entries(inputs.data?.sources ?? {}).map(
                      ([kind, source]) => (
                        <div key={kind}>
                          <Pill
                            tone={source.status === "CURRENT" ? "ok" : "warn"}
                          >
                            {kind} {source.status}
                          </Pill>
                          <p>Available {formatUtc(source.availableAt)}</p>
                          <p>
                            Issue time{" "}
                            {source.issuedAt
                              ? formatUtc(source.issuedAt)
                              : "unavailable"}
                          </p>
                        </div>
                      ),
                    )}
                  </div>
                  <strong>
                    Five-day weather case: {today} → {fiveDay}
                  </strong>
                  <table className="my-2 w-full text-left">
                    <thead>
                      <tr>
                        <th>Valid day UTC</th>
                        <th>Gust max kn</th>
                        <th>Rain mm/day</th>
                        <th>Wave max m</th>
                        <th>Outcome</th>
                      </tr>
                    </thead>
                    <tbody>
                      {(inputs.data?.daily ?? [])
                        .filter((r) => r.date >= today && r.date <= fiveDay)
                        .map((r) => (
                          <tr
                            key={r.date}
                            className="border-t border-[var(--line)]"
                          >
                            <td>
                              {r.date}
                              {r.date === fiveDay ? " · five-day target" : ""}
                            </td>
                            <td>{r.wind_gust ?? "unavailable"}</td>
                            <td>{r.rainfall?.toFixed(2) ?? "unavailable"}</td>
                            <td>{r.wave_height ?? "unavailable"}</td>
                            <td>{r.matchStatus} · no forecast error yet</td>
                          </tr>
                        ))}
                    </tbody>
                  </table>
                  <p>
                    Original values retained. Correction is collecting; a new
                    forecast cannot verify an old one. The full archive remains
                    in Port Weather and Admin Learning.
                  </p>
                  <details className="my-2">
                    <summary>
                      Inspect original five-day forecast and learning
                    </summary>
                    <WeatherVerificationPanel key={port} portCode={port} />
                  </details>
                  <fieldset className="my-3 space-y-2 border border-[var(--line)] p-2">
                    <legend>Explicit demo approach assumptions</legend>
                    <label className="block">
                      Requested arrival UTC{" "}
                      <select
                        aria-label="Requested demo arrival UTC"
                        className="ml-2 bg-[var(--panel-2)]"
                        value={selected}
                        onChange={(e) => setArrival(e.target.value)}
                      >
                        {hours.map((r) => (
                          <option key={r.validAt} value={r.validAt}>
                            {formatUtc(r.validAt)} · gust{" "}
                            {r.wind_gusts_10m ?? "?"} kn · visibility{" "}
                            {r.visibility ?? "?"} m
                          </option>
                        ))}
                      </select>
                    </label>
                    <label className="block">
                      Assumed maximum approach gust (kn){" "}
                      <input
                        aria-label="Assumed maximum approach gust"
                        className="ml-2 w-20 bg-[var(--panel-2)]"
                        type="number"
                        min={3}
                        max={60}
                        value={gust}
                        onChange={(e) => setGust(Number(e.target.value))}
                      />
                    </label>
                    <label className="block">
                      Assumed minimum visibility (m){" "}
                      <input
                        aria-label="Assumed minimum approach visibility"
                        className="ml-2 w-20 bg-[var(--panel-2)]"
                        type="number"
                        min={0}
                        max={10000}
                        value={visibility}
                        onChange={(e) => setVisibility(Number(e.target.value))}
                      />
                    </label>
                    <p>
                      Two consecutive clear hourly forecasts define the assumed
                      approach window. Arrival cannot precede the voyage ETA.
                      Waves and hazards are context here; no whole-route safety
                      or berth allocation is inferred.
                    </p>
                    <Button
                      size="sm"
                      disabled={!selected || create.isPending}
                      onClick={() =>
                        create.mutate(
                          {
                            domain: "vessel",
                            vesselId,
                            currentArrival: {
                              plannedArrival: selected,
                              maxGustKn: gust,
                              minVisibilityM: visibility,
                            },
                          },
                          {
                            onSuccess: (problem) => {
                              setOpen(false);
                              onDecision(problem);
                            },
                          },
                        )
                      }
                    >
                      {create.isPending
                        ? "Comparing dated arrival windows…"
                        : "Compare in the original decision panel"}
                    </Button>
                    {create.isError ? (
                      <p role="alert">{create.error.message}</p>
                    ) : null}
                  </fieldset>
                  <strong>
                    GDACS regional hazards · publication and valid times
                    retained
                  </strong>
                  {inputs.data?.regionalHazards.length ? (
                    inputs.data.regionalHazards.slice(0, 6).map((r) => (
                      <p key={r.id} className="my-2">
                        <a href={r.source} target="_blank" rel="noreferrer">
                          {r.title}
                        </a>
                        <br />
                        Published {formatUtc(r.publishedAt)} · event through{" "}
                        {formatUtc(r.validThrough)}. {r.relationship}
                      </p>
                    ))
                  ) : (
                    <p className="my-2">
                      No regional hazards in this retrieved feed window. No
                      disruption inferred.
                    </p>
                  )}
                </>
              )}
            </div>,
            document.body,
          )
        : null}
    </div>
  );
}
