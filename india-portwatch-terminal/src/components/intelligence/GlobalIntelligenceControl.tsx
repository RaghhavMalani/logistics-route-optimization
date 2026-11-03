import {
  lazy,
  Suspense,
  useCallback,
  useEffect,
  useRef,
  useState,
} from "react";
import * as Dialog from "@radix-ui/react-dialog";
import { FocusScope } from "@radix-ui/react-focus-scope";
import { useQuery } from "@tanstack/react-query";
import { useAuth } from "@/auth/AuthProvider";
import { useIntelligence } from "@/services/intelligence";
import { getJson } from "@/services/api";
import { Button } from "@/components/ui/button";
import { Pill, formatUtc } from "@/components/kit/primitives";
import type { SpatialFeature } from "./ConnectedGodsEye";
import { ShippingIntelligencePanel } from "./ShippingIntelligencePanel";
import type { DecisionProblem } from "@/types/decisions";
const Globe = lazy(() => import("./ConnectedGodsEye"));
type Layer = "aircraft" | "satellites" | "cyclones" | "infrastructure";
interface LayerData {
  status: string;
  features: SpatialFeature[];
  records: Record<string, unknown>[];
  coverage: string;
  source: string;
  fetchedAt?: string;
  reason?: string;
}

export function GlobalIntelligenceControl({
  portCode,
  onPort,
  onEvent,
  onVessel,
  onDecision,
  hideLauncher = false,
}: {
  portCode: string | null;
  onPort: (code: string) => void;
  onEvent: (id: string) => void;
  onVessel: (id: string) => void;
  onDecision?: (problem: DecisionProblem) => void;
  hideLauncher?: boolean;
}) {
  const [open, setOpen] = useState(false);
  const [expanded, setExpanded] = useState(false);
  const [view, setView] = useState<
    "sources" | "learning" | "scenarios" | "globe"
  >("sources");
  const trigger = useRef<HTMLButtonElement>(null);
  const changeOpen = useCallback((next: boolean) => {
    setOpen(next);
    if (!next && window.location.hash.startsWith("#intelligence-review")) {
      window.history.replaceState(
        window.history.state,
        "",
        window.location.pathname + window.location.search,
      );
    }
  }, []);
  useEffect(() => {
    const readHash = () => {
      if (window.location.hash.startsWith("#intelligence-review")) {
        setView("sources");
        setOpen(true);
      }
    };
    readHash();
    const closeForAsset = () => changeOpen(false);
    window.addEventListener("portwatch:focus-constraint", closeForAsset);
    window.addEventListener("hashchange", readHash);
    return () => {
      window.removeEventListener("portwatch:focus-constraint", closeForAsset);
      window.removeEventListener("hashchange", readHash);
    };
  }, [changeOpen]);
  useEffect(() => {
    window.dispatchEvent(
      new CustomEvent("portwatch:inspector-visibility", { detail: open }),
    );
    return () => {
      window.dispatchEvent(
        new CustomEvent("portwatch:inspector-visibility", { detail: false }),
      );
    };
  }, [open]);
  return (
    <Dialog.Root open={open} onOpenChange={changeOpen} modal={false}>
      <div className="absolute bottom-[164px] right-3 z-30 pointer-events-auto">
        {!hideLauncher ? (
          <Button
            ref={trigger}
            data-global-intelligence-trigger
            size="sm"
            variant="outline"
            onClick={() => {
              setView("sources");
              setOpen(true);
            }}
          >
            Global intelligence
          </Button>
        ) : null}
        <Dialog.Portal>
          <Dialog.Content
            aria-modal={expanded || undefined}
            aria-label="Connected global intelligence"
            className="pw-dock pointer-events-auto"
            data-expanded={expanded}
            onInteractOutside={(event) => {
              if (!expanded) event.preventDefault();
            }}
            onCloseAutoFocus={(event) => {
              event.preventDefault();
              (
                trigger.current ??
                document.querySelector<HTMLElement>(
                  '[data-testid="decision-panel"]',
                )
              )?.focus();
            }}
          >
            <FocusScope
              asChild
              trapped={expanded}
              loop={expanded}
              onMountAutoFocus={(event) => event.preventDefault()}
            >
              <div className="flex min-h-0 flex-1 flex-col">
                <div className="pw-dock-header">
                  <div className="pw-dock-heading">
                    <Dialog.Title>Global intelligence</Dialog.Title>
                    <Dialog.Description>
                      Sources, assumptions and voyage review
                    </Dialog.Description>
                  </div>
                  <Button
                    size="sm"
                    variant="ghost"
                    onClick={() => {
                      if (expanded) setView("sources");
                      setExpanded(!expanded);
                    }}
                  >
                    {expanded ? "Dock to map" : "Expand evidence"}
                  </Button>
                  <Button
                    size="sm"
                    variant="ghost"
                    className="shrink-0"
                    onClick={() => changeOpen(false)}
                  >
                    Close intelligence
                  </Button>
                </div>
                <IntelligenceContents
                  view={view}
                  onViewChange={setView}
                  onFocus={() => setExpanded(true)}
                  onDecision={
                    onDecision
                      ? (problem) => {
                          onDecision(problem);
                          changeOpen(false);
                        }
                      : undefined
                  }
                  portCode={portCode ?? "INNSA"}
                  onPort={(c) => {
                    onPort(c);
                    changeOpen(false);
                  }}
                  onEvent={(e) => {
                    onEvent(e);
                    changeOpen(false);
                  }}
                  onVessel={(id) => {
                    onVessel(id);
                    changeOpen(false);
                  }}
                />
              </div>
            </FocusScope>
          </Dialog.Content>
        </Dialog.Portal>
      </div>
    </Dialog.Root>
  );
}

