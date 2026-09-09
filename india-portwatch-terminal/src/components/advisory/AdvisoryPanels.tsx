/**
 * The advisory workflow, as an operator sees it.
 *
 * Two sides, one component set. A port controller reviews, modifies, issues or
 * rejects; a company or a master acknowledges, accepts, queries or declines. The
 * component does not decide which of those is offered -- the API does, in
 * `availableTransitions`, filtered by the acting principal's role. That matters:
 * if the button set were assembled here from a local role check, the two would
 * eventually disagree and the UI would offer an action the server refuses.
 *
 * Every action that changes state asks for a reason where the workflow requires
 * one, and the audit trail is shown in full rather than folded away. An advisory
 * whose history is hidden is one nobody can review afterwards, which for a port
 * authority is the difference between usable and not.
 */

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Check, ChevronDown, MessageSquare, Pencil, Send, X } from "lucide-react";
import { useState, type ReactNode } from "react";

import { Button } from "@/components/kit/layout";
import { Pill, formatUtc, type Tone } from "@/components/kit/primitives";
import { cn } from "@/lib/utils";
import { modifyAdvisory, transitionAdvisory } from "@/services/portwatch-os";
import type { Advisory, AdvisoryState } from "@/types/portwatch-os";

/* ------------------------------------------------------------------ tone -- */

const STATE_TONE: Record<AdvisoryState, Tone> = {
  draft: "neutral",
  under_review: "info",
  issued: "warn",
  acknowledged: "info",
  accepted: "ok",
  queried: "unc",
  declined: "crit",
  rejected: "crit",
  withdrawn: "neutral",
  expired: "neutral",
  completed: "ok",
};

const STATE_LABEL: Record<AdvisoryState, string> = {
  draft: "Draft",
  under_review: "Under review",
  issued: "Issued",
  acknowledged: "Acknowledged",
  accepted: "Accepted",
  queried: "Review requested",
  declined: "Declined",
  rejected: "Rejected",
  withdrawn: "Withdrawn",
  expired: "Expired",
  completed: "Completed",
};

export function advisoryTone(state: AdvisoryState): Tone {
  return STATE_TONE[state] ?? "neutral";
}

export function advisoryLabel(state: AdvisoryState): string {
  return STATE_LABEL[state] ?? state;
}

/* -------------------------------------------------------- recommendation -- */

/**
 * Render the recommendation payload.
 *
 * Deliberately generic: the shape depends on the advisory kind, and hardcoding
 * a renderer per kind would mean a new kind on the server renders as nothing
 * here. Keys are humanised and values printed as they came.
 */
export function RecommendationBody({
  recommendation,
  modifiedFrom,
}: {
  recommendation: Record<string, unknown>;
  modifiedFrom?: Record<string, unknown> | null;
}) {
  const keys = Object.keys(recommendation);
  if (!keys.length) {
    return (
      <p className="text-[10.5px] text-[var(--text-3)]">
        This advisory carries no recommendation payload.
      </p>
    );
  }
  return (
    <dl className="space-y-[3px]">
      {keys.map((key) => {
        const value = recommendation[key];
        const before = modifiedFrom?.[key];
        const changed = before !== undefined && before !== value;
        return (
          <div key={key} className="flex items-baseline justify-between gap-3">
            <dt className="text-[10.5px] text-[var(--text-3)]">{humanise(key)}</dt>
            <dd className="text-right text-[11px] text-[var(--text)]">
              {changed ? (
                <span className="num mr-1.5 text-[10px] text-[var(--text-3)] line-through">
                  {String(before)}
                </span>
              ) : null}
              <span className="num">{formatValue(value)}</span>
            </dd>
          </div>
        );
      })}
    </dl>
  );
}

function humanise(key: string): string {
  return key
    .replace(/([A-Z])/g, " $1")
    .replace(/^./, (c) => c.toUpperCase())
    .trim();
}

function formatValue(value: unknown): string {
  if (value == null) return "n/a";
  if (typeof value === "number") return value.toFixed(value % 1 === 0 ? 0 : 2);
  if (typeof value === "boolean") return value ? "yes" : "no";
  const text = String(value);
  // ISO instants are the common case in an arrival advisory; render them the
  // way every other timestamp in the product is rendered.
  return /^\d{4}-\d{2}-\d{2}T/.test(text) ? formatUtc(text) : text;
}

