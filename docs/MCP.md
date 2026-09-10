# MCP

India PortWatch over Model Context Protocol.

The MCP server exposes the **same** `ToolRegistry` the internal agents use. One
registry, so a capability cannot exist over MCP that does not exist internally,
or carry a different access level there. Two registries would eventually
disagree, and the one that disagreed would be the one with the EXECUTE tool in
it.

---

## Running it

```bash
# Inspect the catalogue and exit
python -m src.portwatch_os.mcp.server --list-tools

# Serve over stdio at the default PROPOSE ceiling
python -m src.portwatch_os.mcp.server

# Raise the ceiling. Requires a named human and their session.
python -m src.portwatch_os.mcp.server --allow-execute \
  --approver "S. Iyer" --session-id "$PORTWATCH_SESSION"
```

Transport is newline-delimited JSON-RPC over stdio, which is what MCP clients
speak. There is no third-party MCP SDK dependency: the protocol at this level is
a few JSON shapes, and adding a dependency for them would be worse than writing
them out.

### Client configuration

```jsonc
{
  "mcpServers": {
    "india-portwatch": {
      "command": "python",
      "args": ["-m", "src.portwatch_os.mcp.server"],
      "cwd": "/path/to/LogisticOptimization"
    }
  }
}
```

---

## The boundary

| Level | Meaning | Side effects | Exposed at default |
|---|---|---|---|
| `READ` | Observe | none | yes |
| `SIMULATE` | Run a model or a what-if | none | yes |
| `PROPOSE` | Create a draft for a human to review | a pending record | yes |
| `EXECUTE` | Act | real | **no** |

At the default ceiling the EXECUTE tools are **absent from `tools/list`**, not
merely refused when called. A client never sees a capability it cannot use.

Raising the ceiling still does not let a model act. An EXECUTE call requires an
`ApprovalContext` whose `human_verified` flag is set, and that flag is set only
by `approval_from_session`, which requires a real authenticated session id. A
context a model client constructs is refused.

A refused call comes back as an MCP **tool error result**, not a protocol error:

```jsonc
{
  "isError": true,
  "content": [{ "type": "text", "text": "portwatch.advisories.issue is a EXECUTE tool and this caller is limited to PROPOSE. Produce a PROPOSE draft for human approval instead." }]
}
```

A client should be able to reason about the refusal and take the PROPOSE route,
which a transport-level failure would not allow.

---

## Methods

| Method | Returns |
|---|---|
| `initialize` | Protocol version, server info, and the honesty rules as `instructions` |
| `tools/list` | Every tool at or below the ceiling, with schema, access level and `computedBy` |
| `tools/call` | The result, plus `computedBy` and the duration |
| `resources/list` | The four descriptive resources |
| `resources/read` | One resource |
| `ping` | `{}` |

---

## Tools

### READ

| Tool | Returns | Computed by |
|---|---|---|
| `portwatch.ports.list` | Every port with observed state | pipeline export + port registry |
| `portwatch.ports.get` | One port, with its forecast series | pipeline export |
| `portwatch.forecast.get` | Calibrated congestion forecast with q10/q50/q90 | `src.forecasting` |
| `portwatch.weather.get` | Marine observations and the impact forecast | Open-Meteo via the pipeline |
| `portwatch.global_eye.events` | Deduplicated, corroborated events | `src.portwatch_os.global_eye` |
| `portwatch.global_eye.exposure` | The impact chain for one event | `global_eye.exposure` |
| `portwatch.company.fleet` | A carrier fleet and its voyages | `fleet.company` |
| `portwatch.company.risk` | Which vessels need intervention, and by when | `global_eye.exposure` |
| `portwatch.port_twin.state` | The twin's logical state | `twin.state` |
| `portwatch.advisories.list` | Advisories visible to a principal | `advisories.store` |
| `portwatch.learning.outcomes` | Scored history and the largest misses | `learning.outcome_agent` |
| `portwatch.learning.reliability` | Learned reliability weights | `learning.reliability` |
| `portwatch.learning.policies` | Policies and their promotion state | `twin.promotion` |
| `portwatch.provenance.get` | LIVE / CACHED / STALE / SYNTHETIC / UNAVAILABLE | `src.utils.provenance` |
| `portwatch.audit.advisory` | An advisory's full audit trail | `advisories.store` |

