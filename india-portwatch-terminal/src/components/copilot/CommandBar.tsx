/**
 * The Copilot as a command bar, not a chat panel.
 *
 * A chat sidebar makes the conversation the product and leaves the world as
 * wallpaper behind it. The answer to "why is JNPA at risk?" is not a paragraph
 * about JNPA -- it is the camera moving there, the cascades that reach it
 * drawing, and the evidence opening. So this is a single field that takes a
 * sentence and gets out of the way, and what it returns is mostly the world
 * changing.
 *
 * The text that does appear is deliberately small: a one-line summary and a
 * list of what actually happened to the world, including anything refused. An
 * operator has to be able to tell "I moved the camera and filtered the queue"
 * from "I also sent something", and a Copilot that reported only its successes
 * would make that impossible.
 */

import { useMutation } from "@tanstack/react-query";
import { useCallback, useEffect, useRef, useState } from "react";

import { useAuth, useWorkspace } from "@/auth/AuthProvider";
import { Pill } from "@/components/kit/primitives";
import { cn } from "@/lib/utils";
import { runAgent } from "@/services/portwatch-os";
import type { AgentRun } from "@/types/portwatch-os";
import { useWorld, type DispatchOutcome } from "@/world/WorldContext";

/** Openers that get somebody to the useful behaviour on their first try. */
const SUGGESTIONS = [
  "What should I handle first?",
  "Why is JNPA at risk?",
  "Show every ship still able to avoid the Red Sea disruption",
  "Project this to tomorrow evening",
];

export function CommandBar() {
  const { identityHeaders } = useAuth();
  const { role, portCode, companyId } = useWorkspace();
  const world = useWorld();

  const [open, setOpen] = useState(false);
  const [text, setText] = useState("");
  const [run, setRun] = useState<AgentRun | null>(null);
  const [outcomes, setOutcomes] = useState<DispatchOutcome[]>([]);
  const inputRef = useRef<HTMLInputElement>(null);

  /* Cmd/Ctrl+K opens it; Escape puts it away. */
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        setOpen(true);
        window.setTimeout(() => inputRef.current?.focus(), 0);
      }
      if (event.key === "Escape") setOpen(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const mutation = useMutation({
    mutationFn: (question: string) =>
      runAgent(
        {
          question,
          role,
          portCode: role === "PORT_AUTHORITY" ? portCode : null,
          companyId,
          includeResults: false,
        },
        identityHeaders,
      ),
    onSuccess: (result) => {
      setRun(result);
      // This is the loop closing: the answer moves the world.
      setOutcomes(world.dispatchAll(result.spatial ?? []));
    },
  });

  const ask = useCallback(
    (question: string) => {
      const trimmed = question.trim();
      if (!trimmed) return;
      setText(trimmed);
      mutation.mutate(trimmed);
    },
    [mutation],
  );

  if (!open) {
    return (
      <button
        type="button"
        data-testid="command-bar-open"
        onClick={() => {
          setOpen(true);
          window.setTimeout(() => inputRef.current?.focus(), 0);
        }}
        className={cn(
          "pointer-events-auto flex items-center gap-2 rounded border border-[var(--line)]",
          "bg-[var(--surface)]/92 px-2.5 py-1.5 text-[10.5px] text-[var(--text-3)]",
          "backdrop-blur transition-colors hover:text-[var(--text)]",
        )}
      >
        <span>Ask the world</span>
        <kbd className="num rounded border border-[var(--line)] px-1 text-[9px]">
          ⌘K
        </kbd>
      </button>
    );
  }

  const applied = outcomes.filter((o) => o.applied);
  const refused = outcomes.filter((o) => !o.applied);

  return (
    <div
      data-testid="command-bar"
      className={cn(
        "pointer-events-auto w-[460px] rounded border border-[var(--line)]",
        "bg-[var(--surface)]/95 backdrop-blur",
      )}
    >
      <form
        onSubmit={(event) => {
          event.preventDefault();
          ask(text);
        }}
        className="flex items-center gap-2 border-b border-[var(--line)] px-2.5 py-2"
      >
        <span className="text-[10px] text-[var(--text-3)]">›</span>
        <input
          ref={inputRef}
          data-testid="command-input"
          value={text}
          onChange={(event) => setText(event.target.value)}
          placeholder="Ask about the world…"
          className={cn(
            "min-w-0 flex-1 bg-transparent text-[11.5px] text-[var(--text)]",
            "placeholder:text-[var(--text-3)] focus:outline-none",
          )}
        />
        {mutation.isPending ? (
          <span className="num text-[9.5px] text-[var(--text-3)]">working…</span>
        ) : null}
        <button
          type="button"
          onClick={() => setOpen(false)}
          aria-label="Close"
          className="text-[10px] text-[var(--text-3)] hover:text-[var(--text)]"
        >
          ✕
        </button>
      </form>

      {!run && !mutation.isPending ? (
        <div className="px-2.5 py-2">
          <p className="mb-1.5 text-[9px] uppercase tracking-wide text-[var(--text-3)]">
            Try
          </p>
          <div className="flex flex-col gap-1">
            {SUGGESTIONS.map((suggestion) => (
              <button
                key={suggestion}
                type="button"
                data-testid="command-suggestion"
                onClick={() => ask(suggestion)}
                className="truncate text-left text-[10.5px] text-[var(--text-2)] hover:text-[var(--text)]"
              >
                {suggestion}
              </button>
            ))}
          </div>
        </div>
      ) : null}

      {mutation.isError ? (
        <p className="px-2.5 py-2 text-[10.5px] text-[var(--warn)]">
          The run failed: {(mutation.error as Error).message}
        </p>
      ) : null}

      {run ? (
        <div data-testid="command-answer" className="px-2.5 py-2">
          <p className="text-[10.5px] leading-relaxed text-[var(--text)]">
            {run.summary}
          </p>

          {applied.length ? (
            <div className="mt-2">
              <p className="mb-1 text-[9px] uppercase tracking-wide text-[var(--text-3)]">
                What changed
              </p>
              <ul data-testid="command-applied" className="flex flex-col gap-0.5">
                {applied.map((outcome, index) => (
                  <li
                    key={`${outcome.kind}-${index}`}
                    className="num text-[9.5px] text-[var(--text-2)]"
                  >
                    {outcome.reason}
                  </li>
                ))}
              </ul>
            </div>
          ) : null}

          {/*
            Refusals are shown, not swallowed. An operator must be able to tell
            "the camera moved" from "and something was also sent".
          */}
          {refused.length ? (
            <div className="mt-2">
              <p className="mb-1 text-[9px] uppercase tracking-wide text-[var(--text-3)]">
                Not run
              </p>
              <ul data-testid="command-refused" className="flex flex-col gap-0.5">
                {refused.map((outcome, index) => (
                  <li
                    key={`${outcome.kind}-${index}`}
                    className="text-[9.5px] text-[var(--text-3)]"
                  >
                    <Pill tone="neutral">{outcome.kind}</Pill>{" "}
                    {outcome.reason}
                  </li>
                ))}
              </ul>
            </div>
          ) : null}

          {run.spatial?.length === 0 ? (
            <p className="mt-2 text-[9.5px] italic text-[var(--text-3)]">
              Nothing in this answer named a subject the world could move to, so
              the view is unchanged.
            </p>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
