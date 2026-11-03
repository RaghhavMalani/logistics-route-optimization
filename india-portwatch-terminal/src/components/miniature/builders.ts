import * as T from "three";
import { BOXCOLS } from "./palette";
import { createMiniatureMaterials } from "./materials";
import { seededRandom } from "./rng";
/** React-free builder factory. One RNG is shared, preserving reference consumption order. */
export function createMiniatureBuilders(scene: T.Scene, rnd = seededRandom()) {
  const M = createMiniatureMaterials(),
    unitBox = new T.BoxGeometry(1, 1, 1),
    dummy = new T.Object3D();
  const rr = (a: number, b: number) => a + (b - a) * rnd();
  const boxCol = () => BOXCOLS[Math.floor(rnd() * BOXCOLS.length)];
  const mat = (color: T.ColorRepresentation) =>
    new T.MeshStandardMaterial({ color, roughness: 0.93, metalness: 0 });
  const SEA_Y = -1.2;
  function box(
    parent: T.Object3D,
    w: number,
    h: number,
    d: number,
    m: T.Material,
    x: number,
    y: number,
    z: number,
    cast = true,
  ) {
    const o = new T.Mesh(unitBox, m);
    o.scale.set(w, h, d);
    o.position.set(x, y, z);
    o.castShadow = cast !== false;
    o.receiveShadow = true;
    parent.add(o);
    return o;
  }
  function makeShip(len: number, beam: number, fill: number) {
    const g = new T.Group();
    box(g, len, 3.2, beam, M.signal, 0, 0.3, 0);
    const bow = box(
      g,
      beam * 0.72,
      3.2,
      beam * 0.72,
      M.signal,
      len / 2,
      0.3,
      0,
    );
    bow.rotation.y = Math.PI / 4;
    box(g, len + 0.4, 0.7, beam + 0.3, M.ink, 0, -1.05, 0, false);
    const sx = -len / 2 + 4.5;
    box(g, 6, 7, beam * 0.86, M.white, sx, 5.4, 0);
    box(g, 2.2, 1.2, beam + 2.6, M.white, sx + 2, 8.4, 0);
    box(g, 6.2, 0.8, beam * 0.9, M.glass, sx + 0.2, 7.6, 0, false);
    box(g, 2.2, 3.4, 2.2, M.ink, sx - 1.8, 9.6, 0);
    const bays = Math.floor((len - 12) / 3.3),
      rows = Math.max(3, Math.floor((beam - 1) / 1.45));
    const ct = new T.InstancedMesh(
      unitBox,
      M.white,
      bays * rows * Math.ceil(fill * 3.4),
    );
    let k = 0;
    for (let i = 0; i < bays; i++) {
      const tiers = Math.round(fill * rr(1.2, 3.4));
      for (let r = 0; r < rows; r++)
        for (let t = 0; t < tiers; t++) {
          dummy.position.set(
            -len / 2 + 10 + i * 3.3,
            2.55 + t * 1.36,
            -(rows - 1) * 0.73 + r * 1.46,
          );
          dummy.scale.set(3.05, 1.28, 1.3);
          dummy.rotation.set(0, 0, 0);
          dummy.updateMatrix();
          ct.setMatrixAt(k, dummy.matrix);
          ct.setColorAt(k, new T.Color(boxCol()));
          k++;
        }
    }
    ct.count = k;
    ct.castShadow = true;
    ct.receiveShadow = true;
    if (ct.instanceColor) ct.instanceColor.needsUpdate = true;
    g.add(ct);
    g.position.y = SEA_Y + 0.9;
    scene.add(g);
    return g;
  }
  function addWake(ship: T.Group, len: number) {
    const w = new T.Mesh(new T.PlaneGeometry(22, 5.4), M.wake.clone());
    w.rotation.x = -Math.PI / 2;
    w.position.set(-len / 2 - 10, -0.85, 0);
    ship.add(w);
    return w;
  }

  function makeQuayCrane(z: number) {
    const g = new T.Group();
    g.position.set(0, 0, z);
    [
      [3, -4.5],
      [3, 4.5],
      [14, -4.5],
      [14, 4.5],
    ].forEach(([x, zz]) => box(g, 1.1, 19, 1.1, M.signal, x, 9.5, zz));
    box(g, 12, 1.2, 1.2, M.signal, 8.5, 18.6, -4.5);
    box(g, 12, 1.2, 1.2, M.signal, 8.5, 18.6, 4.5);
    box(g, 1.2, 1, 10.2, M.signal, 3, 6, 0);
    box(g, 1.2, 1, 10.2, M.signal, 14, 6, 0);
    box(g, 48, 1.3, 1, M.signal, -8, 21.6, -1.8);
    box(g, 48, 1.3, 1, M.signal, -8, 21.6, 1.8);
    box(g, 7, 4, 5.4, M.white, 13, 24.5, 0);
    const apex = box(g, 1, 9, 1, M.signal, 6, 26, 0);
    apex.rotation.z = 0.12;
    const trolley = new T.Group();
    g.add(trolley);
    box(trolley, 3.4, 1.8, 4.6, M.ink, 0, 20.4, 0);
    const cable = box(trolley, 0.18, 1, 0.18, M.ink, 0, 15, 0, false);
    const spreader = new T.Group();
    trolley.add(spreader);
    box(spreader, 3.6, 0.5, 1.6, M.ink, 0, 0, 0);
    const lifted = box(spreader, 3.05, 1.28, 1.3, mat(boxCol()), 0, -0.9, 0);
    scene.add(g);
    return {
      g,
      trolley,
      cable,
      spreader,
      lifted,
      phase: rnd() * 6.28,
      busy: true,
    };
  }
  function makeGantry(spanZ: number, h: number, legGap: number) {
    const g = new T.Group();
    [
      [-legGap, -spanZ / 2],
      [legGap, -spanZ / 2],
      [-legGap, spanZ / 2],
      [legGap, spanZ / 2],
    ].forEach(([x, z]) => box(g, 1, h, 1, M.signal, x, h / 2, z));
    box(g, 1.2, 1.4, spanZ + 4, M.signal, -legGap, h + 0.4, 0);
    box(g, 1.2, 1.4, spanZ + 4, M.signal, legGap, h + 0.4, 0);
    box(g, 2 * legGap + 1, 1, 1, M.signal, 0, 1.6, -spanZ / 2);
    box(g, 2 * legGap + 1, 1, 1, M.signal, 0, 1.6, spanZ / 2);
    const trolley = new T.Group();
    g.add(trolley);
    box(trolley, 2 * legGap + 2, 1.6, 3.4, M.ink, 0, h + 1.6, 0);
    box(trolley, 0.16, h * 0.45, 0.16, M.ink, 0, h * 0.72, 0, false);
    box(trolley, 3.4, 0.5, 1.6, M.ink, 0, h * 0.49, 0);
    scene.add(g);
    return { g, trolley };
  }
  function placePart(
    mesh: T.InstancedMesh,
    i: number,
    x: number,
    z: number,
    h: number,
    ox: number,
    oy: number,
    sx: number,
    sy: number,
    sz: number,
  ) {
    dummy.position.set(x + Math.cos(h) * ox, oy, z - Math.sin(h) * ox);
    dummy.rotation.set(0, h, 0);
    dummy.scale.set(sx, sy, sz);
    dummy.updateMatrix();
    mesh.setMatrixAt(i, dummy.matrix);
  }

  function buildTrees() {
    const HILLS = [
      [430, -175, 72, 22],
      [478, 40, 80, 26],
      [392, 182, 66, 18],
      [300, -205, 54, 14],
      [530, -60, 60, 20],
      [-340, -100, 24, 14],
      [-342, -190, 26, 18],
      [-338, 96, 24, 13],
      [-342, 196, 26, 17],
    ];
    HILLS.forEach(([x, z, r, h]) => {
      const g = new T.ConeGeometry(r, h, 9, 1);
      const m = new T.Mesh(g, M.hill);
      m.position.set(x, h / 2, z);
      m.receiveShadow = true;
      m.castShadow = true;
      scene.add(m);
    });
    const heightAt = (x: number, z: number) =>
      HILLS.reduce(
        (h, [hx, hz, r, hh]) =>
          Math.max(h, hh * (1 - Math.hypot(x - hx, z - hz) / r)),
        0,
      );

    function freeForTree(x: number, z: number) {
      if (x > 0) {
        if (x < 130) return false;
        if (z > 94 && z < 114) return false;
        if (z > -160 && z < -116) return false;
        if (x > 142 && x < 210 && z > 12 && z < 92) return false;
        if (x > 206 && x < 290 && z > -70 && z < 18) return false;
        return x < 556 && Math.abs(z) < 226;
      }
      return (
        x > -364 &&
        x < -316 &&
        Math.abs(z) > 28 &&
        Math.abs(z) < 258 &&
        !(x > -330 && Math.abs(z) < 60)
      );
    }
    {
      const cone = new T.ConeGeometry(2.4, 7, 6);
      const blob = new T.IcosahedronGeometry(3, 0);
      const A = new T.InstancedMesh(cone, M.tree1, 900);
      const B = new T.InstancedMesh(blob, M.tree2, 900);
      let a = 0,
        b = 0,
        tries = 0;
      while (a + b < 1500 && tries < 20000) {
        tries++;
        const onCape = rnd() < 0.18;
        const x = onCape ? rr(-364, -316) : rr(128, 556);
        const z = onCape ? rr(-258, 258) : rr(-226, 226);
        if (!freeForTree(x, z)) continue;
        // cluster: keep trees near a few groves for a modelled look
        if (
          !onCape &&
          Math.sin(x * 0.045) * Math.cos(z * 0.05) < -0.25 &&
          rnd() < 0.7
        )
          continue;
        const s = rr(0.75, 1.3),
          y = heightAt(x, z);
        dummy.rotation.set(0, rr(0, 6.28), 0);
        dummy.scale.set(s, s, s);
        if (rnd() < 0.55 && a < 900) {
          dummy.position.set(x, y + 3.5 * s, z);
          dummy.updateMatrix();
          A.setMatrixAt(a++, dummy.matrix);
        } else if (b < 900) {
          dummy.position.set(x, y + 3.6 * s, z);
          dummy.updateMatrix();
          B.setMatrixAt(b++, dummy.matrix);
        }
      }
      A.count = a;
      B.count = b;
      [A, B].forEach((m) => {
        m.castShadow = true;
        m.receiveShadow = true;
        scene.add(m);
      });
    }
  }
  function buildYard() {
    const REEFER = { x: 72, z: 76 };
    {
      const BX = [40, 72, 104],
        BZ = [-94, -60, -26, 8, 42, 76];
      const max = BX.length * BZ.length * 8 * 18 * 4;
      const yard = new T.InstancedMesh(unitBox, M.white, max);
      let k = 0;
      BX.forEach((bx) =>
        BZ.forEach((bz) => {
          const reefer = bx === REEFER.x && bz === REEFER.z;
          for (let i = 0; i < 8; i++)
            for (let r = 0; r < 18; r++) {
              if (rnd() < 0.08) continue;
              const tiers = reefer
                ? rnd() < 0.8
                  ? 2
                  : 1
                : Math.floor(rr(1, 4.6));
              for (let t = 0; t < tiers; t++) {
                dummy.position.set(
                  bx - 11.2 + i * 3.2,
                  0.78 + t * 1.36,
                  bz - 12.75 + r * 1.5,
                );
                dummy.scale.set(3.0, 1.3, 1.32);
                dummy.rotation.set(0, 0, 0);
                dummy.updateMatrix();
                yard.setMatrixAt(k, dummy.matrix);
                yard.setColorAt(
                  k,
                  new T.Color(
                    reefer ? (rnd() < 0.85 ? 0xf7f7f3 : 0xdfe3e2) : boxCol(),
                  ),
                );
                k++;
              }
            }
        }),
      );
      yard.count = k;
      yard.castShadow = true;
      yard.receiveShadow = true;
      if (yard.instanceColor) yard.instanceColor.needsUpdate = true;
      scene.add(yard);
      // reefer plug racks at the block ends
      for (let r = 0; r < 18; r += 3) {
        box(
          scene,
          0.5,
          4.6,
          0.5,
          M.ink,
          REEFER.x - 13.6,
          2.3,
          REEFER.z - 12.75 + r * 1.5 + 2,
        );
        box(
          scene,
          0.5,
          4.6,
          0.5,
          M.ink,
          REEFER.x + 13.6,
          2.3,
          REEFER.z - 12.75 + r * 1.5 + 2,
        );
      }
      box(scene, 0.3, 0.3, 27, M.ink, REEFER.x - 13.6, 4.6, REEFER.z, false);
      box(scene, 0.3, 0.3, 27, M.ink, REEFER.x + 13.6, 4.6, REEFER.z, false);
    }
  }
  function buildTracks() {
    const TRACKS = [-150, -142, -134, -126];
    TRACKS.forEach((z) => {
      box(scene, 520, 0.24, 5.2, M.ballast, 280, 0.14, z, false);
      box(scene, 520, 0.36, 0.36, M.rail, 280, 0.42, z - 1.2, false);
      box(scene, 520, 0.36, 0.36, M.rail, 280, 0.42, z + 1.2, false);
    });
    box(scene, 2, 2.4, 9, M.ink, 21, 1.2, -138); // buffer stop
  }
  function makeTruckParts(count: number) {
    return {
      cab: new T.InstancedMesh(unitBox, M.signal, count),
      chassis: new T.InstancedMesh(unitBox, M.ink, count),
      cargo: new T.InstancedMesh(unitBox, M.white, count),
    };
  }
  return {
    M,
    unitBox,
    dummy,
    rnd,
    rr,
    boxCol,
    box,
    makeShip,
    addWake,
    makeQuayCrane,
    makeGantry,
    placePart,
    buildTrees,
    buildYard,
    buildTracks,
    makeTruckParts,
  };
}
