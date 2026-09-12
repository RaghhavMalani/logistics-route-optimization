"""The World State Engine: what is true, where, when, and what follows from it.

Global Eye computes one chain -- event to chokepoint to lane to vessel to port --
as a pipeline of hand-written functions. This package generalises that into a
typed temporal graph so the chain can grow to cargo, berths, companies and
commodities without the cross product of hops being written by hand.

The idea that makes it more than a scored graph is that **a consequence changes
unit as it travels**:

    risk -> exposed vessels -> delay hours -> yard pressure -> rupees

Each of those arrows is a named transfer function with a stated basis, so the
engine can never multiply a severity by a distance and call the result an
impact. A transfer that cannot compute its output returns nothing and says why,
which keeps the "no invented numbers" rule the rest of PortWatch already holds.

Four modules, in the order they depend on each other:

*   :mod:`~src.portwatch_os.world.quantity` -- dimensioned magnitudes, temporal
    validity, and the only arithmetic permitted on them.
*   :mod:`~src.portwatch_os.world.graph` -- nodes, edges and time. Structure
    only; it does not know what a consequence is.
*   :mod:`~src.portwatch_os.world.transfers` -- the domain. One rule per
    (relationship, incoming unit).
*   :mod:`~src.portwatch_os.world.cascade` -- the walk, its stopping rules, and
    the step-by-step record that answers "why do you think this?".

:mod:`~src.portwatch_os.world.build` assembles a graph from the catalogues
PortWatch already ships, so nothing here invents a world to reason about.
"""

from src.portwatch_os.world.build import build_world, seed_for
from src.portwatch_os.world.cascade import Cascade, Reached, Step, narrate, propagate
from src.portwatch_os.world.graph import Edge, Node, WorldGraph, key
from src.portwatch_os.world.quantity import (
    BERTH_HOURS,
    HOURS,
    INR,
    Interval,
    Quantity,
    RATIO,
    RISK,
    TEU,
    VESSELS,
    hours,
    risk,
    utc,
    window,
)
from src.portwatch_os.world.transfers import registered, transfer_for

__all__ = [
    "BERTH_HOURS",
    "Cascade",
    "Edge",
    "HOURS",
    "INR",
    "Interval",
    "Node",
    "Quantity",
    "RATIO",
    "RISK",
    "Reached",
    "Step",
    "TEU",
    "VESSELS",
    "WorldGraph",
    "build_world",
    "hours",
    "key",
    "narrate",
    "propagate",
    "registered",
    "risk",
    "seed_for",
    "transfer_for",
    "utc",
    "window",
]
