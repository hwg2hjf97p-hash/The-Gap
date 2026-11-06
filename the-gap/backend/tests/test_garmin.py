import asyncio
import os
import re

import pytest
from fastapi import BackgroundTasks, HTTPException
from urllib.parse import parse_qs, urlparse

from routers import connect
from routers import garmin as route
from sync import garmin_sync
from utils import garmin as g
from utils import provider_caps


def run(coro):
    return asyncio.run(coro)


@pytest.fixture(autouse=True)
def garmin_env(monkeypatch):
    monkeypatch.setenv("GARMIN_CLIENT_ID", "client-id")
    monkeypatch.setenv("GARMIN_CLIENT_SECRET", "client-secret")
    monkeypatch.setenv("GARMIN_PUSH_TOKEN", "abcdefghijklmnopqrstuvwxyz012345")
    monkeypatch.delenv("GARMIN_AI_ALLOWED", raising=False)
    monkeypatch.delenv("GARMIN_USER_CAP", raising=False)


# ── sign-in security (PKCE) ──────────────────────────────────────────────────
def test_the_challenge_matches_the_published_pkce_example():
    # RFC 7636, appendix B
    assert g.pkce_challenge("dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk") == "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM"


def test_the_verifier_fits_garmins_rules_and_depends_on_both_secret_and_nonce():
    v = g.pkce_verifier(b"server-secret", "nonce-1")
    assert 43 <= len(v) <= 128 and re.fullmatch(r"[A-Za-z0-9\-._~]+", v)
    assert v == g.pkce_verifier(b"server-secret", "nonce-1")
    assert v != g.pkce_verifier(b"server-secret", "nonce-2")
    assert v != g.pkce_verifier(b"another-secret", "nonce-1")


def test_the_sign_in_address_has_pkce_and_no_scope_and_its_challenge_matches_the_state():
    url = connect._build_auth_url("garmin", "user-1", "mobile")
    parsed = urlparse(url)
    q = {k: v[0] for k, v in parse_qs(parsed.query).items()}
    assert url.startswith("https://connect.garmin.com/oauth2Confirm?")
    assert q["response_type"] == "code" and q["client_id"] == "client-id" and q["code_challenge_method"] == "S256"
    assert "scope" not in q
    assert q["redirect_uri"].endswith("/connect/garmin/callback")
    state = connect._consume_state(q["state"])
    assert state and state["user_id"] == "user-1" and state["provider"] == "garmin" and state["nonce"]
    assert q["code_challenge"] == g.pkce_challenge(g.pkce_verifier(connect._STATE_SECRET, state["nonce"]))


def test_other_providers_state_has_no_nonce_and_still_works():
    token = connect._store_state("", "user-2", "whoop", "web")
    assert connect._consume_state(token) == {"user_id": "user-2", "provider": "whoop", "platform": "web", "nonce": ""}


def test_the_old_address_based_start_is_refused_for_garmin():
    with pytest.raises(HTTPException) as err:
        run(connect.start_oauth("garmin", "someone-else", "web"))
    assert err.value.status_code == 403


# ── the address Garmin pushes to ─────────────────────────────────────────────
def test_only_the_secret_address_is_accepted(monkeypatch):
    assert g.push_token_ok("abcdefghijklmnopqrstuvwxyz012345")
    assert not g.push_token_ok("abcdefghijklmnopqrstuvwxyz012346")
    assert not g.push_token_ok("")
    monkeypatch.setenv("GARMIN_PUSH_TOKEN", "short")
    assert g.push_token() == "" and not g.push_token_ok("short")
    monkeypatch.delenv("GARMIN_PUSH_TOKEN")
    assert not g.push_token_ok("")


def test_the_address_to_paste_into_garmins_portal():
    assert g.push_url("https://example.test/", "dailies") == "https://example.test/garmin/push/abcdefghijklmnopqrstuvwxyz012345/dailies"


# ── reading Garmin's records ─────────────────────────────────────────────────
DAILY = {
    "userId": "gu1", "summaryId": "d1", "calendarDate": "2026-11-04", "steps": 8123, "restingHeartRateInBeatsPerMinute": 52,
    "activeKilocalories": 410, "averageStressLevel": 31, "bodyBatteryChargedValue": 64, "distanceInMeters": 6000.5, "timeOffsetHeartRateSamples": {"15": 70},
}


