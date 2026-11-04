"""Wake handoff subscribers after a committed write without sharing payloads."""

import asyncio
from collections import defaultdict
from contextlib import contextmanager

_subscribers = defaultdict(set)


@contextmanager
def subscribe(namespace):
    queue = asyncio.Queue(maxsize=1)
    subscribers = _subscribers[namespace]
    subscribers.add(queue)
    try:
        yield queue
    finally:
        subscribers.discard(queue)
        if not subscribers:
            _subscribers.pop(namespace, None)


def publish(namespace):
    for queue in _subscribers.get(namespace, ()):
        if not queue.full():
            queue.put_nowait(None)
