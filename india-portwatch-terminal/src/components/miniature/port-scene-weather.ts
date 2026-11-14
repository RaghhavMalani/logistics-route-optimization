import * as T from "three";

import { seededRandom } from "./rng";
import type { MiniatureWeather } from "./use-port-weather";

const radians = Math.PI / 180;

// NOAA fractional-year approximation. UTC plus longitude gives local solar time.
// https://gml.noaa.gov/grad/solcalc/solareqns.PDF
function sunAt(now: Date, lat: number, lon: number) {
  const year = now.getUTCFullYear();
  const hours = now.getUTCHours() + now.getUTCMinutes() / 60;
  const days = (Date.UTC(year + 1, 0, 1) - Date.UTC(year, 0, 1)) / 86_400_000;
  const gamma =
    ((2 * Math.PI) / days) *
    ((now.getTime() - Date.UTC(year, 0, 1)) / 86_400_000 - 0.5);
  const equation =
    229.18 *
    (0.000075 +
      0.001868 * Math.cos(gamma) -
      0.032077 * Math.sin(gamma) -
      0.014615 * Math.cos(2 * gamma) -
      0.040849 * Math.sin(2 * gamma));
  const declination =
    0.006918 -
    0.399912 * Math.cos(gamma) +
    0.070257 * Math.sin(gamma) -
    0.006758 * Math.cos(2 * gamma) +
    0.000907 * Math.sin(2 * gamma) -
    0.002697 * Math.cos(3 * gamma) +
    0.00148 * Math.sin(3 * gamma);
  const angle = ((hours * 60 + equation + 4 * lon) / 4 - 180) * radians;
  const latitude = lat * radians;
  const east = -Math.cos(declination) * Math.sin(angle);
  const north =
    Math.cos(latitude) * Math.sin(declination) -
    Math.sin(latitude) * Math.cos(declination) * Math.cos(angle);
  const up =
    Math.sin(latitude) * Math.sin(declination) +
    Math.cos(latitude) * Math.cos(declination) * Math.cos(angle);
  return { azimuth: Math.atan2(east, north), up };
}

export function createPortSceneWeather(
  scene: T.Scene,
  center: T.Vector3,
  width: number,
  depth: number,
  /** Compass bearing of the positive z-axis of the port model. */
  modelBearing: number,
  cranePositions: readonly T.Vector3[] = [],
) {
  const group = new T.Group();
  const poles = new T.BoxGeometry(width * 0.005, width * 0.11, width * 0.005);
  const cloth = new T.BoxGeometry(width * 0.063, width * 0.025, width * 0.003);
  const poleMaterial = new T.MeshBasicMaterial({ color: 0x384449 });
  const flagMaterial = new T.MeshBasicMaterial({ color: 0xe7e1c4 });
  const flags = [-0.31, 0.31].map((offset) => {
    const rig = new T.Group();
    rig.position.set(
      center.x + width * offset,
      center.y,
      center.z - depth * 0.42,
    );
    const pole = new T.Mesh(poles, poleMaterial);
    pole.position.y = width * 0.055;
    const flag = new T.Mesh(cloth, flagMaterial);
    flag.position.set(width * 0.0315, width * 0.0975, 0);
    rig.add(pole, flag);
    group.add(rig);
    return rig;
  });
  // Pennants on the cranes show wind independently from the crane work cycle.
  const craneFlags = cranePositions.map((position) => {
    const rig = new T.Group();
    rig.position.copy(position);
    const flag = new T.Mesh(cloth, flagMaterial);
    flag.scale.setScalar(0.52);
    flag.position.x = width * 0.063 * 0.26;
    rig.add(flag);
    group.add(rig);
    return rig;
  });
  const windIndicators = [...flags, ...craneFlags];
  const random = seededRandom(4721);
  const seeds = Array.from({ length: 64 }, () => [
    random(),
    random(),
    random(),
  ]);
  const positions = new T.BufferAttribute(
    new Float32Array(seeds.length * 6),
    3,
  );
  const geometry = new T.BufferGeometry().setAttribute("position", positions);
  const material = new T.LineBasicMaterial({
    color: 0xa6cde4,
    transparent: true,
    opacity: 0.65,
  });
  const rain = new T.LineSegments(geometry, material);
  rain.frustumCulled = false;
  group.add(rain);
  scene.add(group);

  const lightingDirection = new T.Vector3();
  let minute = -1;
  let site = "";
  let daylight = true;
  const localAngle = (bearing: number) => bearing - modelBearing * radians;
  return {
    moveCraneFlag(index: number, x: number, y: number, z: number) {
      craneFlags[index]?.position.set(x, y, z);
    },
    draw(weather: MiniatureWeather | null, now: number, motion: boolean) {
      group.visible = weather !== null;
      if (!weather)
        return { direction: undefined, night: false, animate: false };
      const { hour, lat, lon } = weather;
      const key = `${lat}/${lon}`;
      if (Math.floor(now / 60_000) !== minute || key !== site) {
        site = key;
        minute = Math.floor(now / 60_000);
        const { azimuth, up } = sunAt(new Date(now), lat, lon);
        daylight = up >= Math.sin(-0.833 * radians);
        const az = localAngle(azimuth);
        lightingDirection
          .set(-Math.sin(az), Math.max(0.06, up), Math.cos(az))
          .normalize();
      }
      const from = hour.wind_direction_10m;
      const wind = from == null ? null : localAngle((from + 180) * radians);
      for (const flag of windIndicators) {
        flag.visible = wind != null;
        if (wind != null) flag.rotation.y = -Math.PI / 2 - wind;
      }
      rain.visible = (hour.precipitation ?? 0) >= 0.5;
      if (rain.visible) {
        const time = motion ? performance.now() / 900 : 0;
        const leanX = wind == null ? 0 : -Math.sin(wind);
        const leanZ = wind == null ? 0 : Math.cos(wind);
        seeds.forEach(([x, z, phase], i) => {
          const px = center.x + (x - 0.5) * width;
          const pz = center.z + (z - 0.5) * depth;
          const py = center.y + (1 - ((time + phase) % 1)) * width * 0.32;
          positions.setXYZ(i * 2, px, py, pz);
          positions.setXYZ(
            i * 2 + 1,
            px + leanX * width * 0.009,
            py - width * 0.027,
            pz + leanZ * width * 0.009,
          );
        });
        positions.needsUpdate = true;
      }
      return {
        direction: lightingDirection,
        night: !daylight,
        animate: rain.visible && motion,
      };
    },
    dispose() {
      scene.remove(group);
      for (const resource of [
        poles,
        cloth,
        poleMaterial,
        flagMaterial,
        geometry,
        material,
      ])
        resource.dispose();
    },
  };
}
