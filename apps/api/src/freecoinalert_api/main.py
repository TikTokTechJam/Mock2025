from fastapi import FastAPI

from freecoinalert_api.api.router import api_router


def create_app() -> FastAPI:
    app = FastAPI(
        title="FreeCoinAlert API",
        version="0.1.0",
        description="Backend API for the FreeCoinAlert platform.",
    )
    app.include_router(api_router)
    return app


app = create_app()
