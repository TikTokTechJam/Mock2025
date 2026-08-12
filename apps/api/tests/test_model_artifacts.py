import zipfile
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


def test_register_and_resolve_verified_archive(tmp_path: Path) -> None:
    archive = tmp_path / "buffalo_l.zip"
    with zipfile.ZipFile(archive, "w") as output:
        output.writestr("models/buffalo_l/det_10g.onnx", b"detector")
        output.writestr("models/buffalo_l/w600k_r50.onnx", b"recognizer")
    manifest_path = tmp_path / "manifests" / "face-buffalo-l.json"

    write_manifest(
        model_id="face-buffalo-l",
        version="v1",
        filename=archive.name,
        source="https://example.test/buffalo_l.zip",
        license_name="Example license",
        artifact=archive,
        output=manifest_path,
        artifact_type="archive",
        runtime_format="insightface-pack",
        runtime_model_name="buffalo_l",
        runtime_provider="CPUExecutionProvider",
    )

    resolver = ModelArtifactResolver(manifest_path.parent, tmp_path / "cache")
    resolved = resolver.resolve("face-buffalo-l")

    assert resolved.is_dir()
    assert (resolved / "models" / "buffalo_l" / "det_10g.onnx").read_bytes() == b"detector"
    assert resolver.resolve("face-buffalo-l") == resolved
    manifest = load_manifest(manifest_path)
    assert manifest.artifact_type == "archive"
    assert manifest.runtime is not None
    assert manifest.runtime.format == "insightface-pack"


def test_resolver_rejects_archive_path_traversal(tmp_path: Path) -> None:
    archive = tmp_path / "unsafe.zip"
    with zipfile.ZipFile(archive, "w") as output:
        output.writestr("../outside.txt", b"unsafe")
    manifest_path = tmp_path / "manifests" / "unsafe-model.json"
    write_manifest(
        model_id="unsafe-model",
        version="v1",
        filename=archive.name,
        source=str(archive),
        license_name="Example license",
        artifact=archive,
        output=manifest_path,
        artifact_type="archive",
    )

    with pytest.raises(ModelArtifactError, match="unsafe path"):
        ModelArtifactResolver(manifest_path.parent, tmp_path / "cache").resolve("unsafe-model")


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


def test_manifest_accepts_nested_source_and_runtime_metadata() -> None:
    manifest = ModelManifest.from_mapping(
        {
            "model_id": "face-buffalo-l",
            "version": "v1",
            "type": "archive",
            "filename": "buffalo_l.zip",
            "source": {"url": "https://example.test/buffalo_l.zip", "sha256": "0" * 64},
            "license": "Example license",
            "runtime": {
                "format": "insightface-pack",
                "model_name": "buffalo_l",
                "provider": "CPUExecutionProvider",
            },
        }
    )

    assert manifest.source == "https://example.test/buffalo_l.zip"
    assert manifest.artifact_type == "archive"
    assert manifest.runtime is not None
    assert manifest.runtime.model_name == "buffalo_l"
