"""Deployment readiness: the configuration validated against what its mode
requires, with no silent fallback anywhere.

Three deployments exist -- DEMO, RESEARCH, COMMERCIAL (GOVERNMENT is
COMMERCIAL with a redistribution right) -- and each needs different things
to be true before it is honest to start. This module says which, checks
them, and refuses a configuration that would mislead: a mode that was never
stated and would default quietly; a key configured for a product the mode may
not use; a register so old the world would be empty while the screen says
LIVE; a feed that claims to be observed with nothing observed.

A check is PASS, WARN, FAIL or SKIP. A FAIL on a required check makes the
report not ready, and the startup command refuses to start on it. A WARN is
a fact the operator should know and the product will display. Nothing is
fixed here: the coordinator refreshes, the startup command orchestrates; this
module only judges.
"""

from __future__ import annotations

import os
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.portwatch_os.clock import LIVE, get_clock
from src.portwatch_os.fabric.model import (
    AIS,
    COMMERCIAL,
    DEMO,
    GOVERNMENT,
    MARINE,
    MODES,
    MODE_ENV,
    RESEARCH,
    WEATHER,
)

PASS, WARN, FAIL, SKIP = "PASS", "WARN", "FAIL", "SKIP"

ROOT = Path(__file__).resolve().parents[2]

#: What each deployment must have. Capabilities listed under ``required``
#: must resolve to a usable product; those under ``expected`` are reported
#: when unavailable but do not block.
REQUIREMENTS: Dict[str, Dict[str, Any]] = {
    DEMO: {
        "purpose": "the public demo: non-commercial products with attribution, nothing presented as a customer's own",
        "credentials": (),
        "required_capabilities": (WEATHER, MARINE),
        "expected_capabilities": (AIS,),
        "register_must_be_live": True,
    },
    RESEARCH: {
        "purpose": "research: anything the licence permits for non-commercial use",
        "credentials": (),
        "required_capabilities": (WEATHER,),
        "expected_capabilities": (MARINE, AIS),
        "register_must_be_live": False,
    },
    COMMERCIAL: {
        "purpose": "a paying deployment: only products whose licence permits commercial use",
        "credentials": ("OPEN_METEO_API_KEY",),
        "required_capabilities": (WEATHER, MARINE),
        "expected_capabilities": (AIS,),
        "register_must_be_live": True,
    },
    GOVERNMENT: {
        "purpose": "a government deployment: commercial terms plus a redistribution right",
        "credentials": ("OPEN_METEO_API_KEY",),
        "required_capabilities": (WEATHER, MARINE),
        "expected_capabilities": (AIS,),
        "register_must_be_live": True,
    },
}


@dataclass
class Check:
    name: str
    status: str
    detail: str
    required: bool = True
    facts: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {"name": self.name, "status": self.status, "detail": self.detail,
                "required": self.required, "facts": dict(self.facts)}


@dataclass
class DeploymentReport:
    mode: str
    mode_source: str
    checks: List[Check] = field(default_factory=list)

    @property
    def ready(self) -> bool:
        return not any(c.status == FAIL and c.required for c in self.checks)

    @property
    def refusals(self) -> List[Check]:
        return [c for c in self.checks if c.status == FAIL and c.required]

    @property
    def warnings(self) -> List[Check]:
        return [c for c in self.checks if c.status == WARN]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "mode": self.mode,
            "modeSource": self.mode_source,
            "purpose": REQUIREMENTS[self.mode]["purpose"],
            "ready": self.ready,
            "checks": [c.to_dict() for c in self.checks],
            "refusals": [c.name for c in self.refusals],
            "warnings": [c.name for c in self.warnings],
        }


