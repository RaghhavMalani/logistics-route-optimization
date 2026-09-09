/**
 * The agent surface.
 *
 * Deliberately *not* a chat window that takes over the product. It is a
 * collapsed strip that expands into a panel over whatever screen the operator
 * is already on, and it closes again. The map stays primary.
 *
 * What it shows is the trace, not a transcript. Each agent that ran, each tool
 * it called, whether the call succeeded, and which deterministic module produced
 * the numbers. An operator who does not trust the answer can open the evidence
 * and find the model that computed it -- which is the entire difference between
 * this and a chatbot that says confident things about shipping.
 *
 * Nothing here can execute. The orchestrator runs at a PROPOSE ceiling and the
 * console has no approval path; an advisory drafted by an agent still has to be
 * issued by a controller on the advisory screen.
 */

import { useMutation } from "@tanstack/react-query";
import {
  Check,
  ChevronDown,
  ChevronRight,
  CircleAlert,
  Sparkles,
  X,
} from "lucide-react";
import { useState } from "react";

import { useWorkspace } from "@/auth/AuthProvider";
import { Pill, type Tone } from "@/components/kit/primitives";
import { cn } from "@/lib/utils";
import { runAgent } from "@/services/portwatch-os";
import type { AgentResultView, AgentRun, ToolCallTrace } from "@/types/portwatch-os";

/** Prompts that match a real intent, by role. Not decoration: these are the
 *  questions the orchestrator actually has a plan for. */
const SUGGESTIONS: Record<string, string[]> = {
  NATIONAL_ADMIN: [
    "What is happening in the world that affects Indian ports?",
    "What is happening at Chennai?",
    "How wrong has PortWatch been lately?",
  ],
  SHIPPING_COMPANY: [
    "Which ships in my fleet require action because of Red Sea risk?",
    "Which vessels are exposed at Hormuz in the next 48 hours?",
    "Can cargo at Chennai make a connection?",
  ],
  PORT_AUTHORITY: [
    "What is happening at my port?",
    "Should we advise an arrival change?",
    "Can transshipment cargo make its connection?",
  ],
  VESSEL_OPERATOR: [
    "What weather is ahead?",
    "What is the congestion at my destination?",
  ],
};

const OUTCOME_TONE: Record<string, Tone> = {
  complete: "ok",
  partial: "unc",
  blocked: "crit",
};

const ACCESS_TONE: Record<string, Tone> = {
  READ: "info",
  SIMULATE: "unc",
  PROPOSE: "warn",
  EXECUTE: "crit",
  DENIED: "crit",
  UNKNOWN: "neutral",
};

/* ------------------------------------------------------------------ trace -- */

function ToolChip({ call }: { call: ToolCallTrace }) {
  const short = call.tool.replace(/^portwatch\./, "");
  return (
    <span
      title={
        call.ok
          ? `${call.tool} — computed by ${call.computedBy || "unstated"} (${call.durationMs.toFixed(0)} ms)`
          : `${call.tool} — ${call.error}`
      }
      className={cn(
        "inline-flex items-center gap-1 rounded-[2px] border px-1.5 py-[1px] text-[9.5px]",
        call.ok
          ? "border-[var(--line-strong)] text-[var(--text-2)]"
          : call.unavailable
            ? "border-[var(--unc)]/50 text-[var(--unc)]"
            : "border-[var(--crit)]/50 text-[var(--crit)]",
      )}
    >
      {call.ok ? <Check size={8} /> : <CircleAlert size={8} />}
      <span className="num">{short}</span>
    </span>
  );
}

