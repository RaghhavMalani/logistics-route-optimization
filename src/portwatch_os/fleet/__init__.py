"""Company fleets.

The shipped fleet belongs to a fictional carrier and says so everywhere it is
shown. :func:`from_provider` is the seam a real carrier account plugs into.
"""

from src.portwatch_os.fleet.company import (
    COMPANY_DISCLAIMER,
    DEMO_COMPANY_ID,
    SOURCE_PROVIDER,
    SOURCE_SIMULATED,
    CompanyProfile,
    FleetVessel,
    attach_etas,
    capacities_for,
    demo_company,
    from_provider,
)

__all__ = [
    "COMPANY_DISCLAIMER", "DEMO_COMPANY_ID", "SOURCE_PROVIDER",
    "SOURCE_SIMULATED", "CompanyProfile", "FleetVessel", "attach_etas",
    "capacities_for", "demo_company", "from_provider",
]
