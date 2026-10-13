import { useEffect, useMemo, useRef, useState } from "react";
import * as Cesium from "cesium";
import { createApplication } from "gods-eye-view/application";
import {
  createApplicationViewer,
  installTrackpadPinchZoom,
} from "gods-eye-view/application/viewer";
import {
  createEarthquakesLayer,
  createUsgsEarthquakeSource,
} from "gods-eye-view/layers/earthquakes";
import { createBundledCableSource } from "gods-eye-view/layers/submarine-cables/source";
import { useFixes, useTraffic } from "@/components/app/traffic-context";
import { getJson } from "@/services/api";
import type { IntelligenceContext } from "@/services/intelligence";
import "cesium/Build/Cesium/Widgets/widgets.css";
import {
  json2satrec,
  propagate,
  gstime,
  eciToGeodetic,
  degreesLat,
  degreesLong,
  type OMMJsonObject,
} from "satellite.js";

export interface SpatialFeature {
  id: string;
  name: string;
  lat: number;
  lon: number;
  kind: string;
  geometry?: number[][];
  ageSeconds?: number;
  altitudeFt?: number | string;
}
export default function ConnectedGodsEye({
  context,
  features,
  records,
  onPort,
  onEvent,
  onVessel,
  quake,
  cables,
}: {
  context: IntelligenceContext;
  features: SpatialFeature[];
  records: Record<string, unknown>[];
  onPort: (code: string) => void;
  onEvent: (id: string) => void;
  onVessel: (id: string) => void;
  quake: boolean;
  cables: boolean;
}) {
  const host = useRef<HTMLDivElement>(null),
    credit = useRef<HTMLDivElement>(null);
  const viewer = useRef<Cesium.Viewer | null>(null);
  const quakes = useRef<ReturnType<typeof createEarthquakesLayer> | null>(null);
  const fixes = useFixes(0.5);
  const { source } = useTraffic();
  const trafficLabel = source.info.label;
  const [ready, setReady] = useState(false),
    [error, setError] = useState<string | null>(null);
  const latest = useRef({ onPort, onEvent, onVessel });
  latest.current = { onPort, onEvent, onVessel };
  const satellites = useMemo(
    () =>
      records.flatMap((r) => {
        try {
          const epoch = Date.parse(
            String(r.EPOCH) + (/Z$/.test(String(r.EPOCH)) ? "" : "Z"),
          );
          if (
            !Number.isFinite(epoch) ||
            Math.abs(Date.now() - epoch) > 7 * 86400000
          )
            return [];
          return [
            {
              record: json2satrec(r as OMMJsonObject),
              id: String(r.NORAD_CAT_ID),
              name: String(r.OBJECT_NAME),
              epoch,
            },
          ];
        } catch {
          return [];
        }
      }),
    [records],
  );
  useEffect(() => {
    if (!host.current || !credit.current) return;
    let stopped = false;
    const app = createApplication({
      async createScene({ defer, signal }) {
        const v = createApplicationViewer({
          container: host.current!,
          creditContainer: credit.current!,
        });
        viewer.current = v;
        defer(() => {
          viewer.current = null;
          if (!v.isDestroyed()) v.destroy();
        });
        const recover = () => {
          if (!stopped) {
            setError(
              "3D renderer unavailable. The original maritime map remains available behind this panel.",
            );
            setReady(false);
          }
        };
        v.scene.renderError.addEventListener(recover);
        defer(() => v.scene.renderError.removeEventListener(recover));
        v.scene.globe.show = true;
        v.scene.globe.enableLighting = false;
        v.scene.globe.showGroundAtmosphere = false;
        if (v.scene.skyAtmosphere) v.scene.skyAtmosphere.show = false;
        if (v.scene.skyBox) v.scene.skyBox.show = false;
        v.scene.backgroundColor = Cesium.Color.fromCssColorString("#08121e");
        v.targetFrameRate = 30;
        const base = await Cesium.SingleTileImageryProvider.fromUrl(
          "/maps/nautical-world.png",
          {
            credit:
              "Natural Earth · geographic context, not a navigation chart",
          },
        );
        signal.throwIfAborted();
        v.imageryLayers.addImageryProvider(base);
        v.camera.setView({
          destination: Cesium.Cartesian3.fromDegrees(65, 20, 11000000),
        });
        return { viewer: v };
      },
      createControls({ defer }) {
        const v = viewer.current!;
        defer(installTrackpadPinchZoom(v));
        const pick = new Cesium.ScreenSpaceEventHandler(v.scene.canvas);
        pick.setInputAction((movement: { position: Cesium.Cartesian2 }) => {
          const hit = v.scene.pick(movement.position);
          const id = hit?.id?.id as string | undefined;
          if (id?.startsWith("port:")) latest.current.onPort(id.slice(5));
          if (id?.startsWith("event:")) latest.current.onEvent(id.slice(6));
          if (id?.startsWith("pw:ship:")) latest.current.onVessel(id.slice(8));
        }, Cesium.ScreenSpaceEventType.LEFT_CLICK);
        defer(() => pick.destroy());
        return {};
      },
      createData({ defer }) {
        const v = viewer.current!;
        const source = createUsgsEarthquakeSource({
          fetchImpl: async (_input, init) =>
            new Response(
              JSON.stringify(
                await getJson("/intelligence/earthquakes", undefined, {
                  signal: init?.signal as AbortSignal | undefined,
                }),
              ),
              { status: 200, headers: { "Content-Type": "application/json" } },
            ),
        });
        quakes.current = createEarthquakesLayer({
          source,
          overlayHost: { setVisible() {}, clearSource() {}, setEntries() {} },
        });
        quakes.current.init(v);
        defer(() => quakes.current?.destroy(v));
        return {};
      },
      createTools() {
        return {};
      },
    });
    void app
      .start()
      .then(() => {
        if (!stopped) setReady(true);
      })
      .catch((e) => {
        if (!stopped)
          setError(e instanceof Error ? e.message : "Globe unavailable");
      });
    return () => {
      stopped = true;
      void app.destroy();
    };
  }, []);
  useEffect(() => {
    const v = viewer.current,
      q = quakes.current;
    if (!ready || !v || !q) return;
    if (quake) {
      q.enable(v);
      void q
        .update(v)
        .catch(() =>
          setError(
            "Earthquake layer unavailable; other layers remain available.",
          ),
        );
    } else q.disable(v);
  }, [ready, quake]);
  useEffect(() => {
    const v = viewer.current;
    if (!ready || !v || v.isDestroyed()) return;
    for (const e of [...v.entities.values])
      if (
        e.id.startsWith("pw:") ||
        e.id.startsWith("port:") ||
        e.id.startsWith("event:")
      )
        v.entities.remove(e);
    const point = (
      id: string,
      name: string,
      lat: number,
      lon: number,
      color: string,
      size = 5,
      height = 0,
    ) => {
      if (!Number.isFinite(lat) || !Number.isFinite(lon)) return;
      v.entities.add({
        id,
        name,
        position: Cesium.Cartesian3.fromDegrees(lon, lat, height),
        point: {
          pixelSize: size,
          color: Cesium.Color.fromCssColorString(color),
          disableDepthTestDistance: Number.POSITIVE_INFINITY,
        },
        description: name,
      });
    };
    context.ports.forEach((p) =>
      point(
        "port:" + p.code,
        p.name,
        p.location.lat,
        p.location.lon,
        "#60bdff",
        8,
      ),
    );
    context.news.events.forEach((e) => {
      if (e.coordinates)
        point(
          "event:" + e.eventId,
          e.title,
          e.coordinates.lat,
          e.coordinates.lon,
          "#f79b69",
          9,
        );
    });
    // The SAME original traffic provider supplies the full scene and its own labels.
    fixes.forEach((f) =>
      point(
        "pw:ship:" + f.id,
        f.name + " · " + trafficLabel,
        f.lat,
        f.lon,
        f.owned ? "#f1d173" : "#77afa9",
        f.owned ? 7 : 3,
      ),
    );
    context.cameras.forEach((c) =>
      point(
        "pw:camera:" + c.id,
        c.name + " · " + c.coverage,
        c.lat,
        c.lon,
        "#b0a0ea",
        8,
      ),
    );
    const at = new Date();
    satellites.forEach((s) => {
      const state = propagate(s.record, at);
      if (!state?.position) return;
      const pos = eciToGeodetic(state.position, gstime(at));
      point(
        "pw:satellite:" + s.id,
        s.name + " · SGP4 estimate · " + at.toISOString(),
        degreesLat(pos.latitude),
        degreesLong(pos.longitude),
        "#dad0ff",
        6,
        pos.height * 1000,
      );
    });
    features.forEach((f) => {
      point(
        "pw:" + f.kind + ":" + f.id,
        f.name,
        f.lat,
        f.lon,
        f.kind === "aircraft"
          ? "#fafafa"
          : f.kind === "cyclone"
            ? "#f09271"
            : "#8cafde",
        5,
        typeof f.altitudeFt === "number" && Number.isFinite(f.altitudeFt)
          ? f.altitudeFt * 0.3048
          : 0,
      );
      if (f.geometry?.length && f.geometry.length > 1)
        v.entities.add({
          id: "pw:line:" + f.id,
          name: f.name,
          polyline: {
            positions: Cesium.Cartesian3.fromDegreesArray(f.geometry.flat()),
            width: 1.5,
            material: Cesium.Color.fromCssColorString(
              f.kind === "rail" ? "#e1b980" : "#8cafde",
            ),
          },
        });
    });
    v.scene.requestRender();
  }, [ready, context, features, fixes, satellites, trafficLabel]);
  useEffect(() => {
    const v = viewer.current;
    if (!ready || !v) return;
    let disposed = false;
    let source: Cesium.GeoJsonDataSource | undefined;
    if (cables)
      void createBundledCableSource()
        .fetch()
        .then(async (data: { cables: unknown }) => {
          const ds = await Cesium.GeoJsonDataSource.load(
            data.cables as object,
            { stroke: Cesium.Color.MEDIUMPURPLE, strokeWidth: 1 },
          );
          if (disposed) return;
          source = ds;
          await v.dataSources.add(ds);
        })
        .catch(() => setError("Cable reference layer unavailable."));
    return () => {
      disposed = true;
      if (source && !v.isDestroyed()) v.dataSources.remove(source, true);
    };
  }, [ready, cables]);
  return (
    <div className="relative h-[450px] min-h-64 bg-[#08121e]">
      <div ref={host} className="absolute inset-0" />
      <div
        ref={credit}
        className="absolute bottom-0 left-0 right-0 text-[9px]"
      />
      {error ? (
        <p className="absolute left-3 top-3 max-w-sm bg-[var(--panel)] p-2 text-xs">
          {error}
        </p>
      ) : null}
      <p className="absolute top-2 left-2 bg-[var(--panel)]/90 p-1 text-[10px]">
        God’s Eye View · MIT · original traffic provider · {fixes.length}{" "}
        vessels · {trafficLabel}
      </p>
    </div>
  );
}