function AgentBlock({ result }: { result: AgentResultView }) {
  const [open, setOpen] = useState(false);
  return (
    <li className="border-b border-[var(--line)]/60 last:border-0">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-start gap-2 px-2 py-1.5 text-left hover:bg-[var(--panel-2)]"
      >
        {open ? (
          <ChevronDown size={11} className="mt-[3px] shrink-0 text-[var(--text-3)]" />
        ) : (
          <ChevronRight size={11} className="mt-[3px] shrink-0 text-[var(--text-3)]" />
        )}
        <div className="min-w-0 flex-1">
          <div className="flex items-baseline gap-2">
            <span className="text-[11px] font-medium uppercase tracking-[0.05em] text-[var(--text)]">
              {result.agent.replace(/_/g, " ")}
            </span>
            <Pill tone={OUTCOME_TONE[result.outcome] ?? "neutral"}>{result.outcome}</Pill>
            {result.confidence != null ? (
              <span className="num text-[9.5px] text-[var(--text-3)]">
                conf {result.confidence.toFixed(2)}
              </span>
            ) : null}
          </div>
          <p className="mt-[2px] text-[10.5px] leading-snug text-[var(--text-2)]">
            {result.summary}
          </p>
          <div className="mt-1 flex flex-wrap gap-1">
            {result.trace.map((call, index) => (
              <ToolChip key={`${call.tool}-${index}`} call={call} />
            ))}
          </div>
        </div>
      </button>

      {open ? (
        <div className="space-y-2 border-t border-[var(--line)]/60 bg-[var(--panel-2)]/40 px-3 py-2">
          {result.findings.length ? (
            <section>
              <h4 className="eyebrow text-[8.5px]">Findings</h4>
              <ul className="mt-1 space-y-1">
                {result.findings.map((finding, index) => (
                  <li key={`${finding.label}-${index}`}>
                    <div className="flex items-baseline gap-2">
                      <span className="text-[10.5px] text-[var(--text-3)]">
                        {finding.label}
                      </span>
                      <span className="num text-[11px] text-[var(--text)]">
                        {finding.value == null ? "n/a" : String(finding.value)}
                        {finding.unit ? (
                          <span className="ml-0.5 text-[9px] text-[var(--text-3)]">
                            {finding.unit}
                          </span>
                        ) : null}
                      </span>
                      <span className="num ml-auto shrink-0 text-[8.5px] text-[var(--text-3)]">
                        {finding.sourceTool.replace(/^portwatch\./, "")}
                      </span>
                    </div>
                    {finding.detail ? (
                      <p className="text-[9.5px] leading-snug text-[var(--text-3)]">
                        {finding.detail}
                      </p>
                    ) : null}
                  </li>
                ))}
              </ul>
            </section>
          ) : null}

          {result.gaps.length ? (
            <section>
              <h4 className="eyebrow text-[8.5px]">Evidence gaps</h4>
              <ul className="mt-1 space-y-0.5">
                {result.gaps.map((gap) => (
                  <li key={gap} className="text-[9.5px] leading-snug text-[var(--unc)]">
                    {gap}
                  </li>
                ))}
              </ul>
            </section>
          ) : null}

          <section>
            <h4 className="eyebrow text-[8.5px]">Where the numbers came from</h4>
            <ul className="mt-1 space-y-0.5">
              {result.trace
                .filter((call) => call.ok && call.computedBy)
                .map((call, index) => (
                  <li
                    key={`${call.tool}-${index}`}
                    className="flex items-baseline gap-1.5 text-[9.5px]"
                  >
                    <span className="num shrink-0 text-[var(--text-2)]">
                      {call.tool.replace(/^portwatch\./, "")}
                    </span>
                    <span className="min-w-0 truncate text-[var(--text-3)]">
                      {call.computedBy}
                    </span>
                  </li>
                ))}
            </ul>
          </section>
        </div>
      ) : null}
    </li>
  );
}

/* ---------------------------------------------------------------- console -- */

