from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Annvitra WhatsApp Ordering Bot"
    database_url: str = "sqlite:///./annvitra.db"

    menu_source: str = "demo"

    twilio_account_sid: str = ""
    twilio_auth_token: str = ""
    twilio_whatsapp_from: str = "whatsapp:+14155238886"
    owner_whatsapp_number: str = "whatsapp:+923000000000"
    public_base_url: str = ""

    google_sheet_id: str = ""
    google_worksheet: str = "Menu"
    google_service_account_file: str = "service-account.json"

    upi_payment_instructions: str = (
        "Please transfer the exact amount to the business UPI account "
        "and wait for payment verification."
    )
    upi_id_or_name: str = "Configure the real business UPI ID here"

    twilio_validate_signature: bool = False
    order_reservation_minutes: int = 30

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


settings = Settings()
