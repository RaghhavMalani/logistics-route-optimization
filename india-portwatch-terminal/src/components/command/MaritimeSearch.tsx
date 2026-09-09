/**
 * Global maritime search.
 *
 * One field over three namespaces -- vessels, ports, chokepoints -- because an
 * operator looking for "MSC" or "Chennai" or "Hormuz" does not want to decide
 * which index to consult first. Selecting a result flies the chart to it and
 * opens the inspector, which is the only useful definition of "found" on a map.
 */

import { Search, X } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";

import { useTraffic } from "@/components/app/traffic-context";
import { CHOKEPOINTS } from "@/lib/maritime/chokepoints";
import { VESSEL_CLASSES } from "@/lib/maritime/traffic-types";
import { cn } from "@/lib/utils";
import type { PortSnapshot } from "@/types/portwatch";

export interface SearchHit {
  kind: "vessel" | "port" | "chokepoint";
  id: string;
  title: string;
  subtitle: string;
  lon: number;
  lat: number;
}

export function MaritimeSearch({
  ports,
  onPick,
  className,
  placeholder = "Search vessel, port or chokepoint",
}: {
  ports: PortSnapshot[];
  onPick: (hit: SearchHit) => void;
  className?: string;
  placeholder?: string;
}) {
  const { source, clock, fixAt } = useTraffic();
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const boxRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!open) return undefined;
    const onDown = (event: MouseEvent) => {
      if (boxRef.current && !boxRef.current.contains(event.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", onDown);
    return () => document.removeEventListener("mousedown", onDown);
  }, [open]);

  const hits = useMemo<SearchHit[]>(() => {
    const term = query.trim().toLowerCase();
    if (term.length < 2) return [];

    const out: SearchHit[] = [];

    for (const port of ports) {
      if (
        port.name.toLowerCase().includes(term) ||
        port.code.toLowerCase().includes(term) ||
        port.short.toLowerCase().includes(term)
      ) {
        if (!port.location) continue;
        out.push({
          kind: "port",
          id: port.code,
          title: port.name,
          subtitle: `${port.code} · ${port.risk} · wait ${(port.delayHours ?? 0).toFixed(1)}h`,
          lon: port.location.lon,
          lat: port.location.lat,
        });
      }
    }

    for (const choke of CHOKEPOINTS) {
      if (choke.name.toLowerCase().includes(term) || choke.code.toLowerCase().includes(term)) {
        out.push({
          kind: "chokepoint",
          id: choke.code,
          title: choke.name,
          subtitle: "Chokepoint",
          lon: choke.lon,
          lat: choke.lat,
        });
      }
    }

    // The roster is static particulars; a position is only resolved for the
    // handful of names that actually match.
    const at = clock.now();
    for (const vessel of source.roster()) {
      if (out.length > 40) break;
      if (
        !vessel.name.toLowerCase().includes(term) &&
        !vessel.replayId.toLowerCase().includes(term) &&
        !vessel.operator.toLowerCase().includes(term)
      ) {
        continue;
      }
      const fix = fixAt(vessel.id, at);
      if (!fix) continue;
      out.push({
        kind: "vessel",
        id: vessel.id,
        title: vessel.name,
        subtitle: `${VESSEL_CLASSES[vessel.vesselClass].label} · ${fix.sogKn.toFixed(1)} kn · ${fix.status}`,
        lon: fix.lon,
        lat: fix.lat,
      });
    }

    const rank = (hit: SearchHit) => {
      const title = hit.title.toLowerCase();
      return (title.startsWith(term) ? 0 : 1) + (hit.kind === "port" ? 0 : 0.5);
    };
    return out.sort((a, b) => rank(a) - rank(b)).slice(0, 12);
  }, [clock, fixAt, ports, query, source]);

  const choose = (hit: SearchHit) => {
    onPick(hit);
    setOpen(false);
    setQuery("");
  };

  return (
    <div ref={boxRef} className={cn("pointer-events-auto relative", className)}>
      <div
        className={cn(
          "flex items-center gap-1.5 rounded-[3px] border border-[var(--line-strong)]",
          "bg-[var(--panel)]/95 px-2 py-[4px] backdrop-blur-[3px]",
        )}
      >
        <Search size={12} className="shrink-0 text-[var(--text-3)]" />
        <input
          value={query}
          onChange={(event) => {
            setQuery(event.target.value);
            setOpen(true);
            setActive(0);
          }}
          onFocus={() => setOpen(true)}
          onKeyDown={(event) => {
            if (event.key === "ArrowDown") {
              event.preventDefault();
              setActive((i) => Math.min(i + 1, hits.length - 1));
            } else if (event.key === "ArrowUp") {
              event.preventDefault();
              setActive((i) => Math.max(i - 1, 0));
            } else if (event.key === "Enter" && hits[active]) {
              choose(hits[active]);
            } else if (event.key === "Escape") {
              setOpen(false);
            }
          }}
          type="search"
          aria-label="Search vessels, ports and chokepoints"
          placeholder={placeholder}
          className="w-full bg-transparent text-[11.5px] text-[var(--text)] outline-none placeholder:text-[var(--text-3)]"
        />
        {query ? (
          <button
            type="button"
            aria-label="Clear search"
            onClick={() => {
              setQuery("");
              setOpen(false);
            }}
            className="shrink-0 text-[var(--text-3)] hover:text-[var(--text)]"
          >
            <X size={11} />
          </button>
        ) : null}
      </div>

      {open && query.trim().length >= 2 ? (
        <div
          role="listbox"
          className={cn(
            "pw-fade absolute left-0 right-0 top-[calc(100%+4px)] z-40 max-h-[300px] overflow-y-auto",
            "rounded-[3px] border border-[var(--line-strong)] bg-[var(--panel)] shadow-[0_12px_32px_rgba(0,0,0,0.55)]",
          )}
        >
          {hits.length === 0 ? (
            <p className="px-2.5 py-2 text-[11px] text-[var(--text-3)]">
              Nothing matches “{query.trim()}”.
            </p>
          ) : (
            hits.map((hit, index) => (
              <button
                key={`${hit.kind}:${hit.id}`}
                type="button"
                role="option"
                aria-selected={index === active}
                onMouseEnter={() => setActive(index)}
                onClick={() => choose(hit)}
                className={cn(
                  "flex w-full items-center gap-2 px-2.5 py-[5px] text-left transition-colors",
                  index === active ? "bg-[var(--panel-3)]" : "hover:bg-[var(--panel-2)]",
                )}
              >
                <span
                  className={cn(
                    "shrink-0 rounded-[2px] px-1 py-[1px] text-[8.5px] font-semibold uppercase tracking-[0.08em]",
                    hit.kind === "vessel"
                      ? "bg-[var(--info-dim)] text-[var(--info)]"
                      : hit.kind === "port"
                        ? "bg-[var(--ok-dim)] text-[var(--ok)]"
                        : "bg-[var(--unc-dim)] text-[var(--unc)]",
                  )}
                >
                  {hit.kind}
                </span>
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-[12px] text-[var(--text)]">{hit.title}</span>
                  <span className="block truncate text-[10px] text-[var(--text-3)]">
                    {hit.subtitle}
                  </span>
                </span>
              </button>
            ))
          )}
        </div>
      ) : null}
    </div>
  );
}