export function AgentConsole({ className }: { className?: string }) {
  const { role, portCode, companyId } = useWorkspace();
  const [open, setOpen] = useState(false);
  const [question, setQuestion] = useState("");
  const [run, setRun] = useState<AgentRun | null>(null);

  const mutation = useMutation({
    mutationFn: (text: string) =>
      runAgent({
        question: text,
        role,
        portCode: role === "PORT_AUTHORITY" ? portCode : null,
        companyId,
        includeResults: false,
      }),
    onSuccess: (result) => setRun(result),
  });

  const ask = (text: string) => {
    if (!text.trim()) return;
    setQuestion(text);
    mutation.mutate(text);
  };

  if (!open) {
    return (
      <button
        type="button"
        data-testid="agent-console-open"
        onClick={() => setOpen(true)}
        className={cn(
          "pointer-events-auto inline-flex items-center gap-1.5 rounded-[3px] border border-[var(--line-strong)]",
          "bg-[var(--panel)]/95 px-2 py-[5px] text-[11px] text-[var(--text-2)] backdrop-blur-[3px]",
          "shadow-[0_8px_24px_rgba(0,0,0,0.4)] transition-colors hover:text-[var(--text)]",
          className,
        )}
      >
        <Sparkles size={11} className="text-[var(--info)]" />
        Ask PortWatch
      </button>
    );
  }

  return (
    <section
      data-testid="agent-console"
      className={cn(
        "pointer-events-auto flex max-h-[min(560px,calc(100vh-140px))] w-[400px] flex-col overflow-hidden",
        "rounded-[3px] border border-[var(--line-strong)] bg-[var(--panel)]/97 backdrop-blur-[4px]",
        "shadow-[0_14px_40px_rgba(0,0,0,0.55)]",
        className,
      )}
    >
      <header className="flex h-[26px] shrink-0 items-center gap-2 border-b border-[var(--line)] bg-[var(--panel-2)]/85 px-2">
        <Sparkles size={11} className="text-[var(--info)]" />
        <span className="flex-1 text-[10px] font-semibold uppercase tracking-[0.09em] text-[var(--text-2)]">
          Ask PortWatch
        </span>
        <button
          type="button"
          aria-label="Close the agent console"
          onClick={() => setOpen(false)}
          className="text-[var(--text-3)] hover:text-[var(--text)]"
        >
          <X size={12} />
        </button>
      </header>

      <form
        className="shrink-0 border-b border-[var(--line)] p-2"
        onSubmit={(event) => {
          event.preventDefault();
          ask(question);
        }}
      >
        <input
          value={question}
          onChange={(event) => setQuestion(event.target.value)}
          placeholder="Which ships require action because of Red Sea risk?"
          data-testid="agent-question"
          className="w-full rounded-[2px] border border-[var(--line)] bg-[var(--panel-2)] px-2 py-[5px] text-[11.5px] text-[var(--text)] outline-none placeholder:text-[var(--text-3)] focus:border-[var(--info)]"
        />
        <div className="mt-1.5 flex flex-wrap gap-1">
          {(SUGGESTIONS[role] ?? []).map((suggestion) => (
            <button
              key={suggestion}
              type="button"
              onClick={() => ask(suggestion)}
              className="truncate rounded-[2px] border border-[var(--line)] px-1.5 py-[2px] text-left text-[9.5px] text-[var(--text-3)] transition-colors hover:text-[var(--text-2)]"
            >
              {suggestion}
            </button>
          ))}
        </div>
      </form>

      <div className="min-h-0 flex-1 overflow-auto">
        {mutation.isPending ? (
          <div className="flex items-center gap-2 px-3 py-4 text-[11px] text-[var(--text-3)]">
            <span className="pw-breathe h-1.5 w-1.5 rounded-full bg-[var(--info)]" />
            Running the chain…
          </div>
        ) : mutation.isError ? (
          <p className="px-3 py-4 text-[11px] leading-relaxed text-[var(--crit)]">
            {mutation.error instanceof Error
              ? mutation.error.message
              : "The agent run failed."}
          </p>
        ) : run ? (
          <>
            <div className="border-b border-[var(--line)] px-2 py-2">
              <div className="flex flex-wrap items-center gap-1.5">
                <Pill tone="info">{run.intentLabel}</Pill>
                <Pill tone={OUTCOME_TONE[run.outcome] ?? "neutral"}>{run.outcome}</Pill>
                {run.confidence != null ? (
                  <span className="num text-[9.5px] text-[var(--text-3)]">
                    confidence {run.confidence.toFixed(2)}
                  </span>
                ) : null}
                <span className="num ml-auto text-[9px] text-[var(--text-3)]">
                  {run.durationMs.toFixed(0)} ms · {run.trace.length} tool calls
                </span>
              </div>
              <p className="mt-1.5 text-[11.5px] leading-relaxed text-[var(--text)]">
                {run.summary}
              </p>
              <p className="num mt-1 text-[9px] text-[var(--text-3)]">
                intent chosen by {run.intentBasis}
              </p>
            </div>

            {run.critic ? (
              <div
                className={cn(
                  "border-b border-[var(--line)] px-2 py-2",
                  run.critic.verdict === "REJECTED" && "bg-[var(--crit-dim)]/20",
                  run.critic.verdict === "MODIFIED" && "bg-[var(--unc-dim)]/20",
                )}
                data-testid="agent-critic"
              >
                <div className="flex items-center gap-1.5">
                  <span className="eyebrow text-[8.5px]">Critic</span>
                  <Pill
                    tone={
                      run.critic.verdict === "APPROVED"
                        ? "ok"
                        : run.critic.verdict === "MODIFIED"
                          ? "unc"
                          : "crit"
                    }
                  >
                    {run.critic.verdict}
                  </Pill>
                  {run.critic.adjustedConfidence != null ? (
                    <span className="num ml-auto text-[9.5px] text-[var(--text-3)]">
                      adjusted {run.critic.adjustedConfidence.toFixed(2)}
                    </span>
                  ) : null}
                </div>
                <ul className="mt-1 space-y-0.5">
                  {run.critic.checks.map((check) => (
                    <li
                      key={check.name}
                      className="flex items-start gap-1.5 text-[9.5px] leading-snug"
                    >
                      {check.passed ? (
                        <Check size={9} className="mt-[2px] shrink-0 text-[var(--ok)]" />
                      ) : (
                        <CircleAlert
                          size={9}
                          className={cn(
                            "mt-[2px] shrink-0",
                            check.severity === "blocking"
                              ? "text-[var(--crit)]"
                              : "text-[var(--unc)]",
                          )}
                        />
                      )}
                      <span
                        className={
                          check.passed ? "text-[var(--text-3)]" : "text-[var(--text-2)]"
                        }
                      >
                        {check.detail}
                      </span>
                    </li>
                  ))}
                </ul>
              </div>
            ) : null}

            <ul>
              {run.agents.map((result) => (
                <AgentBlock key={result.agent} result={result} />
              ))}
            </ul>

            <footer className="border-t border-[var(--line)] px-2 py-1.5">
              <p className="text-[9px] leading-snug text-[var(--text-3)]">{run.note}</p>
            </footer>
          </>
        ) : (
          <p className="px-3 py-4 text-[11px] leading-relaxed text-[var(--text-3)]">
            Ask a question and the orchestrator routes it to the specialists that can
            answer it. Every number in the answer comes from a tool in the trace, and
            every tool names the model that computed it. Agents cannot execute
            anything — a drafted advisory still has to be issued by a controller.
          </p>
        )}
      </div>
    </section>
  );
}
