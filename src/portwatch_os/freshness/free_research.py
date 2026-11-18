"""Opt-in research jobs on the existing single-owner coordinator."""
from src.utils.settings import get_settings

from datetime import timedelta
from src.portwatch_os.clock import LIVE, get_clock, wall_now
from src.portwatch_os.freshness.job import RefreshJob, JobOutcome, RefreshAttemptError, RetryAfterError
from src.portwatch_os.freshness.policy import FreshnessPolicy, ArtifactProbe
from src.portwatch_os.intelligence import free_sources, current_environment as environment
from src.portwatch_os.intelligence.surface_relay import relay_settings
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
    def surface_probe():
        now = wall_now()
        checks = [environment.read("surface", port, at=now).get("lastSuccessfulCheckAt")
                  for port in port_registry.PORTS]
        checked_at = min(map(environment.instant, checks)) if all(checks) else None
        return ArtifactProbe(observed_at=checked_at.replace(minute=0, second=0, microsecond=0) if checked_at else None,
                             source_timestamp=checked_at)

    def surface_run(context):
        hour = context.started_at.replace(minute=0, second=0, microsecond=0)
        rows, failures, attempts = environment.collect_surface_groups(
            port_registry.PORTS, hour, force=context.requested, relay_config=relay_settings())
        for port in port_registry.PORTS:
            if port.locode in rows:
                environment.retain_feedback(port)
        detail = {"ports": len(rows), "httpAttempts": attempts}
        if failures:
            last_error = failures[-1]
            if isinstance(last_error, RetryAfterError):
                raise RetryAfterError(str(last_error), last_error.retry_at, detail=detail) from last_error
            # Preserve successes from the other groups. A later scheduled run
            # can fill the holes in the hour without repeating those groups.
            raise RefreshAttemptError(f"Open-Meteo surface groups failed: {', '.join(key for key in attempts if key != 'ok')}",
                                      detail=detail) from last_error
        if not rows:
            return JobOutcome(skipped_reason="All port groups already checked in this UTC hour", detail=detail)
        checked_at = max(environment.instant(row["lastSuccessfulCheckAt"]) for row in rows.values())
        return JobOutcome(changed=True, observed_at=checked_at, detail=detail)

    result.append(RefreshJob(policy=FreshnessPolicy(
        artifact=environment.SURFACE_BATCH_ARTIFACT, label="All port surface forecasts", provider="Open-Meteo",
        fresh_for=timedelta(hours=1), stale_after=timedelta(hours=2), max_attempts=3,
        backoff_base=timedelta(minutes=5), backoff_cap=timedelta(hours=1),
        rationale="Four sequential location groups per UTC hour, one retry circuit for the surface endpoint."),
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
