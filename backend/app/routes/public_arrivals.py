"""Compatibility import for one release. Use backend.app.domains.ports.public_arrivals."""

import sys

from backend.app.domains.ports import public_arrivals as _implementation

sys.modules[__name__] = _implementation
