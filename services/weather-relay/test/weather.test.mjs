import assert from "node:assert/strict";
import { createHmac } from "node:crypto";
import { test } from "node:test";
import handle from "../api/weather.mjs";
import queries from "../queries.json" with { type: "json" };

test("authenticate, restrict coordinates and parameters, reject replay, and limit requests", async () => {
  const key = "test".repeat(16);
  process.env.VERCEL_ENV = "preview";
  process.env.PORTWATCH_WEATHER_RELAY_SECRET = key;
  const previousFetch = globalThis.fetch;
  let upstream = 0;
  globalThis.fetch = async (url) => {
    assert.equal(new URL(url).origin, "https://api.open-meteo.com");
    assert.equal(new URL(url).pathname, "/v1/forecast");
    assert.equal(new URL(url).searchParams.get("latitude"), queries[0].latitude);
    upstream++;
    return new Response('[{"provider":"fixture"}]');
  };
  async function invoke(query, nonce, { bad = false, age = 0 } = {}) {
    const body = Buffer.from(JSON.stringify(query));
    const timestamp = String(Math.floor(Date.now() / 1000) - age);
    const signature = createHmac("sha256", key).update(`request\n0\n${nonce}\n${timestamp}\n`).update(body).digest("hex");
    const res = {
      headers: {}, statusCode: 200,
      setHeader(name, value) { this.headers[name] = value; },
      status(code) { this.statusCode = code; return this; },
      json(data) { this.data = data; return this; },
      send(data) { this.data = JSON.parse(data); this.raw = data; return this; },
    };
    await handle({ method: "POST", body, headers: {
      "x-weather-group": "0", "x-weather-timestamp": timestamp, "x-weather-nonce": nonce,
      "x-weather-signature": bad ? "0".repeat(64) : signature,
    } }, res);
    return res;
  }
  try {
    const nonce = "a".repeat(32);
    assert.equal((await invoke(queries[0], nonce, { bad: true })).statusCode, 401);
    assert.equal((await invoke(queries[0], nonce, { age: 301 })).statusCode, 401);
    assert.equal((await invoke({ ...queries[0], url: "https://example.com" }, nonce)).statusCode, 400);
    assert.equal((await invoke({ ...queries[0], latitude: "0,0,0,0" }, nonce)).statusCode, 400);
    assert.equal(upstream, 0);
    const success = await invoke(queries[0], nonce);
    assert.equal(success.data.outcome, "ok");
    assert.equal(upstream, 1);
    const expected = createHmac("sha256", key)
      .update(`response\n0\n${nonce}\n${success.headers["X-Weather-Timestamp"]}\n`).update(success.raw).digest("hex");
    assert.equal(success.headers["X-Weather-Signature"], expected);
    assert.equal((await invoke(queries[0], nonce)).statusCode, 409);
    assert.equal((await invoke(queries[0], "b".repeat(32))).data.outcome, "relay_rate_limited");
    assert.equal(upstream, 1);
  } finally {
    globalThis.fetch = previousFetch;
  }
});