/* ----------------------------------------------------------------- audit -- */

export function AuditTrail({ advisory }: { advisory: Advisory }) {
  return (
    <ol className="space-y-1.5">
      {advisory.audit.map((entry, index) => (
        <li key={`${entry.at}-${index}`} className="relative pl-4">
          <span
            aria-hidden
            className="absolute left-[3px] top-[6px] h-[5px] w-[5px] rounded-full bg-[var(--line-strong)]"
          />
          {index < advisory.audit.length - 1 ? (
            <span
              aria-hidden
              className="absolute left-[5px] top-[12px] h-[calc(100%-6px)] w-px bg-[var(--line)]"
            />
          ) : null}
          <div className="flex items-baseline gap-2">
            <span className="text-[10.5px] text-[var(--text)]">{entry.action}</span>
            <span className="num ml-auto shrink-0 text-[9px] text-[var(--text-3)]">
              {formatUtc(entry.at)}
            </span>
          </div>
          <div className="mt-[1px] flex items-center gap-1.5 text-[9.5px] text-[var(--text-3)]">
            <span>{entry.actor}</span>
            <Pill tone={entry.actor_role === "system" ? "neutral" : "info"}>
              {entry.actor_role}
            </Pill>
            <span className="num">
              {entry.from_state} → {entry.to_state}
            </span>
          </div>
          {entry.reason ? (
            <p className="mt-[2px] text-[9.5px] leading-snug text-[var(--text-2)]">
              {entry.reason}
            </p>
          ) : null}
        </li>
      ))}
    </ol>
  );
}

/* --------------------------------------------------------------- actions -- */

const TONE_FOR_TARGET: Record<string, Tone> = {
  issued: "ok",
  accepted: "ok",
  completed: "ok",
  rejected: "crit",
  declined: "crit",
  withdrawn: "neutral",
  queried: "unc",
  under_review: "info",
  acknowledged: "info",
  draft: "neutral",
};

export function AdvisoryActions({
  advisory,
  headers,
  onDone,
}: {
  advisory: Advisory;
  headers: Record<string, string>;
  onDone?: (next: Advisory) => void;
}) {
  const queryClient = useQueryClient();
  const [pending, setPending] = useState<string | null>(null);
  const [reason, setReason] = useState("");
  const [error, setError] = useState<string | null>(null);

  const role = headers["X-PortWatch-Role"];
  // The server decides what this principal may do. We only filter to the side
  // of the workflow this identity sits on, so a controller is not shown the
  // recipient's buttons on a screen where both could theoretically render.
  const party =
    role === "PORT_AUTHORITY" || role === "NATIONAL_ADMIN" ? "issuer" : "recipient";
  const options = advisory.availableTransitions.filter(
    (t) => t.actorRole === party || (party === "issuer" && role === "NATIONAL_ADMIN"),
  );

  const mutation = useMutation({
    mutationFn: (input: { target: string; reason?: string }) =>
      transitionAdvisory(headers, advisory.advisoryId, input.target, input.reason),
    onSuccess: (next) => {
      setPending(null);
      setReason("");
      setError(null);
      void queryClient.invalidateQueries({ queryKey: ["advisories"] });
      onDone?.(next);
    },
    onError: (err: unknown) => {
      setError(err instanceof Error ? err.message : "The transition was refused.");
    },
  });

  if (!options.length) {
    return (
      <p className="text-[10px] leading-snug text-[var(--text-3)]">
        {advisory.isTerminal
          ? `This advisory is ${advisoryLabel(advisory.state).toLowerCase()} and takes no further action.`
          : "No action is available to you on this advisory in its current state."}
      </p>
    );
  }

  const active = options.find((t) => t.target === pending);

  return (
    <div className="space-y-1.5">
      <div className="flex flex-wrap gap-1.5">
        {options.map((option) => (
          <button
            key={option.target}
            type="button"
            data-testid={`advisory-action-${option.target}`}
            disabled={mutation.isPending}
            onClick={() => {
              setError(null);
              if (option.requiresReason) {
                setPending(pending === option.target ? null : option.target);
                return;
              }
              mutation.mutate({ target: option.target });
            }}
            className={cn(
              "inline-flex items-center gap-1 rounded-[2px] border px-1.5 py-[3px] text-[10.5px] transition-colors",
              "border-[var(--line-strong)] hover:bg-[var(--panel-3)]",
              pending === option.target && "bg-[var(--panel-3)]",
              mutation.isPending && "cursor-not-allowed opacity-50",
            )}
            style={{ color: `var(--${TONE_FOR_TARGET[option.target] ?? "text-2"})` }}
          >
            {ACTION_ICON[option.target] ?? null}
            {option.label}
          </button>
        ))}
      </div>

      {active ? (
        <div className="rounded-[2px] border border-[var(--line-strong)] bg-[var(--panel-2)] p-1.5">
          <label className="eyebrow block text-[8.5px]" htmlFor="advisory-reason">
            Reason — required for {active.label.toLowerCase()}
          </label>
          <textarea
            id="advisory-reason"
            data-testid="advisory-reason"
            rows={2}
            value={reason}
            onChange={(event) => setReason(event.target.value)}
            placeholder="What a reviewer reading this in a month needs to know."
            className="mt-1 w-full resize-none rounded-[2px] border border-[var(--line)] bg-[var(--panel)] px-1.5 py-1 text-[11px] text-[var(--text)] outline-none focus:border-[var(--info)]"
          />
          <div className="mt-1 flex items-center gap-1.5">
            <Button
              variant="default"
              disabled={reason.trim().length < 4 || mutation.isPending}
              onClick={() => mutation.mutate({ target: active.target, reason })}
            >
              Confirm {active.label.toLowerCase()}
            </Button>
            <Button variant="ghost" onClick={() => setPending(null)}>
              Cancel
            </Button>
          </div>
        </div>
      ) : null}

      {error ? (
        <p className="text-[10px] leading-snug text-[var(--crit)]">{error}</p>
      ) : null}
    </div>
  );
}

