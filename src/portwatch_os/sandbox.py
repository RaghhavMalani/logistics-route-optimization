"""Request-scoped resources for the isolated original-screen demo.

No process environment or operational singleton is changed. The adapter binds
this context only after validating a demo session; normal requests see None.
"""
from contextvars import ContextVar
from dataclasses import dataclass, field
from pathlib import Path
from threading import RLock
from typing import Any, Callable


@dataclass
class Sandbox:
    root: Path
    world: dict
    resources: dict = field(default_factory=dict)
    lock: Any = field(default_factory=RLock)
    save_world: Any = None

    def resource(self, name: str, create: Callable):
        with self.lock:
            if name not in self.resources:
                self.resources[name] = create()
            return self.resources[name]


current_sandbox: ContextVar[Sandbox | None] = ContextVar("terminal_sandbox", default=None)
