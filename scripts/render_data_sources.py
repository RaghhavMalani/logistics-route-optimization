"""Render docs/DATA_SOURCES.md from the product catalogue.

The document is generated rather than written so that a source cannot be
described in prose and absent from the code, and so that every licence line
in it is the *verified* one -- the same four-state permission, the same
quoted finding and the same review date the trust surface shows. Run after
any change to ``src/portwatch_os/fabric/products.py``:

    python scripts/render_data_sources.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.portwatch_os.fabric.adapters import ADAPTERS  # noqa: E402
from src.portwatch_os.fabric.licence import (  # noqa: E402
    ALLOWED,
    PROHIBITED,
    REQUIRES_REVIEW,
    UNKNOWN,
)
from src.portwatch_os.fabric.products import default_catalogue  # noqa: E402

OUT = ROOT / "docs" / "DATA_SOURCES.md"
TARIFFS = ROOT / "data" / "tariffs" / "public_tariffs.json"

UNIT_OF = {
    "port_dues_grt": "per GRT per entry",
    "berth_hire_grt_hour": "per GRT per hour",
    "anchorage_grt_hour": "per GRT per hour",
    "pilotage_grt": "per GRT per movement",
}


def tariff_lines() -> list:
    """The published port tariffs the financial twin prices against.

    Read from the tariff file itself, so a schedule cannot be described here
    that the engine does not hold, and the reuse state shown is the one
    recorded with the evidence.
    """
    import json

    body = json.loads(TARIFFS.read_text(encoding="utf-8"))
    lines = [
        "## Published port tariffs",
        "",
        body["note"],
        "",
        f"Reviewed by {body['reviewedBy']}.",
        "",
        "| Schedule | Authority | Scope | Validity | Reuse | Retrieved | Document |",
        "|---|---|---|---|---|---|---|",
    ]
    for s in body["schedules"]:
        prov = s["provenance"]
        lines.append(
            f"| `{s['scheduleId']}` | {s['authority']} | `{s['scope']}` | "
            f"{s.get('validFrom') or '—'} → {s.get('validTo') or '—'} | `{s['reuse']}` | "
            f"{prov['retrievedAt']} | [{s['title']}]({prov['url']}) · sha256 `{prov['sha256'][:12]}…` |"
        )
    lines.append("")
    for s in body["schedules"]:
        lines.append(f"### {s['title']}")
        lines.append("")
        evidence = s.get("reuseEvidence")
        if isinstance(evidence, dict):
            lines.append(f"Reuse checked at {evidence.get('checked')} on {evidence.get('checkedAt')}:")
            lines.append("")
            if evidence.get("verbatim"):
                lines.append(f"> {evidence['verbatim']}")
                lines.append("")
            if evidence.get("finding"):
                lines.append(evidence["finding"])
                lines.append("")
        elif evidence:
            lines.append(f"> {evidence}")
            lines.append("")
        if s["provenance"].get("fxRule"):
            lines.append(f"FX rule, verbatim: *{s['provenance']['fxRule']}*")
            lines.append("")
        if s["provenance"].get("validityNote"):
            lines.append(s["provenance"]["validityNote"])
            lines.append("")
        lines.append("| Primitive | Rate | Unit | Applies to | Page · section |")
        lines.append("|---|---:|---|---|---|")
        for r in s["rates"]:
            applies = ", ".join(v for v in (r.get("vesselStatus"), r.get("vesselType")) if v) or "all"
            unit = r.get("unit") or UNIT_OF.get(r["primitive"], "")
            # Tonnage bands: a flat per-GRT rate for the band, or a base amount
            # for the first N GRT plus the rate on every additional one.
            tier = ""
            lo, hi, base = r.get("tierMinGrt"), r.get("tierMaxGrt"), r.get("tierBaseAmount")
            if base is not None:
                tier = f" per additional GRT above {lo:,}, after {base:,} {r['currency']} for the first {lo:,}"
            elif lo or hi:
                band = f"up to {hi:,} GRT" if not lo else (f"{lo + 1:,}–{hi:,} GRT" if hi else f"above {lo:,} GRT")
                tier = f" ({band})"
            lines.append(
                f"| `{r['primitive']}` | {r['value']} {r['currency']}{tier} | {unit} | {applies} | "
                f"p.{r['page']} · {r['section']} |"
            )
        lines.append("")
    if body.get("investigated"):
        lines.append("### Investigated and not ingested")
        lines.append("")
        for row in body["investigated"]:
            lines.append(f"- **{row['authority']}** — {row['url']} — checked {row['checkedAt']}: {row['finding']}")
        lines.append("")
    return lines


def mission_lines() -> list:
    """The sources a historical mission's chronology is transcribed from."""
    from src.portwatch_os.missions.catalogue import MISSIONS

    lines = [
        "## Historical mission sources",
        "",
        "A mission's chronology and outcome are transcribed from the sources below and",
        "nothing else; the hulls in it are illustrative and say so. The replay serves an",
        "observation only once the replay clock has passed it.",
        "",
    ]
    for mission in MISSIONS.values():
        lines.append(f"### {mission.name}")
        lines.append("")
        lines.append("| Source | Kind | Retrieved | Note |")
        lines.append("|---|---|---|---|")
        for s in mission.sources:
            lines.append(f"| [{s.name}]({s.url}) | {s.kind} | {s.retrieved_at} | {s.note or ''} |")
        lines.append("")
    return lines

