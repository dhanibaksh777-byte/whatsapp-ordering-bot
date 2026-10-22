from dataclasses import dataclass
from typing import Optional
from app.config import settings


@dataclass(frozen=True)
class MenuItem:
    name: str
    price: float
    qty: int
    available: bool = True


# Fictional learning-only data. Replace with real client data in Google Sheets.
DEMO_MENU = [
    MenuItem("Demo Chicken Biryani", 150, 5, True),
    MenuItem("Demo Daal Chawal", 90, 8, True),
    MenuItem("Demo Chicken Karahi", 250, 10, True),
    MenuItem("Demo Raita", 30, 10, True),
    MenuItem("Demo Gulab Jamun", 60, 6, True),
]


def _to_bool(value) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"true", "1", "yes", "y", "available"}


def get_menu() -> list[MenuItem]:
    source = settings.menu_source.strip().lower()
    if source == "demo":
        return DEMO_MENU
    if source != "google_sheets":
        raise RuntimeError("MENU_SOURCE must be 'demo' or 'google_sheets'.")

    if not settings.google_sheet_id or not settings.google_service_account_file:
        raise RuntimeError("Google Sheets is selected but its ID or service-account file is missing.")

    import gspread

    client = gspread.service_account(filename=settings.google_service_account_file)
    worksheet = client.open_by_key(settings.google_sheet_id).worksheet(settings.google_worksheet)
    rows = worksheet.get_all_records()
    result = []
    for row_num, row in enumerate(rows, start=2):
        try:
            name = str(row.get("name", "")).strip()
            price = float(row.get("price", 0))
            qty = int(row.get("qty", 0))
            available = _to_bool(row.get("available", True))
            if not name or price < 0 or qty < 0:
                raise ValueError("name must be present; price and qty must be non-negative")
            result.append(MenuItem(name=name, price=price, qty=qty, available=available))
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Invalid Google Sheet menu data on row {row_num}: {exc}") from exc
    return result


def visible_menu() -> list[tuple[int, MenuItem]]:
    # Numbers are assigned after filtering, so the displayed numbers always match input numbers.
    items = [item for item in get_menu() if item.available and item.qty > 0]
    return list(enumerate(items, start=1))


def format_menu() -> str:
    items = visible_menu()
    if not items:
        return "Sorry, no extra dishes are available right now."
    lines = ["Today's available extra dishes:"]
    for number, item in items:
        price = f"{item.price:g}"
        lines.append(f"{number}. {item.name} — Rs. {price} ({item.qty} available)")
    lines.append("")
    lines.append("Add items using: NUMBER QUANTITY (example: 1 2)")
    lines.append("Commands: menu, cart, remove NUMBER, done, cancel")
    return "\n".join(lines)