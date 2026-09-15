"""The second mission: Cyclone Biparjoy over the Gulf of Kutch, June 2023.

Structurally unlike Ever Given on purpose. The event is weather, not a
grounding; its subject is two ports on the Gulf of Kutch rather than a
strait; and its consequence runs WEATHER -> ROUTE -> PORT: hulls bound for
Kandla and Mundra were told to stay in the high seas, the ports stopped
work, the cyclone came ashore near Jakhau, and the ports reopened two days
later. Every line below cites the source it was transcribed from and the
instant it was retrieved; where a source gives a day or a "post-market" and
no time, the observation says so and carries the bound the mission chose.

What the sources do not state is not here. No berth was closed at a time
the sources do not give; no vessel count is quoted because none was found;
the ports' own reopening instants are the instants the reports were
published, marked as bounds. The hulls are illustrative: no real vessel's
position in June 2023 is held by this deployment, and three placeholder
hulls are placed on the modelled lanes at stated distances from their ports
so the decision engine has a subject.
"""

from __future__ import annotations

from src.portwatch_os.missions.model import (
    IllustrativeVessel,
    Mission,
    Observation,
    Outcome,
    Source,
)

RETRIEVED = "2026-09-15T04:10:00Z"

SOURCES = [
    Source("wiki-biparjoy", "Wikipedia: Cyclone Biparjoy",
           "https://en.wikipedia.org/wiki/Cyclone_Biparjoy", "encyclopaedic summary citing IMD, JTWC and press",
           RETRIEVED, "Formation 6 June, peak 10 June (165 km/h 3-min sustained), IMD alerts to Gujarat 12 June, "
                      "Kandla and Mundra halted, dissipation 19 June."),
    Source("bt-adani-suspension", "Business Today: Adani Ports shares in focus on suspension of vessel operations at Mundra and Tuna",
           "https://www.businesstoday.in/markets/company-stock/story/adani-ports-shares-in-focus-on-suspension-of-mundra-tuna-port-vessel-operations-385314-2023-06-13",
           "news report of an exchange filing", RETRIEVED,
           "Published 13 June 2023 07:42 IST. Adani Ports informed the exchanges post-market on Monday 12 June that vessel "
           "operations at Mundra and Tuna were suspended in view of the IMD advisory; the advisory expected the storm to "
           "cross between Mandvi and Karachi around 15 June noon with 125-135 km/h winds gusting to 150."),
    Source("mg-kandla-stop", "Maritime Gateway: Deendayal Port shuts operations as cyclone nears",
           "https://www.maritimegateway.com/deendayal-port-shuts-operations-as-cyclone-nears/", "news report",
           RETRIEVED, "Published 14 June 2023 11:02 IST. 'All cargo operations have been stopped at Deendayal Port'; ships "
                      "told to stay in the high seas and away from the Gulf of Kutch entrance and outer harbour."),
    Source("tribune-landfall", "The Tribune: Cyclone Biparjoy starts making landfall near Jakhau port in Gujarat's Kutch",
           "https://www.tribuneindia.com/news/nation/cyclone-biparjoy-starts-making-landfall-near-jakhau-port-in-gujarats-kutch-517382",
           "news report quoting IMD", RETRIEVED,
           "Updated 16 June 2023 00:46 IST. IMD: the landfall process commenced around 18:30 IST on 15 June near Jakhau, "
           "115-125 km/h gusting 140, to be completed over land by midnight."),
    Source("malaymail-resume", "Malay Mail: Coastal areas of India's Gujarat state return to normalcy after cyclone",
           "https://www.malaymail.com/news/world/2023/06/17/coastal-areas-of-indias-gujarat-state-return-to-normalcy-after-cyclone/74906",
           "news report", RETRIEVED,
           "Published 17 June 2023 20:13 MYT (12:13 UTC). Pipavav and Kandla said they had resumed operations; Mundra "
           "was due to restart from that evening."),
    Source("kn-advisory", "Kuehne+Nagel: Update: port operations at Gujarat coast back to normal",
           "https://mykn.kuehne-nagel.com/news/article/update-port-operations-at-gujarat-coast-back-20-Jun-2023",
           "forwarder advisory", RETRIEVED,
           "Published 19 June 2023. Mundra fully suspended 13 June; Pipavav vessel operations suspended 10 June and landside "
           "13 June; Hazira 14 June; all 'in full swing' by 19 June; weather improved 17 June."),
]

