"""Compatibility import for one release. Use backend.app.domains.intelligence.public_workspace."""

import sys

from backend.app.domains.intelligence import public_workspace as _implementation

sys.modules[__name__] = _implementation
