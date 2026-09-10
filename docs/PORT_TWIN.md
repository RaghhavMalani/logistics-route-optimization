# The port digital twin

One logical port state, consumed by four different things.

---

## Why it is one object

`PortState` is read by:

- the **3D renderer** at `/port/twin` and `/admin/twins`
- the **discrete-event simulator** that produces the +2/+6/+12/+24h views
- the **optimisers** that compare berth-assignment policies
- the **RL environment** that trains and evaluates learned policies

That sharing is the entire justification for building it. If the twin an operator
looks at and the twin a policy trains in were different objects, every result
from one would be unfalsifiable in the other. A 3D port that rendered its own
idea of the terminal would be an illustration; one that projects the object a
policy is evaluated against is an inspector.

```
PortState → Simulation engine → Policy → Next state → Metrics
    │                                                    │
    └──────────── 3D renderer ◄──────────────────────────┘
```

**RL logic is never tied to graphics.** `twin/state.py` contains no meshes,
materials or cameras — only berths with lengths and draughts, yard blocks with
slot counts, cranes with move rates, and a queue of vessels.

---

## Geometry honesty

> **SCHEMATIC DIGITAL TWIN — NOT A SURVEYED PORT PLAN**

The banner is not dismissible and does not scroll away.

| Real | Schematic |
|---|---|
| Berth count (port registry) | Berth positions along the quay |
| Capacity index (port registry) | Yard block and shed positions |
| Berth occupancy (observed snapshot) | Crane rail positions |
| Yard utilisation (capacity pressure) | Anchorage arrangement |
| Queue length (anchorage census) | Gate placement |
| Crane move rates (published envelopes) | — |

The layout scales off two real numbers — berth count and capacity index — so a
large port gets a large twin and a feeder port does not. The *arrangement* is a
schematic: berths along a straight quay, cranes on a shared rail, yard blocks
ranked behind, sheds behind those.

Berths carry a **mix** of lengths and draughts. Assuming every berth takes a
400 m hull would let the optimiser make assignments no port could execute.

Cranes serve their home berth **and its immediate neighbours**, because they
share a rail. Without that, every berth would have a fixed gang and crane
allocation would not be a decision at all.

---

## Seeding from observation

`state_from_snapshot` builds a twin from the pipeline's measured port state:

- **Yard fill** from capacity pressure, weighted toward the quay — real terminals
  fill the blocks nearest the water first, and the optimiser needs that asymmetry
  to have anything to optimise.
- **Berth occupancy** from queue pressure.
- **The arrival queue** from the anchorage census plus the run's arrival rate.

The count is measured; the vessel size mix and exact arrival times are modelled,
and the state's `notes` say so.

Seeding is **deterministic**. Free-times are derived from the berth index rather
than `hash()`, which is salted per process and would make two runs of the same
snapshot differ.

---

## The simulator

Fixed-step, 15 minutes, seeded. Two properties the tests hold it to:

**Determinism.** Two policies can only be compared if the same arrivals, weather
and disruptions hit both. Every stochastic draw comes from a seeded generator in
the config, and the same inputs produce byte-identical metrics. ETA noise is
drawn once per call up front, so the arrival sequence does not depend on how many
steps a policy takes.

**Constraints hold.** A vessel too long or too deep for a berth is not assigned
to it, whatever a policy asks for. The action is refused and recorded in
`rejected_actions` with the reason:

```
berth B1 cannot accept Sim 0: LOA 240m/180m, draught 11.5m/9.5m, cargo container
```

That is how an unsafe learned policy fails its promotion gate instead of quietly
producing impossible schedules. The state passed in is cloned and never mutated,
so a rollout cannot contaminate what the operator is looking at.

### The work-rate model

Cargo hours depend on the gang, the weather and the yard:

- **Weather derating** is zero above an impact index of 0.62 — the cranes are
  *down*, not slow. That is what makes a weather-driven advisory worth issuing.
