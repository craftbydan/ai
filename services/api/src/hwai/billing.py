"""Pricing and the Stripe gateway (TEST mode only).

Stripe is reached only through `StripeGateway`, so tests replace it. Webhook signature checking is
local cryptography (no network).
"""

from dataclasses import dataclass
from typing import Any, Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session

from hwai import storage
from hwai.config import Settings, get_settings
from hwai.errors import ApiError
from hwai.models import Chat, Payment, Render


def billing_required(settings: Settings) -> bool:
    """BILLING=off skips payment, but only in ENV=dev (ignored in production)."""
    return not (settings.billing == "off" and settings.env == "dev")


def price_thb(pages: int, settings: Settings) -> int:
    """Price for a document of `pages` pages. Refuses more than MAX_PAGES_PER_DOCUMENT."""
    if pages < 1:
        raise ApiError(400, "no_pages", "This render has no pages.")
    if pages > settings.max_pages_per_document:
        raise ApiError(
            422,
            "too_many_pages",
            f"This document has {pages} pages; the limit is {settings.max_pages_per_document} "
            "pages per document.",
        )
    if settings.pricing_mode == "per_page":
        return settings.price_thb_per_page * pages
    return settings.price_thb_per_document


def render_page_count(render: Render) -> int:
    """Number of composed pages stored for a render (page 1 is preview_path)."""
    from hwai.routes.renders import page_path  # local import: routes import this module

    if render.preview_path is None:
        return 0
    n = 0
    while storage.absolute_path(page_path(render.preview_path, n + 1)).exists():
        n += 1
    return n


def is_paid(db: Session, chat_id: str, version: int) -> bool:
    return (
        db.scalar(
            select(Payment.id).where(
                Payment.chat_id == chat_id,
                Payment.render_version == version,
                Payment.status == "paid",
            )
        )
        is not None
    )


def checkout_hint(chat: Chat, version: int) -> dict[str, Any]:
    return {"checkout": {"method": "POST", "path": f"/chats/{chat.id}/checkout?version={version}"}}


@dataclass(frozen=True)
class CheckoutSession:
    id: str
    url: str


class Gateway(Protocol):
    def create_checkout_session(
        self,
        *,
        amount_thb: int,
        pages: int,
        chat_id: str,
        version: int,
        success_url: str,
        cancel_url: str,
    ) -> CheckoutSession: ...


class StripeGateway:
    """Real Stripe client. Needs STRIPE_SECRET_KEY (sk_test_...; checked at startup)."""

    def create_checkout_session(
        self,
        *,
        amount_thb: int,
        pages: int,
        chat_id: str,
        version: int,
        success_url: str,
        cancel_url: str,
    ) -> CheckoutSession:
        import stripe  # imported lazily so tests and dev without billing never load it

        key = get_settings().stripe_secret_key
        if not key:
            raise ApiError(
                503, "billing_not_configured", "Payments are not set up on this server yet."
            )
        try:
            params: dict[str, Any] = {
                "mode": "payment",
                "payment_method_types": ["promptpay"],
                "line_items": [
                    {
                        "quantity": 1,
                        "price_data": {
                            "currency": "thb",
                            "unit_amount": amount_thb * 100,  # satang
                            "product_data": {"name": f"Handwritten document ({pages} pages)"},
                        },
                    }
                ],
                "metadata": {"chat_id": chat_id, "version": str(version)},
                "success_url": success_url,
                "cancel_url": cancel_url,
            }
            session = stripe.checkout.Session.create(api_key=key, **params)
        except stripe.StripeError:
            raise ApiError(
                502, "billing_unavailable", "The payment service did not respond. Try again."
            ) from None
        if not session.url:
            raise ApiError(502, "billing_unavailable", "The payment service gave no checkout page.")
        return CheckoutSession(id=session.id, url=session.url)


def get_gateway() -> Gateway:
    """FastAPI dependency; tests override it with a fake (no real Stripe calls)."""
    return StripeGateway()


def verify_webhook(payload: bytes, signature: str | None) -> dict[str, Any]:
    """Verify the Stripe-Signature header against STRIPE_WEBHOOK_SECRET; return the event."""
    import stripe

    secret = get_settings().stripe_webhook_secret
    if not secret:
        raise ApiError(503, "billing_not_configured", "Webhook secret is not set up.")
    if not signature:
        raise ApiError(400, "invalid_signature", "Missing signature.")
    try:
        event = stripe.Webhook.construct_event(payload, signature, secret)
    except (ValueError, stripe.SignatureVerificationError):
        raise ApiError(400, "invalid_signature", "Signature could not be verified.") from None
    data: dict[str, Any] = event.to_dict() if hasattr(event, "to_dict") else dict(event)
    return data
