"""Policy learning inside the digital twin, and how a policy earns promotion.

Two things live here and they are kept strictly apart:

*   :class:`PortEnvironment` -- episode generation and training. Everything a
    policy learns from is generated here, in simulation, from seeded scenarios.
*   :func:`evaluate` and :func:`benchmark` -- measurement. A policy is never
    scored by the loop that trained it, and never on the scenarios it trained
    on. Held-out seeds are a separate range.

**RL never touches a ship.** A policy trained here produces a *recommendation*
for a human to approve, and only after it has passed the promotion gate in
:mod:`~src.portwatch_os.twin.promotion`. There is no code path from a learned
policy to an executed action, and the advisory workflow is the reason: an
advisory has to be approved by a controller and accepted by a vessel before it
means anything.
"""

from __future__ import annotations

import random
import statistics
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple

from src.portwatch_os.twin.policies import (
    BasePolicy,
    ContextualBanditPolicy,
    FirstComeFirstServed,
    GreedyPolicy,
    LookaheadPolicy,
    RandomPolicy,
)
from src.portwatch_os.twin.simulation import (
    SimulationConfig,
    SimulationResult,
    reward,
    reward_breakdown,
    simulate,
)
from src.portwatch_os.twin.state import (
    APPROACHING,
    PortState,
    VesselCall,
    schematic_layout,
    seed_yard,
)
from src.utils.logging_utils import get_logger

log = get_logger(__name__)

#: Training seeds and evaluation seeds come from disjoint ranges, always. A
#: policy evaluated on a scenario it trained on is measuring memorisation.
TRAIN_SEED_BASE = 1_000_000
EVAL_SEED_BASE = 9_000_000


@dataclass
class ScenarioSpec:
    """The generator's knobs. One spec plus one seed is one reproducible episode."""

    port_code: str = "INMAA"
    berth_count: int = 8
    capacity_index: float = 0.7
    horizon_hours: float = 48.0
    #: Vessel calls per episode.
    arrivals: int = 14
    #: Starting yard utilisation. Drawn per episode from
    #: ``yard_utilisation ± yard_spread`` so the yard is a live context
    #: dimension rather than a constant the learner cannot key on.
    yard_utilisation: float = 0.7
    yard_spread: float = 0.18
    #: Weather impact index range the episode draws from.
    weather_range: Tuple[float, float] = (0.0, 0.35)
    #: Fraction of calls that carry a departure deadline.
    deadline_share: float = 0.4
    eta_noise_hours: float = 0.5

    def to_dict(self) -> Dict[str, Any]:
        return {
            "portCode": self.port_code,
            "berthCount": self.berth_count,
            "capacityIndex": self.capacity_index,
            "horizonHours": self.horizon_hours,
            "arrivals": self.arrivals,
            "yardUtilisation": self.yard_utilisation,
            "yardSpread": self.yard_spread,
            "weatherRange": list(self.weather_range),
            "deadlineShare": self.deadline_share,
            "etaNoiseHours": self.eta_noise_hours,
        }


#: Vessel size classes the generator draws from, with their move counts. Drawn
#: from published container-vessel envelopes, not from any operator's data.
_CLASSES: Sequence[Tuple[str, float, float, int, int]] = (
    # (class, LOA m, draught m, min moves, max moves)
    ("feeder", 170.0, 9.0, 250, 600),
    ("panamax", 250.0, 12.0, 700, 1400),
    ("post_panamax", 300.0, 13.5, 1200, 2200),
    ("neo_panamax", 366.0, 15.5, 1800, 3200),
)


