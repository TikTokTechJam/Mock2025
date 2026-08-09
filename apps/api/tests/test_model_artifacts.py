from pathlib import Path

import pytest

from privastream_api.model_artifacts import (
    ModelArtifactError,
    ModelArtifactResolver,
    ModelManifest,
    load_manifest,
    write_manifest,
)


def test_register_and_resolve_verified_local_artifact(tmp_path: Path) -> None:
    artifact = tmp_path / "plate-detector.pt"
    artifact.write_bytes(b"deterministic model handoff")
    manifest_path = tmp_path / "manifests" / "plate-detector.json"

    write_manifest(
        model_id="plate-detector",
        version="v1",
        filename=artifact.name,
        source=str(artifact),
        license_name="Example license",
        artifact=artifact,
        output=manifest_path,
    )

    resolver = ModelArtifactResolver(manifest_path.parent, tmp_path / "cache")
    resolved = resolver.resolve("plate-detector")

    assert resolved.read_bytes() == artifact.read_bytes()
    assert load_manifest(manifest_path).sha256


def test_resolver_rejects_corrupt_cached_artifact(tmp_path: Path) -> None:
    artifact = tmp_path / "model.onnx"
    artifact.write_bytes(b"trusted artifact")
    manifest_path = tmp_path / "manifests" / "example-model.json"
    write_manifest(
        model_id="example-model",
        version="v1",
        filename=artifact.name,
        source=str(artifact),
        license_name="Example license",
        artifact=artifact,
        output=manifest_path,
    )

    resolver = ModelArtifactResolver(manifest_path.parent, tmp_path / "cache")
    resolved = resolver.resolve("example-model")
    resolved.write_bytes(b"corrupt artifact")

    with pytest.raises(ModelArtifactError, match="checksum mismatch"):
        resolver.resolve("example-model")


def test_manifest_rejects_path_traversal() -> None:
    with pytest.raises(ModelArtifactError, match="path-safe"):
        ModelManifest.from_mapping(
            {
                "model_id": "plate-detector",
                "version": "../v1",
                "filename": "model.pt",
                "source": "https://example.test/model.pt",
                "sha256": "0" * 64,
                "license": "Example license",
            }
        )
