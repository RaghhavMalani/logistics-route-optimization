import { useEffect, useState } from "react";
import {
  layerCatalogueUrl,
  layerExpired,
  parseLayers,
  resourceUrl,
  type GeospatialLayer,
} from "./geospatial-layers";

export interface DisplayLayer {
  descriptor: GeospatialLayer;
  url: string;
}
export default function RemoteLayers({
  portCode,
  assetIds,
  onChange,
}: {
  portCode: string;
  assetIds: Set<string>;
  onChange: (layers: DisplayLayer[]) => void;
}) {
  const [layers, setLayers] = useState<GeospatialLayer[]>([]);
  const [enabled, setEnabled] = useState<Set<string>>(new Set());
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [revision, setRevision] = useState(0);
  const [clock, setClock] = useState(Date.now());
  const endpoint = layerCatalogueUrl(portCode);
  useEffect(() => {
    const abort = new AbortController();
    let mounted = true;
    const timer = setTimeout(
      () => abort.abort(new Error("Layer service timed out")),
      20000,
    );
    setLoading(true);
    setError(null);
    setLayers([]);
    fetch(endpoint, { signal: abort.signal, credentials: "omit" })
      .then((r) => {
        if (!r.ok) throw new Error(`Layer service unavailable (${r.status})`);
        return r.json();
      })
      .then((value) => {
        if (!abort.signal.aborted) {
          const parsed = parseLayers(value, portCode, assetIds);
          setLayers(parsed.layers);
          setEnabled(new Set(parsed.layers.map((l) => l.layerId)));
        }
      })
      .catch((e) => {
        if (mounted)
          setError(
            e instanceof Error ? e.message : "Layer service unavailable",
          );
      })
      .finally(() => {
        clearTimeout(timer);
        if (mounted) setLoading(false);
      });
    return () => {
      mounted = false;
      clearTimeout(timer);
      abort.abort();
    };
  }, [portCode, assetIds, endpoint, revision]);
  useEffect(() => {
    const deadlines = layers
      .map((l) =>
        l.displayResource?.expiresAt
          ? Date.parse(l.displayResource.expiresAt)
          : Infinity,
      )
      .filter((t) => t > Date.now());
    if (!deadlines.length) return;
    const timer = setTimeout(
      () => setClock(Date.now()),
      Math.min(
        2147483647,
        Math.max(1, Math.min(...deadlines) - Date.now() + 1),
      ),
    );
    return () => clearTimeout(timer);
  }, [layers, clock]);
  useEffect(() => {
    try {
      onChange(
        layers
          .filter((l) => enabled.has(l.layerId) && !layerExpired(l))
          .map((descriptor) => ({
            descriptor,
            url: resourceUrl(descriptor.displayResource!.url, endpoint),
          })),
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : "Invalid resource");
      onChange([]);
    }
  }, [layers, enabled, clock, endpoint, onChange]);
  return (
    <div
      className="mt-1 border-t border-[var(--line)] pt-1"
      data-testid="remote-geospatial-layers"
    >
      <div>
        Dated geospatial layers{" "}
        <button type="button" onClick={() => setRevision((v) => v + 1)}>
          Refresh layers
        </button>
      </div>
      {error && (
        <div role="status">{error}. Static geography remains available.</div>
      )}
      {loading && <div role="status">Loading dated layers…</div>}
      {!loading && !error && !layers.length && <div>No configured layers.</div>}
      {layers.map((layer) => (
        <label key={layer.layerId} className="block">
          <input
            type="checkbox"
            checked={enabled.has(layer.layerId) && !layerExpired(layer)}
            disabled={layerExpired(layer)}
            onChange={() =>
              setEnabled((old) => {
                const n = new Set(old);
                if (n.has(layer.layerId)) n.delete(layer.layerId);
                else n.add(layer.layerId);
                return n;
              })
            }
          />
          {layer.layerId} · {layer.acquisitionFrom ?? "acquisition unknown"} ·{" "}
          {layer.nativeResolutionM === null
            ? "resolution unknown"
            : `${layer.nativeResolutionM} m native`}{" "}
          · {layerExpired(layer) ? "expired — refresh required" : layer.quality}
          <span className="block">{layer.attribution}</span>
        </label>
      ))}
    </div>
  );
}