class PortEnvironment:
    """Generates episodes and runs policies in them.

    Not a Gym environment on purpose: the policies here act on a whole
    :class:`PortState` and emit a list of actions, which is the interface the
    optimisers and the live decision path already use. Wrapping that in a
    step/observation API would add a translation layer whose only purpose would
    be to look like a library this code does not use.
    """

    def __init__(self, spec: Optional[ScenarioSpec] = None) -> None:
        self.spec = spec or ScenarioSpec()

    # -- episode generation ------------------------------------------------
    def build_state(self, seed: int) -> PortState:
        """One reproducible starting state."""
        rng = random.Random(seed)
        spec = self.spec
        state = schematic_layout(
            spec.port_code,
            berth_count=spec.berth_count,
            capacity_index=spec.capacity_index,
        )
        yard = max(
            0.25,
            min(0.97, rng.uniform(
                spec.yard_utilisation - spec.yard_spread,
                spec.yard_utilisation + spec.yard_spread,
            )),
        )
        seed_yard(state, yard)
        low, high = spec.weather_range
        state.weather_impact = rng.uniform(low, high)

        for index in range(spec.arrivals):
            klass, loa, draught, low_moves, high_moves = rng.choice(_CLASSES)
            # Arrivals are spread over the first three quarters of the horizon so
            # every episode has a tail in which the queue can actually clear.
            eta = rng.uniform(0.0, spec.horizon_hours * 0.75)
            moves = rng.randint(low_moves, high_moves)
            deadline = (
                eta + rng.uniform(14.0, 30.0)
                if rng.random() < spec.deadline_share else None
            )
            state.calls.append(
                VesselCall(
                    call_id=f"C{index + 1:02d}",
                    vessel_id=f"SIM-{seed}-{index + 1}",
                    name=f"Sim {klass.title()} {index + 1}",
                    vessel_class=klass,
                    loa_m=loa * rng.uniform(0.92, 1.0),
                    draught_m=draught * rng.uniform(0.85, 1.0),
                    eta_hour=eta,
                    moves=moves,
                    latest_departure_hour=deadline,
                    priority=rng.uniform(0.2, 0.8),
                    state=APPROACHING,
                )
            )
        state.calls.sort(key=lambda c: c.eta_hour)
        return state

    def config(self, seed: int) -> SimulationConfig:
        return SimulationConfig(
            horizon_hours=self.spec.horizon_hours,
            seed=seed,
            eta_noise_hours=self.spec.eta_noise_hours,
            record_trace=False,
        )

    def run_episode(self, policy: BasePolicy, seed: int) -> Tuple[float, SimulationResult]:
        policy.reset()
        state = self.build_state(seed)
        result = simulate(state, policy, self.config(seed), snapshot_hours=())
        return reward(result), result


# --------------------------------------------------------------------------
# training
# --------------------------------------------------------------------------


@dataclass
class TrainingReport:
    policy_id: str
    episodes: int
    seeds: List[int]
    mean_reward: float
    final_window_mean: float
    #: Reward per episode, so a learning curve can be drawn honestly.
    curve: List[float] = field(default_factory=list)
    spec: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "policyId": self.policy_id,
            "episodes": self.episodes,
            "seedRange": [min(self.seeds), max(self.seeds)] if self.seeds else [],
            "meanReward": round(self.mean_reward, 3),
            "finalWindowMean": round(self.final_window_mean, 3),
            "curve": [round(v, 2) for v in self.curve],
            "spec": self.spec,
        }


