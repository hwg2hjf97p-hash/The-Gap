import asyncio
import logging

import pytest

from routers import diagnostics
from utils import client_errors as ce


@pytest.fixture(autouse=True)
def clean():
    ce._recent.clear()
    yield
    ce._recent.clear()


def test_emails_and_tokens_are_blanked_from_a_report():
    text = "Failed for sam@example.com with eyJhbGciOiJIUzI1NiIsInR5cCI6.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6.SflKxwRJSMeKKF2QT4fw"
    cleaned = ce.scrub(text, 500)
    assert "sam@example.com" not in cleaned and "eyJ" not in cleaned
    assert "[email]" in cleaned and "[token]" in cleaned


def test_a_long_secret_looking_string_is_blanked():
    assert "[secret]" in ce.scrub("key=" + "a" * 50, 500)


def test_a_report_is_cut_to_length():
    assert len(ce.scrub("x " * 5000, 100)) == 100


def test_a_field_is_flattened_to_one_line():
    assert ce.one_line("a\nb\n  c") == "a b c"


def test_a_person_can_send_a_handful_of_reports_an_hour_and_no_more():
    assert all(ce.allowed("u1", now=1000.0 + n) for n in range(ce.MAX_PER_HOUR))
    assert ce.allowed("u1", now=1100.0) is False


def test_the_limit_is_per_person_and_resets_after_an_hour():
    for n in range(ce.MAX_PER_HOUR):
        ce.allowed("u1", now=1000.0 + n)
    assert ce.allowed("u2", now=1010.0) is True
    assert ce.allowed("u1", now=1000.0 + 3700) is True


def test_the_endpoint_logs_the_report_without_personal_text(caplog):
    body = diagnostics.ClientError(message="Boom for sam@example.com", stack="at Home (index.tsx:10)", fatal=True, source="boundary", app_version="1.3.0", build="50", update_id="abc", os="ios 18.1")
    with caplog.at_level(logging.ERROR):
        response = asyncio.run(diagnostics.client_error(body, user_id="12345678-aaaa"))
    assert response.status_code == 200
    logged = " ".join(r.getMessage() for r in caplog.records)
    assert "CLIENT_ERROR" in logged and "user=12345678" in logged and "index.tsx:10" in logged
    assert "sam@example.com" not in logged


def test_the_endpoint_keeps_only_the_first_few_reports(caplog):
    body = diagnostics.ClientError(message="again")
    with caplog.at_level(logging.ERROR):
        for _ in range(ce.MAX_PER_HOUR + 5):
            asyncio.run(diagnostics.client_error(body, user_id="loop-user"))
    assert sum("CLIENT_ERROR" in r.getMessage() for r in caplog.records) == ce.MAX_PER_HOUR
