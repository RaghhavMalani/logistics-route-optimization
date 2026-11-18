import { createHmac, timingSafeEqual } from "node:crypto";

const callbackPath = "/api/intelligence/internal/surface-relay";
const maximumOriginalBytes = 1024 * 1024;
const provider = "https://api.open-meteo.com/v1/forecast";

function signature(secret, direction, group, timestamp, bytes) {
  return createHmac("sha256", secret).update(`${direction}\n${group}\n${timestamp}\n`).update(bytes).digest("hex");
}

async function readBody(iterable, limit) {
  const parts = [];
  let size = 0;
  for await (const chunk of iterable) {
    size += chunk.length;
    if (size > limit) throw new RangeError("body too large");
    parts.push(chunk);
  }
  return Buffer.concat(parts, size);
}

function validQuery(query) {
  const numbers = /^-?\d+(?:\.\d+)?(?:,-?\d+(?:\.\d+)?){2,3}$/u;
  return typeof query.latitude === "string" && numbers.test(query.latitude)
    && typeof query.longitude === "string" && numbers.test(query.longitude)
    && query.latitude.split(",").length === query.longitude.split(",").length
    && query.timezone === "GMT" && query.wind_speed_unit === "kn" && query.forecast_days === 6
    && query.hourly === "wind_speed_10m,wind_gusts_10m,wind_direction_10m,precipitation,visibility";
}

function retryAfterSeconds(value) {
  if (!value) return null;
  if (/^\d+$/u.test(value)) return Number(value);
  const date = Date.parse(value);
  return Number.isFinite(date) ? Math.max(0, Math.ceil((date - Date.now()) / 1000)) : null;
}

export default async function handle(req, res) {
  res.setHeader("Cache-Control", "no-store");
  const secret = process.env.PORTWATCH_WEATHER_RELAY_SECRET;
  const target = process.env.PORTWATCH_WEATHER_RELAY_TARGET;
  if (process.env.VERCEL_ENV !== "preview" || !secret || !target
      || !/^https:\/\/[a-z0-9-]+\.up\.railway\.app$/u.test(target)) {
    return res.status(404).json({ outcome: "unavailable" });
  }
  if (req.method !== "POST") return res.status(405).json({ outcome: "method" });
  const group = req.headers["x-weather-group"];
  const timestamp = req.headers["x-weather-timestamp"];
  const provided = req.headers["x-weather-signature"];
  if (typeof group !== "string" || !/^[0-3]$/u.test(group)
      || typeof timestamp !== "string" || !/^\d{10}$/u.test(timestamp)
      || Math.abs(Date.now() / 1000 - Number(timestamp)) > 120
      || typeof provided !== "string" || !/^[a-f0-9]{64}$/u.test(provided)) {
    return res.status(401).json({ outcome: "signature" });
  }

  let query;
  try {
    const body = req.body === undefined ? await readBody(req, 4096) : Buffer.from(req.body);
    const expected = signature(secret, "request", group, timestamp, body);
    if (body.length > 4096 || !timingSafeEqual(Buffer.from(expected), Buffer.from(provided))) {
      return res.status(401).json({ outcome: "signature" });
    }
    query = JSON.parse(body.toString("utf8"));
  } catch {
    return res.status(400).json({ outcome: "request" });
  }
  if (!query || !validQuery(query)) return res.status(400).json({ outcome: "request" });
  const { latitude, longitude, timezone, wind_speed_unit, hourly, forecast_days } = query;

  let original;
  try {
    const response = await fetch(`${provider}?${new URLSearchParams({
      latitude, longitude, timezone, wind_speed_unit, hourly, forecast_days,
    })}`, {
      signal: AbortSignal.timeout(8000),
      redirect: "error",
      headers: { "User-Agent": "PortWatch-Capstone/1.0" },
    });
    if (response.status === 429) return res.json({ outcome: "HTTP 429", retryAfterSeconds: retryAfterSeconds(response.headers.get("Retry-After")) });
    if (!response.ok || !response.body) return res.json({ outcome: "relay_provider_http" });
    original = await readBody(response.body, maximumOriginalBytes);
  } catch (error) {
    if (error instanceof RangeError) return res.json({ outcome: "relay_invalid_response" });
    return res.json({ outcome: error.name === "TimeoutError" ? "relay_provider_timeout" : "relay_provider_http" });
  }

  const fetchedAt = String(Math.floor(Date.now() / 1000));
  try {
    const callback = await fetch(target + callbackPath, {
      method: "POST",
      signal: AbortSignal.timeout(8000),
      redirect: "error",
      headers: {
        "Content-Type": "application/json",
        "X-Weather-Group": group,
        "X-Weather-Timestamp": fetchedAt,
        "X-Weather-Signature": signature(secret, "receipt", group, fetchedAt, original),
      },
      body: original,
    });
    if (callback.status === 422) return res.json({ outcome: "relay_invalid_response" });
    if (!callback.ok) return res.json({ outcome: "relay_callback_error" });
    const { snapshots } = await callback.json();
    return res.json({ outcome: "ok", snapshots });
  } catch {
    return res.json({ outcome: "relay_callback_error" });
  }
}
