import { useEffect, useRef, type RefObject } from "react";
import * as T from "three";
import { MINIATURE } from "../miniature/palette";
import { createMiniatureLighting } from "../miniature/lighting";
import { CHAPTERS, HOTSPOTS } from "./chapters";
import { createTourWorld } from "./world";

interface Props {
  progress: RefObject<number>;
  reduced: boolean;
  pins: RefObject<(HTMLButtonElement | null)[]>;
  openPin: RefObject<number | null>;
  popover: RefObject<HTMLDivElement | null>;
  popSize: RefObject<{ width: number; height: number }>;
  closePin: () => void;
  onUnavailable: () => void;
}

export default function TourScene({
  progress,
  reduced,
  pins,
  openPin,
  popover,
  popSize,
  closePin,
  onUnavailable,
}: Props) {
  const hostRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const host = hostRef.current;
    if (!host) return;
    // StrictMode replays effects; never reuse a force-lost WebGL context.
    const canvas = document.createElement("canvas");
    canvas.dataset.miniatureSeed = "20261102";
    host.appendChild(canvas);
    let renderer: T.WebGLRenderer;
    try {
      const context = canvas.getContext("webgl2", {
        antialias: true,
        powerPreference: "high-performance",
      });
      if (!context) {
        canvas.remove();
        onUnavailable();
        return;
      }
      renderer = new T.WebGLRenderer({ canvas, context, antialias: true });
    } catch {
      canvas.remove();
      onUnavailable();
      return;
    }
    renderer.setClearColor(MINIATURE.paper, 1);
    renderer.outputColorSpace = T.SRGBColorSpace;
    renderer.toneMapping = T.NoToneMapping;
    renderer.shadowMap.enabled = true;
    renderer.shadowMap.type = T.PCFShadowMap;
    const scene = new T.Scene();
    const camera = new T.OrthographicCamera(-1, 1, 1, -1, 1, 4000);
    const world = createTourWorld(scene);
    const lighting = createMiniatureLighting(scene, canvas.clientWidth < 640);
    const target = new T.Vector3(),
      projected = new T.Vector3();
    let width = 1,
      height = 1,
      raf = 0,
      last = performance.now(),
      time = 0,
      p = progress.current;
    let disposed = false;
    let dirty = true;
    let paintedPin: number | null | undefined;
    let paintedPopSize = "";
    const resize = () => {
      dirty = true;
      width = Math.max(1, canvas.clientWidth);
      height = Math.max(1, canvas.clientHeight);
      const mobile = width < 640,
        budget = mobile ? 1024 : 2048;
      renderer.setPixelRatio(Math.min(devicePixelRatio || 1, mobile ? 1.5 : 2));
      renderer.setSize(width, height, false);
      if (lighting.sun.shadow.mapSize.x !== budget) {
        lighting.sun.shadow.map?.dispose();
        lighting.sun.shadow.map = null;
        lighting.sun.shadow.mapSize.setScalar(budget);
      }
    };
    const observer = new ResizeObserver(resize);
    observer.observe(canvas);
    resize();
    const lerp = (a: number, b: number, t: number) => a + (b - a) * t;
    const render = (now: number) => {
      if (disposed || document.hidden) return;
      const popKey = `${popSize.current.width}:${popSize.current.height}`;
      // Reduced motion redraws only when controls or sizing change. Normal
      // animation retains elapsed-time motion with a bounded painting budget.
      if (
        (reduced &&
          !dirty &&
          p === progress.current &&
          paintedPin === openPin.current &&
          paintedPopSize === popKey) ||
        (!reduced && now - last < 1000 / (width < 640 ? 24 : 30))
      ) {
        raf = requestAnimationFrame(render);
        return;
      }
      const dt = Math.max(0, Math.min(0.05, (now - last) / 1000));
      last = now;
      if (!reduced) time += dt;
      p = reduced
        ? progress.current
        : p + (progress.current - p) * (1 - Math.exp(-dt * 3.4));
      if (Math.abs(p - progress.current) < 0.0001) p = progress.current;
      const i = Math.min(4, Math.floor(p)),
        f = p - i,
        t = f * f * f * (f * (f * 6 - 15) + 10);
      const a = CHAPTERS[i].cam,
        b = CHAPTERS[i + 1].cam;
      const x = lerp(a.x, b.x, t),
        z = lerp(a.z, b.z, t),
        size = lerp(a.size, b.size, t);
      const az = (lerp(a.az, b.az, t) * Math.PI) / 180,
        el = (lerp(a.el, b.el, t) * Math.PI) / 180;
      target.set(x, 0, z);
      camera.position.set(
        x + 900 * Math.cos(el) * Math.cos(az),
        900 * Math.sin(el),
        z + 900 * Math.cos(el) * Math.sin(az),
      );
      camera.lookAt(target);
      const aspect = width / height,
        hh = (size / 2) * (aspect < 1 ? 0.62 / aspect : 1),
        hw = hh * aspect;
      const cx = width >= 900 ? -0.3 * hw : 0,
        cy = width >= 900 ? -0.04 * hh : -0.36 * hh;
      camera.left = cx - hw;
      camera.right = cx + hw;
      camera.top = cy + hh;
      camera.bottom = cy - hh;
      camera.updateProjectionMatrix();
      camera.updateMatrixWorld();
      lighting.follow(target, size);
      world.update(time, p);
      const active = Math.round(p),
        near = Math.abs(p - active) < 0.3;
      HOTSPOTS.forEach((pin, k) => {
        const element = pins.current[k];
        if (!element) return;
        projected.set(pin.p[0], pin.p[1], pin.p[2]).project(camera);
        const px = (projected.x * 0.5 + 0.5) * width,
          py = (-projected.y * 0.5 + 0.5) * height;
        const visible =
          near &&
          pin.ch === active &&
          projected.z >= -1 &&
          projected.z <= 1 &&
          px > 20 &&
          px < width - 20 &&
          py > 70 &&
          py < height - 70;
        element.hidden = !visible;
        if (!visible) {
          if (openPin.current === k) closePin();
          return;
        }
        element.style.transform = `translate(${px.toFixed(1)}px,${py.toFixed(1)}px)`;
        if (openPin.current === k && popover.current) {
          const { width: pw, height: ph } = popSize.current;
          const left = px + 22 + pw > width - 12 ? px - 22 - pw : px + 22;
          const top = Math.max(64, Math.min(height - ph - 64, py - ph / 2));
          popover.current.style.transform = `translate(${Math.max(12, left).toFixed(1)}px,${top.toFixed(1)}px)`;
        }
      });
      renderer.render(scene, camera);
      dirty = false;
      paintedPin = openPin.current;
      paintedPopSize = popKey;
      canvas.dataset.renderCalls = String(renderer.info.render.calls);
      canvas.dataset.progress = p.toFixed(4);
      canvas.dataset.animationTime = time.toFixed(3);
      raf = requestAnimationFrame(render);
    };
    const visibility = () => {
      cancelAnimationFrame(raf);
      last = performance.now();
      if (!document.hidden) raf = requestAnimationFrame(render);
    };
    const contextLost = (event: Event) => {
      event.preventDefault();
      cancelAnimationFrame(raf);
      onUnavailable();
    };
    document.addEventListener("visibilitychange", visibility);
    canvas.addEventListener("webglcontextlost", contextLost);
    raf = requestAnimationFrame(render);
    return () => {
      disposed = true;
      cancelAnimationFrame(raf);
      observer.disconnect();
      document.removeEventListener("visibilitychange", visibility);
      canvas.removeEventListener("webglcontextlost", contextLost);
      lighting.dispose();
      world.dispose();
      renderer.dispose();
      renderer.forceContextLoss();
      canvas.remove();
    };
  }, [
    progress,
    reduced,
    pins,
    openPin,
    popover,
    popSize,
    closePin,
    onUnavailable,
  ]);
  return <div ref={hostRef} aria-hidden="true" />;
}
