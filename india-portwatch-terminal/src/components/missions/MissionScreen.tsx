/**
 * Historical missions: replay a sourced incident with only what was known
 * then, decide, reveal, and watch PortWatch score itself.
 *
 * The screen is the loop the product claims to close. The left rail is the
 * chronology as it stood at the replay clock -- every line cites its source,
 * and the hidden lines are counted but not shown. The chart draws the
 * decision the engine makes from that world. The reveal opens the future,
 * and the scorecard beside the map says what PortWatch knew, predicted and
 * recommended, what the operator chose, what happened, how wrong the
 * forecast was, what the chosen option cost against the realised best, and
 * what the engine learned. Nothing on this screen is computed on the client.
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";

import { useAuth } from "@/auth/AuthProvider";
import { ContextMap } from "@/components/command/ContextMap";
import { EmptyNote, FloatPanel } from "@/components/command/panels";
import { useWorkspaceMap } from "@/components/command/useWorkspaceMap";
import { DecisionPanel } from "@/components/decision/DecisionPanel";
import { Pill } from "@/components/kit/primitives";
import { ScreenFallback } from "@/components/kit/states";
import { decisionBounds, optionStyles } from "@/lib/maritime/decision-layers";
import {
  missionBounds,
  missionLabels,
  missionLayers,
} from "@/lib/maritime/mission-layers";
import { cn } from "@/lib/utils";
import {
  chooseOnMission,
  decideOnMission,
  openMissionReplay,
  revealMission,
  seekMissionReplay,
  useMission,
  useMissions,
} from "@/services/decisions";
import type {
  DecisionProblem,
  MissionReplayState,
  MissionReveal,
  MissionScorecard,
} from "@/types/decisions";

const SEEK_OFFSETS = [0, 24, 48, 72, 96] as const;

/** Room for the chronology on the left and the decision on the right. */
const MISSION_PADDING = { top: 48, bottom: 56, left: 372, right: 412 };