def test_a_daily_summary_keeps_only_what_we_use():
    user, day, patch = g.ingest("dailies", DAILY)
    assert (user, day) == ("gu1", "2026-11-04")
    assert patch == {"steps": 8123, "resting_hr": 52, "active_energy": 410, "stress_avg": 31, "body_battery_charged": 64}


def test_no_stress_figure_is_left_out_and_missing_numbers_are_not_made_up():
    _, _, patch = g.ingest("dailies", {**DAILY, "averageStressLevel": -1, "steps": None})
    assert "stress_avg" not in patch and "steps" not in patch


@pytest.mark.parametrize("bad", [{"calendarDate": "2026-11-04"}, {"userId": "u"}, {"userId": "u", "calendarDate": "04/11/2026"}, "text", None])
def test_unusable_records_are_ignored(bad):
    assert g.ingest("dailies", bad) is None


def test_summaries_we_do_not_keep_are_ignored():
    assert g.ingest("epochs", DAILY) is None and g.ingest("stressDetails", DAILY) is None


SLEEP = {
    "userId": "gu1", "summaryId": "s1", "calendarDate": "2026-11-05", "durationInSeconds": 27000, "deepSleepDurationInSeconds": 5400,
    "lightSleepDurationInSeconds": 14400, "remSleepInSeconds": 7200, "awakeDurationInSeconds": 900,
    "overallSleepScore": {"value": 87, "qualifierKey": "GOOD"}, "validation": "ENHANCED_FINAL",
}


def test_sleep_is_kept_in_minutes_with_garmins_own_score_wording():
    _, day, patch = g.ingest("sleeps", SLEEP)
    assert day == "2026-11-05"
    assert patch == {"sleeps": {"s1": {"total_min": 450.0, "deep_min": 90.0, "light_min": 240.0, "rem_min": 120.0, "awake_min": 15.0, "score": 87, "score_label": "GOOD"}}}


def test_an_unknown_score_label_is_dropped_rather_than_invented():
    _, _, patch = g.ingest("sleeps", {**SLEEP, "overallSleepScore": {"value": 70, "qualifierKey": "AMAZING"}})
    assert "score_label" not in patch["sleeps"]["s1"] and patch["sleeps"]["s1"]["score"] == 70


def test_a_sleep_without_an_id_is_ignored():
    assert g.ingest("sleeps", {**SLEEP, "summaryId": ""}) is None


def test_hrv_is_the_nights_average():
    assert g.ingest("hrv", {"userId": "gu1", "calendarDate": "2026-11-05", "lastNightAvg": 44, "lastNight5MinHigh": 72, "hrvValues": {"300": 32}}) == ("gu1", "2026-11-05", {"hrv": 44})


# ── filing them ──────────────────────────────────────────────────────────────
def test_a_newer_daily_replaces_the_older_and_sleeps_sit_side_by_side():
    day = g.merge_day(None, {"steps": 1000, "resting_hr": 55})
    day = g.merge_day(day, {"steps": 8123})
    assert day == {"steps": 8123, "resting_hr": 55}
    day = g.merge_day(day, {"sleeps": {"nap": {"total_min": 20.0}}})
    day = g.merge_day(day, {"sleeps": {"night": {"total_min": 450.0}}})
    assert set(day["sleeps"]) == {"nap", "night"}
    day = g.merge_day(day, {"sleeps": {"night": {"total_min": 460.0}}})  # Garmin's update of the same night
    assert day["sleeps"]["night"]["total_min"] == 460.0 and len(day["sleeps"]) == 2


def test_the_main_sleep_is_the_longest_one():
    day = {"sleeps": {"nap": {"total_min": 20.0}, "night": {"total_min": 450.0}}}
    assert g.main_sleep(day)["total_min"] == 450.0 and g.main_sleep({}) is None


def test_the_app_sees_a_day_with_garmins_wording_for_the_sleep_score():
    view = g.day_view("2026-11-05", {"steps": 5000, "sleeps": {"s1": {"total_min": 450.0, "score": 87, "score_label": "GOOD"}}})
    assert view["steps"] == 5000 and view["sleep"]["score_label"] == "GOOD" and view["resting_hr"] is None


