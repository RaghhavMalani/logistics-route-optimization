"""Unpublished, bounded marine and ensemble coverage trials."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import math

from src.portwatch_os.clock import wall_now
from src.portwatch_os.freshness.source_snapshots import Snapshot
from src.portwatch_os.freshness.trial_collectors import fetch_json
from src.utils.port_registry import PORTS


def summarize(response, kind):
    hourly = response.get('hourly', {})
    times = hourly.get('time', [])
    if not times or len(times) > 192:
        raise ValueError('Missing or oversized forecast timeline')
    for value in times:
        datetime.fromisoformat(value).replace(tzinfo=timezone.utc)
    fields = {key: values for key, values in hourly.items() if key != 'time'}
    wanted = ['wave_height', 'swell_wave_height', 'ocean_current_velocity', 'ocean_current_direction']
    if kind == 'ensemble':
        wanted = [key for key in fields if key.startswith('wind_speed_10m')]
        if len(wanted) < 2:
            raise ValueError('Forecast has fewer than two ensemble members')
    if not wanted or any(key not in fields or len(fields[key]) != len(times) for key in wanted):
        raise ValueError('Incomplete forecast variables or member timelines')
    counts = {key: sum(type(v) in (int, float) and math.isfinite(v) for v in fields[key]) for key in wanted}
    if any(count == 0 for count in counts.values()):
        raise ValueError('No finite coverage for a requested variable')
    return {'validFrom': times[0], 'validThrough': times[-1], 'finiteValues': counts,
            'units': response.get('hourly_units', {}), 'hourly': {'time': times, **{key: fields[key] for key in wanted}}}


def weather_trial(kind):
    if kind not in ('marine', 'ensemble'):
        raise ValueError('Unknown weather trial')
    def collect(port):
        params = {'latitude': port.lat, 'longitude': port.lon, 'timezone': 'GMT', 'forecast_days': 3}
        if kind == 'marine':
            params.update(latitude=port.lat-.15, longitude=port.lon+(.15 if port.coast == 'east' else -.15),
                          hourly='wave_height,swell_wave_height,ocean_current_velocity,ocean_current_direction')
            url = 'https://marine-api.open-meteo.com/v1/marine'
        else:
            params.update(hourly='wind_speed_10m', wind_speed_unit='kn', models='icon_seamless')
            url = 'https://ensemble-api.open-meteo.com/v1/ensemble'
        return port.locode, summarize(fetch_json(url, params), kind)
    with ThreadPoolExecutor(max_workers=2) as workers:
        ports = dict(workers.map(collect, PORTS))
    receipt = wall_now().isoformat()
    return Snapshot({'attribution': 'Open-Meteo, CC BY 4.0; modelled forecasts',
                     'precision': 'RESPONSE_AVAILABILITY_ONLY', 'availableAt': receipt,
                     'coverage': {key: value['validThrough'] for key, value in ports.items()}, 'ports': ports}, None)
