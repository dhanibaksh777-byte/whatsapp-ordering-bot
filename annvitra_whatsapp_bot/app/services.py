import json
import re
from datetime import datetime, timezone
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload
from app.models import CustomerSession, Order, OrderItem
from app.menu import get_menu, visible_menu, format_menu, MenuItem
from app.twilio_service import notify_owner, send_whatsapp
from app.config import settings


# Delivered orders still consume the original sheet stock; only cancelled orders release it.
ACTIVE_RESERVATION_STATUSES = {"awaiting_payment", "confirmed", "preparing", "out_for_delivery", "delivered"}


def normalise_phone(phone: str) -> str:
    return (phone or "").strip()


def get_session(db: Session, phone: str) -> CustomerSession:
    session = db.get(CustomerSession, phone)
    if session is None:
        session = CustomerSession(phone=phone, step="shopping", cart_json="[]")
        db.add(session)
        db.commit()
        db.refresh(session)
    return session


def load_cart(session: CustomerSession) -> list[dict]:
    try:
        cart = json.loads(session.cart_json or "[]")
        return cart if isinstance(cart, list) else []
    except json.JSONDecodeError:
        return []


def save_cart(db: Session, session: CustomerSession, cart: list[dict]) -> None:
    session.cart_json = json.dumps(cart)
    session.updated_at = datetime.now(timezone.utc)
    db.commit()


def available_stock(db: Session, menu_number: int, item: MenuItem) -> int:
    # Use the dish name rather than its displayed menu number: menu numbering can shift
    # when a dish becomes unavailable. Names should be unique in the source sheet.
    reserved = db.execute(
        select(OrderItem.quantity)
        .join(Order, Order.id == OrderItem.order_id)
        .where(
            OrderItem.name == item.name,
            Order.order_status.in_(ACTIVE_RESERVATION_STATUSES),
        )
    ).scalars().all()
    return max(0, item.qty - sum(reserved))


def cart_total(cart: list[dict]) -> float:
    return round(sum(float(row["price"]) * int(row["quantity"]) for row in cart), 2)


def cart_text(cart: list[dict]) -> str:
    if not cart:
        return "Your cart is empty."
    lines = ["Your cart:"]
    for row in cart:
        subtotal = float(row["price"]) * int(row["quantity"])
        lines.append(f"- {row['name']} x {row['quantity']} = Rs. {subtotal:g}")
    lines.append(f"Total: Rs. {cart_total(cart):g}")
    return "\n".join(lines)


def order_summary(cart: list[dict], session: CustomerSession) -> str:
    return (
        f"{cart_text(cart)}\n\n"
        f"Name: {session.customer_name}\n"
        f"Delivery contact: {session.delivery_phone}\n"
        f"Address: {session.address}\n\n"
        "Reply CONFIRM to place this order, or CANCEL to clear it."
    )


def parse_order_code(text: str) -> str:
    parts = text.strip().split(maxsplit=1)
    return parts[1].strip().upper() if len(parts) == 2 else ""


def get_order(db: Session, code: str) -> Order | None:
    if not code:
        return None
    return db.execute(
        select(Order).options(selectinload(Order.items)).where(Order.order_code == code)
    ).scalar_one_or_none()


def format_order(order: Order) -> str:
    lines = [
        f"Order {order.order_code}",
        f"Customer: {order.customer_name}",
        f"WhatsApp: {order.customer_phone}",
        f"Delivery contact: {order.delivery_phone}",
        f"Address: {order.address}",
    ]
    for item in order.items:
        lines.append(f"- {item.name} x {item.quantity} = Rs. {item.price * item.quantity:g}")
    lines.extend([
        f"Total: Rs. {order.total:g}",
        f"Order status: {order.order_status}",
        f"Payment: {order.payment_method or 'not selected'} / {order.payment_status}",
    ])
    return "\n".join(lines)


def _new_order_code(db: Session) -> str:
    # Unique constraint handles collision; this simple ID is adequate for a learning MVP.
    latest = db.execute(select(Order.id).order_by(Order.id.desc()).limit(1)).scalar_one_or_none() or 0
    return f"ANN-{latest + 1001:06d}"


