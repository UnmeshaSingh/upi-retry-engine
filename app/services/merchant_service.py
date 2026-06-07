import logging
from datetime import datetime, timezone
from typing import Optional
from app.core.redis_client import get_redis

log = logging.getLogger(__name__)

# ── Merchant SLA Registry ─────────────────────────────────────────────────────
# SLA = maximum seconds to confirm payment before order is affected

MERCHANT_SLA = {
    "zomato_001": {
        "name":             "Zomato",
        "sla_seconds":      8,
        "priority":         1,      # Higher number = higher priority
        "category":         "food_delivery",
        "breach_action":    "cancel_order",
        "contact":          "payments@zomato.com"
    },
    "swiggy_001": {
        "name":             "Swiggy",
        "sla_seconds":      12,
        "priority":         2,
        "category":         "food_delivery",
        "breach_action":    "cancel_order",
        "contact":          "payments@swiggy.com"
    },
    "blinkit_001": {
        "name":             "Blinkit",
        "sla_seconds":      10,
        "priority":         2,
        "category":         "quick_commerce",
        "breach_action":    "cancel_order",
        "contact":          "payments@blinkit.com"
    },
    "zepto_001": {
        "name":             "Zepto",
        "sla_seconds":      10,
        "priority":         2,
        "category":         "quick_commerce",
        "breach_action":    "cancel_order",
        "contact":          "payments@zepto.com"
    },
    "myntra_001": {
        "name":             "Myntra",
        "sla_seconds":      300,
        "priority":         4,
        "category":         "ecommerce",
        "breach_action":    "hold_order",
        "contact":          "payments@myntra.com"
    },
    "amazon_001": {
        "name":             "Amazon",
        "sla_seconds":      30,
        "priority":         3,
        "category":         "ecommerce",
        "breach_action":    "hold_order",
        "contact":          "payments@amazon.com"
    },
    "flipkart_001": {
        "name":             "Flipkart",
        "sla_seconds":      30,
        "priority":         3,
        "category":         "ecommerce",
        "breach_action":    "hold_order",
        "contact":          "payments@flipkart.com"
    },
    "default": {
        "name":             "Unknown Merchant",
        "sla_seconds":      60,
        "priority":         5,
        "category":         "general",
        "breach_action":    "notify",
        "contact":          None
    }
}

# Priority labels
PRIORITY_LABELS = {
    1: "CRITICAL",
    2: "HIGH",
    3: "MEDIUM",
    4: "LOW",
    5: "MINIMAL"
}


def get_merchant_sla(merchant_id: str) -> dict:
    """Get SLA config for a merchant. Falls back to default."""
    return MERCHANT_SLA.get(merchant_id, MERCHANT_SLA["default"])


def get_sla_status(
    merchant_id: str,
    failed_at: datetime
) -> dict:
    """
    Check SLA status for a payment.
    Returns whether SLA is breached and time remaining.
    """
    sla_config = get_merchant_sla(merchant_id)
    sla_seconds = sla_config["sla_seconds"]

    # Make failed_at timezone aware if it isn't
    if failed_at.tzinfo is None:
        failed_at = failed_at.replace(tzinfo=timezone.utc)

    now = datetime.now(timezone.utc)
    elapsed = (now - failed_at).total_seconds()
    remaining = sla_seconds - elapsed
    breached = elapsed > sla_seconds

    breach_pct = min(100, round((elapsed / sla_seconds) * 100, 1))

    return {
        "merchant_id":      merchant_id,
        "merchant_name":    sla_config["name"],
        "sla_seconds":      sla_seconds,
        "elapsed_seconds":  round(elapsed, 2),
        "remaining_seconds": round(max(0, remaining), 2),
        "breached":         breached,
        "breach_percent":   breach_pct,
        "priority":         sla_config["priority"],
        "priority_label":   PRIORITY_LABELS[sla_config["priority"]],
        "breach_action":    sla_config["breach_action"],
        "urgency":          _get_urgency(breach_pct, breached)
    }


def _get_urgency(breach_pct: float, breached: bool) -> str:
    """Human readable urgency level."""
    if breached:
        return "SLA_BREACHED"
    elif breach_pct >= 80:
        return "CRITICAL"
    elif breach_pct >= 60:
        return "HIGH"
    elif breach_pct >= 40:
        return "MEDIUM"
    else:
        return "LOW"


def get_retry_priority_score(
    merchant_id: str,
    failed_at: datetime
) -> int:
    """
    Calculate priority score for retry queue ordering.
    Higher score = retry sooner.

    Score factors:
    - Merchant base priority (1-5, inverted so 1 = highest)
    - SLA breach status
    - Time elapsed vs SLA
    """
    sla_config  = get_merchant_sla(merchant_id)
    sla_status  = get_sla_status(merchant_id, failed_at)

    # Base score from merchant priority (invert so priority 1 = score 500)
    base_score = (6 - sla_config["priority"]) * 100

    # Boost if SLA is close to breach or already breached
    if sla_status["breached"]:
        urgency_boost = 400
    elif sla_status["breach_percent"] >= 80:
        urgency_boost = 300
    elif sla_status["breach_percent"] >= 60:
        urgency_boost = 200
    elif sla_status["breach_percent"] >= 40:
        urgency_boost = 100
    else:
        urgency_boost = 0

    total_score = base_score + urgency_boost

    log.info(
        f"Priority score for {merchant_id}: "
        f"base={base_score} + urgency={urgency_boost} = {total_score}"
    )

    return total_score


def store_sla_breach(payment_id: str, merchant_id: str):
    """Record SLA breach in Redis for monitoring."""
    redis = get_redis()
    breach_key = f"sla_breach:{payment_id}"
    redis.set(breach_key, merchant_id, ex=86400)

    # Increment breach counter per merchant
    counter_key = f"sla_breach_count:{merchant_id}"
    redis.incr(counter_key)
    redis.expire(counter_key, 86400)

    log.warning(f"SLA BREACHED: payment {payment_id[:8]} for {merchant_id}")


def get_breach_counts() -> dict:
    """Get SLA breach counts per merchant today."""
    redis = get_redis()
    counts = {}

    for merchant_id in MERCHANT_SLA:
        if merchant_id == "default":
            continue
        counter_key = f"sla_breach_count:{merchant_id}"
        count = redis.get(counter_key)
        if count:
            counts[merchant_id] = int(count)

    return counts