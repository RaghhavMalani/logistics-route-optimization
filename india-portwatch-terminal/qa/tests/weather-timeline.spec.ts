import { expect, test } from "@playwright/test";
import { buildWeatherTimeline } from "../../src/lib/maritime/weather-model";
import type { PortSnapshot, WeatherSignal } from "../../src/types/portwatch";

test("forecast strip distinguishes a missing gust from a reported calm hour", () => {
  const hours = ["00", "01", "02"].map((hour, index) => ({
    validAt: `2026-11-03T${hour}:00:00Z`,
    wind_gusts_10m: [null, 0, 16][index],
    wind_speed_10m: null,
    precipitation: null,
    visibility: null,
    wave_height: null,
  }));
  const signals = [
    { portCode: "INMAA", sourceState: "FORECAST", hourly: hours },
  ] as WeatherSignal[];
  const ports = [
    { code: "INMAA", location: { lat: 13.1, lon: 80.3 } },
  ] as PortSnapshot[];

  const timeline = buildWeatherTimeline(signals, ports);

  expect(timeline.meanImpact).toEqual([null, 0, 16]);
  expect(timeline.frameAt(timeline.steps[0]).stations[0].gustKn).toBeNull();
});
