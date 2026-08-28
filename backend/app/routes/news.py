from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

from fastapi import APIRouter, HTTPException

router = APIRouter()

ROOT = Path(__file__).resolve().parents[3]
NEWS_BUNDLE_PATH = ROOT / "data" / "cache" / "news_bundle.json"


def read_news_bundle() -> dict:
    if not NEWS_BUNDLE_PATH.exists():
        raise HTTPException(
            status_code=503,
            detail=f"{NEWS_BUNDLE_PATH} not found. Run python backend/pipeline/export_support_cache.py first.",
        )

    with open(NEWS_BUNDLE_PATH, "r", encoding="utf-8") as f:
        bundle = json.load(f)

    return enrich_news_bundle(bundle)


def derive_entity_sentiment(events: list[dict], alerts: list[dict]) -> list[dict]:
    buckets: dict[str, list[float]] = defaultdict(list)
    mentions: dict[str, int] = defaultdict(int)

    for event in events:
        sentiment = float(event.get("sentiment", 0.0))

        entity = str(event.get("entity", "")).strip().upper()
        if entity:
            buckets[entity].append(sentiment)
            mentions[entity] += 1

        for port_code in event.get("affectedPorts", []):
            port = str(port_code).strip().upper()
            if port:
                buckets[port].append(sentiment)
                mentions[port] += 1

    for alert in alerts:
        port = str(alert.get("portCode", "")).strip().upper()
        if not port:
            continue

        severity = str(alert.get("severity", "")).lower()
        alert_sentiment = -0.45 if severity == "severe" else -0.20

        buckets[port].append(alert_sentiment)
        mentions[port] += 1

    rows = []
    for entity, values in buckets.items():
        if not values:
            continue

        rows.append(
            {
                "entity": entity,
                "mentions": int(mentions[entity]),
                "sentiment": round(sum(values) / len(values), 3),
            }
        )

    rows.sort(key=lambda x: (x["mentions"], abs(x["sentiment"])), reverse=True)
    return rows[:10]


def enrich_news_bundle(bundle: dict) -> dict:
    events = bundle.get("events", [])
    alerts = bundle.get("alerts", [])

    if "sentiment" not in bundle or not isinstance(bundle.get("sentiment"), list):
        bundle["sentiment"] = derive_entity_sentiment(events, alerts)

    if "summary" not in bundle:
        bundle["summary"] = {}

    bundle["summary"]["dataSource"] = bundle["summary"].get(
        "dataSource",
        "data/cache/news_bundle.json",
    )

    return bundle


@router.get("/news")
def news_bundle() -> dict:
    return read_news_bundle()


@router.get("/news/entity/{entity}")
def news_for_entity(entity: str) -> dict:
    bundle = read_news_bundle()
    entity_lower = entity.lower()

    events = [
        event
        for event in bundle.get("events", [])
        if entity_lower in str(event.get("entity", "")).lower()
        or entity_lower in str(event.get("text", "")).lower()
        or any(entity_lower in str(p).lower() for p in event.get("affectedPorts", []))
    ]

    alerts = [
        alert
        for alert in bundle.get("alerts", [])
        if entity_lower in str(alert.get("portCode", "")).lower()
        or entity_lower in str(alert.get("text", "")).lower()
    ]

    sentiment = derive_entity_sentiment(events, alerts)

    return {
        "events": events,
        "alerts": alerts,
        "sentiment": sentiment,
    }
