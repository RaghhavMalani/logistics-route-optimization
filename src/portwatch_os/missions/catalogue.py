"""The first mission: the grounding of Ever Given in the Suez Canal, March 2021.

Chosen because sourceable, timestamped evidence exists for the whole arc: the
grounding on 23 March at 07:40 local, the suspension of navigation, the
salvage milestones, the growing queue, the refloating on 29 March at 15:05
local, the reopening that evening, and the clearing of the backlog on 3
April. Every line below cites the source it was transcribed from and the
instant it was retrieved.

The hulls are illustrative. No real vessel's position in March 2021 is held
by this deployment, and none is invented: three placeholder hulls are placed
on the Europe-India lane at stated distances from Suez so that the decision
engine has a subject to reason about, and each is labelled as such.
"""

from __future__ import annotations

from src.portwatch_os.missions.model import (
    IllustrativeVessel,
    Mission,
    Observation,
    Outcome,
    Source,
)

RETRIEVED = "2026-09-13T18:05:00Z"

SOURCES = [
    Source("wiki-2021-suez", "Wikipedia: 2021 Suez Canal obstruction",
           "https://en.wikipedia.org/wiki/2021_Suez_Canal_obstruction", "encyclopaedic summary citing primary reports",
           RETRIEVED, "Times are given in EGY (UTC+2) and UTC; cited to Reuters, BBC, the SCA and Leth Agencies."),
    Source("boskalis-refloat", "Boskalis press release: Suez Canal unblocked",
           "https://boskalis.com/press/press-releases-and-company-news/suez-canal-unblocked-we-pulled-it-off",
           "salvor's statement", RETRIEVED),
    Source("cnn-freed", "CNN: Ever Given ship freed in the Suez Canal, authority confirms",
           "https://www.cnn.com/2021/03/29/africa/suez-canal-refloating-intl-hnk", "news report", RETRIEVED),
    Source("scd-cape", "Supply Chain Dive: container ships steer toward longer route around Cape of Good Hope",
           "https://www.supplychaindive.com/news/suez-cape-good-hope-ever-given-evergreen-blocked-stuck/597402/",
           "news report", RETRIEVED, "Reports Hapag-Lloyd's service alert naming vessels rerouted via the Cape."),
]

#: The start instant: the first morning after the grounding was reported, so
#: the mission opens with a blocked canal and no statement yet on how long.
START = "2021-03-23T08:00:00Z"

RECORDING = [
    Observation("2021-03-23T05:40:00Z", "report",
                "Ever Given ran aground in the Suez Canal at 07:40 EGY during a sandstorm with winds "
                "exceeding 40 kn, blocking the canal in both directions.",
                "wiki-2021-suez",
                claim={"status": "blocked", "severity": 1.0, "confidence": 0.6, "chokepoint": "SUEZ",
                       "sourceCount": 1}),
    Observation("2021-03-23T08:00:00Z", "corroboration",
                "Multiple outlets carry the grounding; the canal is reported blocked to all transits.",
                "wiki-2021-suez", claim={"confidence": 0.85, "sourceCount": 3}),
    Observation("2021-03-25T00:00:00Z", "statement",
                "The Suez Canal Authority suspended navigation through the canal.",
                "wiki-2021-suez", claim={"status": "suspended", "confidence": 0.95}, time_unstated=True),
    Observation("2021-03-25T12:00:00Z", "statement",
                "Royal Boskalis (Smit Salvage) engaged for the salvage.",
                "wiki-2021-suez", claim={}, time_unstated=True),
    Observation("2021-03-26T12:00:00Z", "report",
                "A refloating attempt was unsuccessful. Hapag-Lloyd's service alert names vessels rerouted "
                "via the Cape of Good Hope; carriers say they are looking into diversions.",
                "scd-cape", claim={"diversions": True}, time_unstated=True),
    Observation("2021-03-27T18:00:00Z", "count",
                "High tide let tugs move the ship 17 m north by 18:00 UTC; over 300 vessels obstructed at both "
                "ends of the canal.",
                "wiki-2021-suez", claim={"shipsWaiting": 300}),
    Observation("2021-03-28T12:00:00Z", "report",
                "Seagoing tug Alp Guard (285 t bollard pull) arrived.",
                "wiki-2021-suez", claim={}, time_unstated=True),
    Observation("2021-03-29T02:30:00Z", "report",
                "Stern refloated at 04:30 local time.",
                "wiki-2021-suez", claim={"status": "partially_refloated"}),
    Observation("2021-03-29T13:05:00Z", "report",
                "Ship fully freed at 15:05 EGY by fourteen Egyptian, Dutch and Italian tugs.",
                "boskalis-refloat", claim={"status": "refloated"}),
    Observation("2021-03-29T17:00:00Z", "statement",
                "Canal reopened to shipping at 19:00 EGY with more than 400 ships waiting: about 200 in the "
                "Red Sea, under 200 in the Mediterranean and around 50 in the Bitter Lakes.",
                "wiki-2021-suez", claim={"status": "reopened", "shipsWaiting": 400}),
    Observation("2021-04-03T23:59:00Z", "statement",
                "Backlog of delayed ships cleared.",
                "wiki-2021-suez", claim={"status": "cleared"}, time_unstated=True),
]

