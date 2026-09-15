/**
 * What two lenses now read from the backend rather than from a static note.
 *
 * SECURITY asks /security/lens. Under the replay the answer is UNAVAILABLE
 * with the reason, and that reason is what is shown -- the lens never draws
 * a detection it did not get. With observed AIS it lists every detection
 * with its rule, evidence, threshold, confidence and instants.
 *
 * CARGO asks /trade/exposure for the selected event: which Indian cargo
 * classes the event structurally reaches, through how many chains. No
 * volume is shown because none is held; the panel says STRUCTURAL EXPOSURE
 * and carries the disclaimer the API sends.
 */

import { Pill } from "@/components/kit/primitives";
import { cn } from "@/lib/utils";
import { useSecurityLens, useTradeExposure } from "@/services/lenses";

const RULE_LABELS: Record<string, string> = {
  prolonged_ais_gap: "Prolonged AIS gap",
  improbable_position_jump: "Improbable position jump",
  unusual_loitering: "Unusual loitering",
  route_deviation: "Route deviation",
  destination_inconsistency: "Destination inconsistency",
  abnormal_speed_state: "Abnormal speed state",
  repeated_identity_conflict: "Repeated identity conflict",
};

function Frame({
  label,
  tone,
  children,
  testId,
}: {
  label: string;
  tone: "neutral" | "ok" | "warn";
  children: React.ReactNode;
  testId: string;
}) {
  return (
    <div
      className="pointer-events-auto rounded border border-[var(--line)] bg-[var(--surface)]/94 px-2.5 py-2 backdrop-blur"
      data-testid={testId}
    >
      <div className="flex items-center gap-1.5">
        <Pill tone={tone}>{label}</Pill>
      </div>
      {children}
    </div>
  );
}

export function SecurityLensReport({ mode }: { mode: string }) {
  const lens = useSecurityLens(mode);
  if (lens.isLoading) {
    return (
      <Frame
        label="Security · asking the feed"
        tone="neutral"
        testId="lens-security"
      >
        <p className="mt-1 text-[10px] text-[var(--text-2)]">
          Reading observed AIS for the seven behaviour rules…
        </p>
      </Frame>
    );
  }
  if (lens.isError || !lens.data) {
    return (
      <Frame
        label="Security · unavailable"
        tone="neutral"
        testId="lens-security"
      >
        <p className="mt-1 text-[10px] text-[var(--text-2)]">
          The security lens could not be read:{" "}
          {(lens.error as Error | null)?.message ?? "no answer"}.
        </p>
      </Frame>
    );
  }
  const data = lens.data;
  if (data.status !== "SECURITY ANALYTICS AVAILABLE") {
    return (
      <Frame
        label="Security analytics unavailable"
        tone="neutral"
        testId="lens-security"
      >
        <p className="mt-1 text-[10.5px] font-medium text-[var(--text)]">
          No observed AIS in this deployment ({data.mode})
        </p>
        <p className="mt-1 text-[10.5px] leading-relaxed text-[var(--text-2)]">
          {data.reason}
        </p>
        <ul className="mt-1.5 flex flex-wrap gap-x-2 gap-y-0.5">
          {data.rules.map((rule) => (
            <li key={rule} className="text-[10px] text-[var(--text-3)]">
              · {RULE_LABELS[rule] ?? rule}
            </li>
          ))}
        </ul>
      </Frame>
    );
  }
  return (
    <Frame
      label={
        data.stale ? "Security · observed, stale" : "Security · observed AIS"
      }
      tone={data.stale ? "warn" : "ok"}
      testId="lens-security"
    >
      <p className="mt-1 text-[10.5px] text-[var(--text-2)]">
        {data.tracksAnalysed} tracks analysed · {data.detections.length}{" "}
        detection
        {data.detections.length === 1 ? "" : "s"}
        {data.reason ? ` · ${data.reason}` : ""}
      </p>
      {data.detections.length === 0 ? (
        <p className="mt-1 text-[10px] text-[var(--text-3)]">
          No rule fired on the observed tracks. That is a computed absence, not
          an empty feed.
        </p>
      ) : (
        <ul className="mt-1.5 flex max-h-[220px] flex-col gap-1 overflow-y-auto">
          {data.detections.slice(0, 20).map((d, index) => (
            <li
              key={`${d.rule}-${d.mmsi}-${index}`}
              className="rounded border border-[var(--line)] px-2 py-1"
              data-testid="security-detection"
            >
              <div className="flex items-center gap-1.5">
                <span className="text-[10px] font-medium text-[var(--text)]">
                  {RULE_LABELS[d.rule] ?? d.rule}
                </span>
                <span className="num ml-auto text-[10px] text-[var(--text-3)]">
                  confidence {(d.confidence * 100).toFixed(0)}%
                </span>
              </div>
              <p className="text-[10.5px] text-[var(--text-2)]">
                {d.statement}
              </p>
              <p className="num text-[10px] text-[var(--text-3)]">
                MMSI {d.mmsi} ·{" "}
                {d.observationTimestamps
                  .map((t) => t.slice(5, 16).replace("T", " "))
                  .join(" → ")}
                {" · threshold "}
                {Object.entries(d.threshold)
                  .map(([k, v]) => `${k} ${String(v)}`)
                  .join(", ")}
              </p>
            </li>
          ))}
        </ul>
      )}
    </Frame>
  );
}

