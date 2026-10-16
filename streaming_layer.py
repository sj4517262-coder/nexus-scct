"""NEXUS real-time streaming layer.
Kafka producer/consumer + Redis pub/sub + FastAPI WebSockets.
"""

from __future__ import annotations

import asyncio
import json
import logging
import random
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Dict, List, Optional

from confluent_kafka import Consumer, KafkaError, KafkaException, Producer
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from core.config import settings
import redis.asyncio as aioredis

logger = logging.getLogger("nexus.streaming.producer")
logger_consumer = logging.getLogger("nexus.streaming.consumer")
logger_redis = logging.getLogger("nexus.streaming.redis")
logger_ws = logging.getLogger("nexus.api.websocket")

KAFKA_TOPICS = {
    "disruptions": "supply-chain.disruptions",
    "inventory": "supply-chain.inventory",
    "shipments": "supply-chain.shipments",
    "decisions": "supply-chain.decisions",
    "kpis": "supply-chain.kpis",
    "alerts": "supply-chain.alerts",
}
REDIS_EVENT_CHANNEL = "nexus:events"

DISRUPTION_TYPES = {
    "DISRUPTION_DETECTED", "SUPPLIER_DELAY", "TRANSPORT_DELAY",
    "PORT_CONGESTION", "FACTORY_CLOSURE", "SUPPLY_DISRUPTION", "DISRUPTION",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def upper(value: Any, default: str = "UNKNOWN") -> str:
    value = default if value is None else str(value).strip()
    return value.upper() if value else default


def ui_type(event_type: str) -> str:
    return {
        "DISRUPTION_DETECTED": "DISRUPTION",
        "SUPPLIER_DELAY": "DISRUPTION",
        "TRANSPORT_DELAY": "DISRUPTION",
        "PORT_CONGESTION": "DISRUPTION",
        "FACTORY_CLOSURE": "DISRUPTION",
        "SUPPLY_DISRUPTION": "DISRUPTION",
        "DISRUPTION": "DISRUPTION",
        "AGENT_DECISION": "DECISION",
        "DECISION": "DECISION",
        "INVENTORY_UPDATE": "OPTIMIZATION",
        "OPTIMIZATION": "OPTIMIZATION",
        "KPI_SNAPSHOT": "UPDATE",
        "OPERATIONAL_ALERT": "ALERT",
        "KPI_ALERT": "ALERT",
        "RISK_SCORE": "RISK",
        "SUPPLIER_RISK": "RISK",
        "FORECAST_UPDATE": "FORECAST",
        "FORECAST": "FORECAST",
        "ESCALATION": "ESCALATION",
        "SHIPMENT_UPDATE": "UPDATE",
        "PORT_UPDATE": "UPDATE",
    }.get(upper(event_type), upper(event_type))


def build_event(
    event_type: str,
    payload: Dict[str, Any],
    envelope: Optional[Dict[str, Any]] = None,
    *,
    message: Optional[str] = None,
    agent: Optional[str] = None,
    severity: Optional[str] = None,
) -> Dict[str, Any]:
    envelope = envelope or {}
    event_type = upper(event_type)
    msg = (
        message or payload.get("message") or payload.get("title")
        or payload.get("action") or payload.get("description")
        or f"{event_type.replace('_', ' ').title()} received"
    )
    return {
        "type": ui_type(event_type),
        "event_type": event_type,
        "severity": upper(
            severity or payload.get("severity") or payload.get("sev"), "LOW"
        ),
        "message": str(msg),
        "agent": str(
            agent or payload.get("agent") or payload.get("agent_name")
            or envelope.get("source") or "NEXUS Event Processor"
        ),
        "timestamp": (
            envelope.get("timestamp")
            or payload.get("timestamp")
            or utc_now()
        ),
        "event_id": (
            envelope.get("event_id")
            or payload.get("event_id")
            or payload.get("id")
            or ""
        ),
        "payload": payload,
    }


class NexusKafkaProducer:
    def __init__(self) -> None:
        self._producer: Optional[Producer] = None
        self._connect()

    def _connect(self) -> bool:
        try:
            self._producer = Producer({
                "bootstrap.servers": settings.KAFKA_BOOTSTRAP_SERVERS,
                "client.id": "nexus-api-producer",
                "acks": "all",
                "retries": 5,
                "retry.backoff.ms": 500,
                "compression.type": "snappy",
                "batch.size": 32768,
                "linger.ms": 10,
                "enable.idempotence": True,
                "max.in.flight.requests.per.connection": 5,
                "delivery.timeout.ms": 120000,
            })
            logger.info(
                "Kafka producer connected | bootstrap=%s",
                settings.KAFKA_BOOTSTRAP_SERVERS,
            )
            return True
        except Exception:
            logger.exception("Kafka producer connection failed")
            self._producer = None
            return False

    def _delivery_report(self, err: Any, msg: Any) -> None:
        if err:
            logger.error(
                "Kafka delivery failed | topic=%s | key=%s | error=%s",
                msg.topic(), msg.key(), err,
            )
        else:
            logger.debug(
                "Kafka delivered | topic=%s | partition=%s | offset=%s",
                msg.topic(), msg.partition(), msg.offset(),
            )

    def _envelope(
        self, event_type: str, payload: Dict[str, Any], source: str = "nexus-api"
    ) -> Dict[str, Any]:
        return {
            "event_id": payload.get(
                "event_id", payload.get("id", f"evt-{int(time.time()*1000)}")
            ),
            "event_type": upper(event_type),
            "source": source,
            "timestamp": utc_now(),
            "schema_version": "2.0",
            "payload": payload,
        }

    def _ensure_connected(self) -> Producer:
        if self._producer is None and not self._connect():
            raise KafkaException("Kafka producer is unavailable")
        return self._producer

    @retry(
        retry=retry_if_exception_type((KafkaException, BufferError)),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=0.5, max=5),
        reraise=True,
    )
    def produce(
        self,
        topic_key: str,
        payload: Dict[str, Any],
        key: Optional[str] = None,
        event_type: Optional[str] = None,
    ) -> bool:
        if not isinstance(payload, dict):
            raise TypeError("Kafka payload must be a dictionary")

        producer = self._ensure_connected()
        topic = KAFKA_TOPICS.get(topic_key, topic_key)
        if not topic:
            raise ValueError("Kafka topic cannot be empty")

        message_key = key or str(
            payload.get("id")
            or payload.get("event_id")
            or payload.get("decision_id")
            or "unknown"
        )

        try:
            producer.produce(
                topic=topic,
                key=message_key.encode("utf-8"),
                value=json.dumps(
                    self._envelope(event_type or topic_key.upper(), payload),
                    default=str,
                ).encode("utf-8"),
                callback=self._delivery_report,
            )
            producer.poll(0)
            return True
        except BufferError:
            producer.poll(1)
            raise
        except Exception:
            logger.exception("Kafka produce failed | topic=%s", topic)
            raise

    def produce_disruption(self, payload: Dict[str, Any]) -> bool:
        return self.produce(
            "disruptions", payload, payload.get("event_id"), "DISRUPTION_DETECTED"
        )

    def produce_agent_decision(self, payload: Dict[str, Any]) -> bool:
        return self.produce(
            "decisions", payload, payload.get("decision_id"), "AGENT_DECISION"
        )

    def produce_inventory_update(self, payload: Dict[str, Any]) -> bool:
        return self.produce(
            "inventory", payload, payload.get("warehouse_id"), "INVENTORY_UPDATE"
        )

    def produce_shipment_update(self, payload: Dict[str, Any]) -> bool:
        return self.produce(
            "shipments",
            payload,
            payload.get("tracking_number") or payload.get("id"),
            "SHIPMENT_UPDATE",
        )

    def produce_kpi_snapshot(self, payload: Dict[str, Any]) -> bool:
        return self.produce(
            "kpis", payload, "realtime_snapshot", "KPI_SNAPSHOT"
        )

    def produce_alert(self, payload: Dict[str, Any]) -> bool:
        return self.produce(
            "alerts", payload, payload.get("alert_id"), "OPERATIONAL_ALERT"
        )

    def flush(self, timeout: float = 10.0) -> int:
        if self._producer is None:
            return 0
        try:
            remaining = self._producer.flush(timeout)
            if remaining:
                logger.warning(
                    "%s Kafka messages not delivered after flush", remaining
                )
            return remaining
        except Exception:
            logger.exception("Kafka producer flush failed")
            return 0

    def close(self) -> None:
        self.flush()
        self._producer = None
        logger.info("Kafka producer closed")


