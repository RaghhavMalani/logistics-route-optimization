import mapWorkerUrl from "maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url";

let chart: Promise<typeof import("maplibre-gl")> | undefined;

export function loadChart() {
  chart ??= import("maplibre-gl")
    .then((engine) => {
      engine.setWorkerUrl(mapWorkerUrl);
      return engine;
    })
    .catch((error: unknown) => {
      chart = undefined;
      throw error;
    });
  return chart;
}

export function prewarmChart() {
  void loadChart()
    .then((engine) => engine.prewarm())
    .catch(() => {
      // The map can retry and owns any operator-facing loading error.
    });
}