STATE_WORD = {
    ALLOWED: "allowed",
    PROHIBITED: "**prohibited**",
    REQUIRES_REVIEW: "*requires review*",
    UNKNOWN: "unknown",
}


def adapters_by_product() -> dict:
    """Which product each shipped adapter serves. Read from the adapters, not typed."""
    from src.portwatch_os.fabric.marine import OpenMeteoMarineAdapter

    served = {}
    for cls in (*ADAPTERS, OpenMeteoMarineAdapter):
        product_id = getattr(cls, "product_id", None)
        if isinstance(product_id, str):
            served[product_id] = cls.__name__
    # The Open-Meteo adapters choose their product by key at runtime; both
    # products are served by the same code.
    served.setdefault("open-meteo-free", "OpenMeteoAdapter, OpenMeteoMarineAdapter")
    served.setdefault("open-meteo-customer", "OpenMeteoAdapter, OpenMeteoMarineAdapter")
    return served


def render() -> str:
    providers = default_catalogue()
    served = adapters_by_product()
    lines = [
        "# Data sources",
        "",
        "Every provider this deployment knows about, every product it offers, the",
        "licence *as verified*, and whether anything in this build reads it.",
        "Generated by `scripts/render_data_sources.py` from the product catalogue,",
        "so a source cannot be described here and absent from the code, and a",
        "permission cannot be written here that the catalogue has not recorded",
        "evidence for.",
        "",
        "Licence is answered per **product**, not per provider: Open-Meteo's free",
        "API is non-commercial and its subscription is not, and they are the same",
        "company. Each permission is one of four states. `allowed` and",
        "`prohibited` are what the published terms say. `requires review` means",
        "the terms were looked for and not found, or do not address the question",
        "-- and a permission nobody has verified is not a permission, so it",
        "resolves like a prohibition for COMMERCIAL and GOVERNMENT deployments.",
        "",
        "A name in this table is **not** a claim of integration. `PLANNED` means",
        "named with no adapter, listed so the commercial path is visible rather",
        "than implied.",
        "",
        "## Matrix",
        "",
        "| Provider | Product | Capabilities | Status | Adapter | Commercial | Government | Redistribute | Attribution | Credential | Cost | Latency |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for provider in sorted(providers, key=lambda p: p.name.lower()):
        for product in provider.products:
            policy = product.policy
            lines.append(
                "| {provider} | `{pid}` | {caps} | `{status}` | {adapter} | {com} | {gov} | {redist} | {attr} | {cred} | {cost} | {lat} |".format(
                    provider=provider.name,
                    pid=product.product_id,
                    caps=", ".join(product.capabilities),
                    status=product.status,
                    adapter=served.get(product.product_id, "none"),
                    com=STATE_WORD[policy.commercial_use],
                    gov=STATE_WORD[policy.government_use],
                    redist=STATE_WORD[policy.redistribution],
                    attr="required" if policy.attribution_required else "not required",
                    cred=product.credential_type.lower(),
                    cost=product.cost_class.lower(),
                    lat=product.latency_class.lower(),
                )
            )
    lines += ["", "## Licence evidence", ""]
    lines += [
        "What was checked, when, and what it said. Where the finding quotes the",
        "terms, the quotation is verbatim. Where no terms were found, that is the",
        "finding.",
        "",
    ]
    for provider in sorted(providers, key=lambda p: p.name.lower()):
        lines.append(f"### {provider.name}")
        lines.append("")
        if provider.homepage:
            lines.append(f"<{provider.homepage}>")
            lines.append("")
        for product in provider.products:
            policy = product.policy
            evidence = policy.evidence
            lines.append(f"#### `{product.product_id}` — {product.name}")
            lines.append("")
            if product.synthetic:
                lines.append("**Synthetic.** Modelled rather than observed, and labelled as such wherever drawn.")
                lines.append("")
            lines.append(
                f"Commercial use {STATE_WORD[policy.commercial_use]} · government use "
                f"{STATE_WORD[policy.government_use]} · redistribution {STATE_WORD[policy.redistribution]}"
                + (f" · data licence {policy.data_licence}" if policy.data_licence else "")
            )
            lines.append("")
            if policy.summary:
                lines.append(policy.summary)
                lines.append("")
            if evidence is not None:
                if evidence.terms_url:
                    lines.append(f"Terms: <{evidence.terms_url}>")
                    lines.append("")
                if evidence.checked_urls:
                    lines.append("Checked: " + ", ".join(f"<{u}>" for u in evidence.checked_urls))
                    lines.append("")
                if evidence.reviewed_at:
                    lines.append(f"Reviewed: {evidence.reviewed_at}")
                    lines.append("")
                if evidence.finding:
                    lines.append(f"> {evidence.finding}")
                    lines.append("")
            if product.notes:
                lines.append(product.notes)
                lines.append("")
            lines.append(f"Coverage: {product.coverage}." + (f" Endpoint: `{product.endpoint}`." if product.endpoint else ""))
            lines.append("")
    lines += [
        "## What this build reads",
        "",
        "| Capability | Adapter | Product | Read on the request path? |",
        "|---|---|---|---|",
        "| `ais` | `AisStreamAdapter` | `aisstream-websocket` | no — a server-side websocket client feeds an in-memory track store |",
        "| `weather` | `OpenMeteoAdapter` | `open-meteo-free` / `open-meteo-customer` | no — the pipeline's forecast artefact |",
        "| `marine` | `OpenMeteoMarineAdapter` | `open-meteo-free` / `open-meteo-customer` | no — a background refresh keeps a cached grid |",
        "| `events` | `GdeltAdapter` | `gdelt-events` | no — the pipeline's news bundle |",
        "",
        "Registered with a licence and read by nothing yet: `disaster`, `seismic`,",
        "`fire`, `vessel_registry`, `port_stats`, `geography`.",
        "",
    ]
    lines += tariff_lines()
    lines += mission_lines()
    lines += [
        "## Deployment mode",
        "",
        "`PORTWATCH_LICENCE_MODE` names the mode a process runs in (`RESEARCH`,",
        "`DEMO`, `COMMERCIAL`, `GOVERNMENT`). It defaults to `COMMERCIAL`, the most",
        "restrictive reading: a deployment that has not said what it is gets only",
        "the products every deployment may use, and in particular never calls the",
        "Open-Meteo free host. A request may ask to *view* the world in another",
        "mode with `?mode=`; the view is gated the same way.",
        "",
    ]
    return "\n".join(lines)


if __name__ == "__main__":
    OUT.write_text(render(), encoding="utf-8", newline="\n")
    print(f"wrote {OUT}")
