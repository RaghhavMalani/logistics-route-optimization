import type { GlobeVessel, GlobeRoute } from "./IntelligenceGlobe";
/** Heading from the closest drawn route segment, never an AIS observation. */
export function routeHeading(vessel: GlobeVessel, routes: GlobeRoute[]) {
  if (vessel.heading != null) return vessel.heading;
  const points = routes.find((r) => r.selected)?.positions ?? [];
  if (points.length < 2) return 0;
  let index = 0,
    distance = Infinity;
  points.slice(0, -1).forEach(([lat, lon], i) => {
    const d = (lat - vessel.lat) ** 2 + (lon - vessel.lon) ** 2;
    if (d < distance) {
      distance = d;
      index = i;
    }
  });
  const a = points[index],
    b = points[index + 1],
    lat1 = (a[0] * Math.PI) / 180,
    lat2 = (b[0] * Math.PI) / 180,
    delta = ((b[1] - a[1]) * Math.PI) / 180;
  return (
    ((Math.atan2(
      Math.sin(delta) * Math.cos(lat2),
      Math.cos(lat1) * Math.sin(lat2) -
        Math.sin(lat1) * Math.cos(lat2) * Math.cos(delta),
    ) *
      180) /
      Math.PI +
      360) %
    360
  );
}
