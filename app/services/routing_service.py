import time
import logging
from typing import Optional
from app.core.redis_client import get_redis

log = logging.getLogger(__name__)

# ── Gateway registry ──────────────────────────────────────────────────────────

# All available payment gateways with priority (lower = preferred)
GATEWAY_REGISTRY = {
    "HDFC":  {"priority": 1, "name": "HDFC Bank PSP",  "upi_handle": "@hdfcbank"},
    "ICICI": {"priority": 2, "name": "ICICI Bank PSP", "upi_handle": "@icici"},
    "SBI":   {"priority": 3, "name": "SBI PSP",        "upi_handle": "@sbi"},
    "AXIS":  {"priority": 4, "name": "Axis Bank PSP",  "upi_handle": "@axisbank"},
    "KOTAK": {"priority": 5, "name": "Kotak PSP",      "upi_handle": "@kotak"},
}

# How many failures before we switch gateway
FAILURE_THRESHOLD = 3

# Time window for tracking success rates (5 minutes)
WINDOW_SECONDS = 300

# Redis key patterns
GATEWAY_ATTEMPTS_KEY = "gateway:attempts:{bank}:{window}"
GATEWAY_FAILURES_KEY = "gateway:failures:{bank}:{window}"
GATEWAY_BLOCKED_KEY  = "gateway:blocked:{bank}"


def _get_time_window() -> int:
    """
    Returns current 5-minute window as integer.
    All events in the same 5-min window share the same key.
    """
    return int(time.time() // WINDOW_SECONDS)


def record_attempt(bank: str):
    """Record a payment attempt through a gateway."""
    redis = get_redis()
    window = _get_time_window()
    key = GATEWAY_ATTEMPTS_KEY.format(bank=bank, window=window)
    redis.incr(key)
    redis.expire(key, WINDOW_SECONDS * 2)
    log.info(f"Recorded attempt: {bank} (window: {window})")


def record_failure(bank: str):
    """
    Record a payment failure through a gateway.
    If failures exceed threshold, block the gateway.
    """
    redis = get_redis()
    window = _get_time_window()

    # Increment failure count
    failure_key = GATEWAY_FAILURES_KEY.format(bank=bank, window=window)
    failure_count = redis.incr(failure_key)
    redis.expire(failure_key, WINDOW_SECONDS * 2)

    log.info(f"Recorded failure: {bank} — failures this window: {failure_count}")

    # Block gateway if threshold exceeded
    if failure_count >= FAILURE_THRESHOLD:
        block_key = GATEWAY_BLOCKED_KEY.format(bank=bank)
        redis.set(block_key, "1", ex=WINDOW_SECONDS)
        log.warning(f"Gateway BLOCKED: {bank} — {failure_count} failures in 5 min")


def record_success(bank: str):
    """Record a successful payment — clears any block on the gateway."""
    redis = get_redis()
    block_key = GATEWAY_BLOCKED_KEY.format(bank=bank)
    redis.delete(block_key)
    log.info(f"Recorded success: {bank} — block cleared")


def is_gateway_blocked(bank: str) -> bool:
    """Returns True if gateway is currently blocked."""
    redis = get_redis()
    block_key = GATEWAY_BLOCKED_KEY.format(bank=bank)
    return redis.exists(block_key) == 1


def get_gateway_stats(bank: str) -> dict:
    """Get current stats for a gateway in this window."""
    redis = get_redis()
    window = _get_time_window()

    attempts_key = GATEWAY_ATTEMPTS_KEY.format(bank=bank, window=window)
    failures_key = GATEWAY_FAILURES_KEY.format(bank=bank, window=window)
    block_key    = GATEWAY_BLOCKED_KEY.format(bank=bank)

    attempts = int(redis.get(attempts_key) or 0)
    failures = int(redis.get(failures_key) or 0)
    blocked  = redis.exists(block_key) == 1

    success_rate = 0.0
    if attempts > 0:
        success_rate = round(((attempts - failures) / attempts) * 100, 1)

    # TTL remaining on block
    block_ttl = redis.ttl(block_key) if blocked else 0

    return {
        "bank":           bank,
        "attempts":       attempts,
        "failures":       failures,
        "success_rate":   f"{success_rate}%",
        "blocked":        blocked,
        "block_expires_in": f"{block_ttl}s" if blocked else None,
        "priority":       GATEWAY_REGISTRY[bank]["priority"],
    }


def get_best_gateway(
    exclude_bank: Optional[str] = None
) -> Optional[str]:
    """
    Returns the best available gateway.

    Logic:
    1. Filter out blocked gateways
    2. Filter out the failed gateway (exclude_bank)
    3. Sort by priority
    4. Return the highest priority available gateway
    """
    available = []

    for bank, info in GATEWAY_REGISTRY.items():
        if bank == exclude_bank:
            continue
        if is_gateway_blocked(bank):
            log.info(f"Skipping blocked gateway: {bank}")
            continue
        available.append((bank, info["priority"]))

    if not available:
        log.error("No gateways available — all blocked or excluded")
        return None

    # Sort by priority (lower number = higher priority)
    available.sort(key=lambda x: x[1])
    best = available[0][0]

    log.info(f"Best available gateway: {best} (excluding: {exclude_bank})")
    return best


def get_all_gateway_status() -> list:
    """Returns health status of all gateways."""
    status = []
    for bank in GATEWAY_REGISTRY:
        stats = get_gateway_stats(bank)
        stats["gateway_name"] = GATEWAY_REGISTRY[bank]["name"]
        status.append(stats)

    # Sort by priority
    status.sort(key=lambda x: x["priority"])
    return status