def owner_command(db: Session, phone: str, text: str) -> str:
    command = text.strip()
    upper = command.upper()

    if upper == "ORDERS":
        orders = db.execute(
            select(Order)
            .where(Order.order_status.not_in(["delivered", "cancelled"]))
            .order_by(Order.created_at.desc())
            .limit(10)
        ).scalars().all()
        if not orders:
            return "There are no active orders."
        return "Recent active orders:\n" + "\n".join(
            f"{o.order_code} | Rs. {o.total:g} | {o.order_status} | {o.payment_status}"
            for o in orders
        )

    if upper.startswith("ORDER "):
        order = get_order(db, parse_order_code(command))
        return format_order(order) if order else "Order not found. Check the order ID."

    action_map = {
        "PAID": ("paid", None),
        "CASHRECEIVED": ("paid", None),
        "PREPARING": (None, "preparing"),
        "OUTFORDELIVERY": (None, "out_for_delivery"),
        "DELIVERED": (None, "delivered"),
        "CANCEL": (None, "cancelled"),
    }
    action = upper.split(maxsplit=1)[0] if upper else ""
    if action not in action_map:
        return (
            "Owner commands:\nORDERS\nORDER ANN-001001\n"
            "PAID ANN-001001\nCASHRECEIVED ANN-001001\n"
            "PREPARING ANN-001001\nOUTFORDELIVERY ANN-001001\n"
            "DELIVERED ANN-001001\nCANCEL ANN-001001"
        )

    code = parse_order_code(command)
    order = get_order(db, code)
    if not order:
        return "Order not found. Check the order ID."

    payment_status, new_order_status = action_map[action]
    if action == "PAID" and order.payment_method != "upi":
        return "This order is not marked as UPI. Use CASHRECEIVED for cash orders."
    if action == "CASHRECEIVED" and order.payment_method != "cash":
        return "This order is not marked as cash. Use PAID for UPI orders."
    if action in {"PAID", "CASHRECEIVED"}:
        if order.payment_status == "paid":
            return f"{order.order_code} is already marked paid."
        if order.order_status == "cancelled":
            return "This order is cancelled; payment cannot be marked paid."
        order.payment_status = "paid"
        if order.order_status == "awaiting_payment":
            order.order_status = "confirmed"
        db.commit()
        send_whatsapp(order.customer_phone, f"Payment for {order.order_code} has been verified by Annvitra. Thank you!")
        return f"{order.order_code}: payment marked PAID. Customer has been notified."

    if new_order_status == "cancelled":
        if order.order_status in {"delivered", "cancelled"}:
            return f"Cannot cancel an order with status {order.order_status}."
        order.order_status = "cancelled"
        db.commit()
        send_whatsapp(order.customer_phone, f"Your Annvitra order {order.order_code} has been cancelled. Please contact the restaurant if you need help.")
        return f"{order.order_code} cancelled. Its reserved stock is released in the app's reservation calculation."

    if order.order_status == "cancelled":
        return "This order is cancelled and cannot be progressed."
    order.order_status = new_order_status
    db.commit()
    if new_order_status == "preparing":
        customer_message = f"Your order {order.order_code} is being prepared."
    elif new_order_status == "out_for_delivery":
        customer_message = f"Your order {order.order_code} is out for delivery."
    else:
        customer_message = f"Your order {order.order_code} has been marked delivered. Thank you!"
    send_whatsapp(order.customer_phone, customer_message)
    return f"{order.order_code} updated to {new_order_status}. Customer has been notified."


def handle_owner(db: Session, phone: str, text: str) -> str:
    return owner_command(db, phone, text)


