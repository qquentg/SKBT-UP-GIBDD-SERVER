from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.devices import router as devices_router
from app.api.employee import router as employee_router
from app.api.messages import router as messages_router
from app.api.realtime import router as realtime_router
from app.core.config import get_settings
from app.db.database import close_database, init_database


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_database(get_settings())

    try:
        yield
    finally:
        close_database()


def create_app(enable_lifespan: bool = True) -> FastAPI:
    app = FastAPI(
        title=get_settings().app_name,
        lifespan=lifespan if enable_lifespan else None,
    )

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(devices_router)
    app.include_router(employee_router)
    app.include_router(messages_router)
    app.include_router(realtime_router)
    return app


app = create_app()
