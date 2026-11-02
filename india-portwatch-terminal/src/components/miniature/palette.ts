import * as T from "three";
export const MINIATURE = {
  paper: 0xe7e9e5,
  sea: 0x86b3bf,
  land: 0xecedea,
  ink: 0x26313b,
  signal: 0xee5a24,
} as const;
export const BOXCOLS = [
  0xf4f4f0, 0xf4f4f0, 0xe2e4e1, 0xcfd3d1, 0xa9b0b4, 0x56626c,
] as const;
export function createMiniatureMaterials() {
  const mat = (
    c: T.ColorRepresentation,
    o?: T.MeshStandardMaterialParameters,
  ) =>
    new T.MeshStandardMaterial(
      Object.assign({ color: c, roughness: 0.93, metalness: 0 }, o || {}),
    );
  const M = {
    signal: mat(0xee5a24, { roughness: 0.7 }),
    ink: mat(0x26313b),
    white: mat(0xf7f7f3),
    land: mat(0xecedea),
    pave: mat(0xe1e3df),
    grass: mat(0xdde7d6),
    road: mat(0xc8ccca),
    dash: mat(0xf7f7f3),
    ballast: mat(0xcdc9bf),
    rail: mat(0x737a80),
    glass: mat(0x34424e, { roughness: 0.5 }),
    sea: mat(0x86b3bf, { roughness: 0.6 }),
    tree1: mat(0x93c7a8, { flatShading: true }),
    tree2: mat(0x74b08f, { flatShading: true }),
    hill: mat(0xd3e0cc, { flatShading: true }),
    cloud: mat(0xf4f6f7, {
      flatShading: true,
      transparent: true,
      opacity: 0.94,
    }),
    wake: new T.MeshBasicMaterial({
      color: 0xffffff,
      transparent: true,
      opacity: 0.6,
      depthWrite: false,
    }),
  };

  return M;
}