def train_bandit(
    environment: PortEnvironment,
    *,
    episodes: int = 120,
    seed_base: int = TRAIN_SEED_BASE,
    policy: Optional[ContextualBanditPolicy] = None,
) -> Tuple[ContextualBanditPolicy, TrainingReport]:
    """Train the contextual bandit on simulated episodes.

    Training seeds are ``seed_base + i``. Evaluation uses
    :data:`EVAL_SEED_BASE`, which is far enough away that the two ranges cannot
    overlap for any episode count this repository will ever run.
    """
    learner = policy or ContextualBanditPolicy()
    curve: List[float] = []
    seeds: List[int] = []

    for episode in range(episodes):
        seed = seed_base + episode
        seeds.append(seed)
        episode_reward, _ = environment.run_episode(learner, seed)
        learner.update(episode_reward)
        curve.append(episode_reward)

    window = curve[-max(10, episodes // 5):] if curve else [0.0]
    report = TrainingReport(
        policy_id=learner.policy_id,
        episodes=episodes,
        seeds=seeds,
        mean_reward=statistics.fmean(curve) if curve else 0.0,
        final_window_mean=statistics.fmean(window),
        curve=curve,
        spec=environment.spec.to_dict(),
    )
    log.info(
        "Trained %s over %d episodes: mean reward %.1f, final window %.1f.",
        learner.policy_id, episodes, report.mean_reward, report.final_window_mean,
    )
    return learner, report


# --------------------------------------------------------------------------
# evaluation
# --------------------------------------------------------------------------


@dataclass
class PolicyEvaluation:
    """Measured performance of one policy on held-out scenarios."""

    policy_id: str
    name: str
    family: str
    episodes: int
    mean_reward: float
    reward_stdev: float
    #: Worst episode. A policy with a good mean and a catastrophic tail is not
    #: promotable, so the tail is reported next to the mean rather than buried.
    min_reward: float
    max_reward: float
    mean_wait_hours: Optional[float]
    mean_turnaround_hours: Optional[float]
    completed_calls: float
    missed_departures: float
    violations: int
    rejected_actions: int
    berth_utilisation: float
    yard_overflow_blocks: float
    seeds: List[int] = field(default_factory=list)
    breakdown: Dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "policyId": self.policy_id,
            "name": self.name,
            "family": self.family,
            "episodes": self.episodes,
            "meanReward": round(self.mean_reward, 3),
            "rewardStdev": round(self.reward_stdev, 3),
            "minReward": round(self.min_reward, 3),
            "maxReward": round(self.max_reward, 3),
            "meanWaitHours": (
                None if self.mean_wait_hours is None else round(self.mean_wait_hours, 3)
            ),
            "meanTurnaroundHours": (
                None if self.mean_turnaround_hours is None
                else round(self.mean_turnaround_hours, 3)
            ),
            "completedCalls": round(self.completed_calls, 2),
            "missedDepartures": round(self.missed_departures, 2),
            "violations": self.violations,
            "rejectedActions": self.rejected_actions,
            "berthUtilisation": round(self.berth_utilisation, 4),
            "yardOverflowBlocks": round(self.yard_overflow_blocks, 3),
            "seedRange": [min(self.seeds), max(self.seeds)] if self.seeds else [],
            "rewardBreakdown": self.breakdown,
        }


def evaluate(
    environment: PortEnvironment,
    policy: BasePolicy,
    *,
    episodes: int = 40,
    seed_base: int = EVAL_SEED_BASE,
) -> PolicyEvaluation:
    """Score a policy on held-out episodes. Never call this with training seeds."""
    rewards: List[float] = []
    waits: List[float] = []
    turnarounds: List[float] = []
    completed: List[int] = []
    missed: List[int] = []
    utilisation: List[float] = []
    overflow: List[int] = []
    violations = 0
    rejected = 0
    seeds: List[int] = []
    totals: Dict[str, float] = {}

    for episode in range(episodes):
        seed = seed_base + episode
        seeds.append(seed)
        episode_reward, result = environment.run_episode(policy, seed)
        rewards.append(episode_reward)
        metrics = result.metrics
        if metrics.get("meanWaitHours") is not None:
            waits.append(float(metrics["meanWaitHours"]))
        if metrics.get("meanTurnaroundHours") is not None:
            turnarounds.append(float(metrics["meanTurnaroundHours"]))
        completed.append(int(metrics.get("completedCalls", 0)))
        missed.append(int(metrics.get("missedDepartures", 0)))
        utilisation.append(float(metrics.get("berthUtilisation", 0.0)))
        overflow.append(int(metrics.get("yardOverflowBlocks", 0)))
        violations += len(result.violations)
        rejected += len(result.rejected_actions)
        for key, value in reward_breakdown(result).items():
            totals[key] = totals.get(key, 0.0) + value

    return PolicyEvaluation(
        policy_id=policy.policy_id,
        name=policy.name,
        family=policy.family,
        episodes=episodes,
        mean_reward=statistics.fmean(rewards) if rewards else 0.0,
        reward_stdev=statistics.pstdev(rewards) if len(rewards) > 1 else 0.0,
        min_reward=min(rewards) if rewards else 0.0,
        max_reward=max(rewards) if rewards else 0.0,
        mean_wait_hours=statistics.fmean(waits) if waits else None,
        mean_turnaround_hours=statistics.fmean(turnarounds) if turnarounds else None,
        completed_calls=statistics.fmean(completed) if completed else 0.0,
        missed_departures=statistics.fmean(missed) if missed else 0.0,
        violations=violations,
        rejected_actions=rejected,
        berth_utilisation=statistics.fmean(utilisation) if utilisation else 0.0,
        yard_overflow_blocks=statistics.fmean(overflow) if overflow else 0.0,
        seeds=seeds,
        breakdown={k: round(v / max(1, episodes), 3) for k, v in totals.items()},
    )


@dataclass
class BenchmarkResult:
    """Every policy on the same held-out scenarios, ranked."""

    spec: Dict[str, Any]
    episodes: int
    evaluations: List[PolicyEvaluation]
    baseline_policy_id: str
    ran_at: Optional[str] = None

    @property
    def baseline(self) -> Optional[PolicyEvaluation]:
        return next(
            (e for e in self.evaluations if e.policy_id == self.baseline_policy_id), None
        )

    def improvement(self, policy_id: str) -> Optional[float]:
        """Fractional reward improvement over the baseline, or ``None``.

        Reward here is negative-dominated (it is mostly costs), so the
        improvement is computed on the *gap*, not the raw ratio, which would be
        meaningless across a sign change.
        """
        base = self.baseline
        target = next((e for e in self.evaluations if e.policy_id == policy_id), None)
        if base is None or target is None:
            return None
        denominator = abs(base.mean_reward)
        if denominator < 1e-6:
            return None
        return (target.mean_reward - base.mean_reward) / denominator

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ranAt": self.ran_at,
            "spec": self.spec,
            "episodes": self.episodes,
            "baselinePolicyId": self.baseline_policy_id,
            "evaluations": [
                {
                    **e.to_dict(),
                    "improvementVsBaseline": (
                        None if (imp := self.improvement(e.policy_id)) is None
                        else round(imp, 4)
                    ),
                }
                for e in sorted(self.evaluations, key=lambda x: -x.mean_reward)
            ],
            "note": (
                "Every policy ran the same held-out scenario seeds, disjoint from the "
                "training range. Reward is the operational cost function in "
                "src.portwatch_os.twin.simulation.REWARD_WEIGHTS; higher is better."
            ),
        }


