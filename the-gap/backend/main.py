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
    allow_methods=["GET", "POST", "OPTIONS"],
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
from sync import daily_sync
app.include_router(analyse.router)
app.include_router(connect.router)
app.include_router(checkin.router)
app.include_router(daily_sync.router)

@app.get("/health")
def health_check():
    return {"status": "ok", "service": "the-gap-api"}

@app.get("/")
def root():
    return {"message": "The Gap API is running. POST /analyse to begin."}

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
