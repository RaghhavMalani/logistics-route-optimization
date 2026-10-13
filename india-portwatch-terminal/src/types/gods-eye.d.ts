declare module "gods-eye-view/application" {
  type ApplicationFactory = (scope: {
    signal: AbortSignal;
    defer: (cleanup: () => unknown) => void;
  }) => unknown;
  export function createApplication(constructors: {
    createScene: ApplicationFactory;
    createControls: ApplicationFactory;
    createData: ApplicationFactory;
    createTools: ApplicationFactory;
  }): { start(): Promise<unknown>; destroy(): Promise<void> };
}
declare module "gods-eye-view/application/viewer" {
  import type { Viewer } from "cesium";
  export function createApplicationViewer(options: {
    container: HTMLElement;
    creditContainer: HTMLElement;
  }): Viewer;
  export function installTrackpadPinchZoom(viewer: Viewer): () => void;
}
declare module "gods-eye-view/layers/earthquakes" {
  import type { Viewer } from "cesium";
  export function createUsgsEarthquakeSource(options: {
    fetchImpl: typeof fetch;
  }): {
    getSnapshot(options?: { signal?: AbortSignal }): Promise<unknown[]>;
  };
  export function createEarthquakesLayer(options: {
    source: {
      getSnapshot(options?: { signal?: AbortSignal }): Promise<unknown[]>;
    };
    overlayHost: {
      setVisible(id: string, visible: boolean): void;
      clearSource(id: string): void;
      setEntries(id: string, rows: unknown[], options?: unknown): void;
    };
  }): {
    init(viewer: Viewer): void;
    enable(viewer: Viewer): void;
    disable(viewer: Viewer): void;
    update(viewer: Viewer): Promise<boolean>;
    destroy(viewer?: Viewer): void;
    getStats(): {
      count: number;
      lastUpdate: number | null;
      error: string | null;
    };
  };
}
declare module "gods-eye-view/sources/cctv-types" {
  export function normalizeFeedType(value: string): string;
  export function isVideoFeedType(value: string): boolean;
}
declare module "gods-eye-view/layers/submarine-cables/source" {
  export function createBundledCableSource(): {
    fetch(
      signal?: AbortSignal,
    ): Promise<{ cables: unknown; landingPoints: unknown }>;
  };
}