- **Yard friction** below 0.80 utilisation is 1.0; above it, every productive
  move needs re-handles and the cost grows quadratically, bottoming out at 0.45.
  A full yard is very slow, not stopped.
- **Gang size** scales with the hull: roughly one crane per 90 m, capped at five.
  A 400 m vessel worked by two cranes sits alongside for three days.

Both curves are models and are labelled as such. Neither is a measured
productivity curve for a specific terminal.

---

## Overlays

The 3D scene is coloured by the state, not decorated:

| Overlay | Shows |
|---|---|
| Utilisation | Berth occupancy and yard fill |
| Dwell | How long cargo has been sitting in each block |
| Crane workload | Working hours accrued per crane |
| Queue | Vessels waiting, and how long |
| Storage pressure | Yard and shed capacity headroom |

Click a berth, block, shed, crane or waiting vessel to inspect its operating
state: lengths, draughts, what may be handled there, which cranes can reach it,
capacity, occupancy, mean dwell, reefer plugs.

Time controls step to NOW / +2h / +6h / +12h / +24h, each a **real forward run**
of the simulator rather than an interpolation of the present.

---

## Optimisation

Actions the policies may take:

`assign_berth` · `assign_cranes` · `delay_arrival` · `prioritise` ·
`open_overflow`

The reward function is the operational cost, stated once in
`REWARD_WEIGHTS` and used by every policy and by the RL trainer — a policy that
optimised something else would not be comparable:

| Term | Weight |
|---|---:|
| Vessel-hour at anchor | −1.00 |
| Vessel-hour in port | −0.30 |
| Missed departure | −25.00 |
| Yard block over 95% | −8.00 |
| Berth-hour idle **with a queue waiting** | −0.12 |
| Completed call | +12.00 |
| Hard-constraint violation | −100.00 |
| Infeasible action proposed | −1.50 |

An idle berth is only a cost when something is waiting: a quiet port with empty
berths is not being run badly.

### The policies

| Policy | Family | What it does |
|---|---|---|
| First come, first served | rule | The incumbent, and the benchmark baseline |
| Random feasible | baseline | The sanity floor |
| Greedy shortest-work | optimiser | Shortest expected work first, tightest compatible berth |
| Greedy with lookahead | optimiser | Plus a penalty for blocking an imminent larger arrival |
| Contextual bandit | learned | UCB1 over the rules, keyed on queue/yard/weather |

Greedy rests on two standard results, both defensible to a controller: serving
the shortest job first minimises mean wait across a queue (a theorem, not a
hunch), and putting a small vessel on the largest berth wastes it.

Measured on held-out scenarios:

| Policy | Mean reward | vs baseline |
|---|---:|---:|
| Greedy with arrival lookahead | −196.8 | **+3.2%** |
| Greedy shortest-work | −197.3 | **+3.0%** |
| Contextual bandit | −199.7 | +1.8% |
| First come, first served | −203.3 | — |
| Random feasible | −206.0 | −1.3% |

No policy produced a violation or proposed an infeasible action.

See [RL safety in the README](../README.md#rl-safety) for why the bandit is not
promoted.

---

## API

```
GET /api/port-twin/{port}             the logical state the renderer projects
GET /api/port-twin/{port}/simulate    forward run, snapshots, reward breakdown
GET /api/port-twin/{port}/optimize    every policy against this port's real state
GET /api/port-twin/{port}/benchmark   every policy on held-out scenarios
```

`/optimize` is the port-optimisation surface: not a benchmark on synthetic
scenarios, but the same policies run against the port **as observed right now**,
so a controller can see what each would do today.

---

## Performance

Three.js directly rather than react-three-fiber. The scene is a few hundred boxes
that change colour and the interaction is one raycast on click; a reconciler
between React and the scene graph would cost more than it saved.

The module is **lazy-loaded**, so Three's ~1.1 MB stays out of the entry bundle
for the eleven screens that do not use it. The scene is rebuilt only when the
port's *shape* changes — a different port, or a different berth count — and
merely recoloured when the numbers change, so switching overlay never tears the
GL context down.
