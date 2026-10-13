"""Public scene projections and request-local simulations; no operator state writes."""
from datetime import datetime, timezone

from backend.app.routes.public_research import explore, optional, safe_url
from backend.app.services import cache_service as cache
from src.portwatch_os.clock import wall_now
from src.portwatch_os.learning.weather_feedback import instant
from src.utils import port_registry


def workspace(mode="current", at=None):
    now = wall_now()  # wall-clock: actual cache receipt and source freshness.
    moment = instant(at) if at else now
    if mode == "current":
        moment = now
    data = explore()
    provenance = optional(cache.get_provenance, {}).get("sources", {})
    bundle = optional(cache.get_news_bundle, {})
    exported_at = optional(cache.get_live_status, {}).get("exportedAt")

    def available_clock(value):
        try:
            return isinstance(value, (str, datetime)) and instant(value) <= min(moment, now)
        except (ValueError, TypeError):
            return False

    def availability(key, publication):
        # The current cache is a single vintage. Its source clock alone cannot
        # prove that a subsequently rewritten document was available in replay.
        source = provenance.get(key, {})
        if not source.get("fetched_at") or not publication:
            return None
        try:
            clocks = [instant(source["fetched_at"]), instant(publication)]
            receipt = max(clocks)
            return receipt.isoformat() if source.get("isReal") is True and receipt <= min(moment, now) else None
        except (ValueError, TypeError, KeyError, AttributeError):
            return None

    # Initial pipeline exports use the enclosing live-status export clock;
    # independently refreshed news bundles carry their own refreshedAt.
    news_receipt = availability("Maritime events (GDELT + GDACS)", bundle.get("refreshedAt") or exported_at)
    ports_receipt = availability("Port activity (IMF PortWatch)", exported_at)
    from src.portwatch_os.global_eye.ingest import from_news_bundle, CHOKEPOINT_GEO
    from src.portwatch_os.global_eye.exposure import TRADE_LANES
    from src.portwatch_os.decision.routing import primary_route
    events, _ = from_news_bundle(bundle) if news_receipt else ([], [])
    locations = {e.event_id: e.to_dict() for e in events}
    data["events"] = [{**e, "coordinates": locations.get(e["eventId"], {}).get("coordinates"),
        "chokepoints": locations.get(e["eventId"], {}).get("chokepoints", []),
        "availableAt": news_receipt}
        for e in data["events"] if news_receipt and available_clock(e.get("firstSeen"))]
    for p in data["ports"]:
        record = port_registry.resolve(p["code"])
        p["location"] = {"lat": record.lat, "lon": record.lon}
        p["capacityMeaning"] = "Port registry context; live berth allocation and draught are unavailable."
        p["availableAt"] = ports_receipt
        if not ports_receipt:
            p.update(forecasts=[], observedAt=None, congestionIndex=None)
        p["forecasts"] = [f for f in p["forecasts"] if available_clock(f.get("originDate"))]
    weather_receipt = availability("Marine weather (Open-Meteo)", exported_at)
    weather = optional(cache.get_weather_by_port, {}) if weather_receipt else {}

    def weather_clock(value):
        try:
            clock = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
            return clock.replace(tzinfo=timezone.utc) if clock.tzinfo is None else clock.astimezone(timezone.utc)
        except (TypeError, ValueError):
            return datetime.max.replace(tzinfo=timezone.utc)

    data["weather"] = [{"portCode": code, "timestampMeaning": "Daily cache clock uses UTC; UTC assumed when offset is absent.", **{k: row.get(k) for k in
        ("observedAt", "windKnots", "gustKnots", "rainfallMm24h", "waveHeightM", "visibilityKm", "dataSource")}}
        | {"availableAt": weather_receipt, "rawObservedAt": row["observedAt"],
           "observedAt": weather_clock(row["observedAt"]).isoformat(),
           "status": "STALE" if (now-weather_clock(row["observedAt"])).total_seconds() > 48*3600 else "CACHED"}
        for code, row in weather.items() if row.get("observedAt") and weather_clock(row["observedAt"]) <= min(moment, now)]
    data["routes"] = []
    for lane in TRADE_LANES.values():
        port = port_registry.resolve(lane.india_ports[0])
        if not port:
            continue
        geometry, sources = primary_route(lane.code, port.locode)
        data["routes"].append({"id": lane.code, "name": lane.name, "portCodes": list(lane.india_ports),
            "chokepoints": list(lane.chokepoints), "positions": geometry, "sources": sources,
            "meaning": "Non-navigational route catalogue; no current voyage is inferred."})
    data["chokepoints"] = [{"id": k, "lat": v[0], "lon": v[1], "name": v[2]} for k, v in CHOKEPOINT_GEO.items()]
    from src.portwatch_os.intelligence.context import economic_context
    data["economics"] = economic_context(cache.CACHE_DIR) if mode != "replay" else []
    data["cameras"] = []
    if mode == "current":
        from src.portwatch_os.intelligence.cameras import CameraRegistry
        import json
        import sqlite3
        path = CameraRegistry().path
        try:
            if path.exists():
                with sqlite3.connect(path.resolve().as_uri()+"?mode=ro", uri=True) as connection:
                    for row in connection.execute("SELECT record FROM cameras ORDER BY id"):
                        c = json.loads(row[0])
                        if c["access"] == "public" and c["enabled"] and safe_url(c["mediaUrl"]):
                            data["cameras"].append({k: c.get(k) for k in ("id", "name", "portCode", "lat", "lon", "coverage", "viewpoint", "mediaUrl", "feedType", "source", "rightsBasis", "health", "lastFrameAt", "healthNote")})
        except (OSError, sqlite3.DatabaseError, ValueError, KeyError):
            pass
    data.update(asOf=moment.isoformat(), collectedAt=now.isoformat(), timeMode=mode, vessels=[],
        vesselMeaning="No verified public AIS feed is connected. The configurable scenario vessel is simulated, not an observed ship.",
        timeMeaning="Visitor-local time; shared operator clocks and collectors remain untouched. Unavailable historical publication vintages are withheld.")
    data["layers"] = [
        {"id": "events", "label": "News & security", "status": "CACHED" if data["events"] else "UNAVAILABLE", "coverage": "Source-linked maritime reports; locations may be regional estimates."},
        {"id": "routes", "label": "Shipping routes", "status": "CATALOGUE", "coverage": "Ten trade lanes to Indian ports; comparison geometry, not navigation."},
        {"id": "vessels", "label": "Vessels", "status": "SCENARIO_ONLY", "coverage": data["vesselMeaning"]},
        {"id": "weather", "label": "Weather", "status": "CACHED" if data["weather"] else "UNAVAILABLE", "coverage": "Dated port weather snapshots; no continuous global weather field in this iteration."},
        {"id": "economics", "label": "Economics", "status": "CACHED" if any(e["value"] is not None for e in data["economics"]) else "UNAVAILABLE", "coverage": "FRED context. Bunker and charter rates in comparisons are explicit visitor assumptions."},
        {"id": "infrastructure", "label": "Ports & infrastructure", "status": "CATALOGUE", "coverage": "Registered ports and chokepoints; road, rail and live berth feeds not connected."},
        {"id": "cameras", "label": "Port cameras", "status": "UNVERIFIED" if data["cameras"] else "UNAVAILABLE", "coverage": "Only enabled public registry feeds; frame health is shown. Live media withheld outside current view."},
    ]
    return data


