"""Reviewed adapter capabilities, not another evidence or session store."""
from copy import deepcopy

NAVCEN_SOURCE = 'https://www.navcen.uscg.gov/sites/default/files/msi/bridge_1.geojson'
ASSETS = {
    'WRIGHTSVILLE_SR74': {'name': 'S.R. 74 Wrightsville Beach Bridge', 'lon': -77.81259, 'lat': 34.21828,
        'namePattern': r'(?:Wrightsville Beach|74 State Route Bridge)', 'timeZone': 'America/New_York',
        'country': 'US', 'template': 'SR74_CLOSED_POSITION_V2', 'clearanceFeetMHW': 20,
        'reviewedTemplateSha256': '8720905aa77c647218025e41c2275e2cc762cb711c8a2f30af132eb6730942c2'},
    'MARE_ISLAND_DRAWBRIDGE': {'name': 'Mare Island Drawbridge', 'lon': -122.27474, 'lat': 38.11091,
        'namePattern': r'MARE ISLAND DRAWBRIDGE', 'timeZone': 'America/Los_Angeles',
        'country': 'US', 'template': 'MARE_ISLAND_CLOSED_POSITION_V1', 'clearanceFeetMHW': 13,
        'reviewedTemplateSha256': 'b632533822d624794b1fb91efff2a8b34fd738673c3b140b111b65f11db5b927'},
    'PAMLICO_CAROLINA_COASTAL_RAILROAD': {'name': 'Carolina Coastal Railroad Bridge 126.10',
        'lon': -77.05297, 'lat': 35.535393, 'namePattern': r'Bridge 126\.10 \(Carolina Coastal Railroad\)',
        'timeZone': 'America/New_York', 'country': 'US',
        'template': 'PAMLICO_REPEATED_CLOSED_POSITION_V1', 'clearanceFeetMHW': None,
        'reviewedTemplateSha256': '3f80c2ac00986db9b3f8a7896677d65f65a4f66e06caeb047d1492f0bd6bdf15'},
}
ADAPTERS = [{
    'id': 'NAVCEN_MSI_BRIDGES_V2', 'provider': 'USCG NAVCEN', 'sourceFamily': 'NAVCEN_MSI',
    'source': NAVCEN_SOURCE, 'catalogueSource': 'https://www.navcen.uscg.gov/msi',
    'status': 'ENABLED_NONCOMMERCIAL_DEMO_RESEARCH',
    'discoveryCoverage': 'All features in the public Bridges GeoJSON received product',
    'calculationCoverage': 'Reviewed named US assets and explicit closed-position clock templates only',
    'geography': ['US North Carolina', 'US California'], 'assetIds': sorted(ASSETS),
    'identity': 'Provider MSI_UID separate from stable asset identity',
    'timestamps': {'providerCreatedAt': 'CREATE_DATE metadata; not established publication',
        'providerModifiedAt': 'MODIFIED_DATE metadata; not established publication',
        'publishedAt': 'UNKNOWN', 'availableAt': 'Actual first receipt of retained revision'},
    'validity': 'Envelope retained separately from local clock windows; explicit expiry',
    'revisionIdentity': 'Record semantics and extraction version; reversions have new receipt lineage',
    'evidenceArchive': 'Existing operational_notices complete hashed response archive and immutable revision files',
    'sourceUse': 'Public noncommercial research/demo only; source credit; no endorsement or NAIS data',
    'calculationCapability': 'Conditional waiting at declared opening-requiring asset; no verified access or savings',
}, {
    'id': 'IN_NHO_NAVAREA_VIII_REVIEW', 'provider': 'Indian Naval Hydrographic Department',
    'sourceFamily': 'NHO_NAVAREA_VIII', 'source': 'https://www.hydrobharat.gov.in/web/guest/navarea-warnings',
    'status': 'INVESTIGATED_NOT_ENABLED', 'geography': ['NAVAREA VIII', 'India', 'Indian Ocean'],
    'reason': 'Current-product extraction and public redistribution terms not established in this review',
    'calculationCapability': 'NONE',
}, {
    'id': 'JNPA_MARINE_CIRCULAR_REVIEW', 'provider': 'Jawaharlal Nehru Port Authority',
    'sourceFamily': 'JNPA_MARINE_CIRCULAR',
    'source': 'https://www.jnport.gov.in/page/marine-safety-circular/aDV4Tk9FRkZsckVDeUxkTlEzMjFadz09',
    'status': 'INVESTIGATED_NOT_ENABLED', 'geography': ['INNSA'],
    'reason': 'No reviewed current timed passage restriction and public reuse terms established',
    'calculationCapability': 'NONE',
}, {
    'id': 'SG_MPA_NOTICES_REVIEW', 'provider': 'Maritime and Port Authority of Singapore',
    'sourceFamily': 'MPA_PORT_MARINE', 'source': 'https://www.mpa.gov.sg/media-centre',
    'status': 'INVESTIGATED_NOT_ENABLED', 'geography': ['Singapore', 'Indian Ocean–East Asia lanes'],
    'reason': 'Official terms require prior written permission for republication; no permission assumed',
    'calculationCapability': 'NONE',
}, {
    'id': 'SCA_NAVIGATION_CIRCULAR_REVIEW', 'provider': 'Suez Canal Authority',
    'sourceFamily': 'SCA_NAVIGATION_CIRCULAR',
    'source': 'https://www.suezcanal.gov.eg/English/Navigation/NavigationCirculars/Pages/default.aspx',
    'status': 'INVESTIGATED_NOT_ENABLED', 'geography': ['Suez Canal', 'India–Europe lanes'],
    'reason': 'Navigation rules explicitly reserve reproduction rights; no public archival licence established for the selected product',
    'calculationCapability': 'NONE',
}]


def registry():
    return deepcopy(ADAPTERS)
