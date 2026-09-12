"""Consequence propagation, and the record of how it got there.

A cascade starts with one claim about one node -- "this event is severe, and it
bears on the Red Sea" -- and walks outward, applying a transfer at every hop
until the consequence is too small, too uncertain, or too far to matter.

The hard part of a graph like this is not the walking. It is stopping. A world
model in which every node eventually affects every other node is worthless: it
produces a list of everything and a ranking of nothing. So the engine attenuates
and then refuses to continue:

*   **Magnitude floor.** Below it, this branch is noise.
*   **Confidence floor.** Multiplicative attenuation means a long chain decays
    on its own; the floor is where it stops being evidence.
*   **Depth and node budget.** Hard stops, so an unexpected shape in the graph
    cannot turn one question into an unbounded traversal.
*   **Cycle safety.** A vessel bound for a port that serves a lane the vessel
    sails is a real, correct cycle in the world; it must not be one in the walk.

Every hop is recorded as a :class:`Step` carrying the edge, the transfer that
ran, and the quantities in and out. That record *is* Evidence Mode: "why do you
think this?" is answered by replaying the steps that produced a number, not by a
separate explanation system that could drift from the computation.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Sequence, Tuple

from src.portwatch_os.world.graph import BOUND_FOR, Edge, Node, WorldGraph
from src.portwatch_os.world.quantity import Quantity, aggregate
from src.portwatch_os.world.transfers import (
    Transferred,
    derivation_for,
    transfer_for,
)

#: Defaults chosen so a cascade answers in one interaction rather than
#: enumerating the world. They are arguments, not constants, because a
#: "what happens next" projection legitimately wants to run deeper than a
#: hover does.
DEFAULT_MAGNITUDE_FLOOR = 0.02
DEFAULT_CONFIDENCE_FLOOR = 0.15
DEFAULT_MAX_DEPTH = 6
DEFAULT_MAX_NODES = 2000


@dataclass(frozen=True)
class Step:
    """One hop: what arrived, what left, and along which relationship."""

    depth: int
    edge: Edge
    rule: str
    incoming: Quantity
    outgoing: Tuple[Quantity, ...] = ()
    declined: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "depth": self.depth,
            "from": self.edge.src,
            "to": self.edge.dst,
            "edgeKind": self.edge.kind,
            "rule": self.rule,
            "source": self.edge.source,
            "incoming": self.incoming.to_dict(),
            "outgoing": [q.to_dict() for q in self.outgoing],
            "declined": self.declined,
        }


@dataclass
class Reached:
    """What a cascade concluded about one node."""

    node: Node
    depth: int
    quantities: Dict[str, Quantity] = field(default_factory=dict)
    #: Indices into :attr:`Cascade.steps` that produced these quantities.
    step_indices: List[int] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "node": self.node.to_dict(),
            "depth": self.depth,
            "quantities": {u: q.to_dict() for u, q in sorted(self.quantities.items())},
            "steps": self.step_indices,
        }


@dataclass
class Cascade:
    """The full consequence of one seed, and the trace that produced it."""

    seed_key: str
    seed: Quantity
    at: Optional[datetime] = None
    reached: Dict[str, Reached] = field(default_factory=dict)
    steps: List[Step] = field(default_factory=list)
    #: Hops that could not be computed, with the reason. Not failures -- these
    #: are usually the most operationally interesting lines in the output.
    notes: List[str] = field(default_factory=list)
    truncated: bool = False

    # -- reading ---------------------------------------------------------
    def by_kind(self, kind: str) -> List[Reached]:
        """Everything of one node kind the cascade reached, worst first."""
        rows = [r for r in self.reached.values() if r.node.kind == kind]
        return sorted(rows, key=_severity, reverse=True)

    def total(self, unit: str) -> Optional[Quantity]:
        """The whole cascade's exposure in one unit.

        Summed over the *frontier* for additive units rather than over every
        node, because a delay counted at a vessel and again at the port it is
        bound for would double-count the same lost hours.
        """
        found = [
            r.quantities[unit] for r in self.reached.values() if unit in r.quantities
        ]
        if not found:
            return None
        folded = aggregate(found)
        return folded.get(unit)

    def explain(self, node_key: str) -> List[Step]:
        """The whole chain of inference that reached a node, seed first.

        Not merely the last hop. "Why do you think MV Konkan is exposed?" is
        answered by the route from the event to that hull -- the report, the
        chokepoint it was classified onto, the lane catalogue that says this
        routing transits it, and only then the timing that makes this particular
        ship exposed. Showing the final step alone would answer a narrower
        question than the one an operator is asking.

        Walks backwards from the node through the steps that produced it, then
        reverses, so the reader gets cause before effect. Cycles in the world are
        real -- a vessel bound for a port that serves the lane it sails -- so
        visited nodes are tracked rather than trusted not to recur.
        """
        reached = self.reached.get(node_key)
        if reached is None:
            return []

        # Every step that landed on a given node, so ancestry can be walked.
        landing: Dict[str, List[int]] = defaultdict(list)
        for index, step in enumerate(self.steps):
            landing[step.edge.dst].append(index)

        chain: List[int] = []
        seen_steps: set[int] = set()
        seen_nodes: set[str] = set()
        frontier = [node_key]
        while frontier:
            current = frontier.pop(0)
            if current in seen_nodes:
                continue
            seen_nodes.add(current)
            for index in landing.get(current, ()):
                if index in seen_steps:
                    continue
                seen_steps.add(index)
                chain.append(index)
                source = self.steps[index].edge.src
                if source != current:
                    frontier.append(source)

        # Depth first, then registration order: cause before effect.
        chain.sort(key=lambda i: (self.steps[i].depth, i))
        return [self.steps[i] for i in chain]

    def to_dict(self, *, include_steps: bool = True) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "seed": {"node": self.seed_key, "quantity": self.seed.to_dict()},
            "at": None if self.at is None else self.at.isoformat(),
            "reached": [
                r.to_dict()
                for r in sorted(self.reached.values(), key=_severity, reverse=True)
            ],
            "notes": self.notes,
            "truncated": self.truncated,
            "nodeCount": len(self.reached),
        }
        if include_steps:
            payload["steps"] = [s.to_dict() for s in self.steps]
        return payload


def _severity(reached: Reached) -> float:
    """Order nodes by the largest normalised magnitude they carry."""
    best = 0.0
    for unit, quantity in reached.quantities.items():
        scale = {"risk": 1.0, "ratio": 1.0, "vessels": 0.1, "hours": 0.01}.get(unit, 0.0)
        best = max(best, quantity.value * scale * quantity.confidence)
    return best


# --------------------------------------------------------------------------
# the engine
# --------------------------------------------------------------------------


def propagate(
    graph: WorldGraph,
    seed_key: str,
    seed: Quantity,
    *,
    at: Optional[datetime] = None,
    magnitude_floor: float = DEFAULT_MAGNITUDE_FLOOR,
    confidence_floor: float = DEFAULT_CONFIDENCE_FLOOR,
    max_depth: int = DEFAULT_MAX_DEPTH,
    max_nodes: int = DEFAULT_MAX_NODES,
) -> Cascade:
    """Walk a consequence outward from ``seed_key`` and record what it does.

    Breadth-first, so a node is reached by its shortest chain of inference
    first: the explanation an operator is shown is the most direct one available
    rather than whichever path the traversal happened to take.
    """
    start = graph.node(seed_key)
    if start is None:
        raise KeyError(f"no node {seed_key} in this world")

    cascade = Cascade(seed_key=seed_key, seed=seed, at=at)
    cascade.reached[seed_key] = Reached(node=start, depth=0, quantities={seed.unit: seed})

    # (node key, quantity to push onward, depth). A node can be queued more than
    # once carrying different units -- that is the point of a typed dataflow.
    frontier: List[Tuple[str, Quantity, int]] = [(seed_key, seed, 0)]
    # Cycle safety per unit: revisiting a node with a *different* unit is
    # legitimate work, revisiting it with the same one is a loop.
    seen: set[Tuple[str, str]] = {(seed_key, seed.unit)}

    while frontier:
        node_key, carried, depth = frontier.pop(0)
        if depth >= max_depth:
            cascade.truncated = True
            continue
        if len(cascade.reached) >= max_nodes:
            cascade.truncated = True
            break

        src_node = graph.require(node_key)
        for edge in graph.out_edges(node_key, at=at):
            rule = transfer_for(edge.kind, carried.unit)
            if rule is None:
                # No rule for this (relationship, unit). Not an error: most
                # relationships do not carry most units, and saying so for every
                # one of them would bury the notes that matter.
                continue

            dst_node = graph.require(edge.dst)
            result: Transferred = rule(carried, edge, src_node, dst_node)
            step = Step(
                depth=depth + 1,
                edge=edge,
                rule=rule.__name__,
                incoming=carried,
                outgoing=tuple(result.quantities),
                declined=result.declined,
            )

            if result.declined:
                cascade.steps.append(step)
                cascade.notes.append(f"{dst_node.label}: {result.declined}")
                continue

            kept: List[Quantity] = []
            for produced in result.quantities:
                if produced.value < magnitude_floor and produced.unit != "vessels":
                    continue
                if produced.confidence < confidence_floor:
                    continue
                kept.append(produced)

            if not kept:
                continue

            cascade.steps.append(step)
            step_index = len(cascade.steps) - 1

            reached = cascade.reached.get(edge.dst)
            if reached is None:
                reached = Reached(node=dst_node, depth=depth + 1)
                cascade.reached[edge.dst] = reached
            reached.step_indices.append(step_index)

            for produced in kept:
                existing = reached.quantities.get(produced.unit)
                reached.quantities[produced.unit] = (
                    produced if existing is None else existing.combined_with(produced)
                )
                marker = (edge.dst, produced.unit)
                if marker not in seen:
                    seen.add(marker)
                    frontier.append((edge.dst, reached.quantities[produced.unit], depth + 1))

    # Derivations run once the walk has settled, because a node-local rule reads
    # the *aggregate* that reached it. Yard pressure from one late ship and from
    # ten arriving into the same window are different findings, and running the
    # rule per arrival would compute the first while the second is what is true.
    _derive_settled(
        cascade,
        magnitude_floor=magnitude_floor,
        confidence_floor=confidence_floor,
    )
    return cascade


def _derive_settled(
    cascade: Cascade,
    *,
    magnitude_floor: float,
    confidence_floor: float,
) -> None:
    """Apply node-local rules to the aggregates a cascade came to rest on.

    Iterates to a fixed point so a chain of derivations -- hours to pressure to
    money -- completes, bounded by the number of units so a rule that produced
    its own input could not spin.
    """
    from src.portwatch_os.world.quantity import UNITS

    for _ in range(len(UNITS)):
        produced_any = False
        for reached in list(cascade.reached.values()):
            for unit, quantity in list(reached.quantities.items()):
                rule = derivation_for(reached.node.kind, unit)
                if rule is None:
                    continue
                result = rule(quantity, reached.node)
                if result.declined:
                    note = f"{reached.node.label}: {result.declined}"
                    if note not in cascade.notes:
                        cascade.notes.append(note)
                    continue
                for derived in result.quantities:
                    if derived.unit in reached.quantities:
                        continue        # already settled; do not compound it
                    if derived.value < magnitude_floor:
                        continue
                    if derived.confidence < confidence_floor:
                        continue
                    cascade.steps.append(
                        Step(
                            depth=reached.depth,
                            edge=Edge(
                                src=reached.node.key,
                                dst=reached.node.key,
                                kind=BOUND_FOR,
                                source="node derivation",
                            ),
                            rule=rule.__name__,
                            incoming=quantity,
                            outgoing=(derived,),
                        )
                    )
                    reached.step_indices.append(len(cascade.steps) - 1)
                    reached.quantities[derived.unit] = derived
                    produced_any = True
        if not produced_any:
            return


def narrate(cascade: Cascade, *, limit: int = 8) -> List[str]:
    """The cascade as the sentence a person would say.

    Deliberately built from the same objects the numbers came from, so a
    narrative line cannot claim something the graph does not hold.
    """
    lines: List[str] = []
    seed = cascade.reached.get(cascade.seed_key)
    if seed is not None:
        lines.append(f"{seed.node.label}: {cascade.seed}")

    for reached in sorted(cascade.reached.values(), key=_severity, reverse=True):
        if reached.node.key == cascade.seed_key:
            continue
        if len(lines) > limit:
            break
        parts = ", ".join(
            str(q) for _, q in sorted(reached.quantities.items())
        )
        lines.append(f"{reached.node.label}: {parts}")
    return lines


__all__ = [
    "Cascade",
    "DEFAULT_CONFIDENCE_FLOOR",
    "DEFAULT_MAGNITUDE_FLOOR",
    "DEFAULT_MAX_DEPTH",
    "DEFAULT_MAX_NODES",
    "Reached",
    "Step",
    "narrate",
    "propagate",
]