def resolve_mode(mode: Optional[str], env: Optional[Dict[str, str]] = None) -> tuple[str, str, Optional[str]]:
    """The mode, where it came from, and a problem if there is one.

    An argument wins over the environment. Neither being set is a problem:
    the process would default to COMMERCIAL without anyone having said so.
    """
    environ = os.environ if env is None else env
    if mode:
        value = mode.strip().upper()
        if value not in MODES:
            return COMMERCIAL, "argument", f"{mode!r} is not a licence mode; one of {', '.join(MODES)}"
        return value, "argument", None
    raw = environ.get(MODE_ENV)
    if raw is None or not raw.strip():
        return COMMERCIAL, "default", (
            f"{MODE_ENV} is not set. The process would default to COMMERCIAL silently; state the mode "
            f"({', '.join(MODES)}) in the environment or with --mode."
        )
    value = raw.strip().upper()
    if value not in MODES:
        return COMMERCIAL, "env", f"{MODE_ENV}={raw!r} is not a licence mode; one of {', '.join(MODES)}"
    return value, "env", None


def validate(
    *,
    mode: Optional[str] = None,
    env: Optional[Dict[str, str]] = None,
    backend_url: Optional[str] = None,
    terminal_url: Optional[str] = None,
    require_terminal: bool = False,
    coordinator: Any = None,
) -> DeploymentReport:
    """Judge the configuration. Every check is recorded; nothing is fixed."""
    environ = dict(os.environ if env is None else env)
    active, source, problem = resolve_mode(mode, environ)
    report = DeploymentReport(mode=active, mode_source=source)
    rules = REQUIREMENTS[active]

    # -- the mode itself ---------------------------------------------------
    if problem:
        report.checks.append(Check("licence_mode", FAIL, problem, facts={"source": source}))
    else:
        report.checks.append(Check("licence_mode", PASS, f"{active} ({source}): {rules['purpose']}",
                                   facts={"source": source}))

    # -- runtime ----------------------------------------------------------------
    if sys.version_info < (3, 11):
        report.checks.append(Check("python", FAIL, f"Python {sys.version.split()[0]}; 3.11 or newer is required"))
    else:
        report.checks.append(Check("python", PASS, f"Python {sys.version.split()[0]}"))

    # -- credentials ---------------------------------------------------------------
    missing = [name for name in rules["credentials"] if not environ.get(name)]
    if missing:
        report.checks.append(Check(
            "credentials", FAIL,
            f"{active} requires {', '.join(missing)}; without it no marine product may be used and the "
            "deployment would run on nothing while looking configured",
            facts={"missing": missing},
        ))
    else:
        present = [n for n in ("AISSTREAM_API_KEY", "OPEN_METEO_API_KEY") if environ.get(n)]
        report.checks.append(Check("credentials", PASS,
                                   "configured: " + (", ".join(present) if present else "none (none required)"),
                                   facts={"present": present}))

    # -- provider eligibility, and keys that would mislead ----------------------
    from src.portwatch_os.fabric import SignalFabric

    fabric = SignalFabric(mode=active)
    resolution: Dict[str, Any] = {}
    for capability in set(rules["required_capabilities"]) | set(rules["expected_capabilities"]):
        found = fabric.resolve(capability)
        resolution[capability] = {
            # A synthetic product (the labelled replay) is not an observed source:
            # it satisfies nothing a deployment is required to have.
            "available": found.available and not found.synthetic,
            "synthetic": found.synthetic,
            "product": None if found.product is None else found.product.product_id,
            "rejected": [{"productId": pid, "reason": why} for pid, why in found.rejected],
        }
    for capability in rules["required_capabilities"]:
        row = resolution[capability]
        if row["available"]:
            report.checks.append(Check(f"provider:{capability}", PASS, f"{capability} -> {row['product']}",
                                       facts=row))
        else:
            reasons = "; ".join(f"{r['productId']}: {r['reason']}" for r in row["rejected"]) or "no product is catalogued"
            report.checks.append(Check(f"provider:{capability}", FAIL,
                                       f"no {capability} product may be used in {active}: {reasons}", facts=row))
    for capability in rules["expected_capabilities"]:
        row = resolution[capability]
        if row["available"]:
            report.checks.append(Check(f"provider:{capability}", PASS, f"{capability} -> {row['product']}",
                                       required=False, facts=row))
        else:
            reasons = "; ".join(f"{r['productId']}: {r['reason']}" for r in row["rejected"]) or "no product is catalogued"
            stands_in = f"; only the labelled replay ({row['product']}) may stand in" if row["synthetic"] else ""
            report.checks.append(Check(
                f"provider:{capability}", WARN,
                f"no observed {capability} source may be used in {active}{stands_in}; every {capability} "
                f"surface will say so: {reasons}",
                required=False, facts=row,
            ))

    # A key for a product this mode may not use is a misleading configuration:
    # either the mode is wrong or the key is, and starting would hide which.
    ais_key = environ.get("AISSTREAM_API_KEY")
    if ais_key and active in (COMMERCIAL, GOVERNMENT):
        ais = fabric.resolve(AIS)
        if not ais.available or (ais.product and ais.product.product_id != "aisstream-websocket"):
            report.checks.append(Check(
                "misleading:aisstream_key", FAIL,
                f"AISSTREAM_API_KEY is configured but AISStream may not be used in {active} "
                "(commercial use REQUIRES_REVIEW); the key would be ignored while looking live. "
                "Remove the key or run DEMO/RESEARCH.",
            ))
    replay = environ.get("PORTWATCH_AIS_REPLAY_PATH")
    if replay and active in (COMMERCIAL, GOVERNMENT):
        report.checks.append(Check(
            "misleading:ais_replay", FAIL,
            f"PORTWATCH_AIS_REPLAY_PATH is set in {active}; a recording replayed into a commercial "
            "deployment would be drawn as traffic the product is not licensed to show",
        ))
    if replay and not Path(replay).exists():
        report.checks.append(Check("misleading:ais_replay", FAIL,
                                   f"PORTWATCH_AIS_REPLAY_PATH={replay} does not exist"))

    # -- traffic honesty ----------------------------------------------------------
    try:
        from src.portwatch_os.fabric import ais_mode

        traffic = ais_mode(licence_mode=active)
        health = traffic.get("health") or {}
        if traffic["mode"] == "LIVE_AIS" and not health.get("lastGoodObservationAt"):
            report.checks.append(Check("traffic_honesty", FAIL, "LIVE_AIS claimed with no valid observation on record"))
        elif traffic["mode"] == "SIMULATED_TRAFFIC" and traffic.get("providerId") != "ais-replay":
            report.checks.append(Check("traffic_honesty", FAIL,
                                       f"SIMULATED_TRAFFIC attributed to {traffic.get('providerId')}"))
        else:
            report.checks.append(Check("traffic_honesty", PASS, f"{traffic['mode']}: {traffic.get('statement', '')}",
                                       facts={"mode": traffic["mode"], "providerId": traffic.get("providerId")}))
        # Honest is not the same as working. A configured live provider that
        # delivers nothing is a broken feed: a refused credential is a
        # configuration error the operator must fix before the deployment is
        # ready; a socket that has not delivered yet is worth a warning.
        if traffic["mode"] == "UNAVAILABLE" and health.get("health") == "AUTH_FAILED":
            report.checks.append(Check("traffic_feed", FAIL,
                                       f"the configured AIS credential was refused: {health.get('lastError')}",
                                       facts={"health": health.get("health")}))
        elif traffic["mode"] == "UNAVAILABLE" and environ.get("AISSTREAM_API_KEY"):
            report.checks.append(Check("traffic_feed", WARN,
                                       f"a live AIS provider is configured and delivering nothing "
                                       f"({health.get('health')}); the chart shows no traffic until it does",
                                       required=False, facts={"health": health.get("health")}))
    except Exception as exc:  # noqa: BLE001 - a crash here is a failed check, not a crashed validator
        report.checks.append(Check("traffic_honesty", FAIL, f"could not determine the traffic mode: {exc}"))

    # -- storage ------------------------------------------------------------------
    for label, path in (("data/cache", ROOT / "data" / "cache"), ("outputs", ROOT / "outputs"),
                        ("ledger", ROOT / "data" / "ledger")):
        try:
            path.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(dir=path, prefix=".write-check-", delete=True):
                pass
            report.checks.append(Check(f"storage:{label}", PASS, f"{path} is writable"))
        except OSError as exc:
            report.checks.append(Check(f"storage:{label}", FAIL, f"{path} is not writable: {exc}"))

    # -- freshness -------------------------------------------------------------------
    try:
        if coordinator is None:
            from src.portwatch_os.freshness import get_coordinator
            from src.portwatch_os.freshness.jobs import install_product_jobs

            coordinator = install_product_jobs(get_coordinator())
        status = coordinator.status()
        by_name = {row["artifact"]: row for row in status["artifacts"]}
        # The marine grid must exist wherever the mode requires the marine
        # capability; a research deployment may run without one.
        marine_required = MARINE in rules["required_capabilities"]
        for artifact, must_exist in (("port_forecast", True), ("events", True), ("marine", marine_required)):
            row = by_name.get(artifact)
            if row is None:
                continue
            state = row["state"]
            age = row["ageSeconds"]
            human = "never" if age is None else f"{age / 3600:.1f} h old"
            if state == "MISSING" and must_exist:
                report.checks.append(Check(f"freshness:{artifact}", FAIL,
                                           f"{row['label']} has never been produced; {row['reason'] or 'the job must run first'}",
                                           facts={"state": state}))
            elif state == "STALE" and (artifact != "events" or rules["register_must_be_live"]):
                report.checks.append(Check(f"freshness:{artifact}", FAIL,
                                           f"{row['label']} is STALE ({human}); the world built from it would be empty",
                                           facts={"state": state, "ageSeconds": age}))
            elif state in ("EXPIRED", "DUE"):
                report.checks.append(Check(f"freshness:{artifact}", WARN, f"{row['label']} is {state} ({human}); refreshing",
                                           required=False, facts={"state": state, "ageSeconds": age}))
            elif state in ("NOT_APPLICABLE", "SIMULATED"):
                report.checks.append(Check(f"freshness:{artifact}", SKIP, f"{row['label']}: {state}; {row['reason']}",
                                           required=False, facts={"state": state}))
            else:
                report.checks.append(Check(f"freshness:{artifact}", PASS, f"{row['label']} is {state} ({human})",
                                           facts={"state": state, "ageSeconds": age}))
    except Exception as exc:  # noqa: BLE001
        report.checks.append(Check("freshness", FAIL, f"the freshness coordinator could not report: {exc}"))

    # -- the clock ----------------------------------------------------------------------
    clock = get_clock().describe()
    if clock["mode"] != LIVE:
        report.checks.append(Check("world_clock", WARN,
                                   f"the world clock is {clock['mode']} at {clock['now']}, not LIVE; every screen "
                                   "will show the offset", required=False, facts=clock))
    else:
        report.checks.append(Check("world_clock", PASS, "LIVE; the world reads the wall", facts={"mode": LIVE}))

    # -- connectivity -------------------------------------------------------------------
    report.checks.append(_probe("connectivity:backend", backend_url, path="/api/health", required=True))
    report.checks.append(_probe("connectivity:terminal", terminal_url, path="/", required=require_terminal))

    return report


def _probe(name: str, base: Optional[str], *, path: str, required: bool) -> Check:
    if not base:
        return Check(name, SKIP, "not started by this validation", required=False)
    import urllib.error
    import urllib.request

    url = base.rstrip("/") + path
    try:
        with urllib.request.urlopen(url, timeout=10) as response:
            code = response.status
    except urllib.error.HTTPError as exc:
        code = exc.code
    except Exception as exc:  # noqa: BLE001
        return Check(name, FAIL if required else WARN, f"{url}: {type(exc).__name__}: {exc}", required=required)
    if 200 <= code < 400:
        return Check(name, PASS, f"{url} -> {code}", required=required)
    return Check(name, FAIL if required else WARN, f"{url} -> {code}", required=required)


__all__ = ["Check", "DeploymentReport", "FAIL", "PASS", "REQUIREMENTS", "SKIP", "WARN", "resolve_mode", "validate"]
