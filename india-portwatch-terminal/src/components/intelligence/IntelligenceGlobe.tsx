import { useEffect, useRef, useState } from "react";
import * as Cesium from "cesium";
import "cesium/Build/Cesium/Widgets/widgets.css";
import { createApplication } from "gods-eye-view/application";
import {
  createApplicationViewer,
  installTrackpadPinchZoom,
} from "gods-eye-view/application/viewer";
import {
  createEarthquakesLayer,
  createUsgsEarthquakeSource,
} from "gods-eye-view/layers/earthquakes";
import { API_BASE } from "@/services/api";
import { routeHeading } from "./globe-geometry";
import { GeographicMap } from "./GeographicMap";
import "./intelligence.css";

export interface GlobeContext {
  ports: {
    code: string;
    name: string;
    location: { lat: number; lon: number };
  }[];
  news: {
    events: {
      eventId: string;
      title: string;
      coordinates: { lat: number; lon: number } | null;
    }[];
  };
  cameras: {
    id: string;
    name: string;
    portCode: string;
    lat: number;
    lon: number;
  }[];
}
export interface GlobeRoute {
  id: string;
  name: string;
  positions: number[][];
  selected?: boolean;
  rejected?: boolean;
}
export interface GlobeVessel {
  id: string;
  name: string;
  lat: number;
  lon: number;
  heading?: number;
}
export interface GlobeMarker {
  id: string;
  name: string;
  lat: number;
  lon: number;
  kind: "weather" | "chokepoint";
  portCode?: string;
}
const NO_ROUTES: GlobeRoute[] = [],
  NO_VESSELS: GlobeVessel[] = [],
  NO_MARKERS: GlobeMarker[] = [],
  NO_PORTS: string[] = [];
const color = (value: string) => Cesium.Color.fromCssColorString(value);
const glyph = (shape: string, fill: string) =>
  "data:image/svg+xml;charset=utf-8," +
  encodeURIComponent(
    `<svg xmlns="http://www.w3.org/2000/svg" width="28" height="32" viewBox="0 0 28 32"><path d="${shape}" fill="${fill}" stroke="#071923" stroke-width="2"/></svg>`,
  );

