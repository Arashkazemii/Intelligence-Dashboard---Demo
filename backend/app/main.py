import os

import psycopg
from fastapi import FastAPI, HTTPException

from app.demo_finance.api import router as demo_finance_router
from app.demo_finance.questions import router as questions_router

app = FastAPI(title="ViraData Intelligence Dashboard Demo API")
app.include_router(demo_finance_router)
app.include_router(questions_router)


@app.get("/health")
def health() -> dict[str, str]:
    """Process liveness. This endpoint does not depend on PostgreSQL."""
    return {"status": "ok"}


@app.get("/ready")
def ready() -> dict[str, str]:
    """Service readiness, including a live PostgreSQL connection."""
    database_url = os.getenv("DATABASE_URL")
    if not database_url and not all(os.getenv(key) for key in ("PGHOST", "PGDATABASE", "PGUSER", "PGPASSWORD")):
        raise HTTPException(status_code=503, detail="Database connection is not configured")

    try:
        with psycopg.connect(database_url or "", connect_timeout=3) as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
                cursor.fetchone()
    except psycopg.Error:
        raise HTTPException(status_code=503, detail="Database is unavailable") from None

    return {"status": "ready"}