function IntelligenceContents({
  portCode,
  onPort,
  onEvent,
  onVessel,
  onDecision,
  view,
  onViewChange,
  onFocus,
}: {
  portCode: string;
  onPort: (code: string) => void;
  onEvent: (id: string) => void;
  onVessel: (id: string) => void;
  onDecision?: (problem: DecisionProblem) => void;
  view: "sources" | "learning" | "scenarios" | "globe";
  onViewChange: (view: "sources" | "learning" | "scenarios" | "globe") => void;
  onFocus: () => void;
}) {
  const { identityHeaders, session } = useAuth();
  const context = useIntelligence(portCode, identityHeaders);
  const [layer, setLayer] = useState<Layer>("cyclones");
  const [globe, setGlobe] = useState(false),
    [quake, setQuake] = useState(false),
    [cables, setCables] = useState(false);
  const q = useQuery({
    queryKey: ["intelligence-layer", layer, portCode],
    queryFn: ({ signal }) =>
      getJson<LayerData>(
        `/intelligence/layer/${layer}?portCode=${portCode}`,
        identityHeaders,
        { signal },
      ),
    staleTime: 60000,
    refetchInterval: 60000,
  });
  const hasContext = Boolean(context.data);
  useEffect(() => {
    if (view !== "globe") setGlobe(false);
  }, [view]);
  useEffect(() => {
    window.dispatchEvent(
      new CustomEvent("portwatch:intelligence-globe", {
        detail: globe && hasContext,
      }),
    );
    return () => {
      window.dispatchEvent(
        new CustomEvent("portwatch:intelligence-globe", { detail: false }),
      );
    };
  }, [globe, hasContext]);
  return (
    <div className="pw-dock-body">
      <div
        className="pw-section-tabs"
        role="tablist"
        aria-label="Intelligence view"
        onKeyDown={(event) => {
          if (event.key !== "ArrowLeft" && event.key !== "ArrowRight") return;
          const tabs = Array.from(
            event.currentTarget.querySelectorAll<HTMLButtonElement>('[role="tab"]'),
          );
          const index = tabs.findIndex((tab) => tab === event.target);
          if (index < 0) return;
          event.preventDefault();
          const direction = event.key === "ArrowRight" ? 1 : -1;
          const next = tabs[(index + direction + tabs.length) % tabs.length];
          next?.focus();
          next?.click();
        }}
      >
        {(
          [
            ["sources", "Sources"],
            ["learning", "Learning"],
            ["scenarios", "Scenarios"],
            ["globe", "Globe"],
          ] as const
        ).map(([id, label]) => (
          <button
            type="button"
            role="tab"
            key={id}
            aria-selected={view === id}
            onClick={() => onViewChange(id)}
          >
            {label}
          </button>
        ))}
      </div>
      <div hidden={view === "globe"}>
        <ShippingIntelligencePanel
          view={view === "globe" ? "sources" : view}
          onDecision={onDecision}
        />
      </div>
      <section
        hidden={view !== "globe"}
        aria-label="Globe and contextual layers"
      >
        <div className="flex flex-wrap gap-2 mb-3">
          {(
            ["cyclones", "aircraft", "satellites", "infrastructure"] as const
          ).map((l) => (
            <Button
              key={l}
              size="sm"
              variant={layer === l ? "default" : "outline"}
              onClick={() => setLayer(l)}
            >
              {l}
            </Button>
          ))}
          <Button
            size="sm"
            variant="outline"
            onClick={() => {
              setGlobe(!globe);
              if (!globe) onFocus();
            }}
          >
            {globe ? "Hide additional globe" : "Open God’s Eye globe"}
          </Button>
          <label className="text-xs self-center">
            <input
              type="checkbox"
              checked={quake}
              onChange={(e) => setQuake(e.target.checked)}
            />{" "}
            Earthquakes
          </label>
          {session?.mode === "demo" ? (
            <label className="text-xs self-center">
              <input
                type="checkbox"
                checked={cables}
                onChange={(e) => setCables(e.target.checked)}
              />{" "}
              Submarine cables · CC BY-NC-SA 3.0
            </label>
          ) : null}
        </div>
        <p className="text-[11px] mb-3 text-[var(--text-3)]">
          Ships, weather/ocean fields, news and consequence chains retain the
          original map and timeline. Aircraft and satellite context does not
          imply a shipping delay. Selecting a port or event returns to its
          existing inspector and decision workflow.
        </p>
        {globe && context.data ? (
          <Suspense
            fallback={<p className="text-xs">Loading additional globe…</p>}
          >
            <Globe
              context={context.data}
              features={q.data?.features ?? []}
              records={q.data?.records ?? []}
              onVessel={onVessel}
              onPort={onPort}
              onEvent={onEvent}
              quake={quake}
              cables={cables}
            />
          </Suspense>
        ) : null}
        {context.isError ? (
          <div className="space-y-2 text-xs">
            <p role="alert">
              Context unavailable. The original map remains available.{" "}
              {context.error.message}
            </p>
            <Button
              size="sm"
              variant="outline"
              onClick={() => void context.refetch()}
            >
              Retry connection
            </Button>
          </div>
        ) : null}
        <div className="grid gap-3 mt-3 lg:grid-cols-2">
          <section className="border border-[var(--line)] p-3">
            <h3 className="text-xs mb-2">
              {layer} · {portCode}{" "}
              <Pill>
                {q.data?.status ?? (q.isError ? "UNAVAILABLE" : "LOADING")}
              </Pill>
            </h3>
            <p className="text-[11px] text-[var(--text-3)]">
              {q.data?.coverage}
            </p>
            <p className="text-[10px]">
              Fetched {formatUtc(q.data?.fetchedAt ?? null)} ·{" "}
              {q.data?.features.length ?? 0} features ·{" "}
              {q.data?.records.length ?? 0} records
            </p>
            {q.data?.source ? (
              <a
                href={q.data.source}
                target="_blank"
                rel="noreferrer"
                className="text-[10px] underline"
              >
                Provider and coverage
              </a>
            ) : null}
            <div className="max-h-48 overflow-auto mt-2 text-[11px]">
              {q.data?.features.slice(0, 70).map((f) => (
                <p key={f.id}>
                  {f.name} · {f.lat.toFixed(2)}, {f.lon.toFixed(2)}
                  {f.ageSeconds != null
                    ? ` · ${Math.round(f.ageSeconds + Math.max(0, (Date.now() - Date.parse(q.data?.fetchedAt ?? new Date().toISOString())) / 1000))}s old`
                    : ""}
                </p>
              ))}
              {(q.data?.records ?? []).map((r) => (
                <p key={String(r.NORAD_CAT_ID)}>
                  {String(r.OBJECT_NAME)} · orbital epoch {String(r.EPOCH)}
                </p>
              ))}
              {q.data?.reason ? <p>{q.data.reason}</p> : null}
            </div>
          </section>
          <section className="border border-[var(--line)] p-3">
            <h3 className="text-xs mb-2">Economic and maritime connections</h3>
            {context.data?.economics.map((e) => (
              <p key={e.id} className="text-[11px] my-2">
                {e.label}: {e.value ?? "Unavailable"} {e.unit} · {e.status}
                <br />
                <span className="text-[var(--text-3)]">
                  {e.shippingConnection} · reference date{" "}
                  {e.observedAt?.length === 10
                    ? `${e.observedAt} (date only)`
                    : formatUtc(e.observedAt)}
                </span>
              </p>
            ))}
            <p className="text-[10px] text-[var(--text-3)]">
              NASA FIRMS requires a provider key. Transit needs a supported
              agency feed. Camera projection requires a surveyed pose. These
              missing providers leave other layers usable.
            </p>
          </section>
        </div>
        <section className="mt-3 border border-[var(--line)] p-3">
          <h3 className="text-xs mb-2">
            Reports touching this port · existing cascades and decisions
          </h3>
          {context.data?.news.events.map((e) => (
            <button
              key={e.eventId}
              onClick={() => onEvent(e.eventId)}
              className="block text-left text-[11px] py-1 underline"
            >
              {e.title} · {e.categoryLabel}
              <span className="block text-[10px] text-[var(--text-3)]">
                Last seen {formatUtc(e.lastSeen)} ·{" "}
                {e.sources.length === 0 || e.title.includes("fictional demo")
                  ? "Fictional scenario"
                  : Date.now() - Date.parse(e.lastSeen) > 72 * 3600_000
                    ? "Archived report"
                    : "Cached report"}
              </span>
            </button>
          ))}
          <div className="mt-2 flex flex-wrap gap-2">
            {context.data?.ports.map((p) => (
              <button
                key={p.code}
                className="text-xs underline"
                onClick={() => onPort(p.code)}
              >
                {p.code}
              </button>
            ))}
          </div>
        </section>
      </section>
    </div>
  );
}
