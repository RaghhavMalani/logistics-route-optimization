import modelStatus from "@/data/model-status.json";

export function ModelStatus() {
  return (
    <section
      aria-labelledby="model-status"
      className="my-5 rounded border border-[var(--line)] bg-[var(--panel)] p-4"
    >
      <h2 id="model-status" className="text-lg font-semibold">
        Model status
      </h2>
      <dl className="mt-2 grid gap-x-4 sm:grid-cols-2">
        {modelStatus.map(({ component, status, basis }) => (
          <div
            key={component}
            className="border-t border-[var(--line)] py-2 text-sm"
          >
            <dt className="font-semibold">{component}</dt>
            <dd>{status}</dd>
            {basis ? (
              <dd className="text-xs text-[var(--text-3)]">{basis}</dd>
            ) : null}
          </div>
        ))}
      </dl>
    </section>
  );
}