_producer_instance: Optional[NexusKafkaProducer] = None


def get_producer() -> NexusKafkaProducer:
    global _producer_instance
    if _producer_instance is None:
        _producer_instance = NexusKafkaProducer()
    return _producer_instance


async def check_kafka_connection() -> bool:
    try:
        producer = get_producer()
        if producer._producer is None:
            return False
        await asyncio.to_thread(producer._producer.list_topics, timeout=2.0)
        return True
    except Exception:
        logger.exception("Kafka connectivity check failed")
        return False


class RedisPubSub:
    def __init__(self) -> None:
        self._redis: Optional[aioredis.Redis] = None
        self._lock = asyncio.Lock()

    async def _connect(self) -> aioredis.Redis:
        if self._redis is not None:
            try:
                await self._redis.ping()
                return self._redis
            except Exception:
                try:
                    await self._redis.close()
                except Exception:
                    pass
                self._redis = None

        async with self._lock:
            if self._redis is None:
                self._redis = aioredis.from_url(
                    settings.REDIS_URL,
                    encoding="utf-8",
                    decode_responses=True,
                    max_connections=50,
                )
                await self._redis.ping()
        return self._redis

    async def publish(self, channel: str, message: Dict[str, Any]) -> int:
        redis_client = await self._connect()
        return int(await redis_client.publish(
            channel, json.dumps(message, default=str)
        ))

    async def subscribe(self, *channels: str):
        if not channels:
            raise ValueError("At least one Redis channel is required")
        redis_client = await self._connect()
        pubsub = redis_client.pubsub()
        await pubsub.subscribe(*channels)
        return pubsub

    async def set_cache(self, key: str, value: Any, ttl: int = 3600) -> bool:
        redis_client = await self._connect()
        return bool(await redis_client.set(
            key, json.dumps(value, default=str), ex=ttl
        ))

    async def get_cache(self, key: str) -> Optional[Any]:
        redis_client = await self._connect()
        value = await redis_client.get(key)
        return json.loads(value) if value else None

    async def close(self) -> None:
        if self._redis is not None:
            try:
                await self._redis.close()
            finally:
                self._redis = None


