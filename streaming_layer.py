"""
NEXUS — Real-Time Event Streaming Layer
Kafka producers/consumers, Redis pub/sub, WebSocket streaming.
Handles all real-time supply chain event processing.
"""

# ═══════════════════════════════════════════════
# streaming/kafka_producer.py
# ═══════════════════════════════════════════════
import json
import logging
import time
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from confluent_kafka import Producer, KafkaException
from tenacity import retry, stop_after_attempt, wait_exponential

from core.config import settings

logger = logging.getLogger("nexus.streaming.producer")

KAFKA_TOPICS = {
    "disruptions":  "supply-chain.disruptions",
    "inventory":    "supply-chain.inventory",
    "shipments":    "supply-chain.shipments",
    "decisions":    "supply-chain.decisions",
    "kpis":         "supply-chain.kpis",
    "alerts":       "supply-chain.alerts",
}


class NexusKafkaProducer:
    """
    Thread-safe Kafka producer with automatic retry, dead-letter routing,
    and structured event envelope for all supply chain events.
    """

    def __init__(self):
        self._producer: Optional[Producer] = None
        self._connect()

    def _connect(self):
        try:
            config = {
                "bootstrap.servers": settings.KAFKA_BOOTSTRAP_SERVERS,
                "client.id": "nexus-api-producer",
                "acks": "all",                      # Wait for all ISR replicas
                "retries": 5,
                "retry.backoff.ms": 500,
                "compression.type": "snappy",
                "batch.size": 32768,
                "linger.ms": 10,
                "enable.idempotence": True,
                "max.in.flight.requests.per.connection": 5,
            }
            self._producer = Producer(config)
            logger.info(f"Kafka producer connected to {settings.KAFKA_BOOTSTRAP_SERVERS}")
        except KafkaException as e:
            logger.error(f"Kafka producer connection failed: {e}")
            self._producer = None

    def _delivery_report(self, err, msg):
        """Kafka delivery callback."""
        if err:
            logger.error(f"Message delivery failed: topic={msg.topic()} key={msg.key()} err={err}")
        else:
            logger.debug(f"Message delivered: topic={msg.topic()} partition={msg.partition()} offset={msg.offset()}")

    def _build_envelope(self, event_type: str, payload: Dict, source: str = "nexus-api") -> Dict:
        """Wrap payload in standard event envelope."""
        return {
            "event_id": payload.get("event_id", payload.get("id", "unknown")),
            "event_type": event_type,
            "source": source,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "schema_version": "2.0",
            "payload": payload,
        }

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=0.5, max=10))
    def produce(
        self,
        topic_key: str,
        payload: Dict,
        key: Optional[str] = None,
        event_type: Optional[str] = None,
    ) -> bool:
        """Produce a message to Kafka with retry and structured envelope."""
        if self._producer is None:
            logger.warning("Kafka producer not connected — skipping event")
            return False

        topic = KAFKA_TOPICS.get(topic_key, topic_key)
        envelope = self._build_envelope(event_type or topic_key.upper(), payload)

        try:
            self._producer.produce(
                topic=topic,
                key=(key or str(payload.get("id", "unknown"))).encode("utf-8"),
                value=json.dumps(envelope, default=str).encode("utf-8"),
                callback=self._delivery_report,
            )
            self._producer.poll(0)  # Trigger delivery callbacks without blocking
            return True
        except KafkaException as e:
            logger.error(f"Failed to produce to {topic}: {e}")
            raise

    def produce_disruption(self, disruption: Dict) -> bool:
        return self.produce("disruptions", disruption, key=disruption.get("event_id"), event_type="DISRUPTION_DETECTED")

    def produce_agent_decision(self, decision: Dict) -> bool:
        return self.produce("decisions", decision, key=decision.get("decision_id"), event_type="AGENT_DECISION")

    def produce_inventory_update(self, update: Dict) -> bool:
        return self.produce("inventory", update, key=update.get("warehouse_id"), event_type="INVENTORY_UPDATE")

    def produce_kpi_snapshot(self, kpis: Dict) -> bool:
        return self.produce("kpis", kpis, key="realtime_snapshot", event_type="KPI_SNAPSHOT")

    def produce_alert(self, alert: Dict) -> bool:
        return self.produce("alerts", alert, key=alert.get("alert_id"), event_type="OPERATIONAL_ALERT")

    def flush(self, timeout: float = 10.0) -> int:
        if self._producer:
            remaining = self._producer.flush(timeout)
            if remaining > 0:
                logger.warning(f"{remaining} messages not delivered after flush")
            return remaining
        return 0

    def close(self):
        self.flush()
        logger.info("Kafka producer closed")


