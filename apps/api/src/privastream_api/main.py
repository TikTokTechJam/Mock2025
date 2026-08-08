from fastapi import FastAPI

from privastream_api.api.router import api_router


def create_app() -> FastAPI:
    app = FastAPI(
        title="PrivaStream API",
        version="0.1.0",
        description="Control-plane API for the PrivaStream platform.",
    )
    app.include_router(api_router)
    return app


app = create_app()
