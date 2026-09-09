/**
 * Maritime routing.
 *
 * The claim this product makes about its route geometry is narrow and testable:
 * every line it draws between two places on water stays on water. That is
 * checked three ways here -- across the whole shipped catalogue, against named
 * passages whose shape a mariner would recognise, and against the geometry the
 * running application actually puts into the GL sources, because a catalogue
 * that is correct and a map that draws something else is still a broken map.
 */

import { expect, seedSession, settle, test } from "../harness";
import { firstLandfall, haversineKm, leg, passesNear, routesDoc } from "../water";

test.describe("route catalogue", () => {
  test("every leg stays on water", () => {
    const failures: string[] = [];
    for (const [key, entry] of Object.entries(routesDoc.legs)) {
      const landfall = firstLandfall(entry.coords);
      if (landfall) {
        failures.push(`${key} crosses land at ${landfall[0].toFixed(2)},${landfall[1].toFixed(2)}`);
      }
    }
    expect(failures, "legs whose geometry crosses land").toEqual([]);
    expect(Object.keys(routesDoc.legs).length).toBeGreaterThan(250);
  });

  test("the catalogue declares itself non-navigational", () => {
    expect(routesDoc.disclaimer).toMatch(/VISUALISATION ONLY/);
    expect(routesDoc.disclaimer).toMatch(/not a navigational product/i);
  });

  /**
   * Named passages.
   *
   * A route can be water-only and still be nonsense, so these assert the shape
   * as well: the west-coast run has to hug India rather than strike out into
   * the Arabian Sea, the Singapore run has to leave through Malacca, and
   * anything between the two Indian coasts has to round Sri Lanka because
   * Adam's Bridge is closed to commercial traffic.
   */
  const CASES: Array<{
    name: string;
    from: string;
    to: string;
    /** The route must pass within `km` of each of these. */
    via?: Array<{ point: [number, number]; km: number; label: string }>;
    /** The route must never come within `km` of these. */
    avoid?: Array<{ point: [number, number]; km: number; label: string }>;
    minKm?: number;
    maxKm?: number;
  }> = [
    {
      name: "JNPA to Cochin follows the west coast",
      from: "INNSA",
      to: "INCOK",
      via: [
        { point: [73.6, 15.4], km: 160, label: "Goa offing" },
        { point: [74.8, 12.9], km: 160, label: "Mangalore offing" },
      ],
      minKm: 900,
      maxKm: 1600,
    },
    {
      name: "Chennai to Singapore crosses the Bay and leaves through Malacca",
      from: "INMAA",
      to: "SGSIN",
      via: [
        { point: [93.8, 9.6], km: 320, label: "Andaman Sea" },
        { point: [98.6, 4.6], km: 320, label: "Malacca approach" },
      ],
      minKm: 2500,
      maxKm: 3800,
    },
    {
      name: "Mundra to Suez runs the Gulf of Aden and the Red Sea",
      from: "INMUN",
      to: "SUEZ",
      via: [
        { point: [43.4, 12.6], km: 260, label: "Bab-el-Mandeb" },
        { point: [38.5, 21.0], km: 400, label: "Red Sea" },
      ],
      minKm: 4500,
      maxKm: 7000,
    },
    {
      name: "Vizag to Chennai stays offshore along the east coast",
      from: "INVTZ",
      to: "INMAA",
      via: [{ point: [82.3, 15.6], km: 220, label: "Andhra offing" }],
      minKm: 480,
      maxKm: 900,
    },
    {
      name: "Kolkata to Chennai runs the Bay of Bengal",
      from: "INCCU",
      to: "INMAA",
      via: [{ point: [86.5, 19.0], km: 300, label: "Odisha offing" }],
      minKm: 1100,
      maxKm: 2000,
    },
    {
      name: "Cochin to Chennai rounds Sri Lanka rather than Adam's Bridge",
      from: "INCOK",
      to: "INMAA",
      // South of Sri Lanka. Palk Bay is a dead end for commercial draughts and
      // the routing graph closes it.
      via: [{ point: [80.8, 5.9], km: 260, label: "south of Sri Lanka" }],
      avoid: [{ point: [79.5, 9.6], km: 60, label: "Palk Bay" }],
      minKm: 1400,
      maxKm: 2400,
    },
  ];

  for (const testCase of CASES) {
    test(testCase.name, () => {
      const entry = leg(testCase.from, testCase.to);
      expect(entry, `no catalogue leg ${testCase.from} to ${testCase.to}`).not.toBeNull();
      const coords = entry!.coords;

      expect(firstLandfall(coords), `${testCase.name}: crosses land`).toBeNull();

      let km = 0;
      for (let i = 0; i < coords.length - 1; i += 1) km += haversineKm(coords[i], coords[i + 1]);
      if (testCase.minKm) expect(km, "passage too short to be plausible").toBeGreaterThan(testCase.minKm);
      if (testCase.maxKm) expect(km, "passage far longer than the sea distance").toBeLessThan(testCase.maxKm);

      for (const gate of testCase.via ?? []) {
        expect(
          passesNear(coords, gate.point, gate.km),
          `${testCase.name}: never passes ${gate.label}`,
        ).toBe(true);
      }
      for (const gate of testCase.avoid ?? []) {
        expect(
          passesNear(coords, gate.point, gate.km),
          `${testCase.name}: passes through ${gate.label}`,
        ).toBe(false);
      }
    });
  }
});

