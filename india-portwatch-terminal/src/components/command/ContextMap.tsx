/**
 * The chart, as a panel on a screen that is mostly not a chart.
 *
 * The three command workspaces are map-first and build their own overlays.
 * Everything else -- event intelligence, the scenario room, the weather desk --
 * wants the same chart with the same traffic and the same environment, in a
 * bounded box, without repeating two hundred lines of overlay plumbing. This is
 * that: one map, a compact legend, and whatever extra geometry the screen has.
 */

import type { ReactNode } from "react";

import { VesselHoverCard } from "@/components/command/VesselInspector";
import { EnvironmentLegend } from "@/components/command/TrafficFilters";
import { MaritimeMap, type MapView } from "@/components/map/MaritimeMap";
import type { RuntimeSource } from "@/components/map/basemap";
import { cn } from "@/lib/utils";
import type { WorkspaceMap } from "./useWorkspaceMap";

export function ContextMap({
  workspace,
  extraData,
  view,
  showTraffic = true,
  showLegend = true,
  overlay,
  note,
  className,
}: {
  workspace: WorkspaceMap;
  extraData?: Partial<Record<RuntimeSource, GeoJSON.FeatureCollection>>;
  view?: MapView;
  showTraffic?: boolean;
  showLegend?: boolean;
  overlay?: ReactNode;
  note?: ReactNode;
  className?: string;
}) {
  return (
    <div className={cn("relative h-full w-full", className)}>
      <MaritimeMap
        layers={{ ...workspace.layers, traffic: showTraffic && workspace.layers.traffic }}
        data={{ ...workspace.data, ...extraData }}
        weatherRaster={workspace.raster}
        windFrame={workspace.frame}
        showWind={workspace.showWind && workspace.layers.weather}
        vesselFilter={workspace.vesselFilter}
        labels={workspace.labels}
        view={view}
        focus={workspace.focus}
        selectedVesselId={workspace.selectedVesselId}
        onSelectVessel={workspace.setSelectedVesselId}
        onHoverVessel={workspace.setHoveredVesselId}
        selectedPortCode={workspace.selectedPortCode}
        onSelectPort={workspace.setSelectedPortCode}
        renderHoverCard={(fix) => <VesselHoverCard fix={fix} />}
        overlay={
          <>
            {showLegend ? (
              <div className="pointer-events-none absolute bottom-2.5 left-2.5 z-20 w-[248px]">
                <EnvironmentLegend workspace={workspace} frame={workspace.frame} />
              </div>
            ) : null}
            {note ? (
              <div className="pointer-events-none absolute left-2.5 top-2.5 z-20 max-w-[300px] rounded-[3px] border border-[var(--line-strong)] bg-[var(--panel)]/95 px-2 py-1 text-[9.5px] leading-snug text-[var(--text-3)]">
                {note}
              </div>
            ) : null}
            {overlay}
          </>
        }
      />
    </div>
  );
}
