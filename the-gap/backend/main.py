from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from routers import analyse

app = FastAPI(
    title="The Gap API",
    description="Personal Causal Intelligence Layer",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)

app.include_router(analyse.router)

@app.get("/health")
def health_check():
    return {"status": "ok", "service": "the-gap-api"}

@app.get("/")
def root():
    return {"message": "The Gap API is running. POST /analyse to begin."}