export default function IntelligenceGlobe({
  context,
  portCode,
  eventId,
  earthquakes,
  headers,
  onPort,
  onEvent,
  onVessel,
  routes = NO_ROUTES,
  vessels = NO_VESSELS,
  markers = NO_MARKERS,
  affectedPorts = NO_PORTS,
  focus,
  resetToken,
  selectedVesselId,
  fitSelectionKey,
}: {
  context: GlobeContext;
  portCode: string | null;
  eventId: string | null;
  earthquakes: boolean;
  headers: Record<string, string>;
  onPort(code: string): void;
  onEvent(id: string): void;
  onVessel?(id: string): void;
  routes?: GlobeRoute[];
  vessels?: GlobeVessel[];
  markers?: GlobeMarker[];
  affectedPorts?: string[];
  focus?: { lat: number; lon: number } | null;
  resetToken?: number;
  selectedVesselId?: string | null;
  fitSelectionKey?: string;
}) {
  const host = useRef<HTMLDivElement>(null),
    credits = useRef<HTMLDivElement>(null),
    viewerRef = useRef<Cesium.Viewer | null>(null);
  const quakeRef = useRef<ReturnType<typeof createEarthquakesLayer> | null>(
    null,
  );
  const [ready, setReady] = useState(false),
    [tilesReady, setTilesReady] = useState(false),
    [failure, setFailure] = useState<string | null>(null);
  const [lens, setLens] = useState<"globe" | "map">("globe"),
    [imagery, setImagery] = useState(false),
    [imageryStatus, setImageryStatus] = useState(
      "Nautical context · Natural Earth",
    );
  const [fitCount, setFitCount] = useState(0),
    [follow, setFollow] = useState(false),
    [quakeStatus, setQuakeStatus] = useState("");
  const latest = useRef({
    context,
    routes,
    vessels,
    focus,
    portCode,
    eventId,
    onPort,
    onEvent,
    onVessel,
    headers,
  });
  latest.current = {
    context,
    routes,
    vessels,
    focus,
    portCode,
    eventId,
    onPort,
    onEvent,
    onVessel,
    headers,
  };
  const fitKey = `${fitSelectionKey ?? selectedVesselId ?? eventId ?? portCode ?? "world"}:${resetToken ?? 0}:${fitCount}`;
  useEffect(() => {
    const viewer = viewerRef.current;
    if (ready && viewer && !viewer.isDestroyed())
      viewer.useDefaultRenderLoop = lens === "globe";
  }, [lens, ready]);
  useEffect(() => {
    if (!host.current || !credits.current) return;
    let disposed = false;
    let viewer: Cesium.Viewer;
    const app = createApplication({
      async createScene({ defer, signal }) {
        viewer = createApplicationViewer({
          container: host.current!,
          creditContainer: credits.current!,
        });
        viewerRef.current = viewer;
        const recoverRenderer = (error: unknown) => {
          viewer.useDefaultRenderLoop = false;
          if (!disposed) {
            setFailure(
              error instanceof Error ? error.message : "Renderer unavailable",
            );
            setLens("map");
          }
        };
        // Widget resize/data-source failures happen outside Scene.renderError.
        // Replace this viewer's public error-panel hook, not the global prototype,
        // so every render-loop failure enters our usable geographic fallback.
        const widget = viewer.cesiumWidget;
        const originalErrorPanel = widget.showErrorPanel;
        widget.showErrorPanel = (_title, _message, error) =>
          recoverRenderer(error);
        defer(() => {
          widget.showErrorPanel = originalErrorPanel;
        });
        defer(() => {
          viewerRef.current = null;
          if (!viewer.isDestroyed()) viewer.destroy();
        });
        if (viewer.scene.skyBox) viewer.scene.skyBox.show = false;
        if (viewer.scene.sun) viewer.scene.sun.show = false;
        if (viewer.scene.moon) viewer.scene.moon.show = false;
        if (viewer.scene.skyAtmosphere) viewer.scene.skyAtmosphere.show = false;
        viewer.scene.globe.show = true;
        viewer.scene.globe.enableLighting = false;
        viewer.scene.globe.showGroundAtmosphere = false;
        viewer.scene.globe.baseColor = color("#071923");
        viewer.scene.backgroundColor = color("#07131c");
        viewer.scene.requestRenderMode = true;
        viewer.targetFrameRate = 30;
        defer(
          viewer.scene.renderError.addEventListener(
            (_scene: Cesium.Scene, error: Error) => {
              // A later tile/shader failure must not strand the visitor behind
              // Cesium's technical error panel. Keep the geographic lens usable.
              recoverRenderer(error);
            },
          ),
        );
        defer(
          viewer.scene.postRender.addEventListener(() => {
            if (!disposed && viewer.scene.globe.tilesLoaded)
              setTilesReady(true);
          }),
        );
        const base = await Cesium.SingleTileImageryProvider.fromUrl(
          "/maps/nautical-world.png",
          {
            credit:
              "Natural Earth · operational styling · not a navigation chart",
          },
        );
        signal.throwIfAborted();
        viewer.imageryLayers.addImageryProvider(base);
        viewer.camera.setView({
          destination: Cesium.Cartesian3.fromDegrees(65, 20, 11_000_000),
        });
        return { viewer };
      },
      createControls({ defer }) {
        defer(installTrackpadPinchZoom(viewer));
        defer(
          viewer.selectedEntityChanged.addEventListener((entity) => {
            const p = entity?.properties?.getValue(viewer.clock.currentTime);
            if (p?.kind === "port") latest.current.onPort(p.code);
            if (p?.kind === "event") latest.current.onEvent(p.id);
            if (p?.kind === "vessel") latest.current.onVessel?.(p.id);
          }),
        );
        return {};
      },
      createData({ defer }) {
        const source = createUsgsEarthquakeSource({
          fetchImpl: (_url, init) =>
            fetch(`${API_BASE}/intelligence/earthquakes`, {
              ...init,
              headers: latest.current.headers,
            }),
        });
        const layer = createEarthquakesLayer({
          source,
          overlayHost: { setVisible() {}, clearSource() {}, setEntries() {} },
        });
        layer.init(viewer);
        quakeRef.current = layer;
        defer(() => {
          quakeRef.current = null;
          layer.destroy(viewer);
        });
        viewer.creditDisplay.addStaticCredit(
          new Cesium.Credit(
            '<a href="/gods-eye-view-LICENSE.txt" target="_blank">God’s Eye View · MIT</a>',
          ),
        );
        return { layer };
      },
      createTools() {
        return {};
      },
    });
    void app
      .start()
      .then(() => {
        if (!disposed) setReady(true);
      })
      .catch((e: Error) => {
        if (!disposed) {
          setFailure(e.message);
          setLens("map");
          void app.destroy();
        }
      });
    return () => {
      disposed = true;
      void app.destroy().catch(() => {});
    };
  }, []);

  useEffect(() => {
    const v = viewerRef.current;
    if (!ready || !v || v.isDestroyed()) return;
    v.entities.removeAll();
    const label = (text: string, selected: boolean, max = 1_700_000) => ({
      text,
      font: "12px sans-serif",
      fillColor: color("#c6dbe7"),
      showBackground: true,
      backgroundColor: color("#091a24").withAlpha(0.85),
      pixelOffset: new Cesium.Cartesian2(12, -16),
      distanceDisplayCondition: new Cesium.DistanceDisplayCondition(
        0,
        selected ? 30_000_000 : max,
      ),
    });
    for (const p of context.ports)
      v.entities.add({
        id: `port:${p.code}`,
        name: p.name,
        position: Cesium.Cartesian3.fromDegrees(
          p.location.lon,
          p.location.lat,
          200,
        ),
        point: {
          pixelSize: p.code === portCode ? 12 : 6,
          color: color(affectedPorts.includes(p.code) ? "#e5b45d" : "#80c4d5"),
          outlineColor: color("#071923"),
          outlineWidth: 2,
        },
        label: label(p.code.slice(2), p.code === portCode),
        properties: { kind: "port", code: p.code },
      });
    for (const e of context.news.events)
      if (e.coordinates)
        v.entities.add({
          id: `event:${e.eventId}`,
          name: e.title,
          position: Cesium.Cartesian3.fromDegrees(
            e.coordinates.lon,
            e.coordinates.lat,
            1000,
          ),
          billboard: {
            image: glyph("M14 3L25 16L14 29L3 16Z", "#e5b45d"),
            width: e.eventId === eventId ? 20 : 11,
            height: e.eventId === eventId ? 22 : 13,
          },
          properties: { kind: "event", id: e.eventId },
        });
    for (const r of routes)
      if (r.positions.length > 1)
        v.entities.add({
          id: `route:${r.id}`,
          name: r.name,
          polyline: {
            positions: r.positions.map(([lat, lon]) =>
              Cesium.Cartesian3.fromDegrees(lon, lat, 2500),
            ),
            width: r.selected ? 3 : 1.3,
            arcType: Cesium.ArcType.GEODESIC,
            material: r.rejected
              ? new Cesium.PolylineDashMaterialProperty({
                  color: color("#d05a4c"),
                })
              : color(r.selected ? "#efbc61" : "#4c9fcb").withAlpha(
                  r.selected ? 1 : 0.45,
                ),
          },
        });
    for (const ship of vessels)
      v.entities.add({
        id: `vessel:${ship.id}`,
        name: ship.name,
        position: Cesium.Cartesian3.fromDegrees(ship.lon, ship.lat, 3000),
        billboard: {
          image: glyph(
            "M14 2L24 27L14 22L4 27Z",
            ship.id === selectedVesselId ? "#ffcf73" : "#4c9fcb",
          ),
          width: ship.id === selectedVesselId ? 24 : 16,
          height: ship.id === selectedVesselId ? 28 : 19,
          rotation: -Cesium.Math.toRadians(routeHeading(ship, routes)),
          alignedAxis: Cesium.Cartesian3.UNIT_Z,
        },
        label: label(ship.name, ship.id === selectedVesselId, 1_500_000),
        properties: { kind: "vessel", id: ship.id },
      });
    for (const m of markers)
      v.entities.add({
        id: `marker:${m.id}`,
        name: m.name,
        position: Cesium.Cartesian3.fromDegrees(m.lon, m.lat, 4000),
        billboard: {
          image: glyph(
            m.kind === "weather"
              ? "M3 16Q8 6 14 16T25 16L25 23Q19 13 14 23T3 23Z"
              : "M14 3L25 25H3Z",
            m.kind === "weather" ? "#719ed2" : "#ae94cc",
          ),
          width: 13,
          height: 15,
        },
        label: label(m.name, false, 900_000),
        properties: m.portCode
          ? { kind: "port", code: m.portCode }
          : { kind: "context" },
      });
    for (const c of context.cameras)
      v.entities.add({
        id: `camera:${c.id}`,
        name: c.name,
        position: Cesium.Cartesian3.fromDegrees(c.lon, c.lat, 300),
        billboard: {
          image: glyph("M3 8H19V25H3ZM19 13L26 8V25L19 20Z", "#dbe5ec"),
          width: 13,
          height: 14,
        },
        properties: { kind: "port", code: c.portCode },
      });
    v.scene.requestRender();
  }, [
    ready,
    context,
    routes,
    vessels,
    markers,
    portCode,
    eventId,
    selectedVesselId,
    affectedPorts,
  ]);

  // Geometry is read from the current scene, but refreshes never trigger a fit.
  useEffect(() => {
    const v = viewerRef.current;
    if (!ready || !v || v.isDestroyed()) return;
    const s = latest.current,
      points = s.routes.filter((r) => r.selected).flatMap((r) => r.positions);
    const duration = window.matchMedia("(prefers-reduced-motion: reduce)")
      .matches
      ? 0
      : 0.7;
    if (points.length > 1) {
      const lats = points.map((p) => p[0]),
        lons = points.map((p) => p[1]);
      const w = Math.max(14, Math.max(...lons) - Math.min(...lons)),
        h = Math.max(12, Math.max(...lats) - Math.min(...lats));
      v.camera.flyTo({
        destination: Cesium.Rectangle.fromDegrees(
          Math.max(-179, Math.min(...lons) - w * 0.18),
          Math.max(-80, Math.min(...lats) - h * 0.12),
          Math.min(179, Math.max(...lons) + w * 0.45),
          Math.min(80, Math.max(...lats) + h * 0.12),
        ),
        duration,
      });
    } else {
      const loc = s.focus ??
        s.context.news.events.find((e) => e.eventId === s.eventId)
          ?.coordinates ??
        s.context.ports.find((p) => p.code === s.portCode)?.location ?? {
          lon: 65,
          lat: 20,
        };
      v.camera.flyTo({
        destination: Cesium.Cartesian3.fromDegrees(
          loc.lon,
          loc.lat,
          s.focus || s.eventId ? 3_800_000 : 11_000_000,
        ),
        duration,
      });
    }
  }, [ready, fitKey]);
  useEffect(() => {
    const v = viewerRef.current;
    if (!ready || !v || v.isDestroyed()) return;
    v.trackedEntity =
      follow && selectedVesselId
        ? v.entities.getById(`vessel:${selectedVesselId}`)
        : undefined;
  }, [ready, follow, selectedVesselId, vessels]);
  useEffect(() => {
    const v = viewerRef.current;
    if (!ready || !v || v.isDestroyed()) return;
    if (!imagery) {
      setImageryStatus("Nautical context · Natural Earth");
      return;
    }
    const provider = new Cesium.UrlTemplateImageryProvider({
      url: "https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/BlueMarble_ShadedRelief_Bathymetry/default/GoogleMapsCompatible_Level8/{z}/{y}/{x}.jpeg",
      maximumLevel: 8,
      credit: "NASA GIBS / ESDIS · Blue Marble static composite",
    });
    let errors = 0;
    const remove = provider.errorEvent.addEventListener(() => {
      if (++errors >= 2) {
        setImagery(false);
        setImageryStatus("Imagery unavailable · nautical context retained");
      }
    });
    const layer = v.imageryLayers.addImageryProvider(provider);
    setImageryStatus("NASA Blue Marble · static imagery");
    v.scene.requestRender();
    return () => {
      remove();
      if (!v.isDestroyed()) v.imageryLayers.remove(layer, true);
    };
  }, [ready, imagery]);
  useEffect(() => {
    const v = viewerRef.current,
      l = quakeRef.current;
    if (!ready || !v || !l || v.isDestroyed()) return;
    if (!earthquakes) {
      l.disable(v);
      return;
    }
    l.enable(v);
    let active = true;
    const update = async () => {
      await l.update(v);
      if (active) {
        const stats = l.getStats();
        setQuakeStatus(stats.error ?? `${stats.count} USGS events`);
        v.scene.requestRender();
      }
    };
    void update();
    const timer = setInterval(() => void update(), 60000);
    return () => {
      active = false;
      clearInterval(timer);
      l.disable(v);
    };
  }, [ready, earthquakes]);
  return (
    <div
      className="intel-globe"
      data-testid="intelligence-globe"
      data-ready={ready || lens === "map"}
      data-lens={lens}
      data-tiles-ready={tilesReady}
      data-ports={context.ports.length}
      data-events={context.news.events.length}
      data-routes={routes.length}
      data-vessels={vessels.length}
      data-markers={markers.length}
    >
      <div
        ref={host}
        className="intel-globe-canvas"
        style={{ display: lens === "globe" ? "block" : "none" }}
      />
      {lens === "map" ? (
        <GeographicMap
          context={context}
          routes={routes}
          vessels={vessels}
          portCode={portCode}
          selectedVesselId={selectedVesselId}
          onPort={onPort}
          onEvent={onEvent}
          onVessel={onVessel}
          fitKey={fitKey}
        />
      ) : null}
      <div className="globe-toolbar" aria-label="Scene controls">
        <button onClick={() => setFitCount((n) => n + 1)}>Fit selection</button>
        {lens === "globe" ? (
          <button
            onClick={() => {
              const v = viewerRef.current;
              if (v && !v.isDestroyed())
                v.camera.setView({
                  orientation: { heading: 0, pitch: v.camera.pitch, roll: 0 },
                });
            }}
          >
            North ↑
          </button>
        ) : null}
        {selectedVesselId && lens === "globe" ? (
          <button aria-pressed={follow} onClick={() => setFollow((f) => !f)}>
            Follow
          </button>
        ) : null}
        <button
          aria-pressed={lens === "map"}
          onClick={() =>
            setLens((l) => (l === "map" && !failure ? "globe" : "map"))
          }
        >
          {lens === "map" ? (failure ? "2D fallback" : "3D globe") : "2D map"}
        </button>
        {lens === "globe" ? (
          <button aria-pressed={imagery} onClick={() => setImagery((i) => !i)}>
            Imagery
          </button>
        ) : null}
      </div>
      {!ready && !failure && lens === "globe" ? (
        <div className="intel-scene-message" role="status">
          Preparing global scene…
        </div>
      ) : null}
      <div className="intel-scene-status">
        {failure ? "WebGL unavailable · interactive map active" : imageryStatus}
        {earthquakes ? ` · ${quakeStatus}` : ""}
      </div>
      <div ref={credits} className="intel-credits" />
    </div>
  );
}
