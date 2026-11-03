import * as T from "three";
import { COLORS } from "./palette";
export function createMiniatureMaterials() {
  const mat = (
    c: T.ColorRepresentation,
    o?: T.MeshStandardMaterialParameters,
  ) =>
    new T.MeshStandardMaterial(
      Object.assign({ color: c, roughness: 0.93, metalness: 0 }, o || {}),
    );
  const M = {
    signal: mat(COLORS.signal, { roughness: 0.7 }),
    ink: mat(COLORS.modelInk),
    white: mat(COLORS.modelWhite),
    land: mat(COLORS.land),
    pave: mat(COLORS.pave),
    grass: mat(COLORS.grass),
    road: mat(COLORS.road),
    dash: mat(COLORS.modelWhite),
    ballast: mat(COLORS.ballast),
    rail: mat(COLORS.rail),
    glass: mat(COLORS.glass, { roughness: 0.5 }),
    sea: mat(COLORS.modelSea, { roughness: 0.6 }),
    tree1: mat(COLORS.tree1, { flatShading: true }),
    tree2: mat(COLORS.tree2, { flatShading: true }),
    hill: mat(COLORS.hill, { flatShading: true }),
    cloud: mat(COLORS.cloud, {
      flatShading: true,
      transparent: true,
      opacity: 0.94,
    }),
    wake: new T.MeshBasicMaterial({
      color: COLORS.skyLight,
      transparent: true,
      opacity: 0.6,
      depthWrite: false,
    }),
  };

  return M;
}