_pubsub_instance: Optional[RedisPubSub] = None


def get_redis_pubsub() -> RedisPubSub:
    global _pubsub_instance
    if _pubsub_instance is None:
        _pubsub_instance = RedisPubSub()
    return _pubsub_instance


async def check_redis_connection() -> bool:
    try:
        await get_redis_pubsub()._connect()
        return True
    except Exception:
        logger_redis.exception("Redis connectivity check failed")
        return False


EventHandler = Callable[
    [Dict[str, Any], Dict[str, Any]],
    Awaitable[Optional[Dict[str, Any]]],
]


class NexusKafkaConsumer:
    """
    confluent-kafka is synchronous, so all Consumer operations are serialized
    on one dedicated worker thread. The FastAPI event loop never blocks.
    """

    def __init__(self, group_id: str, topics: List[str]) -> None:
        self.topics = list(dict.fromkeys(topics))
        self.running = False
        self._consumer: Optional[Consumer] = None
        self._group_id = group_id
        self._handlers: Dict[str, EventHandler] = {}
        self._executor = ThreadPoolExecutor(
            max_workers=1,
            thread_name_prefix=f"nexus-kafka-{group_id}",
        )

    def _connect(self) -> None:
        if self._consumer is not None:
            return

        config = {
            "bootstrap.servers": settings.KAFKA_BOOTSTRAP_SERVERS,
            "group.id": self._group_id,
            "client.id": f"nexus-consumer-{self._group_id}",
            "auto.offset.reset": settings.KAFKA_AUTO_OFFSET_RESET,
            "enable.auto.commit": False,
            "enable.partition.eof": False,
            "session.timeout.ms": 30000,
            "heartbeat.interval.ms": 10000,
            "max.poll.interval.ms": 300000,
            "fetch.min.bytes": 1,
            "fetch.wait.max.ms": 500,
        }

        try:
            self._consumer = Consumer(config)
            self._consumer.subscribe(self.topics)
            logger_consumer.info(
                "Kafka consumer subscribed | group=%s | topics=%s",
                self._group_id, self.topics,
            )
        except Exception:
            try:
                if self._consumer:
                    self._consumer.close()
            except Exception:
                pass
            self._consumer = None
            logger_consumer.exception("Kafka consumer connection failed")
            raise

    def register_handler(self, event_type: str, handler: EventHandler) -> None:
        key = upper(event_type)
        self._handlers[key] = handler
        logger_consumer.info("Handler registered for event type: %s", key)

    def _poll(self, timeout: float):
        return self._consumer.poll(timeout=timeout) if self._consumer else None

    def _commit(self, msg: Any) -> None:
        if self._consumer:
            self._consumer.commit(message=msg, asynchronous=False)

    def _close(self) -> None:
        if self._consumer:
            try:
                self._consumer.close()
            finally:
                self._consumer = None

    async def _commit_async(self, msg: Any) -> None:
        await asyncio.get_running_loop().run_in_executor(
            self._executor, self._commit, msg
        )

    async def _publish_error(
        self, envelope: Dict[str, Any], error: Exception
    ) -> None:
        event = {
            "type": "ALERT",
            "event_type": "STREAMING_PROCESSING_ERROR",
            "severity": "HIGH",
            "message": f"Kafka event processing failed: {str(error)[:250]}",
            "agent": "NEXUS Event Processor",
            "timestamp": utc_now(),
            "event_id": envelope.get("event_id", ""),
            "original_event_type": envelope.get("event_type", "UNKNOWN"),
        }

        try:
            await get_redis_pubsub().publish(REDIS_EVENT_CHANNEL, event)
        except Exception:
            logger_consumer.exception("Failed to publish error to Redis")

    async def _process_message(self, msg: Any) -> bool:
        envelope: Dict[str, Any] = {}

        try:
            raw = msg.value()
            if raw is None:
                raise ValueError("Kafka message has no value")
            if isinstance(raw, bytes):
                raw = raw.decode("utf-8")

            envelope = json.loads(raw)
            if not isinstance(envelope, dict):
                raise ValueError("Kafka envelope must be a JSON object")

            event_type = upper(envelope.get("event_type"))
            payload = envelope.get("payload", {})
            logger_consumer.info(
               "KAFKA PAYLOAD DEBUG | event_type=%s | severity=%r | keys=%s",
                event_type,
                payload.get("severity"),
                list(payload.keys()),
)
            if not isinstance(payload, dict):
                payload = {"value": payload}

            logger_consumer.info(
                "Kafka event received | type=%s | topic=%s | partition=%s | offset=%s",
                event_type, msg.topic(), msg.partition(), msg.offset(),
            )

            handler_key = (
                "DISRUPTION_DETECTED"
                if event_type in DISRUPTION_TYPES else event_type
            )
            handler = self._handlers.get(handler_key)

            realtime_event = None
            if handler:
                logger_consumer.info(
                    "Dispatching event | type=%s | handler=%s",
                    event_type, getattr(handler, "__name__", repr(handler)),
                )
                realtime_event = await handler(payload, envelope)

            if realtime_event is None:
                realtime_event = build_event(event_type, payload, envelope)

            await get_redis_pubsub().publish(
                REDIS_EVENT_CHANNEL, realtime_event
            )
            await self._commit_async(msg)
            return True

        except json.JSONDecodeError as exc:
            logger_consumer.error(
                "Invalid JSON | topic=%s | offset=%s | error=%s",
                msg.topic(), msg.offset(), exc,
            )
            try:
                await self._commit_async(msg)
            except Exception:
                logger_consumer.exception("Could not commit malformed message")
                return False
            return True

        except Exception as exc:
            logger_consumer.exception(
                "Error processing Kafka message | topic=%s | offset=%s",
                msg.topic(), msg.offset(),
            )
            await self._publish_error(envelope, exc)

            try:
                await self._commit_async(msg)
                logger_consumer.warning(
                    "Failed message committed after error handling | offset=%s",
                    msg.offset(),
                )
                return True
            except Exception:
                logger_consumer.exception(
                    "Could not commit failed Kafka message"
                )
                return False

    async def consume(self) -> None:
        self.running = True
        logger_consumer.info(
            "Kafka consumer loop starting | group=%s", self._group_id
        )

        try:
            loop = asyncio.get_running_loop()

            # Consumer creation/subscription happens on the same dedicated
            # thread used for poll/commit/close.
            await loop.run_in_executor(self._executor, self._connect)

            while self.running:
                msg = await loop.run_in_executor(
                    self._executor, self._poll, 1.0
                )

                if msg is None:
                    continue

                if msg.error():
                    error = msg.error()
                    if error.code() == KafkaError._PARTITION_EOF:
                        continue

                    logger_consumer.error(
                        "Kafka consumer error | group=%s | error=%s",
                        self._group_id, error,
                    )
                    if error.fatal():
                        logger_consumer.critical(
                            "Fatal Kafka consumer error; stopping"
                        )
                        break
                    continue

                await self._process_message(msg)

        except asyncio.CancelledError:
            logger_consumer.info(
                "Kafka consumer cancelled | group=%s", self._group_id
            )
            raise
        except KafkaException:
            logger_consumer.exception(
                "Kafka exception | group=%s", self._group_id
            )
        except Exception:
            logger_consumer.exception(
                "Unexpected consumer exception | group=%s", self._group_id
            )
        finally:
            self.running = False
            try:
                await asyncio.get_running_loop().run_in_executor(
                    self._executor, self._close
                )
            except Exception:
                logger_consumer.exception("Kafka consumer close failed")

            self._executor.shutdown(wait=False, cancel_futures=True)
            logger_consumer.info(
                "Kafka consumer closed | group=%s", self._group_id
            )

    def stop(self) -> None:
        self.running = False


