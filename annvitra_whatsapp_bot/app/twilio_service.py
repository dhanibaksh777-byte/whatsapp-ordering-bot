from twilio.rest import Client
from app.config import settings


def _client():
    if not settings.twilio_account_sid or not settings.twilio_auth_token:
        return None
    return Client(settings.twilio_account_sid, settings.twilio_auth_token)


def send_whatsapp(to_number: str, body: str) -> bool:
    client = _client()
    if client is None or not settings.twilio_whatsapp_from:
        # Local development: log instead of failing the webhook.
        print(f"[TWILIO NOT CONFIGURED] To={to_number}\n{body}\n")
        return False
    client.messages.create(
        from_=settings.twilio_whatsapp_from,
        to=to_number if to_number.startswith("whatsapp:") else f"whatsapp:{to_number}",
        body=body,
    )
    return True


def notify_owner(body: str) -> bool:
    if not settings.owner_whatsapp_number:
        print("[OWNER NUMBER NOT CONFIGURED]", body)
        return False
    return send_whatsapp(settings.owner_whatsapp_number, body)
