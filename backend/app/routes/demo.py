"""Compatibility import for one release. Use backend.app.domains.system.demo."""

import sys

from backend.app.domains.system import demo as _implementation

sys.modules[__name__] = _implementation
