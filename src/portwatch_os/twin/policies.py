"""Berth-allocation policies, from a rule to a learned one.

The progression here is deliberate and it stops where the evidence stops:

1.  :class:`FirstComeFirstServed` -- the rule most terminals actually run.
    The baseline everything else has to beat.
2.  :class:`RandomPolicy` -- the sanity floor. If a learned policy cannot beat
    random it is broken, not clever.
3.  :class:`GreedyPolicy` -- assign the waiting vessel that clears fastest to
    the berth that fits it best. A real, defensible optimiser.
4.  :class:`LookaheadPolicy` -- greedy plus a one-step check on what the
    assignment does to the next arrival. Where a plain optimiser stops.
5.  :class:`ContextualBanditPolicy` -- learns which of the above rules to use in
    which state. This is the learned layer, and it is a bandit rather than deep
    RL on purpose: the action space is "which rule", the episode is short, and a
    bandit's behaviour can be explained to a port controller. There is no PPO in
    this repository because nothing here justifies one.

Every policy returns actions that go through
:func:`~src.portwatch_os.twin.simulation.validate_action`. None of them can
break a physical constraint, learned or not.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from src.portwatch_os.twin.simulation import (
    ASSIGN_BERTH,
    NO_ACTION,
    Action,
    PortState,
    call_work_hours,
    validate_action,
)
from src.portwatch_os.twin.state import Berth, VesselCall, WAITING


class BasePolicy:
    """A named policy. The name is what appears in the benchmark table."""

    policy_id: str = "base"
    name: str = "Base"
    family: str = "rule"
    description: str = ""

    def reset(self) -> None:
        """Called before each episode. Stateful policies clear here."""

    def __call__(self, state: PortState) -> List[Action]:
        return self.act(state)

    def act(self, state: PortState) -> List[Action]:  # pragma: no cover - abstract
        raise NotImplementedError

    def to_dict(self) -> Dict[str, Any]:
        return {
            "policyId": self.policy_id,
            "name": self.name,
            "family": self.family,
            "description": self.description,
        }


def _feasible_berths(state: PortState, call: VesselCall) -> List[Berth]:
    return [
        b for b in state.berths
        if b.occupied_by is None and b.can_accept(call.loa_m, call.draught_m, call.cargo_type)
        and b.crane_ids
    ]


def gang_size(call: VesselCall) -> int:
    """How many cranes a call of this size warrants.

    A 400 m vessel worked by two cranes sits alongside for three days. Terminals
    size the gang to the hull, and so does this: roughly one crane per 90 m of
    length, capped at five, which is the practical limit for a single vessel on
    a linear quay.
    """
    return int(max(1, min(5, round(call.loa_m / 90.0))))


def _cranes_for(
    state: PortState,
    berth: Berth,
    call: Optional[VesselCall] = None,
    want: Optional[int] = None,
) -> List[str]:
    """Free cranes able to serve this berth, fastest first."""
    if want is None:
        want = gang_size(call) if call is not None else 2
    available = [
        c for c in state.cranes
        if c.crane_id in berth.crane_ids and c.assigned_berth is None
    ]
    available.sort(key=lambda c: -c.moves_per_hour)
    return [c.crane_id for c in available[:want]]


# --------------------------------------------------------------------------
# baselines
# --------------------------------------------------------------------------


class FirstComeFirstServed(BasePolicy):
    """The incumbent rule: longest-waiting vessel takes the first berth that fits.

    This is what the benchmark's improvement figures are measured against,
    because it is what a terminal without this software does.
    """

    policy_id = "fcfs"
    name = "First come, first served"
    family = "rule"
    description = (
        "Assign the longest-waiting vessel to the first compatible free berth. "
        "The incumbent rule and the benchmark baseline."
    )

    def act(self, state: PortState) -> List[Action]:
        actions: List[Action] = []
        taken: set[str] = set()
        for call in state.waiting_calls():
            options = [b for b in _feasible_berths(state, call) if b.berth_id not in taken]
            if not options:
                continue
            berth = options[0]
            taken.add(berth.berth_id)
            actions.append(
                Action(
                    kind=ASSIGN_BERTH, call_id=call.call_id, berth_id=berth.berth_id,
                    crane_ids=_cranes_for(state, berth, call),
                    reason="first compatible berth, longest wait first",
                )
            )
        return actions or [Action(kind=NO_ACTION)]


class RandomPolicy(BasePolicy):
    """Random feasible assignment. The floor any learned policy must clear."""

    policy_id = "random"
    name = "Random feasible"
    family = "baseline"
    description = "Assign waiting vessels to a random compatible free berth."

    def __init__(self, seed: int = 20260909) -> None:
        self.seed = seed
        self._rng = random.Random(seed)

    def reset(self) -> None:
        self._rng = random.Random(self.seed)

    def act(self, state: PortState) -> List[Action]:
        actions: List[Action] = []
        taken: set[str] = set()
        waiting = state.waiting_calls()
        self._rng.shuffle(waiting)
        for call in waiting:
            options = [b for b in _feasible_berths(state, call) if b.berth_id not in taken]
            if not options:
                continue
            berth = self._rng.choice(options)
            taken.add(berth.berth_id)
            actions.append(
                Action(kind=ASSIGN_BERTH, call_id=call.call_id, berth_id=berth.berth_id,
                       crane_ids=_cranes_for(state, berth, call), reason="random feasible berth")
            )
        return actions or [Action(kind=NO_ACTION)]


# --------------------------------------------------------------------------
# optimisers
# --------------------------------------------------------------------------


class GreedyPolicy(BasePolicy):
    """Shortest-work-first with a berth-fit penalty.

    Two ideas, both standard scheduling results and both defensible to a
    controller:

    *   Serving the shortest job first minimises mean waiting time across a
        queue. That is a theorem, not a hunch.
    *   Putting a small vessel on the largest berth wastes the berth. The fit
        penalty makes the assignment prefer the tightest berth that works, which
        keeps the big berths free for the vessels that need them.
    """

    policy_id = "greedy"
    name = "Greedy shortest-work"
    family = "optimiser"
    description = (
        "Shortest expected cargo work first, assigned to the tightest compatible "
        "berth. Minimises mean wait under a single-server queue argument."
    )

    #: Weight on wasted berth length, in equivalent hours per metre.
    fit_penalty = 0.004

    def act(self, state: PortState) -> List[Action]:
        actions: List[Action] = []
        taken: set[str] = set()

        scored: List[Tuple[float, VesselCall]] = []
        for call in state.waiting_calls():
            rate = max(1.0, gang_size(call) * 26.0)
            scored.append((call.moves / rate - call.priority * 4.0, call))
        scored.sort(key=lambda pair: pair[0])

        for _, call in scored:
            options = [b for b in _feasible_berths(state, call) if b.berth_id not in taken]
            if not options:
                continue
            berth = min(
                options,
                key=lambda b: (
                    self._work(state, call, b)
                    + self.fit_penalty * max(0.0, b.length_m - call.loa_m)
                ),
            )
            taken.add(berth.berth_id)
            actions.append(
                Action(
                    kind=ASSIGN_BERTH, call_id=call.call_id, berth_id=berth.berth_id,
                    crane_ids=_cranes_for(state, berth, call),
                    reason="shortest expected work, tightest compatible berth",
                )
            )
        return actions or [Action(kind=NO_ACTION)]

    @staticmethod
    def _work(state: PortState, call: VesselCall, berth: Berth) -> float:
        cranes = _cranes_for(state, berth, call)
        hours = call_work_hours(state, call, cranes) if cranes else None
        return hours if hours is not None else 999.0


class LookaheadPolicy(GreedyPolicy):
    """Greedy, plus one step of "what does this do to the next arrival?".

    A berth taken now by a long call is a berth unavailable when a bigger vessel
    arrives in three hours. This policy charges for that: an assignment that
    blocks the only berth an imminent arrival could use is penalised, so the
    scheduler holds the berth if the wait it saves is smaller than the wait it
    creates.
    """

    policy_id = "lookahead"
    name = "Greedy with arrival lookahead"
    family = "optimiser"
    description = (
        "Greedy shortest-work, penalised for occupying the only berth an "
        "imminent larger arrival could use."
    )

    #: How far ahead an arrival counts as imminent, hours.
    horizon_hours = 6.0
    #: Cost charged per hour of blocking, relative to hours saved.
    block_penalty = 0.8

    def act(self, state: PortState) -> List[Action]:
        imminent = [
            c for c in state.calls
            if c.state != WAITING and c.berth_id is None
            and state.hour <= c.effective_eta <= state.hour + self.horizon_hours
        ]
        actions: List[Action] = []
        taken: set[str] = set()

        scored: List[Tuple[float, VesselCall]] = []
        for call in state.waiting_calls():
            scored.append((
                call.moves / max(1.0, gang_size(call) * 26.0) - call.priority * 4.0,
                call,
            ))
        scored.sort(key=lambda pair: pair[0])

        for _, call in scored:
            options = [b for b in _feasible_berths(state, call) if b.berth_id not in taken]
            if not options:
                continue
            berth = min(options, key=lambda b: self._cost(state, call, b, imminent, options))
            taken.add(berth.berth_id)
            actions.append(
                Action(
                    kind=ASSIGN_BERTH, call_id=call.call_id, berth_id=berth.berth_id,
                    crane_ids=_cranes_for(state, berth, call),
                    reason="greedy with a penalty for blocking an imminent arrival",
                )
            )
        return actions or [Action(kind=NO_ACTION)]

    def _cost(
        self,
        state: PortState,
        call: VesselCall,
        berth: Berth,
        imminent: Sequence[VesselCall],
        options: Sequence[Berth],
    ) -> float:
        work = self._work(state, call, berth)
        cost = work + self.fit_penalty * max(0.0, berth.length_m - call.loa_m)
        for arriving in imminent:
            if not berth.can_accept(arriving.loa_m, arriving.draught_m, arriving.cargo_type):
                continue
            alternatives = [
                b for b in state.berths
                if b.berth_id != berth.berth_id and b.occupied_by is None
                and b.can_accept(arriving.loa_m, arriving.draught_m, arriving.cargo_type)
            ]
            if not alternatives:
                # This is the only berth that arrival can use. Blocking it costs
                # the arrival the whole of this call's occupancy.
                cost += self.block_penalty * work
        return cost


# --------------------------------------------------------------------------
# learned
# --------------------------------------------------------------------------

#: The state features the bandit discretises on. Kept to three, coarsely binned:
#: with a few hundred training episodes a finer context would learn noise.
def bandit_context(state: PortState) -> Tuple[int, int, int]:
    """Discretised context: queue pressure, yard pressure, weather."""
    queue = state.queue_length
    queue_bin = 0 if queue <= 1 else 1 if queue <= 3 else 2
    yard = state.yard_utilisation
    yard_bin = 0 if yard < 0.62 else 1 if yard < 0.78 else 2
    weather = state.weather_impact
    weather_bin = 0 if weather < 0.12 else 1 if weather < 0.3 else 2
    return queue_bin, yard_bin, weather_bin


@dataclass
class BanditArm:
    """One rule the bandit may choose, and how it has done."""

    policy_id: str
    pulls: int = 0
    total_reward: float = 0.0

    @property
    def mean(self) -> float:
        return self.total_reward / self.pulls if self.pulls else 0.0


class ContextualBanditPolicy(BasePolicy):
    """Chooses which scheduling rule to run, given the port's current state.

    A contextual bandit rather than a full RL agent, for reasons that are about
    the problem rather than about ambition:

    *   The berth-assignment inner loop is already solved well by the optimisers
        above. What is *not* known is which of them suits a congested yard in bad
        weather versus a quiet morning -- a rule-selection problem.
    *   Episodes are short and the reward is observed at the end, so there is no
        long credit-assignment chain for a value function to earn its keep on.
    *   UCB1's choice is explainable: "this arm has the best mean reward in this
        context, over this many trials". A port controller can audit that. A
        policy network's logits are not auditable in the same way, and this
        product will not deploy a recommendation nobody can question.

    If the action space later becomes per-vessel sequencing under a long horizon,
    that argument changes and a value-based method would be justified. It is not
    justified now, so it is not here.
    """

    policy_id = "bandit"
    name = "Contextual bandit rule selection"
    family = "learned"
    description = (
        "UCB1 over the scheduling rules, keyed on queue, yard and weather state. "
        "Learns which rule suits which regime; never invents an assignment itself."
    )

    #: Exploration constant. sqrt(2) is the standard UCB1 value.
    exploration = math.sqrt(2.0)

    def __init__(
        self,
        arms: Optional[Sequence[BasePolicy]] = None,
        *,
        seed: int = 20260909,
        explore: bool = True,
    ) -> None:
        self.arms: List[BasePolicy] = list(arms or [
            FirstComeFirstServed(), GreedyPolicy(), LookaheadPolicy()
        ])
        self.table: Dict[Tuple[int, int, int], Dict[str, BanditArm]] = {}
        self.explore = explore
        self._rng = random.Random(seed)
        #: Contexts touched during the current episode, for the update.
        self._episode: List[Tuple[Tuple[int, int, int], str]] = []

    def reset(self) -> None:
        self._episode = []
        for arm in self.arms:
            arm.reset()

    def _arms_for(self, context: Tuple[int, int, int]) -> Dict[str, BanditArm]:
        return self.table.setdefault(
            context, {arm.policy_id: BanditArm(arm.policy_id) for arm in self.arms}
        )

    def select(self, context: Tuple[int, int, int]) -> BasePolicy:
        arms = self._arms_for(context)
        total = sum(a.pulls for a in arms.values())
        if self.explore:
            unpulled = [a for a in arms.values() if a.pulls == 0]
            if unpulled:
                choice = self._rng.choice(unpulled).policy_id
                return next(a for a in self.arms if a.policy_id == choice)
        best_id = max(
            arms.values(),
            key=lambda a: (
                a.mean + self.exploration * math.sqrt(math.log(max(total, 1)) / a.pulls)
                if self.explore and a.pulls else a.mean
            ),
        ).policy_id
        return next(a for a in self.arms if a.policy_id == best_id)

    def act(self, state: PortState) -> List[Action]:
        context = bandit_context(state)
        arm = self.select(context)
        actions = arm.act(state)

        # Only a step that actually assigned something is a decision. Most steps
        # in an episode have nothing waiting and every arm would do the same
        # nothing; crediting those would bury the signal from the handful of
        # steps where the choice of rule mattered.
        decided = any(a.kind != NO_ACTION for a in actions)
        if decided:
            self._episode.append((context, arm.policy_id))

        for action in actions:
            if action.reason:
                action.reason = f"{arm.name}: {action.reason}"
        return actions

    def update(self, episode_reward: float) -> None:
        """Credit the episode's reward to the arms that made its decisions.

        Credit is split evenly across the episode's *decisions*, not its steps.
        That is still crude -- with one terminal reward and no value function
        there is no principled way to attribute a berthing three hours in to the
        wait it saved at the end -- and it is stated as crude rather than dressed
        up. It works here because an arm is a whole rule whose character does not
        change within an episode, so the mean over many episodes converges on
        that rule's value in that context.
        """
        if not self._episode:
            return
        share = episode_reward / len(self._episode)
        for context, policy_id in self._episode:
            arms = self._arms_for(context)
            arm = arms.setdefault(policy_id, BanditArm(policy_id))
            arm.pulls += 1
            arm.total_reward += share
        self._episode = []

    def freeze(self) -> "ContextualBanditPolicy":
        """A copy that exploits only. What gets evaluated and promoted."""
        frozen = ContextualBanditPolicy(self.arms, explore=False)
        frozen.table = {
            context: {k: BanditArm(k, v.pulls, v.total_reward) for k, v in arms.items()}
            for context, arms in self.table.items()
        }
        return frozen

    def to_dict(self) -> Dict[str, Any]:
        return {
            **super().to_dict(),
            "explore": self.explore,
            "arms": [a.policy_id for a in self.arms],
            "table": {
                "|".join(map(str, context)): {
                    k: {"pulls": v.pulls, "meanReward": round(v.mean, 3)}
                    for k, v in arms.items()
                }
                for context, arms in sorted(self.table.items())
            },
        }

    def load_table(self, payload: Dict[str, Any]) -> None:
        self.table = {}
        for key, arms in (payload or {}).items():
            context = tuple(int(part) for part in key.split("|"))  # type: ignore[assignment]
            self.table[context] = {  # type: ignore[index]
                policy_id: BanditArm(
                    policy_id,
                    int(value.get("pulls", 0)),
                    float(value.get("meanReward", 0.0)) * int(value.get("pulls", 0)),
                )
                for policy_id, value in arms.items()
            }


#: The registry the benchmark and the API iterate over.
POLICY_REGISTRY: Dict[str, Callable[[], BasePolicy]] = {
    "fcfs": FirstComeFirstServed,
    "random": RandomPolicy,
    "greedy": GreedyPolicy,
    "lookahead": LookaheadPolicy,
    "bandit": ContextualBanditPolicy,
}


def build_policy(policy_id: str) -> BasePolicy:
    factory = POLICY_REGISTRY.get(policy_id)
    if factory is None:
        raise KeyError(
            f"unknown policy {policy_id}; known: {', '.join(sorted(POLICY_REGISTRY))}"
        )
    return factory()


__all__ = [
    "POLICY_REGISTRY",
    "BanditArm",
    "BasePolicy",
    "ContextualBanditPolicy",
    "FirstComeFirstServed",
    "GreedyPolicy",
    "LookaheadPolicy",
    "RandomPolicy",
    "bandit_context",
    "build_policy",
    "gang_size",
]