def test_the_engines_columns_come_from_stored_days():
    rows = [
        {"local_date": "2026-11-04", "data": {"steps": 8000, "resting_hr": 52, "active_energy": 400, "hrv": 44, "sleeps": {"s": {"total_min": 450.0, "deep_min": 90.0, "score": 87}}}},
        {"local_date": "2026-11-03", "data": {}},
    ]
    assert g.frame_rows(rows) == {"2026-11-04": {"steps": 8000, "resting_hr": 52, "active_energy": 400, "hrv": 44, "sleep_total_min": 450.0, "sleep_deep_min": 90.0, "sleep_score": 87}}


def test_a_whole_push_is_read_and_junk_in_it_is_skipped():
    payload = {"dailies": [DAILY, {"userId": "x"}, "junk"]}
    assert len(g.parse_push("dailies", payload)) == 1
    assert g.parse_push("dailies", {"sleeps": []}) == [] and g.parse_push("dailies", None) == [] and g.parse_push("epochs", payload) == []


def test_disconnect_and_permission_notices_are_read():
    assert g.parse_deregistrations({"deregistrations": [{"userId": "a"}, {"nope": 1}]}) == ["a"]
    assert g.parse_permission_changes({"userPermissionsChange": [{"userId": "a", "permissions": ["ACTIVITY_EXPORT"]}]}) == [("a", ["ACTIVITY_EXPORT"])]
    assert g.parse_deregistrations("x") == [] and g.parse_permission_changes(None) == []


# ── the AI switch (Garmin licence, section 15.11) ────────────────────────────
def test_garmin_numbers_stay_out_of_the_engine_unless_it_is_switched_on(monkeypatch):
    assert g.engine_allowed() is False
    monkeypatch.setenv("GARMIN_AI_ALLOWED", "false")
    assert g.engine_allowed() is False
    monkeypatch.setenv("GARMIN_AI_ALLOWED", "true")
    assert g.engine_allowed() is True


def test_the_sync_only_reads_garmin_numbers_behind_that_switch():
    path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "sync", "daily_sync.py")
    with open(path, encoding="utf-8") as handle:
        source = handle.read()
    branch = source[source.index('elif provider == "garmin":'):]
    branch = branch[: branch.index('elif provider == "polar":')]
    assert "garmin_utils.engine_allowed()" in branch and branch.index("engine_allowed()") < branch.index("fetch_garmin_data")


def test_the_engine_frame_is_built_from_stored_days(monkeypatch):
    async def rows(user_id, days):
        return [{"local_date": "2026-11-04", "data": {"steps": 8000, "hrv": 44}}, {"local_date": "2026-11-05", "data": {"steps": 9000}}]

    monkeypatch.setattr(route, "recent_rows", rows)
    df = run(garmin_sync.fetch_garmin_data("u1"))
    assert list(df.index.strftime("%Y-%m-%d")) == ["2026-11-04", "2026-11-05"]
    assert df["hrv"].iloc[0] == 44 and df["steps"].iloc[1] == 9000


# ── the member limit ─────────────────────────────────────────────────────────
def test_garmin_defaults_to_the_thousand_people_it_approved_and_the_limit_can_change(monkeypatch):
    assert provider_caps.cap_for("garmin") == 1000 and "garmin" in provider_caps.CAPPED_PROVIDERS
    monkeypatch.setenv("GARMIN_USER_CAP", "250")
    assert provider_caps.cap_for("garmin") == 250


# ── the sign-up after Garmin sends the person back ───────────────────────────
class Calls:
    def __init__(self):
        self.saved = None
        self.linked = None
        self.deregistered = False


