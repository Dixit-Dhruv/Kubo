from fastapi import Depends, FastAPI, HTTPException, status
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
import uvicorn

from kubo_compute.api import router
from kubo_compute.database import get_db


def create_app() -> FastAPI:
    app = FastAPI(title="Kubo Compute", version="0.1.0")
    app.include_router(router)

    @app.get("/health/live", tags=["health"])
    def liveness() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/health/ready", tags=["health"])
    def readiness(session: Session = Depends(get_db)) -> dict[str, str]:
        try:
            session.execute(text("SELECT 1"))
        except SQLAlchemyError as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Database unavailable.",
            ) from exc
        return {"status": "ready"}

    return app


app = create_app()


def run() -> None:
    uvicorn.run("kubo_compute.main:app", host="0.0.0.0", port=8000)
