"""Keeping a long-running process at the speed the host can give it.

Windows applies power throttling (EcoQoS) to a process it judges to be
background work: after a minute or so of sustained CPU the process is moved
to the efficiency cores and low clocks, and it stays there -- a fresh process
runs five times faster than the one that has been serving for two minutes.
The benchmark met it first (every stage after the first minute came out four
to five times slower than the documented figures, on the same machine, in
the same run), and a long-running API on a Windows host meets it the same
way.

:func:`opt_out_of_power_throttling` tells Windows this process is not
background work, through the documented ``SetProcessInformation``
``ProcessPowerThrottling`` call. On any other platform it is a no-op that
says so. The benchmark calls it before measuring and records the answer; the
API calls it at startup and reports it on the diagnostics page, so a slow
deployment on a laptop is a fact with a name rather than a mystery.

Nothing here changes what is measured or how; it only stops the host from
changing it halfway through.
"""

from __future__ import annotations

import os
import platform
import time
from typing import Any, Dict


def opt_out_of_power_throttling() -> Dict[str, Any]:
    """Ask the host not to power-throttle this process. Returns what happened."""
    if os.name != "nt":
        return {"platform": platform.system(), "applied": False, "reason": "power throttling is a Windows mechanism"}
    try:
        import ctypes
        from ctypes import wintypes

        class ProcessPowerThrottlingState(ctypes.Structure):
            _fields_ = [("Version", wintypes.ULONG), ("ControlMask", wintypes.ULONG), ("StateMask", wintypes.ULONG)]

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.GetCurrentProcess.restype = wintypes.HANDLE
        kernel32.SetProcessInformation.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
        kernel32.SetProcessInformation.restype = wintypes.BOOL
        version = 1
        execution_speed = 0x1                   # PROCESS_POWER_THROTTLING_EXECUTION_SPEED
        process_power_throttling = 4            # PROCESS_INFORMATION_CLASS.ProcessPowerThrottling
        # ControlMask names the policy being set; a StateMask of zero for it
        # means "throttling off", never "let the system decide".
        state = ProcessPowerThrottlingState(version, execution_speed, 0)
        ok = kernel32.SetProcessInformation(kernel32.GetCurrentProcess(), process_power_throttling,
                                            ctypes.byref(state), ctypes.sizeof(state))
        if not ok:
            return {"platform": "Windows", "applied": False,
                    "reason": f"SetProcessInformation failed with error {ctypes.get_last_error()}"}
        return {"platform": "Windows", "applied": True, "reason": "ProcessPowerThrottling: execution speed throttling disabled"}
    except Exception as exc:  # noqa: BLE001 - a host we cannot ask is reported, not fatal
        return {"platform": platform.system(), "applied": False, "reason": f"{type(exc).__name__}: {exc}"}


def reference_loop_ms(n: int = 2_000_000) -> float:
    """A fixed piece of pure-Python work, timed. Two readings of it taken
    minutes apart say whether the host slowed the process in between."""
    started = time.perf_counter()
    total = 0
    for i in range(n):
        total += i * i
    return (time.perf_counter() - started) * 1000.0


__all__ = ["opt_out_of_power_throttling", "reference_loop_ms"]