const ACTION_ICON: Record<string, ReactNode> = {
  issued: <Send size={9} />,
  accepted: <Check size={9} />,
  declined: <X size={9} />,
  rejected: <X size={9} />,
  queried: <MessageSquare size={9} />,
  under_review: <ChevronDown size={9} />,
};

/* ------------------------------------------------------------------ card -- */

export function AdvisoryCard({
  advisory,
  headers,
  expanded,
  onToggle,
}: {
  advisory: Advisory;
  headers: Record<string, string>;
  expanded?: boolean;
  onToggle?: () => void;
}) {
  return (
    <article
      data-testid="advisory-card"
      className="border-b border-[var(--line)] last:border-0"
    >
      <button
        type="button"
        onClick={onToggle}
        className="flex w-full items-start gap-2 px-2 py-1.5 text-left hover:bg-[var(--panel-2)]"
      >
        <div className="min-w-0 flex-1">
          <div className="flex items-baseline gap-2">
            <span className="truncate text-[11.5px] font-medium text-[var(--text)]">
              {advisory.kindLabel}
            </span>
            <Pill tone={advisoryTone(advisory.state)}>{advisoryLabel(advisory.state)}</Pill>
          </div>
          <div className="mt-[2px] flex flex-wrap items-center gap-x-2 gap-y-0.5 text-[9.5px] text-[var(--text-3)]">
            <span className="num">{advisory.portCode}</span>
            <span className="truncate">→ {advisory.recipientVesselName}</span>
            <span className="num">{formatUtc(advisory.createdAt)}</span>
            {advisory.modelConfidence != null ? (
              <span className="num">conf {advisory.modelConfidence.toFixed(2)}</span>
            ) : null}
            {advisory.criticVerdict ? (
              <Pill tone={advisory.criticVerdict === "APPROVED" ? "ok" : "unc"}>
                critic {advisory.criticVerdict.toLowerCase()}
              </Pill>
            ) : null}
          </div>
        </div>
        <ChevronDown
          size={12}
          className={cn(
            "mt-[3px] shrink-0 text-[var(--text-3)] transition-transform",
            expanded && "rotate-180",
          )}
        />
      </button>

      {expanded ? (
        <div className="space-y-2 border-t border-[var(--line)]/60 bg-[var(--panel-2)]/40 px-2 py-2">
          <section>
            <h4 className="eyebrow text-[8.5px]">Recommendation</h4>
            <div className="mt-1">
              <RecommendationBody
                recommendation={advisory.recommendation}
                modifiedFrom={advisory.modifiedFrom}
              />
            </div>
            {advisory.modifiedFrom ? (
              <p className="mt-1 text-[9.5px] leading-snug text-[var(--unc)]">
                A controller changed this before issuing it. The original is struck
                through above.
              </p>
            ) : null}
          </section>

          <section>
            <h4 className="eyebrow text-[8.5px]">Reason</h4>
            <p className="mt-1 text-[10.5px] leading-snug text-[var(--text-2)]">
              {advisory.reason}
            </p>
          </section>

          {Object.keys(advisory.evidence).length ? (
            <section>
              <h4 className="eyebrow text-[8.5px]">Evidence</h4>
              <div className="mt-1">
                <RecommendationBody recommendation={advisory.evidence} />
              </div>
            </section>
          ) : null}

          {advisory.criticReasons.length ? (
            <section>
              <h4 className="eyebrow text-[8.5px]">Critic</h4>
              <ul className="mt-1 space-y-0.5">
                {advisory.criticReasons.map((entry) => (
                  <li key={entry} className="text-[9.5px] leading-snug text-[var(--text-3)]">
                    {entry}
                  </li>
                ))}
              </ul>
            </section>
          ) : null}

          <section>
            <h4 className="eyebrow text-[8.5px]">Audit trail</h4>
            <div className="mt-1">
              <AuditTrail advisory={advisory} />
            </div>
          </section>

          <section>
            <h4 className="eyebrow text-[8.5px]">Action</h4>
            <div className="mt-1">
              <AdvisoryActions advisory={advisory} headers={headers} />
            </div>
          </section>
        </div>
      ) : null}
    </article>
  );
}

