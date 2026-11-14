import type { Map as MapLibreMap } from "maplibre-gl";

declare global {
  interface Window {
    __portwatchMap?: MapLibreMap;
    __portwatchSources?: Record<
      string,
      GeoJSON.FeatureCollection<
        GeoJSON.Geometry,
        Record<string, unknown> | null
      >
    >;
  }
}
