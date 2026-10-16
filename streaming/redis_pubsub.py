import json
import logging
from typing import Any, Dict, Optional

import redis.asyncio as aioredis

from core.config import settings

logger_redis = logging.getLogger("nexus.streaming.redis")


class RedisPubSub:
    """Redis pub/sub for real-time event delivery to WebSocket clients."""

    def __init__(self):
        self._redis: Optional[aioredis.Redis] = None

    async def _connect(self):
        if self._redis is None:
            self._redis = aioredis.from_url(
                settings.REDIS_URL,
                encoding="utf-8",
                decode_responses=True,
                max_connections=50,
            )
        return self._redis

    async def publish(self, channel: str, message: Dict) -> int:
        r = await self._connect()
        payload = json.dumps(message, default=str)
        return await r.publish(channel, payload)

    async def subscribe(self, *channels: str):
        r = await self._connect()
        pubsub = r.pubsub()
        await pubsub.subscribe(*channels)
        return pubsub

    async def set_cache(
        self,
        key: str,
        value: Any,
        ttl: int = 3600,
    ) -> bool:
        r = await self._connect()
        return await r.set(
            key,
            json.dumps(value, default=str),
            ex=ttl,
        )

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