@pytest.fixture
def garmin_calls(monkeypatch):
    calls = Calls()

    async def exchange(code, verifier, redirect_uri):
        calls.verifier = verifier
        return {"access_token": "access-1", "refresh_token": "refresh-1", "expires_in": 86400}

    async def user_id(access):
        return "garmin-user-1"

    async def permissions(access):
        return calls.permissions

    async def deregister(access):
        calls.deregistered = True
        return True

    async def save(**kw):
        calls.saved = kw

    async def link(user, garmin_user):
        calls.linked = (user, garmin_user)

    calls.permissions = ["HEALTH_EXPORT", "ACTIVITY_EXPORT"]
    monkeypatch.setattr(g, "exchange_code", exchange)
    monkeypatch.setattr(g, "fetch_user_id", user_id)
    monkeypatch.setattr(g, "fetch_permissions", permissions)
    monkeypatch.setattr(g, "delete_registration", deregister)
    monkeypatch.setattr(connect, "_save_tokens_rest", save)
    monkeypatch.setattr(route, "link_user", link)
    return calls


def test_a_successful_sign_up_proves_pkce_saves_the_login_and_links_the_person(garmin_calls):
    resp = run(connect._garmin_callback("user-1", "mobile", "the-code", "nonce-x"))
    assert "success=true" in resp.headers["location"] and "provider=garmin" in resp.headers["location"]
    assert garmin_calls.verifier == g.pkce_verifier(connect._STATE_SECRET, "nonce-x")
    assert garmin_calls.saved["user_id"] == "user-1" and garmin_calls.saved["provider"] == "garmin" and garmin_calls.saved["refresh_token"] == "refresh-1"
    assert garmin_calls.linked == ("user-1", "garmin-user-1") and not garmin_calls.deregistered


def test_someone_who_declined_health_data_is_not_connected_and_their_registration_is_taken_back(garmin_calls):
    garmin_calls.permissions = ["ACTIVITY_EXPORT"]
    resp = run(connect._garmin_callback("user-1", "mobile", "the-code", "nonce-x"))
    assert "error=permission_missing" in resp.headers["location"]
    assert garmin_calls.deregistered and garmin_calls.saved is None and garmin_calls.linked is None


def test_a_failed_exchange_or_missing_nonce_connects_nobody(monkeypatch, garmin_calls):
    resp = run(connect._garmin_callback("user-1", "mobile", "code", ""))
    assert "error=token_exchange_failed" in resp.headers["location"]

    async def boom(*a, **k):
        raise RuntimeError("garmin said no")

    monkeypatch.setattr(g, "exchange_code", boom)
    resp = run(connect._garmin_callback("user-1", "mobile", "code", "nonce"))
    assert "error=token_exchange_failed" in resp.headers["location"] and garmin_calls.saved is None


# ── disconnecting (Garmin's licence: the registration must go too) ───────────
def test_disconnecting_removes_the_registration_with_a_fresh_login_and_then_the_numbers(monkeypatch):
    seen = {}

    async def refresh(token):
        seen["refreshed_with"] = token
        return {"access_token": "fresh-access", "refresh_token": "fresh-refresh"}

    async def deregister(access):
        seen["deregistered_with"] = access
        return True

    async def forget(user_id):
        seen["forgot"] = user_id

    monkeypatch.setattr(g, "refresh_tokens", refresh)
    monkeypatch.setattr(g, "delete_registration", deregister)
    monkeypatch.setattr(route, "forget_data", forget)
    run(route.disconnect_user("u1", {"access_token": "old", "refresh_token": "r1", "expires_at": 1}))
    assert seen == {"refreshed_with": "r1", "deregistered_with": "fresh-access", "forgot": "u1"}


def test_the_numbers_are_removed_even_if_garmin_cannot_be_reached(monkeypatch):
    forgot = []

    async def refresh(token):
        raise RuntimeError("offline")

    async def forget(user_id):
        forgot.append(user_id)

    monkeypatch.setattr(g, "refresh_tokens", refresh)
    monkeypatch.setattr(route, "forget_data", forget)
    run(route.disconnect_user("u1", {"access_token": "", "refresh_token": "r1", "expires_at": 0}))
    assert forgot == ["u1"]


def test_account_deletion_removes_garmin_data_with_the_rest():
    from routers import account

    assert "garmin_links" in account.USER_DATA_TABLES and "garmin_daily" in account.USER_DATA_TABLES
    assert "garmin_daily" not in account.TABLES  # only the original tables are re-pointed when an old install is claimed