async def _handle_disruption_event(
    payload: Dict[str, Any], envelope: Dict[str, Any]
) -> Dict[str, Any]:
    title = payload.get("title") or payload.get(
        "description", "Supply chain disruption detected"
    )

    # The current checkout exposes orchestrator.py at the repository root.
    # Orchestration failure never blocks real-time event delivery.
    try:
        from orchestrator import DisruptionEvent, get_orchestrator

        event = DisruptionEvent(
            event_id=payload.get(
                "event_id", envelope.get("event_id", "")
            ),
            event_type=upper(
                payload.get(
                    "event_type",
                    envelope.get("event_type", "DISRUPTION"),
                )
            ),
            severity=upper(payload.get("severity", "LOW"), "LOW"),
            title=str(title),
            description=str(payload.get("description", title)),
            affected_entities=payload.get("affected_entities", []) or [],
            estimated_impact_usd=payload.get("estimated_impact_usd"),
            timestamp=payload.get(
                "timestamp", envelope.get("timestamp", utc_now())
            ),
            metadata=payload.get("metadata", {}) or {},
        )

        result = await get_orchestrator().handle_disruption(event)
        logger_consumer.info(
            "Disruption orchestration finished | event_id=%s | status=%s | decisions=%s",
            event.event_id,
            result.get("status"),
            result.get("total_decisions", 0),
        )
    except Exception as exc:
        logger_consumer.warning(
            "Disruption orchestration unavailable/failed; event will still stream: %s",
            exc,
        )

    return build_event(
        "DISRUPTION",
        payload,
        envelope,
        message=str(title),
        agent="Disruption Orchestrator",
        severity=payload.get("severity", "LOW"),
    )


