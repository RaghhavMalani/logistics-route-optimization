"""The world as a typed, temporal graph.

The existing Global Eye exposure module walks one fixed chain --
``event -> chokepoint -> lane -> vessel -> port`` -- as a pipeline of hand-written
functions. That was the right way to prove the chain computes something real,
and it is why this module can exist: the physics is already known-good.

What a pipeline cannot do is grow. Adding cargo, berths, commodities or
companies to a five-function pipeline means writing the cross product of hops by
hand, and every new node type multiplies the work. Adding them to a typed graph
means declaring the node and the edges it participates in.

So the shape here is deliberately small:

*   A **node** is a thing in the world with an identity and a lifetime.
*   An **edge** is a *relationship along which consequence can travel*, with a
    transfer coefficient and a lifetime of its own.
*   Both are temporal, so the graph can be asked what it looked like -- or will
    look like -- at any instant. That is what makes the 4D scrubber a query
    rather than a separate prediction system.

Nothing in this module knows what a consequence *is*. It holds structure and
time. The meaning lives in :mod:`~src.portwatch_os.world.transfer`, and the
traversal in :mod:`~src.portwatch_os.world.cascade`, so that a change to how a
delay becomes money cannot accidentally change what the world contains.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, Iterable, Iterator, List, Optional, Sequence, Tuple

from src.portwatch_os.world.quantity import ALWAYS, Interval

# --------------------------------------------------------------------------
# vocabulary
# --------------------------------------------------------------------------

EVENT = "event"
PLACE = "place"
CHOKEPOINT = "chokepoint"
LANE = "lane"
VESSEL = "vessel"
COMPANY = "company"
PORT = "port"
BERTH = "berth"
CARGO = "cargo"
COMMODITY = "commodity"

NODE_KINDS: Tuple[str, ...] = (
    EVENT,
    PLACE,
    CHOKEPOINT,
    LANE,
    VESSEL,
    COMPANY,
    PORT,
    BERTH,
    CARGO,
    COMMODITY,
)

#: An event puts a place or a chokepoint at risk.
THREATENS = "threatens"
#: A lane's routing passes through a chokepoint. A routing fact, not a judgement.
TRANSITS = "transits"
#: A vessel's current voyage runs on a lane.
SAILS = "sails"
#: A vessel is bound for a port.
BOUND_FOR = "bound_for"
#: A vessel is operated by a company.
OPERATED_BY = "operated_by"
#: A port contains a berth.
HAS_BERTH = "has_berth"
#: A vessel is carrying a consignment.
CARRIES = "carries"
#: A consignment's onward connection depends on another vessel.
CONNECTS_TO = "connects_to"
#: A consignment is of a commodity.
IS_COMMODITY = "is_commodity"
#: A lane calls at a port.
SERVES = "serves"

EDGE_KINDS: Tuple[str, ...] = (
    THREATENS,
    TRANSITS,
    SAILS,
    BOUND_FOR,
    OPERATED_BY,
    HAS_BERTH,
    CARRIES,
    CONNECTS_TO,
    IS_COMMODITY,
    SERVES,
)


class GraphError(ValueError):
    """The graph was asked to hold something it cannot."""


def key(kind: str, identifier: str) -> str:
    """A node's address. Typed, so two id spaces cannot silently collide.

    Vessel ``PWD-001`` and cargo ``PWD-001`` are different things, and the
    advisory bug that prompted much of this work was exactly two unrelated id
    spaces being treated as one.
    """
    return f"{kind}:{identifier}"


# --------------------------------------------------------------------------
# elements
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Node:
    """One thing in the world."""

    key: str
    kind: str
    label: str
    interval: Interval = ALWAYS
    attrs: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.kind not in NODE_KINDS:
            raise GraphError(f"{self.kind!r} is not a node kind this world holds")

    @property
    def identifier(self) -> str:
        return self.key.split(":", 1)[1] if ":" in self.key else self.key

    def alive_at(self, moment: Optional[datetime]) -> bool:
        return moment is None or self.interval.contains(moment)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "key": self.key,
            "kind": self.kind,
            "label": self.label,
            "interval": self.interval.to_dict(),
            "attrs": self.attrs,
        }


@dataclass(frozen=True)
class Edge:
    """A relationship consequence can travel along.

    ``weight`` is a transfer coefficient in 0..1, not a distance: it says how
    much of what arrives at ``src`` reaches ``dst``. A routing fact -- this lane
    does pass that strait -- carries 1.0 and means it. Anything below 1.0 has to
    be justified by the transfer that reads it.
    """

    src: str
    dst: str
    kind: str
    weight: float = 1.0
    interval: Interval = ALWAYS
    attrs: Dict[str, Any] = field(default_factory=dict)
    #: Where this relationship came from -- a catalogue, a provider, a model.
    #: Read by Evidence Mode; never used in arithmetic.
    source: str = ""

    def __post_init__(self) -> None:
        if self.kind not in EDGE_KINDS:
            raise GraphError(f"{self.kind!r} is not an edge kind this world holds")
        if not 0.0 <= self.weight <= 1.0:
            raise GraphError(
                f"edge weight {self.weight} is a transfer coefficient and must lie "
                "in 0..1; a magnitude belongs in the quantity, not the edge"
            )

    def alive_at(self, moment: Optional[datetime]) -> bool:
        return moment is None or self.interval.contains(moment)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "src": self.src,
            "dst": self.dst,
            "kind": self.kind,
            "weight": round(self.weight, 4),
            "interval": self.interval.to_dict(),
            "attrs": self.attrs,
            "source": self.source,
        }


# --------------------------------------------------------------------------
# the graph
# --------------------------------------------------------------------------


class WorldGraph:
    """Nodes, edges, and a temporal view over both.

    Adjacency is indexed on insert because a cascade walks outward from a seed
    many times per request -- once per scenario branch in a "what happens next"
    comparison -- and scanning every edge each time would make the interaction
    the product is named for too slow to feel live.
    """

    def __init__(self) -> None:
        self._nodes: Dict[str, Node] = {}
        self._out: Dict[str, List[Edge]] = defaultdict(list)
        self._in: Dict[str, List[Edge]] = defaultdict(list)
        self._edges: List[Edge] = []

    # -- building --------------------------------------------------------
    def add_node(self, node: Node) -> Node:
        """Add or replace a node. Replacing keeps its edges."""
        self._nodes[node.key] = node
        return node

    def add_edge(self, edge: Edge) -> Edge:
        """Add an edge. Both endpoints must already exist.

        Requiring the endpoints is what stops the graph accumulating relations
        to things nobody defined -- the state in which a traversal silently
        stops early and the answer looks merely small rather than wrong.
        """
        for endpoint in (edge.src, edge.dst):
            if endpoint not in self._nodes:
                raise GraphError(
                    f"cannot relate {edge.src} -> {edge.dst}: {endpoint} is not in "
                    "the graph. Add the node before the edge that reaches it."
                )
        self._edges.append(edge)
        self._out[edge.src].append(edge)
        self._in[edge.dst].append(edge)
        return edge

    # -- reading ---------------------------------------------------------
    def node(self, node_key: str) -> Optional[Node]:
        return self._nodes.get(node_key)

    def require(self, node_key: str) -> Node:
        found = self._nodes.get(node_key)
        if found is None:
            raise GraphError(f"no node {node_key} in this world")
        return found

    def nodes(self, *, kind: Optional[str] = None,
              at: Optional[datetime] = None) -> List[Node]:
        return [
            n for n in self._nodes.values()
            if (kind is None or n.kind == kind) and n.alive_at(at)
        ]

    def edges(self, *, kind: Optional[str] = None,
              at: Optional[datetime] = None) -> List[Edge]:
        return [
            e for e in self._edges
            if (kind is None or e.kind == kind) and e.alive_at(at)
        ]

    def out_edges(
        self,
        node_key: str,
        *,
        kind: Optional[str] = None,
        at: Optional[datetime] = None,
    ) -> List[Edge]:
        """Edges leaving a node that are live at ``at`` and land somewhere live."""
        return [
            e for e in self._out.get(node_key, ())
            if (kind is None or e.kind == kind)
            and e.alive_at(at)
            and self._endpoint_alive(e.dst, at)
        ]

    def in_edges(
        self,
        node_key: str,
        *,
        kind: Optional[str] = None,
        at: Optional[datetime] = None,
    ) -> List[Edge]:
        return [
            e for e in self._in.get(node_key, ())
            if (kind is None or e.kind == kind)
            and e.alive_at(at)
            and self._endpoint_alive(e.src, at)
        ]

    def neighbours(
        self,
        node_key: str,
        *,
        kind: Optional[str] = None,
        at: Optional[datetime] = None,
    ) -> List[Node]:
        return [
            self._nodes[e.dst] for e in self.out_edges(node_key, kind=kind, at=at)
        ]

    def _endpoint_alive(self, node_key: str, at: Optional[datetime]) -> bool:
        node = self._nodes.get(node_key)
        return node is not None and node.alive_at(at)

    # -- whole-graph views ----------------------------------------------
    def at(self, moment: datetime) -> "WorldGraph":
        """The subgraph live at one instant.

        Materialised rather than filtered lazily because the caller is usually
        about to run several cascades over the same instant -- comparing a
        baseline against two responses, say -- and paying the filter once is
        cheaper than paying it per traversal.
        """
        view = WorldGraph()
        for node in self._nodes.values():
            if node.alive_at(moment):
                view.add_node(node)
        for edge in self._edges:
            if (
                edge.alive_at(moment)
                and edge.src in view._nodes
                and edge.dst in view._nodes
            ):
                view.add_edge(edge)
        return view

    def __len__(self) -> int:
        return len(self._nodes)

    def __contains__(self, node_key: object) -> bool:
        return node_key in self._nodes

    def __iter__(self) -> Iterator[Node]:
        return iter(self._nodes.values())

    def summary(self) -> Dict[str, Any]:
        by_node: Dict[str, int] = defaultdict(int)
        for node in self._nodes.values():
            by_node[node.kind] += 1
        by_edge: Dict[str, int] = defaultdict(int)
        for edge in self._edges:
            by_edge[edge.kind] += 1
        return {
            "nodes": len(self._nodes),
            "edges": len(self._edges),
            "byNodeKind": dict(sorted(by_node.items())),
            "byEdgeKind": dict(sorted(by_edge.items())),
        }

    def to_dict(self) -> Dict[str, Any]:
        return {
            "nodes": [n.to_dict() for n in self._nodes.values()],
            "edges": [e.to_dict() for e in self._edges],
            "summary": self.summary(),
        }


__all__ = [
    "BERTH",
    "BOUND_FOR",
    "CARGO",
    "CARRIES",
    "CHOKEPOINT",
    "COMMODITY",
    "COMPANY",
    "CONNECTS_TO",
    "EDGE_KINDS",
    "EVENT",
    "Edge",
    "GraphError",
    "HAS_BERTH",
    "IS_COMMODITY",
    "LANE",
    "NODE_KINDS",
    "Node",
    "OPERATED_BY",
    "PLACE",
    "PORT",
    "SAILS",
    "SERVES",
    "THREATENS",
    "TRANSITS",
    "VESSEL",
    "WorldGraph",
    "key",
]
