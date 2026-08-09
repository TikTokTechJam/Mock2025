"""Reproducible model-manifest and local artifact resolution."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import sys
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import BinaryIO
from urllib.parse import unquote, urlparse
from urllib.request import Request, urlopen

DEFAULT_MANIFEST_DIR = Path("models/manifests")
DEFAULT_CACHE_DIR = Path(os.environ.get("PRIVASTREAM_MODEL_CACHE_DIR", ".cache/models"))
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
IDENTIFIER_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]*$")


class ModelArtifactError(RuntimeError):
    """Raised when a model manifest or artifact cannot be trusted or resolved."""


@dataclass(frozen=True, slots=True)
class ModelManifest:
    """Metadata required to identify and verify one runtime model artifact."""

    model_id: str
    version: str
    filename: str
    source: str
    sha256: str
    license: str

    @classmethod
    def from_mapping(cls, value: object) -> "ModelManifest":
        if not isinstance(value, dict):
            raise ModelArtifactError("model manifest must contain a JSON object")
        required = ("model_id", "version", "filename", "source", "sha256", "license")
        missing = [field for field in required if not isinstance(value.get(field), str)]
        if missing:
            raise ModelArtifactError(f"model manifest fields must be strings: {', '.join(missing)}")

        manifest = cls(
            model_id=value["model_id"],
            version=value["version"],
            filename=value["filename"],
            source=value["source"],
            sha256=value["sha256"],
            license=value["license"],
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

    def as_json(self) -> dict[str, str]:
        return asdict(self)


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
    """Resolve logical model IDs to verified files in a shared local cache."""

    def __init__(
        self,
        manifest_dir: Path = DEFAULT_MANIFEST_DIR,
        cache_dir: Path = DEFAULT_CACHE_DIR,
        timeout_seconds: float = 60.0,
    ) -> None:
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        self.manifest_dir = manifest_dir
        self.cache_dir = cache_dir
        self.timeout_seconds = timeout_seconds

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
        """Return the versioned cache path without creating directories."""

        return self.cache_dir / manifest.model_id / manifest.version / manifest.filename

    def resolve(self, model_id: str, *, refresh: bool = False) -> Path:
        """Return a verified cached artifact, downloading it when necessary."""

        manifest = self.manifest(model_id)
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
            raise ModelArtifactError(f"could not cache model {model_id!r}") from exc
        finally:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)

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
) -> Path:
    """Create a manifest from a handed-off artifact and its computed checksum."""

    if not artifact.is_file():
        raise ModelArtifactError(f"model artifact not found at {artifact}")
    manifest = ModelManifest(
        model_id=model_id,
        version=version,
        filename=filename,
        source=source,
        sha256=sha256_file(artifact),
        license=license_name,
    )
    manifest.validate()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(manifest.as_json(), indent=2) + "\n", encoding="utf-8")
    return output


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Resolve verified PrivaStream model artifacts.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    fetch = subparsers.add_parser("fetch", help="Download or copy one manifest artifact into the cache")
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
                )
            )
    except (ModelArtifactError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
