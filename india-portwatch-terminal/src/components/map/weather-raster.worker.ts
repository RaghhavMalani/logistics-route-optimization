import type {
  WeatherFieldKey,
  WeatherFrame,
} from "@/lib/maritime/weather-model";
import { buildCompositeRaster, buildWeatherRaster } from "./weather-layers";

self.onmessage = async ({
  data,
}: MessageEvent<{ frame: WeatherFrame; field: WeatherFieldKey | null }>) => {
  try {
    self.postMessage({
      raster: await (data.field
        ? buildWeatherRaster(data.frame, data.field)
        : buildCompositeRaster(data.frame)),
    });
  } catch {
    self.postMessage({ failed: true });
  }
};
