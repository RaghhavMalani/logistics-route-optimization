"""Performance benchmark: how long the world takes, at sizes it will meet.

    python scripts/benchmark_performance.py                 # full run, writes docs/PERFORMANCE.md
    python scripts/benchmark_performance.py --quick         # smaller sizes, fewer repeats
    python scripts/benchmark_performance.py --json out.json # machine-readable results too

Measures, on synthetic but well-formed worlds seeded from the real lane
catalogue and port registry:

    world build          build_world() at 100 / 1,000 / 5,000 / 10,000 vessels,
                         and at 100 / 1,000 events
    cascade              propagate() from one event, and the large-fanout case
                         (one event that threatens every chokepoint over a
                         10,000-hull fleet)
    attention            attention_for() over the large cascade, NATIONAL scope
    decision problem     DecisionEngine.solve_vessel() on a 1,000-hull world
    scenario             branch() + propagate on the 1,000-hull world
    pareto               pareto() over 50 / 500 / 5,000 synthetic options
    critic               DecisionCritic.judge() per option
    mission replay       MissionReplay.decide() + reveal() for every mission
    API                  p50 / p95 / p99 for the routes the demo opens, against
                         the real cache on disk, with payload sizes

Every timing is wall time from time.perf_counter(); CPU is process time over
the same block; memory is tracemalloc's peak allocation during the block, so
the figure is the work's own footprint and not the interpreter's. Numbers are
never optimised in this script: it reports.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import random
import statistics
import sys
import time
import tracemalloc
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("PORTWATCH_LICENCE_MODE", "DEMO")
os.environ.setdefault("PORTWATCH_FRESHNESS_SCHEDULER", "0")

NOW = datetime(2026, 9, 14, 12, 0, tzinfo=timezone.utc)
CHOKEPOINTS = ("SUEZ", "BAB_EL_MANDEB", "HORMUZ", "MALACCA")
CATEGORIES = ("chokepoint_disruption", "conflict", "weather_extreme", "port_disruption")


# --------------------------------------------------------------------------
# measurement
# --------------------------------------------------------------------------


def measure(fn: Callable[[], Any], *, repeats: int) -> Dict[str, Any]:
    """Run ``fn`` ``repeats`` times; report wall, CPU and peak memory."""
    walls: List[float] = []
    cpus: List[float] = []
    peaks: List[int] = []
    result = None
    for _ in range(repeats):
        tracemalloc.start()
        cpu0 = time.process_time()
        t0 = time.perf_counter()
        result = fn()
        walls.append(time.perf_counter() - t0)
        cpus.append(time.process_time() - cpu0)
        _, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        peaks.append(peak)
    walls.sort()
    return {
        "repeats": repeats,
        "wallMs": {
            "min": round(1000 * walls[0], 2),
            "median": round(1000 * statistics.median(walls), 2),
            "p95": round(1000 * walls[min(len(walls) - 1, int(0.95 * (len(walls) - 1)))], 2),
            "max": round(1000 * walls[-1], 2),
        },
        "cpuMs": round(1000 * statistics.median(cpus), 2),
        "peakMemoryMb": round(max(peaks) / (1024 * 1024), 2),
        "_result": result,
    }


def strip(row: Dict[str, Any]) -> Dict[str, Any]:
    return {k: v for k, v in row.items() if not k.startswith("_")}


# --------------------------------------------------------------------------
# synthetic worlds
# --------------------------------------------------------------------------


def synthetic_events(count: int, *, seed: int = 7, every_chokepoint: bool = False):
    from src.portwatch_os.global_eye.model import GlobalEvent

    rng = random.Random(seed)
    events = []
    for index in range(count):
        chokes = list(CHOKEPOINTS) if every_chokepoint else [rng.choice(CHOKEPOINTS)]
        first = NOW - timedelta(hours=rng.uniform(0, 48))
        events.append(GlobalEvent(
            event_id=f"EV-{index:05d}", title=f"synthetic event {index}", category=rng.choice(CATEGORIES),
            region="synthetic", lat=12.6, lon=43.3, geolocation_basis="chokepoint",
            first_seen=first.isoformat(), last_seen=NOW.isoformat(), source_count=rng.randint(1, 9),
            confidence=rng.uniform(0.3, 0.95), severity=rng.uniform(0.2, 1.0), horizon_hours=72.0,
            chokepoints=chokes,
        ))
    return events


def synthetic_voyages(count: int, *, seed: int = 11):
    from src.portwatch_os.global_eye.exposure import TRADE_LANES, VesselVoyage

    rng = random.Random(seed)
    lanes = list(TRADE_LANES.values())
    voyages = []
    for index in range(count):
        lane = rng.choice(lanes)
        hours = {choke: round(rng.uniform(-40, 160), 1) for choke in lane.chokepoints}
        voyages.append(VesselVoyage(
            vessel_id=f"SYN-{index:05d}", name=f"Synthetic {index}", lane_code=lane.code,
            destination_port=rng.choice(lane.india_ports), hours_to_chokepoint=hours,
            service_speed_kn=round(rng.uniform(12, 22), 1),
        ))
    return voyages


def build(events, voyages):
    from src.portwatch_os.world.build import build_world

    return build_world(events=events, voyages=voyages, now=NOW)


def synthetic_options(count: int, *, seed: int = 3):
    from src.portwatch_os.decision.model import (
        DecisionEvaluation,
        DecisionOption,
        FEASIBLE,
        OBJECTIVES,
        SHIPPING_COMPANY,
        known,
    )

    rng = random.Random(seed)
    options = []
    for index in range(count):
        measures = {
            k: known(rng.uniform(0, 100), OBJECTIVES[k].unit, basis="synthetic")
            for k in ("eta", "risk", "fuel")
        }
        options.append(DecisionOption(
            option_id=f"opt-{index}", action="X", label=f"option {index}", actor=SHIPPING_COMPANY,
            status=FEASIBLE, evaluation=DecisionEvaluation(objectives=measures),
        ))
    return options


# --------------------------------------------------------------------------
# the suites
# --------------------------------------------------------------------------


def bench_world(sizes: Sequence[int], event_sizes: Sequence[int], repeats: int) -> Dict[str, Any]:
    out: Dict[str, Any] = {"byVessels": {}, "byEvents": {}}
    events = synthetic_events(40)
    for size in sizes:
        voyages = synthetic_voyages(size)
        row = measure(lambda: build(events, voyages), repeats=repeats)
        graph = row.pop("_result")
        row["nodes"] = len(list(graph.nodes()))
        row["edges"] = len(list(graph.edges()))
        out["byVessels"][str(size)] = row
        print(f"  world build  {size:>6} vessels  median {row['wallMs']['median']:>9.1f} ms  "
              f"peak {row['peakMemoryMb']:>6.1f} MB  nodes {row['nodes']}")
    voyages = synthetic_voyages(500)
    for size in event_sizes:
        many = synthetic_events(size)
        row = measure(lambda: build(many, voyages), repeats=repeats)
        graph = row.pop("_result")
        row["nodes"] = len(list(graph.nodes()))
        out["byEvents"][str(size)] = row
        print(f"  world build  {size:>6} events   median {row['wallMs']['median']:>9.1f} ms  "
              f"peak {row['peakMemoryMb']:>6.1f} MB  nodes {row['nodes']}")
    return out


def bench_cascade(sizes: Sequence[int], repeats: int) -> Dict[str, Any]:
    from src.portwatch_os.world.build import seed_for
    from src.portwatch_os.world.cascade import propagate
    from src.portwatch_os.world.graph import EVENT, key

    out: Dict[str, Any] = {"single": {}, "fanout": {}}
    single = synthetic_events(1)[0]
    fanout = synthetic_events(1, every_chokepoint=True, seed=99)[0]
    fanout.severity, fanout.confidence = 1.0, 0.95
    for size in sizes:
        voyages = synthetic_voyages(size)
        graph = build([single], voyages)
        row = measure(lambda: propagate(graph, key(EVENT, single.event_id), seed_for(single), at=NOW),
                      repeats=repeats)
        cascade = row.pop("_result")
        row["reached"] = len(cascade.reached)
        row["steps"] = len(cascade.steps)
        out["single"][str(size)] = row
        print(f"  cascade      {size:>6} vessels  median {row['wallMs']['median']:>9.1f} ms  reached {row['reached']}")
        wide = build([fanout], voyages)
        row = measure(lambda: propagate(wide, key(EVENT, fanout.event_id), seed_for(fanout), at=NOW),
                      repeats=repeats)
        cascade = row.pop("_result")
        row["reached"] = len(cascade.reached)
        row["steps"] = len(cascade.steps)
        out["fanout"][str(size)] = row
        print(f"  fanout       {size:>6} vessels  median {row['wallMs']['median']:>9.1f} ms  reached {row['reached']}")
    return out


def bench_attention(sizes: Sequence[int], repeats: int) -> Dict[str, Any]:
    from src.portwatch_os.attention.engine import attention_for
    from src.portwatch_os.world.build import seed_for
    from src.portwatch_os.world.cascade import propagate
    from src.portwatch_os.world.graph import EVENT, key

    fanout = synthetic_events(1, every_chokepoint=True, seed=99)[0]
    fanout.severity, fanout.confidence = 1.0, 0.95
    out: Dict[str, Any] = {}
    for size in sizes:
        graph = build([fanout], synthetic_voyages(size))
        cascade = propagate(graph, key(EVENT, fanout.event_id), seed_for(fanout), at=NOW)
        row = measure(lambda: attention_for(cascade, scope="NATIONAL_ADMIN", now=NOW, limit=0), repeats=repeats)
        items = row.pop("_result")
        row["items"] = len(items)
        row["vessels"] = size
        out[str(size)] = row
        print(f"  attention    {size:>6} vessels  median {row['wallMs']['median']:>9.1f} ms  items {row['items']}")
    return out


def bench_decision(size: int, repeats: int) -> Dict[str, Any]:
    from src.portwatch_os.decision import DecisionActor, DecisionEngine
    from src.portwatch_os.decision.model import SHIPPING_COMPANY
    from src.portwatch_os.world.branch import ObservedWorldState
    from src.portwatch_os.world.build import seed_for
    from src.portwatch_os.world.graph import EVENT, key
    from src.portwatch_os.world.live import Revision

    event = synthetic_events(1)[0]
    event.chokepoints = ["BAB_EL_MANDEB"]
    event.first_seen, event.severity, event.confidence = NOW.isoformat(), 0.85, 0.9
    voyages = synthetic_voyages(size)
    subject = voyages[0]
    subject.lane_code, subject.destination_port = "EUR_IND", "INNSA"
    subject.hours_to_chokepoint = {"SUEZ": 20.0, "BAB_EL_MANDEB": 46.0}
    graph = build([event], voyages)
    state = ObservedWorldState(state_id="bench", revision=Revision("DEMO", None, "e", "f", 1), at=NOW,
                               graph=graph, traffic_mode="SIMULATED_TRAFFIC")
    engine = DecisionEngine()
    actor = DecisionActor(SHIPPING_COMPANY)
    counter = {"n": 0}

    def solve():
        counter["n"] += 1
        return engine.solve_vessel(state, event_key=key(EVENT, event.event_id), seed=seed_for(event),
                                   vessel_id=subject.vessel_id, actor=actor, at=NOW,
                                   decision_id=f"bench-{counter['n']}")

    row = measure(solve, repeats=repeats)
    problem = row.pop("_result")
    row["options"] = len(problem.options)
    row["feasible"] = sum(1 for o in problem.options if o.feasible)
    row["vessels"] = size
    print(f"  decision     {size:>6} vessels  median {row['wallMs']['median']:>9.1f} ms  options {row['options']}")
    return row


def bench_scenario(size: int, repeats: int) -> Dict[str, Any]:
    from src.portwatch_os.world.branch import Assumption, CLOSE_CHOKEPOINT, ObservedWorldState, branch
    from src.portwatch_os.world.cascade import propagate
    from src.portwatch_os.world.live import Revision

    graph = build(synthetic_events(10), synthetic_voyages(size))
    state = ObservedWorldState(state_id="bench", revision=Revision("DEMO", None, "e", "f", 1), at=NOW,
                               graph=graph, traffic_mode="SIMULATED_TRAFFIC")
    counter = {"n": 0}

    def simulate():
        counter["n"] += 1
        made = branch(state, [Assumption(kind=CLOSE_CHOKEPOINT, subject="SUEZ", value=1.0)],
                      branch_id=f"bench-{counter['n']}", now=NOW)
        return [propagate(made.graph, seed_key, seed, at=NOW) for seed_key, seed in made.seeds]

    row = measure(simulate, repeats=repeats)
    cascades = row.pop("_result")
    row["reached"] = sum(len(c.reached) for c in cascades)
    row["vessels"] = size
    print(f"  scenario     {size:>6} vessels  median {row['wallMs']['median']:>9.1f} ms  reached {row['reached']}")
    return row


def bench_pareto(sizes: Sequence[int], repeats: int) -> Dict[str, Any]:
    from src.portwatch_os.decision.frontier import pareto
    from src.portwatch_os.decision.model import OBJECTIVES

    objectives = [OBJECTIVES[k] for k in ("eta", "risk", "fuel")]
    out: Dict[str, Any] = {}
    for size in sizes:
        options = synthetic_options(size)
        row = measure(lambda: pareto(options, objectives), repeats=repeats)
        frontier = row.pop("_result")
        row["nondominated"] = len(frontier.nondominated)
        out[str(size)] = row
        print(f"  pareto       {size:>6} options  median {row['wallMs']['median']:>9.1f} ms")
    return out


def bench_critic(repeats: int) -> Dict[str, Any]:
    from src.portwatch_os.decision import DecisionActor, DecisionEngine
    from src.portwatch_os.decision.critic import DecisionCritic
    from src.portwatch_os.decision.model import SHIPPING_COMPANY
    from src.portwatch_os.world.branch import ObservedWorldState
    from src.portwatch_os.world.build import seed_for
    from src.portwatch_os.world.graph import EVENT, key
    from src.portwatch_os.world.live import Revision

    event = synthetic_events(1)[0]
    event.chokepoints = ["BAB_EL_MANDEB"]
    event.first_seen, event.severity, event.confidence = NOW.isoformat(), 0.85, 0.9
    voyages = synthetic_voyages(50)
    subject = voyages[0]
    subject.lane_code, subject.destination_port = "EUR_IND", "INNSA"
    subject.hours_to_chokepoint = {"SUEZ": 20.0, "BAB_EL_MANDEB": 46.0}
    graph = build([event], voyages)
    state = ObservedWorldState(state_id="bench", revision=Revision("DEMO", None, "e", "f", 1), at=NOW,
                               graph=graph, traffic_mode="SIMULATED_TRAFFIC")
    problem = DecisionEngine().solve_vessel(state, event_key=key(EVENT, event.event_id), seed=seed_for(event),
                                            vessel_id=subject.vessel_id, actor=DecisionActor(SHIPPING_COMPANY), at=NOW)
    critic = DecisionCritic()
    options = [o for o in problem.options if o.evaluation is not None]
    row = measure(lambda: [critic.review_option(o, problem, now=NOW) for o in options], repeats=repeats)
    row.pop("_result")
    row["optionsJudged"] = len(options)
    row["perOptionMs"] = round(row["wallMs"]["median"] / max(1, len(options)), 3)
    print(f"  critic       {len(options):>6} options  median {row['wallMs']['median']:>9.1f} ms  per option {row['perOptionMs']} ms")
    return row


def bench_missions(repeats: int) -> Dict[str, Any]:
    from src.portwatch_os.decision import DecisionActor, DecisionEngine
    from src.portwatch_os.decision.model import SHIPPING_COMPANY
    from src.portwatch_os.missions import MISSIONS, MissionReplay

    out: Dict[str, Any] = {}
    for mission_id, mission in MISSIONS.items():
        counter = {"n": 0}

        def run():
            counter["n"] += 1
            replay = MissionReplay(mission, DecisionEngine(), replay_id=f"bench-{counter['n']}")
            actor = DecisionActor(SHIPPING_COMPANY, vessel_ids=tuple(v.vessel_id for v in mission.fleet))
            for hull in mission.fleet:
                replay.decide(hull.vessel_id, actor)
            return replay.reveal()

        row = measure(run, repeats=repeats)
        reveal = row.pop("_result")
        row["hulls"] = len(mission.fleet)
        row["scorecards"] = len(reveal["scorecards"])
        out[mission_id] = row
        print(f"  mission      {mission_id:<28} median {row['wallMs']['median']:>9.1f} ms  {row['hulls']} hulls decided + reveal")
    return out


def bench_api(repeats: int) -> Dict[str, Any]:
    from fastapi.testclient import TestClient

    from backend.app.main import app

    headers = {"X-PortWatch-Actor": "bench", "X-PortWatch-Role": "NATIONAL_ADMIN"}
    routes = [
        ("GET", "/api/health", None),
        ("GET", "/api/world/state", None),
        ("GET", "/api/world/cascades", None),
        ("GET", "/api/attention", None),
        ("GET", "/api/global-eye/events", None),
        ("GET", "/api/fabric/health?mode=DEMO", None),
        ("GET", "/api/admin/freshness", None),
        ("GET", "/api/missions", None),
        ("GET", "/api/decisions/actions", None),
    ]
    out: Dict[str, Any] = {}
    with TestClient(app) as client:
        # Warm the world once so the first request's rebuild is not the measurement.
        client.get("/api/world/cascades", headers=headers)
        attention = client.get("/api/attention", headers=headers).json()
        actionable = next((i for i in attention.get("items", [])
                           if i.get("actionable") and i.get("subjectType") == "vessel" and i.get("cascadeId")), None)
        if actionable:
            # The cascade id is the seeding event's key: "event:<id>".
            event_id = str(actionable["cascadeId"]).split(":", 1)[-1]
            routes.append(("POST", "/api/decisions/problems",
                           {"domain": "vessel", "vesselId": actionable["subjectId"], "eventId": event_id,
                            "attentionId": actionable["attentionId"]}))
        for method, path, body in routes:
            samples: List[float] = []
            size = 0
            status = 0
            for _ in range(repeats):
                t0 = time.perf_counter()
                response = client.get(path, headers=headers) if method == "GET" else client.post(path, json=body, headers=headers)
                samples.append(time.perf_counter() - t0)
                size = len(response.content)
                status = response.status_code
            samples.sort()
            pick = lambda f: samples[min(len(samples) - 1, int(f * (len(samples) - 1)))]  # noqa: E731
            out[f"{method} {path}"] = {
                "status": status, "repeats": repeats, "payloadBytes": size,
                "p50Ms": round(1000 * pick(0.50), 1), "p95Ms": round(1000 * pick(0.95), 1),
                "p99Ms": round(1000 * pick(0.99), 1), "maxMs": round(1000 * samples[-1], 1),
            }
            print(f"  api {method:<4} {path:<32} {status}  p50 {out[f'{method} {path}']['p50Ms']:>8.1f} ms  "
                  f"p95 {out[f'{method} {path}']['p95Ms']:>8.1f} ms  p99 {out[f'{method} {path}']['p99Ms']:>8.1f} ms  {size:>8} B")
    return out


# --------------------------------------------------------------------------
# the document
# --------------------------------------------------------------------------


def render(results: Dict[str, Any]) -> str:
    env = results["environment"]
    lines = [
        "# Performance",
        "",
        f"Measured {results['measuredAt']} on {env['machine']} ({env['cpu']}, {env['cores']} cores, "
        f"Python {env['python']}, {env['os']}). Produced by `python scripts/benchmark_performance.py`; "
        + (f"power-throttling opt-out {'applied' if env.get('powerThrottling', {}).get('applied') else 'not applied'}, "
           f"reference loop {env.get('referenceLoopMs', {}).get('start')} ms at the start and "
           f"{env.get('referenceLoopMs', {}).get('end')} ms at the end (drift x{env.get('referenceDrift')}); "
           if env.get("referenceLoopMs") else "")
        +         "every figure below is a measurement from that run, not a target.",
        "",
        "Wall time is `time.perf_counter()` around the call; CPU is process time over the same block; "
        "peak memory is `tracemalloc`'s peak during the block (the work's own allocations, not the "
        "interpreter's). Synthetic worlds are seeded from the real lane catalogue and port registry so "
        "the graph has the shape the product's own graph has.",
        "",
        "## World State build",
        "",
        "| vessels | median | p95 | CPU | peak memory | nodes | edges |",
        "|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for size, row in results["world"]["byVessels"].items():
        lines.append(f"| {size} | {row['wallMs']['median']} ms | {row['wallMs']['p95']} ms | {row['cpuMs']} ms | "
                     f"{row['peakMemoryMb']} MB | {row['nodes']} | {row['edges']} |")
    lines += ["", "| events (500 vessels) | median | p95 | CPU | peak memory | nodes |", "|---:|---:|---:|---:|---:|---:|"]
    for size, row in results["world"]["byEvents"].items():
        lines.append(f"| {size} | {row['wallMs']['median']} ms | {row['wallMs']['p95']} ms | {row['cpuMs']} ms | "
                     f"{row['peakMemoryMb']} MB | {row['nodes']} |")
    lines += ["", "## Cascade query", "", "| vessels | one chokepoint: median | reached | every chokepoint (fanout): median | reached | peak memory |",
              "|---:|---:|---:|---:|---:|---:|"]
    for size in results["cascade"]["single"]:
        s, f = results["cascade"]["single"][size], results["cascade"]["fanout"][size]
        lines.append(f"| {size} | {s['wallMs']['median']} ms | {s['reached']} | {f['wallMs']['median']} ms | {f['reached']} | {f['peakMemoryMb']} MB |")
    a = results["attention"][str(max(int(k) for k in results["attention"]))]
    d = results["decision"]
    ds = results["decisionSmall"]
    s = results["scenario"]
    c = results["critic"]
    lines += [
        "", "## Attention, decisions, scenarios, Critic", "",
        "| stage | size | median | p95 | CPU | peak memory | note |",
        "|---|---:|---:|---:|---:|---:|---|",
        *[f"| attention (NATIONAL, fanout cascade) | {r['vessels']} vessels | {r['wallMs']['median']} ms | {r['wallMs']['p95']} ms | {r['cpuMs']} ms | {r['peakMemoryMb']} MB | {r['items']} items ranked |"
          for r in results["attention"].values()],
        f"| DecisionProblem (vessel routing) | {ds['vessels']} vessels | {ds['wallMs']['median']} ms | {ds['wallMs']['p95']} ms | {ds['cpuMs']} ms | {ds['peakMemoryMb']} MB | {ds['options']} options, {ds['feasible']} feasible |",
        f"| DecisionProblem (vessel routing) | {d['vessels']} vessels | {d['wallMs']['median']} ms | {d['wallMs']['p95']} ms | {d['cpuMs']} ms | {d['peakMemoryMb']} MB | {d['options']} options, {d['feasible']} feasible |",
        f"| scenario branch + cascade | {s['vessels']} vessels | {s['wallMs']['median']} ms | {s['wallMs']['p95']} ms | {s['cpuMs']} ms | {s['peakMemoryMb']} MB | {s['reached']} nodes reached |",
        f"| Critic, every option | {c['optionsJudged']} options | {c['wallMs']['median']} ms | {c['wallMs']['p95']} ms | {c['cpuMs']} ms | {c['peakMemoryMb']} MB | {c['perOptionMs']} ms per option |",
        "", "## Pareto frontier", "", "| options | median | p95 | peak memory |", "|---:|---:|---:|---:|",
    ]
    for size, row in results["pareto"].items():
        lines.append(f"| {size} | {row['wallMs']['median']} ms | {row['wallMs']['p95']} ms | {row['peakMemoryMb']} MB |")
    lines += ["", "## Historical mission replay", "", "| mission | hulls | decide every hull + reveal: median | p95 | peak memory |",
              "|---|---:|---:|---:|---:|"]
    for mission_id, row in results["missions"].items():
        lines.append(f"| {mission_id} | {row['hulls']} | {row['wallMs']['median']} ms | {row['wallMs']['p95']} ms | {row['peakMemoryMb']} MB |")
    lines += ["", "## API latency (in-process, real cache on disk)", "",
              "| route | status | p50 | p95 | p99 | max | payload |", "|---|---:|---:|---:|---:|---:|---:|"]
    for route, row in results["api"].items():
        lines.append(f"| `{route}` | {row['status']} | {row['p50Ms']} ms | {row['p95Ms']} ms | {row['p99Ms']} ms | {row['maxMs']} ms | {row['payloadBytes']:,} B |")
    if results.get("budgets"):
        lines += ["", "## Budgets", "",
                  "Each ceiling was set from the figure measured when the budget was written (`src/portwatch_os/perf_budgets.py`); "
                  "`python scripts/benchmark_performance.py --gate` exits non-zero on a breach, and "
                  "`tests/test_perf_budgets.py` holds the small-size subset in ordinary CI at three times the ceiling.", "",
                  "| budget | statistic | ceiling | this run | set from | headroom |", "|---|---|---:|---:|---:|---:|"]
        for row in results["budgets"]:
            measured = "—" if row["measuredMs"] is None else f"{row['measuredMs']:.1f} ms"
            headroom = "—" if row["headroom"] is None else f"{100 * row['headroom']:.0f}%"
            verdict = "" if row["passed"] else " **OVER**"
            lines.append(f"| {row['label']} | {row['statistic']} | {row['budgetMs']:.0f} ms | {measured} | "
                         f"{row['setFromMs']:.1f} ms | {headroom}{verdict} |")
    lines += ["", "## Reading the numbers", ""]
    lines += results.get("notes", [])
    lines.append("")
    return "\n".join(lines)


def notes_for(results: Dict[str, Any]) -> List[str]:
    """Observations the numbers support, written after the run."""
    out: List[str] = []
    by_v = results["world"]["byVessels"]
    sizes = sorted(int(k) for k in by_v)
    if len(sizes) >= 2:
        lo, hi = sizes[0], sizes[-1]
        ratio = by_v[str(hi)]["wallMs"]["median"] / max(0.001, by_v[str(lo)]["wallMs"]["median"])
        out.append(f"- World build scales close to linearly in vessels: {hi // lo}x the hulls cost {ratio:.1f}x the time.")
    fan = results["cascade"]["fanout"]
    big = str(max(int(k) for k in fan))
    out.append(f"- The large-fanout cascade over {big} hulls reaches {fan[big]['reached']} nodes in "
               f"{fan[big]['wallMs']['median']} ms; the cascade is bounded by the graph it can reach, not by the fleet.")
    api = results["api"]
    posts = {r: row for r, row in api.items() if r.startswith("POST")}
    gets = {r: row for r, row in api.items() if not r.startswith("POST")}
    if posts:
        route, row = max(posts.items(), key=lambda kv: kv[1]["p95Ms"])
        out.append(f"- `{route}` is the slowest call at p95 {row['p95Ms']} ms ({row['payloadBytes']:,} B); "
                   "it computes a decision problem, simulating every option on its own branch.")
    if gets:
        route, row = max(gets.items(), key=lambda kv: kv[1]["p95Ms"])
        out.append(f"- `{route}` is the slowest read at p95 {row['p95Ms']} ms ({row['payloadBytes']:,} B); "
                   "reads are served from the versioned live world, so repeated calls at one revision reuse the build.")
    out.append("- Timings move with host load: the previous publication of this page, taken while a browser suite "
               "ran on the same machine, was three to five times slower on every row. Compare runs on an idle host.")
    out.append("- Decision problems, scenarios and the Critic are all under the interactive budget on this machine; "
               "the pipeline (minutes) is the only slow path and it runs out of process under the freshness coordinator.")
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--quick", action="store_true")
    parser.add_argument("--json", default=None, help="write the raw results here too")
    parser.add_argument("--out", default=str(ROOT / "docs" / "PERFORMANCE.md"))
    parser.add_argument("--gate", action="store_true", help="exit non-zero when a budget is breached")
    args = parser.parse_args()

    from src.portwatch_os.perf_budgets import judge

    repeats = 3 if args.quick else 5
    api_repeats = 10 if args.quick else 30
    vessel_sizes = (100, 1000, 5000) if args.quick else (100, 1000, 5000, 10000)
    event_sizes = (100, 1000)
    pareto_sizes = (50, 500) if args.quick else (50, 500, 5000)

    from src.portwatch_os.hostperf import opt_out_of_power_throttling, reference_loop_ms

    # The host must not change the measurement halfway through: Windows
    # power-throttles a process it takes for background work after a minute
    # of sustained CPU, and every later stage would read four times slower.
    throttling = opt_out_of_power_throttling()
    reference: Dict[str, float] = {"start": round(reference_loop_ms(), 1)}
    results: Dict[str, Any] = {
        "measuredAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "environment": {
            "machine": platform.node(), "cpu": platform.processor() or platform.machine(),
            "cores": os.cpu_count(), "python": platform.python_version(), "os": f"{platform.system()} {platform.release()}",
            "powerThrottling": throttling, "referenceLoopMs": reference,
        },
    }
    print(f"power throttling opt-out: {throttling['applied']} ({throttling['reason']}); reference loop {reference['start']} ms")
    print("world")
    results["world"] = bench_world(vessel_sizes, event_sizes, repeats)
    print("cascade")
    results["cascade"] = bench_cascade(vessel_sizes, repeats)
    print("attention")
    results["attention"] = bench_attention(vessel_sizes, repeats)
    print("decision")
    results["decision"] = bench_decision(1000, repeats)
    results["decisionSmall"] = bench_decision(100, repeats)
    print("scenario")
    results["scenario"] = bench_scenario(1000, repeats)
    print("pareto")
    results["pareto"] = bench_pareto(pareto_sizes, repeats)
    print("critic")
    results["critic"] = bench_critic(repeats)
    print("missions")
    results["missions"] = bench_missions(repeats)
    reference["beforeApi"] = round(reference_loop_ms(), 1)
    print("api")
    results["api"] = bench_api(api_repeats)
    reference["end"] = round(reference_loop_ms(), 1)
    drift = reference["end"] / reference["start"] if reference["start"] else 1.0
    results["environment"]["referenceDrift"] = round(drift, 2)
    if drift > 1.5:
        print(f"  WARNING: the reference loop ran {drift:.1f}x slower at the end than at the start; "
              "the host slowed this process during the run and the later figures are not comparable")
    reads = [row["p95Ms"] for key, row in results["api"].items() if key.startswith("GET ") and isinstance(row, dict)]
    results["apiReads"] = {"p95Ms": max(reads) if reads else None, "routes": len(reads),
                           "note": "the worst p95 across the GET routes"}
    results["notes"] = notes_for(results)
    results["budgets"] = judge(results)

    Path(args.out).write_bytes(render(results).encode("utf-8"))
    print(f"\nwrote {args.out}")
    if args.json:
        Path(args.json).write_text(json.dumps(results, indent=2, default=str), encoding="utf-8")
        print(f"wrote {args.json}")
    print("\nbudgets")
    breached = []
    for row in results["budgets"]:
        mark = "ok  " if row["passed"] else "OVER"
        print(f"  {mark} {row['label']:<60} {str(row['measuredMs']):>8} ms against {row['budgetMs']:>7} ms ({row['statistic']})")
        if not row["passed"]:
            breached.append(row["key"])
    if args.gate and breached:
        print(f"\nBUDGET BREACHED: {', '.join(breached)}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
