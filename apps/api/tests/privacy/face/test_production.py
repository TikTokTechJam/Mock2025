"""Deterministic coverage for the production face integration boundaries."""

from __future__ import annotations

import asyncio
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from privastream_api.main import create_app
from privastream_api.model_artifacts import write_manifest
from privastream_api.pipeline.contracts import VideoFrame
from privastream_api.pipeline.video import VideoOrchestrator, VideoOrchestrationConfig
from privastream_api.privacy.face import (
    CreatorFaceDetectorConfig,
    FaceEnrollmentConfig,
    FaceObservation,
    FaceProductionConfig,
    InsightFaceConfig,
    ProductionFaceIntegration,
)
from privastream_api.privacy.vision.service import DetectorExecutionError


def _creator_face() -> FaceObservation:
    return FaceObservation(
        x1=10,
        y1=10,
        x2=30,
        y2=30,
        detection_confidence=0.99,
        quality=0.99,
        embedding=(1.0, 0.0),
        track_id="creator-track",
    )


def _bystander_face() -> FaceObservation:
    return FaceObservation(
        x1=50,
        y1=20,
        x2=80,
        y2=70,
        detection_confidence=0.98,
        quality=0.98,
        embedding=(0.0, 1.0),
        track_id="bystander-track",
    )


class FakeFaceModel:
    def __init__(self) -> None:
        self.failure = False

    def detect(self, image: object) -> tuple[FaceObservation, ...]:
        if self.failure:
            raise DetectorExecutionError("fake face model failed")
        if image == "enrollment" or image == "replacement":
            return (_creator_face(),)
        if image == "frame":
            return (_creator_face(), _bystander_face())
        return ()


def _integration(model: FakeFaceModel) -> ProductionFaceIntegration:
    return ProductionFaceIntegration(
        model,
        config=FaceProductionConfig(
            model=InsightFaceConfig(model_root=Path("unused")),
            detector=CreatorFaceDetectorConfig(
                creator_match_threshold=0.55,
                ambiguity_margin=0.05,
            ),
            enrollment=FaceEnrollmentConfig(),
        ),
        image_decoder=lambda payload: payload.decode("ascii"),
    )


def test_from_environment_resolves_verified_face_model_pack(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    archive = tmp_path / "buffalo_l.zip"
    with zipfile.ZipFile(archive, "w") as output:
        output.writestr("models/buffalo_l/det_10g.onnx", b"detector")
    write_manifest(
        model_id="face-buffalo-l",
        version="v1",
        filename=archive.name,
        source=str(archive),
        license_name="Example license",
        artifact=archive,
        output=tmp_path / "models" / "manifests" / "face-buffalo-l.json",
        artifact_type="archive",
        runtime_format="insightface-pack",
        runtime_model_name="buffalo_l",
        runtime_provider="CPUExecutionProvider",
    )
    monkeypatch.setenv("PRIVASTREAM_FACE_MODEL_ID", "face-buffalo-l")
    monkeypatch.setenv("PRIVASTREAM_MODEL_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.delenv("PRIVASTREAM_MODEL_ID", raising=False)

    integration = ProductionFaceIntegration.from_environment()

    assert integration.config.model.model_name == "buffalo_l"
    assert integration.config.model.providers == ("CPUExecutionProvider",)
    assert integration.config.model.model_root == (
        tmp_path / "cache" / "face-buffalo-l" / "v1" / "extracted"
    )


def test_face_adapter_registers_issue_18_detector_with_issue_4() -> None:
    model = FakeFaceModel()
    integration = _integration(model)
    assert integration.readiness_status().reason_code == "enrollment_not_found"
    assert integration.create_enrollment(("enrollment",), consent=True).enrolled

    orchestrator = VideoOrchestrator(
        config=VideoOrchestrationConfig(padding_px=0),
    )
    adapter = integration.register(orchestrator)

    result = asyncio.run(
        orchestrator.process_frame(
            VideoFrame(width=100, height=100, timestamp_ms=200, payload="frame")
        )
    )

    assert orchestrator.registrations[0].detector is adapter
    assert result.detector_runs[0].status == "success"
    assert len(result.regions) == 1
    assert result.regions[0].kind == "face_bystander"
    assert result.regions[0].x == pytest.approx(0.5)
    assert result.regions[0].y == pytest.approx(0.2)
    assert result.regions[0].width == pytest.approx(0.3)
    assert result.regions[0].height == pytest.approx(0.5)
    assert integration.readiness_status().ready


def test_enrollment_repository_supports_replace_and_delete_lifecycle() -> None:
    integration = _integration(FakeFaceModel())

    created = integration.create_enrollment(("enrollment",), consent=True)
    assert created.status is not None
    assert integration.enrollment_status().state == "enrolled"

    replaced = integration.replace_enrollment(("replacement",), consent=True)
    assert replaced.status is not None
    assert replaced.status.enrollment_id != created.status.enrollment_id
    assert integration.enrollment_status().state == "enrolled"

    assert integration.delete_enrollment()
    status = integration.enrollment_status()
    assert status.state == "not_enrolled"
    assert status.enrollment is None
    assert status.reason_code == "enrollment_not_found"


def test_face_model_failure_is_explicit_to_scheduler_and_readiness() -> None:
    model = FakeFaceModel()
    integration = _integration(model)
    integration.create_enrollment(("enrollment",), consent=True)
    orchestrator = VideoOrchestrator(config=VideoOrchestrationConfig(padding_px=0))
    integration.register(orchestrator)
    model.failure = True

    result = asyncio.run(
        orchestrator.process_frame(
            VideoFrame(width=100, height=100, timestamp_ms=200, payload="frame")
        )
    )

    assert result.detector_runs[0].status == "error"
    assert result.detector_failures
    assert result.regions == ()
    assert integration.readiness_status().reason_code == "detector_error"
    assert not integration.readiness_status().ready


def test_face_control_routes_are_default_deny_and_support_injected_authorization() -> None:
    integration = _integration(FakeFaceModel())
    denied = TestClient(create_app(integration))
    assert denied.get("/privacy/face/enrollment").status_code == 503

    authorized = TestClient(create_app(integration, face_authorizer=lambda: None))
    status = authorized.get("/privacy/face/enrollment")
    assert status.status_code == 200
    assert status.json()["state"] == "not_enrolled"

    response = authorized.post(
        "/privacy/face/enrollment",
        data={"consent": "true"},
        files={"images": ("creator.jpg", b"enrollment", "image/jpeg")},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["state"] == "enrolled"
    assert "embedding_values" not in response.text

    replacement = authorized.put(
        "/privacy/face/enrollment",
        data={"consent": "true"},
        files={"images": ("creator-replacement.jpg", b"replacement", "image/jpeg")},
    )
    assert replacement.status_code == 200
    assert replacement.json()["state"] == "enrolled"

    deleted = authorized.delete("/privacy/face/enrollment")
    assert deleted.status_code == 200
    assert deleted.json()["deleted"] is True
    assert authorized.get("/privacy/face/enrollment").json()["state"] == "not_enrolled"
