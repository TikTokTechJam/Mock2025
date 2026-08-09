"""JSON-file database for enrolled whitelist identities.

The file holds biometric-derived data (`SECURITY.md` §3, §6) and is the only
place this component writes anything to disk. It is written with owner-only
permissions, replaced atomically so a crash mid-write cannot leave a truncated
whitelist behind, and never written to a log or diagnostics channel.

File-level access control is the protection here; the contents are not
encrypted. Treat the path as sensitive storage — restrict it to the detector
service, keep it out of backups and version control unless those are covered by
the same controls, and delete it when the enrollments it holds are revoked.

Layout::

    {
      "version": 1,
      "identities": {
        "<identity id>": {
          "consent_record_id": "<record in the consent flow>",
          "embeddings": [[<float>, ...], ...]
        }
      }
    }

Every embedding is L2-normalized before it is written, and re-normalized when it
is read, so a hand-edited file cannot skew a similarity comparison.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

from .embeddings import Embedding, as_embedding, l2_normalize
from .errors import WhitelistStorageError

SCHEMA_VERSION = 1

_FILE_MODE = 0o600
_DIRECTORY_MODE = 0o700


@dataclass(frozen=True, slots=True)
class StoredIdentity:
    """One enrolled identity as it is persisted."""

    consent_record_id: str
    embeddings: tuple[Embedding, ...]


def read_whitelist(path: Path) -> dict[str, StoredIdentity]:
    """Load the whitelist database.

    A missing file is an empty whitelist — no enrollment exists yet, so every
    face will be protected, which is the correct default rather than a degraded
    state. A file that exists but cannot be parsed raises instead: silently
    treating it as empty would blur the enrolled creator forever with no signal,
    and silently keeping the readable half would be worse.

    No message raised from here echoes file contents.
    """

    if not path.exists():
        return {}
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except OSError as error:
        raise WhitelistStorageError("whitelist database could not be read") from error
    except json.JSONDecodeError as error:
        raise WhitelistStorageError("whitelist database is not valid JSON") from error
    if not isinstance(document, dict):
        raise WhitelistStorageError("whitelist database must contain a JSON object")
    version = document.get("version")
    if version != SCHEMA_VERSION:
        raise WhitelistStorageError(
            f"whitelist database schema version {version!r} is not supported"
        )
    identities = document.get("identities")
    if not isinstance(identities, dict):
        raise WhitelistStorageError("whitelist database is missing its identities object")
    return {
        identity_id: _read_identity(identity_id, entry) for identity_id, entry in identities.items()
    }


def _read_identity(identity_id: str, entry: object) -> StoredIdentity:
    if not identity_id.strip():
        raise WhitelistStorageError("whitelist database contains an empty identity id")
    if not isinstance(entry, dict):
        raise WhitelistStorageError(f"identity {identity_id!r} is not an object")
    consent_record_id = entry.get("consent_record_id")
    if not isinstance(consent_record_id, str) or not consent_record_id.strip():
        raise WhitelistStorageError(f"identity {identity_id!r} has no consent record")
    raw_embeddings = entry.get("embeddings")
    if not isinstance(raw_embeddings, list) or not raw_embeddings:
        raise WhitelistStorageError(f"identity {identity_id!r} has no reference embeddings")
    embeddings: list[Embedding] = []
    for raw in raw_embeddings:
        if not isinstance(raw, list):
            raise WhitelistStorageError(f"identity {identity_id!r} has a malformed embedding")
        try:
            embeddings.append(l2_normalize(as_embedding(raw)))
        except (TypeError, ValueError) as error:
            raise WhitelistStorageError(
                f"identity {identity_id!r} has an unusable embedding"
            ) from error
    if len({len(embedding) for embedding in embeddings}) != 1:
        raise WhitelistStorageError(
            f"identity {identity_id!r} mixes embeddings of different dimensions"
        )
    return StoredIdentity(consent_record_id=consent_record_id, embeddings=tuple(embeddings))


def write_whitelist(path: Path, identities: dict[str, StoredIdentity]) -> None:
    """Replace the whitelist database atomically, owner-readable only.

    A revocation is only complete once this returns, so the write is a rename
    over the previous file rather than an in-place edit: a reader either sees
    the whole previous whitelist or the whole new one, never a partial list that
    would leave a revoked identity matchable.
    """

    document = {
        "version": SCHEMA_VERSION,
        "identities": {
            identity_id: {
                "consent_record_id": identity.consent_record_id,
                "embeddings": [list(embedding) for embedding in identity.embeddings],
            }
            for identity_id, identity in identities.items()
        },
    }
    temporary = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    try:
        path.parent.mkdir(mode=_DIRECTORY_MODE, parents=True, exist_ok=True)
        # Open with the restricted mode rather than chmod-ing afterwards, so the
        # embeddings are never on disk in a world-readable file, even briefly.
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, _FILE_MODE)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                json.dump(document, handle)
                handle.flush()
                os.fsync(handle.fileno())
        except BaseException:
            temporary.unlink(missing_ok=True)
            raise
        os.replace(temporary, path)
    except OSError as error:
        raise WhitelistStorageError("whitelist database could not be written") from error


def delete_whitelist(path: Path) -> None:
    """Remove the database file entirely, for a revoke-everything operation."""

    try:
        path.unlink(missing_ok=True)
    except OSError as error:
        raise WhitelistStorageError("whitelist database could not be deleted") from error
