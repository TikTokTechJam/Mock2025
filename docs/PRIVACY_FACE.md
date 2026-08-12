# Face Privacy Module

## Purpose

This document owns the standalone face detector, creator enrollment, embedding
matching, and local image/clip runner. The production adapter, process-local
enrollment repository, readiness handoff, and protected HTTP control surface are
implemented in `privastream_api.privacy.face.production` and documented here as
integration boundaries. The standalone module still does not own temporal
retention, padding, compositor policy, transport, durable persistence, or UI.

## Availability

The model-neutral face module, deterministic tests, local InsightFace/ArcFace
adapter boundary, in-memory creator store, and standalone runner are
Implemented in source. Runtime verification, real-model accuracy, threshold
calibration, representative face fixtures, and the production integration are
Unverified.

## Components

| Component | Implementation | Boundary |
| --- | --- | --- |
| Face model adapter | `InsightFaceFaceModel` with a local `buffalo_l`-style InsightFace model pack | `FaceModel.detect` |
| Embedding lifecycle | `CreatorFaceEnrollmentService` and `InMemoryCreatorEmbeddingStore` | consented samples in, safe enrollment metadata out |
| Creator matching | `CreatorFaceDetector` | `FrameContext` in, normalized `VideoRegionDetection` out |
| Production integration | `ProductionFaceIntegration`, `FaceEnrollmentRepository`, and `FaceReadinessTracker` | #4 adapter, #3 lifecycle, sanitized #13 readiness input, and optional #14 verified pack resolution |
| Local runner | `apps/api/scripts/face_demo.py` | image or short clip in, locally blurred copy out |

The standalone adapter loads InsightFace lazily and requires a local model pack
under the configured `model_root`. It does not download model weights during
detection. The production integration can resolve an `insightface-pack` archive
manifest through #14 before constructing the adapter; the extracted pack must
use the `models/<model_name>/...` layout. The default embedding path uses the
ArcFace embedding exposed by InsightFace.

## Enrollment

Enrollment requires an explicit `consent=True` operation. The service accepts a
bounded set of samples, rejects samples with zero faces or multiple faces,
rejects low-confidence/low-quality or failed embeddings, L2-normalizes valid
embeddings, averages them, and normalizes the aggregate again. A valid new
enrollment replaces the previous in-memory creator record. Delete removes it.

Only the aggregate embedding and safe lifecycle metadata are retained by the
hackathon store. Source images are processed through the model and are not
stored by the enrollment service. Embedding values never appear in the status,
runner summary, or module representations.

## Matching and regions

For each detected face:

1. no enrollment produces `no_enrollment` and protects the face;
2. low detection confidence or quality produces `low_quality` and protects it;
3. a missing or invalid embedding produces `embedding_failed` and protects it;
4. an unknown or dimension-mismatched embedding produces `unknown` and protects it;
5. a similarity inside the configured ambiguity band produces `ambiguous` and protects it;
6. only a similarity above the configured creator threshold plus margin is treated as `creator`.

Creator matches emit no privacy region. Every other detected face emits a
`VideoRegionDetection(kind="face_bystander")` with source-frame pixel geometry
clamped to normalized `[0, 1]` bounds. The detector does not apply production
padding or temporal retention; those belong to the shared video engine and its
future production registration.

The cross-modal synchronizer consumes normalized face geometry after this
adapter boundary. It does not invoke the face model, perform identity matching,
or retain embeddings; a supplied lower-face/landmark region or active-speaker
hint remains optional, and the synchronizer uses the face box conservatively
when those hints are unavailable.

Model errors remain detector errors. They are not converted into an empty
successful result. A downstream safety boundary must decide how to hold or
fail closed when the face detector is required.

## Standalone runner

From `apps/api`:

~~~bash
uv sync --extra face
uv run python scripts/face_demo.py \
  --input demo.mp4 \
  --output protected.mp4 \
  --model-root models/insightface
~~~

To enroll explicitly supplied creator images, repeat `--enrollment` and add
`--consent`:

~~~bash
uv run python scripts/face_demo.py \
  --input demo.mp4 \
  --output protected.mp4 \
  --enrollment creator-1.jpg \
  --enrollment creator-2.jpg \
  --consent \
  --model-root models/insightface
~~~

The runner uses a small local blur margin only as a demonstration helper. It
does not represent the production compositor or publication-safety decision.
Its summary reports frame and protected-region counts only.

## Limitations

- The model pack, ONNX runtime, and optional face dependencies are local runtime
  inputs; no weights are committed.
- This module supports one creator and does not identify bystanders or retain
  their embeddings.
- Thresholds require calibration across lighting, pose, masks, occlusion, and
  camera quality. Real-model behavior is Unverified.
- The user-facing enrollment journey, durable database repository, authorization
  provider, temporal composition, transport, and fail-closed publication gate
  remain outside the standalone implementation. The production adapter and
  process-local control surface are separate #5 integration code paths.
