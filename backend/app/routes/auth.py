"""Compatibility import for one release. Use backend.app.domains.system.auth."""

import sys

from backend.app.domains.system import auth as _implementation

sys.modules[__name__] = _implementation
