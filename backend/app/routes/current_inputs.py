"""Compatibility import for one release. Use backend.app.domains.intelligence.current_inputs."""

import sys

from backend.app.domains.intelligence import current_inputs as _implementation

sys.modules[__name__] = _implementation
