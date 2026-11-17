"""Prompt 11: accounts, rate limit, ownership via real cookies, billing (mocked Stripe)."""

import hashlib
import hmac
import json
import time

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from hwai import storage
from hwai.billing import CheckoutSession, get_gateway
from hwai.config import get_settings
from hwai.db import new_session
from hwai.main import create_app
from hwai.models import Chat, Payment, Render

from .conftest import FIXTURES, PASSWORD, new_client, signup
from .test_layout import _body

WEBHOOK_SECRET = "whsec_test_only_secret"


@pytest.fixture
def real_auth(monkeypatch: pytest.MonkeyPatch) -> None:
    """No dev stub: every request needs a real session cookie."""
    monkeypatch.setenv("DEV_USER", "0")
    get_settings.cache_clear()


@pytest.fixture
def billing_on(monkeypatch: pytest.MonkeyPatch, real_auth: None) -> None:
    monkeypatch.setenv("BILLING", "on")
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_dummy_never_used")
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", WEBHOOK_SECRET)
    get_settings.cache_clear()


class FakeGateway:
    """Stands in for Stripe: no network, records what it was asked to create."""

    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def create_checkout_session(self, **kw: object) -> CheckoutSession:
        self.calls.append(kw)
        n = len(self.calls)
        return CheckoutSession(
            id=f"cs_test_{n}", url=f"https://checkout.stripe.test/pay/cs_test_{n}"
        )


def _app_with(gateway: FakeGateway) -> TestClient:
    app = create_app()
    app.dependency_overrides[get_gateway] = lambda: gateway
    return TestClient(app, raise_server_exceptions=False)


def _event(session_id: str, amount_thb: int = 20, paid: bool = True) -> bytes:
    return json.dumps(
        {
            "id": "evt_test_1",
            "object": "event",
            "type": "checkout.session.completed",
            "data": {
                "object": {
                    "id": session_id,
                    "object": "checkout.session",
                    "payment_status": "paid" if paid else "unpaid",
                    "amount_total": amount_thb * 100,
                }
            },
        }
    ).encode()


def _sign(payload: bytes, secret: str = WEBHOOK_SECRET) -> dict[str, str]:
    ts = int(time.time())
    sig = hmac.new(secret.encode(), f"{ts}.".encode() + payload, hashlib.sha256).hexdigest()
    return {"Stripe-Signature": f"t={ts},v1={sig}", "Content-Type": "application/json"}


def _chat_with_render(client: TestClient) -> tuple[str, int]:
    chat_id = client.post("/chats").json()["id"]
    with (FIXTURES / "card.pdf").open("rb") as f:
        assert (
            client.post(f"/chats/{chat_id}/files", files={"file": ("c.pdf", f)}).status_code == 201
        )
    res = client.post(f"/chats/{chat_id}/render", json=_body("Happy birthday!"))
    assert res.status_code == 200, res.text
    return chat_id, res.json()["version"]


def _payments() -> list[Payment]:
    with new_session() as db:
        return list(db.scalars(select(Payment)).all())


# --- accounts -----------------------------------------------------------------------------


def test_signup_me_logout_login_cycle(real_auth: None) -> None:
    client = new_client()
    assert client.get("/auth/me").status_code == 401
    res = client.post("/auth/signup", json={"email": "Ann@Example.com", "password": PASSWORD})
    assert res.status_code == 201
    cookie = res.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=lax" in cookie
    assert client.get("/auth/me").json()["email"] == "ann@example.com"
    assert client.post("/auth/logout").status_code == 204
    assert client.get("/auth/me").status_code == 401
    assert (
        client.post(
            "/auth/login", json={"email": "ann@example.com", "password": PASSWORD}
        ).status_code
        == 200
    )
    assert client.get("/auth/me").json()["email"] == "ann@example.com"
    with new_session() as db:
        from hwai.models import User

        stored = db.scalar(select(User.password_hash).where(User.email == "ann@example.com"))
    assert stored and stored.startswith("$argon2") and PASSWORD not in stored


def test_signup_validation(real_auth: None) -> None:
    client = new_client()
    assert (
        client.post("/auth/signup", json={"email": "nope", "password": PASSWORD}).status_code == 422
    )
    assert (
        client.post(
            "/auth/signup", json={"email": "a@example.com", "password": "short"}
        ).status_code
        == 422
    )
    signup(client, "dup@example.com")
    again = new_client().post(
        "/auth/signup", json={"email": "dup@example.com", "password": PASSWORD}
    )
    assert again.status_code == 409


def test_wrong_password_gives_generic_error(real_auth: None) -> None:
    signup(new_client(), "ann@example.com")
    client = new_client()
    wrong = client.post(
        "/auth/login", json={"email": "ann@example.com", "password": "not the password"}
    )
    unknown = client.post(
        "/auth/login", json={"email": "nobody@example.com", "password": "not the password"}
    )
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json() == unknown.json()
    assert wrong.json()["error"]["code"] == "invalid_credentials"


