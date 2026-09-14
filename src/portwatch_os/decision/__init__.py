"""The decision intelligence engine: from "this is happening" to "these are
the decisions still available, here is what each causes, here is the best
trade-off, here is what happens if you do nothing, here is the evidence".

    model      DecisionProblem / Option / Evaluation / Frontier / Recommendation.
    actions    The typed action catalogue, with entitlement and availability.
    routing    Where a hull is on its lane and where the alternative goes.
    vessel     Routing options, each on its own branch of the observed world.
    port       Berth, crane and arrival options through the port twin.
    cargo      Connection options through the cargo model.
    frontier   Pareto dominance, labelled picks, an explicit ranking.
    critic     Critic v2: PASS / PASS_WITH_WARNINGS / REJECT with named evidence.
    engine     Build, evaluate, criticise, rank, recommend, record; the workflow.
    ledger     The problem as computed, then the choice and the outcome.
    learning   Prediction error, ranking accuracy, regret, calibration, reward.

Deterministic throughout. Language models may explain; they never produce a
number here.
"""

from src.portwatch_os.decision.engine import DecisionEngine, get_engine, reset_engine
from src.portwatch_os.decision.model import (
    DecisionActor,
    DecisionError,
    DecisionOption,
    DecisionProblem,
    Measure,
)

__all__ = [
    "DecisionActor",
    "DecisionEngine",
    "DecisionError",
    "DecisionOption",
    "DecisionProblem",
    "Measure",
    "get_engine",
    "reset_engine",
]
