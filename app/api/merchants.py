from fastapi import APIRouter, HTTPException
from app.services.merchant_service import (
    MERCHANT_SLA,
    PRIORITY_LABELS,
    get_merchant_sla,
    get_sla_status,
    get_retry_priority_score,
    get_breach_counts
)
from datetime import datetime, timezone

router = APIRouter(prefix="/merchants", tags=["Merchants"])


@router.get("/sla")
def get_all_merchant_slas():
    """
    Get SLA configuration for all registered merchants.
    Shows deadline, priority, and breach action per merchant.
    """
    merchants = []

    for merchant_id, config in MERCHANT_SLA.items():
        if merchant_id == "default":
            continue
        merchants.append({
            "merchant_id":   merchant_id,
            "name":          config["name"],
            "sla_seconds":   config["sla_seconds"],
            "priority":      config["priority"],
            "priority_label": PRIORITY_LABELS[config["priority"]],
            "category":      config["category"],
            "breach_action": config["breach_action"],
        })

    # Sort by priority
    merchants.sort(key=lambda x: x["priority"])

    return {
        "total_merchants": len(merchants),
        "merchants":       merchants
    }


@router.get("/sla/{merchant_id}")
def get_merchant_sla_status(merchant_id: str):
    """Get SLA config for a specific merchant."""
    if merchant_id not in MERCHANT_SLA:
        raise HTTPException(
            status_code=404,
            detail=f"Merchant {merchant_id} not found"
        )
    return get_merchant_sla(merchant_id)


@router.get("/priority-score/{merchant_id}")
def get_priority_score(merchant_id: str, failed_seconds_ago: int = 5):
    """
    Calculate retry priority score for a merchant.
    Use failed_seconds_ago to simulate how urgent a payment is.
    """
    if merchant_id not in MERCHANT_SLA:
        raise HTTPException(
            status_code=404,
            detail=f"Merchant {merchant_id} not found"
        )

    # Simulate payment that failed N seconds ago
    from datetime import timedelta
    failed_at = datetime.now(timezone.utc) - timedelta(seconds=failed_seconds_ago)

    score      = get_retry_priority_score(merchant_id, failed_at)
    sla_status = get_sla_status(merchant_id, failed_at)

    return {
        "merchant_id":    merchant_id,
        "failed_seconds_ago": failed_seconds_ago,
        "priority_score": score,
        "sla_status":     sla_status,
        "interpretation": f"Score {score} — higher score = retried sooner"
    }


@router.get("/breaches")
def get_sla_breaches():
    """Get SLA breach counts per merchant today."""
    counts = get_breach_counts()
    return {
        "breach_counts": counts,
        "total_breaches": sum(counts.values())
    }