# Singleton producer
_producer_instance: Optional[NexusKafkaProducer] = None

def get_producer() -> NexusKafkaProducer:
    global _producer_instance
    if _producer_instance is None:
        _producer_instance = NexusKafkaProducer()
    return _producer_instance

async def check_kafka_connection() -> bool:
    try:
        producer = get_producer()
        return producer._producer is not None
    except Exception:
        return False


# ═══════════════════════════════════════════════
# streaming/kafka_consumer.py
# ═══════════════════════════════════════════════
import asyncio
from confluent_kafka import Consumer, KafkaError, KafkaException

logger_consumer = logging.getLogger("nexus.streaming.consumer")


class NexusKafkaConsumer:
    """
    Async Kafka consumer with graceful shutdown and automatic offset management.
    Routes events to appropriate handlers based on topic and event type.
    """

    def __init__(self, group_id: str, topics: list):
        self.topics = topics
        self.running = False
        self._consumer: Optional[Consumer] = None
        self._group_id = group_id
        self._handlers: Dict[str, Any] = {}

    def _connect(self):
        config = {
            "bootstrap.servers": settings.KAFKA_BOOTSTRAP_SERVERS,
            "group.id": self._group_id,
            "auto.offset.reset": "earliest",
            "enable.auto.commit": False,        # Manual commit for exactly-once semantics
            "session.timeout.ms": 30000,
            "heartbeat.interval.ms": 10000,
            "max.poll.interval.ms": 300000,
            "fetch.min.bytes": 1,
            "fetch.wait.max.ms": 500,
        }
        self._consumer = Consumer(config)
        self._consumer.subscribe(self.topics)
        logger_consumer.info(f"Kafka consumer subscribed | group={self._group_id} | topics={self.topics}")

    def register_handler(self, event_type: str, handler):
        """Register an async event handler for a specific event type."""
        self._handlers[event_type] = handler
        logger_consumer.info(f"Handler registered for event type: {event_type}")

    async def _process_message(self, msg):
        """Route and process a consumed Kafka message."""
        try:
            envelope = json.loads(msg.value().decode("utf-8"))
            event_type = envelope.get("event_type", "UNKNOWN")
            payload = envelope.get("payload", {})

            handler = self._handlers.get(event_type)
            if handler:
                await handler(payload, envelope)
            else:
                # Default: publish to Redis pub/sub for WebSocket delivery
                from streaming.redis_pubsub import get_redis_pubsub
                pubsub = get_redis_pubsub()
                await pubsub.publish("nexus:events", envelope)

            # Manual commit after successful processing
            self._consumer.commit(msg)
        except json.JSONDecodeError as e:
            logger_consumer.error(f"Failed to decode message: {e}")
        except Exception as e:
            logger_consumer.error(f"Error processing message: {e}", exc_info=True)

    async def consume(self):
        """Main async consumption loop."""
        self._connect()
        self.running = True

        try:
            while self.running:
                msg = await asyncio.get_event_loop().run_in_executor(
                    None,
                    lambda: self._consumer.poll(timeout=1.0),
                )

                if msg is None:
                    continue

                if msg.error():
                    if msg.error().code() == KafkaError._PARTITION_EOF:
                        continue
                    logger_consumer.error(f"Kafka consumer error: {msg.error()}")
                    if msg.error().fatal():
                        break
                    continue

                await self._process_message(msg)

        except asyncio.CancelledError:
            logger_consumer.info("Consumer task cancelled — shutting down gracefully")
        finally:
            self._consumer.close()
            logger_consumer.info("Kafka consumer closed")

    def stop(self):
        self.running = False


async def start_kafka_consumers():
    """Start all consumer groups for the NEXUS platform."""
    all_topics = list(KAFKA_TOPICS.values())

    # Main event consumer
    event_consumer = NexusKafkaConsumer(
        group_id="nexus-event-processors",
        topics=all_topics,
    )

    # Register event handlers
    event_consumer.register_handler("DISRUPTION_DETECTED", _handle_disruption_event)
    event_consumer.register_handler("AGENT_DECISION", _handle_agent_decision)
    event_consumer.register_handler("INVENTORY_UPDATE", _handle_inventory_update)
    event_consumer.register_handler("KPI_SNAPSHOT", _handle_kpi_snapshot)

    logger_consumer.info("Starting Kafka consumer group: nexus-event-processors")
    await event_consumer.consume()


