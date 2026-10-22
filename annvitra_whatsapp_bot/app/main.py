from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, Depends, HTTPException
from fastapi.responses import Response, PlainTextResponse
from sqlalchemy.orm import Session
from twilio.request_validator import RequestValidator
from app.config import settings
from app.db import Base, engine, get_db
from app.services import handle_customer, handle_owner, normalise_phone


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(title=settings.app_name, lifespan=lifespan)


@app.get("/health")
def health():
    return {"status": "ok", "app": settings.app_name}


def _verify_twilio_signature(request: Request, form_data: dict) -> None:
    if not settings.twilio_validate_signature:
        return
    if not settings.twilio_auth_token:
        raise HTTPException(status_code=500, detail="Twilio signature validation is enabled but auth token is missing.")
    signature = request.headers.get("X-Twilio-Signature", "")
    # Twilio signature validation requires the exact public URL Twilio called.
    url = str(request.url)
    if settings.public_base_url:
        url = settings.public_base_url.rstrip("/") + request.url.path
    validator = RequestValidator(settings.twilio_auth_token)
    if not validator.validate(url, form_data, signature):
        raise HTTPException(status_code=403, detail="Invalid Twilio signature.")


@app.post("/webhook/whatsapp")
async def whatsapp_webhook(request: Request, db: Session = Depends(get_db)):
    form = await request.form()
    form_data = dict(form)
    _verify_twilio_signature(request, form_data)

    sender = normalise_phone(str(form_data.get("From", "")))
    body = str(form_data.get("Body", "")).strip()
    if not sender or not body:
        return PlainTextResponse("Missing sender or message body.", status_code=400)

    owner = normalise_phone(settings.owner_whatsapp_number)
    try:
        if owner and sender.lower() == owner.lower():
            reply = handle_owner(db, sender, body)
        else:
            reply = handle_customer(db, sender, body)
    except Exception as exc:
        db.rollback()
        print(f"Webhook processing error from {sender}: {exc}")
        reply = "Sorry, something went wrong processing your message. Please try again or contact Annvitra."

    # Twilio expects TwiML for an immediate reply.
    safe_reply = (
        reply.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )
    twiml = f'<?xml version="1.0" encoding="UTF-8"?><Response><Message>{safe_reply}</Message></Response>'
    return Response(content=twiml, media_type="application/xml")


@app.get("/")
def root():
    return {"message": "Annvitra WhatsApp Ordering Bot API", "health": "/health", "webhook": "/webhook/whatsapp"}