export function TradeExposureReport({ eventId }: { eventId: string | null }) {
  const exposure = useTradeExposure(eventId);
  if (!eventId) {
    return (
      <Frame label="Structural exposure" tone="neutral" testId="lens-cargo">
        <p className="mt-1 text-[10px] text-[var(--text-2)]">
          Select an event to see which Indian cargo classes it structurally
          reaches.
        </p>
      </Frame>
    );
  }
  if (exposure.isLoading) {
    return (
      <Frame label="Structural exposure" tone="neutral" testId="lens-cargo">
        <p className="mt-1 text-[10px] text-[var(--text-2)]">
          Tracing the chains…
        </p>
      </Frame>
    );
  }
  if (exposure.isError || !exposure.data) {
    return (
      <Frame
        label="Structural exposure · unavailable"
        tone="neutral"
        testId="lens-cargo"
      >
        <p className="mt-1 text-[10px] text-[var(--text-2)]">
          {(exposure.error as Error | null)?.message ?? "no answer"}
        </p>
      </Frame>
    );
  }
  const data = exposure.data;
  const exposed = data.classes.filter((c) => c.exposed);
  return (
    <Frame
      label="Structural exposure"
      tone={exposed.length ? "warn" : "neutral"}
      testId="lens-cargo"
    >
      <p className="mt-1 text-[10.5px] font-medium text-[var(--text)]">
        {exposed.length
          ? `${exposed.length} of ${data.classes.length} cargo classes reached through ${data.chains.length} chain${
              data.chains.length === 1 ? "" : "s"
            }`
          : "No Indian cargo class is structurally reached by this event"}
      </p>
      <ul className="mt-1.5 grid grid-cols-2 gap-x-3 gap-y-0.5">
        {data.classes.map((c) => (
          <li
            key={c.commodityClass}
            className="flex items-baseline gap-1.5 text-[10.5px]"
            data-testid="exposure-class"
            data-exposed={c.exposed}
          >
            <span
              className={cn(
                "min-w-0 truncate",
                c.exposed ? "text-[var(--text)]" : "text-[var(--text-3)]",
              )}
            >
              {c.label.split(" (")[0]}
            </span>
            <span className="num ml-auto shrink-0 whitespace-nowrap text-[var(--text-3)]">
              {c.exposed
                ? `${c.chains} chain${c.chains === 1 ? "" : "s"} · ${c.ports.length} port${c.ports.length === 1 ? "" : "s"}`
                : "—"}
            </span>
          </li>
        ))}
      </ul>
      <p className="mt-1.5 text-[10px] leading-snug text-[var(--text-3)]">
        {data.disclaimer}
      </p>
    </Frame>
  );
}
