import { useEffect, useRef } from "react";
import * as T from "three";
import { createMiniatureBuilders } from "@/components/miniature/builders";
import { createMiniatureLighting } from "@/components/miniature/lighting";
import { COLORS } from "@/components/miniature/palette";
import type { CargoTone } from "./types";

export default function CargoMiniature({ slots }: { slots: CargoTone[] }) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const host = ref.current;
    if (!host || !window.WebGL2RenderingContext) return;
    const canvas = document.createElement("canvas");
    const context = canvas.getContext("webgl2", { antialias: true });
    if (!context) return;
    const renderer = new T.WebGLRenderer({ canvas, context });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 1.5));
    renderer.toneMapping = T.ACESFilmicToneMapping;
    host.appendChild(canvas);
    const scene = new T.Scene();
    scene.background = new T.Color(COLORS.panel3);
    const { M, box, makeShip, makeGantry, unitBox } =
      createMiniatureBuilders(scene);
    createMiniatureLighting(scene, true);
    box(scene, 58, 0.65, 25, M.sea, -28, -1.5, 0, false);
    box(scene, 48, 1, 25, M.pave, 29, -1.1, 0, false);
    const ship = makeShip(34, 10, 0);
    ship.position.x = -30;
    const gantry = makeGantry(14, 8, 4);
    gantry.g.position.set(37, 0, 2);
    const material = {
      ok: new T.MeshStandardMaterial({ color: COLORS.boxGrey }),
      unknown: new T.MeshStandardMaterial({ color: COLORS.boxMid }),
      warn: new T.MeshStandardMaterial({ color: COLORS.warn }),
      crit: new T.MeshStandardMaterial({ color: COLORS.crit }),
    };
    slots.forEach((level, index) => {
      const column = index % 6;
      const row = Math.floor(index / 6);
      box(
        ship,
        3.1,
        1.5,
        1.8,
        material[level],
        -7 + 3.5 * column,
        2.7,
        -3.6 + 2.3 * row,
      );
      box(
        scene,
        4.3,
        2,
        2.4,
        material[level],
        12 + 5 * column,
        0.4,
        -6 + 3 * row,
      );
    });
    const camera = new T.OrthographicCamera(-60, 60, 20, -20, 0.1, 300);
    camera.position.set(9, 66, 105);
    camera.lookAt(0, 0, 0);
    const resize = () => {
      const width = host.clientWidth;
      if (!width) return;
      const height = Math.max(88, Math.round(width * 0.31));
      const half = (59 * height) / width;
      camera.top = half;
      camera.bottom = -half;
      camera.updateProjectionMatrix();
      renderer.setSize(width, height);
      renderer.render(scene, camera);
    };
    const observer = new ResizeObserver(resize);
    observer.observe(host);
    resize();
    return () => {
      observer.disconnect();
      unitBox.dispose();
      [...Object.values(M), ...Object.values(material)].forEach((item) =>
        item.dispose(),
      );
      renderer.dispose();
      renderer.forceContextLoss();
      canvas.remove();
    };
  }, [slots]);
  return (
    <div
      ref={ref}
      className="cargo-miniature"
      role="img"
      aria-label="Illustrative container positions on the vessel and in the port twin. Amber and red indicate modelled cargo risk."
    />
  );
}
