import random
import uuid
from locust import HttpUser, task, between, events
from datetime import datetime

# ── Test data ─────────────────────────────────────────────────────────────────

UPI_ERRORS = ["U69", "Z9", "U30", "U44", "U16", "U99"]
BANKS      = ["HDFC", "ICICI", "SBI", "AXIS", "KOTAK"]
MERCHANTS  = [
    {"id": "zomato_001",   "name": "Zomato"},
    {"id": "swiggy_001",   "name": "Swiggy"},
    {"id": "blinkit_001",  "name": "Blinkit"},
    {"id": "amazon_001",   "name": "Amazon"},
    {"id": "flipkart_001", "name": "Flipkart"},
]


def random_payment():
    merchant = random.choice(MERCHANTS)
    remitter = random.choice(BANKS)
    beneficiary = random.choice([b for b in BANKS if b != remitter])
    return {
        "amount":           round(random.uniform(10, 5000), 2),
        "upi_error_code":   random.choice(UPI_ERRORS),
        "remitter_bank":    remitter,
        "beneficiary_bank": beneficiary,
        "merchant_id":      merchant["id"],
        "merchant_name":    merchant["name"],
        "upi_id":           f"{merchant['name'].lower()}@upi"
    }


class PaymentUser(HttpUser):
    wait_time = between(0.5, 2)
    payment_ids = []

    @task(5)
    def report_failed_payment(self):
        payload = random_payment()
        with self.client.post(
            "/payments/fail",
            json=payload,
            catch_response=True
        ) as response:
            if response.status_code == 201:
                data = response.json()
                PaymentUser.payment_ids.append(data["payment_id"])
                if len(PaymentUser.payment_ids) > 100:
                    PaymentUser.payment_ids = PaymentUser.payment_ids[-100:]
                response.success()
            else:
                response.failure(f"POST /payments/fail returned {response.status_code}")

    @task(2)
    def get_payment(self):
        if not PaymentUser.payment_ids:
            return
        payment_id = random.choice(PaymentUser.payment_ids)
        with self.client.get(
            f"/payments/{payment_id}",
            catch_response=True
        ) as response:
            if response.status_code == 200:
                response.success()
            else:
                response.failure(f"GET /payments/{payment_id} returned {response.status_code}")

    @task(2)
    def get_payment_timeline(self):
        if not PaymentUser.payment_ids:
            return
        payment_id = random.choice(PaymentUser.payment_ids)
        with self.client.get(
            f"/payments/{payment_id}/timeline",
            catch_response=True
        ) as response:
            if response.status_code in [200, 404]:
                response.success()
            else:
                response.failure(f"Timeline returned {response.status_code}")

    @task(1)
    def check_health(self):
        self.client.get("/health")

    @task(1)
    def get_gateway_status(self):
        self.client.get("/routing/status")

    @task(1)
    def get_circuit_breaker_status(self):
        self.client.get("/circuit-breaker/status")

    @task(1)
    def simulate_retry(self):
        error_classes = [
            "REMITTER_BANK_DOWN",
            "BENEFICIARY_BANK_DOWN",
            "LIMIT_EXCEEDED"
        ]
        error_class = random.choice(error_classes)
        self.client.get(f"/retry/simulate/{error_class}")

    @task(1)
    def get_stream_events(self):
        self.client.get("/payments/stream/events")