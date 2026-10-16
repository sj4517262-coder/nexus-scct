import redis.asyncio as redis

from core.config import settings

_redis = redis.from_url(
    settings.REDIS_URL,
    decode_responses=True,
)

async def check_redis_connection() -> bool:
    try:
        await _redis.ping()
        return True
    except Exception:
        return False

def get_redis():
    return _redis
