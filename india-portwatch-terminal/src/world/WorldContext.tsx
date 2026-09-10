/**
 * The world's shared state, and the only place a spatial command lands.
 *
 * Global Eye used to own selection, lens and projection as local component
 * state, which was fine while the screen was the only thing that changed them.
 * The Copilot changes that: an answer to "why is JNPA at risk?" has to select an
 * event, move the camera, switch the lens and open the evidence, and a component
 * that owns its own state privately cannot be driven from outside.
 *
 * So the world state lives here and `dispatch` is the single door into it.
 *
 * The safety rule is enforced at that door rather than trusted to callers.
 * A command classified UI changes what the operator is looking at and runs
 * immediately. A SIMULATION command runs only inside an explicit simulation
 * context. An OPERATIONAL command never runs here at all -- it goes through the
 * approval boundary that already exists, and this dispatcher refuses it rather
 * than quietly doing nothing, so a caller cannot mistake silence for success.
 */

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";

/** The six interpretations of one world. Not routes. */
export const LENSES = [
  "OPERATIONS",
  "INTELLIGENCE",
  "WEATHER",
  "SECURITY",
  "CARGO",
  "FINANCIAL",
] as const;
export type Lens = (typeof LENSES)[number];

export const PROJECTION_OFFSETS = [0, 3, 6, 12, 24, 48, 72] as const;

export type SpatialSafety = "UI" | "SIMULATION" | "OPERATIONAL";

export interface SpatialCommand {
  kind: string;
  subject?: string | null;
  evidenceTool?: string;
  reason?: string;
  params?: Record<string, unknown>;
  safety?: SpatialSafety;
  autoExecutable?: boolean;
}

/** What a dispatch actually did, so a caller can report rather than assume. */
export interface DispatchOutcome {
  kind: string;
  applied: boolean;
  reason: string;
}

export interface WorldState {
  lens: Lens;
  eventId: string | null;
  vesselId: string | null;
  portCode: string | null;
  chokepoint: string | null;
  projectionHours: number;
  /** Attention queue narrowed to these subject ids. Empty means unfiltered. */
  attentionSubjects: string[];
  evidenceFor: string | null;
  /** Bumped to ask the map to fly somewhere without owning the camera. */
  focusToken: number;
  focusTarget: { lon: number; lat: number; zoom?: number } | null;
  /** Set while a simulation context is open; SIMULATION commands need it. */
  simulationOpen: boolean;
}

const INITIAL: WorldState = {
  lens: "OPERATIONS",
  eventId: null,
  vesselId: null,
  portCode: null,
  chokepoint: null,
  projectionHours: 0,
  attentionSubjects: [],
  evidenceFor: null,
  focusToken: 0,
  focusTarget: null,
  simulationOpen: false,
};

interface WorldApi extends WorldState {
  setLens: (lens: Lens) => void;
  selectEvent: (eventId: string | null) => void;
  selectVessel: (vesselId: string | null) => void;
  selectPort: (portCode: string | null) => void;
  setProjectionHours: (hours: number) => void;
  setAttentionSubjects: (ids: string[]) => void;
  openEvidence: (attentionId: string | null) => void;
  flyTo: (lon: number, lat: number, zoom?: number) => void;
  setSimulationOpen: (open: boolean) => void;
  clearContext: () => void;
  /** Run one command. Returns what happened, including refusals. */
  dispatch: (command: SpatialCommand) => DispatchOutcome;
  /** Run a batch, in order. */
  dispatchAll: (commands: SpatialCommand[]) => DispatchOutcome[];
  /** The last batch's outcomes, for the command bar to report. */
  lastOutcomes: DispatchOutcome[];
}

const WorldContext = createContext<WorldApi | null>(null);

