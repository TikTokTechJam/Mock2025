from fastapi import APIRouter

from privastream_api.api.routes.face import FaceControlAuthorizer, create_face_router
from privastream_api.api.routes.health import health_router
from privastream_api.privacy.face.production import ProductionFaceIntegration


def create_api_router(
    face_integration: ProductionFaceIntegration | None = None,
    *,
    face_authorizer: FaceControlAuthorizer | None = None,
) -> APIRouter:
    """Create the API router with an explicitly scoped face integration."""

    integration = face_integration or ProductionFaceIntegration.from_environment()
    router = APIRouter()
    router.include_router(health_router)
    router.include_router(create_face_router(integration, authorizer=face_authorizer))
    return router


api_router = create_api_router()
