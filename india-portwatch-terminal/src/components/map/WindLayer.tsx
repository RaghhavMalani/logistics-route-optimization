/**
 * Wind flow, drawn as advected particles over the chart.
 *
 * A vector field of arrows at this station density would be four arrows and a
 * lot of white space; streamlines make the same thirteen readings legible as a
 * flow, which is how a mariner reads wind. Particles are seeded in screen
 * space, stepped through the interpolated field, and faded with a
 * `destination-out` wash so the trails decay without tinting the map beneath.
 *
 * Speed is measured. Direction is monsoon climatology and is labelled MODELLED
 * everywhere this layer is switched on, because the feed carries no direction
 * at all.
 */

import { useEffect, useRef } from "react";
import type { Map as MapLibreMap } from "maplibre-gl";

import { sampleWind } from "@/lib/maritime/weather-field";
import type { WeatherFrame } from "@/lib/maritime/weather-model";

interface Particle {
  x: number;
  y: number;
  age: number;
  life: number;
  speed: number;
}

const MAX_AGE = 110;
/** Screen pixels per second at 10 knots. Legible without looking like a river. */
const PIXELS_PER_KNOT = 1.5;

export function WindLayer({
  map,
  frame,
  enabled,
  density = 1,
}: {
  map: MapLibreMap | null;
  frame: WeatherFrame | null;
  enabled: boolean;
  density?: number;
}) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const frameRef = useRef<WeatherFrame | null>(frame);
  frameRef.current = frame;

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || !map || !enabled) return undefined;

    const ctx = canvas.getContext("2d");
    if (!ctx) return undefined;

    let particles: Particle[] = [];
    let width = 0;
    let height = 0;
    let raf = 0;
    let stale = true;

    const dpr = Math.min(2, window.devicePixelRatio || 1);

    const resize = () => {
      const container = map.getContainer();
      width = container.clientWidth;
      height = container.clientHeight;
      canvas.width = Math.round(width * dpr);
      canvas.height = Math.round(height * dpr);
      canvas.style.width = `${width}px`;
      canvas.style.height = `${height}px`;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      const target = Math.round(((width * height) / 16_000) * density);
      particles = Array.from({ length: Math.max(60, Math.min(1400, target)) }, () => ({
        x: Math.random() * width,
        y: Math.random() * height,
        age: Math.random() * MAX_AGE,
        life: MAX_AGE * (0.5 + Math.random() * 0.8),
        speed: 0,
      }));
      stale = true;
    };

    const reseed = (particle: Particle) => {
      particle.x = Math.random() * width;
      particle.y = Math.random() * height;
      particle.age = 0;
      particle.life = MAX_AGE * (0.5 + Math.random() * 0.8);
    };

    const clear = () => {
      ctx.clearRect(0, 0, width, height);
    };

    let lastTime = performance.now();

    const step = (time: number) => {
      raf = requestAnimationFrame(step);
      const delta = Math.min(0.05, (time - lastTime) / 1000);
      lastTime = time;

      const weather = frameRef.current;
      if (!weather || !width || !height) return;

      const zoom = map.getZoom();
      const fade = zoom >= 9 ? 0.25 : zoom >= 7 ? 0.25 + ((9 - zoom) / 2) * 0.75 : 1;

      if (stale) {
        clear();
        stale = false;
      }

      // Fade the previous trails without painting over the chart.
      ctx.globalCompositeOperation = "destination-out";
      ctx.fillStyle = "rgba(0,0,0,0.055)";
      ctx.fillRect(0, 0, width, height);
      ctx.globalCompositeOperation = "source-over";

      ctx.lineWidth = 1;
      ctx.lineCap = "round";

      for (const particle of particles) {
        particle.age += 1;
        if (particle.age > particle.life) {
          reseed(particle);
          continue;
        }

        let lngLat;
        try {
          lngLat = map.unproject([particle.x, particle.y]);
        } catch {
          reseed(particle);
          continue;
        }

        const wind = sampleWind(weather, lngLat.lng, lngLat.lat);
        if (!wind || wind.speedKn < 0.2) {
          reseed(particle);
          continue;
        }

        // `u` is eastward, `v` northward; screen y grows downward.
        const scale = PIXELS_PER_KNOT * delta * 10;
        const nx = particle.x + wind.u * scale;
        const ny = particle.y - wind.v * scale;

        const strength = Math.min(1, wind.speedKn / 22);
        // The flow is basin-scale context. Closing in on a harbour it would be
        // streaks over the berths, so it thins out the way the raster does.
        const alpha = (0.26 + strength * 0.44) * fade;
        ctx.strokeStyle = `rgba(${155 + strength * 90}, ${210 + strength * 30}, 255, ${alpha})`;
        ctx.beginPath();
        ctx.moveTo(particle.x, particle.y);
        ctx.lineTo(nx, ny);
        ctx.stroke();

        particle.x = nx;
        particle.y = ny;
        particle.speed = wind.speedKn;

        if (nx < -20 || ny < -20 || nx > width + 20 || ny > height + 20) reseed(particle);
      }
    };

    const invalidate = () => {
      stale = true;
    };

    resize();
    raf = requestAnimationFrame(step);
    map.on("move", invalidate);
    map.on("zoom", invalidate);
    map.on("resize", resize);
    window.addEventListener("resize", resize);

    return () => {
      cancelAnimationFrame(raf);
      map.off("move", invalidate);
      map.off("zoom", invalidate);
      map.off("resize", resize);
      window.removeEventListener("resize", resize);
    };
  }, [density, enabled, map]);

  if (!enabled) return null;
  return (
    <canvas
      ref={canvasRef}
      aria-hidden
      className="pointer-events-none absolute inset-0 z-[5]"
    />
  );
}
