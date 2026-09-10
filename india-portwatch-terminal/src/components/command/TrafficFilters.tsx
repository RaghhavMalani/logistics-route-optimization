/**
 * The filter drawer and the environment legend.
 *
 * Two decisions worth naming. First, weather is not a variable the operator
 * picks before seeing any: the composite is on by default and the control is
 * ON/OFF, with the individual fields tucked behind "Field" for the times
 * somebody genuinely wants visibility rather than rain. Second, the drawer
 * folds to its header, because on a 1366 screen a permanent 200 px column of
 * checkboxes is a fifth of the chart.
 */

import { useState } from "react";

import type { LayerKey } from "@/components/map/basemap";
import { legendStops } from "@/components/map/weather-layers";
import {
  NAV_STATUS_LABEL,
  VESSEL_CLASSES,
  type NavStatus,
  type VesselClass,
} from "@/lib/maritime/traffic-types";
import {
  WEATHER_FIELD_LIST,
  type WeatherFieldKey,
  type WeatherFrame,
} from "@/lib/maritime/weather-model";
import { cn } from "@/lib/utils";
import { Pill } from "@/components/kit/primitives";
import { Chip, FloatPanel, PanelSection } from "./panels";
import type { WorkspaceMap } from "./useWorkspaceMap";

const LAYER_LABELS: Array<{ key: LayerKey; label: string }> = [
  { key: "traffic", label: "Vessel traffic" },
  { key: "vectors", label: "Velocity leaders" },
  { key: "routes", label: "Selected route" },
  { key: "tracks", label: "Past track" },
  { key: "ghosts", label: "Predicted positions" },
  { key: "weather", label: "Weather composite" },
  { key: "storms", label: "Storm cells" },
  { key: "corridors", label: "Shipping corridors" },
  { key: "zones", label: "Port approach" },
  { key: "ports", label: "Ports" },
  { key: "chokepoints", label: "Chokepoints" },
  { key: "graticule", label: "Graticule" },
];

export function TrafficFilters({
  workspace,
  className,
  defaultOpen = false,
}: {
  workspace: WorkspaceMap;
  className?: string;
  defaultOpen?: boolean;
}) {
  const [showFields, setShowFields] = useState(false);

  return (
    <FloatPanel
      title="Layers and filters"
      note={workspace.filterActive ? <Pill tone="warn">filtered</Pill> : undefined}
      collapsible
      defaultOpen={defaultOpen}
      width={216}
      className={cn("max-h-[calc(100%-16px)]", className)}
    >
      <PanelSection
        title="Vessel class"
        right={
          <button
            type="button"
            onClick={workspace.resetFilters}
            className="text-[9.5px] hover:text-[var(--text)]"
          >
            reset
          </button>
        }
      >
        <div className="flex flex-wrap gap-1">
          {Object.values(VESSEL_CLASSES).map((spec) => (
            <Chip
              key={spec.key}
              color={spec.color}
              active={workspace.filters.classes.has(spec.key as VesselClass)}
              onClick={() => workspace.toggleClass(spec.key as VesselClass)}
            >
              {spec.label}
            </Chip>
          ))}
        </div>
      </PanelSection>

      <PanelSection title="Navigation status">
        <div className="flex flex-wrap gap-1">
          {(Object.keys(NAV_STATUS_LABEL) as NavStatus[]).map((status) => (
            <Chip
              key={status}
              active={workspace.filters.statuses.has(status)}
              onClick={() => workspace.toggleStatus(status)}
            >
              {NAV_STATUS_LABEL[status]}
            </Chip>
          ))}
        </div>
      </PanelSection>

      <PanelSection
        title="Environment"
        right={
          <button
            type="button"
            onClick={() => setShowFields((v) => !v)}
            className="text-[9.5px] hover:text-[var(--text)]"
          >
            {showFields ? "hide fields" : "field"}
          </button>
        }
      >
        <div className="flex flex-wrap gap-1">
          <Chip
            active={workspace.layers.weather}
            onClick={() => workspace.toggleLayer("weather")}
          >
            Weather
          </Chip>
          <Chip active={workspace.showWind} onClick={() => workspace.setShowWind(!workspace.showWind)}>
            Wind flow
          </Chip>
          <Chip active={workspace.layers.storms} onClick={() => workspace.toggleLayer("storms")}>
            Storm cells
          </Chip>
        </div>

        {showFields ? (
          <div className="mt-1.5 flex flex-wrap gap-1 border-t border-[var(--line)]/60 pt-1.5">
            {/* The composite is the default and the first chip, so isolating a
                single field reads as narrowing rather than as the normal way to
                use the layer. */}
            <Chip
              active={workspace.weatherField === null}
              onClick={() => workspace.setWeatherField(null)}
              title="Rain, wind and severe cells together"
            >
              Composite
            </Chip>
            {WEATHER_FIELD_LIST.map((spec) => (
              <Chip
                key={spec.key}
                active={workspace.weatherField === spec.key}
                onClick={() => workspace.setWeatherField(spec.key as WeatherFieldKey)}
              >
                {spec.label}
              </Chip>
            ))}
            <span className="mt-1 block w-full text-[9.5px] leading-snug text-[var(--text-3)]">
              Significant wave height is <span className="text-[var(--crit)]">UNAVAILABLE</span>:
              the marine feed returned no wave data in this run.
            </span>
          </div>
        ) : null}
      </PanelSection>

      <PanelSection title="Layers">
        <div className="flex flex-wrap gap-1">
          {LAYER_LABELS.map((layer) => (
            <Chip
              key={layer.key}
              active={workspace.layers[layer.key]}
              onClick={() => workspace.toggleLayer(layer.key)}
            >
              {layer.label}
            </Chip>
          ))}
        </div>
      </PanelSection>
    </FloatPanel>
  );
}

