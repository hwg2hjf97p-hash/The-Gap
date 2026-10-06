import os
import sys

# Tests import the backend's modules directly (routers, utils, causal ...).
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# No real database or keys are ever used in tests.
os.environ.setdefault("SUPABASE_URL", "http://supabase.invalid")
os.environ.setdefault("SUPABASE_SERVICE_KEY", "test-key")
for name in ("REQUIRE_AI_CONSENT", "REQUIRE_SUBSCRIPTION", "ANTHROPIC_API_KEY"):
    os.environ.pop(name, None)


def pytest_runtest_logreport(report):
    """On GitHub Actions, show each failure as an annotation on the run so it can
    be read without opening the full log."""
    if report.when in ("setup", "call") and report.failed:
        text = str(report.longrepr)[-900:]
        text = text.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")
        print(f"::error title={report.nodeid}::{text}")
