import { useEffect, useRef } from "react";
import type { Map as MapLibreMap } from "maplibre-gl";
import { COLORS } from "@/components/miniature/palette";
import { sampleWind } from "@/lib/maritime/weather-field";
import type { WeatherFrame } from "@/lib/maritime/weather-model";

/** Modeled direction and measured speed, repainted when the frame or camera changes. */
export function WindLayer({
  map,
  frame,
  enabled,
}: {
  map: MapLibreMap | null;
  frame: WeatherFrame | null;
  enabled: boolean;
}) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    const ctx = canvas?.getContext("2d");
    if (!canvas || !ctx || !map || !enabled) return;
    let pending = 0;

    const paint = () => {
      pending = 0;
      const { clientWidth: width, clientHeight: height } = map.getContainer();
      const dpr = Math.min(2, window.devicePixelRatio || 1);
      const pixelWidth = Math.round(width * dpr);
      const pixelHeight = Math.round(height * dpr);
      if (canvas.width !== pixelWidth) canvas.width = pixelWidth;
      if (canvas.height !== pixelHeight) canvas.height = pixelHeight;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.clearRect(0, 0, width, height);
      if (!frame) return;

      const fade = Math.max(0.22, Math.min(1, (10 - map.getZoom()) / 3));
      ctx.lineWidth = 1;
      ctx.lineCap = "round";
      ctx.strokeStyle = COLORS.weatherDeep;
      for (let y = 32; y < height; y += 64) {
        for (let x = 32; x < width; x += 64) {
          const { lng, lat } = map.unproject([x, y]);
          const wind = sampleWind(frame, lng, lat);
          if (!wind || wind.speedKn < 0.2) continue;
          const end = map.project([lng + wind.u * 0.01, lat + wind.v * 0.01]);
          const angle = Math.atan2(end.y - y, end.x - x);
          const strength = Math.min(1, wind.speedKn / 22);
          const length = 6 + 9 * strength;
          const tipX = x + length * Math.cos(angle);
          const tipY = y + length * Math.sin(angle);
          ctx.globalAlpha = (0.19 + strength * 0.35) * fade;
          ctx.beginPath();
          ctx.moveTo(x, y);
          ctx.lineTo(tipX, tipY);
          for (const direction of [-0.65, 0.65]) {
            ctx.moveTo(tipX, tipY);
            ctx.lineTo(
              tipX - 4 * Math.cos(angle + direction),
              tipY - 4 * Math.sin(angle + direction),
            );
          }
          ctx.stroke();
        }
      }
    };

    const schedule = () => {
      if (!pending) pending = requestAnimationFrame(paint);
    };
    schedule();
    map.on("move", schedule);
    map.on("resize", schedule);
    return () => {
      cancelAnimationFrame(pending);
      map.off("move", schedule);
      map.off("resize", schedule);
    };
  }, [enabled, frame, map]);

  if (!enabled) return null;
  return (
    <canvas
      ref={canvasRef}
      aria-hidden
      className="pointer-events-none absolute inset-0 size-full"
    />
  );
}