export function WorldProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<WorldState>(INITIAL);
  const [lastOutcomes, setLastOutcomes] = useState<DispatchOutcome[]>([]);
  // Read inside dispatch without making dispatch depend on every change, so a
  // batch sees the world its predecessors left rather than a stale snapshot.
  const latest = useRef(state);
  latest.current = state;

  const patch = useCallback((next: Partial<WorldState>) => {
    setState((current) => {
      const merged = { ...current, ...next };
      latest.current = merged;
      return merged;
    });
  }, []);

  const setLens = useCallback((lens: Lens) => patch({ lens }), [patch]);
  const selectEvent = useCallback(
    (eventId: string | null) => patch({ eventId }),
    [patch],
  );
  const selectVessel = useCallback(
    (vesselId: string | null) => patch({ vesselId }),
    [patch],
  );
  const selectPort = useCallback(
    (portCode: string | null) => patch({ portCode }),
    [patch],
  );
  const setProjectionHours = useCallback(
    (projectionHours: number) => patch({ projectionHours }),
    [patch],
  );
  const setAttentionSubjects = useCallback(
    (attentionSubjects: string[]) => patch({ attentionSubjects }),
    [patch],
  );
  const openEvidence = useCallback(
    (evidenceFor: string | null) => patch({ evidenceFor }),
    [patch],
  );
  const setSimulationOpen = useCallback(
    (simulationOpen: boolean) => patch({ simulationOpen }),
    [patch],
  );
  const flyTo = useCallback(
    (lon: number, lat: number, zoom?: number) =>
      patch({
        focusTarget: { lon, lat, zoom },
        focusToken: latest.current.focusToken + 1,
      }),
    [patch],
  );
  const clearContext = useCallback(
    () =>
      patch({
        eventId: null,
        vesselId: null,
        portCode: null,
        chokepoint: null,
        attentionSubjects: [],
        evidenceFor: null,
      }),
    [patch],
  );

  /**
   * Execute one command, or say why it was not executed.
   *
   * Refusals are returned rather than thrown or swallowed. A Copilot that
   * silently dropped a command it could not run would leave an operator
   * believing the world had moved when it had not, which is worse than an
   * answer that says "this needs approval".
   */
  const dispatch = useCallback(
    (command: SpatialCommand): DispatchOutcome => {
      const refuse = (reason: string): DispatchOutcome => ({
        kind: command.kind,
        applied: false,
        reason,
      });
      const applied = (reason: string): DispatchOutcome => ({
        kind: command.kind,
        applied: true,
        reason,
      });

      const safety = command.safety ?? "UI";
      if (safety === "OPERATIONAL") {
        return refuse(
          "operational actions are not executed from an answer; they go " +
            "through the advisory approval boundary",
        );
      }
      if (safety === "SIMULATION" && !latest.current.simulationOpen) {
        return refuse(
          "simulation commands run only inside an open simulation context",
        );
      }

      const subject = command.subject ?? null;
      switch (command.kind) {
        case "FOCUS_EVENT":
          if (!subject) return refuse("no event named");
          patch({ eventId: subject, evidenceFor: null });
          return applied(`focused event ${subject}`);

        case "SHOW_CASCADE":
          if (!subject) return refuse("no event named");
          patch({ eventId: subject });
          return applied(`drawing the cascade for ${subject}`);

        case "FOCUS_VESSEL":
          if (!subject) return refuse("no vessel named");
          patch({ vesselId: subject, attentionSubjects: [subject] });
          return applied(`focused vessel ${subject}`);

        case "FOCUS_PORT":
          if (!subject) return refuse("no port named");
          patch({ portCode: subject, attentionSubjects: [subject] });
          return applied(`focused port ${subject}`);

        case "FOCUS_CHOKEPOINT":
          if (!subject) return refuse("no chokepoint named");
          patch({ chokepoint: subject, attentionSubjects: [subject] });
          return applied(`focused ${subject}`);

        case "SHOW_ROUTE":
          if (!subject) return refuse("no vessel named");
          patch({ vesselId: subject });
          return applied(`showing the passage for ${subject}`);

        case "SET_TIME": {
          const hours = Number(command.params?.hours ?? subject ?? 0);
          if (!Number.isFinite(hours)) return refuse("no readable horizon");
          // Snap to an offered horizon: the graph is queried at these, and a
          // request for +7h would otherwise silently become a different
          // question from the one the controls can express.
          const nearest = PROJECTION_OFFSETS.reduce((best, offset) =>
            Math.abs(offset - hours) < Math.abs(best - hours) ? offset : best,
          );
          patch({ projectionHours: nearest });
          return applied(
            nearest === 0 ? "moved the world to now" : `projected to +${nearest}h`,
          );
        }

        case "SET_LENS": {
          const lens = String(subject ?? "").toUpperCase() as Lens;
          if (!LENSES.includes(lens)) return refuse(`${subject} is not a lens`);
          patch({ lens });
          return applied(`${lens.toLowerCase()} lens`);
        }

        case "SHOW_ATTENTION":
          patch({
            attentionSubjects: subject ? [subject] : [],
            evidenceFor: null,
          });
          return applied("raised the action queue");

        case "CLEAR_CONTEXT":
          clearContext();
          return applied("cleared the selection");

        case "COMPARE_SCENARIOS":
          patch({ simulationOpen: true });
          return applied("opened scenario comparison");

        default:
          return refuse(`${command.kind} is not a command this world runs`);
      }
    },
    [clearContext, patch],
  );

  const dispatchAll = useCallback(
    (commands: SpatialCommand[]) => {
      const outcomes = commands.map((command) => dispatch(command));
      setLastOutcomes(outcomes);
      return outcomes;
    },
    [dispatch],
  );

  const value = useMemo<WorldApi>(
    () => ({
      ...state,
      setLens,
      selectEvent,
      selectVessel,
      selectPort,
      setProjectionHours,
      setAttentionSubjects,
      openEvidence,
      flyTo,
      setSimulationOpen,
      clearContext,
      dispatch,
      dispatchAll,
      lastOutcomes,
    }),
    [
      state, setLens, selectEvent, selectVessel, selectPort, setProjectionHours,
      setAttentionSubjects, openEvidence, flyTo, setSimulationOpen,
      clearContext, dispatch, dispatchAll, lastOutcomes,
    ],
  );

  /**
   * The dispatcher, exposed for the browser suite.
   *
   * The same seam `MaritimeMap.publish()` uses for its GL sources: a refusal
   * has no DOM of its own, and a test that clicked through the UI could only
   * ever exercise the commands the UI happens to offer. What has to be
   * asserted is that an OPERATIONAL command is refused *whatever* asks for it.
   */
  useEffect(() => {
    if (typeof window === "undefined") return;
    (window as unknown as { __portwatchWorld?: unknown }).__portwatchWorld = {
      dispatch,
      dispatchAll,
      state: latest.current,
    };
  }, [dispatch, dispatchAll, state]);

  return <WorldContext.Provider value={value}>{children}</WorldContext.Provider>;
}

export function useWorld(): WorldApi {
  const context = useContext(WorldContext);
  if (!context) {
    throw new Error("useWorld must be used inside a WorldProvider");
  }
  return context;
}
