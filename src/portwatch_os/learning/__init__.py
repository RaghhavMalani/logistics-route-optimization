"""The learning layer: score what we said, then adjust what we trust.

Reads only the ledger. Writes reliability weights, calibration reports and error
attributions. Contains no operational logic and no model of its own -- it is the
part of the system whose entire job is to be told it was wrong.
"""

from src.portwatch_os.learning.attribution import (
    Attribution,
    ContributionShare,
    MissReport,
    attribute,
    rank_misses,
    verify_decomposition,
)
from src.portwatch_os.learning.outcome_agent import (
    OutcomeAgent,
    OutcomeRun,
    SliceReport,
    score_event_outcome,
    score_prediction,
)
from src.portwatch_os.learning.reliability import (
    LeakageError,
    ReliabilityTable,
    accumulate,
    blend,
    fit_reliability,
    shrink,
)
from src.portwatch_os.learning.scoring import (
    BinaryScoreReport,
    CalibrationReport,
    ConfusionCounts,
    ErrorReport,
    Residual,
    binary_report,
    brier_score,
    calibration,
    confusion,
    error_report,
    log_loss,
    pinball_loss,
    skill_score,
)

__all__ = [
    "Attribution", "BinaryScoreReport", "CalibrationReport", "ConfusionCounts",
    "ContributionShare", "ErrorReport", "LeakageError", "MissReport",
    "OutcomeAgent", "OutcomeRun", "ReliabilityTable", "Residual", "SliceReport",
    "accumulate", "attribute", "binary_report", "blend", "brier_score",
    "calibration", "confusion", "error_report", "fit_reliability", "log_loss",
    "pinball_loss", "rank_misses", "score_event_outcome", "score_prediction",
    "shrink", "skill_score", "verify_decomposition",
]
