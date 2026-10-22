from datetime import datetime, timezone
from sqlalchemy import String, Integer, Float, DateTime, ForeignKey, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db import Base


def utcnow():
    return datetime.now(timezone.utc)


class CustomerSession(Base):
    __tablename__ = "customer_sessions"

    phone: Mapped[str] = mapped_column(String(40), primary_key=True)
    step: Mapped[str] = mapped_column(String(40), default="shopping")
    cart_json: Mapped[str] = mapped_column(Text, default="[]")
    customer_name: Mapped[str] = mapped_column(String(150), default="")
    delivery_phone: Mapped[str] = mapped_column(String(40), default="")
    address: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    order_code: Mapped[str] = mapped_column(String(30), unique=True, index=True)
    customer_phone: Mapped[str] = mapped_column(String(40), index=True)
    customer_name: Mapped[str] = mapped_column(String(150))
    delivery_phone: Mapped[str] = mapped_column(String(40))
    address: Mapped[str] = mapped_column(Text)
    total: Mapped[float] = mapped_column(Float)
    order_status: Mapped[str] = mapped_column(String(40), default="awaiting_payment")
    payment_method: Mapped[str] = mapped_column(String(20), default="")
    payment_status: Mapped[str] = mapped_column(String(30), default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    items: Mapped[list["OrderItem"]] = relationship(
        back_populates="order", cascade="all, delete-orphan"
    )


class OrderItem(Base):
    __tablename__ = "order_items"
    __table_args__ = (UniqueConstraint("order_id", "item_number", name="uq_order_item_number"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"), index=True)
    item_number: Mapped[int] = mapped_column(Integer)
    name: Mapped[str] = mapped_column(String(200))
    price: Mapped[float] = mapped_column(Float)
    quantity: Mapped[int] = mapped_column(Integer)

    order: Mapped["Order"] = relationship(back_populates="items")