#: The start instant: the morning after the Mundra suspension became public,
#: with the IMD forecasting the crossing for 15 June noon and Kandla still working.
START = "2023-06-13T03:00:00Z"

RECORDING = [
    Observation("2023-06-06T12:00:00Z", "report",
                "IMD named the depression over the east-central Arabian Sea Cyclonic Storm Biparjoy.",
                "wiki-biparjoy", claim={}, time_unstated=True),
    Observation("2023-06-10T12:00:00Z", "report",
                "Biparjoy reached its peak as an extremely severe cyclonic storm with 3-minute sustained winds of 165 km/h.",
                "wiki-biparjoy", claim={}, time_unstated=True),
    Observation("2023-06-12T06:00:00Z", "statement",
                "IMD advisory: the storm is expected to cross the Saurashtra and Kutch coasts between Mandvi and Karachi "
                "around 15 June noon as a very severe cyclonic storm, 125-135 km/h gusting to 150; alerts issued to "
                "Gujarat authorities to prepare evacuations.",
                "bt-adani-suspension",
                claim={"status": "forecast_closure", "severity": 0.85, "confidence": 0.7, "sourceCount": 2},
                time_unstated=True),
    Observation("2023-06-12T12:30:00Z", "statement",
                "Adani Ports informed the exchanges post-market that vessel operations at Mundra and Tuna were suspended "
                "in view of the IMD advisory.",
                "bt-adani-suspension",
                claim={"status": "mundra_suspended", "severity": 0.9, "confidence": 0.85, "sourceCount": 3},
                time_unstated=True),
    Observation("2023-06-14T05:32:00Z", "statement",
                "Deendayal Port (Kandla) stopped all cargo operations; ships destined for the port were told not to come "
                "but to stay in the high seas, and not to wait at the mouth of the Gulf of Kutch or in the outer harbour.",
                "mg-kandla-stop",
                claim={"status": "kandla_suspended", "severity": 1.0, "confidence": 0.9, "sourceCount": 4},
                time_unstated=True),
    Observation("2023-06-15T13:00:00Z", "report",
                "IMD: the landfall process commenced around 18:30 IST near Jakhau, with the eye 20 km south-west of "
                "Jakhau port and winds of 115-125 km/h gusting to 140.",
                "tribune-landfall", claim={"status": "landfall", "confidence": 0.95}),
    Observation("2023-06-15T18:30:00Z", "report",
                "Landfall to be completed over land by midnight IST; the storm weakening to a severe cyclonic storm, "
                "winds reducing further by Friday morning.",
                "tribune-landfall", claim={}, time_unstated=True),
    Observation("2023-06-17T12:13:00Z", "statement",
                "Ports along the coast including Pipavav and Kandla said they had resumed operations.",
                "malaymail-resume", claim={"status": "kandla_reopened"}, time_unstated=True),
    Observation("2023-06-17T13:30:00Z", "statement",
                "Mundra was due to restart operations from that evening.",
                "malaymail-resume", claim={"status": "reopened"}, time_unstated=True),
    Observation("2023-06-19T12:00:00Z", "statement",
                "Operations at Mundra, Pipavav and Hazira reported 'in full swing'; Adani Ports confirmed Mundra back to "
                "normal.",
                "kn-advisory", claim={"status": "cleared"}, time_unstated=True),
    Observation("2023-06-19T18:00:00Z", "report",
                "IMD downgraded the system to a well-marked low-pressure area and discontinued advisories.",
                "wiki-biparjoy", claim={}, time_unstated=True),
]

