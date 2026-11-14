"""Opt-in research jobs on the existing single-owner coordinator."""
from src.utils.settings import get_settings

from datetime import timedelta
from random import uniform
from src.portwatch_os.clock import LIVE, get_clock, wall_now
from src.portwatch_os.freshness.job import RefreshJob, JobOutcome
from src.portwatch_os.freshness.policy import FreshnessPolicy, ArtifactProbe
from src.portwatch_os.intelligence import free_sources, current_environment as environment
from src.utils import port_registry


def eligibility():
    if (get_settings().PORTWATCH_RESEARCH_SOURCE_PROFILE or get_settings().PORTWATCH_LOCAL_PROVIDER_PROFILE) != '1': return 'Research source profile is not enabled'
    if get_clock().state.mode != LIVE: return 'Provider collection is paused during replay'
    from src.portwatch_os.deployment import resolve_mode
    if resolve_mode(None)[0]=='COMMERCIAL': return 'Free noncommercial research profile is unavailable in commercial mode'
    return None


def current_weather_eligibility():
    settings = get_settings()
    if (settings.PORTWATCH_CURRENT_WEATHER_AUTOREFRESH or '1').lower() in ('0', 'false', 'no', 'off'):
        return 'Current weather collection is disabled'
    if get_clock().state.mode != LIVE:
        return 'Provider collection is paused during replay'
    from src.portwatch_os.deployment import resolve_mode
    if resolve_mode(None)[0] == 'COMMERCIAL':
        return 'The free Open-Meteo product is not permitted in commercial mode'
    return None


def jobs():
    result=[]
    for key,spec in free_sources.PRODUCTS.items():
        def probe(key=key):
            row=free_sources.public_product(key)
            return ArtifactProbe(observed_at=free_sources.instant(row['lastSuccessfulCheckAt']) if row['lastSuccessfulCheckAt'] else None)
        def run(context,key=key):
            receipt=free_sources.collect(key)
            if not receipt['ok']: raise RuntimeError(receipt['error'])
            return JobOutcome(changed=True,observed_at=free_sources.instant(receipt['lastSuccessfulCheckAt']),detail=receipt)
        cadence=timedelta(seconds=spec['cadence'])
        result.append(RefreshJob(policy=FreshnessPolicy(artifact='free_'+key,label=spec['product'],provider=spec['provider'],
            fresh_for=cadence,lead=cadence/10,stale_after=cadence*2,max_attempts=2,
            backoff_base=timedelta(minutes=5),backoff_cap=timedelta(hours=3),
            rationale='Explicit noncommercial research. Retained public products; provider cadence and value kind remain separate.'),
            probe=probe,run=run,eligibility=eligibility))
    # A single scheduler record serializes all surface calls, including retries.
    # Give each deployment a different phase within the last few minutes of the hour.
    surface_lead = timedelta(seconds=uniform(180, 300))

    def surface_probe():
        now = wall_now()
        checks = [environment.read("surface", port, at=now).get("lastSuccessfulCheckAt")
                  for port in port_registry.PORTS]
        return ArtifactProbe(observed_at=min(map(environment.instant, checks)) if all(checks) else None)

    def surface_run(context):
        rows = environment.refresh_surface_batch(port_registry.PORTS)
        for port in port_registry.PORTS:
            environment.retain_feedback(port)
        checked_at = next(iter(rows.values()))["lastSuccessfulCheckAt"]
        return JobOutcome(changed=True, observed_at=environment.instant(checked_at),
                          detail={"ports": len(rows)})

    result.append(RefreshJob(policy=FreshnessPolicy(
        artifact=environment.SURFACE_BATCH_ARTIFACT, label="All port surface forecasts", provider="Open-Meteo",
        fresh_for=timedelta(hours=1), lead=surface_lead, stale_after=timedelta(hours=2), max_attempts=3,
        backoff_base=timedelta(minutes=5), backoff_cap=timedelta(hours=1),
        rationale="One multi-location hourly forecast and one retry circuit for the surface endpoint."),
        probe=surface_probe, run=surface_run, eligibility=current_weather_eligibility))
    for port in port_registry.PORTS:
        def probe(port=port):
            row=environment.read('marine',port)
            return ArtifactProbe(observed_at=environment.instant(row['availableAt']) if row.get('availableAt') else None)
        def run(context,port=port):
            row=environment.refresh('marine',port,force=True,strict=True)
            if row['status']!='CURRENT': raise RuntimeError(row.get('reason','No current qualified forecast'))
            environment.retain_feedback(port)
            return JobOutcome(changed=True,observed_at=environment.instant(row['availableAt']),detail={'snapshotId':row['snapshotId']})
        result.append(RefreshJob(policy=FreshnessPolicy(artifact=f'current_marine_{port.locode}',label=f'{port.name} marine forecast',provider='Open-Meteo',
            fresh_for=timedelta(hours=1),lead=timedelta(minutes=5),stale_after=timedelta(hours=2),max_attempts=2,
            backoff_base=timedelta(minutes=5),backoff_cap=timedelta(hours=1),
            rationale='Current hourly port forecast, independent of lagging activity observations; not station measurements.'),
            probe=probe,run=run,eligibility=current_weather_eligibility))
    def hazard_probe():
        row=environment.read('hazards',port_registry.PORTS[0])
        return ArtifactProbe(observed_at=environment.instant(row['availableAt']) if row.get('availableAt') else None)
    def hazard_run(context):
        row=environment.refresh('hazards',port_registry.PORTS[0],force=True,strict=True)
        if row['status']!='CURRENT': raise RuntimeError(row.get('reason','No qualified hazard response'))
        return JobOutcome(changed=True,observed_at=environment.instant(row['availableAt']),detail={'snapshotId':row['snapshotId']})
    result.append(RefreshJob(policy=FreshnessPolicy(artifact='current_gdacs',label='GDACS regional context',provider='GDACS',
        fresh_for=timedelta(minutes=30),lead=timedelta(minutes=3),stale_after=timedelta(hours=1),max_attempts=2,
        backoff_base=timedelta(minutes=5),backoff_cap=timedelta(hours=1),
        rationale='Check regional hazard receipts frequently enough to flag stale context during an active event.'),
        probe=hazard_probe,run=hazard_run,eligibility=current_weather_eligibility))
    return result
