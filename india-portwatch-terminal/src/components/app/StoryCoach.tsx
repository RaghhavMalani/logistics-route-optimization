import { useEffect, useState } from "react";
import { useNavigate, useRouterState } from "@tanstack/react-router";
import { useQueryClient } from "@tanstack/react-query";
import { useAuth } from "@/auth/AuthProvider";
import type { Role } from "@/auth/types";
import { Button } from "@/components/kit/layout";
import { invalidateHomePackets } from "@/services/home-screen";
import { fleetReviewHash } from "@/services/rolling-intelligence";
import {
  readStory,
  writeStory,
  type StorySession,
} from "@/services/story-session";
import { runStoryStep } from "@/services/story-workflow";

const chapters: ReadonlyArray<{
  role?: Role;
  title: string;
  coach: string;
  action: string;
}> = [
  {
    role: "SHIPPING_COMPANY",
    title: "A passage decision",
    coach:
      "Calculate the fictional S10 arrival comparison for PW Meridian. The model compares the declared 12 kn approach with a 10 kn alternative.",
    action: "Calculate S10",
  },
  {
    role: "SHIPPING_COMPANY",
    title: "Company chooses 10 kn",
    coach:
      "Compare the assumed anchorage wait at both speeds. Approving sends the saved comparison to the port for review.",
    action: "Approve 10 kn",
  },
  {
    role: "PORT_AUTHORITY",
    title: "Port receives the proposal",
    coach:
      "Open the Company proposal in Port Control. The port reviews the same modelled inputs before it can issue advice.",
    action: "Review proposal",
  },
  {
    role: "PORT_AUTHORITY",
    title: "Port issues advice",
    coach:
      "Confirm the recommendation for PW Meridian. PortWatch records review, approval and issue in the audit trail.",
    action: "Approve and issue to vessel",
  },
  {
    role: "VESSEL_OPERATOR",
    title: "Vessel receives the advisory",
    coach:
      "The bridge sees the issued speed recommendation and the assumed wait. Acknowledge receipt before accepting it.",
    action: "Acknowledge receipt",
  },
  {
    role: "VESSEL_OPERATOR",
    title: "Vessel accepts 10 kn",
    coach:
      "The bridge confirms its choice. The port and Company can now see that the vessel accepted the advisory.",
    action: "Accept advisory",
  },
  {
    role: "PORT_AUTHORITY",
    title: "Port records the outcome",
    coach:
      "Run the frozen simulated outcome. It illustrates the workflow and stays out of real outcome scoring.",
    action: "Run simulated outcome",
  },
  {
    role: "SHIPPING_COMPANY",
    title: "Company sees the completed handoff",
    coach:
      "The handoff now shows Outcome completed. Open Research to see the separate held-out benchmark.",
    action: "Open Research benchmark",
  },
  {
    title: "Passage review complete",
    coach:
      "Company approved, Port issued and Vessel accepted. The Research benchmark measures the decision policy on held-out cases.",
    action: "Finish story",
  },
];

function chapterHref(story: StorySession) {
  switch (story.step) {
    case 1:
      return `/company/global-eye#${fleetReviewHash({
        kind: "SAVED_COMPARISON",
        vesselId: "PWD-001",
        decisionId: story.decisionId,
        optionId: story.optionId,
      })}`;
    case 2:
      return "/port/overview";
    case 3:
    case 6:
      return `/port/advisories?proposal=${encodeURIComponent(story.decisionId ?? "")}`;
    case 4:
      return "/vessel/overview";
    case 5:
      return `/vessel/advisories?advisory=${encodeURIComponent(story.advisoryId ?? "")}`;
    case 8:
      return "/research";
    default:
      return "/company/overview";
  }
}

