# Visual Privacy Module

## Purpose

This document owns the standalone visual-privacy implementation for license
plates and structured on-screen PII. It is an independently runnable API
workstream and does not require WebRTC, the shared compositor, or other
detector modules.

## Availability

The adapter code, deterministic tests, and local image/video demo are
Implemented in source. Running a real model requires the optional `vision`
dependency group, a local YOLO-family plate weight file, and local OCR model
assets. Runtime verification and real-model fixture verification are Unverified.

## Components

| Component | Implementation | Replaceable boundary |
| --- | --- | --- |
| Plate detector | `UltralyticsPlateDetector` using a local YOLO-family weight file | `PlateModel.predict` |
| OCR engine | `EasyOcrEngine` by default | `OcrEngine.read` |
| PII classifier | Deterministic email and phone recognizers | `classify_pii` |
| Composition service | `VisionPrivacyService` concatenates independent results | `VisualPrivacyDetector.detect` |

The default OCR language is English (`en`). Additional EasyOCR language codes
may be provided through repeated `--ocr-language` options or by constructing
`OcrDetectorConfig` directly. The module does not claim coverage for languages
or scripts that are not present in the configured OCR engine.

## Plate path

`UltralyticsPlateDetector` requires a local weight path. It does not download a
model during request or demo handling. A dedicated plate model may accept every
returned class; general models can be restricted with `class_names`.

For each configured inference frame, the adapter:

1. square-letterboxes the source image;
2. runs the configured model and confidence threshold;
3. maps model-input boxes back to the original pixel dimensions;
4. applies proportional region padding;
5. clamps the region to the original frame; and
6. emits a normalized `VideoRegionDetection(kind="license_plate")`.

The normalized coordinates are relative to the original frame, not the model
input. The default confidence threshold is `0.45`, model input is `640`, and
padding is `0.02` of the frame width and height.

## OCR and PII path

`OcrEngine` returns in-memory OCR blocks containing only text, polygon, and
confidence. The default EasyOCR adapter is lazy and is never initialized at
module import time. Before matching, the classifier applies Unicode NFKC
normalization, case folding, whitespace collapsing, and limited OCR punctuation
cleanup.

The MVP recognizes:

- email addresses; and
- phone-like numbers containing 8 to 15 digits, with common separators and an
  optional country-code prefix.

Benign OCR text is not redacted automatically. If a block contains sensitive
content and character-to-sub-box mapping is unavailable, the whole block is
returned as a privacy region. A block containing multiple PII kinds is emitted
as `kind="text"` so the compositor can apply the privacy action without making
a false precision claim. Raw OCR text is never written to application output.

The default OCR threshold is `0.4`, cadence is every 5 frames, and the latest
regions may be reused for 2 subsequent frames. Plate cadence, OCR cadence,
region TTL, threshold, padding, languages, and GPU use are independently
configurable.

## Standalone demo

From `apps/api`:

~~~bash
uv sync --extra vision
uv run python scripts/vision_demo.py \
  --input demo.mp4 \
  --output protected.mp4 \
  --plate \
  --plate-weights weights/license_plate.pt \
  --ocr-pii
~~~

The demo accepts an image or short video, runs the selected adapters, applies
local OpenCV blur masks, and writes a protected image or video. Its summary
reports frame and region counts only; it does not print recognized text.

## Limitations and failure behavior

- Pretrained public plate weights are supported; Singapore-specific training is
  future work.
- The module does not implement sophisticated tracking, WebRTC, streaming, or
  shared compositor integration. Cadence and short TTL reuse are the only
  temporal controls here.
- OCR/model failures surface as detector errors and are not converted to an
  empty result. A caller integrating this module must apply the platform's
  fail-closed policy before releasing output.
- Unit tests use deterministic model/OCR doubles. Real-model accuracy,
  language coverage, latency, and output quality remain Unverified.
