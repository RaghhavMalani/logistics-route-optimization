"""Loopback-only backend entry point for panel rehearsal."""

import ipaddress
import os
import sys
from datetime import datetime


def snapshot_at():
    value = os.environ.get("PORTWATCH_PANEL_SNAPSHOT_AT")
    return datetime.fromisoformat(value) if value else None


def pinned_panel_at():
    """Return the panel anchor only in its visitor-owned, frozen replay."""
    from src.portwatch_os.clock import REPLAY, get_clock
    from src.portwatch_os.sandbox import current_sandbox

    at = snapshot_at()
    if at is not None and current_sandbox.get() is not None:
        state = get_clock().state
        if state.mode == REPLAY and state.anchor == at and state.rate == 0:
            return at
    return None


def restrict_network(event, args):
    if event in ("socket.connect", "socket.sendto"):
        endpoint = args[1]
        host = endpoint[0] if isinstance(endpoint, tuple) else None
    elif event in ("socket.getaddrinfo", "socket.gethostbyname", "socket.gethostbyaddr", "socket.getnameinfo"):
        endpoint = args[0]
        host = endpoint[0] if isinstance(endpoint, tuple) else endpoint
        if host is None:
            return
    else:
        return
    if isinstance(host, bytes):
        host = host.decode("ascii")
    if host == "localhost":
        return
    try:
        if host is not None and ipaddress.ip_address(host).is_loopback:
            return
    except ValueError:
        pass
    raise OSError("Panel mode blocks outbound network access")


if __name__ == "__main__":
    import runpy

    if snapshot_at() is None:
        raise SystemExit("Panel mode needs a retained snapshot instant")
    sys.addaudithook(restrict_network)
    sys.argv[0] = "uvicorn"
    runpy.run_module("uvicorn", run_name="__main__")