OUTCOME = Outcome(
    reopened_at="2021-03-29T17:00:00Z",
    blocked_from="2021-03-23T05:40:00Z",
    backlog_cleared_on="2021-04-03",
    backlog_cleared_bound="2021-04-03T23:59:00Z (end of the stated day; the source gives no time)",
    ships_waiting_peak=400,
    ships_waiting_source_id="wiki-2021-suez",
    summary="The canal was blocked for about 155 h and reopened on the evening of 29 March; the backlog of "
            "more than 400 ships cleared by 3 April.",
    sources=["wiki-2021-suez", "boskalis-refloat", "cnn-freed"],
)

FLEET = [
    IllustrativeVessel("MSN-001", "MV Konkan (illustrative)", "EUR_IND", "INNSA",
                       {"SUEZ": 36.0, "BAB_EL_MANDEB": 66.0}, 18.0),
    IllustrativeVessel("MSN-002", "MV Malabar (illustrative)", "EUR_IND", "INNSA",
                       {"SUEZ": 96.0, "BAB_EL_MANDEB": 126.0}, 17.0),
    IllustrativeVessel("MSN-003", "MV Kutch (illustrative)", "EUR_IND", "INMUN",
                       {"SUEZ": -12.0, "BAB_EL_MANDEB": 18.0}, 19.0),
]

EVER_GIVEN = Mission(
    mission_id="suez-ever-given-2021",
    name="Ever Given: the Suez Canal blockage, March 2021",
    start_timestamp=START,
    chokepoint="SUEZ",
    event_category="canal_restriction",
    event_title="Ever Given aground; Suez Canal blocked",
    sources=SOURCES,
    recording=RECORDING,
    fleet=FLEET,
    outcome=OUTCOME,
    evaluation_window_hours=24.0 * 12,
    claim_horizon_hours=72.0,
    description=(
        "On 23 March 2021 the 400 m container ship Ever Given grounded in the southern Suez Canal and "
        "blocked it in both directions. The replay opens on the first morning, with the canal blocked and "
        "no statement on how long. PortWatch must decide what an India-bound hull should do, then be scored "
        "against what actually happened."
    ),
)

from src.portwatch_os.missions.biparjoy import BIPARJOY  # noqa: E402 - the second mission, structurally unlike this one

MISSIONS = {EVER_GIVEN.mission_id: EVER_GIVEN, BIPARJOY.mission_id: BIPARJOY}


def get_mission(mission_id: str) -> Mission:
    try:
        return MISSIONS[mission_id]
    except KeyError:
        raise KeyError(f"no mission {mission_id}; known: {', '.join(sorted(MISSIONS))}") from None


__all__ = ["BIPARJOY", "EVER_GIVEN", "FLEET", "MISSIONS", "OUTCOME", "RECORDING", "SOURCES", "get_mission"]