def simulate(*, lane_code, port_code, hours_to_risk, speed, closure_hours, severity, wave_m, charter_day, bunker_price, fuel_burn, at=None, risk_chokepoint=None):
    from src.portwatch_os.global_eye.exposure import TRADE_LANES, VesselVoyage
    from src.portwatch_os.global_eye.ingest import CHOKEPOINT_GEO
    from src.portwatch_os.global_eye.model import GlobalEvent
    from src.portwatch_os.world.build import build_world, seed_for
    from src.portwatch_os.world.branch import ObservedWorldState
    from src.portwatch_os.world.live import Revision
    from src.portwatch_os.world.graph import EVENT, key
    from src.portwatch_os.decision.engine import DecisionEngine
    from src.portwatch_os.decision.model import DecisionActor, SHIPPING_COMPANY
    from src.portwatch_os.finance.basis import CostBasis, assumption
    from src.portwatch_os.fabric.marine import MarineForecastCell, MarineSample
    lane = TRADE_LANES.get(lane_code)
    port = port_registry.resolve(port_code)
    if not lane or not lane.chokepoints or not port or port.locode not in {port_registry.resolve(p).locode for p in lane.india_ports if port_registry.resolve(p)}:
        raise ValueError("Choose a catalogued chokepoint lane and one of its destination ports")
    moment = instant(at) if at else wall_now()  # wall-clock: actual creation time of an isolated visitor simulation.
    choke = risk_chokepoint or lane.chokepoints[0]
    if choke not in lane.chokepoints:
        raise ValueError("The restriction must be at a chokepoint on the selected lane")
    risk_index = lane.chokepoints.index(choke)
    location = CHOKEPOINT_GEO[choke]
    event = GlobalEvent(event_id="public-assumed-closure", title=f"Assumed {closure_hours:g} h restriction at {location[2]}",
        category="chokepoint_disruption", region=location[2], lat=location[0], lon=location[1],
        geolocation_basis="catalogue scenario", first_seen=moment.isoformat(), last_seen=moment.isoformat(),
        severity=severity, confidence=1.0, horizon_hours=closure_hours, chokepoints=[choke], data_source="VISITOR_ASSUMPTION")
    vessel = VesselVoyage(vessel_id="public-scenario-vessel", name="Scenario vessel · not observed AIS", lane_code=lane_code,
        destination_port=port.locode, service_speed_kn=speed, hours_to_chokepoint={c: hours_to_risk+(i-risk_index)*30 for i,c in enumerate(lane.chokepoints)}, source="PUBLIC_SCENARIO")
    graph = build_world(events=[event], voyages=[vessel], now=moment)
    state = ObservedWorldState("visitor-local", Revision("DEMO", None, "public assumption", "scenario vessel", 0), moment, graph, "SIMULATED_TRAFFIC")
    basis = CostBasis()
    for primitive, value in (("charter_day", charter_day), ("bunker_price_t", bunker_price), ("fuel_burn_t_day", fuel_burn)):
        basis.add(assumption(primitive, value, "USD", entered_by="Public visitor", purpose="isolated shipping scenario"))

    class AssumedSea:
        def sample(self, lat, lon, when):
            # A uniform what-if field, never substituted for an observation.
            return MarineSample(MarineForecastCell(lat, lon, when, moment, wave_height_m=wave_m,
                wave_direction_deg=0, provider_id="visitor-assumption", product_id="uniform-sea-scenario", label="ASSUMED UNIFORM SEA"), 0, 0)

    engine = DecisionEngine(basis=basis, ledger=None)
    problem = engine.solve_vessel(state, event_key=key(EVENT, event.event_id), seed=seed_for(event),
        vessel_id=vessel.vessel_id, actor=DecisionActor(SHIPPING_COMPANY), at=moment, grid=AssumedSea(), decision_id="public-scenario")
    result = problem.to_dict()
    return {"meaning": "SIMULATION: request-local constrained decision engine. No shared world, ledger, advisory or approval is written.",
        "at": moment.isoformat(), "inputs": {"laneCode": lane_code, "portCode": port.locode, "hoursToRisk": hours_to_risk,
        "speedKn": speed, "riskChokepoint": choke, "closureHours": closure_hours, "severity": severity, "assumedWaveM": wave_m,
        "charterUsdDay": charter_day, "bunkerUsdTonne": bunker_price, "fuelTonnesDay": fuel_burn},
        "forecastConnection": "Port congestion forecasts are contextual evidence, not a calibrated causal input to this routing simulation.",
        "uncertainty": "Closure duration and severity, uniform seas, service speed and prices are assumptions. Other chokepoint clocks use an approximate 30-hour spacing relative to the selected restriction. Vessel position is derived from these clocks and route geometry, not AIS. The engine's risk and fuel indices are model proxies, not calibrated probabilities or measured savings. Berth/draught and cargo constraints lack verified inputs.",
        "position": problem.evidence["position"], "options": result["options"], "recommendation": result["recommendation"],
        "availableActions": result["availableActions"], "doNothingStatement": problem.do_nothing_statement,
        "frontier": result["frontier"], "observedOutcome": None}
