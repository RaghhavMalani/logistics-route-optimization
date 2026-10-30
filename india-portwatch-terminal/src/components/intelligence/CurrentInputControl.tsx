import { useEffect, useRef, useState } from "react";
import * as DialogPrimitive from "@radix-ui/react-dialog";
import { WeatherVerificationPanel } from "./WeatherVerificationPanel";
import { PassagePlanInputs } from "./PassagePlanInputs";
import { CargoCommitmentInputs } from "./CargoCommitmentInputs";
import {
  IndianSourceReviewChoices,
  type IndianReviewSelection,
  type FrozenIndianReview,
} from "./IndianSourceReviewChoices";
import { useMutation, useQuery } from "@tanstack/react-query";
import { useAuth } from "@/auth/AuthProvider";
import { useCompanyFleet } from "@/services/os-hooks";
import { useCreateDecision } from "@/services/decisions";
import { getJson, postJson } from "@/services/api";
import type {
  CurrentEnvironment,
  CargoCommitmentDeclaration,
  DeclaredPassagePlan,
} from "@/services/current-inputs";
import type { DecisionProblem } from "@/types/decisions";
import { Button } from "@/components/ui/button";
import { formatUtc, Pill } from "@/components/kit/primitives";
import {
  Dialog,
  DialogClose,
  DialogDescription,
  DialogOverlay,
  DialogPortal,
  DialogTitle,
} from "@/components/ui/dialog";

