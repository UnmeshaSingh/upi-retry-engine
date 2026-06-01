import redis
from app.core.config import settings

# Create a single Redis client instance
# decode_responses=True means Redis returns strings not bytes
redis_client = redis.Redis(
    host=settings.REDIS_HOST,
    port=settings.REDIS_PORT,
    db=settings.REDIS_DB,
    decode_responses=True
)

def get_redis():
    """
    Returns the Redis client.
    Used as a dependency in FastAPI endpoints.
    """
    return redis_client

def check_redis_connection() -> bool:
    """
    Ping Redis to verify connection is alive.
    Returns True if connected, False otherwise.
    """
    try:
        redis_client.ping()
        return True
    except redis.ConnectionError:
        return False