export function StoryCoach() {
  const [story, setStory] = useState<StorySession | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const { identityHeaders, session, status, switchDemo } = useAuth();
  const navigate = useNavigate();
  const path = useRouterState({ select: (state) => state.location.pathname });
  const client = useQueryClient();
  useEffect(() => {
    const sync = () => setStory(readStory());
    sync();
    window.addEventListener("portwatch:story", sync);
    return () => window.removeEventListener("portwatch:story", sync);
  }, []);
  const chapter = story && chapters[story.step];
  const active =
    chapter &&
    status === "authenticated" &&
    session?.mode === "demo" &&
    session.demoId === story.demoId;

  useEffect(() => {
    if (!active || path !== "/research" || story.step !== 8) return;
    const benchmark = document.querySelector(
      '[aria-label="Decision policy benchmark"]',
    );
    benchmark?.scrollIntoView({ block: "center", behavior: "instant" });
  }, [active, path, story]);

  if (!active) return null;

  const move = async (direction: -1 | 1) => {
    setBusy(true);
    setError(null);
    try {
      if (direction === 1 && story.step === chapters.length - 1) {
        writeStory(null);
        return;
      }
      const requiredRole = chapters[story.step].role;
      let currentRole = session.user.role;
      if (
        direction === 1 &&
        story.step >= story.reached &&
        requiredRole &&
        requiredRole !== currentRole
      ) {
        await switchDemo(requiredRole);
        currentRole = requiredRole;
      }
      const finished =
        direction === 1 && story.step >= story.reached
          ? await runStoryStep(story, identityHeaders)
          : story;
      const step = story.step + direction;
      const next = {
        ...finished,
        step,
        reached: Math.max(story.reached, step),
      };
      writeStory(next);
      const role = chapters[step].role;
      const switchingRole = role && role !== currentRole;
      if (switchingRole) await switchDemo(role);
      await navigate({
        href: chapterHref(next),
        viewTransition: !window.matchMedia("(prefers-reduced-motion: reduce)")
          .matches,
      });
      if (!switchingRole) {
        invalidateHomePackets();
        void client.invalidateQueries();
      }
    } catch (cause) {
      setError(
        cause instanceof Error
          ? cause.message
          : "The chapter could not be completed. Try again.",
      );
    } finally {
      setBusy(false);
    }
  };

  return (
    <aside
      aria-label="Guided demo"
      data-testid="story-coach"
      className="fixed bottom-14 left-4 z-[80] w-[min(25rem,calc(100vw-2rem))] border border-[var(--line-strong)] bg-[var(--panel)] p-4 text-[var(--text)] shadow-[var(--shadow-floating)]"
    >
      <div className="flex items-start justify-between gap-2">
        <p className="eyebrow">
          Guided demo · {story.step + 1} of {chapters.length}
        </p>
        <button
          type="button"
          onClick={() => writeStory(null)}
          disabled={busy}
          className="text-xs underline underline-offset-2"
        >
          Exit story
        </button>
      </div>
      <h2 className="mt-2 text-xl font-semibold tracking-tight">
        {chapter.title}
      </h2>
      <p className="mt-1.5 text-sm leading-snug text-[var(--text-2)]">
        {chapter.coach}
      </p>
      {story.wait && [1, 3, 4, 8].includes(story.step) ? (
        <p className="mt-3 border-y border-[var(--line)] py-2 font-mono text-xs">
          Modelled anchorage wait · {story.wait.before.toFixed(2)} →{" "}
          {story.wait.after.toFixed(2)} h
        </p>
      ) : null}
      {error ? (
        <p role="alert" className="mt-2 text-xs text-[var(--crit)]">
          {error}
        </p>
      ) : null}
      <div className="mt-3 flex items-center justify-between gap-2">
        <Button
          disabled={story.step === 0 || busy}
          onClick={() => void move(-1)}
        >
          Back
        </Button>
        <Button variant="primary" disabled={busy} onClick={() => void move(1)}>
          {busy
            ? "Saving…"
            : story.step < story.reached
              ? "Next"
              : chapter.action}
        </Button>
      </div>
    </aside>
  );
}
