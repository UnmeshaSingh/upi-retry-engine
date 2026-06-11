import json
import random
import asyncio
from fastapi import APIRouter, HTTPException, Depends
from app.core.redis_client import get_redis
from app.services.peak_hour_service import (
    get_system_status,
    simulate_peak_spike,
    clear_spike,
    record_failure_event,
    is_throttle_active,
    should_retry_now,
    PEAK_FAILURE_MULTIPLIER
)
from app.services.stream_service import push_to_stream
from app.models.payment import FailedPaymentEvent, UPIErrorCode
from app.core.database import get_db
from app.services.db_service import save_payment_to_db
from sqlalchemy.orm import Session
import uuid
from datetime import datetime

router = APIRouter(prefix="/simulator", tags=["Simulator"])

# Real UPI error distribution during peak hours
# Based on publicly known NPCI failure patterns
PEAK_ERROR_DISTRIBUTION = [
    ("U69", 0.35),  # Remitter bank down — most common during peak
    ("Z9",  0.25),  # Beneficiary bank down
    ("U30", 0.10),  # Account issues
    ("U44", 0.10),  # Limit exceeded (many people hit limits at night)
    ("U16", 0.10),  # Transaction not permitted
    ("U99", 0.10),  # Unknown
]

PEAK_BANKS = ["HDFC", "ICICI", "SBI", "AXIS", "KOTAK"]
PEAK_MERCHANTS = [
    {"id": "zomato_001",   "name": "Zomato"},
    {"id": "swiggy_001",   "name": "Swiggy"},
    {"id": "blinkit_001",  "name": "Blinkit"},
    {"id": "amazon_001",   "name": "Amazon"},
    {"id": "flipkart_001", "name": "Flipkart"},
]


def _weighted_error() -> str:
    """Pick a UPI error code based on peak hour distribution."""
    rand = random.random()
    cumulative = 0
    for code, prob in PEAK_ERROR_DISTRIBUTION:
        cumulative += prob
        if rand <= cumulative:
            return code
    return "U99"


def _generate_peak_payment() -> dict:
    """Generate a realistic peak-hour payment failure."""
    merchant  = random.choice(PEAK_MERCHANTS)
    remitter  = random.choice(PEAK_BANKS)
    beneficiary = random.choice([b for b in PEAK_BANKS if b != remitter])

    return {
        "payment_id":       str(uuid.uuid4()),
        "amount":           round(random.uniform(50, 2000), 2),
        "upi_error_code":   _weighted_error(),
        "remitter_bank":    remitter,
        "beneficiary_bank": beneficiary,
        "merchant_id":      merchant["id"],
        "merchant_name":    merchant["name"],
        "upi_id":           f"{merchant['name'].lower()}@upi",
        "failed_at":        datetime.utcnow(),
        "status":           "FAILED",
        "retry_count":      0
    }


@router.get("/status")
def system_status():
    """
    Current system status — peak hour detection, spike status, throttle.
    """
    return get_system_status()


@router.post("/spike")
def trigger_spike(failure_count: int = 100):
    """
    Simulate a peak-hour failure spike.
    Injects N failures to trigger throttling.
    This is what happens at 9pm on a Friday in India.
    """
    result = simulate_peak_spike(failure_count)
    return {
        **result,
        "system_status": get_system_status()
    }


@router.post("/spike/clear")
def clear_spike_endpoint():
    """Clear the simulated spike and throttle."""
    clear_spike()
    return {
        "cleared": True,
        "system_status": get_system_status()
    }


@router.post("/burst/{count}")
def simulate_burst(
    count: int,
    redis=Depends(get_redis),
    db: Session = Depends(get_db)
):
    """
    Simulate a burst of N failed payments — like peak hour traffic.
    Pushes real payment events into the stream.
    Max 50 per call to avoid overload.
    """
    if count > 50:
        raise HTTPException(
            status_code=400,
            detail="Max 50 payments per burst call"
        )

    results = []
    throttled = 0
    processed = 0

    for i in range(count):
        # Check throttle
        if not should_retry_now():
            throttled += 1
            continue

        payment_data = _generate_peak_payment()

        try:
            event = FailedPaymentEvent(**payment_data)

            # Store in Redis
            redis_key = f"payment:{event.payment_id}"
            redis.setex(redis_key, 86400, event.model_dump_json())

            # Push to stream
            stream_id = push_to_stream(event)

            # Record failure for spike detection
            failure_count = record_failure_event()

            # Save to DB
            save_payment_to_db(event, db)

            processed += 1
            results.append({
                "payment_id":     event.payment_id,
                "merchant":       event.merchant_name,
                "amount":         event.amount,
                "error_code":     event.upi_error_code.value,
                "stream_id":      stream_id,
            })

        except Exception as e:
            results.append({"error": str(e)})

    return {
        "requested":       count,
        "processed":       processed,
        "throttled":       throttled,
        "throttle_active": is_throttle_active(),
        "system_status":   get_system_status(),
        "payments":        results
    }


@router.get("/error-distribution")
def error_distribution():
    """
    Show the peak hour UPI error distribution used in simulation.
    Based on publicly known NPCI failure patterns.
    """
    return {
        "description": "UPI error distribution during peak hours (8-10pm IST)",
        "distribution": [
            {
                "error_code":  code,
                "probability": f"{prob * 100}%",
                "meaning":     {
                    "U69": "Remitter bank unavailable",
                    "Z9":  "Beneficiary bank unavailable",
                    "U30": "Account frozen",
                    "U44": "Daily limit exceeded",
                    "U16": "Transaction not permitted",
                    "U99": "Unknown failure"
                }.get(code, "Unknown")
            }
            for code, prob in PEAK_ERROR_DISTRIBUTION
        ],
        "peak_failure_multiplier": f"{PEAK_FAILURE_MULTIPLIER}x normal rate",
        "note": "During peak hours, U69 dominates because major PSP banks "
                "experience degraded performance under load"
    }