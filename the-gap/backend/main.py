from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from routers import analyse
import os

app = FastAPI(
    title="The Gap API",
    description="Personal Causal Intelligence Layer — analyses wearable data to find verified cause-and-effect insights",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*",
        "https://causalme.com",
        "https://www.causalme.com",
        "https://the-gap.vercel.app",
        "http://localhost:3000",
        "http://localhost:3001",
    ],
    allow_credentials=True,
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
