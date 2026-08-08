from fastapi import FastAPI

from privastream_api.api.router import FaceControlAuthorizer, api_router, create_api_router
from privastream_api.privacy.face.production import ProductionFaceIntegration


def create_app(
    face_integration: ProductionFaceIntegration | None = None,
    *,
    face_authorizer: FaceControlAuthorizer | None = None,
) -> FastAPI:
    app = FastAPI(
        title="PrivaStream API",
        version="0.1.0",
        description="Control-plane API for the PrivaStream platform.",
    )
    app.include_router(
        api_router
        if face_integration is None and face_authorizer is None
        else create_api_router(face_integration, face_authorizer=face_authorizer)
    )
    return app


app = create_app()