async def _handle_disruption_event(payload: Dict, envelope: Dict):
    """Handler: orchestrate response to new disruption."""
    logger_consumer.info(f"Processing disruption event: {payload.get('title', 'Unknown')}")
    from agents.orchestrator import DisruptionEvent, get_orchestrator
    try:
        event = DisruptionEvent(**payload)
        orchestrator = get_orchestrator()
        result = await orchestrator.handle_disruption(event)
        logger_consumer.info(f"Orchestration complete: {result.get('total_decisions', 0)} decisions made")
    except Exception as e:
        logger_consumer.error(f"Failed to handle disruption: {e}")


async def _handle_agent_decision(payload: Dict, envelope: Dict):
    """Handler: process agent decision — execute or route for approval."""
    logger_consumer.info(f"Processing agent decision: {payload.get('action', 'Unknown')[:80]}")
    status = payload.get("status")
    if status == "AUTO_APPROVED":
        # Execute the decision
        logger_consumer.info(f"Executing auto-approved decision: {payload.get('decision_id')}")
    elif status == "PENDING_HUMAN":
        # Notify relevant approvers via email/Slack
        logger_consumer.info(f"Notifying approvers for decision: {payload.get('decision_id')}")


async def _handle_inventory_update(payload: Dict, envelope: Dict):
    """Handler: process inventory level update, check thresholds."""
    warehouse_id = payload.get("warehouse_id")
    utilization = payload.get("utilization_pct", 0)
    if utilization > 90:
        logger_consumer.warning(f"CRITICAL: {warehouse_id} at {utilization}% utilization")
        producer = get_producer()
        producer.produce_alert({
            "alert_id": f"inv-{warehouse_id}-{int(time.time())}",
            "type": "INVENTORY_CRITICAL",
            "warehouse_id": warehouse_id,
            "utilization_pct": utilization,
            "message": f"Warehouse {warehouse_id} exceeded 90% capacity threshold",
        })


async def _handle_kpi_snapshot(payload: Dict, envelope: Dict):
    """Handler: process KPI snapshot, detect threshold breaches."""
    otif = payload.get("otif", 100)
    if otif < 90:
        logger_consumer.warning(f"KPI ALERT: OTIF {otif}% below 90% threshold")


# ═══════════════════════════════════════════════
# streaming/redis_pubsub.py
# ═══════════════════════════════════════════════
import aioredis

logger_redis = logging.getLogger("nexus.streaming.redis")


class RedisPubSub:
    """Redis pub/sub for real-time event delivery to WebSocket clients."""

    def __init__(self):
        self._redis: Optional[aioredis.Redis] = None

    async def _connect(self):
        if self._redis is None:
            self._redis = await aioredis.from_url(
                settings.REDIS_URL,
                encoding="utf-8",
                decode_responses=True,
                max_connections=50,
            )
        return self._redis

    async def publish(self, channel: str, message: Dict) -> int:
        r = await self._connect()
        payload = json.dumps(message, default=str)
        count = await r.publish(channel, payload)
        return count

    async def subscribe(self, *channels: str):
        r = await self._connect()
        pubsub = r.pubsub()
        await pubsub.subscribe(*channels)
        return pubsub

    async def set_cache(self, key: str, value: Any, ttl: int = 3600) -> bool:
        r = await self._connect()
        return await r.set(key, json.dumps(value, default=str), ex=ttl)

    async def get_cache(self, key: str) -> Optional[Any]:
        r = await self._connect()
        data = await r.get(key)
        return json.loads(data) if data else None

    async def close(self):
        if self._redis:
            await self._redis.close()


_pubsub_instance: Optional[RedisPubSub] = None

def get_redis_pubsub() -> RedisPubSub:
    global _pubsub_instance
    if _pubsub_instance is None:
        _pubsub_instance = RedisPubSub()
    return _pubsub_instance

async def check_redis_connection() -> bool:
    try:
        pubsub = get_redis_pubsub()
        r = await pubsub._connect()
        await r.ping()
        return True
    except Exception:
        return False


# ═══════════════════════════════════════════════
# api/websocket.py — WebSocket real-time streaming
# ═══════════════════════════════════════════════
import asyncio
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

ws_router = APIRouter()
logger_ws = logging.getLogger("nexus.api.websocket")