/* ------------------------------------------------------- rendered geometry -- */

interface DrawnLine {
  properties: Record<string, unknown>;
  coordinates: Array<[number, number]>;
}

async function drawnLines(
  page: import("@playwright/test").Page,
  source: string,
): Promise<DrawnLine[] | null> {
  return page.evaluate((key) => {
    const registry = (window as unknown as { __portwatchSources?: Record<string, any> })
      .__portwatchSources;
    const data = registry?.[key];
    if (!data) return null;
    if (!data.features) return [];
    return data.features
      .filter((feature: any) => feature.geometry?.type === "LineString")
      .map((feature: any) => ({
        properties: feature.properties ?? {},
        coordinates: feature.geometry.coordinates as Array<[number, number]>,
      }));
  }, source);
}

test.describe("rendered routes", () => {
  test("the corridors the chart draws are water-only", async ({ context, page }) => {
    await seedSession(context, "ADMIN");
    await page.goto("/admin/radar");
    await settle(page);
    await page.waitForFunction(
      () => Boolean((window as any).__portwatchSources?.vessels),
      undefined,
      { timeout: 30_000 },
    );

    const lines = await drawnLines(page, "corridors");
    expect(lines, "the map exposed no corridor source").not.toBeNull();
    expect(lines!.length, "no shipping corridors were drawn").toBeGreaterThan(8);

    for (const line of lines!) {
      expect(
        firstLandfall(line.coordinates),
        `a drawn corridor crosses land`,
      ).toBeNull();
    }
  });

  test("a selected vessel's passage is drawn, and on water", async ({ context, page }) => {
    await seedSession(context, "VESSEL_OPERATOR");
    await page.goto("/vessel/overview");
    await settle(page);
    await page.waitForFunction(
      () => Boolean((window as any).__portwatchSources?.vessels),
      undefined,
      { timeout: 30_000 },
    );
    // The bridge selects the operator's own vessel on arrival, which draws its
    // passage; give the traffic loop a tick to write the source.
    await page.waitForTimeout(1200);

    const lines = await drawnLines(page, "routes");
    expect(lines, "the map exposed no route source").not.toBeNull();
    expect(lines!.length, "no passage was drawn for the selected vessel").toBeGreaterThan(0);

    const ahead = lines!.filter((line) => line.properties.part === "ahead");
    expect(ahead.length, "the remaining passage was not drawn").toBeGreaterThan(0);

    for (const line of lines!) {
      // The behind/ahead split cuts at the vessel, so a fragment can start or
      // end mid-ocean; the entry allowance only needs to cover the quay ends.
      expect(firstLandfall(line.coordinates, 30), "a drawn passage crosses land").toBeNull();
    }
  });
});
