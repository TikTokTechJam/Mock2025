# Model manifests

This directory contains logical model manifests such as face, plate, OCR,
speech, and PII metadata. Issue #14 owns the manifest schema, bootstrap,
checksum validation, and artifact resolver.

Every manifest is a JSON object with these required string fields:

```json
{
  "model_id": "plate-detector",
  "version": "v1",
  "filename": "plate-detector.pt",
  "source": "https://public.example/plate-detector.pt",
  "sha256": "64 lowercase hexadecimal characters",
  "license": "upstream license identifier"
}
```

The resolver stores verified artifacts under `.cache/models/<model_id>/<version>/`.

Do not place downloaded weights or provider credentials here.