export function MissionScreen({ title }: { title: string }) {
  const { identityHeaders } = useAuth();
  const client = useQueryClient();
  const missions = useMissions();
  const missionId = missions.data?.missions[0]?.missionId ?? null;
  const mission = useMission(missionId);
  // The live world stays off this chart: its ports, weather, storms and
  // traffic are today's, and the clock is not. Only the mission is drawn.
  const workspace = useWorkspaceMap({
    layerOverrides: {
      cascade: true,
      traffic: false,
      ghosts: false,
      observed: false,
      tracks: false,
      vectors: false,
      weather: false,
      storms: false,
      seastate: false,
      ports: false,
      routes: false,
      zones: false,
      events: false,
      chokepoints: true,
    },
  });

  const [problem, setProblem] = useState<DecisionProblem | null>(null);
  const [optionId, setOptionId] = useState<string | null>(null);
  const [compare, setCompare] = useState(true);
  const [reveal, setReveal] = useState<MissionReveal | null>(null);

  const settle = useCallback(
    (state: MissionReplayState) => {
      client.setQueryData(["mission", state.missionId], state);
    },
    [client],
  );

  const open = useMutation({
    mutationFn: (offsetHours: number) =>
      openMissionReplay(missionId as string, { offsetHours }),
    onSuccess: (state) => {
      settle(state);
      setProblem(null);
      setOptionId(null);
      setReveal(null);
    },
  });
  const seek = useMutation({
    mutationFn: (offsetHours: number) =>
      seekMissionReplay(missionId as string, { offsetHours }),
    onSuccess: (state) => {
      settle(state);
      setProblem(null);
      setOptionId(null);
    },
  });
  const decide = useMutation({
    mutationFn: (vesselId: string) =>
      decideOnMission(missionId as string, vesselId, identityHeaders),
    onSuccess: (result) => {
      setProblem(result);
      setOptionId(result.recommendation?.optionId ?? result.baselineOptionId);
      client.setQueryData(["decision", result.decisionId], result);
      void client.invalidateQueries({ queryKey: ["mission", missionId] });
    },
  });
  const choose = useMutation({
    mutationFn: (args: { vesselId: string; optionId: string }) =>
      chooseOnMission(missionId as string, args, identityHeaders),
    onSuccess: () =>
      void client.invalidateQueries({ queryKey: ["mission", missionId] }),
  });
  const doReveal = useMutation({
    mutationFn: () => revealMission(missionId as string, identityHeaders),
    onSuccess: (result) => {
      setReveal(result);
      settle(result.mission);
    },
  });

  // A fresh replay whenever the screen opens: a mission is a run, not a page.
  useEffect(() => {
    if (missionId && !mission.data?.replayId) open.mutate(0);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [missionId]);

  const layers = useMemo(
    () => missionLayers(mission.data, problem, optionId, compare),
    [mission.data, problem, optionId, compare],
  );
  const labels = useMemo(
    () => missionLabels(mission.data, problem, optionId, compare),
    [mission.data, problem, optionId, compare],
  );
  const frame = useMemo(() => missionBounds(mission.data), [mission.data]);
  const frameKey = frame ? frame.flat().join(",") : "";
  useEffect(() => {
    const box = decisionBounds(problem, optionId, compare) ?? frame;
    // Room on the right only while the decision panel is there to need it.
    if (box)
      workspace.fitBounds(box, {
        ...MISSION_PADDING,
        right: problem ? MISSION_PADDING.right : 48,
      });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [problem?.decisionId, compare, frameKey]);

  const chosen = mission.data?.choices?.[problem?.subject.id ?? ""] ?? null;
  const card: MissionScorecard | null =
    reveal && problem ? (reveal.scorecards[problem.subject.id] ?? null) : null;
  const revealed = Boolean(mission.data?.revealed);

  if (missions.isLoading || mission.isLoading || missions.isError) {
    return (
      <ScreenFallback
        title={title}
        context={
          <span>Replay a sourced incident with only what was known then</span>
        }
        isLoading={missions.isLoading || mission.isLoading}
        error={missions.error}
        retry={() => void missions.refetch()}
        label="Opening the mission"
      />
    );
  }
  const state = mission.data;

  return (
    <div className="absolute inset-0">
      <h1 className="sr-only">{title}</h1>
      <ContextMap
        workspace={workspace}
        extraData={{ cascade: layers.cascade }}
        labels={labels}
        showTraffic={false}
        showLegend={false}
        view={{ center: [40, 14], zoom: 3.1 }}
        overlay={
          <>
            {/* ---------------------------------------------- chronology -- */}
            <div className="pointer-events-none absolute bottom-2.5 left-2.5 top-2.5 z-20 flex w-[330px] flex-col gap-2">
              <FloatPanel
                title="Historical mission"
                note={
                  state ? (
                    <Pill tone={revealed ? "ok" : "info"}>
                      {revealed ? "Revealed" : "Replay"}
                    </Pill>
                  ) : null
                }
                className="pointer-events-auto min-h-0 flex-1"
                testId="mission-panel"
                footer={state?.disclaimer}
              >
                {state ? (
                  <MissionRail
                    state={state}
                    onSeek={(hours) => seek.mutate(hours)}
                    onRestart={() => open.mutate(0)}
                    onDecide={(vesselId) => decide.mutate(vesselId)}
                    deciding={decide.isPending}
                    decidedFor={problem?.subject.id ?? null}
                    onReveal={() => doReveal.mutate()}
                    revealing={doReveal.isPending}
                    canReveal={
                      Boolean(
                        state.choices && Object.keys(state.choices).length,
                      ) && !revealed
                    }
                    error={
                      (decide.error as Error | null)?.message ??
                      (doReveal.error as Error | null)?.message ??
                      null
                    }
                  />
                ) : (
                  <EmptyNote>No mission is loaded.</EmptyNote>
                )}
              </FloatPanel>
            </div>

            {/* -------------------------------------------------- decision -- */}
            {problem ? (
              <div className="pointer-events-none absolute bottom-2.5 right-2.5 top-2.5 z-30 flex w-[372px] flex-col gap-2">
                <FloatPanel
                  title={card ? "Scorecard" : "Decision at the replay clock"}
                  note={
                    <span className="num">
                      {problem.decisionId.slice(0, 28)}
                    </span>
                  }
                  className="pointer-events-auto min-h-0 flex-1"
                  scroll={false}
                  testId={card ? "mission-scorecard" : "mission-decision"}
                  onClose={() => setProblem(null)}
                >
                  {card ? (
                    <Scorecard card={card} problem={problem} />
                  ) : (
                    <div className="flex min-h-0 flex-1 flex-col">
                      <DecisionPanel
                        problem={problem}
                        selectedOptionId={optionId}
                        compare={compare}
                        onSelectOption={setOptionId}
                        onToggleCompare={setCompare}
                        compact
                      />
                      <div className="flex shrink-0 items-center gap-2 border-t border-[var(--line)] px-2 py-1.5">
                        <button
                          type="button"
                          data-testid="mission-choose"
                          disabled={!optionId || choose.isPending || revealed}
                          onClick={() =>
                            optionId &&
                            choose.mutate({
                              vesselId: problem.subject.id,
                              optionId,
                            })
                          }
                          className="rounded bg-[var(--accent)] px-2 py-1 text-[10px] font-medium text-[var(--surface)] disabled:opacity-50"
                        >
                          {chosen ? `Chosen: ${chosen}` : "Choose this option"}
                        </button>
                        <span className="text-[9px] text-[var(--text-3)]">
                          {chosen
                            ? "Recorded before the reveal."
                            : "Your choice is recorded before the future is opened."}
                        </span>
                      </div>
                    </div>
                  )}
                </FloatPanel>
              </div>
            ) : null}
          </>
        }
      />
    </div>
  );
}

/* ------------------------------------------------------------------ rail -- */

function MissionRail({
  state,
  onSeek,
  onRestart,
  onDecide,
  deciding,
  decidedFor,
  onReveal,
  revealing,
  canReveal,
  error,
}: {
  state: MissionReplayState;
  onSeek: (hours: number) => void;
  onRestart: () => void;
  onDecide: (vesselId: string) => void;
  deciding: boolean;
  decidedFor: string | null;
  onReveal: () => void;
  revealing: boolean;
  canReveal: boolean;
  error: string | null;
}) {
  const elapsed = state.elapsedHours ?? 0;
  const sources = new Map(state.sources.map((s) => [s.sourceId, s]));
  return (
    <div className="flex flex-col">
      <div className="border-b border-[var(--line)] px-2 py-1.5">
        <p className="text-[11px] font-medium text-[var(--text)]">
          {state.name}
        </p>
        <p className="mt-0.5 text-[9.5px] leading-snug text-[var(--text-2)]">
          {state.description}
        </p>
        <div className="mt-1.5 flex items-center gap-1">
          <span className="text-[9px] uppercase tracking-wide text-[var(--text-3)]">
            Clock
          </span>
          <span
            className="num text-[10px] text-[var(--text)]"
            data-testid="mission-clock"
          >
            {state.clock.slice(0, 16).replace("T", " ")}Z
          </span>
          <span className="num ml-auto text-[9px] text-[var(--text-3)]">
            T0 +{elapsed.toFixed(0)}h
          </span>
        </div>
        <div className="mt-1 flex items-center gap-0.5">
          {SEEK_OFFSETS.map((offset) => (
            <button
              key={offset}
              type="button"
              data-testid="mission-seek"
              data-offset={offset}
              disabled={state.revealed}
              onClick={() => onSeek(offset)}
              className={cn(
                "num rounded px-1.5 py-0.5 text-[9.5px] disabled:opacity-40",
                Math.round(elapsed) === offset
                  ? "bg-[var(--accent)] text-[var(--surface)]"
                  : "text-[var(--text-2)] hover:bg-[var(--surface-2)]",
              )}
            >
              +{offset}h
            </button>
          ))}
          <button
            type="button"
            onClick={onRestart}
            data-testid="mission-restart"
            className="ml-auto rounded px-1.5 py-0.5 text-[9.5px] text-[var(--text-3)] hover:bg-[var(--surface-2)]"
          >
            restart
          </button>
        </div>
      </div>

      <div className="border-b border-[var(--line)] px-2 py-1.5">
        <div className="flex items-center gap-1.5">
          <span className="text-[9px] uppercase tracking-wide text-[var(--text-3)]">
            Known at the clock
          </span>
          <span
            className="num ml-auto text-[9px] text-[var(--text-3)]"
            data-testid="mission-hidden-count"
          >
            {state.hiddenCount} hidden until reveal
          </span>
        </div>
        <ol className="mt-1 flex flex-col gap-1">
          {state.visible.map((observation, index) => (
            <li
              key={`${observation.observedAt}-${index}`}
              data-testid="mission-observation"
              className="flex flex-col"
            >
              <span className="num text-[9px] text-[var(--text-3)]">
                {observation.observedAt.slice(5, 16).replace("T", " ")}Z ·{" "}
                {observation.kind}
                {observation.timeUnstated ? " · time not stated by source" : ""}
              </span>
              <span className="text-[10px] leading-snug text-[var(--text)]">
                {observation.text}
              </span>
              <a
                href={sources.get(observation.sourceId)?.url}
                target="_blank"
                rel="noreferrer"
                className="truncate text-[8.5px] text-[var(--info)] hover:underline"
              >
                {sources.get(observation.sourceId)?.name ??
                  observation.sourceId}
              </a>
            </li>
          ))}
        </ol>
        {state.hidden?.length ? (
          <>
            <p className="mt-2 text-[9px] uppercase tracking-wide text-[var(--ok)]">
              Revealed
            </p>
            <ol className="mt-1 flex flex-col gap-1">
              {state.hidden.map((observation, index) => (
                <li
                  key={`${observation.observedAt}-${index}`}
                  data-testid="mission-revealed"
                  className="flex flex-col"
                >
                  <span className="num text-[9px] text-[var(--text-3)]">
                    {observation.observedAt.slice(5, 16).replace("T", " ")}Z ·{" "}
                    {observation.kind}
                  </span>
                  <span className="text-[10px] leading-snug text-[var(--text-2)]">
                    {observation.text}
                  </span>
                </li>
              ))}
            </ol>
          </>
        ) : null}
      </div>

      <div className="border-b border-[var(--line)] px-2 py-1.5">
        <span className="text-[9px] uppercase tracking-wide text-[var(--text-3)]">
          Illustrative hulls
        </span>
        {state.fleet.map((vessel) => {
          const decided = state.decisions?.[vessel.vesselId];
          const chosen = state.choices?.[vessel.vesselId];
          return (
            <div
              key={vessel.vesselId}
              data-testid="mission-vessel"
              className="mt-1 flex items-center gap-1.5"
            >
              <span className="min-w-0 flex-1">
                <span className="block truncate text-[10.5px] text-[var(--text)]">
                  {vessel.name}
                </span>
                <span className="num block text-[8.5px] text-[var(--text-3)]">
                  {vessel.laneCode} → {vessel.destinationPort} ·{" "}
                  {Object.entries(vessel.hoursToChokepointAtStart)
                    .map(([code, h]) => `${code} ${h >= 0 ? "+" : ""}${h}h`)
                    .join(", ")}
                  {chosen ? ` · chose ${chosen}` : decided ? " · decided" : ""}
                </span>
              </span>
              <button
                type="button"
                data-testid="mission-decide"
                data-vessel={vessel.vesselId}
                disabled={deciding || state.revealed}
                onClick={() => onDecide(vessel.vesselId)}
                className={cn(
                  "rounded border border-[var(--line-strong)] px-1.5 py-0.5 text-[9px] uppercase tracking-wide",
                  decidedFor === vessel.vesselId
                    ? "bg-[var(--accent)] text-[var(--surface)]"
                    : "text-[var(--text)] hover:bg-[var(--surface-2)]",
                  "disabled:opacity-50",
                )}
              >
                {deciding && decidedFor !== vessel.vesselId ? "…" : "decide"}
              </button>
            </div>
          );
        })}
        <p className="mt-1 text-[8.5px] leading-snug text-[var(--text-3)]">
          {state.fleet[0]?.note}
        </p>
      </div>

      <div className="px-2 py-1.5">
        <button
          type="button"
          data-testid="mission-reveal"
          disabled={!canReveal || revealing}
          onClick={onReveal}
          className="w-full rounded bg-[var(--crit)] px-2 py-1.5 text-[10.5px] font-semibold uppercase tracking-wide text-[var(--surface)] disabled:opacity-40"
        >
          {state.revealed
            ? "Outcome revealed"
            : revealing
              ? "Revealing…"
              : "Reveal outcome"}
        </button>
        <p className="mt-1 text-[9px] leading-snug text-[var(--text-3)]">
          {state.revealed
            ? "The hidden observations and the outcome are open; every decision made on this replay has been scored."
            : "Choose an option for at least one hull first. The reveal is irreversible for this replay."}
        </p>
        {error ? (
          <p className="mt-1 text-[9.5px] text-[var(--crit)]">{error}</p>
        ) : null}
      </div>
    </div>
  );
}

/* ------------------------------------------------------------- scorecard -- */

function Scorecard({
  card,
  problem,
}: {
  card: MissionScorecard;
  problem: DecisionProblem;
}) {
  const styles = optionStyles(problem);
  const label = (id: string | null) =>
    id ? (problem.options.find((o) => o.optionId === id)?.label ?? id) : "—";
  const realised = Object.entries(card.realised);
  const maxHours = Math.max(
    1,
    ...realised.map(([, r]) => Math.max(r.hours, r.predicted ?? 0)),
  );
  return (
    <div className="flex min-h-0 flex-1 flex-col overflow-y-auto">
      <Section title="What PortWatch knew">
        <p className="text-[10px] leading-snug text-[var(--text)]">
          {String(card.knew.status ?? "")} · severity{" "}
          {String(card.knew.severity ?? "—")} · confidence{" "}
          {String(card.knew.confidence ?? "—")} · claim horizon{" "}
          {card.forecastError.claimHorizonHours} h ·{" "}
          {String(card.knew.visibleObservations)} observations visible
        </p>
      </Section>
      <Section title="What it predicted">
        <p className="text-[10px] leading-snug text-[var(--text)]">
          Baseline exposure {card.predicted.baselineRisk ?? "—"}; expected shift{" "}
          {card.predicted.baselineExpectedShiftHours ?? "—"} h if unchanged.
        </p>
      </Section>
      <Section title="What it recommended">
        <p className="text-[10px] leading-snug text-[var(--text)]">
          {label(card.recommended.optionId)}{" "}
          <Pill tone={card.recommended.critic === "REJECT" ? "crit" : "ok"}>
            {card.recommended.critic ?? "—"}
          </Pill>
        </p>
      </Section>
      <Section title="What the operator selected">
        <p
          className="text-[10px] text-[var(--text)]"
          data-testid="scorecard-selected"
        >
          {label(card.selected)}
        </p>
      </Section>
      <Section title="What happened">
        <p className="text-[10px] leading-snug text-[var(--text)]">
          {card.happened.summary}
        </p>
        <p className="num mt-0.5 text-[9px] text-[var(--text-3)]">
          reopened {card.happened.reopenedAt.slice(0, 16).replace("T", " ")}Z ·
          backlog cleared {card.happened.backlogClearedOn} · sources{" "}
          {card.happened.sources.join(", ")}
        </p>
      </Section>
      <Section title="Forecast error">
        <div className="num grid grid-cols-2 gap-x-3 gap-y-0.5 text-[10px]">
          <span className="text-[var(--text-3)]">claim horizon</span>
          <span>{card.forecastError.claimHorizonHours} h</span>
          <span className="text-[var(--text-3)]">blocked for</span>
          <span>{card.forecastError.blockedHours} h</span>
          <span className="text-[var(--text-3)]">persistence error</span>
          <span
            className={
              card.forecastError.persistenceErrorHours > 0
                ? "text-[var(--warn)]"
                : ""
            }
          >
            {card.forecastError.persistenceErrorHours > 0 ? "+" : ""}
            {card.forecastError.persistenceErrorHours} h
          </span>
          <span className="text-[var(--text-3)]">closed on arrival</span>
          <span>
            {card.forecastError.closedOnArrival == null
              ? "—"
              : card.forecastError.closedOnArrival
                ? "yes"
                : "no"}
          </span>
          <span className="text-[var(--text-3)]">Brier (baseline risk)</span>
          <span>{card.forecastError.brier ?? "—"}</span>
        </div>
      </Section>
      <Section title="Every option, realised">
        <ul className="flex flex-col gap-1">
          {realised.map(([id, row]) => {
            const style = styles.get(id);
            return (
              <li
                key={id}
                data-testid="scorecard-option"
                data-option={id}
                className="flex flex-col gap-[2px]"
              >
                <div className="flex items-center gap-1.5 text-[10px]">
                  <span
                    className="num font-semibold"
                    style={{ color: style?.colour }}
                  >
                    {style?.letter ?? "·"}
                  </span>
                  <span className="min-w-0 flex-1 truncate text-[var(--text)]">
                    {row.label}
                  </span>
                  {id === card.realisedBest ? (
                    <Pill tone="ok">best</Pill>
                  ) : null}
                  {id === card.selected ? (
                    <Pill tone="info">chosen</Pill>
                  ) : null}
                </div>
                <div className="flex items-center gap-1">
                  <span className="num w-14 text-right text-[9px] text-[var(--text-3)]">
                    pred {row.predicted ?? "—"}
                  </span>
                  <span
                    className="h-[5px] rounded-sm"
                    style={{
                      width: `${((row.predicted ?? 0) / maxHours) * 100}%`,
                      background: "var(--text-3)",
                      opacity: 0.5,
                    }}
                  />
                </div>
                <div className="flex items-center gap-1">
                  <span className="num w-14 text-right text-[9px] text-[var(--text-2)]">
                    real {row.hours}
                  </span>
                  <span
                    className="h-[5px] rounded-sm"
                    style={{
                      width: `${(row.hours / maxHours) * 100}%`,
                      background: style?.colour ?? "var(--text-2)",
                    }}
                  />
                </div>
                <p className="pl-1 text-[8.5px] leading-snug text-[var(--text-3)]">
                  {row.how}
                </p>
              </li>
            );
          })}
        </ul>
      </Section>
      <Section title="Decision regret">
        <p
          className="num text-[10px] text-[var(--text)]"
          data-testid="scorecard-regret"
        >
          {card.regretHours == null
            ? "not computable"
            : `${card.regretHours} h against the realised best (${label(card.realisedBest)})`}
          {card.rankingCorrect != null
            ? ` · ranking ${card.rankingCorrect ? "correct" : "incorrect"}`
            : ""}
          {card.wouldAnotherOptionHaveBeenBetter != null
            ? ` · another option better: ${card.wouldAnotherOptionHaveBeenBetter ? "yes" : "no"}`
            : ""}
        </p>
      </Section>
      <Section title="What PortWatch learned">
        <ul className="flex flex-col gap-0.5">
          {card.learned.map((line) => (
            <li
              key={line}
              className="text-[10px] leading-snug text-[var(--text)]"
            >
              · {line}
            </li>
          ))}
        </ul>
        <p className="mt-1 text-[8.5px] leading-snug text-[var(--text-3)]">
          Realised model: {card.realisedModel}
        </p>
      </Section>
    </div>
  );
}

function Section({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <div className="border-b border-[var(--line)] px-2 py-1.5 last:border-0">
      <p className="mb-0.5 text-[9px] uppercase tracking-wide text-[var(--text-3)]">
        {title}
      </p>
      {children}
    </div>
  );
}
