"""Message-bus abstraction: real Kafka or an in-process queue.

`get_bus()` returns a KafkaBus when a broker is configured and reachable
(env KAFKA_BOOTSTRAP_SERVERS + kafka-python installed), otherwise an
InMemoryBus. Both expose the same tiny API:

    bus.publish(key, value_dict)
    for key, value in bus.consume(timeout=...):
        ...
    bus.flush() / bus.close()
"""

from __future__ import annotations

from src.utils.settings import get_settings

import json
import queue
from typing import Iterator, Optional, Tuple

from src.utils.logging_utils import get_logger

log = get_logger(__name__)

DEFAULT_TOPIC = "port_records"


class InMemoryBus:
    """A drop-in, broker-free bus backed by a thread-safe queue."""

    def __init__(self, topic: str = DEFAULT_TOPIC):
        self.topic = topic
        self._q: "queue.Queue" = queue.Queue()
        self.backend = "in-memory"

    def publish(self, key: str, value: dict) -> None:
        self._q.put((key, value))

    def consume(self, timeout: float = 1.0) -> Iterator[Tuple[str, dict]]:
        while True:
            try:
                yield self._q.get(timeout=timeout)
            except queue.Empty:
                return

    def flush(self) -> None:
        pass

    def close(self) -> None:
        pass


class KafkaBus:
    """Real Kafka bus (lazy producer/consumer creation)."""

    def __init__(self, bootstrap: str, topic: str = DEFAULT_TOPIC,
                 group_id: str = "logistics-demo"):
        from kafka import KafkaProducer  # noqa
        self.topic = topic
        self.bootstrap = bootstrap
        self.group_id = group_id
        self.backend = "kafka"
        self._producer = KafkaProducer(
            bootstrap_servers=bootstrap,
            value_serializer=lambda v: json.dumps(v, default=str).encode(),
            key_serializer=lambda k: str(k).encode(),
        )
        self._consumer = None

    def publish(self, key: str, value: dict) -> None:
        self._producer.send(self.topic, key=key, value=value)

    def consume(self, timeout: float = 2.0) -> Iterator[Tuple[str, dict]]:
        from kafka import KafkaConsumer
        if self._consumer is None:
            self._consumer = KafkaConsumer(
                self.topic,
                bootstrap_servers=self.bootstrap,
                group_id=self.group_id,
                auto_offset_reset="earliest",
                enable_auto_commit=True,
                value_deserializer=lambda v: json.loads(v.decode()),
                key_deserializer=lambda k: k.decode() if k else None,
                consumer_timeout_ms=int(timeout * 1000),
            )
        for msg in self._consumer:
            yield msg.key, msg.value

    def flush(self) -> None:
        self._producer.flush()

    def close(self) -> None:
        try:
            self._producer.close()
            if self._consumer is not None:
                self._consumer.close()
        except Exception:
            pass


def get_bus(topic: str = DEFAULT_TOPIC, force_memory: bool = False):
    """Return a Kafka bus if configured & reachable, else an in-memory bus."""
    bootstrap = get_settings().KAFKA_BOOTSTRAP_SERVERS
    if force_memory or not bootstrap:
        log.info("Streaming bus: in-memory (no KAFKA_BOOTSTRAP_SERVERS set).")
        return InMemoryBus(topic)
    try:
        bus = KafkaBus(bootstrap, topic)
        log.info("Streaming bus: Kafka @ %s", bootstrap)
        return bus
    except Exception as exc:
        log.warning("Kafka unavailable (%s); using in-memory bus.", exc)
        return InMemoryBus(topic)
