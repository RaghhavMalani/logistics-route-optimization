"""Compatibility import for one release. Use backend.app.domains.system.agents."""

import sys

from backend.app.domains.system import agents as _implementation

sys.modules[__name__] = _implementation
