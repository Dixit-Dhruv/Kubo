from fastapi import Depends, FastAPI, HTTPException, status
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from kubo_iam.database import get_db
from kubo_iam.routes import limiter, router


def create_app() -> FastAPI:
    app = FastAPI(title="Kubo IAM", version="0.1.0")
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
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
