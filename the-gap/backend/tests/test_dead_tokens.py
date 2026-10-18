import httpx

from utils.token_health import refresh_token_is_dead


def _error(status: int, body: str) -> httpx.HTTPStatusError:
    request = httpx.Request("POST", "https://oauth2.googleapis.com/token")
    return httpx.HTTPStatusError("failed", request=request, response=httpx.Response(status, text=body, request=request))


def test_a_login_the_provider_rejects_is_dead():
    assert refresh_token_is_dead(_error(400, '{"error": "invalid_grant", "error_description": "Token has been expired or revoked."}'))
    assert refresh_token_is_dead(_error(401, "invalid_grant"))


def test_other_failures_are_not_treated_as_a_dead_login():
    # Our own app secret being wrong, a server error, or a timeout must not switch anyone's connection off.
    assert not refresh_token_is_dead(_error(400, '{"error": "invalid_client"}'))
    assert not refresh_token_is_dead(_error(500, "invalid_grant"))
    assert not refresh_token_is_dead(_error(429, "slow down"))
    assert not refresh_token_is_dead(httpx.ReadTimeout("slow"))
    assert not refresh_token_is_dead(RuntimeError("boom"))


def test_google_calendar_is_a_retired_provider():
    from utils.token_health import RETIRED_PROVIDERS

    assert "google" in RETIRED_PROVIDERS
