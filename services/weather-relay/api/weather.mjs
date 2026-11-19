import { createHmac, timingSafeEqual } from "node:crypto";
import queries from "../queries.json" with { type: "json" };

const maximumOriginalBytes = 1024 * 1024;
const provider = "https://api.open-meteo.com/v1/forecast";
const recentRequests = new Map();
const nextGroupRequestAt = new Map();

function signature(secret, direction, group, nonce, timestamp, bytes) {
  return createHmac("sha256", secret).update(`${direction}\n${group}\n${nonce}\n${timestamp}\n`).update(bytes).digest("hex");
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

function validQuery(query, expected) {
  return query && !Array.isArray(query) && Object.keys(query).length === Object.keys(expected).length
    && Object.entries(expected).every(([key, value]) => query[key] === value);
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
  if (!["preview", "production"].includes(process.env.VERCEL_ENV) || !secret || secret.length < 32) {
    return res.status(404).json({ outcome: "unavailable" });
  }
  if (req.method !== "POST") return res.status(405).json({ outcome: "method" });
  const group = req.headers["x-weather-group"];
  const timestamp = req.headers["x-weather-timestamp"];
  const nonce = req.headers["x-weather-nonce"];
  const provided = req.headers["x-weather-signature"];
  if (typeof group !== "string" || !/^[0-3]$/u.test(group)
      || typeof timestamp !== "string" || !/^\d{10}$/u.test(timestamp)
      || Math.abs(Date.now() / 1000 - Number(timestamp)) > 300
      || typeof nonce !== "string" || !/^[a-f0-9]{32}$/u.test(nonce)
      || typeof provided !== "string" || !/^[a-f0-9]{64}$/u.test(provided)) {
    return res.status(401).json({ outcome: "signature" });
  }

  let query;
  try {
    const body = req.body === undefined ? await readBody(req, 4096) : Buffer.from(req.body);
    const expected = signature(secret, "request", group, nonce, timestamp, body);
    if (body.length > 4096 || !timingSafeEqual(Buffer.from(expected), Buffer.from(provided))) {
      return res.status(401).json({ outcome: "signature" });
    }
    query = JSON.parse(body.toString("utf8"));
  } catch {
    return res.status(400).json({ outcome: "request" });
  }
  if (!validQuery(query, queries[Number(group)])) return res.status(400).json({ outcome: "request" });
  const { latitude, longitude, timezone, wind_speed_unit, hourly, forecast_days } = queries[Number(group)];
  function signedReply(outcome) {
    const body = Buffer.from(JSON.stringify({ ...outcome, provider }));
    const fetchedAt = String(Math.floor(Date.now() / 1000));
    res.setHeader("X-Weather-Timestamp", fetchedAt);
    res.setHeader("X-Weather-Nonce", nonce);
    res.setHeader("X-Weather-Signature", signature(secret, "response", group, nonce, fetchedAt, body));
    res.setHeader("Content-Type", "application/json");
    return res.status(200).send(body);
  }
  const now = Date.now();
  for (const [challenge, expiresAt] of recentRequests) {
    if (expiresAt <= now) recentRequests.delete(challenge);
  }
  if (recentRequests.has(nonce)) return res.status(409).json({ outcome: "replay" });
  // Shared across concurrent invocations in this warm instance. The single-owner
  // Railway scheduler and durable breaker also bound collection across restarts.
  if (recentRequests.size >= 256 || (nextGroupRequestAt.get(group) ?? 0) > now) {
    res.setHeader("Retry-After", "30");
    return signedReply({ outcome: "relay_rate_limited" });
  }
  recentRequests.set(nonce, now + 300_000);
  nextGroupRequestAt.set(group, now + 30_000);

  let original;
  try {
    const response = await fetch(`${provider}?${new URLSearchParams({
      latitude, longitude, timezone, wind_speed_unit, hourly, forecast_days,
    })}`, {
      signal: AbortSignal.timeout(8000),
      redirect: "error",
      headers: { "User-Agent": "PortWatch-Capstone/1.0" },
    });
    if (response.status === 429) return signedReply({ outcome: "HTTP 429", retryAfterSeconds: retryAfterSeconds(response.headers.get("Retry-After")) });
    if (!response.ok || !response.body) return signedReply({ outcome: "relay_provider_http" });
    original = await readBody(response.body, maximumOriginalBytes);
  } catch (error) {
    if (error instanceof RangeError) return signedReply({ outcome: "relay_invalid_response" });
    return signedReply({ outcome: error.name === "TimeoutError" ? "relay_provider_timeout" : "relay_provider_http" });
  }
  return signedReply({ outcome: "ok", original: original.toString("base64") });
}
