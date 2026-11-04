interface WorkflowRailProps {
  label: string;
  steps: ReadonlyArray<{ key: string; label: string }>;
  current: string | undefined;
  onStep: (key: string) => void;
}

export function WorkflowRail({
  label,
  steps,
  current,
  onStep,
}: WorkflowRailProps) {
  const reached = steps.findIndex((step) => step.key === current);
  return (
    <nav aria-label={label} className="pw-miniature-rail">
      <ol>
        {steps.map((step, index) => (
          <li key={step.key}>
            <button
              type="button"
              aria-current={step.key === current ? "step" : undefined}
              data-reached={index < reached}
              onClick={() => onStep(step.key)}
            >
              <span className="pw-miniature-track" aria-hidden="true" />
              <span className="pw-miniature-step-number" aria-hidden="true">
                {String(index + 1).padStart(2, "0")}
              </span>
              {step.label}
            </button>
          </li>
        ))}
      </ol>
    </nav>
  );
}

export function scrollToWorkflowStep(target: HTMLElement | null | undefined) {
  target?.scrollIntoView({
    block: "nearest",
    inline: "nearest",
    behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches
      ? "instant"
      : "smooth",
  });
}