/* ------------------------------------------------------------- modify UI -- */

export function ModifyRecommendation({
  advisory,
  headers,
  onDone,
}: {
  advisory: Advisory;
  headers: Record<string, string>;
  onDone?: () => void;
}) {
  const queryClient = useQueryClient();
  const [values, setValues] = useState<Record<string, string>>(() =>
    Object.fromEntries(
      Object.entries(advisory.recommendation).map(([k, v]) => [k, String(v ?? "")]),
    ),
  );
  const [reason, setReason] = useState("");
  const [error, setError] = useState<string | null>(null);

  const mutation = useMutation({
    mutationFn: () =>
      modifyAdvisory(headers, advisory.advisoryId, values, reason),
    onSuccess: () => {
      setError(null);
      void queryClient.invalidateQueries({ queryKey: ["advisories"] });
      onDone?.();
    },
    onError: (err: unknown) =>
      setError(err instanceof Error ? err.message : "The edit was refused."),
  });

  return (
    <div className="space-y-1.5">
      {Object.keys(values).map((key) => (
        <label key={key} className="block">
          <span className="text-[9.5px] text-[var(--text-3)]">{humanise(key)}</span>
          <input
            value={values[key]}
            onChange={(event) =>
              setValues((prev) => ({ ...prev, [key]: event.target.value }))
            }
            className="mt-[2px] w-full rounded-[2px] border border-[var(--line)] bg-[var(--panel)] px-1.5 py-[3px] text-[11px] text-[var(--text)] outline-none focus:border-[var(--info)]"
          />
        </label>
      ))}
      <label className="block">
        <span className="text-[9.5px] text-[var(--text-3)]">
          Why the change — kept with the original for review
        </span>
        <input
          value={reason}
          onChange={(event) => setReason(event.target.value)}
          className="mt-[2px] w-full rounded-[2px] border border-[var(--line)] bg-[var(--panel)] px-1.5 py-[3px] text-[11px] text-[var(--text)] outline-none focus:border-[var(--info)]"
        />
      </label>
      <div className="flex items-center gap-1.5">
        <Button
          variant="default"
          disabled={reason.trim().length < 4 || mutation.isPending}
          onClick={() => mutation.mutate()}
        >
          <Pencil size={9} /> Save change
        </Button>
        <Button variant="ghost" onClick={onDone}>
          Cancel
        </Button>
      </div>
      {error ? <p className="text-[10px] text-[var(--crit)]">{error}</p> : null}
    </div>
  );
}
