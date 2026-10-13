import { Link } from "@tanstack/react-router";
import type { ReactNode } from "react";
import "./public.css";
import { fmt } from "./format";

export function PublicShell({
  section,
  children,
}: {
  section: "explore" | "research";
  children: ReactNode;
}) {
  return (
    <div className="public-app">
      <a className="public-skip" href="#public-content">
        Skip to content
      </a>
      <header className="public-header">
        <Link to="/explore" className="public-brand">
          <span className="public-mark" aria-hidden="true">
            ↗
          </span>{" "}
          PortWatch <small>Shipping intelligence</small>
        </Link>
        <nav aria-label="Public navigation">
          <Link
            to="/explore"
            aria-current={section === "explore" ? "page" : undefined}
          >
            Explore
          </Link>
          <Link
            to="/research"
            aria-current={section === "research" ? "page" : undefined}
          >
            Research results
          </Link>
          <Link to="/login" className="public-signin">
            Operator sign-in ↗
          </Link>
        </nav>
      </header>
      <main id="public-content" className="public-content">
        {children}
      </main>
      <footer className="public-footer">
        <span>
          Public evidence. Explicit assumptions. Reproducible results.
        </span>
        <Link to={section === "explore" ? "/research" : "/explore"}>
          {section === "explore"
            ? "Examine the research →"
            : "Back to exploration →"}
        </Link>
      </footer>
    </div>
  );
}
export function DataState({
  error,
  pending,
  onRetry,
}: {
  error?: Error | null;
  pending?: boolean;
  onRetry: () => void;
}) {
  return (
    <section className="public-data-state" role={error ? "alert" : "status"}>
      <h2>
        {pending
          ? "Loading published evidence"
          : "Evidence service unavailable"}
      </h2>
      <p>
        {pending
          ? "Connecting to the public data service."
          : "The public data service could not provide this view. Try again shortly."}
      </p>
      {error && (
        <button type="button" onClick={onRetry}>
          Retry loading
        </button>
      )}
    </section>
  );
}
export function LinePlot({
  lines,
  labels,
  title,
  max = 100,
  band,
}: {
  lines: { name: string; values: (number | null)[]; color: string }[];
  labels: string[];
  title: string;
  max?: number;
  band?: { name: string; low: (number | null)[]; high: (number | null)[] };
}) {
  const x = (i: number) => 54 + (i * 650) / Math.max(1, labels.length - 1),
    y = (v: number) => 216 - (v * 176) / max;
  const segments: number[][] = [];
  band?.low.forEach((low, i) => {
    if (low == null || band.high[i] == null) return;
    if (i === 0 || band.low[i - 1] == null || band.high[i - 1] == null)
      segments.push([]);
    segments[segments.length - 1].push(i);
  });
  return (
    <figure className="public-plot">
      <svg viewBox="0 0 740 270" role="img" aria-label={title}>
        <title>{title}</title>
        {[0, 0.25, 0.5, 0.75, 1].map((n) => (
          <g key={n}>
            <line
              x1="54"
              x2="704"
              y1={y(n * max)}
              y2={y(n * max)}
              stroke="#dbe3df"
            />
            <text x="44" y={y(n * max) + 4} textAnchor="end">
              {fmt(n * max, 0)}
            </text>
          </g>
        ))}
        {band &&
          segments.map((indices, i) => (
            <path
              key={i}
              fill="#235d50"
              fillOpacity="0.12"
              d={`M${indices.map((n) => `${x(n)},${y(band.high[n]!)}`).join(" L")} L${[
                ...indices,
              ]
                .reverse()
                .map((n) => `${x(n)},${y(band.low[n]!)}`)
                .join(" L")} Z`}
            />
          ))}
        {lines.map((l) => (
          <path
            key={l.name}
            stroke={l.color}
            fill="none"
            strokeWidth="2.5"
            d={l.values
              .map((v, i) =>
                v == null
                  ? ""
                  : `${i === 0 || l.values[i - 1] == null ? "M" : "L"}${x(i)},${y(v)}`,
              )
              .join(" ")}
          />
        ))}
        {labels.map(
          (l, i) =>
            (i === 0 ||
              i === labels.length - 1 ||
              i % Math.max(1, Math.ceil(labels.length / 5)) === 0) && (
              <text key={i} x={x(i)} y="244" textAnchor="middle">
                {l}
              </text>
            ),
        )}
      </svg>
      <figcaption>
        {band && (
          <span>
            <i style={{ background: "#aac5b8" }} />
            {band.name}
          </span>
        )}
        {lines.map((l) => (
          <span key={l.name}>
            <i style={{ background: l.color }} />
            {l.name}
          </span>
        ))}
      </figcaption>
    </figure>
  );
}
