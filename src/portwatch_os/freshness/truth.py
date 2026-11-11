"""Shared wall-clock freshness truth for API health, Sources and workspace SSE."""
from datetime import datetime, timezone


def instant(value):
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
        return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed.astimezone(timezone.utc)
    except (ValueError, TypeError):
        return None


def classify(at, now, budget, *, valid_through=None):
    at = instant(at)
    through = instant(valid_through)
    if at is None or at > now:
        return 'unavailable', None
    age = (now - at).total_seconds()
    current = age <= budget and (valid_through is None or through is not None and through >= now)
    return ('live' if current else 'stale'), age


def retained_sources(now):
    from backend.app.services import cache_service as cache
    from src.portwatch_os.freshness import get_coordinator
    from src.portwatch_os.freshness.jobs import install_product_jobs
    from src.portwatch_os.intelligence import current_environment
    from src.utils.port_registry import PORTS
    coordinator = install_product_jobs(get_coordinator())

    def job_metrics(artifacts):
        jobs = [coordinator.attempt_metrics(key, now) for key in artifacts if key in coordinator.artifacts()]
        successes = [row['lastGood']['finishedAt'] for row in jobs if row.get('lastGood')]
        errors = sorted((row for row in jobs if row.get('lastErrorAt')), key=lambda row: row['lastErrorAt'], reverse=True)
        count = sum(row.get('attempts7d', 0) for row in jobs)
        return {'lastSuccess': max(successes) if successes else None,
                'lastError': errors[0]['lastError'] if errors else None,
                'lastErrorAt': errors[0]['lastErrorAt'] if errors else None,
                'attempts7d': count,
                'successRate7d': sum((row.get('successRate7d') or 0) * row.get('attempts7d', 0) for row in jobs) / count if count else None,
                'circuit': 'open' if any(row.get('circuit') == 'OPEN' for row in jobs) else 'closed'}

    provenance = cache.get_provenance().get('sources', {})
    activity = provenance.get('Port activity (IMF PortWatch)', {})
    observed = activity.get('observed_at')
    state, age = classify(observed, now, 72 * 3600)
    shared = job_metrics(['port_forecast'])
    rows = [{'id': 'imf-portwatch-data', 'name': 'Port activity', 'provider': 'IMF PortWatch',
             'status': state, 'observedAt': instant(observed), 'dataAgeSeconds': age, 'core': True,
             'policySeconds': 72 * 3600,
             'detail': 'Daily satellite-AIS aggregates. Age is the observation date, not the export receipt; publication lag remains visible.',
             'termsUrl': 'https://portwatch.imf.org/pages/data-and-methodology', **shared}]
    status = cache.get_live_status()
    origin = status.get('forecastOrigin')
    through = status.get('targetThrough')
    valid = instant(through)
    # Date-only horizons include that UTC calendar day.
    if valid:
        from datetime import timedelta
        valid = valid.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
    state, age = classify(origin, now, 72 * 3600, valid_through=valid.isoformat() if valid else '')
    rows.append({'id': 'congestion-forecast', 'name': 'Congestion forecast', 'provider': 'PortWatch model',
                 'status': state, 'observedAt': instant(origin), 'validThrough': valid,
                 'dataAgeSeconds': age, 'core': True, 'policySeconds': 72 * 3600,
                 'detail': 'Modelled from the latest accepted activity observation. An expired horizon is historical, even after a new export.', **shared})
    for kind, name in [('surface', 'Port weather'), ('marine', 'Marine forecast')]:
        samples = []
        for port in PORTS:
            try:
                samples.append(current_environment.read(kind, port, at=now))
            except (ValueError, OSError, KeyError):
                samples.append({'rows': [], 'availableAt': None})
        evaluated = []
        for sample in samples:
            coverage = max((row.get('validAt', '') for row in sample['rows']), default='')
            state, age = classify(sample.get('availableAt'), now, current_environment.TTL[kind], valid_through=coverage)
            evaluated.append((state, age, sample.get('availableAt')))
        current = sum(row[0] == 'live' for row in evaluated)
        retained = [row for row in evaluated if row[1] is not None]
        state = 'live' if current == len(PORTS) else 'stale' if retained else 'unavailable'
        rows.append({'id': f'open-meteo-{kind}', 'name': name, 'provider': 'Open-Meteo', 'status': state,
                     'observedAt': None, 'availableAt': min((row[2] for row in retained), default=None),
                     'dataAgeSeconds': max((row[1] for row in retained), default=None),
                     'policySeconds': current_environment.TTL[kind], 'core': True,
                     'portsCurrent': current, 'portsTotal': len(PORTS),
                     'detail': f'{current}/{len(PORTS)} ports within response-age and valid-time policy. Provider forecasts, not station observations; issue time unavailable.',
                     'termsUrl': 'https://open-meteo.com/en/terms',
                     **job_metrics([f'current_{kind}_{port.locode}' for port in PORTS])})
    try:
        hazards = current_environment.read('hazards', PORTS[0], at=now)
    except (ValueError, OSError, KeyError):
        hazards = {}
    available = instant(hazards.get('availableAt'))
    budget = current_environment.TTL['hazards']
    state, age = classify(available, now, budget)
    rows.append({'id': 'gdacs-alerts', 'name': 'Regional hazard feed', 'provider': 'GDACS',
                 'status': state, 'availableAt': available if state != 'unavailable' else None,
                 'dataAgeSeconds': age, 'policySeconds': budget,
                 'detail': 'Age of the retained feed response. Check the event timestamps for individual alerts.',
                 'homepage': 'https://www.gdacs.org/', **job_metrics(['current_gdacs'])})
    return rows, coordinator.scheduler_status()
