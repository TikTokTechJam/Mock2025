"""Control-plane enrollment and readiness routes for production face privacy."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Annotated, NoReturn

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

from privastream_api.privacy.face.enrollment import (
    ConsentRequiredError,
    EnrollmentRejection,
    FaceEnrollmentError,
)
from privastream_api.privacy.face.production import (
    EnrollmentAlreadyExistsError,
    EnrollmentNotFoundError,
    FaceCapabilityReadiness,
    FaceEnrollmentLifecycle,
    FaceEnrollmentLifecycleStatus,
    ProductionFaceIntegration,
)
from privastream_api.privacy.vision.service import DetectorError

FaceControlAuthorizer = Callable[[], object]


class FaceEnrollmentMetadataResponse(BaseModel):
    """Safe enrollment metadata without embedding values or source images."""

    enrollment_id: str
    sample_count: int
    embedding_dimension: int
    created_at_ms: int
    updated_at_ms: int


class FaceEnrollmentRejectionResponse(BaseModel):
    sample_index: int
    reason: str


class FaceEnrollmentResponse(BaseModel):
    state: FaceEnrollmentLifecycle
    enrollment: FaceEnrollmentMetadataResponse | None
    reason_code: str | None
    accepted_samples: int | None = None
    rejections: tuple[FaceEnrollmentRejectionResponse, ...] = ()
    deleted: bool | None = None


class FaceReadinessResponse(BaseModel):
    capability: str = "face"
    enabled: bool
    required: bool
    ready: bool
    reason_code: str | None
    detector_id: str
    model_name: str
    providers: tuple[str, ...]
    enrollment_state: FaceEnrollmentLifecycle


def _deny_face_control() -> None:
    """Keep the default app closed until the host injects creator authorization."""

    raise HTTPException(
        status_code=503,
        detail="face enrollment authorization is not configured",
    )


def _enrollment_response(
    status: FaceEnrollmentLifecycleStatus,
    *,
    accepted_samples: int | None = None,
    rejections: Sequence[EnrollmentRejection] = (),
    deleted: bool | None = None,
) -> FaceEnrollmentResponse:
    enrollment = status.enrollment
    return FaceEnrollmentResponse(
        state=status.state,
        enrollment=(
            FaceEnrollmentMetadataResponse(
                enrollment_id=enrollment.enrollment_id,
                sample_count=enrollment.sample_count,
                embedding_dimension=enrollment.embedding_dimension,
                created_at_ms=enrollment.created_at_ms,
                updated_at_ms=enrollment.updated_at_ms,
            )
            if enrollment is not None
            else None
        ),
        reason_code=status.reason_code,
        accepted_samples=accepted_samples,
        rejections=tuple(
            FaceEnrollmentRejectionResponse(
                sample_index=rejection.sample_index,
                reason=rejection.reason,
            )
            for rejection in rejections
        ),
        deleted=deleted,
    )


def _readiness_response(readiness: FaceCapabilityReadiness) -> FaceReadinessResponse:
    return FaceReadinessResponse(
        enabled=readiness.enabled,
        required=readiness.required,
        ready=readiness.ready,
        reason_code=readiness.reason_code,
        detector_id=readiness.detector_id,
        model_name=readiness.model_name,
        providers=readiness.providers,
        enrollment_state=readiness.enrollment_state,
    )


async def _decode_uploads(
    integration: ProductionFaceIntegration,
    uploads: Sequence[UploadFile],
) -> list[object]:
    if not uploads:
        raise HTTPException(status_code=422, detail="at least one enrollment image is required")
    if len(uploads) > integration.config.enrollment.max_samples:
        raise HTTPException(
            status_code=413,
            detail=(
                f"at most {integration.config.enrollment.max_samples} enrollment images are accepted"
            ),
        )

    samples: list[object] = []
    for upload in uploads:
        try:
            payload = await upload.read(integration.config.max_sample_bytes + 1)
            if len(payload) > integration.config.max_sample_bytes:
                raise HTTPException(
                    status_code=413,
                    detail="enrollment image exceeds the configured size limit",
                )
            samples.append(integration.decode_sample(payload))
        except HTTPException:
            raise
        except DetectorError as exc:
            raise HTTPException(
                status_code=503,
                detail="face enrollment capability is unavailable",
            ) from exc
        except FaceEnrollmentError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        finally:
            await upload.close()
    return samples


def _raise_enrollment_error(exc: Exception) -> NoReturn:
    if isinstance(exc, ConsentRequiredError):
        raise HTTPException(
            status_code=400,
            detail="explicit creator consent is required for enrollment",
        ) from exc
    if isinstance(exc, EnrollmentAlreadyExistsError):
        raise HTTPException(status_code=409, detail="creator enrollment already exists") from exc
    if isinstance(exc, EnrollmentNotFoundError):
        raise HTTPException(status_code=404, detail="creator enrollment does not exist") from exc
    if isinstance(exc, FaceEnrollmentError):
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    raise HTTPException(status_code=503, detail="face enrollment capability failed") from exc


def _raise_rejected_enrollment(
    integration: ProductionFaceIntegration,
    result_rejections: Sequence[EnrollmentRejection],
) -> NoReturn:
    reasons = {rejection.reason for rejection in result_rejections}
    if reasons & {"detector_unavailable", "detector_error"}:
        integration.readiness.record_failure(
            "detector_unavailable" if "detector_unavailable" in reasons else "detector_error"
        )
        raise HTTPException(status_code=503, detail="face enrollment detector failed")
    raise HTTPException(
        status_code=422,
        detail={
            "reason_code": "enrollment_rejected",
            "rejections": [
                {"sample_index": rejection.sample_index, "reason": rejection.reason}
                for rejection in result_rejections
            ],
        },
    )


def create_face_router(
    integration: ProductionFaceIntegration,
    *,
    authorizer: FaceControlAuthorizer | None = None,
) -> APIRouter:
    """Create routes bound to one process-scoped integration and creator scope."""

    router = APIRouter(
        prefix="/privacy/face",
        tags=["face"],
        dependencies=[Depends(authorizer or _deny_face_control)],
    )

    @router.get("/enrollment", response_model=FaceEnrollmentResponse)
    def get_enrollment() -> FaceEnrollmentResponse:
        return _enrollment_response(integration.enrollment_status())

    @router.post("/enrollment", response_model=FaceEnrollmentResponse, status_code=201)
    async def create_enrollment(
        images: Annotated[list[UploadFile], File()],
        consent: Annotated[bool, Form()] = False,
    ) -> FaceEnrollmentResponse:
        samples = await _decode_uploads(integration, images)
        try:
            result = integration.create_enrollment(samples, consent=consent)
        except Exception as exc:
            _raise_enrollment_error(exc)
        if not result.enrolled:
            _raise_rejected_enrollment(integration, result.rejections)
        return _enrollment_response(
            integration.enrollment_status(),
            accepted_samples=result.accepted_samples,
            rejections=result.rejections,
        )

    @router.put("/enrollment", response_model=FaceEnrollmentResponse)
    async def replace_enrollment(
        images: Annotated[list[UploadFile], File()],
        consent: Annotated[bool, Form()] = False,
    ) -> FaceEnrollmentResponse:
        samples = await _decode_uploads(integration, images)
        try:
            result = integration.replace_enrollment(samples, consent=consent)
        except Exception as exc:
            _raise_enrollment_error(exc)
        if not result.enrolled:
            _raise_rejected_enrollment(integration, result.rejections)
        return _enrollment_response(
            integration.enrollment_status(),
            accepted_samples=result.accepted_samples,
            rejections=result.rejections,
        )

    @router.delete("/enrollment", response_model=FaceEnrollmentResponse)
    def delete_enrollment() -> FaceEnrollmentResponse:
        try:
            deleted = integration.delete_enrollment()
        except Exception as exc:
            _raise_enrollment_error(exc)
        return _enrollment_response(integration.enrollment_status(), deleted=deleted)

    @router.get("/readiness", response_model=FaceReadinessResponse)
    def get_readiness() -> FaceReadinessResponse:
        return _readiness_response(integration.readiness_status())

    return router


__all__ = [
    "FaceEnrollmentMetadataResponse",
    "FaceEnrollmentRejectionResponse",
    "FaceEnrollmentResponse",
    "FaceReadinessResponse",
    "create_face_router",
]
