"""Checkout (per render version) and the Stripe webhook."""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, Request
from pydantic import BaseModel
from sqlalchemy import select

from hwai.billing import (
    Gateway,
    billing_required,
    get_gateway,
    is_paid,
    price_thb,
    render_page_count,
    verify_webhook,
)
from hwai.config import get_settings
from hwai.deps import DbDep, UserDep
from hwai.errors import ApiError
from hwai.models import Payment
from hwai.routes.chats import get_owned_chat
from hwai.routes.renders import get_owned_render, target_file

router = APIRouter()


class CheckoutOut(BaseModel):
    checkout_url: str
    amount_thb: int
    pages: int


@router.post("/chats/{chat_id}/checkout", response_model=CheckoutOut)
def start_checkout(
    chat_id: str,
    version: int,
    db: DbDep,
    user: UserDep,
    gateway: Annotated[Gateway, Depends(get_gateway)],
) -> CheckoutOut:
    settings = get_settings()
    chat = get_owned_chat(db, user, chat_id)
    render = get_owned_render(db, chat, version)
    target_file(db, chat)  # safety refusals still apply before anyone is asked to pay
    if not billing_required(settings):
        raise ApiError(409, "billing_off", "Payment is switched off in this environment.")
    if is_paid(db, chat.id, version):
        raise ApiError(409, "already_paid", "This version is already paid for.")
    pages = render_page_count(render)
    amount = price_thb(pages, settings)
    base = f"{settings.web_base_url}/chats/{chat.id}"
    session = gateway.create_checkout_session(
        amount_thb=amount,
        pages=pages,
        chat_id=chat.id,
        version=version,
        success_url=f"{base}?paid=1&version={version}",
        cancel_url=f"{base}?canceled=1",
    )
    db.add(
        Payment(
            user_id=user.id,
            chat_id=chat.id,
            render_version=version,
            stripe_session_id=session.id,
            status="pending",
            amount_thb=amount,
            pages=pages,
        )
    )
    db.commit()
    return CheckoutOut(checkout_url=session.url, amount_thb=amount, pages=pages)


_PAID_EVENTS = {"checkout.session.completed", "checkout.session.async_payment_succeeded"}


@router.post("/billing/webhook")
async def webhook(
    request: Request,
    db: DbDep,
    stripe_signature: Annotated[str | None, Header()] = None,
) -> dict[str, bool]:
    event = verify_webhook(await request.body(), stripe_signature)
    if event.get("type") not in _PAID_EVENTS:
        return {"received": True}
    obj: dict[str, Any] = event.get("data", {}).get("object", {})
    if obj.get("payment_status") != "paid":
        return {"received": True}  # e.g. PromptPay QR shown but not yet paid
    payment = db.scalar(select(Payment).where(Payment.stripe_session_id == obj.get("id")))
    if payment is None or payment.status == "paid":
        return {"received": True}  # unknown session, or a repeat delivery: nothing to change
    total = obj.get("amount_total")
    if isinstance(total, int) and total != payment.amount_thb * 100:
        return {"received": True}  # amount does not match what we asked for: never unlock
    payment.status = "paid"
    db.commit()
    return {"received": True}
