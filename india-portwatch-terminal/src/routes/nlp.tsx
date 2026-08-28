import { createFileRoute } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { Panel, Chip, Bar } from "@/components/terminal/ui";
import { fetchNewsBundle, fetchNewsEventsForEntity } from "@/services/news";

export const Route = createFileRoute("/nlp")({
  validateSearch: (search: Record<string, unknown>) => ({
    entity: typeof search.entity === "string" ? search.entity : "HORMUZ",
  }),
  component: NlpPage,
});

function NlpPage() {
  const { entity } = Route.useSearch();
  const normalizedEntity = entity.toUpperCase();

  const focusedQuery = useQuery({
    queryKey: ["news-entity", normalizedEntity],
    queryFn: () => fetchNewsEventsForEntity(normalizedEntity),
    staleTime: 30_000,
  });

  const newsBundleQuery = useQuery({
    queryKey: ["news-bundle"],
    queryFn: fetchNewsBundle,
    staleTime: 30_000,
  });

  if (focusedQuery.isLoading || newsBundleQuery.isLoading) {
    return (
      <div className="h-full grid place-items-center text-[var(--color-cyan)] text-[12px] tracking-[0.2em]">
        LOADING BACKEND NLP FEED...
      </div>
    );
  }

  if (
    focusedQuery.isError ||
    newsBundleQuery.isError ||
    !focusedQuery.data ||
    !newsBundleQuery.data
  ) {
    return (
      <div className="h-full grid place-items-center text-[var(--color-red)] text-[12px] tracking-[0.2em]">
        NEWS API UNAVAILABLE
      </div>
    );
  }

  const events = newsBundleQuery.data.events ?? [];
  const entityEvents = focusedQuery.data ?? [];
  const focusedEvents = entityEvents.length
    ? entityEvents
    : events.filter(
        (event) =>
          event.entity.includes(normalizedEntity) ||
          event.tag.includes(normalizedEntity),
      );
  const feedEvents = focusedEvents.length
    ? [
        ...focusedEvents,
        ...events.filter((event) => !focusedEvents.includes(event)),
      ]
    : events;
  const entities = newsBundleQuery.data.sentiment ?? [];
  const alerts = newsBundleQuery.data.alerts ?? [];
  const summary = newsBundleQuery.data.summary ?? {};
  const sourceLabel =
    summary.dataSource ??
    events[0]?.dataSource ??
    "data/cache/news_bundle.json";

  const avgSentiment = events.length
    ? events.reduce((total, event) => total + Number(event.sentiment ?? 0), 0) /
      events.length
    : 0;

  const dominantEntities = entities
    .slice(0, 3)
    .map((entity) => entity.entity)
    .join(", ");

  const stopWords = new Set([
    "daily",
    "maritime",
    "news",
    "sentiment",
    "index",
    "rolling14",
    "affected",
    "ports",
    "selected",
    "from",
    "current",
    "risk",
    "ranking",
    "backend",
    "cache",
    "historical",
    "aggregate",
  ]);

  const derivedKeywords = Array.from(
    new Set(
      feedEvents.flatMap((event) =>
        `${event.tag} ${event.entity} ${event.text}`
          .toLowerCase()
          .split(/[^a-z0-9]+/)
          .filter((word) => word.length > 3 && !stopWords.has(word)),
      ),
    ),
  ).slice(0, 12);

  const keywordPulse = derivedKeywords.length
    ? derivedKeywords
    : ["no-keywords-from-backend"];

  const timelineSource = feedEvents.length ? feedEvents : events;
  const timelinePoints =
    timelineSource.length > 1
      ? timelineSource
          .slice(0, 24)
          .map((event, index, arr) => {
            const x = (index * 240) / Math.max(arr.length - 1, 1);
            const sentiment = Math.max(
              -1.5,
              Math.min(1.5, Number(event.sentiment ?? 0)),
            );
            const y = 40 - (sentiment / 1.5) * 28;
            return `${x},${y}`;
          })
          .join(" ")
      : "0,40 240,40";

  return (
    <div className="h-full grid grid-cols-[1.4fr_1fr_1fr] gap-2">
      <Panel
        title={`NLP FEED · ${normalizedEntity} · BACKEND NEWS CACHE`}
      >
        <div className="p-2 space-y-2">
          {feedEvents.map((n, i) => (
            <div key={`${n.id}-${i}`} className="panel p-2">
              <div className="flex items-center justify-between text-[9px] tracking-widest text-[var(--color-muted-foreground)]">
                <div className="flex items-center gap-2">
                  <span className="tabular-nums">{n.timestamp}Z</span>
                  <Chip
                    tone={
                      n.severity === "severe"
                        ? "red"
                        : n.severity === "elevated"
                          ? "amber"
                          : "amber"
                    }
                  >
                    {n.tag}
                  </Chip>
                  <span>{n.source}</span>
                </div>
                <span>
                  SENT {n.sentiment >= 0 ? "+" : ""}
                  {n.sentiment.toFixed(2)}
                </span>
              </div>
              <div className="text-[11px] text-[var(--color-foreground)] leading-snug mt-1">
                {n.text}
              </div>
            </div>
          ))}
        </div>
      </Panel>

      <div className="grid grid-rows-2 gap-2 min-h-0">
        <Panel title="ENTITY SALIENCE">
          <div className="p-3 space-y-1.5 text-[11px]">
            {entities.map((e) => (
              <div
                key={e.entity}
                className="grid grid-cols-[80px_1fr_46px] items-center gap-2"
              >
                <span className="text-[var(--color-cyan)]">{e.entity}</span>
                <Bar
                  value={e.mentions / 50}
                  tone={
                    e.sentiment < -0.2
                      ? "red"
                      : e.sentiment < 0
                        ? "amber"
                        : "mint"
                  }
                />
                <span
                  className={
                    "text-right tabular-nums " +
                    (e.sentiment < -0.2
                      ? "text-[var(--color-red)]"
                      : e.sentiment < 0
                        ? "text-[var(--color-amber)]"
                        : "text-[var(--color-mint)]")
                  }
                >
                  {e.sentiment >= 0 ? "+" : ""}
                  {e.sentiment.toFixed(2)}
                </span>
              </div>
            ))}
          </div>
        </Panel>
        <Panel title="BACKEND ENTITY LINKS">
          <div className="p-3 space-y-2 text-[10px]">
            {entities.length ? (
              entities.slice(0, 6).map((entity, index) => (
                <div
                  key={entity.entity}
                  className="panel px-2 py-1.5 flex items-center justify-between"
                >
                  <span className="text-[var(--color-cyan)]">
                    #{index + 1} {entity.entity}
                  </span>
                  <span className="tabular-nums text-[var(--color-muted-foreground)]">
                    {entity.mentions} mentions ·{" "}
                    {entity.sentiment >= 0 ? "+" : ""}
                    {entity.sentiment.toFixed(2)}
                  </span>
                </div>
              ))
            ) : (
              <div className="text-[var(--color-muted-foreground)]">
                No entity sentiment returned by backend.
              </div>
            )}
          </div>
        </Panel>
      </div>

      <div className="grid grid-rows-[auto_1fr_auto] gap-2 min-h-0">
        <Panel title="SENTIMENT TIMELINE · 24H">
          <div className="p-3">
            <svg viewBox="0 0 240 80" className="w-full h-24">
              <line
                x1="0"
                y1="40"
                x2="240"
                y2="40"
                stroke="var(--color-line-strong)"
                strokeDasharray="2 3"
              />
              <polyline
                points={timelinePoints}
                fill="none"
                stroke="var(--color-red)"
                strokeWidth="1.4"
              />
            </svg>
            <div className="flex justify-between text-[9px] text-[var(--color-muted-foreground)] tabular-nums">
              <span>-24h</span>
              <span>NOW</span>
            </div>
          </div>
        </Panel>
        <Panel title="BACKEND NLP CACHE · SUMMARY">
          <div className="p-3 text-[11px] leading-relaxed space-y-2">
            <p>
              Source:{" "}
              <span className="text-[var(--color-cyan)]">
                {sourceLabel}
              </span>
              .
            </p>
            <p>
              Loaded{" "}
              <span className="text-[var(--color-cyan)] tabular-nums">
                {events.length}
              </span>{" "}
              historical sentiment events and{" "}
              <span className="text-[var(--color-cyan)] tabular-nums">
                {alerts.length}
              </span>{" "}
              TFT-linked alerts from the backend cache.
            </p>
            <p>
              Dominant backend entities:{" "}
              <span className="text-[var(--color-amber)]">
                {dominantEntities || "none returned"}
              </span>
              .
            </p>
            <p>
              Mean displayed sentiment:{" "}
              <span
                className={
                  avgSentiment < -0.2
                    ? "text-[var(--color-red)]"
                    : avgSentiment < 0
                      ? "text-[var(--color-amber)]"
                      : "text-[var(--color-mint)]"
                }
              >
                {avgSentiment >= 0 ? "+" : ""}
                {avgSentiment.toFixed(2)}
              </span>
              . This page is showing backend cache signals, not live articles.
            </p>
          </div>
        </Panel>
        <Panel title="KEYWORD PULSE">
          <div className="p-3 flex flex-wrap gap-1.5 text-[10px]">
            {keywordPulse.map((k) => (
              <span
                key={k}
                className="border border-[var(--color-line-strong)] px-1.5 py-0.5 text-[var(--color-muted-foreground)]"
              >
                {k}
              </span>
            ))}
          </div>
        </Panel>
      </div>
    </div>
  );
}