def test_sixth_failed_login_is_rate_limited(real_auth: None) -> None:
    signup(new_client(), "ann@example.com")
    client = new_client()
    bad = {"email": "ann@example.com", "password": "not the password"}
    assert [client.post("/auth/login", json=bad).status_code for _ in range(5)] == [401] * 5
    sixth = client.post("/auth/login", json=bad)
    assert sixth.status_code == 429 and sixth.json()["error"]["code"] == "rate_limited"
    # Blocked even with the right password, but only for this email.
    good = {"email": "ann@example.com", "password": PASSWORD}
    assert client.post("/auth/login", json=good).status_code == 429
    signup(new_client(), "bob@example.com")
    assert (
        client.post(
            "/auth/login", json={"email": "bob@example.com", "password": PASSWORD}
        ).status_code
        == 200
    )


def test_user_b_cannot_read_user_a_chat(real_auth: None) -> None:
    a = signup(new_client(), "a@example.com")
    chat_id = a.post("/chats").json()["id"]
    assert a.get(f"/chats/{chat_id}").status_code == 200
    b = signup(new_client(), "b@example.com")
    assert b.get(f"/chats/{chat_id}").status_code == 404
    assert b.get("/chats").json() == []
    anon = new_client()
    assert anon.get(f"/chats/{chat_id}").status_code == 401


def test_tampered_cookie_is_rejected(real_auth: None) -> None:
    client = signup(new_client(), "a@example.com")
    token = client.cookies["hwai_session"]
    client.cookies.clear()
    client.cookies.set("hwai_session", token + "x")
    assert client.get("/auth/me").status_code == 401


# --- startup guards -----------------------------------------------------------------------