def benchmark(
    environment: PortEnvironment,
    policies: Sequence[BasePolicy],
    *,
    episodes: int = 40,
    baseline_policy_id: str = "fcfs",
    ran_at: Optional[str] = None,
) -> BenchmarkResult:
    """Run every policy over the same held-out seeds."""
    evaluations = [
        evaluate(environment, policy, episodes=episodes) for policy in policies
    ]
    result = BenchmarkResult(
        spec=environment.spec.to_dict(),
        episodes=episodes,
        evaluations=evaluations,
        baseline_policy_id=baseline_policy_id,
        ran_at=ran_at,
    )
    log.info(
        "Policy benchmark over %d held-out episodes: leader %s.",
        episodes,
        max(evaluations, key=lambda e: e.mean_reward).name if evaluations else "none",
    )
    return result


def default_policies(trained: Optional[ContextualBanditPolicy] = None) -> List[BasePolicy]:
    """The standard comparison set: the floor, the incumbent, two optimisers."""
    policies: List[BasePolicy] = [
        RandomPolicy(), FirstComeFirstServed(), GreedyPolicy(), LookaheadPolicy(),
    ]
    if trained is not None:
        policies.append(trained)
    return policies


__all__ = [
    "EVAL_SEED_BASE",
    "TRAIN_SEED_BASE",
    "BenchmarkResult",
    "PolicyEvaluation",
    "PortEnvironment",
    "ScenarioSpec",
    "TrainingReport",
    "benchmark",
    "default_policies",
    "evaluate",
    "train_bandit",
]