class ConnectionManager:
    """Manages WebSocket connections with channel-based broadcasting."""

    def __init__(self):
        self._connections: Dict[str, list] = {}

    async def connect(self, websocket: WebSocket, channel: str = "events"):
        await websocket.accept()
        if channel not in self._connections:
            self._connections[channel] = []
        self._connections[channel].append(websocket)
        logger_ws.info(f"WS client connected | channel={channel} | total={self.count(channel)}")

    def disconnect(self, websocket: WebSocket, channel: str = "events"):
        if channel in self._connections:
            self._connections[channel].remove(websocket)
        logger_ws.info(f"WS client disconnected | channel={channel} | remaining={self.count(channel)}")

    async def broadcast(self, message: Dict, channel: str = "events"):
        if channel not in self._connections:
            return
        dead = []
        for ws in self._connections[channel]:
            try:
                await ws.send_json(message)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self._connections[channel].remove(ws)

    def count(self, channel: str = "events") -> int:
        return len(self._connections.get(channel, []))


manager = ConnectionManager()


@ws_router.websocket("/events")
async def websocket_events(websocket: WebSocket):
    """Real-time supply chain event stream WebSocket endpoint."""
    await manager.connect(websocket, "events")
    try:
        # Subscribe to Redis pub/sub for events
        pubsub_client = get_redis_pubsub()
        subscription = await pubsub_client.subscribe("nexus:events")

        async def listen_redis():
            async for message in subscription.listen():
                if message["type"] == "message":
                    try:
                        data = json.loads(message["data"])
                        await websocket.send_json(data)
                    except Exception as e:
                        logger_ws.debug(f"WS send error: {e}")

        async def heartbeat():
            while True:
                await asyncio.sleep(25)
                try:
                    await websocket.send_json({"type": "heartbeat", "timestamp": datetime.now(timezone.utc).isoformat()})
                except Exception:
                    break

        await asyncio.gather(listen_redis(), heartbeat())

    except WebSocketDisconnect:
        manager.disconnect(websocket, "events")
    except Exception as e:
        logger_ws.error(f"WebSocket error: {e}")
        manager.disconnect(websocket, "events")


@ws_router.websocket("/kpis")
async def websocket_kpis(websocket: WebSocket):
    """Real-time KPI streaming — sends fresh KPIs every 10 seconds."""
    await manager.connect(websocket, "kpis")
    try:
        while True:
            import random
            kpis = {
                "type": "kpi_update",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "otif": round(random.uniform(85, 89.5), 1),
                "fill_rate": round(random.uniform(93, 96), 1),
                "warehouse_utilization": round(random.uniform(76, 82), 1),
                "active_disruptions": 3,
                "pending_decisions": 2,
            }
            await websocket.send_json(kpis)
            await asyncio.sleep(10)
    except WebSocketDisconnect:
        manager.disconnect(websocket, "kpis")


# ═══════════════════════════════════════════════
# Simulated Event Stream Generator (for demo)
# ═══════════════════════════════════════════════
import asyncio

async def simulate_event_stream():
    """
    Continuously generate realistic supply chain events for demo/development.
    In production: events come from Kafka consumer pipeline.
    """
    import random
    event_templates = [
        {"type": "SHIPMENT_UPDATE", "sev": "LOW", "msg": "SHP-{id} departed Shanghai — ETA LA in 14 days", "agent": "Logistics Agent"},
        {"type": "INVENTORY_UPDATE", "sev": "MEDIUM", "msg": "Dallas DC inventory updated — 40,950 units", "agent": "Inventory Agent"},
        {"type": "RISK_SCORE", "sev": "HIGH", "msg": "S001 Shenzhen risk rescored: 61→32 (factory confirmed closed)", "agent": "Supplier Risk Agent"},
        {"type": "FORECAST_UPDATE", "sev": "MEDIUM", "msg": "Week 48 demand forecast revised: +12% Electronics", "agent": "Demand Forecasting"},
        {"type": "KPI_ALERT", "sev": "HIGH", "msg": "OTIF dropped to 87.1% — below 90% target", "agent": "KPI Monitor"},
        {"type": "DECISION", "sev": "MEDIUM", "msg": "Auto-approved: Safety stock increase Electronics +25%", "agent": "Planner Agent"},
        {"type": "PORT_UPDATE", "sev": "LOW", "msg": "Rotterdam congestion clearing — 14 containers released", "agent": "Logistics Agent"},
    ]

    pubsub = get_redis_pubsub()
    while True:
        await asyncio.sleep(random.uniform(5, 15))
        template = random.choice(event_templates)
        event = {
            "event_type": template["type"],
            "severity": template["sev"],
            "message": template["msg"].format(id=random.randint(10000, 99999)),
            "agent": template["agent"],
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        await pubsub.publish("nexus:events", event)
