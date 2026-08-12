"""Reproducible model-manifest and local artifact resolution."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import stat
import sys
import tarfile
import tempfile
import zipfile
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import BinaryIO, Literal, cast
from urllib.parse import unquote, urlparse
from urllib.request import Request, urlopen

DEFAULT_MANIFEST_DIR = Path("models/manifests")
DEFAULT_CACHE_DIR = Path(os.environ.get("PRIVASTREAM_MODEL_CACHE_DIR", ".cache/models"))
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
IDENTIFIER_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]*$")
ArtifactType = Literal["file", "archive"]
ARCHIVE_EXTRACTION_MARKER = ".privastream-extraction-sha256"
DEFAULT_MAX_ARCHIVE_MEMBERS = 10_000
DEFAULT_MAX_EXTRACTED_BYTES = 4 * 1024 * 1024 * 1024


class ModelArtifactError(RuntimeError):
    """Raised when a model manifest or artifact cannot be trusted or resolved."""


@dataclass(frozen=True, slots=True)
class ModelRuntime:
    """Optional adapter metadata supplied with a model handoff."""

    format: str
    model_name: str | None = None
    provider: str | None = None

    @classmethod
    def from_mapping(cls, value: object) -> "ModelRuntime":
        if not isinstance(value, Mapping):
            raise ModelArtifactError("model runtime metadata must contain an object")
        model_format = value.get("format")
        if not isinstance(model_format, str):
            raise ModelArtifactError("model runtime metadata must contain a string format")
        model_name = value.get("model_name")
        provider = value.get("provider")
        if model_name is not None and not isinstance(model_name, str):
            raise ModelArtifactError("model runtime model_name must be a string")
        if provider is not None and not isinstance(provider, str):
            raise ModelArtifactError("model runtime provider must be a string")
        runtime = cls(format=model_format, model_name=model_name, provider=provider)
        runtime.validate()
        return runtime

    def validate(self) -> None:
        if not self.format.strip():
            raise ModelArtifactError("model runtime format must not be empty")
        if self.model_name is not None and not self.model_name.strip():
            raise ModelArtifactError("model runtime model_name must not be empty")
        if self.provider is not None and not self.provider.strip():
            raise ModelArtifactError("model runtime provider must not be empty")

    def as_json(self) -> dict[str, str]:
        value = {"format": self.format}
        if self.model_name is not None:
            value["model_name"] = self.model_name
        if self.provider is not None:
            value["provider"] = self.provider
        return value


@dataclass(frozen=True, slots=True)
class ModelManifest:
    """Metadata required to identify, verify, and load one runtime artifact."""

    model_id: str
    version: str
    filename: str
    source: str
    sha256: str
    license: str
    artifact_type: ArtifactType = "file"
    runtime: ModelRuntime | None = None

    @classmethod
    def from_mapping(cls, value: object) -> "ModelManifest":
        if not isinstance(value, dict):
            raise ModelArtifactError("model manifest must contain a JSON object")
        required = ("model_id", "version", "filename", "license")
        missing = [field for field in required if not isinstance(value.get(field), str)]
        if missing:
            raise ModelArtifactError(f"model manifest fields must be strings: {', '.join(missing)}")

        source_value = value.get("source")
        source: str | None
        sha256: str | None
        if isinstance(source_value, Mapping):
            source = source_value.get("url")
            sha256 = source_value.get("sha256")
            if not isinstance(source, str) or not isinstance(sha256, str):
                raise ModelArtifactError("model source must contain string url and sha256 fields")
            top_level_sha256 = value.get("sha256")
            if top_level_sha256 is not None and top_level_sha256 != sha256:
                raise ModelArtifactError("model source sha256 conflicts with top-level sha256")
        else:
            source = source_value if isinstance(source_value, str) else None
            sha256 = value.get("sha256") if isinstance(value.get("sha256"), str) else None
        if source is None or sha256 is None:
            raise ModelArtifactError("model manifest requires source and sha256 metadata")

        artifact_type = value.get("type", value.get("artifact_type", "file"))
        if not isinstance(artifact_type, str):
            raise ModelArtifactError("model manifest type must be a string")
        runtime_value = value.get("runtime")
        runtime = None if runtime_value is None else ModelRuntime.from_mapping(runtime_value)

        manifest = cls(
            model_id=value["model_id"],
            version=value["version"],
            filename=value["filename"],
            source=source,
            sha256=sha256,
            license=value["license"],
            artifact_type=cast(ArtifactType, artifact_type),
            runtime=runtime,
        )
        manifest.validate()
        return manifest

    def validate(self) -> None:
        if not IDENTIFIER_PATTERN.fullmatch(self.model_id):
            raise ModelArtifactError("model_id must use lowercase letters, numbers, '_' or '-'")
        if not self.version.strip() or Path(self.version).name != self.version:
            raise ModelArtifactError("model version must be a non-empty path-safe value")
        if not self.filename or Path(self.filename).name != self.filename:
            raise ModelArtifactError("model filename must be a single safe filename")
        if not self.source.strip():
            raise ModelArtifactError("model source must not be empty")
        if not SHA256_PATTERN.fullmatch(self.sha256) or self.sha256 != self.sha256.lower():
            raise ModelArtifactError("model sha256 must be 64 lowercase hexadecimal characters")
        if not self.license.strip():
            raise ModelArtifactError("model license must not be empty")
        if self.artifact_type not in {"file", "archive"}:
            raise ModelArtifactError("model type must be either file or archive")
        if self.artifact_type == "archive":
            _archive_format(self.filename)
        if self.runtime is not None:
            self.runtime.validate()

    def as_json(self) -> dict[str, object]:
        value: dict[str, object] = {
            "model_id": self.model_id,
            "version": self.version,
            "type": self.artifact_type,
            "filename": self.filename,
            "source": {"url": self.source, "sha256": self.sha256},
            "license": self.license,
        }
        if self.runtime is not None:
            value["runtime"] = self.runtime.as_json()
        return value


def _archive_format(filename: str) -> Literal["zip", "tar"]:
    """Return the supported archive family for a safe manifest filename."""

    lower_name = filename.lower()
    if lower_name.endswith(".zip"):
        return "zip"
    if lower_name.endswith((".tar", ".tar.gz", ".tgz")):
        return "tar"
    raise ModelArtifactError("archive filename must end with .zip, .tar, .tar.gz, or .tgz")


def load_manifest(path: Path) -> ModelManifest:
    """Load and validate one manifest file without loading the model artifact."""

    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ModelArtifactError(f"model manifest not found at {path}") from exc
    except (OSError, json.JSONDecodeError) as exc:
        raise ModelArtifactError(f"could not read model manifest at {path}") from exc
    return ModelManifest.from_mapping(value)


def sha256_file(path: Path) -> str:
    """Return the SHA-256 digest of a local artifact."""

    digest = hashlib.sha256()
    try:
        with path.open("rb") as artifact:
            for chunk in iter(lambda: artifact.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as exc:
        raise ModelArtifactError(f"could not read model artifact at {path}") from exc
    return digest.hexdigest()


class ModelArtifactResolver:
    """Resolve logical model IDs to verified files or extracted packs."""

    def __init__(
        self,
        manifest_dir: Path = DEFAULT_MANIFEST_DIR,
        cache_dir: Path | None = None,
        timeout_seconds: float = 60.0,
        max_archive_members: int = DEFAULT_MAX_ARCHIVE_MEMBERS,
        max_extracted_bytes: int = DEFAULT_MAX_EXTRACTED_BYTES,
    ) -> None:
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        if max_archive_members <= 0:
            raise ValueError("max_archive_members must be positive")
        if max_extracted_bytes <= 0:
            raise ValueError("max_extracted_bytes must be positive")
        self.manifest_dir = manifest_dir
        self.cache_dir = cache_dir or Path(
            os.environ.get("PRIVASTREAM_MODEL_CACHE_DIR", str(DEFAULT_CACHE_DIR))
        )
        self.timeout_seconds = timeout_seconds
        self.max_archive_members = max_archive_members
        self.max_extracted_bytes = max_extracted_bytes

    def manifest(self, model_id: str) -> ModelManifest:
        if not IDENTIFIER_PATTERN.fullmatch(model_id):
            raise ModelArtifactError("model_id must use lowercase letters, numbers, '_' or '-'")
        manifest = load_manifest(self.manifest_dir / f"{model_id}.json")
        if manifest.model_id != model_id:
            raise ModelArtifactError(
                f"manifest ID {manifest.model_id!r} does not match requested model {model_id!r}"
            )
        return manifest

    def cached_path(self, manifest: ModelManifest) -> Path:
        """Return the versioned downloaded artifact path without creating directories."""

        return self.cache_dir / manifest.model_id / manifest.version / manifest.filename

    def extracted_path(self, manifest: ModelManifest) -> Path:
        """Return the versioned extraction directory for an archive manifest."""

        return self.cache_dir / manifest.model_id / manifest.version / "extracted"

    def resolve(self, model_id: str, *, refresh: bool = False) -> Path:
        """Return a verified file or extracted directory, downloading when necessary."""

        manifest = self.manifest(model_id)
        destination = self._cache_artifact(manifest, refresh=refresh)
        if manifest.artifact_type == "file":
            return destination

        extracted = self.extracted_path(manifest)
        marker = extracted / ARCHIVE_EXTRACTION_MARKER
        if not refresh and extracted.is_dir() and marker.is_file():
            try:
                if marker.read_text(encoding="ascii").strip() == manifest.sha256:
                    return extracted
            except OSError:
                pass

        temporary_directory: Path | None = Path(
            tempfile.mkdtemp(prefix=".extracted-", dir=str(destination.parent))
        )
        try:
            assert temporary_directory is not None
            self._extract_archive(destination, temporary_directory, manifest)
            (temporary_directory / ARCHIVE_EXTRACTION_MARKER).write_text(
                manifest.sha256 + "\n", encoding="ascii"
            )
            if extracted.exists():
                if extracted.is_dir():
                    shutil.rmtree(extracted)
                else:
                    extracted.unlink()
            temporary_directory.replace(extracted)
            temporary_directory = None
            return extracted
        except ModelArtifactError:
            raise
        except OSError as exc:
            raise ModelArtifactError(f"could not extract model archive {model_id!r}") from exc
        finally:
            if temporary_directory is not None:
                shutil.rmtree(temporary_directory, ignore_errors=True)

    def _cache_artifact(self, manifest: ModelManifest, *, refresh: bool) -> Path:
        destination = self.cached_path(manifest)
        if destination.is_file() and not refresh:
            self._verify(destination, manifest)
            return destination

        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="wb",
                dir=destination.parent,
                prefix=f".{manifest.filename}.",
                suffix=".part",
                delete=False,
            ) as temporary:
                temporary_path = Path(temporary.name)
                self._copy_source(manifest, temporary)
            self._verify(temporary_path, manifest)
            temporary_path.replace(destination)
            temporary_path = None
            return destination
        except OSError as exc:
            raise ModelArtifactError(f"could not cache model {manifest.model_id!r}") from exc
        finally:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)

    def _extract_archive(
        self,
        archive_path: Path,
        destination: Path,
        manifest: ModelManifest,
    ) -> None:
        archive_format = _archive_format(manifest.filename)
        try:
            if archive_format == "zip":
                self._extract_zip(archive_path, destination, manifest)
            else:
                self._extract_tar(archive_path, destination, manifest)
        except ModelArtifactError:
            raise
        except (OSError, tarfile.TarError, zipfile.BadZipFile) as exc:
            raise ModelArtifactError(
                f"could not extract model archive for {manifest.model_id}"
            ) from exc

    def _extract_zip(self, archive_path: Path, destination: Path, manifest: ModelManifest) -> None:
        with zipfile.ZipFile(archive_path) as archive:
            members = archive.infolist()
            self._validate_member_count(len(members), manifest)
            total_bytes = 0
            seen: set[str] = set()
            for member in members:
                target, key = self._safe_archive_path(destination, member.filename)
                self._record_member(key, seen, manifest)
                if member.is_dir():
                    target.mkdir(parents=True, exist_ok=True)
                    continue
                mode = (member.external_attr >> 16) & 0o170000
                if mode == stat.S_IFLNK or mode not in {0, stat.S_IFREG}:
                    raise ModelArtifactError(
                        f"model archive contains an unsupported entry: {member.filename!r}"
                    )
                total_bytes = self._record_size(total_bytes, member.file_size, manifest)
                target.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(member, "r") as source, target.open("wb") as output:
                    shutil.copyfileobj(source, output, length=1024 * 1024)

    def _extract_tar(self, archive_path: Path, destination: Path, manifest: ModelManifest) -> None:
        with tarfile.open(archive_path, mode="r:*") as archive:
            members = archive.getmembers()
            self._validate_member_count(len(members), manifest)
            total_bytes = 0
            seen: set[str] = set()
            for member in members:
                target, key = self._safe_archive_path(destination, member.name)
                self._record_member(key, seen, manifest)
                if member.isdir():
                    target.mkdir(parents=True, exist_ok=True)
                    continue
                if member.issym() or member.islnk() or member.isdev() or not member.isfile():
                    raise ModelArtifactError(
                        f"model archive contains an unsupported entry: {member.name!r}"
                    )
                total_bytes = self._record_size(total_bytes, member.size, manifest)
                target.parent.mkdir(parents=True, exist_ok=True)
                source = archive.extractfile(member)
                if source is None:
                    raise ModelArtifactError(
                        f"model archive entry could not be read: {member.name!r}"
                    )
                with source, target.open("wb") as output:
                    shutil.copyfileobj(source, output, length=1024 * 1024)

    def _safe_archive_path(self, root: Path, name: str) -> tuple[Path, str]:
        normalized = name.replace("\\", "/")
        path = PurePosixPath(normalized)
        parts = tuple(part for part in path.parts if part != ".")
        if (
            not parts
            or path.is_absolute()
            or any(part == ".." or ":" in part for part in parts)
        ):
            raise ModelArtifactError(f"model archive contains an unsafe path: {name!r}")
        target = root.joinpath(*parts)
        root_resolved = root.resolve()
        target_resolved = target.resolve()
        if target_resolved != root_resolved and root_resolved not in target_resolved.parents:
            raise ModelArtifactError(f"model archive contains an unsafe path: {name!r}")
        return target, "/".join(parts)

    def _validate_member_count(self, count: int, manifest: ModelManifest) -> None:
        if count > self.max_archive_members:
            raise ModelArtifactError(
                f"model archive for {manifest.model_id} exceeds the member limit"
            )

    @staticmethod
    def _record_member(key: str, seen: set[str], manifest: ModelManifest) -> None:
        if key in seen:
            raise ModelArtifactError(
                f"model archive for {manifest.model_id} contains a duplicate entry"
            )
        seen.add(key)

    def _record_size(self, total: int, size: int, manifest: ModelManifest) -> int:
        if size < 0 or total > self.max_extracted_bytes - size:
            raise ModelArtifactError(
                f"model archive for {manifest.model_id} exceeds the extracted-size limit"
            )
        return total + size

    def _verify(self, path: Path, manifest: ModelManifest) -> None:
        actual = sha256_file(path)
        if actual != manifest.sha256:
            raise ModelArtifactError(
                f"checksum mismatch for {manifest.model_id} {manifest.version}: "
                f"expected {manifest.sha256}, got {actual}"
            )

    def _copy_source(self, manifest: ModelManifest, destination: BinaryIO) -> None:
        parsed = urlparse(manifest.source)
        if parsed.scheme in {"http", "https"}:
            request = Request(manifest.source, headers={"User-Agent": "privastream-model-resolver/1"})
            try:
                with urlopen(request, timeout=self.timeout_seconds) as response:  # noqa: S310
                    shutil.copyfileobj(response, destination, length=1024 * 1024)
            except OSError as exc:
                raise ModelArtifactError(f"could not download model source for {manifest.model_id}") from exc
            return

        if parsed.scheme == "file":
            source_path = Path(unquote(parsed.path))
        elif parsed.scheme:
            raise ModelArtifactError(f"unsupported model source scheme {parsed.scheme!r}")
        else:
            source_path = Path(manifest.source)
        try:
            with source_path.open("rb") as source:
                shutil.copyfileobj(source, destination, length=1024 * 1024)
        except OSError as exc:
            raise ModelArtifactError(f"could not copy model source for {manifest.model_id}") from exc


def write_manifest(
    *,
    model_id: str,
    version: str,
    filename: str,
    source: str,
    license_name: str,
    artifact: Path,
    output: Path,
    artifact_type: ArtifactType = "file",
    runtime_format: str | None = None,
    runtime_model_name: str | None = None,
    runtime_provider: str | None = None,
) -> Path:
    """Create a manifest from a handed-off artifact and its computed checksum."""

    if not artifact.is_file():
        raise ModelArtifactError(f"model artifact not found at {artifact}")
    if runtime_format is None and (runtime_model_name is not None or runtime_provider is not None):
        raise ModelArtifactError("runtime model_name and provider require runtime_format")
    runtime = (
        ModelRuntime(
            format=runtime_format,
            model_name=runtime_model_name,
            provider=runtime_provider,
        )
        if runtime_format is not None
        else None
    )
    manifest = ModelManifest(
        model_id=model_id,
        version=version,
        filename=filename,
        source=source,
        sha256=sha256_file(artifact),
        license=license_name,
        artifact_type=artifact_type,
        runtime=runtime,
    )
    manifest.validate()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(manifest.as_json(), indent=2) + "\n", encoding="utf-8")
    return output


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Resolve verified PrivaStream model artifacts.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    fetch = subparsers.add_parser(
        "fetch", help="Download or copy one manifest artifact into the cache"
    )
    fetch.add_argument("--model", required=True, help="Logical model ID, for example plate-detector")
    fetch.add_argument("--manifest-dir", type=Path, default=DEFAULT_MANIFEST_DIR)
    fetch.add_argument("--cache-dir", type=Path, default=DEFAULT_CACHE_DIR)
    fetch.add_argument("--refresh", action="store_true", help="Replace a cached artifact after re-verifying it")

    register = subparsers.add_parser("register", help="Create a manifest from an ML-handoff artifact")
    register.add_argument("--model", required=True)
    register.add_argument("--version", required=True)
    register.add_argument("--filename", required=True)
    register.add_argument("--source", required=True, help="Download URL or local file path used by the runtime")
    register.add_argument("--license", required=True, dest="license_name")
    register.add_argument("--artifact", type=Path, required=True)
    register.add_argument("--output", type=Path, required=True)
    register.add_argument(
        "--type",
        choices=("file", "archive"),
        default="file",
        dest="artifact_type",
        help="Artifact type; archives are extracted after checksum verification",
    )
    register.add_argument("--runtime-format", help="Adapter format, for example insightface-pack")
    register.add_argument("--runtime-model-name")
    register.add_argument("--runtime-provider")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "fetch":
            path = ModelArtifactResolver(args.manifest_dir, args.cache_dir).resolve(
                args.model, refresh=args.refresh
            )
            print(path)
        else:
            print(
                write_manifest(
                    model_id=args.model,
                    version=args.version,
                    filename=args.filename,
                    source=args.source,
                    license_name=args.license_name,
                    artifact=args.artifact,
                    output=args.output,
                    artifact_type=args.artifact_type,
                    runtime_format=args.runtime_format,
                    runtime_model_name=args.runtime_model_name,
                    runtime_provider=args.runtime_provider,
                )
            )
    except (ModelArtifactError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