def handle_customer(db: Session, phone: str, text: str) -> str:
    session = get_session(db, phone)
    message = text.strip()
    lower = message.lower()
    cart = load_cart(session)

    if lower in {"hi", "hello", "hey", "start", "menu"}:
        session.step = "shopping"
        db.commit()
        return "Welcome to Annvitra!\n\n" + format_menu()

    if lower == "help":
        return (
            "Customer commands:\nmenu — show menu\ncart — show cart\n"
            "remove NUMBER — remove an item\ndone — finish shopping\n"
            "cancel — clear cart or cancel current data\n"
            "Use NUMBER QUANTITY to add an item."
        )

    if session.step == "awaiting_name":
        if len(message) < 2 or len(message) > 150:
            return "Please enter a valid name (2–150 characters)."
        session.customer_name = message
        session.step = "awaiting_delivery_phone"
        db.commit()
        return "Thanks! Send the delivery contact number. You can send your WhatsApp number or another reachable number."

    if session.step == "awaiting_delivery_phone":
        cleaned = re.sub(r"[\s()-]", "", message)
        if not re.fullmatch(r"\+?[0-9]{7,16}", cleaned):
            return "Please send a valid contact number, including country code if possible."
        session.delivery_phone = cleaned
        session.step = "awaiting_address"
        db.commit()
        return "Now send the complete delivery address, including area and a nearby landmark."

    if session.step == "awaiting_address":
        if len(message) < 8 or len(message) > 500:
            return "Please send a more complete address (8–500 characters), including area or landmark."
        session.address = message
        session.step = "review"
        db.commit()
        return order_summary(load_cart(session), session)

    if session.step == "review":
        if lower == "cancel":
            session.cart_json = "[]"
            session.step = "shopping"
            session.customer_name = ""
            session.delivery_phone = ""
            session.address = ""
            db.commit()
            return "Order request cancelled and cart cleared. Send MENU to start again."
        if lower != "confirm":
            return "Please review your details. Reply CONFIRM to place the order or CANCEL to clear it."
        cart = load_cart(session)
        if not cart:
            session.step = "shopping"
            db.commit()
            return "Your cart is empty. Send MENU to start again."

        # Validate the entire cart against current menu data before creating an order.
        current_items = visible_menu()
        for row in cart:
            if row["menu_number"] < 1 or row["menu_number"] > len(current_items):
                return "The menu changed while you were ordering. Send MENU, review your cart, and try again."
            current_item = current_items[row["menu_number"] - 1][1]
            stock = available_stock(db, row["menu_number"], current_item)
            if current_item.name != row["name"] or current_item.price != row["price"]:
                return "A dish or price has changed. Send MENU, update your cart, and try again."
            if int(row["quantity"]) > stock:
                return f"Only {stock} of {row['name']} are available now. Update your cart and send DONE again."

        order = Order(
            order_code=_new_order_code(db),
            customer_phone=phone,
            customer_name=session.customer_name,
            delivery_phone=session.delivery_phone,
            address=session.address,
            total=cart_total(cart),
            order_status="awaiting_payment",
            payment_method="",
            payment_status="pending",
        )
        db.add(order)
        db.flush()
        for row in cart:
            db.add(OrderItem(
                order_id=order.id,
                item_number=row["menu_number"],
                name=row["name"],
                price=row["price"],
                quantity=row["quantity"],
            ))
        # Keep order creation and session transition together in the same DB transaction.
        session.cart_json = "[]"
        session.step = "awaiting_payment_method"
        db.commit()
        db.refresh(order)

        owner_message = (
            f"NEW ANN VITRA ORDER: {order.order_code}\n"
            f"Customer: {order.customer_name}\n"
            f"WhatsApp: {order.customer_phone}\n"
            f"Delivery contact: {order.delivery_phone}\n"
            f"Address: {order.address}\n"
            f"Total: Rs. {order.total:g}\n"
            "Payment: pending\n"
            "Use ORDER " + order.order_code + " for details."
        )
        try:
            notify_owner(owner_message)
        except Exception as exc:
            # Order is safely stored even if the notification fails.
            print(f"Owner notification failed for {order.order_code}: {exc}")

        return (
            f"Your order {order.order_code} has been placed!\n"
            f"Total: Rs. {order.total:g}\n\n"
            "Choose payment method:\n"
            "Reply UPI for UPI transfer, or CASH for cash on delivery.\n"
            "Your order is saved; payment is still pending."
        )

    if session.step == "awaiting_payment_method":
        if lower not in {"upi", "cash"}:
            return "Please choose a payment method: reply UPI or CASH."
        # Find the newest order for this customer that is still awaiting payment method.
        order = db.execute(
            select(Order)
            .options(selectinload(Order.items))
            .where(
                Order.customer_phone == phone,
                Order.payment_method == "",
                Order.order_status == "awaiting_payment",
            )
            .order_by(Order.created_at.desc())
            .limit(1)
        ).scalar_one_or_none()
        if not order:
            session.step = "shopping"
            db.commit()
            return "I couldn't find an order awaiting payment selection. Send MENU to start again."

        order.payment_method = lower
        session.step = "shopping"
        db.commit()
        if lower == "upi":
            notify_text = (
                f"Payment method selected: UPI\nOrder: {order.order_code}\n"
                f"Amount: Rs. {order.total:g}\n"
                "Owner: verify payment manually, then send PAID " + order.order_code
            )
            try:
                notify_owner(notify_text)
            except Exception as exc:
                print(f"Owner payment notification failed: {exc}")
            return (
                f"UPI selected for {order.order_code}.\n"
                f"Amount: Rs. {order.total:g}\n"
                f"UPI details: {settings.upi_id_or_name}\n"
                f"{settings.upi_payment_instructions}\n\n"
                "Your payment status is PENDING until Annvitra verifies it. "
                "Please don't send sensitive banking details in this chat."
            )
        try:
            notify_owner(
                f"Payment method selected: CASH\nOrder: {order.order_code}\n"
                f"Amount: Rs. {order.total:g}\n"
                f"Owner: send CASHRECEIVED {order.order_code} after receiving cash."
            )
        except Exception as exc:
            print(f"Owner cash notification failed: {exc}")
        return (
            f"Cash on delivery selected for {order.order_code}.\n"
            "Your order is awaiting fulfilment. Payment will be marked received only after cash is collected."
        )

    if session.step == "awaiting_name":
        return "Please send your name."

    if lower == "cart":
        return cart_text(cart)

    if lower == "cancel":
        if cart:
            session.cart_json = "[]"
            session.step = "shopping"
            db.commit()
            return "Cart cleared. Your already placed orders are not affected."
        session.step = "shopping"
        db.commit()
        return "No cart items to clear. Send MENU to view available dishes."

    if lower == "done":
        if not cart:
            return "Your cart is empty. Add a dish first. Send MENU to see available dishes."
        session.step = "awaiting_name"
        db.commit()
        return "Let's prepare your order. What's your name?"

    if lower.startswith("remove "):
        try:
            number = int(lower.split(maxsplit=1)[1])
        except (ValueError, IndexError):
            return "Use REMOVE NUMBER, for example: remove 1."
        new_cart = [row for row in cart if row["menu_number"] != number]
        if len(new_cart) == len(cart):
            return "That item number isn't in your cart."
        save_cart(db, session, new_cart)
        return cart_text(new_cart)

    # If a user is mid-flow, don't interpret random text as a menu selection.
    if session.step != "shopping":
        return "Please follow the current step, or send HELP for commands."

    match = re.fullmatch(r"(\d+)\s+(\d+)", message)
    if match:
        number, quantity = map(int, match.groups())
        items = visible_menu()
        if number < 1 or number > len(items):
            return "Invalid dish number. Send MENU to see the current menu."
        if quantity < 1 or quantity > 50:
            return "Quantity must be between 1 and 50."
        item = items[number - 1][1]
        stock = available_stock(db, number, item)
        existing = next((row for row in cart if row["menu_number"] == number), None)
        already = int(existing["quantity"]) if existing else 0
        if quantity + already > stock:
            return f"Only {stock} of {item.name} are available, and you already have {already} in your cart."
        row = {
            "menu_number": number,
            "name": item.name,
            "price": item.price,
            "quantity": quantity,
        }
        if existing:
            existing["quantity"] += quantity
        else:
            cart.append(row)
        save_cart(db, session, cart)
        return f"Added {quantity} x {item.name}.\n\n{cart_text(cart)}"

    return "I didn't understand that. Send MENU to view dishes or HELP to see commands."