CLEARED_BOUND = "2023-06-19T12:00:00Z (the day the forwarder advisory said operations were in full swing; no time given)"

OUTCOME = Outcome(
    reopened_at="2023-06-17T12:13:00Z",
    blocked_from="2023-06-14T05:32:00Z",
    backlog_cleared_on="2023-06-19",
    backlog_cleared_bound=CLEARED_BOUND,
    ships_waiting_peak=None,
    ships_waiting_source_id=None,
    summary="Kandla stopped cargo work by the morning of 14 June and said it had resumed on 17 June, about 79 h by the "
            "report instants; Mundra suspended vessel operations from the evening of 12 June and restarted on the "
            "evening of 17 June, about 121 h. The cyclone came ashore near Jakhau from 18:30 IST on 15 June. No "
            "source states how many ships waited.",
    sources=["mg-kandla-stop", "malaymail-resume", "bt-adani-suspension", "tribune-landfall", "kn-advisory"],
    closures={
        "INIXY": {"closedFrom": "2023-06-14T05:32:00Z", "reopenedAt": "2023-06-17T12:13:00Z",
                  "backlogClearedBound": CLEARED_BOUND,
                  "note": "both instants are the reports' publication instants; the stop and the restart preceded them"},
        "INMUN": {"closedFrom": "2023-06-12T12:30:00Z", "reopenedAt": "2023-06-17T13:30:00Z",
                  "backlogClearedBound": CLEARED_BOUND,
                  "note": "post-market on 12 June and 'this evening' on 17 June, read as 18:00 and 19:00 IST"},
    },
)

#: Timings are consistent with the modelled lane geometry at the hull's own
#: speed (Suez to Bab el Mandeb is 1,316 nm on the EUR_IND polyline; Bab el
#: Mandeb to Kandla 1,765 nm; Hormuz to Mundra 837 nm), so the chart places
#: each hull where its hours say it is.
FLEET = [
    IllustrativeVessel("BPJ-001", "MV Kutch (illustrative)", "EUR_IND", "INIXY",
                       {"SUEZ": -156.0, "BAB_EL_MANDEB": -74.0}, 16.0, hours_to_destination_at_start=36.0),
    IllustrativeVessel("BPJ-002", "MV Saurashtra (illustrative)", "GULF_IND", "INMUN",
                       {"HORMUZ": -40.0}, 14.0, hours_to_destination_at_start=20.0),
    IllustrativeVessel("BPJ-003", "MV Bhuj (illustrative)", "EUR_IND", "INMUN",
                       {"SUEZ": 12.0, "BAB_EL_MANDEB": 89.0}, 17.0, hours_to_destination_at_start=191.0),
]

BIPARJOY = Mission(
    mission_id="gulf-of-kutch-biparjoy-2023",
    name="Biparjoy: the Gulf of Kutch ports, June 2023",
    start_timestamp=START,
    chokepoint=None,
    event_category="cyclone",
    event_title="Cyclone Biparjoy; Kandla and Mundra closed to arrivals",
    sources=SOURCES,
    recording=RECORDING,
    fleet=FLEET,
    outcome=OUTCOME,
    evaluation_window_hours=24.0 * 10,
    claim_horizon_hours=96.0,
    ports=["INIXY", "INMUN"],
    event_lat=23.2,
    event_lon=68.6,
    description=(
        "On 12 June 2023, with Cyclone Biparjoy forecast to cross the Kutch coast around noon on the 15th, Adani Ports "
        "suspended vessel operations at Mundra; Kandla followed. The replay opens on the morning of the 13th with two "
        "hulls a day or so from ports about to close and one still on the far side of Suez. PortWatch must decide "
        "whether each holds in the high seas, diverts to an open port or proceeds, and is then scored against the "
        "reopening the sources record."
    ),
)

__all__ = ["BIPARJOY", "FLEET", "OUTCOME", "RECORDING", "SOURCES"]