def test_live_stripe_key_fails_startup(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_live_x")
    get_settings.cache_clear()
    with pytest.raises(RuntimeError, match="sk_test_"):
        create_app()


def test_placeholder_keys_count_as_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("STRIPE_SECRET_KEY", "<YOUR_STRIPE_TEST_SECRET_KEY>")
    monkeypatch.setenv("SECRET_KEY", "<GENERATE_A_RANDOM_32_BYTE_STRING>")
    get_settings.cache_clear()
    assert get_settings().stripe_secret_key == "" and get_settings().secret_key == ""
    create_app()  # ENV=dev: allowed (random dev key)


def test_missing_secret_key_fails_outside_dev(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ENV", "production")
    get_settings.cache_clear()
    with pytest.raises(RuntimeError, match="SECRET_KEY"):
        create_app()
    monkeypatch.setenv("SECRET_KEY", "x" * 32)
    get_settings.cache_clear()
    create_app()


def test_billing_off_and_dev_user_ignored_in_production(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ENV", "production")
    monkeypatch.setenv("SECRET_KEY", "x" * 32)
    get_settings.cache_clear()
    client = new_client()
    assert client.get("/auth/me").status_code == 401  # DEV_USER=1 ignored
    from hwai.billing import billing_required

    assert billing_required(get_settings())  # BILLING=off ignored


def test_admin_cost_dev_only(data_dir, monkeypatch: pytest.MonkeyPatch) -> None:  # type: ignore[no-untyped-def]
    client = new_client()
    assert client.get("/admin/cost").status_code == 404
    (data_dir / "cost_report.json").write_text(json.dumps({"thb_per_page": 0.42}))
    assert client.get("/admin/cost").json()["thb_per_page"] == 0.42
    monkeypatch.setenv("ENV", "production")
    monkeypatch.setenv("SECRET_KEY", "x" * 32)
    get_settings.cache_clear()
    assert new_client().get("/admin/cost").status_code == 404


# --- billing ------------------------------------------------------------------------------


def test_checkout_refuses_eleven_pages(billing_on: None) -> None:
    gw = FakeGateway()
    client = signup(_app_with(gw), "a@example.com")
    chat_id, v = _chat_with_render(client)
    with new_session() as db:
        render = db.scalar(select(Render).where(Render.chat_id == chat_id))
        assert render and render.preview_path
        png = storage.read_file(render.preview_path)
        for n in range(2, 12):
            storage.write_file(render.preview_path.replace(".png", f"-p{n}.png"), png)
    res = client.post(f"/chats/{chat_id}/checkout?version={v}")
    assert res.status_code == 422 and res.json()["error"]["code"] == "too_many_pages"
    assert gw.calls == [] and _payments() == []


def test_checkout_prices_and_per_page_mode(
    billing_on: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    gw = FakeGateway()
    client = signup(_app_with(gw), "a@example.com")
    chat_id, v = _chat_with_render(client)
    res = client.post(f"/chats/{chat_id}/checkout?version={v}")
    assert res.status_code == 200
    assert res.json()["amount_thb"] == 20 and res.json()["checkout_url"].startswith("https://")
    monkeypatch.setenv("PRICING_MODE", "per_page")
    get_settings.cache_clear()
    res = client.post(f"/chats/{chat_id}/checkout?version={v}")
    assert res.json()["amount_thb"] == 1 * res.json()["pages"] == 1
    assert [p.amount_thb for p in _payments()] == [20, 1]
    assert client.post(f"/chats/{chat_id}/checkout?version=99").status_code == 404
    other = signup(_app_with(gw), "b@example.com")
    assert other.post(f"/chats/{chat_id}/checkout?version={v}").status_code == 404


def test_webhook_bad_signature_changes_nothing(billing_on: None) -> None:
    client = signup(_app_with(FakeGateway()), "a@example.com")
    chat_id, v = _chat_with_render(client)
    client.post(f"/chats/{chat_id}/checkout?version={v}")
    payload = _event("cs_test_1")
    forged = _sign(payload, secret="whsec_wrong")
    assert client.post("/billing/webhook", content=payload, headers=forged).status_code == 400
    assert client.post("/billing/webhook", content=payload).status_code == 400
    assert [p.status for p in _payments()] == ["pending"]


def test_webhook_good_signature_marks_paid_once(billing_on: None) -> None:
    client = signup(_app_with(FakeGateway()), "a@example.com")
    chat_id, v = _chat_with_render(client)
    client.post(f"/chats/{chat_id}/checkout?version={v}")
    payload = _event("cs_test_1")
    for _ in range(2):  # Stripe may deliver the same event twice
        res = client.post("/billing/webhook", content=payload, headers=_sign(payload))
        assert res.status_code == 200
    rows = _payments()
    assert [(p.status, p.amount_thb) for p in rows] == [("paid", 20)]
    with new_session() as db:
        assert db.scalar(select(func.count()).select_from(Payment)) == 1
    # Wrong amount or unpaid status never unlocks.
    client.post(f"/chats/{chat_id}/checkout?version=1")  # already paid -> 409, no new row
    assert len(_payments()) == 1


def test_webhook_amount_mismatch_or_unpaid_does_not_unlock(billing_on: None) -> None:
    client = signup(_app_with(FakeGateway()), "a@example.com")
    chat_id, v = _chat_with_render(client)
    client.post(f"/chats/{chat_id}/checkout?version={v}")
    for payload in (_event("cs_test_1", amount_thb=1), _event("cs_test_1", paid=False)):
        assert (
            client.post("/billing/webhook", content=payload, headers=_sign(payload)).status_code
            == 200
        )
    assert [p.status for p in _payments()] == ["pending"]


def test_export_402_before_payment_200_after(billing_on: None) -> None:
    client = signup(_app_with(FakeGateway()), "a@example.com")
    chat_id, v = _chat_with_render(client)
    res = client.post(f"/chats/{chat_id}/export?version={v}&format=pdf")
    assert res.status_code == 402
    err = res.json()["error"]
    assert err["code"] == "payment_required"
    assert err["checkout"]["path"] == f"/chats/{chat_id}/checkout?version={v}"
    client.post(f"/chats/{chat_id}/checkout?version={v}")
    assert client.post(f"/chats/{chat_id}/export?version={v}&format=pdf").status_code == 402
    payload = _event("cs_test_1")
    assert (
        client.post("/billing/webhook", content=payload, headers=_sign(payload)).status_code == 200
    )
    paid = client.post(f"/chats/{chat_id}/export?version={v}&format=pdf")
    assert paid.status_code == 200 and paid.content.startswith(b"%PDF")
    assert b"AI-generated" in paid.content or paid.headers["content-type"] == "application/pdf"
    # A new render version needs its own payment.
    v2 = client.post(f"/chats/{chat_id}/render", json=_body("Another", seed=2)).json()["version"]
    assert client.post(f"/chats/{chat_id}/export?version={v2}&format=pdf").status_code == 402


def test_billing_off_skips_payment_in_dev(client: TestClient) -> None:
    with new_session() as db:
        assert db.scalar(select(func.count()).select_from(Chat)) == 0
    chat_id, v = _chat_with_render(client)
    assert client.post(f"/chats/{chat_id}/export?version={v}&format=pdf").status_code == 200


def test_stripe_gateway_sends_promptpay_thb_satang(
    billing_on: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    import stripe

    from hwai.billing import StripeGateway

    seen: dict[str, object] = {}

    def fake_create(**params: object) -> object:
        seen.update(params)
        return type("S", (), {"id": "cs_test_9", "url": "https://checkout.stripe.test/x"})()

    monkeypatch.setattr(stripe.checkout.Session, "create", fake_create)
    out = StripeGateway().create_checkout_session(
        amount_thb=20,
        pages=2,
        chat_id="c1",
        version=3,
        success_url="http://w/ok",
        cancel_url="http://w/no",
    )
    assert out.id == "cs_test_9"
    assert seen["payment_method_types"] == ["promptpay"] and seen["mode"] == "payment"
    item = seen["line_items"][0]["price_data"]  # type: ignore[index]
    assert item["currency"] == "thb" and item["unit_amount"] == 2000
    assert seen["api_key"] == "sk_test_dummy_never_used"
