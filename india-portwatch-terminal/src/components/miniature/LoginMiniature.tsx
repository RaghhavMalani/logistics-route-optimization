import { useEffect, useRef } from "react";
import * as THREE from "three";
import { createTourWorld } from "../tour/world";
import { createMiniatureLighting } from "./lighting";
import { COLORS } from "./palette";

export default function LoginMiniature() {
  const host = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const element = host.current;
    if (!element) return;
    let dispose: (() => void) | undefined;
    const observer = new ResizeObserver(() => {
      const { clientWidth: width, clientHeight: height } = element;
      if (!width || !height) return;
      if (dispose) return;
      const canvas = document.createElement("canvas");
      const context = canvas.getContext("webgl2", { antialias: true });
      if (!context) {
        observer.disconnect();
        return;
      }
      const renderer = new THREE.WebGLRenderer({
        canvas,
        context,
        antialias: true,
      });
      renderer.setClearColor(COLORS.paper);
      renderer.shadowMap.enabled = true;
      renderer.shadowMap.type = THREE.PCFShadowMap;
      const scene = new THREE.Scene();
      const world = createTourWorld(scene);
      const lighting = createMiniatureLighting(scene, width < 800);
      const target = new THREE.Vector3(-58, 0, 4);
      const camera = new THREE.OrthographicCamera(-1, 1, 1, -1, 1, 4000);
      camera.position.copy(target).add(new THREE.Vector3(290, 320, 410));
      camera.lookAt(target);
      lighting.follow(target, 205);
      world.update(0, 3);
      canvas.className = "block h-full w-full";
      element.append(canvas);
      const paint = () => {
        const { clientWidth, clientHeight } = element;
        if (!clientWidth || !clientHeight) return;
        const aspect = clientWidth / clientHeight;
        const halfWidth = Math.max(104, 100 * aspect);
        camera.left = -halfWidth;
        camera.right = halfWidth;
        camera.top = halfWidth / aspect;
        camera.bottom = -camera.top;
        camera.updateProjectionMatrix();
        renderer.setPixelRatio(Math.min(window.devicePixelRatio, 1.5));
        renderer.setSize(clientWidth, clientHeight, false);
        renderer.render(scene, camera);
      };
      const resize = new ResizeObserver(paint);
      resize.observe(element);
      paint();
      dispose = () => {
        resize.disconnect();
        lighting.dispose();
        world.dispose();
        renderer.dispose();
        renderer.forceContextLoss();
        canvas.remove();
      };
      observer.disconnect();
    });
    observer.observe(element);
    return () => {
      observer.disconnect();
      dispose?.();
    };
  }, []);

  return <div ref={host} className="absolute inset-0" aria-hidden="true" />;
}
