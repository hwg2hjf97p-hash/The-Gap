from datetime import datetime, timezone

from routers import subscriptions as subs

NOW = datetime(2026, 10, 20, 12, 0, tzinfo=timezone.utc)


def test_a_renewal_records_the_real_period_and_expiry():
    event = {"period_type": "normal", "product_id": "com.x.pro.monthly", "expiration_at_ms": 1795000000000}
    row = subs.mirror_payload("RENEWAL", event, "u1")
    assert row["is_active"] is True
    assert row["period_type"] == "NORMAL"
    assert row["product_id"] == "com.x.pro.monthly"
    assert row["expires_at"] is not None


def test_an_expiry_switches_access_off():
    assert subs.mirror_payload("EXPIRATION", {"product_id": "p"}, "u1")["is_active"] is False


def test_a_product_change_does_not_overwrite_the_period_or_expiry():
    """Someone ending their free week early switches products. That event carries the OLD
    product's trial values, which must not put a person who has started paying back on the free week."""
    event = {
        "period_type": "TRIAL", "product_id": "com.x.pro.monthly", "new_product_id": "com.x.pro.monthly.startnow",
        "expiration_at_ms": 1795000000000,
    }
    row = subs.mirror_payload("PRODUCT_CHANGE", event, "u1")
    assert "period_type" not in row and "expires_at" not in row
    assert row["product_id"] == "com.x.pro.monthly.startnow"
    assert row["is_active"] is True


def _subscriber(period="trial", expires="2026-11-19T12:00:00Z", product="com.x.pro.monthly"):
    return {
        "subscriber": {
            "entitlements": {"the_gap_premium": {"product_identifier": product, "expires_date": expires}},
            "subscriptions": {product: {"period_type": period, "expires_date": expires}},
        }
    }


def test_the_free_month_is_read_from_revenuecats_own_record():
    row = subs.parse_subscriber(_subscriber("trial"), "u1", NOW)
    assert row["is_active"] is True and row["period_type"] == "TRIAL"
    assert row["product_id"] == "com.x.pro.monthly"


def test_after_the_free_month_ends_early_the_person_is_paying():
    row = subs.parse_subscriber(_subscriber("normal", "2026-11-20T12:00:00Z", "com.x.pro.monthly.startnow"), "u1", NOW)
    assert row["is_active"] is True and row["period_type"] == "NORMAL"
    assert row["product_id"] == "com.x.pro.monthly.startnow"


def test_an_expired_entitlement_is_inactive():
    row = subs.parse_subscriber(_subscriber("normal", "2026-09-01T00:00:00Z"), "u1", NOW)
    assert row["is_active"] is False


def test_no_entitlement_means_not_active():
    row = subs.parse_subscriber({"subscriber": {"entitlements": {}, "subscriptions": {}}}, "u1", NOW)
    assert row["is_active"] is False and row["product_id"] is None
