import { createFileRoute } from "@tanstack/react-router";
import { useMemo, useState } from "react";

import { useFixes, useTrafficTick } from "@/components/app/traffic-context";
import { usePortContext } from "@/components/app/port-context";
import { AgentConsole } from "@/components/agent/AgentConsole";
import { MaritimeSearch, type SearchHit } from "@/components/command/MaritimeSearch";
import { PortSummary } from "@/components/command/PortCockpit";
import { TimeTransport } from "@/components/command/TimeTransport";
import {
  EnvironmentLegend,
  TrafficFilters,
  VesselClassLegend,
} from "@/components/command/TrafficFilters";
import {
  VesselHoverCard,
  VesselInspector,
  useRouteExposure,
} from "@/components/command/VesselInspector";
import { FloatPanel } from "@/components/command/panels";
import { selectionGeometry } from "@/components/command/selection-geometry";
import { useWorkspaceMap } from "@/components/command/useWorkspaceMap";
import { ScreenFallback } from "@/components/kit/states";
import { MaritimeMap } from "@/components/map/MaritimeMap";
import { portTraffic } from "@/lib/maritime/traffic-views";

export const Route = createFileRoute("/port/traffic")({ component: PortTraffic });

/**
 * The port's own traffic picture.
 *
 * The same chart as national command, with the camera on this facility and the
 * approach geometry drawn. A port controller wants the approaches, the
 * anchorage and the berths, not the whole coast.
 */
function PortTraffic() {
  const { port, portCode, query } = usePortContext();
  const workspace = useWorkspaceMap({ zonesFor: portCode, initialSelectedPort: portCode });
  const fixes = useFixes(1);
  const at = useTrafficTick(1);
  const [following, setFollowing] = useState(false);

  const selectedFix = useMemo(
    () => fixes.find((fix) => fix.id === workspace.selectedVesselId) ?? null,
    [fixes, workspace.selectedVesselId],
  );
  const exposure = useRouteExposure(selectedFix, workspace.timeline);
  const geometry = useMemo(
    () => selectionGeometry(selectedFix, exposure),
    [exposure, selectedFix],
  );

  const traffic = useMemo(() => {
    if (!port?.location) return null;
    return portTraffic(fixes, {
      code: port.code,
      lat: port.location.lat,
      lon: port.location.lon,
    });
  }, [fixes, port]);

  if (query.isLoading || query.isError || !port) {
    return (
      <ScreenFallback
        title="Traffic"
        context={<span>Approaches, anchorage and berths</span>}
        isLoading={query.isLoading}
        error={query.error}
        retry={() => void query.refetch()}
        label="Acquiring the port picture"
      />
    );
  }

  const onPick = (hit: SearchHit) => {
    if (hit.kind === "vessel") workspace.setSelectedVesselId(hit.id);
    else workspace.setSelectedPortCode(hit.id);
    workspace.flyTo([hit.lon, hit.lat], hit.kind === "vessel" ? 9 : 8);
  };

  return (
    <div className="absolute inset-0">
      <h1 className="sr-only">{port.name} traffic</h1>

      <MaritimeMap
        layers={workspace.layers}
        data={{ ...workspace.data, ...geometry }}
        weatherRaster={workspace.raster}
        windFrame={workspace.frame}
        showWind={workspace.showWind && workspace.layers.weather}
        vesselFilter={workspace.vesselFilter}
        labels={workspace.labels}
        selectedVesselId={workspace.selectedVesselId}
        onSelectVessel={(id) => {
          workspace.setSelectedVesselId(id);
          setFollowing(false);
        }}
        onHoverVessel={workspace.setHoveredVesselId}
        selectedPortCode={portCode}
        onSelectPort={workspace.setSelectedPortCode}
        view={
          port.location
            ? { center: [port.location.lon, port.location.lat], zoom: 8.2 }
            : undefined
        }
        focus={
          following && selectedFix
            ? {
                center: [selectedFix.lon, selectedFix.lat],
                zoom: 9.5,
                token: Math.floor(at / 4000),
              }
            : workspace.focus
        }
        renderHoverCard={(fix) => <VesselHoverCard fix={fix} />}
        overlay={
          <>
            <div className="pointer-events-none absolute left-2.5 top-2.5 z-20 flex max-h-[calc(100%-96px)] w-[216px] flex-col gap-2">
              <MaritimeSearch ports={workspace.ports} onPick={onPick} />
              <TrafficFilters workspace={workspace} />
            </div>

            <div className="pointer-events-none absolute bottom-2.5 left-2.5 z-20 flex w-[248px] flex-col gap-1.5">
              <VesselClassLegend />
              <EnvironmentLegend workspace={workspace} frame={workspace.frame} />
            </div>

            <div className="pointer-events-none absolute bottom-2.5 left-[272px] right-[352px] z-20">
              <TimeTransport timeline={workspace.timeline} weatherAt={workspace.weatherAt} />
            </div>

            <div className="pointer-events-none absolute bottom-2.5 right-2.5 top-2.5 z-20 flex w-[338px] flex-col gap-2">
              {selectedFix ? (
                <VesselInspector
                  fix={selectedFix}
                  ports={workspace.ports}
                  timeline={workspace.timeline}
                  onClose={() => {
                    workspace.setSelectedVesselId(null);
                    workspace.setIsolate(null);
                    setFollowing(false);
                  }}
                  onIsolate={() =>
                    workspace.setIsolate(workspace.filters.isolate ? null : selectedFix.id)
                  }
                  isolated={workspace.filters.isolate === selectedFix.id}
                  onFollow={() => setFollowing((v) => !v)}
                  following={following}
                  onSelectVessel={(id) => workspace.setSelectedVesselId(id)}
                  className="min-h-0 flex-1"
                />
              ) : traffic ? (
                <FloatPanel
                  title={port.name}
                  note={<span className="num">{port.code}</span>}
                  className="min-h-0 flex-1"
                >
                  <PortSummary port={port} traffic={traffic} />
                </FloatPanel>
              ) : null}
            </div>

            <div className="pointer-events-none absolute right-2.5 top-[calc(100%-46px)] z-30 -translate-y-full">
              <AgentConsole />
            </div>
          </>
        }
      />
    </div>
  );
}
