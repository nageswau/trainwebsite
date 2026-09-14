import httpx

from app.core.config import settings


class PaymentService:
    async def create_checkout(self, provider: str, amount: float, currency: str, reference: str) -> dict:
        minor_amount = int(round(amount * 100))
        if provider == "razorpay":
            if not settings.razorpay_key_id or not settings.razorpay_key_secret:
                return {"status": "configuration_required", "provider": provider, "amount": amount, "currency": currency, "reference": reference}
            async with httpx.AsyncClient(timeout=20) as client:
                response = await client.post(
                    "https://api.razorpay.com/v1/orders", auth=(settings.razorpay_key_id, settings.razorpay_key_secret), json={"amount": minor_amount, "currency": currency, "receipt": reference}
                )
                response.raise_for_status()
                data = response.json()
            return {"status": "ready", "provider": provider, "amount": amount, "currency": currency, "reference": reference, "key_id": settings.razorpay_key_id, "provider_order_id": data["id"]}
        return {"status": "manual", "provider": "manual", "amount": amount, "currency": currency, "reference": reference}


payments = PaymentService()
