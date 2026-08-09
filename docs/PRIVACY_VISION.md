# Visual Privacy Module

## Purpose

This document owns the standalone visual-privacy implementation for license
plates and structured on-screen PII, plus thin production adapters for
registering the plate and OCR/visual-PII detectors with the shared video engine.
The standalone path remains independently runnable and does not require WebRTC
or other detector modules.

## Availability

The standalone adapters, production plate and OCR/visual-PII adapters,
deterministic tests, and local image/video demo are Implemented in source.
Running a real model requires the optional `vision` dependency group, a local
YOLO-family plate weight file, and local OCR model assets. Runtime verification
and real-model fixture verification are Unverified.

## Components

| Component | Implementation | Replaceable boundary |
| --- | --- | --- |
| Plate detector | `UltralyticsPlateDetector` using a local YOLO-family weight file | `PlateModel.predict` |
| Production plate adapter | `PlateVideoDetector` and `register_plate_detector` | `FrameImageProvider` and #4 scheduler settings |
| OCR engine | `EasyOcrEngine` by default | `OcrEngine.read` |
| Production OCR/PII adapter | `OcrVideoDetector` and `register_ocr_detector` | `FrameImageProvider` and #4 scheduler settings |
| Shared text-PII recognizer | Shared normalized text-PII service used by OCR and spoken paths; detailed contract is in [PRIVACY_TEXT_PII.md](PRIVACY_TEXT_PII.md) | `privastream_api.privacy.text_pii` |
| Composition service | `VisionPrivacyService` concatenates independent results | `VisualPrivacyDetector.detect` |

The default OCR language is English (`en`). Additional EasyOCR language codes
may be provided through repeated `--ocr-language` options or by constructing
`OcrDetectorConfig` directly. The module does not claim coverage for languages
or scripts that are not present in the configured OCR engine.

## Plate path

`UltralyticsPlateDetector` requires a local weight path. It does not download a
model during request or demo handling. A dedicated plate model may accept every
returned class; general models can be restricted with `class_names`.

For each configured standalone inference frame, `UltralyticsPlateDetector.detect()`:

1. square-letterboxes the source image;
2. runs the configured model and confidence threshold;
3. maps model-input boxes back to the original pixel dimensions;
4. applies proportional region padding;
5. clamps the region to the original frame; and
6. emits a normalized `VideoRegionDetection(kind="license_plate")`.

The normalized coordinates are relative to the original frame, not the model
input. The default confidence threshold is `0.45`, model input is `640`, and
padding is `0.02` of the frame width and height.

The production adapter calls `detect_source_frame()` so the same inference and
coordinate mapping implementation emits detector-native source-frame geometry
without standalone padding, cadence, or TTL reuse. `register_plate_detector()`
passes cadence, deadline, TTL, and concurrency settings to
`VideoOrchestrator`; the shared engine applies production padding exactly once.
The adapter accepts an injectable `FrameImageProvider` because the canonical
`VideoFrame.payload` is intentionally opaque to the model runtime.

## OCR and PII path

`OcrEngine` returns in-memory OCR blocks containing only text, polygon, and
confidence. The default EasyOCR adapter is lazy and is never initialized at
module import time. Visual OCR normalization applies Unicode NFKC normalization,
case folding, whitespace collapsing, and limited OCR punctuation cleanup before
calling the shared `TextPiiRecognizer`. Spoken-transcript normalization remains
owned by the spoken path; both paths then consume the same recognizer service.
The shared contract, taxonomy, configuration, and failure semantics are owned
by [PRIVACY_TEXT_PII.md](PRIVACY_TEXT_PII.md).

Benign OCR text, dates, prices, and short/random numeric strings are not
redacted automatically. If a block contains sensitive content and
character-to-sub-box mapping is unavailable, the whole block is returned as a
privacy region. A block containing multiple PII categories is emitted as
`kind="custom_sensitive_text"` so the compositor can apply the privacy action
without making a false precision claim. Raw OCR text and matched values are
never written to application output.

The standalone OCR default threshold is `0.4`, cadence is every 5 frames, and
the latest regions may be reused for 2 subsequent frames. Plate cadence, OCR
cadence, region TTL, threshold, padding, languages, and GPU use are
independently configurable. Production OCR scheduling is configured separately
through `OcrOrchestrationConfig`.

The production OCR adapter calls `detect_source_frame()` so OCR confidence
filtering, visual normalization, shared text-PII recognition, and OCR-block
mapping are reused without standalone padding, cadence, or TTL reuse.
`register_ocr_detector()` passes cadence, deadline, TTL, and concurrency settings
to `VideoOrchestrator`; the shared engine applies production padding exactly
once. When character-to-sub-box geometry is unavailable, the sensitive span is
mapped conservatively to its complete source OCR block.

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

When the ML handoff manifest is available, replace `--plate-weights` with
`--plate-model plate-detector`. The model resolver fetches the versioned local
artifact and verifies its checksum before the detector loads it. The repository
does not currently contain a production plate manifest or weight.

The demo accepts an image or short video, runs the selected adapters, applies
local OpenCV blur masks, and writes a protected image or video. Its summary
reports frame and region counts only; it does not print recognized text.

## Limitations and failure behavior

- Pretrained public plate weights are supported; Singapore-specific training is
  future work.
- The module does not implement sophisticated tracking, WebRTC, streaming,
  HTTP media ingestion, or the final fail-closed publication decision. Shared
  temporal coordination and composition are owned by the video engine; the
  production plate and OCR/PII adapters only register detectors and return
  source-frame regions.
- OCR/model or contextual-recognizer failures surface as explicit detector or
  text-recognizer errors and are not converted to an empty result. A caller
  integrating this module must apply the platform's fail-closed policy before
  releasing output; see [PRIVACY_TEXT_PII.md](PRIVACY_TEXT_PII.md) for the
  shared error contract.
- Unit tests use deterministic model/OCR doubles. Real-model accuracy,
  language coverage, latency, and output quality remain Unverified.
