import random
import math
from datetime import datetime, timedelta
from typing import Optional


# ── Backoff configuration per error class ────────────────────────────────────

RETRY_CONFIG = {
    "REMITTER_BANK_DOWN": {
        "max_retries":    5,
        "base_delay":     30,    # seconds
        "max_delay":      600,   # cap at 10 minutes
        "strategy":       "exponential_backoff_jitter",
    },
    "BENEFICIARY_BANK_DOWN": {
        "max_retries":    3,
        "base_delay":     60,
        "max_delay":      900,   # cap at 15 minutes
        "strategy":       "exponential_backoff_jitter",
    },
    "LIMIT_EXCEEDED": {
        "max_retries":    2,
        "base_delay":     3600,  # 1 hour
        "max_delay":      7200,  # cap at 2 hours
        "strategy":       "fixed_delay",
    },
    "UNKNOWN": {
        "max_retries":    2,
        "base_delay":     120,
        "max_delay":      300,
        "strategy":       "exponential_backoff_jitter",
    },
    "ACCOUNT_ISSUE": {
        "max_retries":    0,
        "base_delay":     0,
        "max_delay":      0,
        "strategy":       "no_retry",
    },
}


def calculate_exponential_backoff(
    attempt: int,
    base_delay: int,
    max_delay: int
) -> float:
    """
    Exponential backoff with FULL jitter.

    Formula: min(max_delay, random(0, base_delay * 2^attempt))

    Why full jitter?
    Without jitter: all payments that failed at the same time
    retry at the same time — thundering herd, bank gets hammered.

    With full jitter: retries are spread randomly across the window.
    This is what AWS recommends in their architecture blog.

    Attempt 0: random(0, 30)   → avg 15s
    Attempt 1: random(0, 60)   → avg 30s
    Attempt 2: random(0, 120)  → avg 60s
    Attempt 3: random(0, 240)  → avg 120s
    Attempt 4: random(0, 480)  → avg 240s (capped at max_delay)
    """
    # Calculate the exponential ceiling
    exponential_ceiling = base_delay * (2 ** attempt)

    # Cap it
    capped = min(max_delay, exponential_ceiling)

    # Add full jitter — random value between 0 and the ceiling
    delay_with_jitter = random.uniform(0, capped)

    return round(delay_with_jitter, 2)


def calculate_fixed_delay(base_delay: int) -> float:
    """Fixed delay with small jitter (±10%) to avoid thundering herd."""
    jitter = random.uniform(-0.1, 0.1) * base_delay
    return round(base_delay + jitter, 2)


def get_retry_delay(
    error_class: str,
    attempt: int
) -> Optional[float]:
    """
    Get delay in seconds for a given error class and attempt number.
    Returns None if no retry should happen.
    """
    config = RETRY_CONFIG.get(error_class, RETRY_CONFIG["UNKNOWN"])

    # No retry
    if config["strategy"] == "no_retry":
        return None

    # Exceeded max retries
    if attempt >= config["max_retries"]:
        return None

    if config["strategy"] == "exponential_backoff_jitter":
        return calculate_exponential_backoff(
            attempt=attempt,
            base_delay=config["base_delay"],
            max_delay=config["max_delay"]
        )

    if config["strategy"] == "fixed_delay":
        return calculate_fixed_delay(config["base_delay"])

    return None


def build_full_retry_schedule(error_class: str) -> list:
    """
    Build the complete retry schedule for a payment.
    Shows every planned retry attempt with exact timestamps.
    """
    config = RETRY_CONFIG.get(error_class, RETRY_CONFIG["UNKNOWN"])

    if config["strategy"] == "no_retry":
        return []

    schedule = []
    now = datetime.utcnow()
    cumulative_seconds = 0

    for attempt in range(config["max_retries"]):
        delay = get_retry_delay(error_class, attempt)
        if delay is None:
            break

        cumulative_seconds += delay
        retry_at = now + timedelta(seconds=cumulative_seconds)

        schedule.append({
            "attempt":            attempt + 1,
            "delay_seconds":      delay,
            "cumulative_seconds": round(cumulative_seconds, 2),
            "retry_at":           retry_at.isoformat(),
            "strategy":           config["strategy"],
        })

    return schedule


def get_max_retries(error_class: str) -> int:
    """Returns max retries for a given error class."""
    config = RETRY_CONFIG.get(error_class, RETRY_CONFIG["UNKNOWN"])
    return config["max_retries"]


def should_retry(error_class: str, current_attempt: int) -> bool:
    """Returns True if another retry should be attempted."""
    return get_retry_delay(error_class, current_attempt) is not None