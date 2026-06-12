import redis
import os
from app.core.config import settings

def get_redis_client():
    redis_url = os.environ.get("REDIS_URL")
    if redis_url:
        return redis.from_url(
            redis_url,
            decode_responses=True,
            socket_connect_timeout=5,
            socket_timeout=5
        )
    else:
        return redis.Redis(
            host=settings.REDIS_HOST,
            port=settings.REDIS_PORT,
            db=settings.REDIS_DB,
            decode_responses=True,
            socket_connect_timeout=5,
            socket_timeout=5
        )

redis_client = get_redis_client()

def get_redis():
    return redis_client

def check_redis_connection() -> bool:
    try:
        redis_client.ping()
        return True
    except Exception:
        return False