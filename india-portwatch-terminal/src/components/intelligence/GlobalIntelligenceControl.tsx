import { lazy, Suspense, useEffect, useState } from "react";
import { createPortal } from "react-dom";
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
}: {
  portCode: string | null;
  onPort: (code: string) => void;
  onEvent: (id: string) => void;
  onVessel: (id: string) => void;
  onDecision?: (problem: DecisionProblem) => void;
}) {
  const [open, setOpen] = useState(false);
  useEffect(() => {
    const closeForAsset = () => setOpen(false);
    window.addEventListener("portwatch:focus-constraint", closeForAsset);
    return () =>
      window.removeEventListener("portwatch:focus-constraint", closeForAsset);
  }, []);
  return (
    <div className="absolute bottom-[164px] right-3 z-30 pointer-events-auto">
      <Button size="sm" variant="outline" onClick={() => setOpen(true)}>
        Global intelligence
      </Button>
      {open
        ? createPortal(
            <div
              role="dialog"
              aria-label="Connected global intelligence"
              className="pointer-events-auto fixed inset-x-[4vw] top-[8vh] bottom-[8vh] z-[100] flex flex-col overflow-hidden rounded border border-[var(--line-strong)] bg-[var(--panel)] shadow-2xl"
            >
              <div className="flex justify-between border-b border-[var(--line)] p-3">
                <strong className="min-w-0 text-sm">
                  Global intelligence · connected to the existing workspace
                </strong>
                <Button
                  size="sm"
                  variant="ghost"
                  className="shrink-0"
                  onClick={() => setOpen(false)}
                >
                  Close intelligence
                </Button>
              </div>
              <IntelligenceContents
                onDecision={
                  onDecision
                    ? (problem) => {
                        onDecision(problem);
                        setOpen(false);
                      }
                    : undefined
                }
                portCode={portCode ?? "INNSA"}
                onPort={(c) => {
                  onPort(c);
                  setOpen(false);
                }}
                onEvent={(e) => {
                  onEvent(e);
                  setOpen(false);
                }}
                onVessel={(id) => {
                  onVessel(id);
                  setOpen(false);
                }}
              />
            </div>,
            document.body,
          )
        : null}
    </div>
  );
}

function IntelligenceContents({
  portCode,
  onPort,
  onEvent,
  onVessel,
  onDecision,
}: {
  portCode: string;
  onPort: (code: string) => void;
  onEvent: (id: string) => void;
  onVessel: (id: string) => void;
  onDecision?: (problem: DecisionProblem) => void;
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
    <div className="flex-1 min-h-0 overflow-auto p-3">
      <ShippingIntelligencePanel onDecision={onDecision} />
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
        <Button size="sm" variant="outline" onClick={() => setGlobe(!globe)}>
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
        original map and timeline. Aircraft and satellite context does not imply
        a shipping delay. Selecting a port or event returns to its existing
        inspector and decision workflow.
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
        <p className="text-xs">
          Context unavailable. The original map remains available.
        </p>
      ) : null}
      <div className="grid gap-3 mt-3 lg:grid-cols-2">
        <section className="border border-[var(--line)] p-3">
          <h3 className="text-xs mb-2">
            {layer} · {portCode}{" "}
            <Pill>
              {q.data?.status ?? (q.isError ? "UNAVAILABLE" : "LOADING")}
            </Pill>
          </h3>
          <p className="text-[11px] text-[var(--text-3)]">{q.data?.coverage}</p>
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
                {e.shippingConnection} · observed {formatUtc(e.observedAt)}
              </span>
            </p>
          ))}
          <p className="text-[10px] text-[var(--text-3)]">
            NASA FIRMS requires a provider key. Transit needs a supported agency
            feed. Camera projection requires a surveyed pose. These missing
            providers leave other layers usable.
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
    </div>
  );
}