### SIMULATE

| Tool | Returns | Computed by |
|---|---|---|
| `portwatch.port_twin.simulate` | Metrics, +2/+6/+12/+24h snapshots, reward breakdown, violations | `twin.simulation` |
| `portwatch.port_twin.benchmark` | Every policy on held-out scenarios, ranked | `twin.rl` |
| `portwatch.routing.optimize` | Route exposure, ETA effect, chokepoint risk, provenance | `global_eye.exposure` + forecasts |
| `portwatch.cargo.opportunities` | Feasible transshipment connections, ranked | `cargo.optimizer` |
| `portwatch.cargo.optimize` | An assignment plan and every unplaced reason | `cargo.optimizer` |
| `portwatch.scenarios.simulate` | Per-port congestion deltas under a shock | `decision.scenario_engine` |

### PROPOSE

| Tool | Returns |
|---|---|
| `portwatch.advisories.draft` | A draft advisory. **Not visible to the recipient** until issued |

### EXECUTE

| Tool | Requires |
|---|---|
| `portwatch.advisories.issue` | An approval context naming the controller |
| `portwatch.advisories.respond` | An approval context naming the recipient |

---

## Example

```jsonc
// → tools/call
{
  "name": "portwatch.routing.optimize",
  "arguments": { "vessel_id": "PWD-001", "risk_tolerance": "medium" }
}

// ← structuredContent (verbatim from the shipped demo fleet,
//    with the per-event exposure list elided for length)
{
  "ok": true,
  "access": "SIMULATE",
  "computedBy": "src.portwatch_os.global_eye.exposure + the port forecast artefacts",
  "result": {
    "vesselId": "PWD-001",
    "vesselName": "MV Konkan",
    "destination": "INNSA",
    "lane": "Europe ↔ India (Suez)",
    "primaryRoutingNm": 4650,
    "alternativeRouting": "Cape of Good Hope",
    "detourNm": 3750,
    "detourHours": 232.9,
    "worstExposure": 0.604,
    "riskTolerance": "medium",
    "threshold": 0.4,
    "recommendation": "evaluate_diversion",
    "destinationPortRisk": null,
    "currentEta": null,
    "provenance": {
      "routing": "Water-only routing graph; non-navigational.",
      "positions": "SIMULATED_TRAFFIC",
      "events": "GDELT/GDACS via the pipeline; see portwatch.provenance.get."
    },
    "note": "This is decision support, not a passage plan. Routing geometry is non-navigational and must not be used for navigation."
  }
}
```

`threshold` is the caller's own risk tolerance — 0.25 / 0.40 / 0.60 for
low / medium / high — applied to the worst exposure on the lane. It sits above
the 0.35 floor below which no individual event recommends a diversion at all, so
a cautious operator sees more options and a tolerant one fewer, from the same
measured exposure. `null` is a real answer: `destinationPortRisk` and
`currentEta` are absent rather than guessed.

---

## Resources

| URI | Contents |
|---|---|
| `portwatch://tools` | The exposed catalogue with access levels and computing modules |
| `portwatch://agents` | The orchestrator, the specialists, the Critic and the boundary |
| `portwatch://provenance` | What is live, cached, stale, simulated or unavailable now |
| `portwatch://boundary` | Which tools are exposed at this ceiling, and which are withheld |

---

## What a client is told at initialize

The `instructions` string states the access model, that numbers come from
deterministic models rather than a language model, that every tool declares its
`computedBy`, and — importantly — the data honesty rules:

> Data honesty: vessel traffic in this deployment is simulated, port twin
> geometry is schematic, and cargo manifests are demo data. Each tool's result
> carries the relevant disclaimer. Do not present any of it as observed AIS or as
> a surveyed port plan.

A tool whose artefact is missing raises `ToolUnavailable` naming the command that
produces it, rather than returning a plausible empty result. An agent can then
say "the weather artefact is not available" instead of "there is no weather".