async def _handle_agent_decision(
    payload: Dict[str, Any], envelope: Dict[str, Any]
) -> Dict[str, Any]:
    status = upper(payload.get("status"), "PROPOSED")

    if status == "AUTO_APPROVED":
        logger_consumer.info(
            "Executing auto-approved decision | id=%s",
            payload.get("decision_id"),
        )
    elif status in {"PENDING_HUMAN", "HUMAN_REQUIRED"}:
        logger_consumer.info(
            "Decision requires human approval | id=%s",
            payload.get("decision_id"),
        )

    return build_event(
        "AGENT_DECISION",
        payload,
        envelope,
        message=payload.get("action", "Agent decision"),
        agent=payload.get("agent")
        or payload.get("agent_type")
        or "Planner Agent",
        severity=(
            "HIGH"
            if status in {"PENDING_HUMAN", "HUMAN_REQUIRED"}
            else "MEDIUM"
        ),
    )


async def _handle_inventory_update(
    payload: Dict[str, Any], envelope: Dict[str, Any]
) -> Dict[str, Any]:
    warehouse = payload.get("warehouse_id", "UNKNOWN")
    try:
        utilization = float(payload.get("utilization_pct", 0) or 0)
    except (TypeError, ValueError):
        utilization = 0.0

    severity = (
        "CRITICAL" if utilization > 90
        else "HIGH" if utilization > 85
        else "MEDIUM"
    )

    if utilization > 90:
        alert = {
            "alert_id": f"inv-{warehouse}-{int(time.time())}",
            "type": "INVENTORY_CRITICAL",
            "warehouse_id": warehouse,
            "utilization_pct": utilization,
            "message": (
                f"Warehouse {warehouse} exceeded 90% capacity threshold"
            ),
        }
        try:
            get_producer().produce_alert(alert)
        except Exception:
            logger_consumer.exception("Failed to publish inventory alert")

    return build_event(
        "INVENTORY_UPDATE",
        payload,
        envelope,
        message=payload.get(
            "message",
            f"Warehouse {warehouse} utilization updated to {utilization:.1f}%",
        ),
        agent="Inventory Agent",
        severity=severity,
    )


