"""Historical missions: replay a sourced incident with only what was known
then, decide, reveal, and score PortWatch against reality.

    model       Mission, Observation, Source, Outcome; the no-leak gate.
    catalogue   The missions this build ships. One, built properly.
    replay      The clock, the world at that clock, decisions, the reveal.
    scorecard   Knew / predicted / recommended / selected / happened / learned.
"""

from src.portwatch_os.missions.catalogue import MISSIONS, get_mission
from src.portwatch_os.missions.model import FutureLeak, Mission, MissionError, Observation, Outcome, Source
from src.portwatch_os.missions.replay import MissionReplay
from src.portwatch_os.missions.scorecard import scorecard

__all__ = [
    "FutureLeak",
    "MISSIONS",
    "Mission",
    "MissionError",
    "MissionReplay",
    "Observation",
    "Outcome",
    "Source",
    "get_mission",
    "scorecard",
]
