import { formatUtc } from "@/components/kit/primitives";
import {
  ageLabel,
  successLabel,
  useSourceHealth,
} from "@/services/source-health";

export function DataNowSources() {
  const { data, isError } = useSourceHealth();
  const sources = data?.sources ?? [];
  const activity = sources.find(({ id }) => id === "imf-portwatch-data");
  const live = sources.filter(({ status }) => status === "live").length;
  const stale = sources.filter(({ status }) => status === "stale").length;
  return (
    <>
      <div className="pt-1">
        <a href="/sources" className="underline underline-offset-2">
          Source health
        </a>
        {data
          ? ` · ${live} current · ${stale} stale · ${sources.length - live - stale} unavailable`
          : isError
            ? " · unavailable"
            : " · checking"}
        {activity?.dataAgeSeconds != null
          ? ` · IMF data ${ageLabel(activity.dataAgeSeconds)} old`
          : null}
      </div>
      {data ? (
        <details className="relative">
          <summary className="cursor-pointer">Recent source checks</summary>
          <ul className="absolute inset-x-0 top-full z-40 max-h-52 overflow-auto rounded border border-[var(--line)] bg-[var(--panel)] p-2 shadow-sm">
            {sources.map((source) => (
              <li
                key={source.id}
                className="border-b border-[var(--line)] py-1 last:border-b-0"
              >
                <strong>{source.name}</strong>
                <p>
                  Last success{" "}
                  {source.lastSuccess
                    ? formatUtc(source.lastSuccess)
                    : "Unmeasured"}
                </p>
                <p>
                  7-day success{" "}
                  {successLabel(source.successRate7d, source.attempts7d)} ·
                  median lag {ageLabel(source.medianLagSeconds)}
                </p>
              </li>
            ))}
          </ul>
        </details>
      ) : null}
    </>
  );
}

export function WeatherDataNow() {
  const { data } = useSourceHealth();
  const source = data?.sources.find((row) => row.id === "open-meteo-surface");
  if (source?.status === "live") return <>provider forecast · {source.portsCurrent}/{source.portsTotal} ports current</>;
  const at = source?.availableAt;
  return <span className="text-[var(--text-3)]" data-testid="weather-latest-available">
    {at ? `Latest available · ${formatUtc(at)} (${ageLabel(source.dataAgeSeconds)} old)` : "unavailable · no current snapshot"}
  </span>;
}

export function DatedSource({ id }: { id: string }) {
  const { data } = useSourceHealth();
  const source = data?.sources.find((row) => row.id === id);
  const at = source?.observedAt ?? source?.availableAt;
  return <span data-testid={`dated-source-${id}`} className={source?.status === "live" ? "" : "text-[var(--text-3)]"}>
    {source?.status === "live" ? "within policy" : at ? `Latest available · ${formatUtc(at)} (${ageLabel(source?.dataAgeSeconds)} old)` : "unavailable"}
  </span>;
}