# ── Garmin's pushes ──────────────────────────────────────────────────────────
class FakeRequest:
    def __init__(self, body):
        self._body = body

    async def json(self):
        if isinstance(self._body, Exception):
            raise self._body
        return self._body


def test_a_push_to_the_wrong_address_or_kind_is_a_plain_404():
    for token, kind in (("wrong-token-wrong-token-wrong-token", "dailies"), ("abcdefghijklmnopqrstuvwxyz012345", "epochs")):
        with pytest.raises(HTTPException) as err:
            run(route.receive_push(token, kind, FakeRequest({}), BackgroundTasks()))
        assert err.value.status_code == 404


def test_a_good_push_is_answered_200_and_filed_afterwards():
    background = BackgroundTasks()
    resp = run(route.receive_push("abcdefghijklmnopqrstuvwxyz012345", "dailies", FakeRequest({"dailies": [DAILY]}), background))
    assert resp.status_code == 200 and len(background.tasks) == 1
    assert background.tasks[0].func is route.process_push and background.tasks[0].args[0] == "dailies"


def test_a_push_that_is_not_json_is_still_answered_200():
    background = BackgroundTasks()
    resp = run(route.receive_push("abcdefghijklmnopqrstuvwxyz012345", "sleeps", FakeRequest(ValueError("not json")), background))
    assert resp.status_code == 200 and background.tasks[0].args[1] is None


@pytest.fixture
def store(monkeypatch):
    days: dict = {}
    people = {"gu1": "user-1"}

    async def user_for(garmin_user):
        return people.get(garmin_user)

    async def load(client, user_id, local_date):
        return days.get((user_id, local_date))

    async def save(client, user_id, local_date, data):
        days[(user_id, local_date)] = data

    monkeypatch.setattr(route, "user_for", user_for)
    monkeypatch.setattr(route, "_load_day", load)
    monkeypatch.setattr(route, "_save_day", save)
    return days


def test_pushed_numbers_are_filed_for_the_right_person_and_updates_replace_earlier_ones(store):
    run(route.process_push("dailies", {"dailies": [DAILY, {**DAILY, "userId": "stranger"}]}))
    assert store == {("user-1", "2026-11-04"): {"steps": 8123, "resting_hr": 52, "active_energy": 410, "stress_avg": 31, "body_battery_charged": 64}}
    run(route.process_push("dailies", {"dailies": [{**DAILY, "steps": 9500}]}))
    assert store[("user-1", "2026-11-04")]["steps"] == 9500
    run(route.process_push("sleeps", {"sleeps": [SLEEP]}))
    run(route.process_push("hrv", {"hrv": [{"userId": "gu1", "calendarDate": "2026-11-05", "lastNightAvg": 44}]}))
    assert store[("user-1", "2026-11-05")]["hrv"] == 44 and store[("user-1", "2026-11-05")]["sleeps"]["s1"]["score"] == 87


def test_a_disconnect_notice_switches_the_person_off(monkeypatch, store):
    off = []

    async def turn_off(user_id):
        off.append(user_id)

    monkeypatch.setattr(route, "_turn_off", turn_off)
    run(route.process_push("deregistrations", {"deregistrations": [{"userId": "gu1"}, {"userId": "stranger"}]}))
    assert off == ["user-1"]


def test_someone_who_stops_sharing_health_data_loses_their_stored_numbers(monkeypatch, store):
    cleared = []

    async def clear(user_id):
        cleared.append(user_id)

    monkeypatch.setattr(route, "_clear_days", clear)
    run(route.process_push("permissions", {"userPermissionsChange": [{"userId": "gu1", "permissions": ["ACTIVITY_EXPORT"]}]}))
    assert cleared == ["user-1"]
    cleared.clear()
    run(route.process_push("permissions", {"userPermissionsChange": [{"userId": "gu1", "permissions": ["HEALTH_EXPORT"]}]}))
    assert cleared == []


def test_a_failure_while_filing_never_escapes(monkeypatch):
    async def boom(garmin_user):
        raise RuntimeError("database down")

    monkeypatch.setattr(route, "user_for", boom)
    run(route.process_push("dailies", {"dailies": [DAILY]}))  # must not raise: Garmin has already been answered
