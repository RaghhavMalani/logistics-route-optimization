import { useEffect, useRef, useState } from "react";
import {
  scrollToWorkflowStep,
  WorkflowRail,
} from "@/components/miniature/WorkflowRail";

const stations = [
  { key: "company", label: "Company" },
  { key: "port", label: "Port" },
  { key: "vessel", label: "Vessel" },
] as const;

const stages: Record<string, { station: number; detail: string }> = {
  COMPANY_PROPOSED: { station: 0, detail: "Comparison sent to Port." },
  PORT_REVIEWING: { station: 1, detail: "Port review is open." },
  ISSUED_TO_VESSEL: { station: 2, detail: "Advisory issued to Vessel." },
  ACKNOWLEDGED: { station: 2, detail: "Vessel acknowledged receipt." },
  ACCEPTED: { station: 2, detail: "Vessel accepted the advisory." },
  QUERIED: { station: 1, detail: "Vessel returned a question to Port." },
  DECLINED: { station: 2, detail: "Vessel declined the advisory." },
  REJECTED: { station: 1, detail: "Port rejected the advisory." },
  WITHDRAWN: { station: 1, detail: "Port withdrew the advisory." },
  EXPIRED: { station: 2, detail: "The advisory expired." },
  COMPLETED: { station: 2, detail: "The advisory is complete." },
  OUTCOME_RECORDED: { station: 2, detail: "Port recorded the outcome." },
};

export function HandoffJourney({
  id,
  state,
  viewer,
}: {
  id: string;
  state: string;
  viewer: string | undefined;
}) {
  const stage = stages[state];
  const [viewed, setViewed] = useState<string | null>(null);
  const [motion, setMotion] = useState<{
    from: number;
    state: string;
  } | null>(null);
  const journey = useRef<HTMLDivElement>(null);
  const detail = useRef<HTMLParagraphElement>(null);
  const visited = useRef<{ id: string; state: string } | null>(null);

  useEffect(() => {
    if (!stage || !journey.current) return;
    // Another role can open the same record while this copy is offscreen.
    // Only remember a stage once the operator can see its parcel.
    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.intersectionRatio < 0.8) return;
        observer.disconnect();
        const key = `portwatch:handoff:${viewer ?? ""}:${id}`;
        let previous =
          visited.current?.id === id ? visited.current.state : null;
        try {
          previous = sessionStorage.getItem(key) ?? previous;
          sessionStorage.setItem(key, state);
        } catch {
          // Same-card transitions still work when browser storage is unavailable.
        }
        visited.current = { id, state };
        const from = previous ? stages[previous]?.station : undefined;
        if (from !== undefined && previous !== state) {
          setMotion({ from, state });
        }
      },
      { threshold: 0.8 },
    );
    observer.observe(journey.current);
    return () => observer.disconnect();
  }, [id, stage, state, viewer]);

  useEffect(() => {
    if (viewed) scrollToWorkflowStep(detail.current);
  }, [viewed]);

  if (!stage) return null;
  const active = stations[stage.station].key;
  const picked = stations.findIndex((station) => station.key === viewed);
  const parcelPosition = (index: number) => `${((index + 0.5) / 3) * 100}%`;
  return (
    <div ref={journey} className="pw-handoff-journey">
      <WorkflowRail
        label="Company to Port to Vessel"
        steps={stations}
        current={active}
        onStep={(key) => {
          setViewed(key);
          if (key === viewed) scrollToWorkflowStep(detail.current);
        }}
      />
      <div className="pw-handoff-lane" aria-hidden="true">
        {stations.map(({ key }) => (
          <span key={key} />
        ))}
        <i
          key={state}
          className="pw-handoff-parcel"
          data-animation={
            motion?.state === state
              ? motion.from === stage.station
                ? "stamp"
                : "travel"
              : undefined
          }
          style={{
            left: parcelPosition(stage.station),
            ...{
              "--parcel-from": parcelPosition(motion?.from ?? stage.station),
            },
          }}
        />
      </div>
      <p ref={detail} hidden={!viewed} className="pw-handoff-stage-detail">
        {picked < 0
          ? null
          : picked === stage.station
            ? stage.detail
            : picked < stage.station
              ? `${stations[picked]?.label ?? ""} has handed the record onward.`
              : `Awaiting the handoff to ${stations[picked].label}.`}
      </p>
    </div>
  );
}
