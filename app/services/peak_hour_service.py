import time
import logging
from datetime import datetime, timezone
from app.core.redis_client import get_redis

log = logging.getLogger(__name__)

# ── Peak hour configuration ───────────────────────────────────────────────────

# Peak hours in IST (UTC+5:30) — converted to UTC
# 8pm IST = 14:30 UTC, 10pm IST = 16:30 UTC
PEAK_HOURS_UTC = [
    (14, 30, 16, 30),   # 8pm-10pm IST
    (6, 30, 8, 30),     # 12pm-2pm IST (lunch spike)
]

# Failure rate multiplier during peak hours
PEAK_FAILURE_MULTIPLIER = 3.5

# Retry throttle during peak — only retry X% of normal volume
PEAK_RETRY_THROTTLE = 0.4  # 40% of normal retry volume

# Redis keys
PEAK_HOUR_KEY        = "system:peak_hour"
FAILURE_RATE_KEY     = "system:failure_rate:{window}"
SPIKE_DETECTED_KEY   = "system:spike_detected"
TOTAL_FAILURES_KEY   = "system:total_failures:{window}"
THROTTLE_ACTIVE_KEY  = "system:throttle_active"


def is_peak_hour() -> bool:
    """
    Check if current time is within peak hours.
    Uses UTC time internally.
    """
    now_utc = datetime.now(timezone.utc)
    current_minutes = now_utc.hour * 60 + now_utc.minute

    for start_h, start_m, end_h, end_m in PEAK_HOURS_UTC:
        start_minutes = start_h * 60 + start_m
        end_minutes   = end_h * 60 + end_m
        if start_minutes <= current_minutes <= end_minutes:
            return True

    return False


def get_current_window() -> int:
    """Returns current 1-minute window as integer."""
    return int(time.time() // 60)


def record_failure_event():
    """Record a payment failure for spike detection."""
    redis  = get_redis()
    window = get_current_window()

    key = TOTAL_FAILURES_KEY.format(window=window)
    count = redis.incr(key)
    redis.expire(key, 300)  # 5 min TTL

    # Check if spike threshold exceeded
    if count >= 50:  # 50+ failures in 1 minute = spike
        _declare_spike(count)

    return count


def _declare_spike(failure_count: int):
    """Declare a failure spike and activate throttling."""
    redis = get_redis()

    # Mark spike detected
    redis.set(SPIKE_DETECTED_KEY, str(failure_count), ex=300)

    # Activate throttle
    redis.set(THROTTLE_ACTIVE_KEY, "1", ex=300)

    log.warning(
        f"SPIKE DETECTED: {failure_count} failures in current window. "
        f"Throttling activated for 5 minutes."
    )


def is_spike_active() -> bool:
    """Returns True if a failure spike is currently detected."""
    redis = get_redis()
    return redis.exists(SPIKE_DETECTED_KEY) == 1


def is_throttle_active() -> bool:
    """Returns True if retry throttling is currently active."""
    redis = get_redis()
    return redis.exists(THROTTLE_ACTIVE_KEY) == 1


def should_retry_now(base_probability: float = 1.0) -> bool:
    """
    Determine if a retry should proceed based on current conditions.

    During spike/peak hours, only a fraction of retries proceed
    to avoid thundering herd on recovering infrastructure.
    """
    import random

    if is_throttle_active():
        # During throttle — only 40% of retries proceed
        return random.random() < (base_probability * PEAK_RETRY_THROTTLE)

    if is_peak_hour():
        # During peak hours — only 70% of retries proceed
        return random.random() < (base_probability * 0.7)

    return random.random() < base_probability


def get_system_status() -> dict:
    """Get full system status including peak hour and spike info."""
    redis  = get_redis()
    window = get_current_window()

    failures_key  = TOTAL_FAILURES_KEY.format(window=window)
    failure_count = int(redis.get(failures_key) or 0)

    spike_count = redis.get(SPIKE_DETECTED_KEY)
    throttle_ttl = redis.ttl(THROTTLE_ACTIVE_KEY)

    now_ist = datetime.now(timezone.utc)
    ist_hour = (now_ist.hour + 5) % 24
    ist_min  = (now_ist.minute + 30) % 60

    return {
        "current_time_ist":    f"{ist_hour:02d}:{ist_min:02d} IST",
        "is_peak_hour":        is_peak_hour(),
        "failures_this_minute": failure_count,
        "spike_detected":      is_spike_active(),
        "spike_failure_count": int(spike_count) if spike_count else 0,
        "throttle_active":     is_throttle_active(),
        "throttle_expires_in": f"{throttle_ttl}s" if throttle_ttl > 0 else None,
        "retry_probability":   f"{PEAK_RETRY_THROTTLE * 100}%" if is_throttle_active() else "100%",
        "peak_multiplier":     PEAK_FAILURE_MULTIPLIER,
    }


def simulate_peak_spike(failure_count: int = 100) -> dict:
    """
    Simulate a peak hour failure spike.
    Injects N failures into the current window to trigger throttling.
    """
    redis  = get_redis()
    window = get_current_window()

    key = TOTAL_FAILURES_KEY.format(window=window)
    redis.set(key, str(failure_count), ex=300)

    _declare_spike(failure_count)

    log.warning(f"SIMULATED SPIKE: {failure_count} failures injected")

    return {
        "simulated":     True,
        "failures_injected": failure_count,
        "throttle_active": True,
        "message": f"Spike of {failure_count} failures simulated. Throttling active for 5 minutes."
    }


def clear_spike():
    """Clear spike and throttle — for testing."""
    redis = get_redis()
    redis.delete(SPIKE_DETECTED_KEY)
    redis.delete(THROTTLE_ACTIVE_KEY)
    log.info("Spike and throttle cleared")