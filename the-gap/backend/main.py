from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import traceback
import os

app = FastAPI(
    title="The Gap API",
    description="Personal Causal Intelligence Layer — analyses wearable data to find verified cause-and-effect insights",
    version="1.0.0"
)

# Allow all origins — tighten after launch
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "*",
        "https://the-gap-15e7.vercel.app",
        "https://causalme.com",
        "https://www.causalme.com",
        "http://localhost:3000",
    ],
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

# Global exception handler — returns JSON instead of HTML 500
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    return JSONResponse(
        status_code=500,
        content={
            "error": type(exc).__name__,
            "detail": str(exc),
            "traceback": traceback.format_exc()
        }
    )

from routers import analyse
from routers import connect
from routers import checkin
from routers import journal
from routers import assistant
from routers import account
from sync import daily_sync
app.include_router(analyse.router)
app.include_router(connect.router)
app.include_router(checkin.router)
app.include_router(daily_sync.router)
app.include_router(journal.router)
app.include_router(assistant.router)
app.include_router(account.router)

@app.get("/health")
def health_check():
    return {"status": "ok", "service": "the-gap-api"}

@app.get("/")
def root():
    return {"message": "The Gap API is running. POST /analyse to begin."}

@app.get("/debug-oauth")
async def debug_oauth():
    """Debug OAuth env vars and test Whoop token endpoint reachability."""
    import httpx, os
    whoop_client_id = os.getenv("WHOOP_CLIENT_ID", "")
    whoop_secret = os.getenv("WHOOP_CLIENT_SECRET", "")
    oura_client_id = os.getenv("OURA_CLIENT_ID", "")
    app_base = os.getenv("APP_BASE_URL", "")
    frontend = os.getenv("FRONTEND_URL", "")
    result = {
        "WHOOP_CLIENT_ID_set": bool(whoop_client_id),
        "WHOOP_CLIENT_ID_preview": whoop_client_id[:8] + "..." if whoop_client_id else "(empty)",
        "WHOOP_CLIENT_SECRET_set": bool(whoop_secret),
        "WHOOP_CLIENT_SECRET_length": len(whoop_secret),
        "OURA_CLIENT_ID_set": bool(oura_client_id),
        "APP_BASE_URL": app_base,
        "FRONTEND_URL": frontend,
        "redirect_uri_would_be": f"{app_base}/connect/whoop/callback",
    }
    # Test reachability of Whoop token endpoint
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.post(
                "https://api.prod.whoop.com/oauth/oauth2/token",
                data={"grant_type": "authorization_code", "code": "test",
                      "redirect_uri": f"{app_base}/connect/whoop/callback",
                      "client_id": whoop_client_id, "client_secret": whoop_secret},
                headers={"Accept": "application/json"},
            )
            result["whoop_token_endpoint_status"] = resp.status_code
            result["whoop_token_endpoint_response"] = resp.json()
    except Exception as e:
        result["whoop_token_endpoint_error"] = str(e)
    return result


@app.get("/debug-network")
async def debug_network():
    """Test DNS and network connectivity from Railway."""
    import httpx, socket, os
    supabase_url = os.getenv("SUPABASE_URL", "").strip().rstrip("/")
    supabase_host = supabase_url.replace("https://", "").replace("http://", "").split("/")[0]
    results = {
        "supabase_url": supabase_url,
        "supabase_host": supabase_host,
    }

    # Test DNS resolution
    try:
        ip = socket.gethostbyname(supabase_host)
        results["dns_resolved"] = True
        results["dns_ip"] = ip
    except Exception as e:
        results["dns_resolved"] = False
        results["dns_error"] = str(e)

    # Test HTTP GET to Supabase REST
    supabase_key = os.getenv("SUPABASE_SERVICE_KEY", "").strip()
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                f"{supabase_url}/rest/v1/results",
                headers={
                    "apikey": supabase_key,
                    "Authorization": f"Bearer {supabase_key}",
                },
                params={"limit": "1"},
            )
            results["supabase_http_status"] = resp.status_code
            results["supabase_http_ok"] = resp.status_code < 400
    except Exception as e:
        results["supabase_http_error"] = str(e)

    # Test a known public URL to confirm general outbound internet works
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.get("https://httpbin.org/get")
            results["internet_ok"] = resp.status_code == 200
    except Exception as e:
        results["internet_error"] = str(e)

    return results


@app.get("/debug-imports")
def debug_imports():
    """Check which packages are available on this server."""
    import os
    results = {}
    packages = ["pandas", "numpy", "scipy", "econml", "sklearn", "supabase"]
    for pkg in packages:
        try:
            mod = __import__(pkg)
            results[pkg] = getattr(mod, "__version__", "installed")
        except ImportError as e:
            results[pkg] = f"MISSING: {e}"
    # Show env var status (not the actual values)
    supabase_url = os.getenv("SUPABASE_URL", "")
    supabase_key = os.getenv("SUPABASE_SERVICE_KEY", "")
    results["SUPABASE_URL_set"] = bool(supabase_url)
    results["SUPABASE_URL_starts_https"] = supabase_url.startswith("https://")
    results["SUPABASE_URL_preview"] = supabase_url[:40] if supabase_url else "(empty)"
    results["SUPABASE_KEY_set"] = bool(supabase_key)
    results["SUPABASE_KEY_length"] = len(supabase_key)
    return results
