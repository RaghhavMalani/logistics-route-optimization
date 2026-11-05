"""Compatibility import for one release. Use backend.app.domains.system.admin."""

import sys

from backend.app.domains.system import admin as _implementation

sys.modules[__name__] = _implementation