export function CurrentInputControl({
  onDecision,
  open: controlledOpen,
  onOpenChange,
  hideLauncher = false,
  initialVesselId,
  sourceComparison,
}: {
  onDecision: (problem: DecisionProblem) => void;
  open?: boolean;
  onOpenChange?: (open: boolean) => void;
  /** The workspace provides an in-flow action while an inspector occupies this control space. */
  hideLauncher?: boolean;
  /** Explicit queue/inspector target; no vessel-name or latest-record inference. */
  initialVesselId?: string | null;
  sourceComparison?: DecisionProblem | null;
}) {
  const { session, identityHeaders } = useAuth();
  const [localOpen, setLocalOpen] = useState(false);
  const open = controlledOpen ?? localOpen;
  const setOpen = onOpenChange ?? setLocalOpen;
  const initiatingControl = useRef<HTMLElement | null>(null);
  const [vesselId, setVesselId] = useState("PWD-001");
  const [arrival, setArrival] = useState("");
  const [gust, setGust] = useState(15);
  const [visibility, setVisibility] = useState(5000);
  const [passagePlan, setPassagePlan] = useState<DeclaredPassagePlan | null>(
    null,
  );
  const [cargoCommitment, setCargoCommitment] =
    useState<CargoCommitmentDeclaration | null>(null);
  const [sourceReviews, setSourceReviews] = useState<IndianReviewSelection[]>(
    [],
  );
  const preparedForOpen = useRef(false);
  useEffect(() => {
    if (!open) {
      preparedForOpen.current = false;
      return;
    }
    if (preparedForOpen.current) return;
    preparedForOpen.current = true;
    setSourceReviews([]);
    const target = initialVesselId ?? sourceComparison?.subject.id;
    if (target) setVesselId(target);
    const frozen = sourceComparison?.evidence.currentEnvironment as
      import("@/services/current-inputs").FrozenEnvironment | undefined;
    if (sourceComparison?.subject.id === target && frozen) {
      setArrival(frozen.plannedArrival);
      setGust(frozen.assumptions.maxGustKn);
      setVisibility(frozen.assumptions.minVisibilityM);
      setPassagePlan(frozen.passagePlan ?? null);
      setCargoCommitment(frozen.cargoCommitment ?? null);
    } else if (target) {
      setArrival("");
      setPassagePlan(null);
      setCargoCommitment(null);
    }
  }, [open, initialVesselId, sourceComparison]);
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
  const earliest = Date.parse(vessel?.eta ?? "");
  const hours = (inputs.data?.hourly ?? []).filter(
    (r) =>
      Date.parse(r.validAt) >= earliest &&
      Date.parse(r.validAt) <= earliest + 72 * 3600000,
  );
  const selected = arrival || hours[0]?.validAt || "";
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
  const predecessor =
    (sourceComparison?.subject.id === vesselId ? sourceComparison : null) ??
    [...(saved.data?.problems ?? [])]
      .filter(
        (p) =>
          p.evidence.currentEnvironment &&
          p.actor.role === "SHIPPING_COMPANY" &&
          p.subject.id === vesselId,
      )
      .sort((a, b) => Date.parse(b.createdAt) - Date.parse(a.createdAt))[0];
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
        (passagePlan || sourceReviews.length) &&
          saved.data?.problems.some(
            (p) => p.decisionId === id && p.subject.id === vesselId,
          )
          ? {
              currentArrival: {
                plannedArrival: selected,
                maxGustKn: gust,
                minVisibilityM: visibility,
                ...(passagePlan ? { passagePlan } : {}),
                ...(cargoCommitment ? { cargoCommitment } : {}),
                ...(sourceReviews.length ? { sourceReviews } : {}),
              },
            }
          : {},
        identityHeaders,
      ),
    onSuccess: (problem) => {
      onDecision(problem);
      setOpen(false);
    },
  });
  if (session?.mode !== "demo") return null;
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
    <Dialog open={open} onOpenChange={setOpen}>
      {!hideLauncher ? (
        <div className="pointer-events-auto absolute bottom-[207px] right-3 z-40">
          <Button
            variant="outline"
            size="sm"
            data-current-inputs-trigger
            onClick={() => setOpen(true)}
          >
            Current weather decision
          </Button>
        </div>
      ) : null}
      <DialogPortal>
        <DialogOverlay className="z-[100]" />
        <DialogPrimitive.Content
          className="pointer-events-auto fixed inset-x-[4vw] top-[8vh] bottom-[8vh] z-[101] flex min-w-0 flex-col rounded border border-[var(--line-strong)] bg-[var(--panel)] text-xs shadow-2xl"
          onOpenAutoFocus={() => {
            initiatingControl.current =
              document.activeElement instanceof HTMLElement
                ? document.activeElement
                : null;
          }}
          onCloseAutoFocus={(event) => {
            event.preventDefault();
            // Successful creation can replace the floating trigger with the
            // inspector's equivalent action. Cancel/Escape returns to the
            // exact initiating control whenever it still exists.
            const focusTarget = initiatingControl.current?.isConnected
              ? initiatingControl.current
              : document.querySelector<HTMLElement>(
                  "[data-current-inputs-trigger]",
                );
            focusTarget?.focus();
          }}
        >
          <div className="flex shrink-0 items-start justify-between gap-3 border-b border-[var(--line)] p-3">
            <DialogTitle className="min-w-0 text-sm">
              Current inputs for voyage planning
            </DialogTitle>
            <DialogClose asChild>
              <Button variant="ghost" size="sm" className="shrink-0">
                Close current inputs
              </Button>
            </DialogClose>
          </div>
          <div className="min-h-0 overflow-y-auto p-3 [overflow-wrap:anywhere]">
            <DialogDescription className="my-2 text-xs text-[var(--text-2)]">
              Public forecasts refreshed independently of IMF activity. Voyage
              and operating limits below are fictional demo assumptions; this
              does not establish an observed closure.
            </DialogDescription>
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
              comparison, approvals and advisories. The successor needs its own
              review and approval.
            </p>
            {predecessor ? (
              <p className="break-all">
                New comparison links to {predecessor.decisionId}. For an expired
                passage declaration, enter updated passage inputs before
                refreshing its saved comparison; position is never advanced
                automatically.
              </p>
            ) : null}
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
                  className="max-w-full bg-[var(--panel-2)]"
                  value={vesselId}
                  onChange={(e) => {
                    setVesselId(e.target.value);
                    setArrival("");
                    setPassagePlan(null);
                    setCargoCommitment(null);
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
                {port} · earliest declared ETA {formatUtc(vessel?.eta ?? null)}
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
                <div
                  role="region"
                  aria-label="Five-day forecast values"
                  tabIndex={0}
                  className="my-2 max-w-full overflow-x-auto"
                >
                  <table className="w-full text-left">
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
                </div>
                <p>
                  Original values retained. Correction is collecting; a new
                  forecast cannot verify an old one. The full archive remains in
                  Port Weather and Admin Learning.
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
                      className="max-w-full bg-[var(--panel-2)]"
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
                    Waves and hazards are context here; no whole-route safety or
                    berth allocation is inferred.
                  </p>
                  <PassagePlanInputs
                    value={passagePlan}
                    onChange={(next) => {
                      setPassagePlan(next);
                      if (!next) setCargoCommitment(null);
                    }}
                    voyageEta={vessel?.eta ?? null}
                    requestedArrival={selected}
                  />
                  <CargoCommitmentInputs
                    value={cargoCommitment}
                    onChange={setCargoCommitment}
                    voyageId={vesselId}
                    portCode={port}
                    requestedArrival={selected}
                    passageEnabled={passagePlan != null}
                  />
                  <IndianSourceReviewChoices
                    vesselId={vesselId}
                    previous={
                      (
                        predecessor?.evidence.currentEnvironment as
                          | { sourceReviewBindings?: FrozenIndianReview[] }
                          | undefined
                      )?.sourceReviewBindings
                    }
                    value={sourceReviews}
                    onChange={setSourceReviews}
                  />
                  <Button
                    size="sm"
                    disabled={!selected || create.isPending}
                    onClick={() =>
                      create.mutate(
                        {
                          domain: "vessel",
                          vesselId,
                          ...(predecessor
                            ? {
                                predecessorDecisionId: predecessor.decisionId,
                              }
                            : {}),
                          currentArrival: {
                            plannedArrival: selected,
                            maxGustKn: gust,
                            minVisibilityM: visibility,
                            ...(passagePlan ? { passagePlan } : {}),
                            ...(cargoCommitment ? { cargoCommitment } : {}),
                            ...(sourceReviews.length ? { sourceReviews } : {}),
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
                      ? "Comparing frozen voyage inputs…"
                      : "Compare in the original decision panel"}
                  </Button>
                  {create.isError ? (
                    <p role="alert">{create.error.message}</p>
                  ) : null}
                </fieldset>
                <strong>
                  GDACS regional hazards · publication and valid times retained
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
          </div>
        </DialogPrimitive.Content>
      </DialogPortal>
    </Dialog>
  );
}
