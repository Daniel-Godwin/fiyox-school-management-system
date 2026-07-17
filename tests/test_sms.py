"""SMS go-live: phone-number normalization and the admin test-send.

The normalization is the piece that actually decides whether messages arrive.
Termii only accepts international MSISDN (2348…), but schools type 0803… — so a
wrong rule here means every SMS fails silently in production.
"""
import pytest

from app.services.notify import normalize_msisdn
from tests.conftest import headers


@pytest.mark.parametrize("raw,expected", [
    ("08031234567", "2348031234567"),        # the common case
    ("0803 123 4567", "2348031234567"),       # with spaces
    ("+2348031234567", "2348031234567"),      # already international, with +
    ("2348031234567", "2348031234567"),       # already international
    ("8031234567", "2348031234567"),          # bare 10-digit, no leading 0
    ("0809-876-5432", "2348098765432"),       # with dashes
])
def test_nigerian_numbers_become_termii_format(raw, expected):
    assert normalize_msisdn(raw) == expected


def test_normalization_is_idempotent():
    once = normalize_msisdn("08031234567")
    assert normalize_msisdn(once) == once


async def test_admin_can_send_a_test_sms_and_see_the_result(ctx):
    client, ids = ctx
    ah = await headers(client, "admin@gss-ikeja.ng", "admin123")

    r = await client.post("/api/notifications/test-sms", headers=ah,
                          json={"phone": "08031234567"})
    assert r.status_code == 200
    body = r.json()

    # no Termii key in tests -> mock provider, logged not delivered, but OK
    assert body["provider"] == "mock"
    assert body["sent_to"] == "2348031234567"     # normalized before sending
    assert body["ok"] is True
    assert "not configured" in body["note"]


async def test_test_sms_is_admin_only(ctx):
    client, ids = ctx
    th = await headers(client, "teacher@gss-ikeja.ng", "teach123")
    r = await client.post("/api/notifications/test-sms", headers=th,
                          json={"phone": "08031234567"})
    assert r.status_code == 403