async def _handle_kpi_snapshot(
    payload: Dict[str, Any], envelope: Dict[str, Any]
) -> Dict[str, Any]:
    try:
        otif = float(payload.get("otif", 100) or 100)
    except (TypeError, ValueError):
        otif = 100.0

    if otif < 90:
        logger_consumer.warning("KPI ALERT | OTIF=%s%%", otif)

    return build_event(
        "KPI_SNAPSHOT",
        payload,
        envelope,
        message=f"OTIF updated to {otif:.1f}%",
        agent="KPI Monitor Agent",
        severity="HIGH" if otif < 90 else "LOW",
    )


_consumer_instance: Optional[NexusKafkaConsumer] = None


async def start_kafka_consumers() -> None:
    global _consumer_instance

    if _consumer_instance and _consumer_instance.running:
        logger_consumer.info("Kafka consumer already running")
        return

    consumer = NexusKafkaConsumer(
        group_id="nexus-event-processors",
        topics=list(KAFKA_TOPICS.values()),
    )

    consumer.register_handler(
        "DISRUPTION_DETECTED", _handle_disruption_event
    )
    consumer.register_handler(
        "AGENT_DECISION", _handle_agent_decision
    )
    consumer.register_handler(
        "INVENTORY_UPDATE", _handle_inventory_update
    )
    consumer.register_handler(
        "KPI_SNAPSHOT", _handle_kpi_snapshot
    )

    _consumer_instance = consumer
    logger_consumer.info(
        "Starting Kafka consumer group: nexus-event-processors"
    )
    await consumer.consume()