/* --------------------------------------------------------------- legend -- */

export function EnvironmentLegend({
  workspace,
  frame,
  className,
}: {
  workspace: WorkspaceMap;
  frame: WeatherFrame;
  className?: string;
}) {
  const composite = workspace.weatherField === null;
  const spec = composite
    ? null
    : (WEATHER_FIELD_LIST.find((field) => field.key === workspace.weatherField) ?? null);
  const stops = legendStops(composite ? "precipitation" : workspace.weatherField!);
  const raster = workspace.raster;
  const covered = raster?.covered ?? 0;
  const peaks = raster?.peaks;
  const storms = workspace.storms.cells.length;

  return (
    <div
      className={cn(
        "pointer-events-auto rounded-[3px] border border-[var(--line-strong)] bg-[var(--panel)]/95",
        "px-2 py-1.5 backdrop-blur-[3px]",
        className,
      )}
      data-testid="environment-legend"
    >
      <div className="flex items-baseline gap-2">
        <span className="eyebrow text-[9px]">
          {composite ? "Environment" : spec?.label}
        </span>
        <span className="num text-[9.5px] text-[var(--text-3)]">
          {composite ? "rain · wind · severe" : spec?.unit}
        </span>
        {frame.derived ? (
          <Pill
            tone="unc"
            title="Scaled from the daily weather-impact forecast and interpolated between forecast days."
          >
            derived
          </Pill>
        ) : (
          <Pill tone="ok">observed</Pill>
        )}
      </div>

      <div className="mt-1 flex items-center">
        {stops.map((stop) => (
          <span key={stop.label} className="flex-1">
            <span className="block h-[6px] w-full" style={{ background: stop.color }} />
            <span className="num mt-[2px] block text-center text-[8.5px] text-[var(--text-3)]">
              {stop.label}
            </span>
          </span>
        ))}
      </div>

      {/* The composite carries three fields at once, so the legend has to say
          what the peak of each currently is -- otherwise a reader cannot tell
          whether a hot cell is rain, wind or a severe flag. */}
      {composite && peaks ? (
        <div className="mt-1.5 grid grid-cols-3 gap-1.5 border-t border-[var(--line)]/60 pt-1.5">
          {(
            [
              ["Rain", peaks.rainMm, "mm"],
              ["Wind", peaks.windKn, "kn"],
              ["Severe", peaks.stormRisk, "idx"],
            ] as Array<[string, number | null, string]>
          ).map(([label, value, unit]) => (
            <div key={label}>
              <div className="text-[8.5px] uppercase tracking-[0.06em] text-[var(--text-3)]">
                peak {label}
              </div>
              <div className="num text-[11px] leading-none text-[var(--text)]">
                {value == null ? "—" : value.toFixed(value < 1 ? 3 : 1)}
                <span className="ml-0.5 text-[8.5px] text-[var(--text-3)]">{unit}</span>
              </div>
            </div>
          ))}
        </div>
      ) : null}

      <div className="mt-1 flex flex-wrap items-center gap-x-2.5 gap-y-0.5 border-t border-[var(--line)]/60 pt-1 text-[9px] text-[var(--text-3)]">
        <span className="flex items-center gap-1">
          <span className="h-[2px] w-4 rounded-full bg-[#8fd0ef]" />
          Wind flow
          <span className="text-[var(--unc)]">modelled dir.</span>
        </span>
        <span className="flex items-center gap-1">
          <span className="h-[7px] w-[7px] rounded-full border border-[#d05a4c]" />
          Storm cell
          {storms ? <span className="num">{storms}</span> : null}
        </span>
        <span className="num">{covered} stations</span>
      </div>
    </div>
  );
}

/** The class key, so a reader can decode the colours on the chart. */
export function VesselClassLegend({ className }: { className?: string }) {
  return (
    <div
      className={cn(
        "pointer-events-auto flex flex-wrap items-center gap-x-2.5 gap-y-1 rounded-[3px]",
        "border border-[var(--line-strong)] bg-[var(--panel)]/95 px-2 py-1 backdrop-blur-[3px]",
        className,
      )}
    >
      {Object.values(VESSEL_CLASSES).map((spec) => (
        <span key={spec.key} className="flex items-center gap-1 text-[9.5px] text-[var(--text-3)]">
          <span
            aria-hidden
            className="h-[8px] w-[8px] rounded-[1px]"
            style={{ background: spec.color }}
          />
          {spec.label}
        </span>
      ))}
      <span className="ml-1 flex items-center gap-1 border-l border-[var(--line)] pl-2 text-[9.5px] text-[var(--text-3)]">
        <span aria-hidden className="h-0 w-0 border-x-[4px] border-b-[7px] border-x-transparent border-b-[#93a7b8]" />
        under way
        <span aria-hidden className="ml-1 h-[8px] w-[8px] rounded-full border border-[#93a7b8]" />
        stopped
      </span>
    </div>
  );
}
