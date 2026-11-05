"""Compatibility import for one release. Use backend.app.domains.system.demo_terminal."""

import sys

from backend.app.domains.system import demo_terminal as _implementation

sys.modules[__name__] = _implementation