def stop_kafka_consumers() -> None:
    if _consumer_instance:
        _consumer_instance.stop()


ws_router = APIRouter()


class ConnectionManager:
    def __init__(self) -> None:
        self._connections: Dict[str, List[WebSocket]] = {}
        self._lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket, channel: str) -> None:
        await websocket.accept()
        async with self._lock:
            self._connections.setdefault(channel, []).append(websocket)
        logger_ws.info(
            "WS client connected | channel=%s | total=%s",
            channel, self.count(channel),
        )

    async def disconnect(
        self, websocket: WebSocket, channel: str
    ) -> None:
        async with self._lock:
            connections = self._connections.get(channel, [])
            if websocket in connections:
                connections.remove(websocket)
            if not connections:
                self._connections.pop(channel, None)
        logger_ws.info(
            "WS client disconnected | channel=%s | remaining=%s",
            channel, self.count(channel),
        )

    async def broadcast(
        self, message: Dict[str, Any], channel: str = "events"
    ) -> None:
        async with self._lock:
            clients = list(self._connections.get(channel, []))

        dead = []
        for websocket in clients:
            try:
                await websocket.send_json(message)
            except Exception:
                dead.append(websocket)

        for websocket in dead:
            await self.disconnect(websocket, channel)

    def count(self, channel: str) -> int:
        return len(self._connections.get(channel, []))


manager = ConnectionManager()


@ws_router.websocket("/events")
async def websocket_events(websocket: WebSocket) -> None:
    await manager.connect(websocket, "events")
    subscription = None
    listener_task: Optional[asyncio.Task] = None
    receiver_task: Optional[asyncio.Task] = None

    try:
        subscription = await get_redis_pubsub().subscribe(
            REDIS_EVENT_CHANNEL
        )

        async def listen_redis() -> None:
            async for message in subscription.listen():
                if message.get("type") != "message":
                    continue

                raw = message.get("data")
                data = json.loads(raw)

                if isinstance(data, dict):
                    await websocket.send_json(data)

        async def listen_client() -> None:
            # Browser WebSocket clients normally send nothing. This task
            # exists only so a clean browser disconnect is detected even
            # when no Redis events are being published.
            while True:
                message = await websocket.receive()
                if message.get("type") == "websocket.disconnect":
                    raise WebSocketDisconnect()

        listener_task = asyncio.create_task(listen_redis())
        receiver_task = asyncio.create_task(listen_client())

        done, pending = await asyncio.wait(
            {listener_task, receiver_task},
            return_when=asyncio.FIRST_COMPLETED,
        )

        for task in done:
            task.result()

        for task in pending:
            task.cancel()

    except WebSocketDisconnect:
        logger_ws.info("Event WebSocket disconnected normally")
    except asyncio.CancelledError:
        raise
    except Exception:
        logger_ws.exception("Event WebSocket error")
    finally:
        for task in (listener_task, receiver_task):
            if task and not task.done():
                task.cancel()
                try:
                    await task
                except BaseException:
                    pass

        if subscription is not None:
            try:
                await subscription.unsubscribe(REDIS_EVENT_CHANNEL)
            except Exception:
                pass
            try:
                await subscription.close()
            except Exception:
                pass

        await manager.disconnect(websocket, "events")


