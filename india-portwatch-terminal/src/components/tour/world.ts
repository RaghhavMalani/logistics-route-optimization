import * as T from "three";
import { createMiniatureBuilders } from "../miniature/builders";
export function createTourWorld(scene: T.Scene) {
  const {
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
  } = createMiniatureBuilders(scene);
  const SEA_Y = -1.2;
  const sea = new T.Mesh(new T.PlaneGeometry(5000, 5000), M.sea);
  sea.rotation.x = -Math.PI / 2;
  sea.position.y = SEA_Y;
  sea.receiveShadow = true;
  scene.add(sea);

  box(scene, 560, 8, 460, M.land, 280, -4, 0, false); // mainland x 0..560
  box(scene, 112, 0.12, 214, M.pave, 70, 0.06, -6, false); // container yard
  box(scene, 420, 0.1, 460, M.grass, 350, 0.05, 0, false); // hinterland grass
  box(scene, 52, 8, 244, M.land, -340, -4, -140, false); // north headland
  box(scene, 52, 8, 244, M.land, -340, -4, 140, false); // south headland
  box(scene, 34, 8, 60, M.land, -330, -4, -48, false);
  box(scene, 30, 8, 54, M.land, -352, -4, 46, false);
  box(scene, 62, 3, 6, M.pave, -31, -0.3, -114); // moles
  box(scene, 62, 3, 6, M.pave, -31, -0.3, 114);

  function lighthouse(x: number, z: number, h: number) {
    box(scene, 3, h, 3, M.white, x, h / 2, z);
    box(scene, 3.4, 1.6, 3.4, M.ink, x, h + 0.8, z);
  }
  lighthouse(-60, -114, 9);
  lighthouse(-60, 114, 9);
  lighthouse(-324, -22, 12);
  lighthouse(-358, 22, 12);

  /* roads and rail */
  box(scene, 546, 0.14, 10, M.road, 287, 0.14, 104, false);
  box(scene, 10, 0.14, 222, M.road, 18, 0.14, -6, false);
  {
    const dashes = new T.InstancedMesh(unitBox, M.dash, 160);
    let k = 0;
    for (let x = 28; x < 556 && k < 160; x += 8) {
      dummy.position.set(x, 0.24, 104);
      dummy.scale.set(3.4, 0.05, 0.4);
      dummy.rotation.set(0, 0, 0);
      dummy.updateMatrix();
      dashes.setMatrixAt(k++, dummy.matrix);
    }
    for (let z = -110; z < 98 && k < 160; z += 8) {
      dummy.position.set(18, 0.24, z);
      dummy.scale.set(0.4, 0.05, 3.4);
      dummy.updateMatrix();
      dashes.setMatrixAt(k++, dummy.matrix);
    }
    dashes.count = k;
    dashes.receiveShadow = true;
    scene.add(dashes);
  }
  buildTracks();
  /* --------------------------------------------------------- hills, trees */
  buildTrees();
  /* ---------------------------------------------------------------- ships */

  // Moored at berths (two of three berths occupied)
  const BERTHS = [-50, 0, 50];
  const moored = [makeShip(42, 9, 1), makeShip(38, 8.5, 0.75)];
  moored[0].position.set(-7.5, SEA_Y + 0.9, -50);
  moored[0].rotation.y = -Math.PI / 2;
  moored[1].position.set(-7.2, SEA_Y + 0.9, 0);
  moored[1].rotation.y = Math.PI / 2;

  // Waiting at anchorage
  const anchor = [
    { s: makeShip(38, 8.5, 1), x: -132, z: -46, r: 0.5 },
    { s: makeShip(34, 8, 0.9), x: -150, z: 2, r: 0.25 },
    { s: makeShip(40, 9, 1.1), x: -128, z: 48, r: -0.2 },
  ];
  anchor.forEach((a) => {
    a.s.position.set(a.x, SEA_Y + 0.9, a.z);
    a.s.rotation.y = a.r;
  });

  // The hull whose decision we follow
  const hero = makeShip(40, 9, 1);
  hero.position.set(-250, SEA_Y + 0.9, 78);
  hero.rotation.y = 0.18;
  const heroWake = addWake(hero, 40);
  heroWake.material.opacity = 0.35;

  // Traffic on the lane through the strait (closed loop)
  const LANE = new T.CatmullRomCurve3(
    [
      [-640, 46],
      [-480, 24],
      [-385, 9],
      [-300, 10],
      [-232, -4],
      [-186, -38],
      [-200, -80],
      [-262, -62],
      [-330, -12],
      [-405, -10],
      [-505, -28],
      [-660, -64],
      [-720, 0],
    ].map(([x, z]) => new T.Vector3(x, 0, z)),
    true,
    "catmullrom",
    0.5,
  );
  const LANE_LEN = LANE.getLength();
  const laneShips = [0, 0.19, 0.4, 0.58, 0.79].map((u, i) => {
    const len = [36, 40, 32, 38, 34][i];
    const s = makeShip(len, 8 + (i % 2), 0.8 + (i % 3) * 0.15);
    addWake(s, len);
    return { s, u };
  });

  /* ------------------------------------------------------------ quay cranes */

  const cranes: ReturnType<typeof makeQuayCrane>[] = [];
  BERTHS.forEach((z, i) =>
    [-12, 10].forEach((dz) => {
      const c = makeQuayCrane(z + dz);
      c.busy = i < 2;
      cranes.push(c);
    }),
  );

  /* -------------------------------------------------------- container yard */
  buildYard();

  const rtgs = [
    Object.assign(makeGantry(31, 11, 3.6), { x0: 40, z: 8, phase: 0 }),
    Object.assign(makeGantry(31, 11, 3.6), { x0: 104, z: -60, phase: 2.1 }),
  ];
  rtgs.forEach((r) => {
    r.g.position.set(r.x0, 0, r.z);
  });
  const rmg = Object.assign(makeGantry(46, 17, 5), { x0: 86, z: -138 });
  rmg.g.position.set(86, 0, -138);
  // stacks of boxes alongside the rail yard, under the RMG reach
  {
    const n = 140,
      s = new T.InstancedMesh(unitBox, M.white, n);
    let k = 0;
    for (let i = 0; i < 20 && k < n; i++)
      for (let t = 0; t < 3 && k < n; t++)
        for (let r = 0; r < 2; r++) {
          if (rnd() < 0.15) continue;
          dummy.position.set(40 + i * 3.2, 0.78 + t * 1.36, -160.5 + r * 1.5);
          dummy.scale.set(3, 1.3, 1.32);
          dummy.updateMatrix();
          s.setMatrixAt(k, dummy.matrix);
          s.setColorAt(k, new T.Color(boxCol()));
          k++;
        }
    s.count = k;
    s.castShadow = true;
    s.receiveShadow = true;
    if (s.instanceColor) s.instanceColor.needsUpdate = true;
    scene.add(s);
  }

  /* ------------------------------------------------------- warehouse, HQ */
  {
    box(scene, 56, 11, 64, M.white, 176, 5.5, 52);
    for (let i = 0; i < 6; i++) {
      const r = box(scene, 10.2, 0.6, 64, M.pave, 152.5 + i * 9.4, 13.4, 52);
      r.rotation.z = 0.42;
      box(scene, 0.6, 3.6, 62, M.glass, 157 + i * 9.4, 13.2, 52, false);
    }
    for (let i = 0; i < 7; i++)
      box(scene, 0.4, 5, 5, M.ink, 147.8, 2.6, 30 + i * 7.5, false);
  }
  {
    box(scene, 64, 5, 52, M.pave, 246, 2.5, -26);
    box(scene, 18, 48, 18, M.white, 236, 29, -30);
    box(scene, 15, 34, 22, M.white, 258, 22, -14);
    for (let y = 9; y < 52; y += 3.4)
      box(scene, 18.3, 1.3, 18.3, M.glass, 236, y, -30, false);
    for (let y = 9; y < 38; y += 3.4)
      box(scene, 15.3, 1.3, 22.3, M.glass, 258, y, -14, false);
    box(scene, 18.6, 2.4, 18.6, M.signal, 236, 54, -30);
    box(scene, 0.4, 9, 0.4, M.ink, 240, 59.5, -34, false);
  }

  /* --------------------------------------------------------------- trucks */
  const TRUCK_PATH = [
    [16, -112],
    [16, 101],
    [548, 101],
    [548, 107],
    [20, 107],
    [20, -112],
  ].map(([x, z]) => new T.Vector2(x, z));
  const truckSegs: { a: T.Vector2; b: T.Vector2; l: number; s: number }[] = [];
  let truckLen = 0;
  for (let i = 0; i < TRUCK_PATH.length; i++) {
    const a = TRUCK_PATH[i],
      b = TRUCK_PATH[(i + 1) % TRUCK_PATH.length];
    const l = a.distanceTo(b);
    truckSegs.push({ a, b, l, s: truckLen });
    truckLen += l;
  }
  function onTruckPath(d: number) {
    d = ((d % truckLen) + truckLen) % truckLen;
    let seg = truckSegs[truckSegs.length - 1];
    for (const s of truckSegs)
      if (d < s.s + s.l) {
        seg = s;
        break;
      }
    const t = (d - seg.s) / seg.l;
    return {
      x: seg.a.x + (seg.b.x - seg.a.x) * t,
      z: seg.a.y + (seg.b.y - seg.a.y) * t,
      h: Math.atan2(-(seg.b.y - seg.a.y), seg.b.x - seg.a.x),
    };
  }
  const NT = 18;
  const { cab: tCab, chassis: tChassis, cargo: tBox } = makeTruckParts(NT);
  for (let i = 0; i < NT; i++)
    tBox.setColorAt(i, new T.Color(rnd() < 0.15 ? 0xffffff : boxCol()));
  if (tBox.instanceColor) tBox.instanceColor.needsUpdate = true;
  [tCab, tChassis, tBox].forEach((m) => {
    m.castShadow = true;
    m.receiveShadow = true;
    scene.add(m);
  });
  // parked at the warehouse doors
  for (let i = 0; i < 3; i++) {
    const g = new T.Group();
    g.position.set(140, 0, 34 + i * 15);
    g.rotation.y = Math.PI;
    box(g, 3, 3, 2.6, M.signal, 5, 1.8, 0);
    box(g, 10, 0.6, 2.4, M.ink, -1, 1.2, 0);
    box(g, 9.4, 2.4, 2.4, M.white, -1, 2.7, 0);
    scene.add(g);
  }

  /* --------------------------------------------------------------- trains */
  const CARS = 11,
    NTRAINS = 2;
  const loco = new T.InstancedMesh(unitBox, M.signal, NTRAINS);
  const cab = new T.InstancedMesh(unitBox, M.ink, NTRAINS);
  const flats = new T.InstancedMesh(unitBox, M.ink, NTRAINS * CARS);
  const fboxes = new T.InstancedMesh(unitBox, M.white, NTRAINS * CARS * 2);
  for (let i = 0; i < NTRAINS * CARS * 2; i++)
    fboxes.setColorAt(i, new T.Color(boxCol()));
  if (fboxes.instanceColor) fboxes.instanceColor.needsUpdate = true;
  [loco, cab, flats, fboxes].forEach((m) => {
    m.castShadow = true;
    m.receiveShadow = true;
    scene.add(m);
  });
  const trains = [
    { z: -134, dir: 1, speed: 15, off: 0 },
    { z: -142, dir: -1, speed: 12, off: 260 },
  ];
  const TRAIN_SPAN = 640;
  // parked wagon strings
  {
    const n = 2 * 14,
      f = new T.InstancedMesh(unitBox, M.ink, n),
      c = new T.InstancedMesh(unitBox, M.white, n * 2);
    let k = 0,
      j = 0;
    [-150, -126].forEach((z, zi) => {
      for (let i = 0; i < 14; i++) {
        const x = 150 + zi * 70 + i * 13.5;
        dummy.rotation.set(0, 0, 0);
        dummy.position.set(x, 1.3, z);
        dummy.scale.set(12.4, 0.8, 2.6);
        dummy.updateMatrix();
        f.setMatrixAt(k++, dummy.matrix);
        if (rnd() < 0.8) {
          dummy.position.set(x - 3, 2.4, z);
          dummy.scale.set(5.8, 1.4, 2.4);
          dummy.updateMatrix();
          c.setMatrixAt(j, dummy.matrix);
          c.setColorAt(j++, new T.Color(boxCol()));
        }
        if (rnd() < 0.6) {
          dummy.position.set(x + 3, 2.4, z);
          dummy.scale.set(5.8, 1.4, 2.4);
          dummy.updateMatrix();
          c.setMatrixAt(j, dummy.matrix);
          c.setColorAt(j++, new T.Color(boxCol()));
        }
      }
    });
    f.count = k;
    c.count = j;
    if (c.instanceColor) c.instanceColor.needsUpdate = true;
    [f, c].forEach((m) => {
      m.castShadow = true;
      m.receiveShadow = true;
      scene.add(m);
    });
  }

  /* --------------------------------------------------- event at the strait */
  const STRAIT = new T.Vector3(-340, 0, 0);
  const ringMat = new T.MeshBasicMaterial({
    color: 0x26313b,
    transparent: true,
    opacity: 0.5,
    depthWrite: false,
    side: T.DoubleSide,
  });
  const rings = [0, 1, 2].map((i) => {
    const m = new T.Mesh(new T.RingGeometry(7.6, 8.4, 64), ringMat.clone());
    m.rotation.x = -Math.PI / 2;
    m.position.set(STRAIT.x, SEA_Y + 0.12, STRAIT.z);
    scene.add(m);
    return { m, o: i / 3 };
  });
  const heroRing = new T.Mesh(
    new T.RingGeometry(26, 27.2, 72),
    ringMat.clone(),
  );
  heroRing.rotation.x = -Math.PI / 2;
  heroRing.position.set(-250, SEA_Y + 0.12, 78);
  scene.add(heroRing);

  /* --------------------------------------------------- option paths (decide) */
  function dotted(
    points: number[][],
    closed: boolean,
    r: number,
    color: T.ColorRepresentation,
    step: number,
  ) {
    const curve = new T.CatmullRomCurve3(
      points.map(([x, z]) => new T.Vector3(x, SEA_Y + 0.15, z)),
      closed,
      "catmullrom",
      0.5,
    );
    const n = Math.floor(curve.getLength() / step);
    const m = new T.InstancedMesh(
      new T.CylinderGeometry(r, r, 0.12, 12),
      new T.MeshBasicMaterial({
        color,
        transparent: true,
        opacity: 0,
        depthWrite: false,
      }),
      n,
    );
    for (let i = 0; i < n; i++) {
      dummy.position.copy(curve.getPointAt(i / n));
      dummy.rotation.set(0, 0, 0);
      dummy.scale.set(1, 1, 1);
      dummy.updateMatrix();
      m.setMatrixAt(i, dummy.matrix);
    }
    scene.add(m);
    return m;
  }
  const options = [
    {
      m: dotted(
        [
          [-226, 73],
          [-196, 66],
          [-170, 56],
          [-150, 40],
          [-140, 26],
        ],
        false,
        1.15,
        0x26313b,
        4.2,
      ),
      peak: 0.95,
    },
    {
      m: dotted(
        [
          [-226, 84],
          [-200, 106],
          [-160, 126],
          [-110, 134],
          [-62, 132],
        ],
        false,
        0.85,
        0x6c767e,
        5,
      ),
      peak: 0.6,
    },
    {
      m: dotted(
        [
          [-236, 104],
          [-222, 112],
          [-224, 126],
          [-240, 128],
          [-250, 116],
        ],
        true,
        0.85,
        0x6c767e,
        4.4,
      ),
      peak: 0.6,
    },
  ];

  const tmp = new T.Vector3(),
    tan = new T.Vector3();
  const lerp = (a: number, b: number, t: number) => a + (b - a) * t;
  return {
    update(time: number, progress: number) {
      laneShips.forEach((o) => {
        const u = (((o.u + (time * 9) / LANE_LEN) % 1) + 1) % 1;
        LANE.getPointAt(u, tmp);
        LANE.getTangentAt(u, tan);
        o.s.position.set(
          tmp.x,
          SEA_Y + 0.9 + Math.sin(time * 1.3 + o.u * 20) * 0.12,
          tmp.z,
        );
        o.s.rotation.y = Math.atan2(-tan.z, tan.x);
      });
      anchor.forEach((a, i) => {
        a.s.position.y = SEA_Y + 0.9 + Math.sin(time * 1.1 + i * 2) * 0.15;
        a.s.rotation.y = a.r + Math.sin(time * 0.18 + i) * 0.05;
      });
      hero.position.y = SEA_Y + 0.9 + Math.sin(time * 1.2) * 0.14;

      // quay cranes: trolley runs ship → apron, spreader dips at each end
      cranes.forEach((c) => {
        if (!c.busy) {
          c.trolley.position.x = 10;
          c.spreader.position.y = 14;
          c.cable.scale.y = 6;
          c.cable.position.y = 17.4;
          c.lifted.visible = false;
          return;
        }
        const s = (Math.sin(time * 0.45 + c.phase) + 1) / 2;
        const x = lerp(-11, 9, s);
        const dip = Math.pow(Math.abs(Math.cos(time * 0.45 + c.phase)), 6);
        const y = lerp(14.5, 5.5, dip);
        c.trolley.position.x = x;
        c.spreader.position.y = y;
        c.cable.scale.y = 20 - y;
        c.cable.position.y = (20 + y) / 2;
        c.lifted.visible =
          Math.sin(time * 0.45 + c.phase) * Math.sin(time * 0.9 + c.phase) >
          -0.2;
      });
      rtgs.forEach((r) => {
        r.g.position.x = r.x0 + Math.sin(time * 0.16 + r.phase) * 7;
        r.trolley.position.z = Math.sin(time * 0.5 + r.phase) * 12;
      });
      rmg.g.position.x = rmg.x0 + Math.sin(time * 0.12) * 26;
      rmg.trolley.position.z = Math.sin(time * 0.4) * 18;

      // trucks
      for (let i = 0; i < NT; i++) {
        const q = onTruckPath(time * 13 + (i / NT) * truckLen);
        placePart(tCab, i, q.x, q.z, q.h, 5, 1.8, 3, 3, 2.6);
        placePart(tChassis, i, q.x, q.z, q.h, -1, 1.2, 10, 0.6, 2.4);
        placePart(tBox, i, q.x, q.z, q.h, -1, 2.7, 9.4, 2.4, 2.4);
      }
      [tCab, tChassis, tBox].forEach((m) => {
        m.instanceMatrix.needsUpdate = true;
      });

      // trains, clipped at the buffer stop and the far edge of the model
      trains.forEach((tr, ti) => {
        const run = (time * tr.speed + tr.off) % TRAIN_SPAN;
        const head = tr.dir > 0 ? -40 + run : 600 - run;
        const h = tr.dir > 0 ? 0 : Math.PI;
        const vis = (x: number) => x > 24 && x < 538;
        const lx = head;
        const ls = vis(lx) ? 1 : 0.0001;
        placePart(loco, ti, lx, tr.z, h, 0, 2.2, 13 * ls, 3.2 * ls, 3 * ls);
        placePart(cab, ti, lx, tr.z, h, 4.6, 3.9, 3.6 * ls, 0.8 * ls, 3.1 * ls);
        for (let k = 0; k < CARS; k++) {
          const x = head - tr.dir * (14 + k * 13.5);
          const s = vis(x) ? 1 : 0.0001;
          const idx = ti * CARS + k;
          placePart(flats, idx, x, tr.z, h, 0, 1.3, 12.4 * s, 0.8 * s, 2.6 * s);
          const full = (k * 7 + ti * 3) % 5 !== 0 ? 1 : 0.0001;
          placePart(
            fboxes,
            idx * 2,
            x,
            tr.z,
            h,
            -3,
            2.4,
            5.8 * s * full,
            1.4 * s * full,
            2.4 * s * full,
          );
          placePart(
            fboxes,
            idx * 2 + 1,
            x,
            tr.z,
            h,
            3,
            2.4,
            5.8 * s,
            1.4 * s,
            2.4 * s,
          );
        }
      });
      [loco, cab, flats, fboxes].forEach((m) => {
        m.instanceMatrix.needsUpdate = true;
      });

      // the event at the strait, strongest in chapter 1
      const w1 = Math.max(0, 1 - Math.abs(progress - 1) * 1.1);
      rings.forEach((r) => {
        const k = (time * 0.28 + r.o) % 1;
        const s = 1 + k * 3.6;
        r.m.scale.set(s, s, s);
        r.m.material.opacity = (1 - k) * (0.18 + 0.55 * w1);
      });

      // option branches fade in for chapter 2
      const w2 = Math.max(0, 1 - Math.abs(progress - 2) * 1.4);
      options.forEach((o) => {
        o.m.material.opacity = o.peak * w2;
        o.m.visible = w2 > 0.01;
      });
      const hk = (time * 0.35) % 1;
      heroRing.material.opacity = w2 * (1 - hk) * 0.6;
      heroRing.scale.setScalar(0.7 + hk * 0.6);
    },
    dispose() {
      const geometries = new Set<T.BufferGeometry>(),
        materials = new Set<T.Material>();
      scene.traverse((o) => {
        if (o instanceof T.InstancedMesh) o.dispose();
        if (o instanceof T.Mesh) {
          geometries.add(o.geometry);
          for (const m of Array.isArray(o.material) ? o.material : [o.material])
            materials.add(m);
        }
      });
      // Include unused factory materials as well as shared and cloned scene resources.
      Object.values(M).forEach((m) => materials.add(m));
      materials.add(ringMat);
      geometries.add(unitBox);
      geometries.forEach((g) => g.dispose());
      materials.forEach((m) => m.dispose());
      scene.clear();
    },
  };
}
