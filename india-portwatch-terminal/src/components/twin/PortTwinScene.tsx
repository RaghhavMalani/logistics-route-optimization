import { useEffect, useRef, useState } from "react";
import * as T from "three";
import type { PortTwinState, TwinMetrics } from "@/types/portwatch-os";
import { createTwinWorld } from "./twin-world";
import { twinSelection } from "./twin-selection";
import type { TwinOverlay, TwinSelection } from "./twin-presentation";
import type { TwinPlayback } from "./twin-playback";

export interface PortTwinSceneProps {
  state: PortTwinState;
  overlay: TwinOverlay;
  metrics?: TwinMetrics | null;
  playback?: TwinPlayback | null;
  simulationHour?: number;
  selectedId?: string | null;
  onSelect?: (selection: TwinSelection | null) => void;
  className?: string;
}

export function PortTwinScene({ className, ...props }: PortTwinSceneProps) {
  const mount = useRef<HTMLDivElement>(null);
  const current = useRef(props);
  current.current = props;
  const refresh = useRef<(() => void) | null>(null);
  const [failed, setFailed] = useState(false);
  const shape = [
    props.state.portCode,
    props.state.berths.length,
    props.state.cranes.length,
    props.state.yardBlocks.length,
    props.state.sheds.length,
    props.state.gates.length,
    props.state.calls.length,
    props.state.vehicles.length,
  ].join("|");

  useEffect(() => {
    const container = mount.current;
    if (!container) return;
    let renderer: T.WebGLRenderer;
    try {
      renderer = new T.WebGLRenderer({ antialias: true, alpha: false });
    } catch {
      setFailed(true);
      return;
    }
    const world = createTwinWorld(current.current.state);
    const canvas = renderer.domElement;
    canvas.style.display = "block";
    canvas.setAttribute(
      "aria-label",
      "Schematic port model. Drag to orbit, scroll to zoom, click an object to inspect.",
    );
    container.appendChild(canvas);
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 1.5));
    const camera = new T.OrthographicCamera(-1, 1, 1, -1, 5, 24000);
    const target = new T.Vector3(world.mid, 0, world.inland * 0.31);
    const spherical = new T.Spherical().setFromVector3(
      new T.Vector3(world.span * 0.29, world.span * 1.2, -world.span * 1.45),
    );
    const ray = new T.Raycaster();
    const point = new T.Vector2();
    let frame = 0;
    let dirty = true;
    const paint = () => {
      frame = 0;
      if (document.hidden) return;
      if (dirty) {
        const { state, overlay, selectedId, playback, simulationHour } =
          current.current;
        const model =
          playback && simulationHour !== undefined
            ? playback.sample(simulationHour)
            : undefined;
        world.draw(model?.state ?? state, overlay, selectedId ?? null, model);
        dirty = false;
      }
      renderer.render(world.scene, camera);
      container.dataset.drawCalls = String(renderer.info.render.calls);
    };
    const schedule = () => {
      if (!frame && !document.hidden) frame = requestAnimationFrame(paint);
    };
    refresh.current = () => {
      dirty = true;
      schedule();
    };
    function aim() {
      camera.position.setFromSpherical(spherical).add(target);
      camera.lookAt(target);
      schedule();
    }
    const size = () => {
      const w = container.clientWidth;
      const h = container.clientHeight;
      if (!w || !h) return;
      const aspect = w / h;
      const halfHeight = Math.max(
        (world.span * 0.45) / aspect,
        world.inland * 0.72 + 170,
      );
      camera.left = -halfHeight * aspect;
      camera.right = halfHeight * aspect;
      camera.top = halfHeight;
      camera.bottom = -halfHeight;
      camera.updateProjectionMatrix();
      renderer.setSize(w, h);
      schedule();
    };
    let down: { x: number; y: number; moved: boolean } | null = null;
    const onDown = (event: PointerEvent) => {
      canvas.setPointerCapture(event.pointerId);
      down = { x: event.clientX, y: event.clientY, moved: false };
    };
    const onMove = (event: PointerEvent) => {
      if (!down) return;
      const dx = event.clientX - down.x;
      const dy = event.clientY - down.y;
      if (!down.moved && Math.hypot(dx, dy) < 4) return;
      down = { x: event.clientX, y: event.clientY, moved: true };
      spherical.theta -= dx * 0.006;
      spherical.phi = T.MathUtils.clamp(spherical.phi - dy * 0.006, 0.18, 1.43);
      aim();
    };
    const onUp = (event: PointerEvent) => {
      const pick = down && !down.moved;
      down = null;
      if (!pick) return;
      const rect = canvas.getBoundingClientRect();
      point.set(
        ((event.clientX - rect.left) / rect.width) * 2 - 1,
        1 - ((event.clientY - rect.top) / rect.height) * 2,
      );
      ray.setFromCamera(point, camera);
      const id = world.pick(ray);
      const { state, playback, simulationHour, onSelect } = current.current;
      const visibleState =
        playback && simulationHour !== undefined
          ? playback.sample(simulationHour).state
          : state;
      onSelect?.(id ? twinSelection(visibleState, id) : null);
    };
    const onCancel = () => {
      down = null;
    };
    const onWheel = (event: WheelEvent) => {
      event.preventDefault();
      camera.zoom = T.MathUtils.clamp(
        camera.zoom * (1 - Math.sign(event.deltaY) * 0.12),
        0.5,
        4.5,
      );
      camera.updateProjectionMatrix();
      schedule();
    };
    const visibility = () => {
      if (document.hidden) {
        cancelAnimationFrame(frame);
        frame = 0;
      } else schedule();
    };
    const observer = new ResizeObserver(size);
    observer.observe(container);
    canvas.style.touchAction = "none";
    canvas.addEventListener("pointerdown", onDown);
    canvas.addEventListener("pointermove", onMove);
    canvas.addEventListener("pointerup", onUp);
    canvas.addEventListener("pointercancel", onCancel);
    canvas.addEventListener("wheel", onWheel, { passive: false });
    document.addEventListener("visibilitychange", visibility);
    aim();
    size();
    return () => {
      refresh.current = null;
      cancelAnimationFrame(frame);
      observer.disconnect();
      document.removeEventListener("visibilitychange", visibility);
      canvas.removeEventListener("pointerdown", onDown);
      canvas.removeEventListener("pointermove", onMove);
      canvas.removeEventListener("pointerup", onUp);
      canvas.removeEventListener("pointercancel", onCancel);
      canvas.removeEventListener("wheel", onWheel);
      world.dispose();
      renderer.dispose();
      renderer.forceContextLoss();
      canvas.remove();
    };
  }, [shape]);

  useEffect(
    () => refresh.current?.(),
    [
      props.state,
      props.overlay,
      props.selectedId,
      props.playback,
      props.simulationHour,
    ],
  );

  if (failed) {
    return (
      <div className="grid h-full place-items-center p-6 text-xs">
        3D renderer unavailable. Port metrics remain available in the inspector
        panels.
      </div>
    );
  }
  return (
    <div ref={mount} className={className} data-testid="port-twin-scene" />
  );
}

export default PortTwinScene;