async def get_live_kpis() -> Dict[str, Any]:
    return {
        "type": "kpi_update",
        "event_type": "KPI_SNAPSHOT",
        "timestamp": utc_now(),
        "otif": round(random.uniform(85, 89.5), 1),
        "fill_rate": round(random.uniform(93, 96), 1),
        "inventory_turnover": round(random.uniform(7.1, 7.8), 1),
        "warehouse_utilization": round(random.uniform(76, 82), 1),
        "transport_cost_per_unit": round(random.uniform(2.3, 2.8), 2),
        "stockout_probability": round(random.uniform(3.2, 5.1), 1),
        "supplier_reliability": round(random.uniform(87, 92), 1),
        "delay_risk": round(random.uniform(16, 22), 1),
        "ai_decisions_today": random.randint(120, 210),
        "ai_auto_approve_rate": round(random.uniform(91, 96), 1),
        "active_disruptions": 3,
        "pending_decisions": 2,
    }


@ws_router.websocket("/kpis")
async def websocket_kpis(websocket: WebSocket) -> None:
    await manager.connect(websocket, "kpis")
    logger_ws.info("KPI WebSocket connected")

    try:
        while True:
            try:
                await websocket.send_json(await get_live_kpis())
            except WebSocketDisconnect:
                logger_ws.info("KPI WebSocket disconnected during send")
                break

            logger_ws.info("KPI update sent")
            await asyncio.sleep(10)

    except WebSocketDisconnect:
        logger_ws.info("KPI WebSocket disconnected normally")
    except asyncio.CancelledError:
        raise
    except Exception:
        logger_ws.exception("KPI WebSocket error")
    finally:
        await manager.disconnect(websocket, "kpis")
        logger_ws.info("KPI WebSocket connection closed")


async def simulate_event_stream() -> None:
    """Explicit development/demo generator; never starts automatically."""
    templates = [
        (
            "SHIPMENT_UPDATE", "LOW",
            "SHP-{id} departed Shanghai — ETA LA in 14 days",
            "Logistics Agent",
        ),
        (
            "INVENTORY_UPDATE", "MEDIUM",
            "Dallas DC inventory updated — 40,950 units",
            "Inventory Agent",
        ),
        (
            "RISK_SCORE", "HIGH",
            "S001 Shenzhen risk rescored: 61→32 (factory confirmed closed)",
            "Supplier Risk Agent",
        ),
        (
            "FORECAST_UPDATE", "MEDIUM",
            "Week 48 demand forecast revised: +12% Electronics",
            "Demand Forecasting",
        ),
        (
            "KPI_ALERT", "HIGH",
            "OTIF dropped to 87.1% — below 90% target",
            "KPI Monitor",
        ),
        (
            "AGENT_DECISION", "MEDIUM",
            "Auto-approved: Safety stock increase Electronics +25%",
            "Planner Agent",
        ),
        (
            "PORT_UPDATE", "LOW",
            "Rotterdam congestion clearing — 14 containers released",
            "Logistics Agent",
        ),
    ]

    pubsub = get_redis_pubsub()

    while True:
        await asyncio.sleep(random.uniform(5, 15))
        event_type, severity, message, agent = random.choice(templates)

        event = {
            "type": ui_type(event_type),
            "event_type": event_type,
            "severity": severity,
            "message": message.format(id=random.randint(10000, 99999)),
            "agent": agent,
            "timestamp": utc_now(),
            "event_id": f"demo-{int(time.time()*1000)}",
        }

        await pubsub.publish(REDIS_EVENT_CHANNEL, event)


__all__ = [
    "KAFKA_TOPICS",
    "NexusKafkaProducer",
    "NexusKafkaConsumer",
    "get_producer",
    "check_kafka_connection",
    "RedisPubSub",
    "get_redis_pubsub",
    "check_redis_connection",
    "ConnectionManager",
    "manager",
    "ws_router",
    "start_kafka_consumers",
    "stop_kafka_consumers",
    "simulate_event_stream",
]
